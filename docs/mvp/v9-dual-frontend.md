# v9 - Dual Frontend (Control Tower + Seller)

## 작업 요약
priceit-starter에 역할 분리형 프론트 2트랙을 추가했다.

- 관제탑 어드민: `/admin/control-tower`
- 셀러 어드민: `/admin/seller`

기존 대시보드(` /dashboard`, `dashboard_v1~v5`)는 유지했고, 기존 API 호환을 깨지 않도록 신규 endpoint만 추가했다.

## 구현 상세

### 1) 라우팅/화면 추가
- `GET /admin/control-tower` → `web/admin_control_tower.html`
- `GET /admin/seller` → `web/admin_seller.html`

### 2) API 최소 확장
- `GET /stats/control-tower`
  - KPI: messages, last_message_at, events_last_hour, ingestion_errors
  - 데이터 품질: skip_reasons, error_count
  - 룸별 트래픽 상위(top 10)
  - 파이프라인 상태: `OK|WARN|DOWN`

- `GET /stats/seller`
  - 오늘 주요 알람 요약(7유형 고정 순서)
  - 최근 알람 피드
  - 대응 필요 항목(`SOLD_OUT`, `DELAY_NOTICE`, `PRICE_UP`, `PRICE_DOWN`)

### 3) 7유형 고정 순서 반영
`PRICE_UP`, `PRICE_DOWN`, `SOLD_OUT`, `RESTOCK`, `DELAY_NOTICE`, `NEW_ITEM`, `NOTICE`

## 정보 노출 분리
세부 설계 문서: `docs/plan/frontend-dual-admin-plan.md`

핵심:
- 관제탑: 전체 운영/품질/리스크 중심
- 셀러: 알람 중심 운영 핵심만

## 변경 파일
- `src/api.py`
- `web/admin_control_tower.html`
- `web/admin_seller.html`
- `docs/plan/frontend-dual-admin-plan.md`
- `docs/mvp/v9-dual-frontend.md`

## 실행 검증 (실측 로그)
검증 환경: 로컬 FastAPI (`python -m src.api`, port 8877)

### URL 응답 코드
```bash
curl -s -o /tmp/control.html -w "%{http_code}" 'http://127.0.0.1:8877/admin/control-tower'
# 200

curl -s -o /tmp/seller.html -w "%{http_code}" 'http://127.0.0.1:8877/admin/seller'
# 200
```

### 데이터 로딩 증거 (API 응답 일부)
```bash
curl -s 'http://127.0.0.1:8877/stats/control-tower?limit_hours=24'
# {"hours":24,"kpi":{"messages":37694,"last_message_at":"2026-02-12T00:08:52","events_last_hour":327,"ingestion_errors":0}, ... "pipeline_status":{"status":"OK",...}}

curl -s 'http://127.0.0.1:8877/stats/seller?limit_hours=24'
# {"hours":24,"alert_types_order":["PRICE_UP","PRICE_DOWN","SOLD_OUT","RESTOCK","DELAY_NOTICE","NEW_ITEM","NOTICE"],"today_alert_summary":[...],"recent_alert_feed":[...],"action_required_items":[...]}
```

두 화면이 각각 참조하는 API에서 실제 데이터가 내려오는 것을 확인했다.

## 호환성
- 기존 endpoint 유지
- 기존 dashboard 파일 유지
- DB schema 변경 없음
