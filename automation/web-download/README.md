# Web Download Automation (Google Drive MCP)

## 목표
- Google Drive 기반 다운로드 자동화를 카카오 루프와 분리 운영
- 하루 3회(예: 09:00/14:00/19:00 KST) 배치 실행
- 자격증명은 git에 저장하지 않음

## 보안 원칙
- OAuth client JSON, refresh token/credential 파일은 로컬 전용
- `.gitignore`로 차단
- 비밀번호/OTP 평문 공유 금지

## 준비물
1) Google Cloud OAuth Desktop Client JSON 파일
2) Drive API enabled + scope `https://www.googleapis.com/auth/drive.readonly`

## 로컬 파일 위치(권장)
- OAuth client: `automation/web-download/secrets/gcp-oauth.keys.json`
- OAuth creds: `automation/web-download/secrets/gdrive-credentials.json`

## 인증
```bash
cd automation/web-download
./auth_gdrive_mcp.sh
```

## 참고
현재 npm의 `@modelcontextprotocol/server-gdrive` 패키지는 deprecate 메시지가 뜰 수 있음.
운영 전 최신 공식 MCP 서버 패키지명으로 교체 권장.
