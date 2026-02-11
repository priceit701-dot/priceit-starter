# priceit E2E 기획/수정 로드맵 (수집→정제→이벤트→알림→운영툴)

작성일: 2026-02-11  
범위: 현재 `priceit-starter` MVP 기준 전체 파이프라인 개선 실행계획

---

## 1) 현재 상태 요약 (As-Is)

현재 시스템은 아래 흐름으로 동작한다.

1. **수집(Ingestion)**
   - FastAPI `/ingest` 직접 입력
   - macOS 카카오톡 UI 자동화(`kakao_clipboard_collector.py`)로 복사/붙여넣기 수집
2. **정제/파싱(Cleansing/Parsing)**
   - 노이즈 필터(`_is_noise_line`) + 정규식 기반 룰 파싱(`parse_message`)
3. **이벤트 처리(Eventing)**
   - `events` 저장 + `products` 최신 상태 갱신
4. **알림(Notification)**
   - 특정 이벤트 타입만 Telegram 전송
5. **운영(Operation)**
   - 로그 파일, watchdog shell, 간단 리포트 스크립트

MVP로는 유효하나, E2E 관점에서 **정확도/중복/운영 가시성/확장성** 병목이 명확하다.

---

## 2) E2E 병목 진단 (Bottleneck)

### A. 수집
- **UI 자동화 의존도 높음**: 포커스/접근성 상태에 취약, 누락/오탐 가능
- **메시지 타임스탬프 신뢰도 낮음**: 대부분 `now()`로 저장되어 실제 발화시각 유실
- **중복 키 약함**: `hash(room_name|line)`만 사용 → 동일 문장 재공지/타 방 동일 문장 처리 취약

### B. 정제/파싱
- **룰 기반 확장 비용 증가**: 채널/문구 variation 증가 시 유지보수 급격히 어려움
- **제품명 정규화 미흡**: `cleaned[:50]` 방식으로 품목 식별 정확도 낮음
- **벤더 Alias 운영 미흡**: 사전 관리 프로세스/검증 부재

### C. 이벤트
- **이벤트 idempotency 없음**: 동일 이벤트 재발행 제어(윈도우/버전) 부재
- **신뢰도(confidence) 활용 미흡**: low-confidence 이벤트도 동일하게 downstream 처리
- **상태 전이 모델 부재**: SOLD_OUT→RESTOCK 등 lifecycle 추적 제한

### D. 알림
- **노이즈 필터링/라우팅 없음**: 중요도 기반 채널 분리 미구현
- **재시도/실패 큐 없음**: Telegram 실패 시 유실 가능
- **중복 알림 방지 부재**: 동일 이벤트 반복 발송 가능

### E. 운영툴
- **관측성 부족**: 단계별 처리량, 파싱 성공률, 실패율, 지연, 알림 실패율 지표 미노출
- **운영 콘솔 없음**: 규칙 수정/재처리/수동 정정이 코드 변경 중심
- **품질 게이트 없음**: 회귀 테스트셋/정확도 기준(DoD) 미정의

---

## 3) 개선 우선순위 (왜 이 순서인가)

### P0 (즉시): 데이터 신뢰도 + 중복 제어 + 운영 가시성
- 이유: 정확도보다 먼저 **데이터 품질/재현성/운영 안정성**을 확보해야 후속 개선이 의미 있음

### P1 (단기): 파싱 정확도 + 이벤트 품질
- 이유: 수집/저장 안정화 후 규칙 개선 및 상태전이 도입 시 ROI가 가장 큼

### P2 (중기): 알림 지능화 + 운영 툴링
- 이유: 사용자 체감 품질(알림 피로 감소, 대응 속도 증가)을 끌어올리는 단계

### P3 (확장): 모델 보조 분류/멀티채널 확장
- 이유: 룰 엔진 한계를 넘는 단계이며, 데이터셋/관측체계 확보 뒤 착수해야 비용 대비 효과가 큼

---

## 4) 실행 로드맵 (Phase별)

## Phase 0 (D0~D3): 안정화 베이스라인

### 작업 항목
1. **ingest_id 도입 (idempotency key)**
   - 기준: `source + room_name + sender + normalized_text + source_timestamp`
2. **메시지 원본 메타 확장**
   - `source`, `source_message_id`, `ingested_at`, `source_created_at` 컬럼 추가
3. **처리 파이프라인 로그 구조화(JSONL)**
   - 단계: ingest/filter/parse/event/notify 결과를 공통 correlation id로 로깅
4. **기본 운영 지표 스크립트 추가**
   - 일별 수집량, 파싱률, 이벤트 전환률, 알림 성공률

### DoD
- 중복 입력(동일 샘플 2회) 시 `messages/events` 증가율이 0~1% 이내
- `source_created_at` 없는 데이터 비율을 지표로 산출 가능
- 하루치 로그에서 이벤트 1건의 end-to-end trace 가능

---

## Phase 1 (D4~D10): 정제/파싱 정확도 개선

### 작업 항목
1. **정규화 레이어 분리** (`normalizer.py`)
   - 특수문자/공백/이모지/링크 처리 규칙 표준화
2. **제품명 canonicalization**
   - 상품명 토큰화 + stopword 제거 + 벤더별 normalize rule
3. **룰셋 외부화**
   - 이벤트 키워드/패턴을 yaml/json 설정 파일로 분리
4. **회귀 테스트셋 구축**
   - `data/messages_sample_*.txt/csv` 기반 정답 라벨 300~500건 구축

### DoD
- 회귀셋 기준 event-type macro F1 ≥ 0.85
- `PRICE_UP/DOWN`, `SOLD_OUT/RESTOCK` precision 각 ≥ 0.90
- 룰 변경 시 테스트 자동 실행(로컬 스크립트 또는 CI)

---

## Phase 2 (D11~D17): 이벤트 엔진 고도화

### 작업 항목
1. **상태 전이 모델 도입**
   - 상품별 상태: `UNKNOWN → IN_STOCK → SOLD_OUT → RESTOCK`
2. **이벤트 중복 억제 윈도우**
   - 동일 canonical product + event_type + n분 이내 재발행 차단
3. **confidence 게이트**
   - low-confidence는 `REVIEW_QUEUE`로 보내고 알림 보류
4. **재처리(replay) 유틸**
   - 기간/방 기준 raw message 재파싱 및 결과 비교

### DoD
- 중복 이벤트 발행율 50% 이상 감소(베이스라인 대비)
- 저신뢰 이벤트 알림 유출율 < 5%
- 재처리 결과 diff 리포트 자동 생성 가능

---

## Phase 3 (D18~D24): 알림 품질/신뢰성 강화

### 작업 항목
1. **알림 라우팅 정책**
   - 중요 이벤트(품절/재입고/급격한 가격변동) 우선 채널 분리
2. **알림 dedup 키 도입**
   - `(event_fingerprint, notify_window)` 기반 중복 억제
3. **실패 재시도 큐 + DLQ**
   - Telegram 전송 실패 시 재시도, 최종 실패는 DLQ 기록
4. **메시지 템플릿 개선**
   - 상품/벤더/가격변동폭/신뢰도/발생시각 포함

### DoD
- 알림 성공률 99%+
- 중복 알림 민원(운영 확인 기준) 주간 0~1건
- 실패 건은 재시도 또는 DLQ에서 반드시 추적 가능

---

## Phase 4 (D25~D35): 운영툴(Minimum Ops Console)

### 작업 항목
1. **운영 대시보드(읽기 전용부터)**
   - ingest량, parse율, event율, notify 성공률, top error
2. **수동 정정 툴**
   - vendor alias 편집, product canonical merge/split
3. **리뷰 큐 처리 화면**
   - low-confidence 이벤트 승인/기각
4. **운영 Runbook 문서화**
   - 장애 대응(수집 멈춤/알림 실패/DB lock) 절차

### DoD
- 비개발자 운영자가 코드 수정 없이 alias/정정 수행 가능
- 주요 장애 시 10분 내 원인 구간(수집/파싱/알림) 식별 가능
- Runbook 따라 신규 운영자 온보딩 1일 내 가능

---

## 5) 즉시 실행 가능한 작업 백로그 (이번 주)

## W1-1. 스키마 마이그레이션 초안
- 작업:
  - `messages`에 `source`, `source_message_id`, `source_created_at`, `ingested_at`, `ingest_id` 추가
  - `events`에 `event_fingerprint` 추가
- DoD:
  - 기존 DB 데이터 보존 마이그레이션 성공
  - 신규 컬럼 NULL/기본값 정책 문서화

## W1-2. ingest_id + event_fingerprint 생성기 구현
- 작업:
  - 정규화 텍스트 기반 fingerprint 함수 추가
  - 중복 입력 시 early return 처리
- DoD:
  - 샘플 재주입 테스트에서 duplicate insert 억제 확인

## W1-3. 구조화 로깅 도입
- 작업:
  - `logs/pipeline.jsonl` 작성
  - 공통 필드: `ts`, `trace_id`, `stage`, `status`, `room`, `event_type`, `error`
- DoD:
  - 1건 처리 시 최소 4단계 로그(ingest/filter/parse/notify) 확인

## W1-4. 품질 리포트 스크립트
- 작업:
  - `scripts/daily_metrics.py` 생성
  - 지표 CSV 출력 (일자별 ingest/parse/event/notify)
- DoD:
  - 최근 7일 지표 자동 출력 가능

## W1-5. 파서 회귀셋 v0 작성
- 작업:
  - 300건 라벨 파일 작성(`tests/fixtures/parser_gold_v0.jsonl`)
- DoD:
  - 테스트 실행 시 F1/precision/recall 계산 리포트 출력

---

## 6) 기술 결정 제안

- 저장소: 단기 SQLite 유지 + 마이그레이션 스크립트 도입, 중기 PostgreSQL 이관 검토
- 스케줄러: watchdog shell 유지하되 상태체크/재기동 결과를 JSON 로그로 남김
- API: `/ingest`는 source별 인증키(간단 shared secret) 추가
- 테스트: parser 회귀셋 + pipeline e2e smoke test를 최소 품질 게이트로 채택

---

## 7) 리스크와 대응

1. **카카오 UI 변경/포커스 이슈**
   - 대응: 수집 healthcheck + 무수집 경보(예: 15분)
2. **룰 복잡도 증가**
   - 대응: 룰 외부화 + 테스트셋 강제
3. **알림 피로도**
   - 대응: dedup + 중요도 라우팅 + 저신뢰 보류
4. **운영자 의존성(개발자 only)**
   - 대응: alias/리뷰 툴을 먼저 제공

---

## 8) 최종 완료 기준 (프로젝트 레벨 DoD)

아래 5개를 충족하면 “MVP→운영 가능한 v1”로 판정한다.

1. **정확도**: 핵심 이벤트 4종(PRICE_UP/DOWN/SOLD_OUT/RESTOCK) precision ≥ 0.90
2. **안정성**: 중복 이벤트율 주간 기준 50% 이상 개선
3. **신뢰성**: 알림 성공률 99%+, 실패 건 추적 100%
4. **가시성**: 일일 지표 자동 산출 + trace 기반 원인추적 가능
5. **운영성**: 비개발자가 alias/리뷰 큐 처리 가능

---

## 9) 다음 액션 (권장 착수 순서)

1. 스키마 확장 + ingest/event fingerprint 구현 (W1-1, W1-2)
2. 구조화 로깅 + 일일 지표 스크립트 (W1-3, W1-4)
3. 파서 회귀셋 v0 구축 및 기준선 측정 (W1-5)
4. 측정 결과 기반으로 Phase 1 룰 개선 착수

이 순서를 지키면 “추측 기반 개선”이 아니라 “측정 기반 개선”으로 전환된다.
