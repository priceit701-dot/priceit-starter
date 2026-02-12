# OpenChat 중요도 기반 운영 아키텍처 v1 (2026-02-12)

## 목표
N개의 오픈채팅방에서 들어오는 메시지를 **업체별/시간순(최신순)**으로 통합하고,
운영자가 **중요/비중요를 빠르게 선별**해 사람에게 전달할 수 있게 한다.

---

## 핵심 원칙
1. **DB가 원본(Source of Truth)**, 파일은 파생 산출물(리포트/뷰)
2. **로컬 DB 선저장 후 전송(outbox)**: 서버 장애 시에도 유실 방지
3. **이벤트 + 공지 세부유형(notice_subtype) 분리**
4. **중요도(score/level) 계산은 규칙 기반으로 시작 → 추후 모델 고도화**

---

## 이벤트 분류 체계 v1
- 기본 event_type(기존):
  - PRICE_UP, PRICE_DOWN, SOLD_OUT, RESTOCK, DELAY_NOTICE, NEW_ITEM, NOTICE

- 공지 세부유형 notice_subtype(신규):
  - DELIVERY_DELAY (배송지연)
  - PRICE_UP_SCHEDULED (공급가 인상 예정)
  - PRICE_UP_SCHEDULED_2D (2일 뒤 공급가 인상 예정)
  - ORDER_CUTOFF_CHANGE (마감시간 변경)
  - HOLIDAY_NOTICE (휴무/명절 공지)
  - SHIPPING_POLICY_CHANGE (배송정책 변경)
  - ETC

---

## 중요도 스코어 규칙 v1 (0~100)
- 기본점수:
  - SOLD_OUT: 90
  - RESTOCK: 85
  - PRICE_UP: 80
  - PRICE_DOWN: 70
  - DELAY_NOTICE: 75
  - NEW_ITEM: 45
  - NOTICE: 40

- 가산점(예시):
  - "배송지연" 키워드: +15
  - "2일 뒤" + "공급가 인상": +20
  - "오늘/내일 인상": +25
  - 변동폭 >= 10%: +15

- 감점:
  - 일반 홍보성 문구: -15

- 레벨 매핑:
  - 80 이상: high
  - 50~79: medium
  - 49 이하: low

---

## DB 설계 변경 v1
`openchat_event_fact`에 아래 컬럼 추가:
- notice_subtype TEXT
- effective_at TEXT
- importance_score REAL DEFAULT 0
- importance_level TEXT CHECK('high','medium','low') DEFAULT 'low'
- is_actionable INTEGER DEFAULT 0
- dedup_key TEXT
- processed_at TEXT

추가 테이블:
- `event_priority_log` (스코어 산출 이력)

뷰:
- `v_openchat_priority_feed` (업체별 최신순 + 중요도 기준)

---

## API 초안
1. `GET /events/priority-feed?vendor=...&level=high&limit=100`
2. `GET /events/latest-by-vendor?level=high`
3. `GET /events/summary?from=...&to=...`

---

## 액션플랜
### Phase A (즉시)
1) DB 컬럼/뷰 추가
2) 규칙기반 스코어링 배치 스크립트 적용
3) 업체별 최신순 피드 파일 생성(JSON/CSV)

### Phase B (단기)
4) 실시간 outbox 전송 연결
5) 사람 알림(High만 즉시, Medium/Low는 요약)

### Phase C (고도화)
6) 중요도 피드백 루프(사람이 중요/비중요 교정) 반영
7) 규칙 + 모델 하이브리드 분류
