# gcp-compute-engine-chatbot

`gemini-3.8-flash` 기반 웹 챗봇을 GCP 에 배포해 보는 저장소입니다.

| 폴더 | 내용 |
|---|---|
| [`compute-engine/`](compute-engine/) | FastAPI 챗봇 + Compute Engine VM 배포 (Secret Manager, systemd, Caddy HTTPS) |
| [`cloud-run/`](cloud-run/) | 같은 챗봇을 컨테이너로 Cloud Run 에 배포 (Dockerfile, Cloud Build) |

챗봇 소스는 `compute-engine/` 에 있고, `cloud-run/` 은 이를 복제 없이 그대로 빌드합니다.

## 빠른 시작
```bash
cd compute-engine
export GEMINI_API_KEY="발급받은_키"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app:app --reload
```
자세한 실행·배포 방법은 [compute-engine/README.md](compute-engine/README.md), 실제 배포 기록은 [compute-engine/DEPLOY.md](compute-engine/DEPLOY.md) 를 참고하세요.
