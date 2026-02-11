# priceit-starter 운영/자동화 기획: Subagent Loop

작성시각: 2026-02-11 23:45 (KST)
기준 코드: `automation/controller.py`, `automation/md_logger.py`

---

## 1) 목표와 설계 원칙

### 목표
- 무인 자동화 루프(Planner → Executor → Validator → MD Logger)를 **야간에도 안전하게** 운영한다.
- 실패를 코드화하여 원인-대응을 빠르게 연결한다.
- 모든 실행은 **증거(Evidence) 기반**으로 남기고, 아침에 즉시 재시작 가능한 런북을 표준화한다.

### 설계 원칙
- **Fail-safe 우선**: 애매하면 중단/대기, 무리한 재시도 금지
- **증거 우선**: 성공/실패 모두 로그 + 요약 마크다운 남김
- **상태 최소화**: 정책(`policy.json`) + 상태(`state.json`) + 이벤트(`loop_log.jsonl`) 중심
- **운영 가능성**: 코드 변경 없이도 정책값으로 야간 모드/중단 임계치 조정 가능

---

## 2) 현재 구현 요약 (기준점)

## `automation/controller.py`
- 루프: `planner()` → `executor()` → `validator()` → `patcher()`
- 실패코드(현재):
  - `NO_NEXT_STEP`
  - `NO_EVIDENCE`
  - `ROUTE_DEVIATION`
  - `EXECUTOR_NOT_CONFIGURED`
  - `EXECUTOR_NONZERO`
- 상태파일: `automation/state.json`
  - `enabled`, `retry_count`, `last_fail_code`
- 로그: `automation/loop_log.jsonl`
  - `status`, `plan`, `validator`, `executor(rc/stdout/stderr 일부)`

## `automation/md_logger.py`
- 정책 기반 단발성 기록기
  - mode: `idle` 또는 `memory-daily`
  - heading/lines를 md 파일에 append
- 상태파일: `automation/md_logger_state.json`
  - `last_run`, `last_heading`

### 현재 한계
- Planner 결과(`runbook exists`)가 Validator 판정에 직접 반영되지 않음
- 실패코드는 있으나 **치명도/대응수준(자동재시도 vs 즉시중단)** 매핑이 없음
- `retry_count`가 누적만 되고 리셋/윈도우 기반 임계치 관리가 없음
- 야간 무인운영 조건(시간대, 최대 실패 횟수, 자동중단 규칙) 미정의
- md_logger가 controller 로그를 구조적으로 소비하지 않음(수동 lines 입력 중심)

---

## 3) 목표 루프 설계 (Planner / Executor / Validator / MD Logger)

## 3.1 Planner
입력:
- `policy.json` (cycle, executor command, token requirement, 시간대 정책)
- runbook 존재 여부
- 이전 상태(`state.json`)와 최근 실패 이력

출력(예시):
```json
{
  "ok": true,
  "runbook": "docs/kakao-openchat-export-runbook.md",
  "night_mode": true,
  "can_execute": true,
  "stop_reason": null,
  "ts": "..."
}
```

핵심 규칙:
- `runbook` 없으면 즉시 `PLANNER_RUNBOOK_MISSING`
- 야간모드에서 `retry_count`/연속실패/치명코드가 임계치 초과면 `can_execute=false`
- `enabled=false` 또는 수동잠금(`manual_lock`)이면 실행 금지

## 3.2 Executor
입력:
- Planner의 `can_execute=true`인 경우에만 수행
- `executor_command`, `timeout_sec`, `env`

출력(예시):
```json
{
  "ok": false,
  "rc": 124,
  "stdout": "...",
  "stderr": "timeout",
  "duration_ms": 180032,
  "evidence": ["logs/...", "data/..."],
  "code": "EXECUTOR_TIMEOUT"
}
```

핵심 규칙:
- timeout 필수화 (기본 180초)
- stdout/stderr 절단 저장 + 원문은 파일 경로로 evidence화
- 종료코드 + 표준출력 토큰 + 산출물 존재를 함께 기록

## 3.3 Validator
입력:
- Planner 결과 + Executor 결과
- 정책상 필수 토큰(`NEXT_STEP_OK`, `EVIDENCE:`)
- 라우트 변경 금지 토큰(`ROUTE_CHANGED`)

출력:
- `pass/fail`, `fail_code`, `severity(S1/S2/S3)`, `action(RETRY/STOP/MANUAL)`

판정 우선순위:
1. Planner 실패(구성/사전조건) → 즉시 fail
2. Executor infra 실패(timeout/nonzero/not configured)
3. 결과 내용 실패(no next step/no evidence/route deviation)

## 3.4 MD Logger
역할:
- `loop_log.jsonl`의 최근 이벤트를 요약해 `docs/WORKLOG.md` 또는 `memory/YYYY-MM-DD.md`에 기록
- 실패 발생 시 **증거 링크 + 대응결정 + 재시작 조건**을 한 블록으로 남김

권장 기록 주기:
- 성공: N회(예: 10회) 누적 시 1회 요약
- 실패: 즉시 1회 기록
- 상태 전이(`enabled true→false`, `manual_lock on`) 시 즉시 기록

---

## 4) 실패코드 체계 (확장안)

## 4.1 코드 네이밍 규칙
- `PLANNER_*`, `EXECUTOR_*`, `VALIDATOR_*`, `SYSTEM_*`
- 각 코드에 `severity`, `auto_action`, `human_action` 정의

## 4.2 코드 표

| 코드 | 단계 | 의미 | 심각도 | 자동조치 | 수동개입 |
|---|---|---|---|---|---|
| `PLANNER_RUNBOOK_MISSING` | Planner | runbook 파일 없음 | S2 | 즉시 STOP | runbook 경로 수정 후 재개 |
| `PLANNER_DISABLED` | Planner | state enabled=false/manual_lock | S3 | 대기 | 운영자 unlock |
| `EXECUTOR_NOT_CONFIGURED` | Executor | command 미설정 | S2 | STOP | policy 보정 |
| `EXECUTOR_TIMEOUT` | Executor | 제한시간 초과 | S1 | 1회 재시도 후 STOP | 장기작업 분리/timeout 재설정 |
| `EXECUTOR_NONZERO` | Executor | 비정상 종료 | S1 | 최대 N회 재시도 | stderr 확인 후 조치 |
| `VALIDATOR_NO_NEXT_STEP` | Validator | NEXT_STEP_OK 없음 | S2 | RETRY 1회 | 프롬프트/출력포맷 교정 |
| `VALIDATOR_NO_EVIDENCE` | Validator | EVIDENCE 없음 | S2 | RETRY 1회 | evidence 생성 강제 |
| `VALIDATOR_ROUTE_DEVIATION` | Validator | ROUTE_CHANGED 검출 | S1 | 즉시 STOP | 라우트 변경 승인 절차 |
| `SYSTEM_LOG_WRITE_FAIL` | System | 로그파일 쓰기 실패 | S1 | 즉시 STOP | 디스크/권한 점검 |

권장 임계치:
- S1: 즉시 중단(또는 1회 제한 재시도 후 중단)
- S2: 짧은 재시도(최대 2회), 초과 시 중단
- S3: 정보성/운영상태, 무인운영 영향 없음

---

## 5) 증거기반 보고 포맷 (표준)

실패/성공 공통 JSON 이벤트 스키마(권장):
```json
{
  "ts": "2026-02-11T23:45:00+09:00",
  "run_id": "20260211-234500-0012",
  "status": "success|fail|paused",
  "phase": "planner|executor|validator|logger",
  "fail_code": "EXECUTOR_TIMEOUT",
  "severity": "S1",
  "action": "STOP",
  "policy_snapshot": {
    "cycle_sec": 5,
    "timeout_sec": 180,
    "night_mode": true
  },
  "evidence": [
    "automation/loop_log.jsonl#L2012",
    "logs/executor/20260211-234500.stdout.log",
    "logs/executor/20260211-234500.stderr.log"
  ],
  "next_step": "timeout 180->300 검토 후 수동 재개"
}
```

MD 블록 템플릿:
```md
## [FAIL][S1] EXECUTOR_TIMEOUT (2026-02-11T23:45:00+09:00)
- Run ID: 20260211-234500-0012
- 요약: executor 180초 초과로 중단
- 증거:
  - automation/loop_log.jsonl#L2012
  - logs/executor/20260211-234500.stderr.log
- 자동조치: STOP (야간 무인운영 보호)
- 수동조치: timeout 재설정/작업 분리 후 재가동
- NEXT_STEP_OK: 내일 09:00 점검 후 재개
```

---

## 6) 야간 무인운영 조건 / 중단조건

야간 윈도우(권장):
- `23:00~08:00` KST를 `night_mode=true`

무인운영 시작 조건:
1. `enabled=true`
2. `manual_lock=false`
3. 최근 3회 내 S1 실패 없음
4. runbook 경로 유효
5. 디스크 여유(로그쓰기 가능)

즉시 중단 조건:
- S1 코드 1회 발생
- 동일 S2 코드 2회 연속 발생
- 전체 실패율이 최근 20회 중 30% 초과
- evidence 기록 실패(`SYSTEM_LOG_WRITE_FAIL`)
- ROUTE_DEVIATION 발생

중단 시 자동 상태전이:
- `state.enabled=false`
- `state.manual_lock=true`
- `state.stop_reason=<fail_code>`
- md_logger로 장애 블록 즉시 기록

---

## 7) 수동개입 절차 (On-call Lite)

1. 상태 확인
- `automation/state.json` 확인 (`enabled/manual_lock/last_fail_code/retry_count`)
- `automation/loop_log.jsonl` 최신 20줄 확인

2. 증거 확인
- stderr/stdout 로그, runbook 경로, 산출물 존재 여부 확인

3. 분류
- 설정오류(경로/command/token)
- 실행환경오류(timeout, 권한, 네트워크)
- 정책오류(검증규칙 과도)

4. 조치
- policy 수정(명령, timeout, token)
- 필요 시 수동 1회 실행으로 재현 확인

5. 재가동
- `manual_lock=false`, `enabled=true`, `retry_count=0`로 초기화 후 루프 재개
- 첫 3사이클은 관찰 모드로 로그 확인

---

## 8) 내일 재시작 런북 (09:00 기준)

체크리스트:
1. `git status`로 야간 변경/산출물 확인
2. `automation/state.json` 확인
   - 중단 상태면 `stop_reason` 파악
3. 최근 실패 이벤트 3건 확인 (`loop_log.jsonl`)
4. 정책 점검 (`policy.json`, `md_logger_policy.json`)
5. 수동 dry-run 1회
   - `executor_command` 단독 실행
   - stdout에 `NEXT_STEP_OK`, `EVIDENCE:` 포함 여부 확인
6. 재가동
   - `enabled=true`, `manual_lock=false`, `retry_count=0`
7. 15분 모니터링 후 정상 시 무인모드 복귀

재시작 종료조건:
- 3연속 PASS + evidence 정상 기록 시 종료

---

## 9) 코드 개선안 (controller.py / md_logger.py 기반)

## 9.1 `automation/controller.py` 개선안
- [ ] Planner 실패를 Validator 이전에 강제 반영
- [ ] `timeout_sec` 지원 (`subprocess.run(..., timeout=...)`)
- [ ] 실패코드 확장(`PLANNER_*`, `EXECUTOR_TIMEOUT`, `SYSTEM_*`)
- [ ] 심각도/자동조치 매핑 테이블 추가
- [ ] `retry_count`를 코드별/윈도우별로 분리(`fail_streak`, `fail_by_code`)
- [ ] run_id 도입으로 이벤트 추적성 강화
- [ ] stdout/stderr 원문파일 로그 경로 evidence에 포함
- [ ] 중단 상태 전이(`manual_lock`, `stop_reason`) 내장

## 9.2 `automation/md_logger.py` 개선안
- [ ] 외부 입력 lines 대신 `loop_log.jsonl` tail 읽기 모드 추가
- [ ] 실패 이벤트 자동 템플릿 기록(코드/심각도/증거/다음조치)
- [ ] 성공 요약 배치 기록(노이즈 감소)
- [ ] heading 표준화(`[PASS]`, `[FAIL][S1]`)
- [ ] state에 `last_event_offset` 저장(중복 기록 방지)

---

## 10) 즉시 적용 작업 목록 (우선순위)

P0 (오늘 밤 필수)
1. 실패코드/심각도 매핑표를 `policy.json`에 추가
2. controller에 timeout + planner fail gate 추가
3. S1/S2 중단 규칙 구현(`enabled=false`, `manual_lock=true`)
4. loop_log 이벤트에 `run_id`, `fail_code`, `severity`, `action`, `evidence` 필드 추가

P1 (내일 오전)
5. md_logger에 `loop_log tail -> markdown` 모드 구현
6. md_logger_state에 offset 기반 증분처리 추가
7. WORKLOG 장애 템플릿 자동화

P2 (이번 주)
8. 야간/주간 별 정책 프로파일 분리 (`policy.night.json`, `policy.day.json`)
9. 간단한 운영 대시보드(JSON -> md/table 또는 웹)
10. route 변경 승인 플래그(`route_change_approved`) 도입

---

## 11) 완료 기준 (Definition of Done)

- 야간모드에서 S1 발생 시 1분 내 자동중단 + 증거기록
- 실패 이벤트 100%가 fail_code/severity/evidence/next_step 포함
- 아침 런북으로 15분 내 재가동 가능
- 운영자가 `state.json + WORKLOG`만 읽어도 상황 파악 가능

---

## 부록 A) 권장 state.json 필드

```json
{
  "enabled": true,
  "manual_lock": false,
  "retry_count": 0,
  "fail_streak": 0,
  "last_fail_code": null,
  "last_severity": null,
  "stop_reason": null,
  "last_run_id": null,
  "updated_at": "2026-02-11T23:45:00+09:00"
}
```

## 부록 B) 운영자 1줄 명령 예시

```bash
# 최근 이벤트 20개 확인
 tail -n 20 automation/loop_log.jsonl

# 상태 확인
 cat automation/state.json

# 오늘 워크로그 확인
 tail -n 80 docs/WORKLOG.md
```
