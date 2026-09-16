# Cloud Run 배포 과정 기록

`compute-engine/` 의 챗봇을 컨테이너로 만들어 Cloud Run 에 배포한 과정의 기록입니다.
명령어 위주의 배포 가이드는 [README.md](README.md) 를 참고하세요.

- 배포일: 2026-09-16
- 서비스 URL: `https://chatbot-307601624742.asia-northeast3.run.app` (구형 주소 `https://chatbot-rkdjfnjfsq-du.a.run.app` 도 동일 서비스)
- 현재 상태: **배포 유지, 비공개** (토큰 없는 요청은 403)

---

## 1. 최종 구성

| 항목 | 값 |
|---|---|
| 프로젝트 | `iceu-songpa05` (프로젝트 번호 `307601624742`) |
| 리전 | `asia-northeast3` |
| 서비스 | `chatbot` / 리비전 `chatbot-00001-krm` (트래픽 100%) |
| 이미지 | `asia-northeast3-docker.pkg.dev/iceu-songpa05/chatbot/chatbot:latest` |
| 다이제스트 | `sha256:8199ea26c483…f529b` (2026-09-16 10:02 등록) |
| 런타임 서비스 계정 | `307601624742-compute@developer.gserviceaccount.com` |
| 시크릿 | `GEMINI_API_KEY:latest` → 환경변수 `GEMINI_API_KEY` |
| 포트 | 컨테이너 8080 (`PORT` 주입) |
| HTTPS | Cloud Run 기본 제공 (인증서 설정 불필요) |
| 접근 제어 | `roles/run.invoker` 바인딩 없음 = 비공개 |

## 2. 빌드부터 실행까지의 경로

```
로컬 저장소
   │  gcloud builds submit --config cloud-run/cloudbuild.yaml
   │  (.gcloudignore 로 .venv/ __pycache__/ .git/ .omc/ 제외 → 15개 파일 67KB)
   ▼
GCS  gs://iceu-songpa05_cloudbuild/source/*.tgz          소스 압축본 보관
   │  Cloud Build 가 x86-64 머신에서 cloud-run/Dockerfile 로 빌드 (45초)
   ▼
Artifact Registry  …/chatbot/chatbot:latest              cloudbuild.yaml 의 images: 가 푸시
   │  gcloud run deploy --image=…
   ▼
Cloud Run 인스턴스 기동 시 이미지 pull
```

로컬에서 만든 `chatbot-local:latest`(235MB)는 배포 전 검증용이며 업로드하지 않았습니다.
이 Mac 의 이미지는 arm64 이고 Cloud Run 은 x86-64 를 요구하므로, 그대로 푸시했다면 컨테이너가 시작되지 않았을 것입니다. Cloud Build 가 x86-64 에서 빌드해 이 문제를 피했습니다.

## 3. Secret Manager 키 주입 방식

배포 시 지정한 `--set-secrets=GEMINI_API_KEY=GEMINI_API_KEY:latest` 가 서비스 정의에 **참조**로 저장됩니다.

```yaml
containers:
- env:
  - name: GEMINI_API_KEY          # 컨테이너 환경변수 이름
    valueFrom:
      secretKeyRef:
        name: GEMINI_API_KEY      # Secret Manager 시크릿
        key: latest               # 버전
  serviceAccountName: 307601624742-compute@developer.gserviceaccount.com
```

인스턴스가 시작될 때 Cloud Run 이 **런타임 서비스 계정의 신원으로** 시크릿을 조회해 환경변수로 넣고 컨테이너를 시작합니다. `app.py` 는 이 환경변수를 읽습니다.

- 값은 서비스 정의·이미지 레이어·빌드 로그 어디에도 남지 않습니다.
- 런타임 서비스 계정에 `roles/secretmanager.secretAccessor` 가 없으면 컨테이너가 시작되지 않습니다. 이 권한은 Compute Engine 배포 때 시크릿 단위로 부여해 둔 것을 그대로 사용했습니다.
- 조회는 **인스턴스 시작 시 1회**입니다. 시크릿에 새 버전을 올리면 새로 뜨는 인스턴스부터 반영되고, 즉시 전체 적용하려면 새 리비전을 배포해야 합니다.
- 운영에서는 `latest` 대신 고정 버전(`:1`)이 더 안전합니다.

## 4. Compute Engine 방식과의 차이

| 항목 | Compute Engine | Cloud Run |
|---|---|---|
| 키 주입 | `deploy/start.sh` 가 `gcloud secrets versions access` 호출 | 플랫폼이 조회해 환경변수로 주입 |
| HTTPS | Caddy + Let's Encrypt 직접 구성 | 기본 제공 |
| 포트 | 8000 고정 | `PORT` 환경변수 (8080) |
| 자동 시작 | systemd `enable` | 요청 시 자동 기동, 없으면 0 개로 축소 |
| 방화벽·고정 IP | 직접 설정 | 불필요 |
| access scope | `cloud-platform` 필요 | 개념 없음 (IAM 만 사용) |

`app.py` 는 어느 쪽에서도 수정하지 않았습니다. `Dockerfile` 의 `CMD` 가 셸 형식이라 시작 시 `PORT` 가 채워집니다.

## 5. 진행 과정

| 단계 | 작업 | 결과 |
|---|---|---|
| 0 | 로컬 도커 빌드 및 기동 확인 (`PORT=9090` 주입 포함) | `/api/health`, `/`, `PORT` 반영 모두 정상 |
| 1 | `gcloud auth login` 재인증 | 토큰 만료로 배포가 막혀 사용자가 직접 수행 |
| 2 | API 활성화 (run, cloudbuild, artifactregistry) | 완료 |
| 3 | Artifact Registry 저장소 `chatbot` 생성 | 완료 |
| 4 | `gcloud builds submit` | 1회차 `PERMISSION_DENIED`, 재시도 45초 만에 SUCCESS |
| 5 | `gcloud run deploy --no-allow-unauthenticated` | 리비전 `chatbot-00001-krm` 배포, 인증 접속 정상 / 무인증 403 |
| 6 | `add-iam-policy-binding allUsers run.invoker` | 공개 전환, 무인증 200 확인 |
| 7 | `remove-iam-policy-binding allUsers` | 약 1분 뒤 무인증 403 으로 전환 확인 |

## 6. 발생한 문제와 해결

| # | 증상 | 원인 | 해결 |
|---|---|---|---|
| 1 | 로컬 컨테이너 점검에서 연결 실패로 보임 | `curl` 이 오류 56(연결 재설정)에는 재시도하지 않아 기동 전에 포기 | `--retry-all-errors` 사용 |
| 2 | `gcloud` 전 명령이 `Reauthentication failed` | 인증 토큰 만료 | 사용자가 `gcloud auth login` 수행 (브라우저 방식 2회 실패 후 성공) |
| 3 | `gcloud builds submit` 이 `PERMISSION_DENIED` | API 활성화 직후 권한 전파 지연 | 그대로 재시도 → 성공 |
| 4 | 공개 권한 회수 후에도 무인증 요청이 200 | Cloud Run 프런트엔드까지 IAM 변경이 퍼지는 데 시간 소요 | 약 1분 후 403 으로 전환됨 (정책 조회가 아니라 실제 요청으로 확인해야 함) |

## 7. 남은 리소스와 정리

| 리소스 | 상태 | 요금 |
|---|---|---|
| Cloud Run 서비스 `chatbot` | 비공개 유지, 인스턴스 0 개 | 요청 없으면 사실상 없음 |
| Artifact Registry 이미지 | `latest` 1 개 | 저장 용량에 요금 발생 |
| `gs://iceu-songpa05_cloudbuild/source/` | 소스 압축본 2 개 (44KB) | 사실상 무시 가능 |
| 시크릿 `GEMINI_API_KEY` | 유지 (Compute Engine 배포 때 생성) | 버전당 월 약 $0.06 |

```bash
# 서비스만 삭제 (이미지 보관 → 재배포 1~2분)
gcloud run services delete chatbot --region=asia-northeast3 --project=iceu-songpa05 --quiet

# 이미지 저장소까지 삭제
gcloud artifacts repositories delete chatbot --location=asia-northeast3 --project=iceu-songpa05 --quiet
```

## 8. 다시 공개하려면

```bash
gcloud run services add-iam-policy-binding chatbot \
  --region=asia-northeast3 --project=iceu-songpa05 \
  --member=allUsers --role=roles/run.invoker
```
비공개 상태에서 본인만 접속하려면:
```bash
gcloud run services proxy chatbot --region asia-northeast3 --project iceu-songpa05
# http://127.0.0.1:8080
```
