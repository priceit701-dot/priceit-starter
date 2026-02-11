#!/usr/bin/env python3
"""Bootstrap meeting and domain logs for agent operations.

Usage examples:
  python scripts/agent_meeting_bootstrap.py --topic kickoff
  python scripts/agent_meeting_bootstrap.py --topic weekly-sync --domains marketing,content
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

DOMAINS = ("marketing", "content", "pd")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create meeting doc and domain logs.")
    parser.add_argument("--topic", required=True, help="Meeting topic slug, e.g. kickoff")
    parser.add_argument(
        "--domains",
        default=",".join(DOMAINS),
        help="Comma-separated domains to log (marketing,content,pd)",
    )
    parser.add_argument(
        "--base-dir",
        default=".",
        help="Project base directory (default: current directory)",
    )
    return parser.parse_args()


def ensure_domain_list(raw: str) -> list[str]:
    items = [x.strip().lower() for x in raw.split(",") if x.strip()]
    invalid = [x for x in items if x not in DOMAINS]
    if invalid:
        raise SystemExit(f"Invalid domain(s): {', '.join(invalid)}. Allowed: {', '.join(DOMAINS)}")
    return items


def write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def main() -> None:
    args = parse_args()
    domains = ensure_domain_list(args.domains)

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    ts = now.strftime("%Y%m%d-%H%M%S")

    base = Path(args.base_dir).resolve()
    meeting_path = base / "docs" / "agents" / "meetings" / f"{date_str}-{args.topic}.md"

    agenda = f"""# Meeting: {args.topic}\n\n- Date: {date_str}\n- Time: {now.strftime('%H:%M:%S')}\n- Domains: {', '.join(domains)}\n\n## Agenda\n1. Status updates\n2. Blockers\n3. Decisions\n4. Action items\n\n## Decisions\n- (fill)\n\n## Action Items\n| ID | Action | Owner | Due Date | Status |\n|---|---|---|---|---|\n| A1 |  |  |  | TODO |\n\n## Feedback (Plan→Execute→Review→Patch)\n- Plan quality:\n- Execute issues:\n- Review findings:\n- Patch proposal:\n"""

    created_meeting = write_if_missing(meeting_path, agenda)

    created_logs: list[Path] = []
    for domain in domains:
        log_path = base / "logs" / "agents" / domain / f"{date_str}-{args.topic}-{ts}.md"
        log_text = f"""# {domain.capitalize()} Execution Log\n\n- Timestamp: {now.isoformat(timespec='seconds')}\n- Meeting: {meeting_path.name}\n- Topic: {args.topic}\n\n## Updates\n-\n\n## Decisions Applied\n-\n\n## Next Actions\n-\n"""
        if write_if_missing(log_path, log_text):
            created_logs.append(log_path)

    print(f"meeting_file={'created' if created_meeting else 'exists'}:{meeting_path}")
    for p in created_logs:
        print(f"log_file=created:{p}")


if __name__ == "__main__":
    main()
