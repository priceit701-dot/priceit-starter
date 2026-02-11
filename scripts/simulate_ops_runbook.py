import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

parser = argparse.ArgumentParser()
parser.add_argument("--mode", default="normal", choices=["normal", "downgrade"])
args = parser.parse_args()

checks = [
    ("v1_integrity", ["python3", "scripts/verify_v1.py"]),
    ("v2_parser", ["python3", "-m", "unittest", "tests/test_parser_rules.py"]),
    ("v3_api", ["python3", "scripts/verify_v3.py"]),
    ("v4_controller", ["python3", "scripts/verify_v4_controller.py"]),
]

if args.mode == "downgrade":
    checks = checks[:2]

results = []
for name, cmd in checks:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    results.append({
        "check": name,
        "rc": p.returncode,
        "stdout_head": "\n".join((p.stdout or "").splitlines()[:4]),
        "stderr_head": "\n".join((p.stderr or "").splitlines()[:4]),
    })

failed = [r for r in results if r["rc"] != 0]
status = "PASS" if not failed else "FAIL"

print("RUNBOOK_SIMULATION status=", status, "mode=", args.mode)
print("RUNBOOK_SIMULATION checks=", len(results), "failed=", len(failed))
print("NEXT_STEP_OK" if status == "PASS" else "NEXT_STEP_BLOCKED")
print(
    "EVIDENCE:" + json.dumps(
        {
            "step": "runbook_simulation",
            "status": status,
            "checks": len(results),
            "failed": len(failed),
            "mode": args.mode,
            "proof_ts": datetime.now().isoformat(timespec="seconds"),
        },
        ensure_ascii=False,
    )
)

for r in results:
    print(f"- {r['check']} rc={r['rc']}")
