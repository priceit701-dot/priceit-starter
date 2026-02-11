# Seller Needs Model (콘텐츠 중심 셀러 정보모델)

## 배경
기존 셀러 화면은 이벤트 타입(PRICE_UP, SOLD_OUT 등) 중심 나열 비중이 높아,
셀러가 **바로 행동하기 위한 판단 정보**를 한 번에 파악하기 어려웠다.

목표는 "무슨 이벤트가 있었나"가 아니라,
"그래서 지금 무엇을 해야 하나"를 보여주는 것이다.

---

## 셀러 의사결정 질문 → 데이터 항목 매핑

### Q1. 지금 바로 조치해야 할 항목은 무엇인가?
- `action_priority_list[]`
  - `priority_score`: 조치 우선순위 점수
  - `event_type`: 품절/지연/가격상승/가격하락 등
  - `item`: vendor/product 결합 표시
  - `reason`: 왜 지금 대응이 필요한지
  - `recommended_action`: 바로 실행 가능한 권장 조치
  - `evidence_fields`: confidence, 최근시각, 가격변동 근거

### Q2. 어떤 상품을 어떻게 수정해야 하나?
- `change_summary_by_item[]`
  - `item`, `vendor`, `product_name`
  - `human_summary`: 사람이 읽는 문장 요약
  - `event_count`, `price_up_count`, `price_down_count`
  - `sold_out_count`, `delay_notice_count`
  - `max_abs_price_change_pct`, `last_event_at`
  - `recent_rooms`

### Q3. 가격 변동 폭/빈도는 어느 정도인가?
- `change_summary_by_item[].event_count`
- `change_summary_by_item[].max_abs_price_change_pct`
- `action_priority_list[].evidence_fields.price_delta_rate_pct`
- `evidence_fields.event_type_counts.PRICE_UP/PRICE_DOWN`

### Q4. 품절 예상/지연 영향이 큰 상품은?
- `stock_risk_items[]`
  - `risk_level`: HIGH/MEDIUM
  - `risk_reason`: 품절 발생/지연 공지
  - `last_seen_at`, `room_name`
  - `evidence_fields.confidence`, `stock_status`

### Q5. 이번 윈도우에서 전체적으로 무엇이 문제인가?
- `evidence_fields`
  - `window_hours`, `generated_at`
  - `action_item_count`, `stock_risk_count`, `items_with_changes`
  - `event_type_counts` (7유형 보조지표)

---

## 응답 설계 원칙
1. **행동 우선**: 권장 액션을 텍스트로 명시한다.
2. **근거 포함**: 최근시각/빈도/변동폭/신뢰도를 함께 노출한다.
3. **사람이 읽는 요약**: 상품별 변화는 문장형으로 제공한다.
4. **기존 호환 유지**: `today_alert_summary`, `recent_alert_feed`, `action_required_items`는 유지한다.
5. **과장 금지**: 계산 가능한 실제 이벤트 데이터만 사용한다.

---

## 프론트 섹션 구조 (의사결정 질문 순서)
1. 지금 당장 할 일 Top N (`action_priority_list`)
2. 가격/품절/지연 핵심 요약 (`evidence_fields`, `stock_risk_items`)
3. 상품별 변경 내용 (`change_summary_by_item`)
4. 권장 액션 (`recommended_actions`)
5. 보조 지표: 7종 알람 카운트 (`today_alert_summary`)
