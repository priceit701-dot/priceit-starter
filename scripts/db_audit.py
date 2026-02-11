#!/usr/bin/env python3
"""priceit DB 진단 스크립트.

사용:
  python3 scripts/db_audit.py --db data/priceit.db
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

ALLOWED_EVENT_TYPES = {
    "PRICE_UP",
    "PRICE_DOWN",
    "SOLD_OUT",
    "RESTOCK",
    "DELAY_NOTICE",
    "NEW_ITEM",
    "NOTICE",
}


def fetch_val(cur: sqlite3.Cursor, sql: str):
    return cur.execute(sql).fetchone()[0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/priceit.db")
    args = ap.parse_args()

    db_path = Path(args.db)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    metrics: dict[str, int | float] = {}

    for t in ["messages", "events", "products", "ingestion_audit"]:
        metrics[f"{t}_rows"] = fetch_val(cur, f"select count(*) from {t}")

    metrics["messages_hash_null"] = fetch_val(cur, "select count(*) from messages where hash is null or trim(hash)=''")
    metrics["messages_sender_null"] = fetch_val(cur, "select count(*) from messages where sender is null or trim(sender)=''")
    metrics["messages_raw_line_null"] = fetch_val(cur, "select count(*) from messages where raw_line is null or trim(raw_line)=''")

    metrics["messages_created_at_invalid"] = fetch_val(cur, "select count(*) from messages where datetime(created_at) is null")
    metrics["events_created_at_invalid"] = fetch_val(cur, "select count(*) from events where datetime(created_at) is null")
    metrics["ingestion_created_at_invalid"] = fetch_val(cur, "select count(*) from ingestion_audit where datetime(created_at) is null")

    metrics["messages_dup_group_room_sender_text_time"] = fetch_val(
        cur,
        """
        select count(*) from (
          select room_name, ifnull(sender,''), message_text, created_at, count(*) c
          from messages
          group by 1,2,3,4
          having c > 1
        )
        """,
    )
    metrics["messages_dup_rows_room_sender_text_time"] = fetch_val(
        cur,
        """
        select ifnull(sum(c-1),0) from (
          select room_name, ifnull(sender,''), message_text, created_at, count(*) c
          from messages
          group by 1,2,3,4
          having c > 1
        )
        """,
    )

    metrics["events_dup_group_message_type_vendor_product"] = fetch_val(
        cur,
        """
        select count(*) from (
          select message_id, event_type, ifnull(vendor,''), ifnull(product_name,''), count(*) c
          from events
          group by 1,2,3,4
          having c > 1
        )
        """,
    )
    metrics["events_dup_rows_message_type_vendor_product"] = fetch_val(
        cur,
        """
        select ifnull(sum(c-1),0) from (
          select message_id, event_type, ifnull(vendor,''), ifnull(product_name,''), count(*) c
          from events
          group by 1,2,3,4
          having c > 1
        )
        """,
    )

    rooms = [r[0] for r in cur.execute("select distinct room_name from messages")]

    def norm_room(s: str) -> str:
        t = s.strip().lower()
        t = re.sub(r"\s+", " ", t)
        return t.replace("\u200b", "")

    norm_map: dict[str, list[str]] = {}
    for room in rooms:
        norm_map.setdefault(norm_room(room), []).append(room)

    metrics["room_distinct"] = len(rooms)
    metrics["room_norm_distinct"] = len(norm_map)
    metrics["room_potential_variant_groups"] = sum(1 for v in norm_map.values() if len(v) > 1)

    metrics["events_vendor_null"] = fetch_val(cur, "select count(*) from events where vendor is null or trim(vendor)=''")
    metrics["events_product_null"] = fetch_val(cur, "select count(*) from events where product_name is null or trim(product_name)=''")
    metrics["products_canonical_key_null"] = fetch_val(cur, "select count(*) from products where canonical_key is null or trim(canonical_key)=''")

    metrics["events_vendor_iso_like"] = fetch_val(cur, "select count(*) from events where vendor like '____-__-__T__:%'")
    metrics["events_product_iso_like"] = fetch_val(cur, "select count(*) from events where product_name like '____-__-__T__:%'")

    event_types = [r[0] for r in cur.execute("select distinct event_type from events")]
    metrics["event_type_distinct"] = len(event_types)
    metrics["event_type_out_of_scope"] = sum(1 for e in event_types if e not in ALLOWED_EVENT_TYPES)
    metrics["event_type_not_upper_rows"] = fetch_val(cur, "select count(*) from events where event_type != upper(event_type)")

    metrics["bench_room_messages"] = fetch_val(cur, "select count(*) from messages where room_name like 'bench_room_%'")
    metrics["bench_room_events"] = fetch_val(cur, "select count(*) from events where room_name like 'bench_room_%'")

    top_event_types = [
        {"event_type": t, "count": c}
        for (t, c) in cur.execute("select event_type, count(*) c from events group by 1 order by c desc")
    ]

    out_of_scope_types = [t for t in event_types if t not in ALLOWED_EVENT_TYPES]

    iso_like_samples = [
        {
            "event_id": row[0],
            "message_id": row[1],
            "event_type": row[2],
            "vendor": row[3],
            "product_name": row[4],
            "created_at": row[5],
        }
        for row in cur.execute(
            """
            select id, message_id, event_type, vendor, product_name, created_at
            from events
            where vendor like '____-__-__T__:%' or product_name like '____-__-__T__:%'
            order by id
            limit 10
            """
        )
    ]

    report = {
        "db_path": str(db_path),
        "metrics": metrics,
        "top_event_types": top_event_types,
        "out_of_scope_event_types": out_of_scope_types,
        "room_variant_groups": [v for v in norm_map.values() if len(v) > 1],
        "iso_like_samples": iso_like_samples,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
