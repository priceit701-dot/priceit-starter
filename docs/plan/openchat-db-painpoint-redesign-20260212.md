# OpenChat DB 재설계안 (Pain Point 즉시 식별) - 2026-02-12

## 1) 목표 / 범위
- 쿠팡 농산물 카테고리 학습 + 상품명/옵션 학습 결과를 DB 모델에 반영.
- 상태어(공지/안내/품절 텍스트)보다 **실상품명 + 옵션**을 우선 키로 저장.
- 이벤트는 아래 7종만 표준 저장:
  `PRICE_UP, PRICE_DOWN, SOLD_OUT, RESTOCK, DELAY_NOTICE, NEW_ITEM, NOTICE`
- `/stats/seller` 응답에서 셀러 pain point 필드(가격급등리스크, 반복품절, 공급지연, 옵션혼선, 마진압박후보)를 노출.

## 2) 기존 한계
- `events`는 `vendor + product_name` 중심 단일 문자열 구조로 옵션 차원을 분리하지 못함.
- 비표준 타입(`PRICE_SEEN`, `SOLD_OUT_RISK`)이 섞여 이벤트 집계 일관성이 떨어짐.
- `/stats/seller`가 행동우선순위는 제공하지만 pain point를 명시 필드로 반환하지 않음.
- 상태어가 product_name으로 들어오면 실상품 기준 누적 분석이 약해짐.

## 3) 신규 스키마 (테이블/컬럼/인덱스)

### A. `openchat_item_master`
- 목적: 실상품명 중심 마스터
- 주요 컬럼:
  - `canonical_item_key` (UNIQUE): `vendor|product`
  - `vendor_name`, `product_name_raw`, `product_name_norm`
  - `coupang_category_l1`, `coupang_category_l2`, `item_type_hint`
  - `first_seen_at`, `last_seen_at`
- 인덱스: `(vendor_name, product_name_norm)`

### B. `openchat_item_option`
- 목적: 옵션 분리 저장(중량/등급/포장 등)
- 주요 컬럼:
  - `item_id` (FK), `option_name_raw`, `option_name_norm`
  - `unit`, `spec_value`, `pack_count`, `weight_gram`
  - UNIQUE `(item_id, option_name_norm)`
- 인덱스: `(item_id, option_name_norm)`

### C. `openchat_event_fact`
- 목적: 7종 이벤트 표준 팩트
- 주요 컬럼:
  - `legacy_event_id` (기존 events.id 연결), `message_id`
  - `room_name`, `vendor_name`, `item_id`, `option_id`
  - `event_type` CHECK(7종)
  - `old_price`, `new_price`, `stock_status`, `confidence`, `event_at`
- 인덱스:
  - `(event_at)`
  - `(event_type, event_at)`
  - `(item_id, option_id, event_at)`

## 4) pain point 산출 규칙
- 산출 윈도우: `/stats/seller?limit_hours=N` 범위
- 기준 단위: item(필요시 option 포함)

1. **가격급등리스크**
   - `price_up_count >= 2` 또는 `max_abs_price_change_pct >= 7`
2. **반복품절**
   - `sold_out_count >= 2`
3. **공급지연**
   - `delay_notice_count >= 1`
4. **옵션혼선**
   - 동일 item에서 단기 내 상/하향 가격 이벤트가 혼재 (`event_count>=3` & up/down 동시 발생)
5. **마진압박후보**
   - 가격인상 우세 + 변동폭 존재(>=5%) 또는
   - 가격인상과 품절/지연 이벤트가 동반

## 5) 구현 반영 요약
- `src/parser.py`
  - `ParsedEvent`에 `option_name` 추가.
  - 상품 프로파일 옵션 토큰을 이벤트에 연결.
  - 비표준 이벤트를 저장 단계에서 7종으로 수렴 가능한 형태로 정리(위험성 문구는 NOTICE/stock_status로 흡수).
- `src/pipeline.py`
  - 기존 `events/products` 적재 유지.
  - 신규 스키마(`openchat_item_master/openchat_item_option/openchat_event_fact`) 병행 적재 추가.
  - 이벤트 타입은 적재 시 7종 표준화.
- `src/api.py` (`/stats/seller`)
  - `change_summary_by_item[].pain_points` 필드 추가.
  - `pain_point_candidates` 배열 추가.

## 6) 이행 전략
1. SQL 마이그레이션 적용 후 과거 데이터 백필.
2. 파이프라인 병행 적재로 신규 이벤트부터 자동 누적.
3. `/stats/seller`에서 pain point 노출 검증.
4. 차기 단계에서 `openchat_event_fact` 기반 집계로 완전 전환.
