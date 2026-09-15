# gcp-compute-engine-chatbot
GCP Compute Engine 챗봇 구현 해보기

`gemini-3.8-flash` 모델 기반으로 로컬 PC에서 동작하는 웹 챗봇입니다.

## 구성
- `app.py` — FastAPI 서버. `/api/chat` 에서 Gemini 응답을 스트리밍으로 전달
- `static/index.html` — 채팅 UI (빌드 과정 없는 단일 HTML)

## 실행
```bash
export GEMINI_API_KEY="발급받은_키"   # 필수
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app:app --reload
```
브라우저에서 http://127.0.0.1:8000 접속

## 환경변수
| 이름 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `GEMINI_API_KEY` | O | – | Gemini API 키 |
| `GEMINI_MODEL` | X | `gemini-3.8-flash` | 사용할 모델 ID |
