#!/usr/bin/env python3
import json
import sqlite3
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "priceit.db"
CATALOG = ROOT / "data" / "seller_product_catalog_20260212.json"
REPORT_JSON = ROOT / "reports" / "seller_catalog_openchat_link_20260212.json"
REPORT_MD = ROOT / "reports" / "seller_catalog_openchat_link_20260212.md"


def main():
    if not CATALOG.exists():
        raise SystemExit(f"catalog not found: {CATALOG}")

    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    keywords = [k.strip() for k in payload.get("keywords", []) if str(k).strip()]

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS seller_catalog_link (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          matched_keyword TEXT NOT NULL,
          room_name TEXT,
          message_id INTEGER,
          event_id INTEGER,
          event_type TEXT,
          matched_text TEXT,
          created_at TEXT,
          UNIQUE(matched_keyword, message_id, event_id)
        )
        """
    )

    cur.execute("DELETE FROM seller_catalog_link")

    # recent 30 days messages + joined events
    cur.execute(
        """
        SELECT m.id, m.room_name, m.message_text, m.created_at, e.id, e.event_type
        FROM messages m
        LEFT JOIN events e ON e.message_id = m.id
        WHERE datetime(m.created_at) >= datetime('now', '-30 day')
        ORDER BY m.id DESC
        """
    )
    rows = cur.fetchall()

    inserted = 0
    matched_keywords = set()
    room_counter = {}
    type_counter = {}

    for mid, room, text, created_at, eid, etype in rows:
        t = text or ""
        found = []
        for kw in keywords:
            if len(kw) < 2:
                continue
            if kw in t:
                found.append(kw)
        if not found:
            continue
        for kw in sorted(set(found), key=lambda x: (-len(x), x))[:3]:
            try:
                cur.execute(
                    """
                    INSERT OR IGNORE INTO seller_catalog_link
                    (matched_keyword, room_name, message_id, event_id, event_type, matched_text, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (kw, room, mid, eid, etype, t[:300], created_at),
                )
                if cur.rowcount:
                    inserted += 1
                    matched_keywords.add(kw)
                    room_counter[room] = room_counter.get(room, 0) + 1
                    if etype:
                        type_counter[etype] = type_counter.get(etype, 0) + 1
            except Exception:
                pass

    conn.commit()

    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "catalog_keywords": len(keywords),
        "matched_keywords": len(matched_keywords),
        "linked_rows": inserted,
        "top_rooms": sorted(
            [{"room": k, "count": v} for k, v in room_counter.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10],
        "event_type_counts": type_counter,
        "sample_keywords": sorted(list(matched_keywords))[:30],
    }

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 판매리스트-오픈채팅 데이터 연결 결과 (2026-02-12)",
        "",
        f"- catalog_keywords: **{out['catalog_keywords']}**",
        f"- matched_keywords: **{out['matched_keywords']}**",
        f"- linked_rows: **{out['linked_rows']}**",
        "",
        "## 이벤트 유형 분포",
    ]
    for k, v in sorted(type_counter.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- {k}: {v}")

    lines.append("")
    lines.append("## 상위 매칭 룸")
    for r in out["top_rooms"]:
        lines.append(f"- {r['room']}: {r['count']}")

    lines.append("")
    lines.append("## 샘플 매칭 키워드")
    lines.append("- " + ", ".join(out["sample_keywords"]))

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
