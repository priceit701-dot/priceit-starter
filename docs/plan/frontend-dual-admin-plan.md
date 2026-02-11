# Frontend Dual Admin Plan (Control Tower + Seller)

## 목적
기존 `dashboard` 체계를 유지한 채, 사용자 역할에 따라 정보 노출을 분리한다.

- 관제탑 어드민: 전체 운영 관점(룸/이벤트/품질/리스크/오류)
- 셀러 어드민: 판매/운영에 필요한 핵심 알람 중심(잡음 최소)

## URL 구조
- 기존 유지: `/dashboard`, `/dashboard_v1~v5.html`
- 신규 추가:
  - `/admin/control-tower`
  - `/admin/seller`

## 정보 노출 범위 (Who sees what)

| 정보 항목 | 관제탑 어드민 | 셀러 어드민 |
|---|---|---|
| 전체 메시지/이벤트 KPI | ✅ | ❌ |
| 룸별 트래픽 상위 | ✅ | ❌ |
| 데이터 품질(스킵 사유) | ✅ | ❌ |
| ingestion 오류 수(24h) | ✅ | ❌ |
| 파이프라인 상태(OK/WARN/DOWN) | ✅ | ❌ |
| 오늘 주요 알람 요약(7유형 고정) | ✅(참고 가능) | ✅(핵심) |
| 최근 알람 피드 | ✅ | ✅ |
| 내 대응 필요 항목(품절/지연/가격변동) | ❌ | ✅(핵심) |

## 셀러 화면 설계 기준
핵심 블록만 제공:
1. 오늘 주요 알람 요약(7유형 고정 순서)
2. 최근 알람 피드
3. 내 대응 필요 항목(강조: `SOLD_OUT`, `DELAY_NOTICE`, `PRICE_UP`, `PRICE_DOWN`)

### 7유형 고정 순서
`PRICE_UP`, `PRICE_DOWN`, `SOLD_OUT`, `RESTOCK`, `DELAY_NOTICE`, `NEW_ITEM`, `NOTICE`

## 관제탑 화면 설계 기준
추가 블록 중심:
1. 데이터 품질(스킵/오류)
2. 룸별 트래픽 상위
3. 파이프라인 상태

## API 확장 (기존 호환 유지)
기존 API 변경 없음, 신규 endpoint만 추가:
- `GET /stats/seller`
- `GET /stats/control-tower`

### `/stats/seller`
- 7유형 요약(정렬 고정)
- 최근 알람 피드
- 대응 필요 항목

### `/stats/control-tower`
- KPI(messages, events_last_hour, ingestion_errors, last_message_at)
- data_quality(skip_reasons, error_count)
- top_room_traffic
- pipeline_status(OK/WARN/DOWN + 설명)

## 비기능/호환 원칙
- 기존 대시보드 화면/엔드포인트는 손상 없이 유지
- DB schema 변경 없음
- 신규 기능은 read-only 조회 중심
