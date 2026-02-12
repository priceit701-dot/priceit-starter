#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import requests

DB = Path('/Users/sanghun/.openclaw/workspace/priceit-starter/data/priceit.db')
API_URL = os.getenv('PRICEIT_PRIORITY_API_URL', '').strip()
API_TOKEN = os.getenv('PRICEIT_PRIORITY_API_TOKEN', '').strip()
BATCH_SIZE = int(os.getenv('PRICEIT_PRIORITY_BATCH_SIZE', '100'))


def next_retry(attempt: int) -> str:
    # simple backoff: 1m, 5m, 15m, 60m (cap)
    mins = [1, 5, 15, 60][min(attempt, 3)]
    return (datetime.now() + timedelta(minutes=mins)).isoformat(timespec='seconds')


def main():
    if not API_URL:
        print('skip: PRICEIT_PRIORITY_API_URL not set')
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute(
        '''
        SELECT id, event_fact_id, payload_json, attempt_count
        FROM openchat_priority_outbox
        WHERE status='pending' AND (next_retry_at IS NULL OR next_retry_at <= datetime('now'))
        ORDER BY created_at ASC
        LIMIT ?
        ''',
        (BATCH_SIZE,)
    ).fetchall()

    sent = 0
    failed = 0
    headers = {'Content-Type': 'application/json'}
    if API_TOKEN:
        headers['Authorization'] = f'Bearer {API_TOKEN}'

    for r in rows:
        try:
            payload = json.loads(r['payload_json'])
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=20)
            if 200 <= resp.status_code < 300:
                cur.execute(
                    "UPDATE openchat_priority_outbox SET status='sent', sent_at=datetime('now'), attempt_count=attempt_count+1, last_error=NULL WHERE id=?",
                    (r['id'],)
                )
                sent += 1
            else:
                attempt = int(r['attempt_count']) + 1
                cur.execute(
                    "UPDATE openchat_priority_outbox SET status='pending', attempt_count=?, last_error=?, next_retry_at=? WHERE id=?",
                    (attempt, f'http_{resp.status_code}:{resp.text[:300]}', next_retry(attempt), r['id'])
                )
                failed += 1
        except Exception as e:
            attempt = int(r['attempt_count']) + 1
            cur.execute(
                "UPDATE openchat_priority_outbox SET status='pending', attempt_count=?, last_error=?, next_retry_at=? WHERE id=?",
                (attempt, str(e)[:300], next_retry(attempt), r['id'])
            )
            failed += 1

    conn.commit()
    pending = cur.execute("SELECT count(*) FROM openchat_priority_outbox WHERE status='pending'").fetchone()[0]
    sent_total = cur.execute("SELECT count(*) FROM openchat_priority_outbox WHERE status='sent'").fetchone()[0]
    print(f'batch={len(rows)} sent={sent} failed={failed} pending={pending} sent_total={sent_total}')
    conn.close()


if __name__ == '__main__':
    main()
