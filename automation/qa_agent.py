#!/usr/bin/env python3
"""
QA agent for priceit-starter.

Scope:
- API health/endpoints response checks
- Parser regression checks
- Notifier idempotency/retry behavior checks
- Dashboard static/link/core-data checks
- Controller evidence PASS/FAIL policy checks

Outputs per run (logs/qa/<timestamp>/):
- raw.log
- summary.json
- report.md
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
LOG_ROOT = ROOT / "logs" / "qa"


@dataclass
class CheckResult:
    name: str
    status: str  # PASS / FAIL
    code: str
    detail: str
    evidence: Dict[str, Any]
    repro_command: str


def utc_ts() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def append_raw(raw_lines: List[str], line: str):
    raw_lines.append(f"[{now_iso()}] {line}")


def run_api_checks(raw_lines: List[str]) -> CheckResult:
    import sys

    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    from src.api import app

    client = TestClient(app)

    endpoints = [
        ("GET", "/health"),
        ("GET", "/stats/summary"),
        ("GET", "/stats/quality?limit_hours=24"),
        ("GET", "/events/recent?limit=5"),
        ("GET", "/dashboard"),
    ]

    statuses = {}
    for method, path in endpoints:
        r = client.request(method, path)
        statuses[path] = r.status_code
        append_raw(raw_lines, f"API {method} {path} -> {r.status_code}")

    required_ok = all(code == 200 for code in statuses.values())

    summary = client.get("/stats/summary").json()
    quality = client.get("/stats/quality?limit_hours=24").json()
    recent = client.get("/events/recent?limit=5").json()

    keys_ok = all(
        [
            "messages" in summary,
            "events" in summary,
            "event_quality" in quality,
            "skip_reasons" in quality,
            "items" in recent,
        ]
    )

    if required_ok and keys_ok:
        return CheckResult(
            name="api_health_endpoints",
            status="PASS",
            code="API_OK",
            detail="핵심 API 및 dashboard 엔드포인트 응답/키 확인",
            evidence={"status_codes": statuses, "summary": summary, "quality_keys": list(quality.keys()), "recent_count": len(recent.get("items", []))},
            repro_command="python3 automation/qa_agent.py --only api",
        )

    return CheckResult(
        name="api_health_endpoints",
        status="FAIL",
        code="API_RESPONSE_INVALID",
        detail="API status code 또는 응답 키 불일치",
        evidence={"status_codes": statuses, "summary_keys": list(summary.keys()), "quality_keys": list(quality.keys()), "recent_keys": list(recent.keys())},
        repro_command="python3 automation/qa_agent.py --only api",
    )


def run_parser_checks(raw_lines: List[str]) -> CheckResult:
    import sys

    sys.path.insert(0, str(ROOT))
    from src.parser import parse_message

    cases = [
        ("#가격인상", "PRICE_UP"),
        ("팜허브 입고 지연으로 순차출고 예정입니다", "DELAY_NOTICE"),
        ("📌신규상품 'A급 남해 보물초 시금치' 11,700원", "NEW_ITEM"),
        ("[품절 안내] 샤인머스켓 특품", "SOLD_OUT"),
    ]

    failed = []
    for text, expected in cases:
        parsed = parse_message(text)
        actual = parsed.event_type if parsed else None
        append_raw(raw_lines, f"PARSER input={text!r} expected={expected} actual={actual}")
        if actual != expected:
            failed.append({"text": text, "expected": expected, "actual": actual})

    if not failed:
        return CheckResult(
            name="parser_regression",
            status="PASS",
            code="PARSER_OK",
            detail="핵심 파서 회귀 케이스 통과",
            evidence={"cases": len(cases), "failed": 0},
            repro_command="python3 automation/qa_agent.py --only parser",
        )

    return CheckResult(
        name="parser_regression",
        status="FAIL",
        code="PARSER_REGRESSION",
        detail="파서 회귀 케이스 실패",
        evidence={"cases": len(cases), "failed": len(failed), "items": failed},
        repro_command="python3 automation/qa_agent.py --only parser",
    )


def run_notifier_checks(raw_lines: List[str]) -> CheckResult:
    import sys

    sys.path.insert(0, str(ROOT))
    import src.notifier as notifier

    with tempfile.TemporaryDirectory(prefix="qa_notify_state_") as td:
        state_path = Path(td) / "notify_state.json"
        notifier.STATE_PATH = state_path

        class FakeResp:
            def __init__(self, status_code: int):
                self.status_code = status_code

        class FakeClient:
            def __init__(self, timeout: float = 10.0):
                self.calls = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def post(self, url: str, json: Dict[str, Any]):
                self.calls += 1
                if self.calls <= 2:
                    raise RuntimeError("simulated_network_error")
                return FakeResp(200)

        old_client = notifier.httpx.Client
        old_sleep = notifier.time.sleep
        old_token = notifier.TELEGRAM_BOT_TOKEN
        old_chat = notifier.TELEGRAM_CHAT_ID

        notifier.httpx.Client = FakeClient
        notifier.time.sleep = lambda _: None
        notifier.TELEGRAM_BOT_TOKEN = "qa-token"
        notifier.TELEGRAM_CHAT_ID = "qa-chat"

        try:
            first = notifier.send_telegram("qa notifier check", idempotency_key="qa-key-1")
            second = notifier.send_telegram("qa notifier check", idempotency_key="qa-key-1")
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

            history = state.get("history", [])
            sent_cnt = sum(1 for h in history if h.get("event") == "sent")
            dedup_cnt = sum(1 for h in history if h.get("event") == "dedup_skip")
            append_raw(raw_lines, f"NOTIFIER first={first} second={second} sent={sent_cnt} dedup={dedup_cnt}")

            ok = bool(first) and bool(second) and sent_cnt == 1 and dedup_cnt >= 1
            if ok:
                return CheckResult(
                    name="notifier_idempotency_retry",
                    status="PASS",
                    code="NOTIFIER_OK",
                    detail="재시도 후 성공 + 중복키 재전송 skip 확인",
                    evidence={"first": first, "second": second, "sent_events": sent_cnt, "dedup_events": dedup_cnt, "history_tail": history[-5:]},
                    repro_command="python3 automation/qa_agent.py --only notifier",
                )

            return CheckResult(
                name="notifier_idempotency_retry",
                status="FAIL",
                code="NOTIFIER_BEHAVIOR_INVALID",
                detail="알림 재시도/중복방지 동작이 기대와 다름",
                evidence={"first": first, "second": second, "sent_events": sent_cnt, "dedup_events": dedup_cnt, "history": history},
                repro_command="python3 automation/qa_agent.py --only notifier",
            )
        finally:
            notifier.httpx.Client = old_client
            notifier.time.sleep = old_sleep
            notifier.TELEGRAM_BOT_TOKEN = old_token
            notifier.TELEGRAM_CHAT_ID = old_chat


def run_dashboard_checks(raw_lines: List[str]) -> CheckResult:
    import sys

    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    from src.api import app

    dash_path = ROOT / "web" / "dashboard.html"
    html_file_exists = dash_path.exists()
    html_text = dash_path.read_text(encoding="utf-8") if html_file_exists else ""

    required_links = ["/stats/summary", "/stats/quality", "/events/recent"]
    missing_links = [u for u in required_links if u not in html_text]

    client = TestClient(app)
    dashboard_resp = client.get("/dashboard")
    summary = client.get("/stats/summary").json()

    core_data_ok = isinstance(summary.get("messages"), int) and isinstance(summary.get("events"), int)
    endpoint_ok = dashboard_resp.status_code == 200 and "<" in dashboard_resp.text

    append_raw(raw_lines, f"DASHBOARD file_exists={html_file_exists} endpoint={dashboard_resp.status_code} missing_links={missing_links}")

    ok = html_file_exists and not missing_links and endpoint_ok and core_data_ok
    if ok:
        return CheckResult(
            name="dashboard_static_links_coredata",
            status="PASS",
            code="DASHBOARD_OK",
            detail="대시보드 정적 파일/링크/핵심 데이터 로딩 확인",
            evidence={"dashboard_status": dashboard_resp.status_code, "missing_links": missing_links, "messages": summary.get("messages"), "events": summary.get("events")},
            repro_command="python3 automation/qa_agent.py --only dashboard",
        )

    return CheckResult(
        name="dashboard_static_links_coredata",
        status="FAIL",
        code="DASHBOARD_CHECK_FAILED",
        detail="대시보드 파일/링크/핵심 데이터 검증 실패",
        evidence={"file_exists": html_file_exists, "dashboard_status": dashboard_resp.status_code, "missing_links": missing_links, "summary": summary},
        repro_command="python3 automation/qa_agent.py --only dashboard",
    )


def run_controller_checks(raw_lines: List[str]) -> CheckResult:
    import sys

    sys.path.insert(0, str(ROOT))
    from automation.controller import validator, FAIL_CODES

    policy = {"require_next_step_token": "NEXT_STEP_OK", "require_evidence_token": "EVIDENCE:"}

    pass_exec = {
        "ok": True,
        "stdout": 'NEXT_STEP_OK\nEVIDENCE:{"step":"qa","status":"PASS","checks":5,"failed":0,"proof_ts":"2026-02-12T00:00:00"}',
    }
    fail_exec = {
        "ok": True,
        "stdout": 'NEXT_STEP_OK\nEVIDENCE:{"step":"qa","status":"PASS","checks":5,"failed":2,"proof_ts":"2026-02-12T00:00:00"}',
    }

    v_pass = validator(policy, pass_exec)
    v_fail = validator(policy, fail_exec)
    append_raw(raw_lines, f"CONTROLLER v_pass={v_pass} v_fail={v_fail}")

    ok = v_pass.get("pass") is True and v_pass.get("code") == "PASS" and v_fail.get("pass") is False and v_fail.get("code") == FAIL_CODES["EVIDENCE_FAIL_COUNT_MISMATCH"]
    if ok:
        return CheckResult(
            name="controller_evidence_contract",
            status="PASS",
            code="CONTROLLER_RULE_OK",
            detail="PASS/FAIL evidence 규약 검증 로직 확인",
            evidence={"pass_case": v_pass, "fail_case": v_fail},
            repro_command="python3 automation/qa_agent.py --only controller",
        )

    return CheckResult(
        name="controller_evidence_contract",
        status="FAIL",
        code="CONTROLLER_RULE_INVALID",
        detail="controller evidence 규약 검증 결과 불일치",
        evidence={"pass_case": v_pass, "fail_case": v_fail},
        repro_command="python3 automation/qa_agent.py --only controller",
    )


def render_md(summary: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"# QA Report - {summary['run_id']}")
    lines.append("")
    lines.append(f"- started_at: {summary['started_at']}")
    lines.append(f"- finished_at: {summary['finished_at']}")
    lines.append(f"- overall_status: **{summary['overall_status']}**")
    lines.append(f"- checks_total: {summary['counts']['total']} (pass={summary['counts']['pass']}, fail={summary['counts']['fail']})")
    lines.append("")
    lines.append("## Check Results")
    lines.append("")
    for c in summary["checks"]:
        icon = "✅" if c["status"] == "PASS" else "❌"
        lines.append(f"### {icon} {c['name']} ({c['status']})")
        lines.append(f"- code: `{c['code']}`")
        lines.append(f"- detail: {c['detail']}")
        lines.append(f"- repro: `{c['repro_command']}`")
        if c["status"] == "FAIL":
            lines.append(f"- failure_code: `{c['code']}`")
        lines.append("")
    lines.append("## Notes")
    lines.append("- 본 결과는 QA agent 단일 실행 기준입니다.")
    lines.append("- 상세 raw evidence는 같은 디렉터리의 raw.log/summary.json 참조.")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["api", "parser", "notifier", "dashboard", "controller"], default=None)
    args = parser.parse_args()

    run_id = utc_ts()
    run_dir = LOG_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    raw_lines: List[str] = []
    started_at = now_iso()
    append_raw(raw_lines, f"QA_RUN_START run_id={run_id} only={args.only}")

    checks: List[CheckResult] = []

    plan = [
        ("api", run_api_checks),
        ("parser", run_parser_checks),
        ("notifier", run_notifier_checks),
        ("dashboard", run_dashboard_checks),
        ("controller", run_controller_checks),
    ]

    for key, fn in plan:
        if args.only and args.only != key:
            continue
        try:
            result = fn(raw_lines)
        except Exception as e:
            result = CheckResult(
                name=f"{key}_check_exception",
                status="FAIL",
                code="CHECK_EXCEPTION",
                detail=f"예외 발생: {e}",
                evidence={"exception": str(e)},
                repro_command=f"python3 automation/qa_agent.py --only {key}",
            )
            append_raw(raw_lines, f"CHECK_EXCEPTION key={key} err={e}")
        checks.append(result)

    finished_at = now_iso()
    pass_count = sum(1 for c in checks if c.status == "PASS")
    fail_count = sum(1 for c in checks if c.status == "FAIL")

    overall_status = "PASS" if fail_count == 0 else "FAIL"
    summary = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "overall_status": overall_status,
        "counts": {"total": len(checks), "pass": pass_count, "fail": fail_count},
        "checks": [asdict(c) for c in checks],
        "failure_codes": [c.code for c in checks if c.status == "FAIL"],
        "repro_commands": [c.repro_command for c in checks if c.status == "FAIL"],
    }

    raw_path = run_dir / "raw.log"
    summary_path = run_dir / "summary.json"
    report_path = run_dir / "report.md"

    raw_lines.append(f"[{now_iso()}] QA_RUN_END status={overall_status} pass={pass_count} fail={fail_count}")
    raw_path.write_text("\n".join(raw_lines) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(render_md(summary), encoding="utf-8")

    print(json.dumps({"run_id": run_id, "status": overall_status, "pass": pass_count, "fail": fail_count, "summary": str(summary_path)}, ensure_ascii=False))

    raise SystemExit(0 if overall_status == "PASS" else 1)


if __name__ == "__main__":
    main()
