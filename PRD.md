# 목표
웹기반 gemini-3.8flash 기반으로 동작하는  챗봇 서비스를 생성

# 요구사항
* 웹 기반
* gemini-3.8flash 기반
* 로컬 pc에서 동작
* 로컬 실행 시 GEMINI API KEY는 환경변수의 값을 사용
* GCP Compute Engine 배포
  * Compute Engine VM에서 챗봇 서비스 실행
  * 외부 브라우저에서 VM 외부 IP로 접속 가능
  * VM에서는 GEMINI API KEY를 Secret Manager에서 조회하여 사용 (코드·저장소·VM 디스크에 키 포함 금지)
  * VM 서비스 계정에는 해당 시크릿 조회 권한만 부여
  * VM 재부팅 시 서비스 자동 시작
# 제외사항


