#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB = Path('/Users/sanghun/.openclaw/workspace/priceit-starter/data/priceit.db')


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute(
        '''
        SELECT f.id, f.event_type, f.notice_subtype, f.room_name, f.vendor_name,
               f.old_price, f.new_price, f.importance_level, f.importance_score,
               f.is_actionable, f.event_at, m.message_text
        FROM openchat_event_fact f
        LEFT JOIN messages m ON m.id = f.message_id
        WHERE f.importance_level IN ('high','medium')
        ORDER BY f.event_at DESC
        LIMIT 5000
        '''
    ).fetchall()

    inserted = 0
    for r in rows:
        payload = {
            'event_fact_id': r['id'],
            'event_type': r['event_type'],
            'notice_subtype': r['notice_subtype'],
            'room_name': r['room_name'],
            'vendor_name': r['vendor_name'],
            'old_price': r['old_price'],
            'new_price': r['new_price'],
            'importance_level': r['importance_level'],
            'importance_score': r['importance_score'],
            'is_actionable': r['is_actionable'],
            'event_at': r['event_at'],
            'message_text': r['message_text'],
        }
        c = cur.execute(
            '''
            INSERT OR IGNORE INTO openchat_priority_outbox(event_fact_id, payload_json, status)
            VALUES (?, ?, 'pending')
            ''',
            (r['id'], json.dumps(payload, ensure_ascii=False))
        )
        if c.rowcount:
            inserted += 1

    conn.commit()
    total_pending = cur.execute("SELECT count(*) FROM openchat_priority_outbox WHERE status='pending'").fetchone()[0]
    print(f'inserted={inserted}')
    print(f'pending={total_pending}')
    conn.close()


if __name__ == '__main__':
    main()
