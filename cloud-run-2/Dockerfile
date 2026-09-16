# 빌드 컨텍스트는 저장소 루트다. (소스는 compute-engine/ 의 것을 그대로 사용)
#   docker build -f cloud-run-2/Dockerfile -t chatbot-adc .
# 인증은 API 키가 아니라 ADC(실행 환경의 신원)를 사용한다. 관련 환경변수는 배포 시 지정한다.
FROM python:3.13-slim

WORKDIR /app

COPY compute-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY compute-engine/app.py .
COPY compute-engine/static ./static

# Cloud Run 이 주입하는 PORT 로 listen 한다 (로컬 실행 시 기본 8080).
CMD exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}
