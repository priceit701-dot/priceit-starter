#!/usr/bin/env python3
"""중복 점검 + (옵션) 안전 적용 스크립트.

기본 동작: 중복 점검 리포트만 생성
옵션 --apply: 중복이 있을 때만 안전 삭제(백업 포함) 후 전/후 비교 리포트 생성

사용 예시:
  python3 scripts/dedup_audit.py --db data/priceit.db
  python3 scripts/dedup_audit.py --db data/priceit.db --apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DedupSpec:
    name: str
    description: str
    group_sql: str
    delete_sql: str | None


SPECS = [
    DedupSpec(
        name="messages",
        description=(
            "중복 정의: room_name + sender(NULL→'') + message_text + created_at가 동일한 레코드"
        ),
        group_sql="""
            select room_name, ifnull(sender,''), message_text, created_at, count(*) c
            from messages
            group by 1,2,3,4
            having c > 1
        """,
        delete_sql="""
            delete from messages
            where id in (
              select id from (
                select id,
                       row_number() over (
                         partition by room_name, ifnull(sender,''), message_text, created_at
                         order by id
                       ) rn
                from messages
              ) t
              where rn > 1
            )
        """,
    ),
    DedupSpec(
        name="events",
        description=(
            "중복 정의: message_id + event_type + vendor(NULL→'') + product_name(NULL→'') + created_at가 동일한 레코드"
        ),
        group_sql="""
            select message_id, event_type, ifnull(vendor,''), ifnull(product_name,''), created_at, count(*) c
            from events
            group by 1,2,3,4,5
            having c > 1
        """,
        delete_sql="""
            delete from events
            where id in (
              select id from (
                select id,
                       row_number() over (
                         partition by message_id, event_type, ifnull(vendor,''), ifnull(product_name,''), created_at
                         order by id
                       ) rn
                from events
              ) t
              where rn > 1
            )
        """,
    ),
    DedupSpec(
        name="products",
        description="중복 정의: canonical_key(공백/NULL 제외)가 동일한 레코드",
        group_sql="""
            select canonical_key, count(*) c
            from products
            where canonical_key is not null and trim(canonical_key) <> ''
            group by canonical_key
            having c > 1
        """,
        delete_sql="""
            delete from products
            where id in (
              select id from (
                select id,
                       row_number() over (
                         partition by canonical_key
                         order by id
                       ) rn
                from products
                where canonical_key is not null and trim(canonical_key) <> ''
              ) t
              where rn > 1
            )
        """,
    ),
    DedupSpec(
        name="alarm_summary",
        description=(
            "중복 정의: v_events_alarm 기준 room_name + event_type_std + vendor_std(NULL→'') + "
            "product_std(NULL→'') + created_at + message_id(NULL→-1)가 동일한 이벤트"
        ),
        group_sql="""
            select room_name, event_type_std, ifnull(vendor_std,''), ifnull(product_std,''), created_at, ifnull(message_id,-1), count(*) c
            from v_events_alarm
            group by 1,2,3,4,5,6
            having c > 1
        """,
        delete_sql=None,
    ),
]


def _count_rows(cur: sqlite3.Cursor, sql: str) -> tuple[int, int]:
    group_count = cur.execute(f"select count(*) from ({sql})").fetchone()[0]
    dup_rows = cur.execute(f"select ifnull(sum(c-1),0) from ({sql})").fetchone()[0]
    return int(group_count), int(dup_rows)


def collect_metrics(conn: sqlite3.Connection) -> dict[str, Any]:
    cur = conn.cursor()
    out: dict[str, Any] = {"targets": {}}
    for spec in SPECS:
        group_count, dup_rows = _count_rows(cur, spec.group_sql)
        out["targets"][spec.name] = {
            "definition": spec.description,
            "duplicate_groups": group_count,
            "duplicate_rows": dup_rows,
        }

    alarm_counts = [
        {"event_type_std": r[0], "count": r[1]}
        for r in cur.execute(
            """
            select event_type_std, count(*) c
            from v_events_alarm
            group by 1
            order by c desc, event_type_std
            """
        )
    ]
    out["alarm_type_counts"] = alarm_counts
    return out


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def render_md(report: dict[str, Any]) -> str:
    pre = report["pre"]
    post = report["post"]
    lines = [
        f"# Dedup Audit Report ({report['audit_date']})",
        "",
        f"- DB: `{report['db_path']}`",
        f"- Executed at: {report['executed_at']}",
        f"- Apply mode: `{str(report['apply_mode']).lower()}`",
        f"- Backup file: `{report.get('backup_file') or '-'}`",
        "",
        "## Duplicate Definitions",
    ]
    for name, item in pre["targets"].items():
        lines.append(f"- **{name}**: {item['definition']}")

    lines += ["", "## Before/After Duplicate Counts", "", "| Target | Before groups | Before rows | After groups | After rows |", "|---|---:|---:|---:|---:|"]
    for name in pre["targets"].keys():
        b = pre["targets"][name]
        a = post["targets"][name]
        lines.append(
            f"| {name} | {b['duplicate_groups']} | {b['duplicate_rows']} | {a['duplicate_groups']} | {a['duplicate_rows']} |"
        )

    lines += ["", "## Alarm Type Impact (Before → After)", "", "| event_type_std | before | after | delta |", "|---|---:|---:|---:|"]
    before_map = {r["event_type_std"]: r["count"] for r in pre["alarm_type_counts"]}
    after_map = {r["event_type_std"]: r["count"] for r in post["alarm_type_counts"]}
    keys = sorted(set(before_map) | set(after_map))
    for k in keys:
        b = before_map.get(k, 0)
        a = after_map.get(k, 0)
        lines.append(f"| {k} | {b} | {a} | {a-b:+d} |")

    lines += ["", "## Rollback", "", f"- Restore command: `{report['rollback']['restore_command']}`"]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/priceit.db")
    ap.add_argument("--apply", action="store_true", help="중복이 있을 때 안전 삭제 적용")
    args = ap.parse_args()

    db_path = Path(args.db).resolve()
    today = datetime.now().strftime("%Y%m%d")
    reports_dir = Path("reports")
    json_path = reports_dir / f"dedup_audit_{today}.json"
    md_path = reports_dir / f"dedup_audit_{today}.md"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    pre = collect_metrics(conn)
    backup_file: Path | None = None

    if args.apply:
        removable_dup_rows = 0
        for spec in SPECS:
            if spec.delete_sql is None:
                continue
            removable_dup_rows += pre["targets"][spec.name]["duplicate_rows"]

        if removable_dup_rows > 0:
            backup_file = db_path.with_name(f"{db_path.name}.backup_dedup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            shutil.copy2(db_path, backup_file)

            conn.execute("begin immediate")
            try:
                cur = conn.cursor()
                for spec in SPECS:
                    if spec.delete_sql:
                        cur.execute(spec.delete_sql)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    post = collect_metrics(conn)
    conn.close()

    report = {
        "audit_date": today,
        "executed_at": datetime.now().isoformat(),
        "db_path": str(db_path),
        "apply_mode": args.apply,
        "backup_file": str(backup_file) if backup_file else None,
        "definitions": {s.name: s.description for s in SPECS},
        "pre": pre,
        "post": post,
        "rollback": {
            "restore_command": (
                f"cp '{backup_file}' '{db_path}'" if backup_file else "No-op (no changes applied)"
            )
        },
    }

    ensure_parent(json_path)
    ensure_parent(md_path)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_md(report), encoding="utf-8")

    print(str(json_path))
    print(str(md_path))


if __name__ == "__main__":
    main()
