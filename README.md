# gcp-compute-engine-chatbot
GCP Compute Engine 챗봇 구현 해보기

`gemini-3.8-flash` 모델 기반 웹 챗봇입니다. 로컬 PC에서 실행하거나 GCP Compute Engine VM에 HTTPS로 배포할 수 있습니다.

- 현재 배포: https://34-64-69-239.sslip.io

## 구성
- `app.py` — FastAPI 서버. `/api/chat` 에서 Gemini 응답을 NDJSON 스트리밍으로 전달
- `static/index.html` — 채팅 UI (빌드 과정 없는 단일 HTML)
- `deploy/start.sh` — VM 실행 스크립트. Secret Manager 에서 키를 조회해 환경변수로만 전달
- `deploy/chatbot.service` — systemd 유닛 (재부팅 시 자동 시작)
- `compute_engine_example.ipynb` — VM 생성·정리용 gcloud 예제 노트북

## 로컬 실행
```bash
export GEMINI_API_KEY="발급받은_키"   # 필수
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app:app --reload
```
브라우저에서 http://127.0.0.1:8000 접속

## 환경변수
| 이름 | 필수 | 기본값 | 설명 |
|---|---|---|---|
| `GEMINI_API_KEY` | O (로컬) | – | Gemini API 키. VM 에서는 `start.sh` 가 Secret Manager 에서 채움 |
| `GEMINI_MODEL` | X | `gemini-3.8-flash` | 사용할 모델 ID |
| `SECRET_NAME` | X | `GEMINI_API_KEY` | VM 에서 조회할 Secret Manager 시크릿 이름 |

---

## GCP Compute Engine 배포

### 아키텍처
```
브라우저 ──HTTPS(443)──▶ Caddy ──HTTP──▶ uvicorn (127.0.0.1:8000)
            HTTP(80) → 443 리다이렉트          │
                                               └─ 시작 시 Secret Manager 에서 GEMINI_API_KEY 조회
```
- 키는 코드·저장소·VM 디스크에 저장하지 않고 프로세스 메모리에만 존재
- VM 서비스 계정에는 해당 시크릿 **하나**에 대한 `secretAccessor` 권한만 부여 (프로젝트 단위 권한 X)
- `caddy`, `chatbot` 서비스 모두 `systemctl enable` 로 재부팅 시 자동 시작
- 인증서는 Caddy 가 Let's Encrypt 로 자동 발급·갱신

### 배포 환경
| 항목 | 값 |
|---|---|
| 프로젝트 | `iceu-songpa05` |
| VM | `instance-20260915-043514` (`asia-northeast3-c`, Debian 13) |
| 서비스 계정 | `307601624742-compute@developer.gserviceaccount.com` (scope: `cloud-platform`) |
| 시크릿 | `GEMINI_API_KEY` |
| 고정 IP | `chatbot-ip` = `34.64.69.239` |
| 도메인 | `34-64-69-239.sslip.io` (IP 가 이름에 들어간 무료 와일드카드 DNS) |
| 방화벽 | `default-allow-http` (80, 태그 `http-server`), `allow-chatbot-https` (443, 태그 `chatbot`) |

> PRD 는 전용 서비스 계정을 권장합니다. 현재는 기본 Compute 서비스 계정을 사용하므로, 운영 시에는 전용 계정을 만들어 시크릿 권한만 부여하는 것을 권장합니다.

### 공통 변수 [로컬]
```bash
PROJECT=iceu-songpa05
REGION=asia-northeast3
ZONE=asia-northeast3-c
VM=instance-20260915-043514
SA_EMAIL=307601624742-compute@developer.gserviceaccount.com
SECRET=GEMINI_API_KEY
DOMAIN=34-64-69-239.sslip.io
```

### 1. 시크릿 등록 및 권한 부여 [로컬]
```bash
gcloud services enable compute.googleapis.com secretmanager.googleapis.com --project=$PROJECT

printf '%s' "$GEMINI_API_KEY" | gcloud secrets create $SECRET \
  --data-file=- --replication-policy=automatic --project=$PROJECT

# 시크릿 하나에만 읽기 권한
gcloud secrets add-iam-policy-binding $SECRET \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/secretmanager.secretAccessor" --project=$PROJECT
```

### 2. VM scope · 태그 설정 [로컬]
Secret Manager 호출에는 `cloud-platform` scope 가 필요합니다. scope 변경은 VM 중지 상태에서만 가능합니다.
```bash
gcloud compute instances stop $VM --zone=$ZONE --project=$PROJECT
gcloud compute instances set-service-account $VM \
  --service-account=$SA_EMAIL --scopes=cloud-platform --zone=$ZONE --project=$PROJECT
gcloud compute instances start $VM --zone=$ZONE --project=$PROJECT

gcloud compute instances add-tags $VM --tags=chatbot,http-server --zone=$ZONE --project=$PROJECT
```

### 3. 고정 IP · 방화벽 [로컬]
```bash
IP=$(gcloud compute instances describe $VM --zone=$ZONE --project=$PROJECT \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

# 현재 임시 IP 를 고정 IP 로 전환 (중지/시작 시 IP 가 바뀌어 도메인이 끊기는 것 방지)
gcloud compute addresses create chatbot-ip --addresses=$IP --region=$REGION --project=$PROJECT

gcloud compute firewall-rules create allow-chatbot-https \
  --network=default --direction=INGRESS --allow=tcp:443 \
  --source-ranges=0.0.0.0/0 --target-tags=chatbot --project=$PROJECT
```

### 4. 코드 복사 [로컬]
```bash
gcloud compute ssh $VM --zone=$ZONE --project=$PROJECT --command='mkdir -p ~/chatbot'
gcloud compute scp --recurse app.py requirements.txt static deploy \
  $VM:~/chatbot/ --zone=$ZONE --project=$PROJECT
```

### 5. 앱 설치 [VM]
```bash
gcloud compute ssh $VM --zone=$ZONE --project=$PROJECT
```
```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip
sudo useradd --system --home-dir /opt/chatbot --shell /usr/sbin/nologin chatbot
sudo mkdir -p /opt/chatbot && sudo cp -r ~/chatbot/* /opt/chatbot/
sudo python3 -m venv /opt/chatbot/.venv
sudo /opt/chatbot/.venv/bin/pip install -r /opt/chatbot/requirements.txt
sudo chmod +x /opt/chatbot/deploy/start.sh
sudo chown -R chatbot:chatbot /opt/chatbot

# 시크릿 조회 테스트 (키 값 대신 글자 수만 출력)
sudo -u chatbot -H gcloud secrets versions access latest --secret=GEMINI_API_KEY | wc -c
```

### 6. systemd 등록 [VM]
```bash
sudo cp /opt/chatbot/deploy/chatbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now chatbot
curl http://127.0.0.1:8000/api/health
```

### 7. HTTPS (Caddy) [VM]
```bash
sudo apt-get install -y caddy

sudo tee /etc/caddy/Caddyfile >/dev/null <<'EOF'
34-64-69-239.sslip.io {
	reverse_proxy 127.0.0.1:8000 {
		flush_interval -1
	}
}
EOF

sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo journalctl -u caddy -n 30 --no-pager   # "certificate obtained successfully" 확인
```
- `flush_interval -1`: `/api/chat` 의 스트리밍 응답을 버퍼링 없이 즉시 전달
- 인증서 발급·갱신에 80 포트가 필요하므로 `default-allow-http` 규칙과 `http-server` 태그는 유지

### 8. 확인 [로컬]
```bash
curl https://$DOMAIN/api/health                            # {"status":"ok",...}
curl -I http://$DOMAIN                                     # 308 → https
curl --max-time 5 http://34.64.69.239:8000/api/health      # 시간 초과 (외부 직접 접근 차단)

# 재부팅 후 자동 시작 확인
gcloud compute instances reset $VM --zone=$ZONE --project=$PROJECT
curl --retry 30 --retry-delay 5 --retry-all-errors https://$DOMAIN/api/health
```

### 코드 변경 후 재배포
```bash
# [로컬]
gcloud compute scp --recurse app.py requirements.txt static deploy $VM:~/chatbot/ --zone=$ZONE --project=$PROJECT
```
```bash
# [VM]
sudo cp -r ~/chatbot/* /opt/chatbot/
sudo /opt/chatbot/.venv/bin/pip install -r /opt/chatbot/requirements.txt
sudo chown -R chatbot:chatbot /opt/chatbot
sudo systemctl restart chatbot
```

### 운영 명령 [VM]
```bash
sudo systemctl status chatbot caddy
sudo journalctl -u chatbot -f
sudo journalctl -u caddy -f
```

### 문제 해결
| 증상 | 원인 | 해결 |
|---|---|---|
| `sudo: unknown user chatbot` | 서비스 사용자 미생성 | `useradd` 실행 후 `chown` 재실행 |
| `.venv/bin/pip: command not found` | `python3-venv` 미설치로 venv 가 불완전 | `python3-venv` 설치 → `.venv` 삭제 후 재생성 |
| `ACCESS_TOKEN_SCOPE_INSUFFICIENT` | VM scope 에 `cloud-platform` 없음 | 2단계. 변경 후에도 같으면 `sudo rm -rf /opt/chatbot/.config/gcloud` (토큰 캐시) |
| `IAM_PERMISSION_DENIED` | 서비스 계정에 시크릿 권한 없음 | 1단계 `add-iam-policy-binding`, 1분 후 재시도 |
| `NOT_FOUND` (시크릿) | 시크릿 이름 오타 (대소문자 구분) | `GEMINI_API_KEY` 확인 |
| Caddy `challenge failed` | 80 포트 차단 또는 DNS 불일치 | `http-server` 태그, `dig +short $DOMAIN` 확인 |
| `502 Bad Gateway` | `chatbot` 서비스 중단 | `sudo journalctl -u chatbot -n 50` |
| 답변이 한꺼번에 표시됨 | 프록시 버퍼링 | Caddyfile `flush_interval -1` 확인 |

### 리소스 정리 (과금 방지) [로컬]
```bash
gcloud compute instances delete $VM --zone=$ZONE --project=$PROJECT --quiet
gcloud compute addresses delete chatbot-ip --region=$REGION --project=$PROJECT --quiet   # VM 삭제 후 남기면 과금
gcloud compute firewall-rules delete allow-chatbot-https --project=$PROJECT --quiet
gcloud secrets remove-iam-policy-binding $SECRET \
  --member="serviceAccount:$SA_EMAIL" --role="roles/secretmanager.secretAccessor" --project=$PROJECT
# 시크릿까지 삭제: gcloud secrets delete $SECRET --project=$PROJECT --quiet
```
