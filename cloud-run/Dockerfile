# 빌드 컨텍스트는 저장소 루트다. (소스는 compute-engine/ 의 것을 그대로 사용)
#   docker build -f cloud-run/Dockerfile -t chatbot .
FROM python:3.13-slim

WORKDIR /app

COPY compute-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY compute-engine/app.py .
COPY compute-engine/static ./static

# Cloud Run 이 주입하는 PORT 로 listen 한다 (로컬 실행 시 기본 8080).
CMD exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}
