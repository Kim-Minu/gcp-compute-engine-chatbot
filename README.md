# gcp-compute-engine-chatbot

Gemini 기반 웹 챗봇을 GCP 에 여러 방식으로 배포해 보는 저장소입니다.

| 폴더 | 내용 |
|---|---|
| [`compute-engine/`](compute-engine/) | FastAPI 챗봇 + Compute Engine VM 배포 (Secret Manager, systemd, Caddy HTTPS) |
| [`cloud-run/`](cloud-run/) | 같은 챗봇을 컨테이너로 Cloud Run 에 배포 (API 키 + Secret Manager) |
| [`cloud-run-2/`](cloud-run-2/) | 같은 챗봇을 Cloud Run 에 배포하되 **API 키 없이 ADC** 로 인증 (Vertex AI) |

챗봇 소스는 `compute-engine/` 에만 있고, `cloud-run/` 과 `cloud-run-2/` 는 이를 복제 없이 그대로 빌드합니다.
배포 방식의 차이는 코드가 아니라 **환경변수**로 표현됩니다.

## 빠른 시작
```bash
cd compute-engine
export GEMINI_API_KEY="발급받은_키"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app:app --reload
```

## 문서
| 배포 방식 | 가이드 | 배포 기록 |
|---|---|---|
| Compute Engine VM | [compute-engine/README.md](compute-engine/README.md) | [compute-engine/DEPLOY.md](compute-engine/DEPLOY.md) |
| Cloud Run (API 키) | [cloud-run/README.md](cloud-run/README.md) | [cloud-run/DEPLOY.md](cloud-run/DEPLOY.md) |
| Cloud Run (ADC) | [cloud-run-2/README.md](cloud-run-2/README.md) | [cloud-run-2/DEPLOY.md](cloud-run-2/DEPLOY.md) |

> 실습으로 만든 GCP 리소스(VM, 고정 IP, 방화벽, Cloud Run 서비스, 컨테이너 이미지)는 모두 삭제했습니다.
> 시크릿 `GEMINI_API_KEY` 만 남아 있습니다.
