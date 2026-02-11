# MVP v8 - QA Foundation

작성일: 2026-02-12 KST

## 1) 무엇을 만들었는지

### A. 버전 체계 확장 (v8~v50)
- `docs/mvp/roadmap-v8-v50.md`
  - v1~v7 결과와 연결된 v8~v50 장기 운영 프레임 정의
  - 단계별(품질기반/관측성/확장성/자동운영/제품화) 목표와 exit criteria 정리
- `docs/mvp/version_status.json`
  - v1~v50 버전 상태 단일 소스
  - 상태 enum: `PLANNED / IN_PROGRESS / DONE / BLOCKED`

### B. QA 전용 에이전트/루프
- `automation/qa_agent.py` 신규 작성
- 체크 항목 구현:
  1. API 헬스/엔드포인트 응답 (`/health`, `/stats/summary`, `/stats/quality`, `/events/recent`, `/dashboard`)
  2. 파서 회귀 테스트 (핵심 4케이스)
  3. 알림 idempotency/재시도 동작 (mock client로 retry 후 성공 + dedup skip 검증)
  4. 대시보드 정적/링크/핵심 데이터 로딩 확인
  5. controller PASS/FAIL evidence 규약 검증 (`EVIDENCE_FAIL_COUNT_MISMATCH` 케이스 포함)
- 산출물 표준화:
  - `logs/qa/<run_id>/raw.log`
  - `logs/qa/<run_id>/summary.json`
  - `logs/qa/<run_id>/report.md`

---

## 2) 어떻게 실행하는지

### 전체 QA 1회 실행
```bash
cd priceit-starter
python3 automation/qa_agent.py
```

### 항목별 재현
```bash
python3 automation/qa_agent.py --only api
python3 automation/qa_agent.py --only parser
python3 automation/qa_agent.py --only notifier
python3 automation/qa_agent.py --only dashboard
python3 automation/qa_agent.py --only controller
```

---

## 3) 실제 실행 결과 (근거 기반)

실행 커맨드:
```bash
python3 automation/qa_agent.py
```

실행 출력:
```json
{"run_id": "20260211T151508Z", "status": "PASS", "pass": 5, "fail": 0, "summary": ".../logs/qa/20260211T151508Z/summary.json"}
```

실행 산출물:
- `logs/qa/20260211T151508Z/raw.log`
- `logs/qa/20260211T151508Z/summary.json`
- `logs/qa/20260211T151508Z/report.md`

핵심 숫자:
- total checks: 5
- pass: 5
- fail: 0
- failure codes: 없음

세부 증거 예시:
- API: `/health`, `/stats/summary`, `/stats/quality`, `/events/recent`, `/dashboard` 모두 200
- parser regression: 4/4 통과
- notifier: 재시도 후 `attempt=3` 성공 + 동일 key 재전송 `dedup_skip=1`
- controller: PASS 케이스 수용 + 불일치 케이스 `EVIDENCE_FAIL_COUNT_MISMATCH` 검출 확인

---

## 4) 남은 리스크
1. 현재 notifier QA는 mock 기반이므로 실제 Telegram API rate-limit/네트워크 지연은 별도 실환경 점검 필요.
2. QA 에이전트는 단일 실행 구조이며 주기 스케줄링(cron/CI)은 아직 미구성.
3. dashboard 검증은 정적 링크/핵심 API 중심이며 브라우저 렌더링 시각회귀는 포함하지 않음.
4. QA 결과와 배포 게이트 자동 연동(실패 시 배포 차단)은 v9 이후 과제.

---

## 5) v9~v50 운영 계획
- 상세 로드맵: `docs/mvp/roadmap-v8-v50.md`
- 상태 추적: `docs/mvp/version_status.json`
- 즉시 다음(v9) 우선순위:
  1. QA 스케줄러(주기 실행 + 실패 알림)
  2. 실기기 수집기 burn-in 검증 자동화
  3. QA 실패 코드별 runbook 링크 자동 첨부
