# OpenChat DB 재설계 적용/검증 리포트 (2026-02-12)

## 1) 적용 내용
- 적용 SQL: `sql/20260212_openchat_painpoint_schema.sql`
- 대상 DB: `data/priceit.db`
- 적용 명령:
```bash
sqlite3 data/priceit.db < sql/20260212_openchat_painpoint_schema.sql
```
- 실행 결과: `applied`

## 2) 검증 쿼리 #1 (7종 이벤트 분포)
```sql
SELECT event_type, COUNT(*) AS cnt
FROM openchat_event_fact
GROUP BY event_type
ORDER BY CASE event_type
  WHEN 'PRICE_UP' THEN 1
  WHEN 'PRICE_DOWN' THEN 2
  WHEN 'SOLD_OUT' THEN 3
  WHEN 'RESTOCK' THEN 4
  WHEN 'DELAY_NOTICE' THEN 5
  WHEN 'NEW_ITEM' THEN 6
  WHEN 'NOTICE' THEN 7
  ELSE 99 END;
```

### 결과
| event_type | cnt |
|---|---:|
| PRICE_UP | 40 |
| PRICE_DOWN | 366 |
| SOLD_OUT | 234 |
| RESTOCK | 629 |
| DELAY_NOTICE | 101 |
| NEW_ITEM | 112 |
| NOTICE | 358 |

## 3) 검증 쿼리 #2 (pain point 후보 샘플)
```sql
WITH base AS (
  SELECT
    im.vendor_name,
    im.product_name_norm AS item_name,
    SUM(CASE WHEN ef.event_type='PRICE_UP' THEN 1 ELSE 0 END) AS price_up_count,
    SUM(CASE WHEN ef.event_type='SOLD_OUT' THEN 1 ELSE 0 END) AS sold_out_count,
    SUM(CASE WHEN ef.event_type='DELAY_NOTICE' THEN 1 ELSE 0 END) AS delay_count
  FROM openchat_event_fact ef
  JOIN openchat_item_master im ON im.id=ef.item_id
  WHERE datetime(ef.event_at) >= datetime('now','-72 hours')
  GROUP BY im.vendor_name, im.product_name_norm
)
SELECT
  vendor_name,
  item_name,
  price_up_count,
  sold_out_count,
  delay_count,
  CASE WHEN price_up_count>=2 THEN 'Y' ELSE 'N' END AS price_spike_risk,
  CASE WHEN sold_out_count>=2 THEN 'Y' ELSE 'N' END AS repeat_sold_out
FROM base
WHERE (price_up_count>=2 OR sold_out_count>=2 OR delay_count>=1)
ORDER BY (sold_out_count+delay_count) DESC, price_up_count DESC
LIMIT 10;
```

### 결과 샘플 (실행 출력 그대로)
- UNKNOWN / #품절 #긴급 → 반복품절=Y
- 미출고 리스트 / 최고집 → 공급지연 신호(delay_count=2)

> 주의: 기존 레거시 데이터에 상태어 기반 상품명이 섞여 있어 상위 샘플에 노이즈가 존재함. 신규 스키마 + parser 병행 적재부터 점진적으로 개선됨.

## 4) 코드 검증
- `python3 -m unittest tests/test_parser_rules.py` → OK (4 tests)
- `python3 -m py_compile src/parser.py src/pipeline.py src/api.py src/db.py` → OK

## 5) 반영 확인 포인트
- `/stats/seller` 응답에 `change_summary_by_item[].pain_points` 추가.
- `/stats/seller` 응답에 `pain_point_candidates` 추가.
