#!/bin/bash
# VM 에서 챗봇 실행: Secret Manager 에서 키를 조회해 프로세스 환경변수로만 전달한다 (디스크에 저장하지 않음).
set -euo pipefail

SECRET_NAME="${SECRET_NAME:-GEMINI_API_KEY}"

export GEMINI_API_KEY="$(gcloud secrets versions access latest --secret="$SECRET_NAME")"
# 외부 접속은 Caddy(443) 가 받아 127.0.0.1:8000 으로 전달한다.
exec /opt/chatbot/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
