# priceit-starter

카카오톡 오픈채팅 메시지를 수집해 가격/품절 이벤트를 자동 분류하고 텔레그램 알림을 보내는 MVP.

## 포함 기능
- SQLite 기반 저장소 (`messages`, `products`, `events`)
- 메시지 파서(가격 인상/인하/품절/재입고)
- 업체/상품 추출 규칙
- 텔레그램 알림 전송
- FastAPI 수집 API
- 데스크톱(카카오톡) 클립보드 수집기 (A안: 반자동, 계정 리스크 낮춤)

## 빠른 실행
```bash
cd priceit-starter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m src.init_db
python -m src.api
```

## 텔레그램 설정
`.env`에 아래 2개를 채우면 알림이 동작합니다.
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## 수집 방식
- API 직접 수집: `/ingest`
- 클립보드 수집: `python -m src.kakao_clipboard_collector`

클립보드 수집기는 현재 포커스된 카카오톡 대화창의 텍스트를 주기적으로 복사해 신규 라인만 DB에 반영합니다.
