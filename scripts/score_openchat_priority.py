#!/usr/bin/env python3
from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

DB = Path('/Users/sanghun/.openclaw/workspace/priceit-starter/data/priceit.db')
RULE_VERSION = 'priority-v1'

BASE = {
    'SOLD_OUT': 90,
    'RESTOCK': 85,
    'PRICE_UP': 80,
    'PRICE_DOWN': 70,
    'DELAY_NOTICE': 75,
    'NEW_ITEM': 45,
    'NOTICE': 40,
}


def classify_notice(text: str) -> tuple[str | None, int, str]:
    t = text or ''
    score_add = 0
    reasons = []
    subtype = None

    if re.search(r'배송\s*지연|지연\s*배송|출고\s*지연', t):
        subtype = 'DELIVERY_DELAY'
        score_add += 15
        reasons.append('delivery_delay')

    if re.search(r'2일\s*뒤|이틀\s*뒤', t) and re.search(r'공급가\s*인상|가격\s*인상|단가\s*인상', t):
        subtype = 'PRICE_UP_SCHEDULED_2D'
        score_add += 20
        reasons.append('price_up_scheduled_2d')
    elif re.search(r'공급가\s*인상\s*예정|가격\s*인상\s*예정|단가\s*인상\s*예정', t):
        subtype = 'PRICE_UP_SCHEDULED'
        score_add += 12
        reasons.append('price_up_scheduled')

    if re.search(r'오늘|내일', t) and re.search(r'인상', t):
        score_add += 25
        reasons.append('near_term_price_up')

    if re.search(r'마감\s*시간\s*변경|접수\s*마감', t):
        subtype = subtype or 'ORDER_CUTOFF_CHANGE'
        score_add += 10
        reasons.append('order_cutoff_change')

    return subtype, score_add, ','.join(reasons)


def level(score: float) -> str:
    if score >= 80:
        return 'high'
    if score >= 50:
        return 'medium'
    return 'low'


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute(
        '''
        SELECT f.id, f.event_type, f.old_price, f.new_price, f.importance_score,
               m.message_text
        FROM openchat_event_fact f
        LEFT JOIN messages m ON m.id = f.message_id
        '''
    ).fetchall()

    now = datetime.now().isoformat(timespec='seconds')
    updated = 0
    for r in rows:
        base = BASE.get(r['event_type'], 35)
        score = float(base)
        reasons = [f'base:{base}']

        # price delta bonus
        old_p = r['old_price']
        new_p = r['new_price']
        if old_p and new_p and old_p > 0:
            delta = abs(new_p - old_p) / old_p
            if delta >= 0.10:
                score += 15
                reasons.append('price_delta>=10%')

        subtype, add, reason_txt = classify_notice(r['message_text'] or '')
        score += add
        if reason_txt:
            reasons.append(reason_txt)

        score = max(0, min(100, score))
        lv = level(score)
        actionable = 1 if lv == 'high' else 0

        cur.execute(
            '''
            UPDATE openchat_event_fact
            SET notice_subtype = COALESCE(?, notice_subtype),
                importance_score = ?,
                importance_level = ?,
                is_actionable = ?,
                processed_at = ?
            WHERE id = ?
            ''',
            (subtype, score, lv, actionable, now, r['id'])
        )

        cur.execute(
            '''
            INSERT INTO event_priority_log
            (event_fact_id, rule_version, score_before, score_after, level_after, reason, processed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (r['id'], RULE_VERSION, r['importance_score'], score, lv, ';'.join(reasons), now)
        )
        updated += 1

    conn.commit()

    # export latest-by-vendor file
    out = Path('/Users/sanghun/.openclaw/workspace/priceit-starter/reports/openchat_priority_latest_by_vendor.csv')
    out.parent.mkdir(parents=True, exist_ok=True)
    rows2 = conn.execute(
        '''
        SELECT vendor_name, room_name, event_type, notice_subtype, importance_level, importance_score, event_at,
               substr(message_text,1,120) AS message_snippet
        FROM v_openchat_priority_feed
        WHERE vendor_name IS NOT NULL
        ORDER BY event_at DESC
        LIMIT 500
        '''
    ).fetchall()

    with out.open('w', encoding='utf-8') as f:
        f.write('vendor_name,room_name,event_type,notice_subtype,importance_level,importance_score,event_at,message_snippet\n')
        for x in rows2:
            vals = [x[k] if x[k] is not None else '' for k in x.keys()]
            vals = [str(v).replace('"', '""') for v in vals]
            f.write('"' + '","'.join(vals) + '"\n')

    print(f'updated={updated}')
    print(f'output={out}')

    conn.close()


if __name__ == '__main__':
    main()
