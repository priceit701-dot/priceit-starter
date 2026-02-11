# QA Report - 20260211T151508Z

- started_at: 2026-02-11T15:15:08Z
- finished_at: 2026-02-11T15:15:09Z
- overall_status: **PASS**
- checks_total: 5 (pass=5, fail=0)

## Check Results

### ✅ api_health_endpoints (PASS)
- code: `API_OK`
- detail: 핵심 API 및 dashboard 엔드포인트 응답/키 확인
- repro: `python3 automation/qa_agent.py --only api`

### ✅ parser_regression (PASS)
- code: `PARSER_OK`
- detail: 핵심 파서 회귀 케이스 통과
- repro: `python3 automation/qa_agent.py --only parser`

### ✅ notifier_idempotency_retry (PASS)
- code: `NOTIFIER_OK`
- detail: 재시도 후 성공 + 중복키 재전송 skip 확인
- repro: `python3 automation/qa_agent.py --only notifier`

### ✅ dashboard_static_links_coredata (PASS)
- code: `DASHBOARD_OK`
- detail: 대시보드 정적 파일/링크/핵심 데이터 로딩 확인
- repro: `python3 automation/qa_agent.py --only dashboard`

### ✅ controller_evidence_contract (PASS)
- code: `CONTROLLER_RULE_OK`
- detail: PASS/FAIL evidence 규약 검증 로직 확인
- repro: `python3 automation/qa_agent.py --only controller`

## Notes
- 본 결과는 QA agent 단일 실행 기준입니다.
- 상세 raw evidence는 같은 디렉터리의 raw.log/summary.json 참조.
