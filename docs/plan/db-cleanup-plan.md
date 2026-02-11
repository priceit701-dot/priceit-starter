# priceit-starter DB 정리/개선 기획서 (실측 기반)

작성일: 2026-02-12  
대상 DB: `data/priceit.db`  
검증 스크립트: `scripts/db_audit.py`  
검증 결과 파일: `reports/db_audit_20260212.json`

---

## 0) 요약 (핵심 결론)

- **중복 자체는 낮음**: 메시지/이벤트 중복 그룹 0건 (현재 dedup 로직은 효과적).
- **가장 큰 품질 리스크는 정규화**:
  - `events.vendor` NULL 1,167건 (**63.42%**)
  - `events.product_name` NULL 160건 (**8.70%**)
  - `vendor/product`에 ISO timestamp 오염 327건 (**17.77%**) 
- **event_type 표준 불일치**: 운영 타깃 7종 외 `PRICE_SEEN`, `SOLD_OUT_RISK` 존재.
- **created_at 포맷은 양호**: 파싱 실패 0건, 미래/이상치 0건.
- **인덱스는 기능 대비 부족**: `events`는 `idx_events_type_time`만 존재하여 room/time, message join 계열 조회에 비효율 가능.

즉, 이번 정리는 “중복 제거”보다 **이벤트 표준화 + 차원(alias) 정리 + 알람 중심 조회 구조화**가 우선순위다.

---

## 1) 현재 DB 스키마/인덱스/데이터 품질 진단

## 1-1. 스키마/인덱스 현황

### 테이블
- `messages(id, room_name, sender, message_text, raw_line, created_at, hash)`
- `events(id, message_id, room_name, vendor, product_name, event_type, old_price, new_price, stock_status, confidence, created_at)`
- `products(id, vendor, product_name, canonical_key, latest_price, last_stock_status, updated_at)`
- `ingestion_audit(...)`

### 인덱스
- messages: `idx_messages_room_time`, `idx_messages_room_line_time`, `hash UNIQUE`
- events: `idx_events_type_time` (단일)
- products: `canonical_key UNIQUE`
- ingestion_audit: `idx_ingestion_audit_time`

**진단**: `events`에 `message_id`, `room_name+created_at`, `created_at` 단독, `vendor+product` 인덱스 부재.

## 1-2. 실측 수치

- messages: **37,694**
- events: **1,840**
- products: **1,115**
- ingestion_audit: **0**

## 1-3. 중복 진단

- 메시지 중복 (room+sender+message+created_at): **0건**
- 이벤트 중복 (message+event_type+vendor+product): **0건**

> 결론: 현재 로직 기준 중복은 구조적 이슈 아님.

## 1-4. room_name 표준화 진단

- room_name distinct: **83**
- trim/lower/공백정규화 기준 distinct: **83**
- 잠재 변형군: **0**

> 표면상 표준화는 양호. 단, `bench_room_%` 데이터 유입(327건)은 운영/테스트 분리 과제.

## 1-5. vendor/product 정규화 진단

- `events.vendor` NULL: **1,167건 (63.42%)**
- `events.product_name` NULL: **160건 (8.70%)**
- `events.vendor` ISO timestamp 형태: **327건 (17.77%)**
- `events.product_name` ISO timestamp 형태: **327건 (17.77%)**

샘플:
- `vendor = 2026-02-12T00:07:58`
- `product_name = 2026-02-12T00:07:58`
- 동일 row에서 `created_at`와 값이 같음

해석:
- `message_text`의 `[ ... ]` bracket 값을 vendor로 파싱하는 로직 영향으로 보임.
- 벤치 데이터(`bench_room_%`)가 운영 DB에 혼합되어 통계 오염.

## 1-6. event_type 일관성

실제 타입 9종:
- 표준 7종: `PRICE_UP`, `PRICE_DOWN`, `SOLD_OUT`, `RESTOCK`, `DELAY_NOTICE`, `NEW_ITEM`, `NOTICE`
- 비표준 2종: `PRICE_SEEN`(5), `SOLD_OUT_RISK`(2)

> 타깃 모델 대비 불일치 2종 존재. 알람 뷰/집계에서 매핑 규칙 필요.

## 1-7. created_at 품질

- `messages.created_at` 파싱 실패: 0
- `events.created_at` 파싱 실패: 0
- 2020 이전/미래(+1일 초과): 0

> 시각 컬럼 품질은 현재 양호.

---

## 2) 정리 계획서

## 2-1. 즉시 적용(무중단)

목표: 서비스 중단 없이 “조회 품질”을 먼저 올림.

1. **표준화 보조 테이블 추가**
   - `room_aliases`, `vendor_aliases_db`, `product_aliases_db`, `event_type_map`
2. **알람 정규화 뷰 추가**
   - `v_events_alarm` (raw → std 매핑, ISO 오염값 NULL 처리)
3. **조회 인덱스 추가**
   - `events(created_at)`, `events(room_name, created_at)`, `events(message_id)`, `events(vendor, product_name)`, `products(updated_at)`

적용 SQL: `sql/20260212_db_cleanup_phase1_nondisruptive.sql`

## 2-2. 점진 마이그레이션

목표: 운영 안정성 유지하며 정규화 모델로 전환.

1. `events_v2` 생성 (event_type CHECK 포함)
2. `events` → `events_v2` 백필 (`event_type_map` 기반 표준화)
3. API를 `v_events_alarm` 또는 `events_v2` 우선 조회로 전환
4. 일정 기간 dual-read 검증 후 완전 전환

적용 SQL: `sql/20260212_db_cleanup_phase2_gradual_migration.sql`

## 2-3. 리스크 항목 분리

- **R1. parser 규칙 변경 시 분류율 하락**
  - 대응: event_type_map로 우선 흡수, 파서 변경은 별도 배포
- **R2. alias 오매핑**
  - 대응: alias 테이블 is_active + 업데이트 로그 관리
- **R3. 벤치/운영 데이터 혼합**
  - 대응: `room_name like 'bench_room_%'` 분리 정책(삭제 아님, 필터링 우선)
- **R4. 롤백 부재**
  - 대응: 사전 백업 + `sql/20260212_db_cleanup_rollback.sql` 준비

---

## 3) 알람유형 중심 모델 점검 및 설계 제안

타깃 이벤트:  
`PRICE_UP`, `PRICE_DOWN`, `SOLD_OUT`, `RESTOCK`, `DELAY_NOTICE`, `NEW_ITEM`, `NOTICE`

## 3-1. 컬럼/모델 제안

- `event_type_std` (표준 7종)
- `severity` (`low|normal|high`)
- `is_alert` (0/1)
- `is_supported` (파서 공식 지원 여부)
- `vendor_std`, `product_std`, `room_name_std`

> 즉시 적용은 물리 컬럼 추가 대신 `v_events_alarm` 뷰로 제공 (무중단).

## 3-2. 뷰 제안

- `v_events_alarm`: raw+std 동시 제공
  - 비표준 타입 매핑 (`PRICE_SEEN -> NOTICE`, `SOLD_OUT_RISK -> SOLD_OUT`)
  - timestamp 오염 vendor/product는 NULL 처리

## 3-3. 인덱스 제안

- `events(event_type, created_at)` 유지
- `events(room_name, created_at)` 추가
- `events(message_id)` 추가
- `events(vendor, product_name)` 추가
- (v2 전환 시) `events_v2(event_type, created_at)`, `events_v2(room_name_std, created_at)`

---

## 4) 실행안 (초안)

## 4-1. SQL 마이그레이션 초안

- 1단계(무중단): `sql/20260212_db_cleanup_phase1_nondisruptive.sql`
- 2단계(점진): `sql/20260212_db_cleanup_phase2_gradual_migration.sql`
- 롤백: `sql/20260212_db_cleanup_rollback.sql`

## 4-2. 백업/롤백 절차

### 백업
```bash
cd priceit-starter
cp data/priceit.db data/priceit.db.bak.$(date +%Y%m%d_%H%M%S)
sqlite3 data/priceit.db ".backup data/priceit.backup.$(date +%Y%m%d_%H%M%S).db"
```

### 적용
```bash
sqlite3 data/priceit.db < sql/20260212_db_cleanup_phase1_nondisruptive.sql
# 점진 전환 시
sqlite3 data/priceit.db < sql/20260212_db_cleanup_phase2_gradual_migration.sql
```

### 롤백
```bash
sqlite3 data/priceit.db < sql/20260212_db_cleanup_rollback.sql
# 또는 백업 파일로 원복
cp data/priceit.db.bak.YYYYMMDD_HHMMSS data/priceit.db
```

## 4-3. 검증 쿼리

```sql
-- 핵심 건수
select count(*) from events;
select count(*) from v_events_alarm;

-- 표준 타입 분포
select event_type_std, count(*)
from v_events_alarm
group by 1
order by 2 desc;

-- 비지원 타입 모니터링
select event_type_raw, event_type_std, is_supported
from event_type_map
where is_supported = 0;

-- 오염값 잔여 확인
select count(*) from v_events_alarm where vendor_raw like '____-__-__T__:%';
select count(*) from v_events_alarm where product_raw like '____-__-__T__:%';

-- 인덱스 확인
pragma index_list('events');
```

---

## 5) 산출물 파일

- 문서: `docs/plan/db-cleanup-plan.md`
- 진단 스크립트: `scripts/db_audit.py`
- SQL 초안:
  - `sql/20260212_db_cleanup_phase1_nondisruptive.sql`
  - `sql/20260212_db_cleanup_phase2_gradual_migration.sql`
  - `sql/20260212_db_cleanup_rollback.sql`
- 진단 리포트(JSON): `reports/db_audit_20260212.json`

---

## 6) 실제 검증 수치 (data/priceit.db 기준)

- 총 메시지: 37,694
- 총 이벤트: 1,840
- 총 상품: 1,115
- 메시지 중복(정의 기준): 0
- 이벤트 중복(정의 기준): 0
- room_name 변형군: 0
- vendor NULL: 1,167 (63.42%)
- product_name NULL: 160 (8.70%)
- vendor/product timestamp 오염: 각 327 (17.77%)
- 비표준 event_type: 2종 (`PRICE_SEEN`, `SOLD_OUT_RISK`)
- created_at 파싱 실패: 0

---

## 7) 후속 권고 (코드 레벨)

1. `src/parser.py`의 `[ ... ]` 패턴을 vendor로 해석할 때, ISO datetime 패턴은 vendor로 채택하지 않도록 가드.
2. `bench_room_%` ingest를 운영 DB와 분리(별도 DB 또는 `source='bench'` 컬럼).
3. `src/pipeline.py` 저장 시점에 `event_type_map` 기반 표준화 옵션 도입(플래그 기반).

> 본 문서는 실제 DB 실측 결과를 기반으로 작성했으며, 향후 데이터 유입 패턴 변화 시 `scripts/db_audit.py` 재실행으로 수치를 갱신해야 함.
