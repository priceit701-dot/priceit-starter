# Priceit Starter 운영 대시보드 MVP 기획안 (프론트엔드 + API 연동)

> 기준: 현재 `priceit-starter` 코드베이스(FastAPI + SQLite + parser/pipeline)
> 목표: 운영자가 **방/이벤트/알림 상태**를 한 화면에서 파악하고, 이상 징후를 빠르게 확인하는 MVP(1~2주)

---

## 1) 목표/범위

### MVP 목표
- 운영자가 다음 3가지를 실시간/준실시간으로 확인
  - **방 상태(Room Health)**: 최근 메시지 유입 여부, 이벤트 발생량
  - **이벤트 상태(Event Feed)**: 품절/재입고/가격변동/공지 등 최근 이벤트
  - **알림 상태(Alert Delivery)**: 텔레그램 알림 성공/실패 및 지연

### 비목표(이번 MVP에서 제외)
- 완전한 권한 관리(RBAC)
- 복잡한 규칙 편집 UI
- 멀티 테넌시/고급 분석 대시보드
- 실시간 소켓 스트리밍(폴링 기반으로 시작)

---

## 2) 현재 시스템 요약 (As-Is)

### 현재 API
- `GET /health` : 서버 상태
- `POST /ingest` : 메시지 수집 입력

### 현재 DB 스키마(핵심)
- `messages`: room_name, sender, message_text, created_at, hash(중복방지)
- `events`: event_type, vendor, product_name, old/new_price, stock_status, confidence
- `products`: canonical_key 기준 최신 가격/재고 상태

### 현재 파이프라인
1. `/ingest` 수신
2. noise 필터링 + `messages` 저장
3. parser로 이벤트 추출 후 `events` 저장
4. `products` 최신 상태 업데이트
5. 중요 이벤트 텔레그램 전송

---

## 3) MVP 정보구조(IA)

## 화면 구조

1. **대시보드 홈 (`/dashboard`)**
   - 상단 KPI 카드
     - 최근 1시간 메시지 수
     - 최근 1시간 이벤트 수
     - 품절/재입고 건수
     - 알림 실패 건수
   - 방 상태 테이블(최근 수집시각, 1h 이벤트 수, 상태)
   - 최근 이벤트 피드(최신 20건)
   - 알림 전송 상태 위젯(최근 실패 10건)

2. **이벤트 모니터 (`/events`)**
   - 필터: room, event_type, vendor, 기간, confidence
   - 정렬: 최신순(기본)
   - 이벤트 상세 패널: 원문 메시지, 파싱값, 알림 전송 결과

3. **방 상태 (`/rooms`)**
   - 방별 수집/이벤트 추이(간단 sparkline 또는 수치)
   - 비정상 탐지: N분 이상 메시지 없음, 이벤트 급감/급증

4. **알림 상태 (`/alerts`)**
   - 텔레그램 전송 로그(성공/실패/오류코드/재시도여부)
   - 실패건 재전송(추후, 이번 MVP는 버튼 disabled 가능)

5. **시스템 상태 (`/system`)**
   - API health, DB 상태, 수집기 watchdog 상태(연동 가능 시)

---

## 4) 프론트엔드 연동 설계

### 권장 스택(빠른 MVP)
- React + Vite (또는 Next.js)
- UI: Tailwind + shadcn/ui(선택)
- 데이터패칭: TanStack Query
- 차트: Recharts(필요 최소)

### 기본 데이터 갱신 정책
- KPI/방상태/이벤트: 10~30초 폴링
- 알림 상태: 30초 폴링
- 필터 검색: 서버사이드 pagination + query params

### 공통 API 클라이언트
- `GET /api/v1/...` prefix 통일
- 에러 포맷 표준화: `{ code, message, details? }`
- 시간대 통일: 서버 UTC 저장 + UI는 KST 렌더

---

## 5) 필요한 API 엔드포인트 (To-Be)

> 기존 `/health`, `/ingest` 유지 + 운영 조회 API 추가

### 5.1 대시보드 집계

#### `GET /api/v1/dashboard/summary?from=&to=`
- 목적: KPI 카드 집계
- 응답 예시
```json
{
  "messageCount": 1240,
  "eventCount": 312,
  "soldOutCount": 41,
  "restockCount": 27,
  "priceUpCount": 55,
  "priceDownCount": 63,
  "alertFailCount": 3,
  "lastIngestAt": "2026-02-11T14:35:10Z"
}
```

### 5.2 방 상태

#### `GET /api/v1/rooms/status?limit=50`
- 목적: room별 상태 테이블
- 응답 필드
  - roomName
  - lastMessageAt
  - lastEventAt
  - messageCount1h
  - eventCount1h
  - health (`OK` | `STALE` | `DOWN`)

#### `GET /api/v1/rooms/{roomName}/timeline?window=24h&bucket=1h`
- 목적: 특정 room 메시지/이벤트 추이

### 5.3 이벤트 조회

#### `GET /api/v1/events`
- 쿼리
  - `roomName`, `eventType`, `vendor`, `minConfidence`, `from`, `to`, `cursor`, `limit`
- 응답
  - 이벤트 목록 + cursor pagination

#### `GET /api/v1/events/{id}`
- 목적: 이벤트 상세(원문 message 포함)

### 5.4 알림 상태

> 신규 테이블 `alert_logs` 필요 (아래 데이터모델 참고)

#### `GET /api/v1/alerts/logs?status=FAILED&limit=100`
- 목적: 텔레그램 전송 이력/실패 조회

#### `GET /api/v1/alerts/summary?from=&to=`
- 목적: 성공률, 실패율, 평균 지연

### 5.5 시스템 상태

#### `GET /api/v1/system/status`
- 목적: API/DB/collector/watchdog 상태 요약

---

## 6) 데이터 모델 제안

## 6.1 기존 테이블 활용
- `messages`, `events`, `products` 유지
- 운영 조회를 위해 인덱스 보강
  - `messages(created_at)`
  - `events(room_name, created_at)`
  - `events(vendor, created_at)`

## 6.2 신규 테이블

### `alert_logs`
```sql
CREATE TABLE IF NOT EXISTS alert_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id INTEGER,
  channel TEXT NOT NULL,              -- telegram
  destination TEXT,
  status TEXT NOT NULL,               -- SENT | FAILED
  error_code TEXT,
  error_message TEXT,
  latency_ms INTEGER,
  sent_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(event_id) REFERENCES events(id)
);
CREATE INDEX IF NOT EXISTS idx_alert_logs_status_time ON alert_logs(status, created_at);
```

### (선택) `room_health_snapshots`
- 배치성 집계 캐시가 필요할 때만 추가
- MVP에서는 쿼리 집계로 시작 가능

---

## 7) API/백엔드 구현 메모

1. `src/api.py`에 Router 분리
   - `routers/dashboard.py`, `routers/events.py`, `routers/rooms.py`, `routers/alerts.py`, `routers/system.py`
2. DB 접근 레이어 분리
   - `src/repositories/*.py`
3. notifier 개선
   - `send_telegram` 결과(success/fail, latency)를 `alert_logs`에 기록
4. 조회 성능
   - 이벤트 목록은 cursor 기반 pagination
   - 기간 집계는 기본 24h/7d 제한

---

## 8) 1~2주 우선순위 백로그

### Week 1 (핵심 기능 완성)

**P0**
1. `alert_logs` 스키마 추가 + notifier 로깅 연동
2. `GET /api/v1/dashboard/summary`
3. `GET /api/v1/rooms/status`
4. `GET /api/v1/events` + 필터/페이지네이션
5. 프론트 `/dashboard` 기본 화면(카드 + 방테이블 + 최근이벤트)

**P1**
6. 프론트 `/events` 필터 UI + 상세 패널
7. `GET /api/v1/alerts/logs`, `/api/v1/alerts/summary`

### Week 2 (운영성/안정화)

**P0**
8. `/rooms` 화면 + stale/down 판정 로직
9. `/system` 상태 API + 간단 UI
10. API 응답 스키마 표준화 및 에러 핸들링
11. 인덱스 튜닝 + 느린 쿼리 점검

**P1**
12. 방/이벤트 자동 새로고침 UX 개선(폴링 제어)
13. confidence 낮은 이벤트 하이라이트
14. 기본 E2E 시나리오(대시보드 로딩, 필터 동작)

---

## 9) 리스크 및 대응

1. **파서 오탐/누락 리스크**
   - 대응: 이벤트 상세에서 원문 메시지 노출, confidence 기반 필터

2. **알림 실패 가시성 부재**
   - 대응: `alert_logs` 필수 도입, 실패율 KPI/실패 목록 제공

3. **SQLite 집계 성능 한계**
   - 대응: 기간 제한, 인덱스 강화, 필요시 snapshot/cache 테이블 도입

4. **수집기 중단 탐지 미흡**
   - 대응: room stale/down 판정 + system status 화면에 watchdog 상태 표시

5. **시간대/정렬 혼선**
   - 대응: 저장 UTC, 표시 KST 통일 정책 문서화

---

## 10) 수용 기준(Definition of Done)

- 운영자가 `/dashboard`에서 30초 이내 최신 상태를 확인 가능
- room별 stale/down 상태가 명확히 표시됨
- 이벤트 필터링(event_type/room/vendor/기간)이 동작
- 알림 실패 건이 목록으로 확인 가능
- 핵심 API 응답시간(최근 24h 기준) p95 < 500ms 목표

---

## 11) 후속 확장(차기)

- WebSocket/SSE 실시간 푸시
- 룰 엔진(키워드/예외 규칙) UI 편집
- 다중 채널 알림(Slack/Discord)
- PostgreSQL 전환 + 시계열 분석
