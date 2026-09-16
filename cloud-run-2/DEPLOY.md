# Cloud Run ADC 배포 과정 기록

`compute-engine/` 의 챗봇을 **API 키 없이 ADC 로 인증**하도록 Cloud Run 에 배포한 과정의 기록입니다.
명령어 위주의 배포 가이드는 [README.md](README.md) 를 참고하세요.

- 배포일: 2026-09-16
- 서비스: `chatbot-adc` (`asia-northeast3`)
- **현재 상태: 리소스 정리 완료** (서비스·이미지 삭제됨). 아래는 삭제 전까지의 기록입니다.

---

## 1. 배포했던 구성

| 항목 | 값 |
|---|---|
| 프로젝트 | `iceu-songpa05` |
| 서비스 / 최종 리비전 | `chatbot-adc` / `chatbot-adc-00004-x4p` |
| 이미지 | `asia-northeast3-docker.pkg.dev/iceu-songpa05/chatbot/chatbot-adc:latest` |
| 런타임 서비스 계정 | `307601624742-compute@developer.gserviceaccount.com` (`roles/aiplatform.user`) |
| 환경변수 | `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT=iceu-songpa05`, `GOOGLE_CLOUD_LOCATION=global`, `GEMINI_MODEL=gemini-2.5-flash` |
| 시크릿 주입 | **없음** |
| 접근 제어 | 비공개 (무인증 요청 403) |

## 2. 인증 방식

배포 시 `--set-env-vars=GOOGLE_GENAI_USE_VERTEXAI=true,…` 만 지정하면, `google-genai` SDK 가 API 키 대신 **실행 환경의 신원(ADC)** 으로 Vertex AI 를 호출합니다. Cloud Run 에서 그 신원은 런타임 서비스 계정입니다.

`app.py` 에는 분기 하나만 추가했습니다.

```python
USE_VERTEXAI = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in {"1", "true", "yes"}
if not USE_VERTEXAI and not os.environ.get("GEMINI_API_KEY"):
    raise RuntimeError(...)
```

이 변수가 없으면 기존 API 키 방식과 100% 동일하게 동작합니다. 회귀 테스트로 세 경우를 확인했습니다: 키 없음 → 명확한 오류, API 키 모드 → 정상, ADC 모드 → 키 검사 건너뜀.

## 3. 진행 과정

| 단계 | 작업 | 결과 |
|---|---|---|
| 1 | `app.py` ADC 분기 추가 + 로컬 회귀 테스트 | 3 경우 모두 통과 |
| 2 | `aiplatform.googleapis.com` 활성화, 런타임 SA 에 `roles/aiplatform.user` | 완료 |
| 3 | `gcloud builds submit --config cloud-run-2/cloudbuild.yaml` | 45초, SUCCESS |
| 4 | `gcloud run deploy --no-allow-unauthenticated` | 리비전 00001, 무인증 403 확인 |
| 5 | 인증 토큰으로 `/api/health` + 실제 채팅 | 키 없이 응답 성공 → **ADC 인증 검증 완료** |
| 6 | 이후 채팅에서 응답 지연·무응답 발생 | 원인: 429 (아래) |
| 7 | 위치를 `us-central1` 로 변경 (리비전 00002) | **404** — 해당 리전에 모델 미제공 |
| 8 | 위치를 `global` 로 복귀 (리비전 00003) | 동작 복구되나 429 재발 |
| 9 | 모델을 `gemini-2.5-flash` 로 변경 (리비전 00004) | **해결** — 4.0초 응답, 검색 그라운딩 정상 |
| 10 | 서비스·이미지 삭제 | 정리 완료 |

## 4. 발생한 문제와 해결

### 4-1. `/api/chat` 이 계속 대기하다 응답 없음
- **원인**: Vertex AI 할당량 부족(429 RESOURCE_EXHAUSTED). 첫 바이트까지 22초를 기다린 뒤 오류 이벤트가 왔습니다.
- **왜 눈에 안 띄었나**: `app.py` 는 스트리밍 도중 예외가 나면 HTTP 상태를 바꿀 수 없어(헤더 전송 완료) 본문에 `{"type":"error"}` 를 실어 보냅니다. 그래서 로그에는 `POST 200` 으로 남고 화면은 비어 보입니다.
- **해결**: 모델을 `gemini-2.5-flash` 로 변경. 할당량은 **모델 단위**로 잡히므로 위치 변경이 아니라 모델 변경이 정답이었습니다.

### 4-2. 위치를 `us-central1` 로 바꾸자 404
- **원인**: 그 리전에 `gemini-3.8-flash` 미제공. 응답은 JSON 오류였고 모델 경로가 명시되어 있었습니다.
- **해결**: `global` 로 복귀. 신규 모델은 `global` 에 가장 먼저 열리는 편입니다.

### 4-3. 모델 가용성 조회가 전부 "미제공"으로 나옴
- **원인**: 사용한 REST 경로가 존재하지 않아 **HTML 404** 가 반환됨. 동작 중인 `global` 까지 미제공으로 표시되어 결과가 무효였습니다.
- **교훈**: 오류가 JSON 이면 API 의 진짜 응답, HTML 이면 경로 문제입니다. 가용성은 실제 호출로 판단하는 편이 확실합니다.

### 4-4. `Truncated response body` 경고
- 클라이언트가 응답을 끝까지 받기 전에 끊었을 때 남는 기록입니다. 429 로 지연되던 요청을 타임아웃으로 중단해 발생했고, 앱 비정상 종료와는 무관합니다.

## 5. ADC 방식의 득실

| | 내용 |
|---|---|
| 얻은 것 | 관리할 API 키가 없음. 시크릿 생성·권한·조회 코드가 모두 불필요. 접근 제어는 IAM 하나로 정리 |
| 치른 것 | 호출이 Vertex AI 로 이동 → **프로젝트의 Vertex AI 할당량에 종속**. 새 프로젝트는 초기 할당량이 낮아 429 를 만나기 쉬움 |
| 결론 | 조직 정책상 키 금지, 감사 로그 필요, 서비스 다수로 키 회전이 부담인 경우에 유리. 소규모 실습에는 API 키 방식(`cloud-run/`)이 단순 |

## 6. 재배포 방법
[README.md](README.md) 의 1~5 단계를 그대로 실행하면 됩니다. 이미지가 삭제되었으므로 빌드부터 시작합니다.
