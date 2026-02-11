import hashlib
from datetime import datetime
from typing import Optional
from .db import conn_ctx
from .parser import parse_message
from .notifier import send_telegram


def _hash(room_name: str, line: str):
    return hashlib.sha1(f"{room_name}|{line}".encode("utf-8")).hexdigest()


def _is_noise_line(line: str) -> bool:
    s = line.strip().lower()
    if not s:
        return True
    css_tokens = [
        "border:", "padding:", "margin:", "box-sizing", "background-color:",
        "color:", "height:", "width:", "--", "counter-reset:", "katex",
    ]
    if any(tok in s for tok in css_tokens):
        return True
    if s.startswith("http") and "kakao" not in s and "docs.google.com" not in s:
        return False
    # very short symbol-only lines
    if len(s) < 2:
        return True
    return False


def ingest_line(room_name: str, line: str, sender: str = "unknown", created_at: Optional[str] = None):
    created_at = created_at or datetime.now().isoformat(timespec="seconds")
    if _is_noise_line(line):
        return False
    h = _hash(room_name, line)

    with conn_ctx() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO messages(room_name, sender, message_text, raw_line, created_at, hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (room_name, sender, line, line, created_at, h),
        )
        if cur.rowcount == 0:
            return False

        msg_id = conn.execute("SELECT id FROM messages WHERE hash=?", (h,)).fetchone()[0]
        parsed = parse_message(line)
        if not parsed:
            return True

        conn.execute(
            """
            INSERT INTO events(
                message_id, room_name, vendor, product_name, event_type,
                old_price, new_price, stock_status, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                msg_id,
                room_name,
                parsed.vendor,
                parsed.product_name,
                parsed.event_type,
                parsed.old_price,
                parsed.new_price,
                parsed.stock_status,
                parsed.confidence,
                created_at,
            ),
        )

        vendor = parsed.vendor or "UNKNOWN"
        product = parsed.product_name or line[:40]
        key = f"{vendor}|{product}"
        row = conn.execute("SELECT id FROM products WHERE canonical_key=?", (key,)).fetchone()
        if row:
            conn.execute(
                """
                UPDATE products
                SET latest_price = COALESCE(?, latest_price),
                    last_stock_status = COALESCE(?, last_stock_status),
                    updated_at = ?
                WHERE canonical_key = ?
                """,
                (parsed.new_price, parsed.stock_status, created_at, key),
            )
        else:
            conn.execute(
                """
                INSERT INTO products(vendor, product_name, canonical_key, latest_price, last_stock_status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (vendor, product, key, parsed.new_price, parsed.stock_status, created_at),
            )

    if parsed.event_type in {"SOLD_OUT", "RESTOCK", "PRICE_DOWN", "PRICE_UP"}:
        old_new = f" ({parsed.old_price} → {parsed.new_price})" if parsed.old_price or parsed.new_price else ""
        send_telegram(f"[{parsed.event_type}] {room_name}\n{parsed.vendor or ''} {parsed.product_name or ''}{old_new}".strip())

    return True
