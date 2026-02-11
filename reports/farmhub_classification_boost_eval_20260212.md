# farmhub/최고집 상품명 분류율 강화 평가 (2026-02-12)

## 범위/근거
- DB: `data/priceit.db`
- 기간: 최근 7일
- 룸 필터: `room_name like '최고집%' or room_name like '%팜허브%'`
- 이벤트 표본 수: **42건**

## before/after 비교

| 지표 | before | after | 변화 |
|---|---:|---:|---:|
| 미분류 건수 | 15 | 6 | -9 |
| 미분류율 | 35.71% | 14.29% | -21.43%p |
| 공지문구 오분류(상품명으로 노출) | 0 | 0 | 0 |

## 미분류 → 분류 개선 사례 (샘플 10)
- id 1650 / RESTOCK / `골드키위` (template)
  - msg: 2월 9일 골드키위 입고
- id 1653 / RESTOCK / `홍매향 중소과` (room_context_recent)
  - msg: 2월 9일 부사 입고
- id 1654 / RESTOCK / `가정용 배` (message_keyword)
  - msg: 2월 9일 가정용 배 입고
- id 1661 / RESTOCK / `깐마늘` (template)
  - msg: 2월 10일 미니오이, 깐마늘 입고
- id 1663 / RESTOCK / `골드키위` (template)
  - msg: 2월 10일 골드키위 입고
- id 747 / RESTOCK / `골드키위` (template)
  - msg: 2월 10일 골드키위 입고
확실한 매출 최고집과 함께 시작하세요 !
- id 1664 / RESTOCK / `미나리` (template)
  - msg: 2월 10일 미니오이, 백오이, 비트, 콜라비, 미나리 입고
- id 748 / RESTOCK / `미나리` (template)
  - msg: 2월 10일 미니오이, 백오이, 비트, 콜라비, 미나리 입고
눈으로 확인하고, 손으로 만져본  
진짜배기만 출고됩니다 !
- id 1669 / RESTOCK / `구좌당근` (room_context_recent)
  - msg: 2월 11일 부사 입고대표님의 상품 출고가

## 오분류 사례 점검 (after)
- 점검 기준(공지/안내/알림/배송/출고 문자열 포함)에 해당하는 after 오분류 샘플 없음