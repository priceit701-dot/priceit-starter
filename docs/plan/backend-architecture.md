# priceit-starter 백엔드/API 아키텍처 기획안

> 작성일: 2026-02-11
> 범위: 수집 파이프라인, import 표준화, DB 스키마 개선, API 계약 확장, 검증 에이전트 승인 게이트, 장애복구 플로우, 현재 코드 기준 gap/우선순위

## 1) 목표와 설계 원칙

- **신뢰성 우선**: "데이터 저장 성공"과 "이벤트 파싱 성공"을 분리해 부분 실패를 허용.
- **재처리 가능성**: raw 원문과 import 메타를 보존하여 파서 개선 시 재분류 가능.
- **조회 성능**: 시간순/유형순 조회에 맞는 인덱스/파티셔닝(논리) 적용.
- **검증 게이트 강제**: Validator 승인 없이는 성공 상태를 외부 노출 금지.
- **운영 복구성**: 실패 원인별 복구 루트(runbook + 자동 재시도 + 수동 재처리) 명확화.

---

## 2) 수집 파이프라인(목표 아키텍처)

```text
[Source]
  ├─ API /ingest
  ├─ CSV importer
  └─ Text export importer
      ↓
[Normalizer]
  - 공통 메시지 Envelope 생성
  - 시간/발신자/룸/본문 표준화
      ↓
[Deduper]
  - source + external_id + content_hash 기반 중복 제거
      ↓
[Raw Store]
  - message_ingest_log (raw + parse_state)
      ↓
[Parser]
  - rule parser + context parser
  - confidence/parse_version 기록
      ↓
[Domain Write]
  - events
  - product_state (upsert)
      ↓
[Index/Materialized Aggregation]
  - timeline rollup (hour/day)
  - room/type별 통계 캐시
      ↓
[API / Dashboard / Alert]
```

### 처리 단계 상세

1. **Ingest**: 입력 채널별 adapter가 공통 Envelope로 변환.
2. **Normalize**: timezone(Asia/Seoul) 강제, created_at 파싱 실패 시 `ingest_at` fallback + 에러코드 적재.
3. **Dedup**: `dedup_key = sha1(source|room|sender|created_at|message_text)`.
4. **Persist Raw**: 파싱 실패해도 raw는 저장.
5. **Parse**: 이벤트 후보 0..N개 생성 (현 구조 1개 제한 → 다건 이벤트 확장 고려).
6. **Write Domain**: 트랜잭션으로 `events` + `product_state` 반영.
7. **Emit**: 알림은 이벤트 write 성공 후 비동기 큐에서 수행(알림 실패가 DB 트랜잭션 롤백 유발 금지).

---

## 3) CSV/텍스트 import 표준화

현재 `import_kakao_csv.py`, `import_kakao_export.py`가 포맷별 분리되어 있으며 timestamp/room 추론 규칙도 분산됨. 이를 **공통 Import Contract**로 통합.

### 3.1 공통 Import Envelope

```json
{
  "source": "kakao_csv | kakao_txt | api",
  "source_file": "optional path",
  "source_line_no": 123,
  "room_name": "...",
  "sender": "...",
  "message_text": "...",
  "created_at": "2026-02-11T14:30:00+09:00",
  "ingest_at": "server time",
  "external_id": "optional",
  "raw_payload": "original row/line"
}
```

### 3.2 표준화 규칙

- 시간: ISO8601 + timezone 포함 저장(권장: UTC 저장 + API 응답 시 KST 변환 옵션).
- sender/room trim + 빈값 fallback (`unknown`, `unknown_room`).
- 본문 normalize: 줄바꿈/제로폭 문자 정리하되 원문은 `raw_payload` 보존.
- 에러 분류:
  - `INVALID_TIMESTAMP`
  - `EMPTY_MESSAGE`
  - `UNSUPPORTED_FORMAT`
  - `DUPLICATE`

### 3.3 Import 실행 인터페이스

- `python -m src.import_messages --source kakao_csv --path ... --room ...`
- `python -m src.import_messages --source kakao_txt --path ... --room ...`
- dry-run 지원: `--dry-run` (DB 쓰기 없이 파싱 통계 출력)
- 결과 리포트(JSON): total/read/imported/duplicated/parse_failed/errors

---

## 4) DB 스키마 개선안 (시간순/유형순 조회 최적화)

## 4.1 현행 스키마 요약

- `messages(room_name, sender, message_text, created_at, hash UNIQUE)`
- `events(message_id, room_name, vendor, product_name, event_type, created_at, ...)`
- 인덱스:
  - `idx_messages_room_time(room_name, created_at)`
  - `idx_events_type_time(event_type, created_at)`

### 한계

- `created_at`이 TEXT이며 timezone 일관성 미보장.
- 이벤트 조회 주요 패턴(룸+시간, 룸+타입+시간)에 대한 복합 인덱스 부족.
- import provenance(파일/라인) 미기록 → 재처리/감사 어려움.
- parse_version, parser_error 저장 부재.

## 4.2 제안 스키마

### messages (확장)

- `id PK`
- `source TEXT NOT NULL` (api/csv/txt/collector)
- `source_file TEXT NULL`
- `source_line_no INTEGER NULL`
- `external_id TEXT NULL`
- `room_name TEXT NOT NULL`
- `sender TEXT`
- `message_text TEXT NOT NULL`
- `raw_payload TEXT`
- `created_at DATETIME NOT NULL` (UTC)
- `ingested_at DATETIME NOT NULL`
- `dedup_key TEXT UNIQUE`
- `parse_state TEXT NOT NULL DEFAULT 'PENDING'` (PENDING/SUCCESS/FAILED/SKIPPED)
- `parse_error_code TEXT NULL`

인덱스:
- `idx_messages_created_at(created_at DESC)`
- `idx_messages_room_created(room_name, created_at DESC)`
- `idx_messages_source_created(source, created_at DESC)`

### events (확장)

- 기존 컬럼 +
- `event_time DATETIME NOT NULL` (메시지 기준 시간)
- `parse_version TEXT NOT NULL`
- `confidence REAL`

인덱스:
- `idx_events_time(event_time DESC)`
- `idx_events_room_time(room_name, event_time DESC)`
- `idx_events_type_time(event_type, event_time DESC)`
- `idx_events_room_type_time(room_name, event_type, event_time DESC)`  ← 핵심

### product_state (products 대체/명확화)

- `canonical_key PK UNIQUE`
- `vendor`, `product_name`
- `latest_price`, `last_stock_status`
- `first_seen_at`, `last_seen_at`, `last_event_type`

### rollup tables (옵션)

- `event_hourly_stats(hour_bucket, room_name, event_type, count)`
- `event_daily_stats(day_bucket, room_name, event_type, count)`

> SQLite 유지 시에도 rollup으로 대시보드 속도 확보 가능. 중장기엔 PostgreSQL 이전 용이한 구조.

---

## 5) API 계약 확장안

기존 `/stats/summary`, `/stats/timeline`를 호환 유지하면서 필터/타임라인 상세 제공.

## 5.1 GET `/stats/summary` (확장)

Query:
- `from` (ISO datetime, optional)
- `to` (ISO datetime, optional)
- `room` (optional, 다중은 comma)
- `event_type` (optional, 다중 가능)
- `tz` (`UTC|Asia/Seoul`, default UTC)

Response 예시:

```json
{
  "messages": 12450,
  "events": 3288,
  "last_message_at": "2026-02-11T14:40:11Z",
  "rooms": [{"room":"최고집","messages":8120,"events":2110}],
  "events_by_type": [{"type":"PRICE_UP","count":521}],
  "window": {"from":"...","to":"...","tz":"Asia/Seoul"}
}
```

## 5.2 GET `/stats/timeline` (확장)

Query:
- `bucket` = `hour|day` (default hour)
- `limit` (default 48)
- `room` (optional)
- `event_type` (optional)
- `include_messages` (bool, default false)

Response:

```json
{
  "bucket": "hour",
  "timeline": [
    {
      "time": "2026-02-11T13:00:00Z",
      "events": 14,
      "messages": 120,
      "by_type": {"PRICE_UP":4,"SOLD_OUT":2}
    }
  ]
}
```

## 5.3 신규 GET `/events`

목적: 룸/유형/시간 필터 기반 원시 이벤트 조회

Query:
- `room`, `event_type`, `vendor`, `product_name_like`
- `from`, `to`
- `cursor` or `offset/limit`
- `sort` = `event_time_desc|event_time_asc`

## 5.4 신규 GET `/rooms`

- 룸 목록 + 최근 이벤트 시간 + 카운트 제공 (필터 UI 초기 로딩 최적화)

### API 운영 정책

- 모든 통계 API는 서버 기본 pagination/limit 강제.
- datetime 파라미터 검증 실패 시 400 + 명확한 code 반환.
- 응답에 `generated_at`, `query_cost_ms` 포함(운영 디버깅용).

---

## 6) "검증 에이전트 승인 없는 성공 보고 금지" 로직

현 `automation/controller.py`는 validator pass 시 status=success 로그를 남기지만, **성공 보고 제어면**이 명시적으로 분리되어 있지 않음. 다음 게이트를 추가.

### 6.1 상태 모델

- `RUN_EXECUTED`
- `VALIDATION_PASSED`
- `APPROVED`
- `REPORTED_SUCCESS`  (이 상태 전이 전 외부 성공 보고 금지)

### 6.2 승인 토큰 설계

- Validator가 `APPROVAL_TOKEN:<uuid>`를 발급해야만 report 단계 진입.
- report 모듈은 토큰 없는 success payload 전송 시 hard-fail.

### 6.3 정책 예시

`policy.json`:

```json
{
  "require_approval_token": true,
  "approval_token_prefix": "APPROVAL_TOKEN:",
  "forbid_success_without_approval": true
}
```

### 6.4 금지 규칙

- `validator.pass == true`여도 `approval_token` 없으면 상태는 `READY_FOR_APPROVAL`로 유지.
- 텔레그램/외부 채널에 "성공" 단어 포함 메시지 전송 금지(정책 플래그 기반).

---

## 7) 장애복구(Disaster Recovery) 플로우

## 7.1 장애 유형

1. **수집 중단**: collector/api 다운
2. **파서 오류 급증**: parse_failed 비율 임계치 초과
3. **DB 손상/잠금**: sqlite busy/locked/corrupt
4. **알림 실패**: telegram API 오류

## 7.2 복구 단계

1. **감지**: `/health` + watchdog + 실패율 메트릭
2. **격리**: 신규 ingest는 계속 받되 parse/notify를 degrade mode로 분리 가능
3. **복원**:
   - sqlite lock: 재시도(backoff) + 단일 writer 보장
   - sqlite corrupt: 최신 백업 복원 후 `message_ingest_log` replayer로 누락구간 재처리
4. **검증**: row count, 최근 1시간 이벤트 건수, 샘플 파싱 정확도 비교
5. **재개**: 승인 토큰 발급 후 success report

## 7.3 백업/리텐션 권장

- DB 스냅샷: 시간당 1회 + 일간 보관 14일
- raw import 파일: 최소 30일 보관
- 재처리 커맨드 제공:
  - `python -m src.replay --from ... --to ... --source kakao_csv`

---

## 8) 현재 코드 기준 Gap 분석

## 8.1 수집/표준화

- **현재**: 소스별 importer가 직접 `ingest_line` 호출, 공통 envelope 없음.
- **Gap**: provenance, parse_state, 표준 에러코드, dry-run 미지원.

## 8.2 DB

- **현재**: 최소 스키마 + 기본 인덱스 2개.
- **Gap**: 룸+유형+시간 복합조회 최적화 부족, created_at timezone 일관성 부족, 재처리 추적 컬럼 부재.

## 8.3 API

- **현재**: `/stats/summary`, `/stats/timeline(limit_hours)` 단순 제공.
- **Gap**: room/event_type 필터 부재, 버킷 옵션 부재, 원시 이벤트 조회 API 부재.

## 8.4 검증 게이트

- **현재**: validator pass/fail은 있으나 approval 토큰 기반 성공 보고 차단 없음.
- **Gap**: "승인 없는 성공 보고 금지" 요구 미충족.

## 8.5 장애복구

- **현재**: watchdog 스크립트 수준, 표준 DR runbook/복구 검증 체크 미흡.
- **Gap**: 백업-복원-재처리 표준 절차 및 자동화 미구축.

---

## 9) 우선순위 구현 순서 (실행 로드맵)

### P0 (즉시)

1. **API 필터 확장**: `/stats/summary`, `/stats/timeline`에 room/event_type/time window 추가.
2. **DB 인덱스 추가**: `idx_events_room_type_time`, `idx_events_room_time`, `idx_messages_created_at`.
3. **검증 게이트 최소 구현**: approval token 없으면 success report 금지.

### P1 (단기)

4. **Import 표준화 모듈 도입**: 공통 envelope + unified CLI + dry-run.
5. **messages/events 스키마 확장 마이그레이션**: source/provenance/parse_state/parse_version.
6. **`/events`, `/rooms` API 추가**.

### P2 (중기)

7. **rollup 테이블 + 배치 집계**(timeline 고속화).
8. **재처리(replay) 도구** + parser versioning 전략.
9. **DR 자동화**: backup/restore script + 복구 검증 체크 자동 리포트.

### P3 (중장기)

10. PostgreSQL 전환 검토(멀티 writer/고급 인덱스/운영성 개선).

---

## 10) 수용 기준(Definition of Done)

- room/type/time 필터 쿼리의 p95 응답시간 목표 충족(예: <300ms@최근7일).
- 승인 토큰 없는 success report 0건(정책 위반 테스트 포함).
- import dry-run/실행 결과 JSON 리포트 재현 가능.
- 장애 복구 리허설(월 1회)에서 RTO/RPO 목표 충족.

---

## 부록 A: 최소 마이그레이션 SQL 예시

```sql
ALTER TABLE messages ADD COLUMN source TEXT DEFAULT 'api';
ALTER TABLE messages ADD COLUMN source_file TEXT;
ALTER TABLE messages ADD COLUMN source_line_no INTEGER;
ALTER TABLE messages ADD COLUMN ingested_at TEXT;
ALTER TABLE messages ADD COLUMN parse_state TEXT DEFAULT 'PENDING';
ALTER TABLE messages ADD COLUMN parse_error_code TEXT;

ALTER TABLE events ADD COLUMN event_time TEXT;
ALTER TABLE events ADD COLUMN parse_version TEXT DEFAULT 'v1';

CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_room_time ON events(room_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_room_type_time ON events(room_name, event_type, created_at DESC);
```

> SQLite 특성상 대규모 컬럼 변경은 shadow table 방식이 더 안전할 수 있음.
