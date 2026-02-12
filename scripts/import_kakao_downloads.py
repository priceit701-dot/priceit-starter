#!/usr/bin/env python3
from __future__ import annotations

import csv
import glob
import hashlib
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

DB = Path('/Users/sanghun/.openclaw/workspace/priceit-starter/data/priceit.db')
REPORT = Path('/Users/sanghun/.openclaw/workspace/priceit-starter/reports') / f"kakao_download_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"


def room_from_filename(path: str) -> str:
    name = os.path.basename(path)
    m = re.match(r"KakaoTalk_Chat_(.+)_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.csv$", name)
    return m.group(1) if m else name


def msg_hash(room: str, sender: str, created_at: str, text: str) -> str:
    raw = f"{room}\n{sender}\n{created_at}\n{text}".encode('utf-8', 'ignore')
    return hashlib.sha1(raw).hexdigest()


def norm_text(t: str) -> str:
    return re.sub(r"\s+", " ", (t or '').strip())


def detect_event_type(text: str) -> str | None:
    if re.search(r"품절", text):
        return 'SOLD_OUT'
    if re.search(r"재입고|입고", text):
        return 'RESTOCK'
    if re.search(r"배송\s*지연|지연\s*배송", text):
        return 'DELAY_NOTICE'
    if re.search(r"인상|상승", text):
        return 'PRICE_UP'
    if re.search(r"인하|하락|할인", text):
        return 'PRICE_DOWN'
    if re.search(r"신상품|신규", text):
        return 'NEW_ITEM'
    if re.search(r"공지|안내|필독", text):
        return 'NOTICE'
    return None


def extract_prices(text: str):
    nums = re.findall(r"([0-9][0-9,]{2,})\s*원", text)
    vals = []
    for n in nums[:2]:
        try:
            vals.append(int(n.replace(',', '')))
        except Exception:
            pass
    if len(vals) >= 2:
        return vals[0], vals[1]
    if len(vals) == 1:
        return None, vals[0]
    return None, None


def extract_item_name(text: str) -> str:
    t = norm_text(text)
    t = re.sub(r"https?://\S+", "", t)
    parts = re.split(r"[|\-:\[\]()]", t)
    cand = next((p.strip() for p in parts if len(p.strip()) >= 2), t[:80])
    return cand[:80] if cand else 'unknown_item'


def upsert_item(conn: sqlite3.Connection, vendor: str, product_name: str, event_at: str) -> int:
    norm = norm_text(product_name).lower()
    key = hashlib.sha1(f"{vendor}|{norm}".encode()).hexdigest()[:24]
    conn.execute(
        '''
        INSERT INTO openchat_item_master(canonical_item_key, vendor_name, product_name_raw, product_name_norm, first_seen_at, last_seen_at)
        VALUES(?, ?, ?, ?, ?, ?)
        ON CONFLICT(canonical_item_key) DO UPDATE SET last_seen_at=excluded.last_seen_at
        ''',
        (key, vendor, product_name, norm, event_at, event_at)
    )
    row = conn.execute('SELECT id FROM openchat_item_master WHERE canonical_item_key=?', (key,)).fetchone()
    return int(row[0])


def import_one(conn: sqlite3.Connection, path: str):
    room = room_from_filename(path)
    encodings = ['utf-8-sig', 'cp949', 'utf-8']
    rows = None
    for enc in encodings:
        try:
            with open(path, 'r', encoding=enc, errors='ignore', newline='') as f:
                rows = list(csv.DictReader(f))
            break
        except Exception:
            continue
    if rows is None:
        return {'file': path, 'room': room, 'read_error': 1, 'msg_new': 0, 'msg_dup': 0, 'evt_new': 0, 'evt_dup': 0}

    msg_new = msg_dup = evt_new = evt_dup = 0
    for r in rows:
        created_at = (r.get('Date') or '').strip()
        sender = (r.get('User') or '').strip()
        text = (r.get('Message') or '').strip()
        if not created_at or not text:
            continue

        h = msg_hash(room, sender, created_at, text)
        cur = conn.execute(
            '''
            INSERT OR IGNORE INTO messages(room_name, sender, message_text, raw_line, created_at, hash)
            VALUES(?, ?, ?, ?, ?, ?)
            ''',
            (room, sender, text, text, created_at, h)
        )
        if cur.rowcount:
            msg_new += 1
        else:
            msg_dup += 1

        mid = conn.execute('SELECT id FROM messages WHERE hash=?', (h,)).fetchone()[0]
        et = detect_event_type(text)
        if not et:
            continue

        old_p, new_p = extract_prices(text)
        item_name = extract_item_name(text)
        vendor = room
        item_id = upsert_item(conn, vendor, item_name, created_at)

        dedup_key = hashlib.sha1(f"{room}|{created_at}|{et}|{item_name}|{old_p}|{new_p}".encode()).hexdigest()
        existed = conn.execute('SELECT 1 FROM openchat_event_fact WHERE dedup_key=?', (dedup_key,)).fetchone()
        if existed:
            evt_dup += 1
            continue

        conn.execute(
            '''
            INSERT INTO openchat_event_fact(
              legacy_event_id, message_id, room_name, vendor_name, item_id, option_id,
              event_type, old_price, new_price, stock_status, confidence, event_at, dedup_key
            ) VALUES(NULL, ?, ?, ?, ?, NULL, ?, ?, ?, NULL, 0.35, ?, ?)
            ''',
            (mid, room, vendor, item_id, et, old_p, new_p, created_at, dedup_key)
        )
        evt_new += 1

    return {'file': path, 'room': room, 'read_error': 0, 'msg_new': msg_new, 'msg_dup': msg_dup, 'evt_new': evt_new, 'evt_dup': evt_dup}


def main():
    files = sorted(glob.glob(str(Path.home() / 'Downloads' / 'KakaoTalk_Chat_*.csv')))
    conn = sqlite3.connect(DB)
    try:
        results = [import_one(conn, p) for p in files]
        conn.commit()

        total = {
            'files': len(results),
            'msg_new': sum(x['msg_new'] for x in results),
            'msg_dup': sum(x['msg_dup'] for x in results),
            'evt_new': sum(x['evt_new'] for x in results),
            'evt_dup': sum(x['evt_dup'] for x in results),
        }

        REPORT.parent.mkdir(parents=True, exist_ok=True)
        with REPORT.open('w', encoding='utf-8') as f:
            f.write(f"# Kakao Downloads Import Report\n\n")
            f.write(f"- files: {total['files']}\n")
            f.write(f"- msg_new: {total['msg_new']}\n")
            f.write(f"- msg_dup: {total['msg_dup']}\n")
            f.write(f"- evt_new: {total['evt_new']}\n")
            f.write(f"- evt_dup: {total['evt_dup']}\n\n")
            f.write("## per-file\n")
            for r in results[-80:]:
                f.write(f"- {os.path.basename(r['file'])}: msg_new={r['msg_new']} msg_dup={r['msg_dup']} evt_new={r['evt_new']} evt_dup={r['evt_dup']}\n")

        print(total)
        print(f"report={REPORT}")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
