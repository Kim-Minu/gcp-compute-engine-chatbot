"""Gemini 기반 웹 챗봇 서버 (로컬 실행용)."""

from pydantic import functional_serializers
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from pydantic import BaseModel

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
STATIC_DIR = Path(__file__).parent / "static"

# ADC 모드: GOOGLE_GENAI_USE_VERTEXAI=true 이면 API 키 대신 실행 환경의 신원(ADC)으로 인증한다.
# (Cloud Run 에서는 런타임 서비스 계정이 곧 ADC 이므로 키가 필요 없다.)
USE_VERTEXAI = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in {"1", "true", "yes"}

if not USE_VERTEXAI and not os.environ.get("GEMINI_API_KEY"):
    raise RuntimeError(
        "환경변수 GEMINI_API_KEY 가 설정되어 있지 않습니다. "
        "(ADC 를 쓰려면 GOOGLE_GENAI_USE_VERTEXAI=true 와 GOOGLE_CLOUD_PROJECT/LOCATION 을 설정)"
    )

# genai.Client() 는 GEMINI_API_KEY 또는 GOOGLE_GENAI_USE_VERTEXAI/GOOGLE_CLOUD_* 환경변수를 자동으로 읽는다.
client = genai.Client()
# 도구(function calling)를 쓰지 않으므로 AFC 를 꺼서 불필요한 경고를 막는다.
GEN_CONFIG = types.GenerateContentConfig(
    # Google 검색 그라운딩: 날씨·뉴스 등 실시간 정보가 필요하면 모델이 스스로 검색한다.
    tools=[types.Tool(google_search=types.GoogleSearch())],
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False),
)
app = FastAPI(title="Gemini Chatbot")


class Message(BaseModel):
    role: Literal["user", "model"]
    text: str


class ChatRequest(BaseModel):
    messages: list[Message]


def event(**data) -> str:
    """NDJSON 한 줄 (text / sources / error 이벤트)."""
    return json.dumps(data, ensure_ascii=False) + "\n"


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "model": MODEL}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    if not req.messages or req.messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="마지막 메시지는 user 역할이어야 합니다.")

    contents = [
        types.Content(role=m.role, parts=[types.Part(text=m.text)])
        for m in req.messages
    ]

    async def stream():
        sources: dict[str, str] = {}  # uri -> title (중복 제거, 순서 유지)
        search_html = None
        try:
            async for chunk in await client.aio.models.generate_content_stream(
                model=MODEL, contents=contents, config=GEN_CONFIG
            ):
                if chunk.text:
                    yield event(type="text", text=chunk.text)

                meta = chunk.candidates[0].grounding_metadata if chunk.candidates else None
                if not meta:
                    continue
                for gc in meta.grounding_chunks or []:
                    if gc.web and gc.web.uri:
                        sources.setdefault(gc.web.uri, gc.web.title or gc.web.domain or gc.web.uri)
                if meta.search_entry_point and meta.search_entry_point.rendered_content:
                    search_html = meta.search_entry_point.rendered_content
        except Exception as e:  # 스트림 도중 오류는 이벤트로 전달
            yield event(type="error", message=str(e))
            return

        if sources or search_html:
            yield event(
                type="sources",
                sources=[{"title": t, "uri": u} for u, t in sources.items()],
                search_html=search_html,
            )

    return StreamingResponse(stream(), media_type="application/x-ndjson")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
