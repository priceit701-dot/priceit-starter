# Feedback Loop: Plan → Execute → Review → Patch

## Purpose
회의/실행 결과를 단순 기록으로 끝내지 않고, 반복 가능한 개선 루프로 운영한다.

## Loop Definition

## 1) Plan
- Inputs:
  - Domain goals, KPI baseline, known constraints
  - Previous review notes
- Required outputs:
  - Clear objective (1 sprint/1 week 단위)
  - Task list with owner/due date
  - Success criteria (정량/정성)
- Record path:
  - `docs/agents/meetings/*.md`

## 2) Execute
- Inputs:
  - Approved plan + handoff package
- Required outputs:
  - Execution logs per domain
  - Intermediate artifacts (draft/spec/checklist)
- Record path:
  - `logs/agents/{marketing|content|pd}/*.md`

## 3) Review
- Inputs:
  - Execution logs + KPI delta + incident notes
- Required outputs:
  - What worked / failed / uncertain
  - Decision: continue, adjust, stop
- Record path:
  - meeting doc review section + domain summary log

## 4) Patch
- Inputs:
  - Review decisions
- Required outputs:
  - Updated process rule, revised task priority, new safeguards
  - Next Plan seed items
- Record path:
  - `docs/agents/org.md` (rule changes)
  - next meeting doc agenda seed

---

## Operational Cadence (Recommended)
- Weekly:
  - Full loop sync (Plan+Review+Patch)
- Daily:
  - Execute status update (short log)

## Exit Criteria per Cycle
- Must satisfy all:
  - Owner assigned for each action item
  - Due date assigned
  - At least one measurable success criterion
  - Logs written to `logs/agents/`

If any condition is missing, cycle remains OPEN.
