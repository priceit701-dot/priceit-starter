import hashlib
from datetime import datetime
from typing import Optional
from .db import conn_ctx
from .parser import parse_message, ParsedEvent
from .notifier import send_telegram


ROOM_EVENT_CONTEXT = {}
CONTEXT_TTL_SECONDS = 60 * 30
CONTEXT_EVENT_TYPES = {"PRICE_UP", "PRICE_DOWN", "NEW_ITEM", "SOLD_OUT", "DELAY_NOTICE"}
EVENT_TYPES_ORDER = ["PRICE_UP", "PRICE_DOWN", "SOLD_OUT", "RESTOCK", "DELAY_NOTICE", "NEW_ITEM", "NOTICE"]
EVENT_TYPES_SET = set(EVENT_TYPES_ORDER)


def _hash(room_name: str, sender: str, line: str, created_at: str):
    # created_at 포함으로 날짜가 다른 동일 공지까지 영구 중복처리되는 문제 방지
    return hashlib.sha1(f"{room_name}|{sender}|{created_at}|{line}".encode("utf-8")).hexdigest()


def _line_hash(room_name: str, line: str):
    return hashlib.sha1(f"{room_name}|{line.strip()}".encode("utf-8")).hexdigest()


def _is_noise_line(line: str) -> bool:
    s = line.strip().lower()
    if not s:
        return True

    # UI/devtools/css pollution
    css_tokens = [
        "border:", "padding:", "margin:", "box-sizing", "background-color:",
        "color:", "height:", "width:", "--", "counter-reset:", "katex",
    ]
    if any(tok in s for tok in css_tokens):
        return True

    # Kakao openchat boilerplate / join-leave noise
    kakao_noise_patterns = [
        "님이 들어왔습니다",
        "님이 나갔습니다",
        "오픈채팅봇",
        "환영합니다 대표님",
        "우측 상단",
        "공지사항에 있는 발주가이드",
        "\ud83d\udcac 상품/발주/송장/cs 문의는 1:1 채팅 바랍니다",
        "\ud83d\udc9b 발주마감",
        "운영정책을 위반한 메시지",
        "불법촬영물 식별",
        "관리자가",
        "메시지가 삭제되었습니다",
    ]
    if any(p in line for p in kakao_noise_patterns) or any(p in s for p in ["님이 들어왔습니다", "님이 나갔습니다", "메시지가 삭제되었습니다"]):
        return True

    if s.startswith("http") and "kakao" not in s and "docs.google.com" not in s:
        return False

    # very short symbol-only lines
    if len(s) < 2:
        return True
    return False


def _is_context_header(line: str) -> bool:
    s = line.strip()
    return (
        s.startswith("#가격")
        or "상품변동 요약" in s
        or "팜허브신규변동알림" in s
    )


def _extract_context_product(line: str) -> Optional[str]:
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    for quote in ["'", "‘", '"']:
        if quote in line:
            parts = line.split(quote)
            if len(parts) >= 3:
                candidate = parts[1].strip(" ’'\"")
                if candidate and len(candidate) > 1:
                    return candidate

    if line.startswith("📌"):
        candidate = line.replace("📌", "").replace("팜허브", "").strip(" -:")
        if candidate and len(candidate) >= 2:
            return candidate[:60]

    return None


def _get_context_event(room_name: str, created_at: str) -> Optional[str]:
    ctx = ROOM_EVENT_CONTEXT.get(room_name)
    if not ctx:
        return None
    try:
        now = datetime.fromisoformat(created_at)
        ts = datetime.fromisoformat(ctx["created_at"])
        if (now - ts).total_seconds() > CONTEXT_TTL_SECONDS:
            ROOM_EVENT_CONTEXT.pop(room_name, None)
            return None
    except Exception:
        ROOM_EVENT_CONTEXT.pop(room_name, None)
        return None
    return ctx.get("event_type")


def _audit_skip(conn, room_name: str, created_at: str, line: str, reason: str):
    conn.execute(
        """
        INSERT INTO ingestion_audit(room_name, created_at, line_hash, reason, raw_line)
        VALUES (?, ?, ?, ?, ?)
        """,
        (room_name, created_at, _line_hash(room_name, line), reason, line[:500]),
    )


def ingest_line(room_name: str, line: str, sender: str = "unknown", created_at: Optional[str] = None):
    created_at = created_at or datetime.now().isoformat(timespec="seconds")

    with conn_ctx() as conn:
        if _is_noise_line(line):
            _audit_skip(conn, room_name, created_at, line, "noise")
            return False

        # 최근 10분내 동일 방/동일 라인 중복 방지 (복붙 루프/스크롤 반복 대응)
        dup = conn.execute(
            """
            SELECT 1 FROM messages
            WHERE room_name = ?
              AND message_text = ?
              AND datetime(created_at) >= datetime(?, '-10 minutes')
            LIMIT 1
            """,
            (room_name, line, created_at),
        ).fetchone()
        if dup:
            _audit_skip(conn, room_name, created_at, line, "duplicate_window_10m")
            return False

        h = _hash(room_name, sender, line, created_at)
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO messages(room_name, sender, message_text, raw_line, created_at, hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (room_name, sender, line, line, created_at, h),
        )
        if cur.rowcount == 0:
            _audit_skip(conn, room_name, created_at, line, "duplicate_hash")
            return False

        msg_id = conn.execute("SELECT id FROM messages WHERE hash=?", (h,)).fetchone()[0]
        parsed = parse_message(line)

        if parsed and parsed.event_type in CONTEXT_EVENT_TYPES and _is_context_header(line) and not parsed.product_name:
            ROOM_EVENT_CONTEXT[room_name] = {"event_type": parsed.event_type, "created_at": created_at}
            return True

        if not parsed:
            ctx_event_type = _get_context_event(room_name, created_at)
            if ctx_event_type:
                product = _extract_context_product(line)
                if product:
                    parsed = ParsedEvent(
                        vendor="팜허브" if "팜허브" in line else None,
                        product_name=product,
                        option_name=None,
                        event_type=ctx_event_type,
                        old_price=None,
                        new_price=None,
                        stock_status="SOLD_OUT" if ctx_event_type == "SOLD_OUT" else None,
                        confidence=0.70,
                    )

        if not parsed:
            return True

        ev_cur = conn.execute(
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
        event_id = ev_cur.lastrowid

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

        # 신규 painpoint 스키마 병행 적재 (테이블 미존재 시 자동 스킵)
        try:
            canonical_item_key = f"{vendor}|{product}"
            conn.execute(
                """
                INSERT INTO openchat_item_master(
                    canonical_item_key, vendor_name, product_name_raw, product_name_norm, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(canonical_item_key) DO UPDATE SET
                    last_seen_at=excluded.last_seen_at,
                    product_name_raw=COALESCE(excluded.product_name_raw, openchat_item_master.product_name_raw),
                    product_name_norm=COALESCE(excluded.product_name_norm, openchat_item_master.product_name_norm)
                """,
                (canonical_item_key, vendor, product, product, created_at, created_at),
            )
            item_id = conn.execute("SELECT id FROM openchat_item_master WHERE canonical_item_key=?", (canonical_item_key,)).fetchone()[0]

            option_id = None
            if getattr(parsed, "option_name", None):
                option_key = parsed.option_name.strip().lower()
                conn.execute(
                    """
                    INSERT INTO openchat_item_option(item_id, option_name_raw, option_name_norm)
                    VALUES (?, ?, ?)
                    ON CONFLICT(item_id, option_name_norm) DO UPDATE SET option_name_raw=excluded.option_name_raw
                    """,
                    (item_id, parsed.option_name, option_key),
                )
                row_opt = conn.execute(
                    "SELECT id FROM openchat_item_option WHERE item_id=? AND option_name_norm=?",
                    (item_id, option_key),
                ).fetchone()
                option_id = row_opt[0] if row_opt else None

            event_type_std = parsed.event_type if parsed.event_type in EVENT_TYPES_SET else "NOTICE"
            conn.execute(
                """
                INSERT OR IGNORE INTO openchat_event_fact(
                    legacy_event_id, message_id, room_name, vendor_name, item_id, option_id,
                    event_type, old_price, new_price, stock_status, confidence, event_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    msg_id,
                    room_name,
                    vendor,
                    item_id,
                    option_id,
                    event_type_std,
                    parsed.old_price,
                    parsed.new_price,
                    parsed.stock_status,
                    parsed.confidence,
                    created_at,
                ),
            )
        except Exception:
            pass

    if parsed.event_type in {"SOLD_OUT", "RESTOCK", "PRICE_DOWN", "PRICE_UP"}:
        old_new = f" ({parsed.old_price} → {parsed.new_price})" if parsed.old_price or parsed.new_price else ""
        dedup_key = f"{msg_id}:{parsed.event_type}:{parsed.old_price}:{parsed.new_price}:{parsed.stock_status}"
        send_telegram(
            f"[{parsed.event_type}] {room_name}\n{parsed.vendor or ''} {parsed.product_name or ''}{old_new}".strip(),
            idempotency_key=dedup_key,
        )

    return True
