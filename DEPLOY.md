# 배포 과정 기록

Gemini 챗봇을 GCP Compute Engine VM 에 배포하고 HTTPS 를 적용한 과정의 기록입니다.
명령어 위주의 배포 가이드는 [README.md](README.md#gcp-compute-engine-배포) 를 참고하세요.

- 배포일: 2026-09-15
- 접속 주소: https://34-64-69-239.sslip.io

---

## 1. 최종 구성

```
브라우저 ──HTTPS(443)──▶ Caddy ──HTTP──▶ uvicorn (127.0.0.1:8000) ──▶ Gemini API
            HTTP(80) → 443 리다이렉트          │
                                               └─ 시작 시 Secret Manager 에서 GEMINI_API_KEY 조회
```

| 항목 | 값 |
|---|---|
| 프로젝트 | `iceu-songpa05` |
| VM | `instance-20260915-043514` (`asia-northeast3-c`, Debian 13) |
| 서비스 계정 | `307601624742-compute@developer.gserviceaccount.com` (기본 Compute SA) |
| Access scope | `cloud-platform` |
| 시크릿 | `GEMINI_API_KEY` (버전 1) — 위 SA 에 이 시크릿 한정 `roles/secretmanager.secretAccessor` |
| 고정 IP | `chatbot-ip` = `34.64.69.239` |
| 도메인 | `34-64-69-239.sslip.io` |
| 인증서 | Let's Encrypt (YE2), 만료 2026-12-14, Caddy 자동 갱신 |
| 방화벽 | `default-allow-http` (tcp:80 → `http-server`), `allow-chatbot-https` (tcp:443 → `chatbot`) |
| VM 태그 | `chatbot`, `http-server` |
| 서비스 | `chatbot.service` (uvicorn, 사용자 `chatbot`), `caddy.service` — 둘 다 `enabled` |
| 앱 경로 | `/opt/chatbot` (venv: `/opt/chatbot/.venv`) |

---

## 2. PRD 요구사항 충족 여부

| 요구사항 | 결과 | 비고 |
|---|---|---|
| 웹 기반, gemini-3.8-flash | ✅ | `/api/health` → `{"status":"ok","model":"gemini-3.8-flash"}` |
| 로컬 실행 시 환경변수의 키 사용 | ✅ | `app.py` 가 `GEMINI_API_KEY` 환경변수 사용 |
| Compute Engine VM 에서 실행 | ✅ | systemd 서비스로 실행 |
| 외부 브라우저에서 접속 | ✅ | 외부 IP 에 연결된 도메인으로 HTTPS 접속 |
| VM 은 Secret Manager 에서 키 조회, 코드·저장소·디스크에 키 없음 | ✅ | `deploy/start.sh` 가 조회해 프로세스 환경변수로만 전달 |
| VM 서비스 계정에 해당 시크릿 조회 권한만 | ⚠️ 부분 충족 | 시크릿 권한은 시크릿 단위로 부여했으나, **기본 Compute SA 를 사용**해 다른 프로젝트 권한이 남아 있을 수 있음 |
| 재부팅 시 서비스 자동 시작 | ✅ | `reset` 후 가동 0분 시점에 `caddy`·`chatbot` 모두 active, HTTPS 응답 확인 |

---

## 3. 진행 과정

### 3-1. 사전 준비
1. gcloud 활성 계정·프로젝트 확인 — 노트북에 적힌 `iceu-songpa25` 는 권한이 없어 실제 프로젝트 `iceu-songpa05` 로 정정
2. `compute_engine_example.ipynb` 의 프로젝트 ID 와 기본 SA 이메일(프로젝트 번호 `307601624742`)을 `iceu-songpa05` 기준으로 수정
3. 확인된 초기 상태
   - Compute Engine / Secret Manager API 활성화됨
   - 시크릿 `GEMINI_API_KEY` 등록됨 (콘솔에서 사전 등록)
   - VM `instance-20260915-043514` 가 기본 SA, `http-server` 태그로 이미 생성되어 있음

### 3-2. 방식 결정
- 신규 VM·전용 SA 대신 **기존 VM + 기본 Compute SA** 를 사용하기로 결정
- 코드 수정 없이, 실행 스크립트(`deploy/start.sh`)가 Secret Manager 에서 키를 받아 환경변수로 넘기는 방식 채택

### 3-3. HTTP 배포 (포트 8000)
1. 방화벽 `allow-chatbot-8000` (tcp:8000 → 태그 `chatbot`) 생성, VM 에 `chatbot` 태그 추가
2. `gcloud compute scp` 로 `app.py`, `requirements.txt`, `static/`, `deploy/` 복사
3. VM 에서 `python3-venv` 설치, 시스템 사용자 `chatbot` 생성, `/opt/chatbot` 에 venv·의존성 설치
4. 시크릿 조회 테스트 중 오류 발생 → [4장](#4-발생한-문제와-해결) 순서대로 해결
5. `deploy/chatbot.service` 등록 (`systemctl enable --now chatbot`)
6. 브라우저에서 `http://34.64.69.239:8000` 접속 확인

### 3-4. HTTPS 적용
| 단계 | 작업 | 결과 |
|---|---|---|
| 사전 확인 | VM IP·태그, 방화벽, `dig +short 34-64-69-239.sslip.io` | IP `34.64.69.239`, 태그 정상, DNS 정상 |
| 1 | 임시 IP → 고정 IP `chatbot-ip` 전환 | `IN_USE` |
| 2 | 방화벽 `allow-chatbot-https` (tcp:443) 생성 | 생성 완료 |
| 3 | VM 포트 점유 확인 후 `apt-get install caddy` | 80/443 비어 있음, Caddy 2.6.2 active |
| 4 | `/etc/caddy/Caddyfile` 작성 (기존 파일 `.bak` 백업), validate 후 reload | `Valid configuration`, `certificate obtained successfully` |
| 5 | HTTPS 확인 | `/api/health` 정상, `http://` → `308` → `https://` |
| 6 | `start.sh` 의 `--host 0.0.0.0` → `127.0.0.1` (기존 파일 `.bak` 백업), 서비스 재시작 | `127.0.0.1:8000` 에서만 listen, HTTPS 정상 |
| 7 | 방화벽 `allow-chatbot-8000` 삭제 | `http://34.64.69.239:8000` 시간 초과 (차단), HTTPS 정상 |
| 8 | `gcloud compute instances reset` | 재부팅 직후 `caddy`·`chatbot` 자동 시작, HTTPS 정상 |

적용한 Caddyfile:
```
34-64-69-239.sslip.io {
	reverse_proxy 127.0.0.1:8000 {
		flush_interval -1
	}
}
```
- `flush_interval -1`: `/api/chat` 의 NDJSON 스트리밍 응답이 프록시에서 버퍼링되지 않도록 설정
- 인증서 발급은 HTTP-01 챌린지(80 포트)로 진행됨

---

## 4. 발생한 문제와 해결

실제로 발생한 순서대로 기록합니다.

| # | 증상 | 원인 | 해결 |
|---|---|---|---|
| 1 | `gcloud ... iceu-songpa25`: `PERMISSION_DENIED` | 노트북의 프로젝트 ID 가 활성 계정의 프로젝트와 다름 | `iceu-songpa05` 로 정정 |
| 2 | `sudo: unknown user chatbot` | `useradd` 가 실행되지 않음 | `useradd --system ... chatbot` 실행 후 `chown -R chatbot:chatbot /opt/chatbot` 재실행 |
| 3 | `/opt/chatbot/.venv/bin/pip: command not found` | Debian 에서 `python3-venv` 미설치 → venv 가 pip 없이 생성됨 | `python3-venv python3-pip` 설치 → `.venv` 삭제 후 재생성 → `chown` 재실행 |
| 4 | `ACCESS_TOKEN_SCOPE_INSUFFICIENT` | VM 생성 시 기본 scope 에 Secret Manager 미포함 | VM 중지 → `set-service-account --scopes=cloud-platform` → 시작 |
| 5 | `IAM_PERMISSION_DENIED` | 기본 Compute SA 에 시크릿 읽기 권한 없음 (Editor 여도 시크릿 값 조회 권한은 없음) | `gcloud secrets add-iam-policy-binding GEMINI_API_KEY --role=roles/secretmanager.secretAccessor` |

참고:
- 4번 해결 후에도 같은 오류가 반복되면 gcloud 토큰 캐시가 원인일 수 있음 → `sudo rm -rf /opt/chatbot/.config/gcloud`
- Google API 호출은 **scope** 와 **IAM** 을 모두 통과해야 하므로, 4번을 해결하면 5번이 이어서 드러날 수 있음

---

## 5. VM 에 남아 있는 백업 파일

| 파일 | 내용 |
|---|---|
| `/etc/caddy/Caddyfile.bak` | Caddy 설치 시 생성된 기본 설정 |
| `/opt/chatbot/deploy/start.sh.bak` | `--host 0.0.0.0` 버전 |

---

## 6. 남은 과제

- [ ] 브라우저에서 채팅 응답이 스트리밍(한 글자씩)으로 표시되는지 확인
- [ ] 전용 서비스 계정으로 전환하여 PRD 의 "시크릿 조회 권한만" 요구사항 완전 충족
- [ ] `/api/chat` 에 인증이 없어 주소를 아는 누구나 Gemini 사용량을 소모할 수 있음 → 인증 또는 요청 제한 검토
- [ ] 필요 시 sslip.io 대신 보유 도메인 사용 (공용 도메인은 인증서 발급 한도에 걸릴 수 있음)

---

## 7. 리소스 정리 대상

실습 종료 시 삭제할 리소스 (명령은 [README.md](README.md#리소스-정리-과금-방지-로컬) 참고):

| 리소스 | 이름 | 비고 |
|---|---|---|
| VM | `instance-20260915-043514` | |
| 고정 IP | `chatbot-ip` | VM 삭제 후 남기면 과금 |
| 방화벽 | `allow-chatbot-https` | |
| IAM 바인딩 | `GEMINI_API_KEY` ← 기본 Compute SA | |
| 시크릿 | `GEMINI_API_KEY` | 필요 시 |
