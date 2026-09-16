# cloud-run-2 (ADC 인증)

[`compute-engine/`](../compute-engine/) 의 챗봇을 Cloud Run 에 배포하되, **API 키 대신 ADC(애플리케이션 기본 사용자 인증 정보)** 로 인증합니다.
소스는 복제하지 않고 `compute-engine/` 의 파일을 그대로 빌드합니다.

실제 배포 과정과 겪은 문제는 [DEPLOY.md](DEPLOY.md) 에 정리되어 있습니다.

## [`cloud-run/`](../cloud-run/) 과의 차이

| 항목 | cloud-run (API 키) | cloud-run-2 (ADC) |
|---|---|---|
| 인증 | Secret Manager 의 `GEMINI_API_KEY` 주입 | 런타임 서비스 계정의 신원 그대로 |
| 호출 대상 | Gemini API | Vertex AI 의 Gemini |
| 배포 옵션 | `--set-secrets=GEMINI_API_KEY=…` | `--set-env-vars=GOOGLE_GENAI_USE_VERTEXAI=true,…` |
| 필요한 권한 | 시크릿 `secretmanager.secretAccessor` | 프로젝트 `roles/aiplatform.user` |
| 관리할 키 | 있음 (유출·회전·시크릿 요금) | **없음** |
| 할당량 | Gemini API 할당량 | **Vertex AI 할당량** (모델별로 잡힘) |

```
cloud-run  :  컨테이너 → GEMINI_API_KEY (Secret Manager) → Gemini API
cloud-run-2:  컨테이너 → 런타임 서비스 계정 신원(ADC)     → Vertex AI 의 Gemini
```

`app.py` 는 `GOOGLE_GENAI_USE_VERTEXAI=true` 일 때 API 키 검사를 건너뛰고, `google-genai` SDK 가 ADC 로 인증합니다. 이 변수가 없으면 기존과 동일하게 동작합니다.

## 배포

### 변수 [로컬]
```bash
PROJECT=iceu-songpa05
REGION=asia-northeast3           # Cloud Run 서비스가 뜨는 리전
LOCATION=global                  # Vertex AI 엔드포인트 위치
MODEL=gemini-2.5-flash           # 아래 "모델과 위치 고르기" 참고
REPO=chatbot
SERVICE=chatbot-adc
IMAGE=$REGION-docker.pkg.dev/$PROJECT/$REPO/chatbot-adc:latest
SA_EMAIL=307601624742-compute@developer.gserviceaccount.com
```

### 1. API 활성화 · 권한 부여
```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com aiplatform.googleapis.com --project=$PROJECT

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:$SA_EMAIL" --role="roles/aiplatform.user"
```

### 2. Artifact Registry 저장소 (없으면)
```bash
gcloud artifacts repositories create $REPO \
  --repository-format=docker --location=$REGION --project=$PROJECT
```

### 3. 이미지 빌드 (저장소 루트에서 실행)
루트의 `.gcloudignore` 로 `.venv/`, `__pycache__/`, `.git/`, `.omc/` 를 제외합니다.
```bash
gcloud builds submit --config cloud-run-2/cloudbuild.yaml \
  --substitutions=_IMAGE=$IMAGE --project=$PROJECT .
```

### 4. 배포
시크릿을 주입하지 않는 것이 핵심입니다.
```bash
gcloud run deploy $SERVICE \
  --image=$IMAGE --region=$REGION --project=$PROJECT \
  --set-env-vars=GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$LOCATION,GEMINI_MODEL=$MODEL \
  --no-allow-unauthenticated
```
모델·위치는 환경변수이므로 **이미지 재빌드 없이** 바꿀 수 있습니다.
```bash
gcloud run services update $SERVICE --region=$REGION --project=$PROJECT \
  --update-env-vars=GEMINI_MODEL=gemini-2.5-flash
```

### 5. 확인
```bash
URL=$(gcloud run services describe $SERVICE --region=$REGION --project=$PROJECT --format='value(status.url)')
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" $URL/api/health

# 브라우저로 채팅까지 확인 (비공개 유지)
gcloud run services proxy $SERVICE --region $REGION --project $PROJECT
# http://127.0.0.1:8080
```
`/api/health` 는 모델을 호출하지 않으므로, ADC 인증이 실제로 되는지는 **채팅을 한 번 보내야** 확인됩니다.

## 모델과 위치 고르기
Vertex AI 는 **모델별·위치별로 제공 여부와 할당량이 다릅니다.** 실제 배포에서 확인한 조합:

| 모델 | 위치 | 결과 |
|---|---|---|
| `gemini-3.8-flash` | `global` | 제공되지만 할당량 부족으로 **429 빈발** |
| `gemini-3.8-flash` | `us-central1` | **404** (해당 리전 미제공) |
| `gemini-2.5-flash` | `global` | **정상** (약 4초 응답, 검색 그라운딩 포함) |

## 문제 해결
| 증상 | 원인 | 해결 |
|---|---|---|
| 응답 없이 대기하다 `{"type":"error"} 429 RESOURCE_EXHAUSTED` | Vertex AI **할당량 부족** (모델 단위) | 할당량이 여유로운 모델로 `GEMINI_MODEL` 변경, 또는 Cloud Quotas 에서 상향 요청 |
| `{"type":"error"} 404 ... model was not found` (JSON) | 해당 **위치에 모델 미제공** | `GOOGLE_CLOUD_LOCATION` 변경 (기본값 `global` 권장) |
| `403 ... aiplatform` | 런타임 서비스 계정 권한 부족 | 1번의 `aiplatform.user` 부여 |
| 컨테이너 시작 실패 (`GEMINI_API_KEY ...`) | `GOOGLE_GENAI_USE_VERTEXAI` 미설정 | 4번 `--set-env-vars` 확인 |
| 모델 메타데이터 조회가 **HTML 404** | 존재하지 않는 REST 경로 | 가용성은 조회 대신 실제 호출로 판단 |

> 오류가 **JSON** 이면 API 가 돌려준 진짜 오류이고, **HTML** 이면 요청이 서비스에 도달하지 못한 것입니다.

## 로컬 실행
ADC 를 본인 계정으로 설정한 뒤 같은 코드를 그대로 실행합니다.
```bash
gcloud auth application-default login

cd compute-engine
GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=iceu-songpa05 \
GOOGLE_CLOUD_LOCATION=global GEMINI_MODEL=gemini-2.5-flash \
  .venv/bin/uvicorn app:app --reload
```

## 리소스 정리
```bash
gcloud run services delete $SERVICE --region=$REGION --project=$PROJECT --quiet
gcloud artifacts docker images delete $IMAGE --delete-tags --project=$PROJECT --quiet
```
