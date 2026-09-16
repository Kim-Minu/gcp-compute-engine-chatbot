# cloud-run

[`compute-engine/`](../compute-engine/) 의 챗봇을 컨테이너로 만들어 Cloud Run 에 배포합니다.
소스는 복제하지 않고 `compute-engine/` 의 파일을 그대로 빌드합니다.

실제 배포 과정과 현재 상태는 [DEPLOY.md](DEPLOY.md) 에 정리되어 있습니다.

| 파일 | 내용 |
|---|---|
| `Dockerfile` | python:3.13-slim 기반. 빌드 컨텍스트는 **저장소 루트** |
| `cloudbuild.yaml` | 루트를 컨텍스트로 두고 `cloud-run/Dockerfile` 로 빌드 |

## Compute Engine 배포와의 차이
| 항목 | Compute Engine | Cloud Run |
|---|---|---|
| 키 주입 | `deploy/start.sh` 가 Secret Manager 조회 | `--set-secrets` 로 환경변수 주입 |
| HTTPS | Caddy + Let's Encrypt 직접 구성 | 기본 제공 (`*.run.app`) |
| 포트 | 8000 고정 | `PORT` 환경변수 (기본 8080) |
| 자동 시작 | systemd `enable` | 요청이 오면 자동 기동, 없으면 0개로 축소 |
| 방화벽·고정 IP | 직접 설정 | 불필요 |
| access scope | `cloud-platform` 필요 | 개념 없음 (IAM 만 사용) |

`app.py` 는 수정하지 않습니다. `Dockerfile` 의 `CMD` 가 셸 형식이라 컨테이너 시작 시 `PORT` 가 채워집니다.

## 로컬 확인 (선택)
```bash
# 저장소 루트에서
docker build -f cloud-run/Dockerfile -t chatbot-local .
docker run --rm -p 8080:8080 -e GEMINI_API_KEY="발급받은_키" chatbot-local
# http://127.0.0.1:8080
```

## 배포

### 변수 [로컬]
```bash
PROJECT=iceu-songpa05
REGION=asia-northeast3
REPO=chatbot
SERVICE=chatbot
IMAGE=$REGION-docker.pkg.dev/$PROJECT/$REPO/chatbot:latest
SECRET=GEMINI_API_KEY
```

### 1. API 활성화 · Artifact Registry 저장소 생성
```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com --project=$PROJECT

gcloud artifacts repositories create $REPO \
  --repository-format=docker --location=$REGION --project=$PROJECT
```

### 2. 이미지 빌드 (저장소 루트에서 실행)
빌드는 저장소 전체를 업로드하므로, 루트의 `.gcloudignore` 로 `.venv/`, `__pycache__/`, `.git/`, `.omc/` 를 제외합니다.
```bash
gcloud builds submit --config cloud-run/cloudbuild.yaml \
  --substitutions=_IMAGE=$IMAGE --project=$PROJECT .
```

### 3. 배포
먼저 비공개(인증 필요)로 배포해 컨테이너가 정상 기동하는지 확인한다.
```bash
gcloud run deploy $SERVICE \
  --image=$IMAGE --region=$REGION --project=$PROJECT \
  --set-secrets=GEMINI_API_KEY=$SECRET:latest \
  --no-allow-unauthenticated
```
확인 후 공개로 전환한다. (배포 시 `--allow-unauthenticated` 를 주면 한 번에 공개로 배포된다)
```bash
gcloud run services add-iam-policy-binding $SERVICE \
  --region=$REGION --project=$PROJECT \
  --member=allUsers --role=roles/run.invoker
```
> 공개하면 주소를 아는 누구나 이 챗봇으로 Gemini 사용량을 소모할 수 있다.

런타임 서비스 계정에 시크릿 조회 권한이 없으면 컨테이너가 시작되지 않습니다.
```bash
SA_EMAIL=$(gcloud projects describe $PROJECT --format='value(projectNumber)')-compute@developer.gserviceaccount.com
gcloud secrets add-iam-policy-binding $SECRET \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/secretmanager.secretAccessor" --project=$PROJECT
```

### 4. 확인
```bash
URL=$(gcloud run services describe $SERVICE --region=$REGION --project=$PROJECT --format='value(status.url)')
curl $URL/api/health        # {"status":"ok","model":"gemini-3.8-flash"}
echo $URL                   # 브라우저로 접속
```

### 코드 변경 후 재배포
2번(빌드)과 3번(배포)을 다시 실행하면 됩니다.

## 로그
```bash
gcloud run services logs read $SERVICE --region=$REGION --project=$PROJECT --limit=50
```

## 문제 해결
| 증상 | 원인 | 해결 |
|---|---|---|
| 배포 시 `container failed to start` | 시크릿 접근 실패 또는 PORT 미사용 | 3번의 권한 부여, 로그 확인 |
| `PERMISSION_DENIED` (빌드) | Cloud Build 서비스 계정 권한 부족 | 빌드 계정에 `roles/cloudbuild.builds.builder` 부여 |
| 첫 요청이 느림 | 인스턴스 0개에서 기동 (cold start) | 필요 시 `--min-instances=1` (상시 과금) |

## 리소스 정리 (과금 방지)
```bash
gcloud run services delete $SERVICE --region=$REGION --project=$PROJECT --quiet
gcloud artifacts repositories delete $REPO --location=$REGION --project=$PROJECT --quiet
```
Cloud Run 은 요청이 없으면 인스턴스가 0 개로 줄어 비용이 거의 들지 않지만, Artifact Registry 의 이미지 저장 용량에는 요금이 부과됩니다.
