from typing import Optional
from pathlib import Path
import sqlite3
import re

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .db import init_db
from .pipeline import ingest_line
from .config import DB_PATH
from .parser import extract_item_profile

app = FastAPI(title="priceit collector")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALERT_TYPES_ORDER = [
    "PRICE_UP",
    "PRICE_DOWN",
    "SOLD_OUT",
    "RESTOCK",
    "DELAY_NOTICE",
    "NEW_ITEM",
    "NOTICE",
]
ACTION_REQUIRED_TYPES = ["SOLD_OUT", "DELAY_NOTICE", "PRICE_UP", "PRICE_DOWN"]

FOCUS_ROOM_FILTER_SQL = " and (room_name like '최고집%' or room_name like '%팜허브%') "

ITEM_NAME_NOISE_KEYWORDS = [
    "긴급공지", "중요공지", "공지", "안내", "알림", "배송", "출고", "마감", "확인", "연휴",
    "품절", "품절안내", "재입고", "입고", "가격인상", "가격인하", "가격변동", "전격 오픈",
    "인상", "인하", "특가", "필독", "사항", "슈퍼", "명절", "신상품", "오픈", "세일",
]

PRODUCT_KEYWORDS = [
    "사과", "부사", "감귤", "딸기", "토마토", "감자", "고구마", "양파", "마늘", "오이",
    "상추", "시금치", "구좌당근", "당근", "키위", "쌀", "잡곡", "아몬드", "호두", "버즈", "애플워치",
]


def _load_seller_product_keywords() -> list[str]:
    catalog_path = Path(__file__).resolve().parent.parent / "data" / "seller_product_catalog_20260212.json"
    if not catalog_path.exists():
        return []
    try:
        import json

        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        kws = payload.get("keywords") or []
        return [str(k).strip() for k in kws if str(k).strip()]
    except Exception:
        return []


_PRODUCT_KEYWORDS_SELLER = _load_seller_product_keywords()
if _PRODUCT_KEYWORDS_SELLER:
    PRODUCT_KEYWORDS = sorted(set(PRODUCT_KEYWORDS + _PRODUCT_KEYWORDS_SELLER), key=lambda x: (-len(x), x))


def _is_noise_item_name(value: Optional[str]) -> bool:
    s = _clean_text(value)
    if not s:
        return True
    if len(s) <= 2:
        return True
    if re.fullmatch(r"[\W_]+", s):
        return True
    if re.match(r"^\d{1,2}월\s*\d{1,2}일", s):
        return True
    if any(x in s for x in ["드립니다", "확인", "마감", "흐름", "관련", "사고", "연휴"]):
        return True
    if any(x in s for x in ["🔺", "🔻", "⬆", "⬇", "★", "🔥"]) and not any(pk in s for pk in PRODUCT_KEYWORDS):
        return True
    if "입고" in s and len(s) >= 8:
        return True
    # 상태/공지성 문구가 섞이고 상품 키워드가 없으면 상품명으로 보지 않음
    hit = sum(1 for k in ITEM_NAME_NOISE_KEYWORDS if k in s)
    has_product_kw = any(pk in s for pk in PRODUCT_KEYWORDS)
    if hit >= 1 and not has_product_kw:
        return True
    if any(s.startswith(prefix) for prefix in ["공지", "긴급공지", "중요공지", "안내", "알림", "📢"]):
        return True
    return False


def _extract_market_item_from_text(message_text: Optional[str]) -> Optional[str]:
    s = _clean_text(message_text)
    if not s:
        return None
    s = re.sub(r"[\[\]{}()<>|]", " ", s)
    s = re.sub(r"\s+", " ", s)
    for kw in PRODUCT_KEYWORDS:
        if kw in s:
            return kw
    return None


def _best_item_name(product_name: Optional[str], profile_item_name: Optional[str], vendor: Optional[str], message_text: Optional[str] = None) -> tuple[str, str]:
    p = re.sub(r"\[[^\]]+\]", "", _clean_text(product_name)).strip()
    prof = re.sub(r"\[[^\]]+\]", "", _clean_text(profile_item_name)).strip()
    v = _clean_text(vendor)

    if prof and not _is_noise_item_name(prof):
        return prof, "profile"
    if p and not _is_noise_item_name(p):
        return p, "product_name"

    extracted = _extract_market_item_from_text(message_text)
    if extracted and not _is_noise_item_name(extracted):
        return extracted, "message_keyword"

    if v and not _is_noise_item_name(v):
        return v, "vendor"
    return "미분류 상품", "fallback"


def _is_ts_like(value: Optional[str]) -> bool:
    if not value:
        return False
    s = str(value).strip()
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", s))


def _clean_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if not s or _is_ts_like(s):
        return ""
    return s


def _extract_item_fields(message_text: Optional[str], vendor: Optional[str] = None) -> dict:
    if not message_text:
        return {
            "item_name": "미분류 상품",
            "item_name_raw": None,
            "item_name_norm": None,
            "option_tokens": [],
            "brand": vendor,
            "grade": None,
            "origin": None,
            "unit": None,
        }
    profile = extract_item_profile(str(message_text), vendor=vendor)
    item_name = profile.item_name_norm or profile.item_name_raw or "미분류 상품"
    return {
        "item_name": item_name,
        "item_name_raw": profile.item_name_raw,
        "item_name_norm": profile.item_name_norm,
        "option_tokens": profile.option_tokens,
        "brand": profile.brand,
        "grade": profile.grade,
        "origin": profile.origin,
        "unit": profile.unit,
    }


def _event_change_text(event_type: str, old_price: Optional[int], new_price: Optional[int]) -> str:
    if event_type in {"PRICE_UP", "PRICE_DOWN"}:
        if old_price is not None and new_price is not None:
            diff = new_price - old_price
            sign = "+" if diff > 0 else ""
            return f"{old_price:,}원 → {new_price:,}원 ({sign}{diff:,}원)"
        if new_price is not None:
            return f"현재가 {new_price:,}원"
        return "가격 변동"
    if event_type == "SOLD_OUT":
        return "품절"
    if event_type == "RESTOCK":
        return "재입고"
    if event_type == "DELAY_NOTICE":
        return "출고/배송 지연"
    if event_type == "NEW_ITEM":
        return "신규 상품"
    if event_type == "NOTICE":
        return "운영 공지"
    return "-"


class IngestBody(BaseModel):
    room_name: str
    message_text: str
    sender: str = "unknown"
    created_at: Optional[str] = None


WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
if WEB_ROOT.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_ROOT)), name="web")


@app.on_event("startup")
def _startup():
    init_db()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ingest")
def ingest(body: IngestBody):
    ok = ingest_line(body.room_name, body.message_text, body.sender, body.created_at)
    return {"ok": ok}


@app.get("/stats/summary")
def stats_summary():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("select count(*), max(created_at) from messages")
    msg_count, last_msg = cur.fetchone()
    cur.execute("select count(*) from events")
    ev_count = cur.fetchone()[0]
    cur.execute("select room_name, count(*) c from messages group by room_name order by c desc limit 20")
    top_rooms = [{"room": r, "count": c} for r, c in cur.fetchall()]
    cur.execute("select event_type, count(*) c from events group by event_type order by c desc")
    by_type = [{"type": t, "count": c} for t, c in cur.fetchall()]
    conn.close()
    return {
        "messages": msg_count,
        "events": ev_count,
        "last_message_at": last_msg,
        "top_rooms": top_rooms,
        "events_by_type": by_type,
    }


@app.get("/stats/timeline")
def stats_timeline(limit_hours: int = 48):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        select substr(created_at, 1, 13) || ':00:00' as hour_key, count(*)
        from messages
        where datetime(created_at) >= datetime('now', ?)
        group by hour_key
        order by hour_key asc
        """,
        (f"-{limit_hours} hours",),
    )
    timeline = [{"hour": h, "count": c} for h, c in cur.fetchall()]
    conn.close()
    return {"timeline": timeline}


@app.get("/stats/quality")
def stats_quality(limit_hours: int = 24):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        select event_type, count(*) c, round(avg(confidence), 3) avg_conf
        from events
        where datetime(created_at) >= datetime('now', ?)
        group by event_type
        order by c desc
        """,
        (f"-{limit_hours} hours",),
    )
    by_type = [
        {"event_type": t, "count": c, "avg_confidence": avg_conf}
        for t, c, avg_conf in cur.fetchall()
    ]
    cur.execute(
        """
        select reason, count(*) c
        from ingestion_audit
        where datetime(created_at) >= datetime('now', ?)
        group by reason
        order by c desc
        """,
        (f"-{limit_hours} hours",),
    )
    skips = [{"reason": r, "count": c} for r, c in cur.fetchall()]
    conn.close()
    return {"hours": limit_hours, "event_quality": by_type, "skip_reasons": skips}


@app.get("/events/recent")
def events_recent(limit: int = 30):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        select id, room_name, vendor, product_name, event_type, old_price, new_price, confidence, created_at
        from events
        order by id desc
        limit ?
        """,
        (min(max(limit, 1), 200),),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"items": rows}


@app.get("/stats/seller")
def stats_seller(limit_hours: int = 24, feed_limit: int = 30, action_limit: int = 15, include_bench: bool = False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    placeholders = ",".join(["?"] * len(ALERT_TYPES_ORDER))
    room_filter = "" if include_bench else " and room_name not like 'bench_room_%' "
    room_filter += FOCUS_ROOM_FILTER_SQL
    cur.execute(
        f"""
        select event_type, count(*) c
        from events
        where datetime(created_at) >= datetime('now', ?)
          and event_type in ({placeholders})
          {room_filter}
        group by event_type
        """,
        [f"-{limit_hours} hours", *ALERT_TYPES_ORDER],
    )
    counts = {row["event_type"]: row["c"] for row in cur.fetchall()}
    today_alerts = [{"type": alert_type, "count": int(counts.get(alert_type, 0))} for alert_type in ALERT_TYPES_ORDER]

    cur.execute(
        """
        select e.id, e.room_name, e.vendor, e.product_name, e.event_type, e.old_price, e.new_price, e.confidence, e.created_at,
               m.message_text
        from events e
        left join messages m on m.id = e.message_id
        where e.event_type in ({})
          {}
        order by e.id desc
        limit ?
        """.format(placeholders, room_filter.replace('room_name', 'e.room_name')),
        [*ALERT_TYPES_ORDER, min(max(feed_limit, 1), 100)],
    )
    recent_feed = []
    for r in cur.fetchall():
        row = dict(r)
        item_fields = _extract_item_fields(row.get("message_text"), vendor=row.get("vendor"))
        row.update(item_fields)
        best_name, source = _best_item_name(row.get("product_name"), item_fields.get("item_name"), row.get("vendor"), row.get("message_text"))
        row["item_name"] = best_name
        row["item_name_source"] = source
        row["change_text"] = _event_change_text(row.get("event_type"), row.get("old_price"), row.get("new_price"))
        recent_feed.append(row)

    action_placeholders = ",".join(["?"] * len(ACTION_REQUIRED_TYPES))
    cur.execute(
        """
        select e.id, e.room_name, e.vendor, e.product_name, e.event_type, e.old_price, e.new_price, e.confidence, e.created_at,
               m.message_text
        from events e
        left join messages m on m.id = e.message_id
        where e.event_type in ({})
          {}
        order by e.id desc
        limit ?
        """.format(action_placeholders, room_filter.replace('room_name', 'e.room_name')),
        [*ACTION_REQUIRED_TYPES, min(max(action_limit, 1), 100)],
    )
    action_items = []
    for r in cur.fetchall():
        row = dict(r)
        item_fields = _extract_item_fields(row.get("message_text"), vendor=row.get("vendor"))
        row.update(item_fields)
        best_name, source = _best_item_name(row.get("product_name"), item_fields.get("item_name"), row.get("vendor"), row.get("message_text"))
        row["item_name"] = best_name
        row["item_name_source"] = source
        row["change_text"] = _event_change_text(row.get("event_type"), row.get("old_price"), row.get("new_price"))
        action_items.append(row)

    # seller insight model (content-focused)
    cur.execute(
        """
        select e.id, e.room_name, e.vendor, e.product_name, e.event_type, e.old_price, e.new_price, e.stock_status, e.confidence, e.created_at,
               m.message_text
        from events e
        left join messages m on m.id = e.message_id
        where datetime(e.created_at) >= datetime('now', ?)
          and e.event_type in ({})
          {}
        order by datetime(e.created_at) desc, e.id desc
        """.format(placeholders, room_filter.replace('room_name', 'e.room_name')),
        [f"-{limit_hours} hours", *ALERT_TYPES_ORDER],
    )
    scoped_events = [dict(r) for r in cur.fetchall()]

    def clean_text(value):
        text = (value or "").strip()
        if not text:
            return ""
        # parser noise guard: timestamp-like 문자열은 아이템 라벨에서 제외
        if len(text) >= 19 and text[4:5] == "-" and text[7:8] == "-" and text[10:11] in {"T", " "}:
            return ""
        return text

    def item_key(row):
        vendor = clean_text(row.get("vendor"))
        product = clean_text(row.get("product_name"))
        return (vendor.lower(), product.lower())

    def item_label(row):
        extracted = _extract_item_fields(row.get("message_text"), vendor=row.get("vendor"))
        best_name, _ = _best_item_name(row.get("product_name"), extracted.get("item_name"), row.get("vendor"), row.get("message_text"))
        return best_name

    def price_evidence(row):
        old_price = row.get("old_price")
        new_price = row.get("new_price")
        if old_price in (None, "") or new_price in (None, ""):
            return None
        try:
            old_i = int(old_price)
            new_i = int(new_price)
        except (TypeError, ValueError):
            return None
        if old_i == 0:
            return {"old_price": old_i, "new_price": new_i, "delta": new_i - old_i, "delta_rate_pct": None}
        delta = new_i - old_i
        return {
            "old_price": old_i,
            "new_price": new_i,
            "delta": delta,
            "delta_rate_pct": round((delta / old_i) * 100, 2),
        }

    aggregated = {}
    for row in scoped_events:
        key = item_key(row)
        if key not in aggregated:
            aggregated[key] = {
                "item": item_label(row),
                "vendor": row.get("vendor"),
                "product_name": row.get("product_name"),
                "last_event_at": row.get("created_at"),
                "event_count": 0,
                "price_up_count": 0,
                "price_down_count": 0,
                "sold_out_count": 0,
                "delay_notice_count": 0,
                "max_abs_price_change_pct": 0.0,
                "recent_rooms": set(),
                "recent_event_types": set(),
            }
        rec = aggregated[key]
        rec["event_count"] += 1
        rec["recent_rooms"].add(row.get("room_name") or "-")
        rec["recent_event_types"].add(row.get("event_type"))
        if row.get("event_type") == "PRICE_UP":
            rec["price_up_count"] += 1
        if row.get("event_type") == "PRICE_DOWN":
            rec["price_down_count"] += 1
        if row.get("event_type") == "SOLD_OUT":
            rec["sold_out_count"] += 1
        if row.get("event_type") == "DELAY_NOTICE":
            rec["delay_notice_count"] += 1
        pe = price_evidence(row)
        if pe and pe.get("delta_rate_pct") is not None:
            rec["max_abs_price_change_pct"] = max(rec["max_abs_price_change_pct"], abs(pe["delta_rate_pct"]))

    change_summary_by_item = []
    for rec in aggregated.values():
        sentence = (
            f"최근 {limit_hours}시간 동안 {rec['item']}에서 {rec['event_count']}건 변동 "
            f"(인상 {rec['price_up_count']} / 인하 {rec['price_down_count']} / 품절 {rec['sold_out_count']} / 지연 {rec['delay_notice_count']})."
        )
        price_spike_risk = rec["price_up_count"] >= 2 or rec["max_abs_price_change_pct"] >= 7
        repeat_sold_out = rec["sold_out_count"] >= 2
        supply_delay = rec["delay_notice_count"] >= 1
        option_confusion = rec["event_count"] >= 3 and rec["price_up_count"] >= 1 and rec["price_down_count"] >= 1
        margin_pressure = (rec["price_up_count"] > rec["price_down_count"] and rec["max_abs_price_change_pct"] >= 5) or (
            rec["price_up_count"] >= 1 and (rec["sold_out_count"] + rec["delay_notice_count"]) >= 1
        )

        change_summary_by_item.append(
            {
                "item": rec["item"],
                "vendor": rec["vendor"],
                "product_name": rec["product_name"],
                "last_event_at": rec["last_event_at"],
                "event_count": rec["event_count"],
                "price_up_count": rec["price_up_count"],
                "price_down_count": rec["price_down_count"],
                "sold_out_count": rec["sold_out_count"],
                "delay_notice_count": rec["delay_notice_count"],
                "max_abs_price_change_pct": round(rec["max_abs_price_change_pct"], 2),
                "recent_rooms": sorted(rec["recent_rooms"]),
                "recent_event_types": sorted([t for t in rec["recent_event_types"] if t]),
                "pain_points": {
                    "가격급등리스크": price_spike_risk,
                    "반복품절": repeat_sold_out,
                    "공급지연": supply_delay,
                    "옵션혼선": option_confusion,
                    "마진압박후보": margin_pressure,
                },
                "human_summary": sentence,
            }
        )

    change_summary_by_item.sort(
        key=lambda x: (x["sold_out_count"] + x["delay_notice_count"], x["event_count"], x["max_abs_price_change_pct"]),
        reverse=True,
    )

    stock_risk_items = []
    for row in scoped_events:
        if row.get("event_type") not in {"SOLD_OUT", "DELAY_NOTICE"}:
            continue
        risk_level = "HIGH" if row.get("event_type") == "SOLD_OUT" else "MEDIUM"
        risk_reason = "품절 발생" if row.get("event_type") == "SOLD_OUT" else "출고/배송 지연 공지"
        stock_risk_items.append(
            {
                "item": item_label(row),
                "vendor": row.get("vendor"),
                "product_name": row.get("product_name"),
                "event_type": row.get("event_type"),
                "risk_level": risk_level,
                "risk_reason": risk_reason,
                "last_seen_at": row.get("created_at"),
                "room_name": row.get("room_name"),
                "evidence_fields": {
                    "confidence": row.get("confidence"),
                    "stock_status": row.get("stock_status"),
                    "last_seen_at": row.get("created_at"),
                },
            }
        )

    stock_risk_items = stock_risk_items[: min(max(action_limit, 1), 50)]

    action_priority_list = []
    for row in scoped_events[: min(max(action_limit * 3, 10), 150)]:
        event_type = row.get("event_type")
        if event_type not in {"SOLD_OUT", "DELAY_NOTICE", "PRICE_UP", "PRICE_DOWN"}:
            continue
        base = {"SOLD_OUT": 100, "DELAY_NOTICE": 80, "PRICE_UP": 65, "PRICE_DOWN": 45}.get(event_type, 40)
        pe = price_evidence(row)
        price_weight = min(20, int(abs(pe.get("delta_rate_pct", 0)))) if pe and pe.get("delta_rate_pct") is not None else 0
        score = base + price_weight
        if event_type == "SOLD_OUT":
            recommended = "대체 상품 노출/재입고 일정 확인 후 즉시 공지"
            reason = "주문 불가 상태"
        elif event_type == "DELAY_NOTICE":
            recommended = "지연 사유/예상 출고일을 상품 상세와 공지에 반영"
            reason = "고객 CS 증가 위험"
        elif event_type == "PRICE_UP":
            recommended = "마진/경쟁가 비교 후 판매가·프로모션 조정"
            reason = "원가 상승 반영 필요"
        else:
            recommended = "가격 인하 폭 대비 판매량/마진 영향 확인"
            reason = "가격 인하 기회 또는 과도한 할인 점검"

        action_priority_list.append(
            {
                "priority_score": score,
                "event_type": event_type,
                "item": item_label(row),
                "room_name": row.get("room_name"),
                "created_at": row.get("created_at"),
                "reason": reason,
                "recommended_action": recommended,
                "evidence_fields": {
                    "confidence": row.get("confidence"),
                    "old_price": row.get("old_price"),
                    "new_price": row.get("new_price"),
                    "price_delta": (pe or {}).get("delta"),
                    "price_delta_rate_pct": (pe or {}).get("delta_rate_pct"),
                    "last_seen_at": row.get("created_at"),
                },
            }
        )

    action_priority_list.sort(key=lambda x: (x["priority_score"], x["created_at"] or ""), reverse=True)
    action_priority_list = action_priority_list[: min(max(action_limit, 1), 50)]

    recommended_actions = []
    for item in action_priority_list:
        text = f"[{item['event_type']}] {item['item']}: {item['recommended_action']}"
        if text not in recommended_actions:
            recommended_actions.append(text)
    recommended_actions = recommended_actions[: min(max(action_limit, 1), 20)]

    pain_point_candidates = []
    for item in change_summary_by_item:
        pp = item.get("pain_points", {})
        active = [k for k, v in pp.items() if v]
        if not active:
            continue
        pain_point_candidates.append(
            {
                "item": item.get("item"),
                "vendor": item.get("vendor"),
                "product_name": item.get("product_name"),
                "pain_points": active,
                "event_count": item.get("event_count"),
                "last_event_at": item.get("last_event_at"),
            }
        )

    evidence_fields = {
        "window_hours": limit_hours,
        "generated_at": scoped_events[0]["created_at"] if scoped_events else None,
        "event_type_counts": {k: int(v) for k, v in counts.items()},
        "action_item_count": len(action_priority_list),
        "stock_risk_count": len(stock_risk_items),
        "items_with_changes": len(change_summary_by_item),
        "pain_point_candidate_count": len(pain_point_candidates),
    }

    conn.close()
    return {
        "hours": limit_hours,
        "alert_types_order": ALERT_TYPES_ORDER,
        "today_alert_summary": today_alerts,
        "recent_alert_feed": recent_feed,
        "action_required_types": ACTION_REQUIRED_TYPES,
        "action_required_items": action_items,
        # content-focused seller insights
        "action_priority_list": action_priority_list,
        "change_summary_by_item": change_summary_by_item,
        "stock_risk_items": stock_risk_items,
        "pain_point_candidates": pain_point_candidates,
        "recommended_actions": recommended_actions,
        "evidence_fields": evidence_fields,
    }



@app.get("/stats/control-tower")
def stats_control_tower(limit_hours: int = 24):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("select count(*), max(created_at) from messages")
    message_count, last_message_at = cur.fetchone()

    cur.execute(
        """
        select room_name, count(*) c
        from messages
        where datetime(created_at) >= datetime('now', ?)
        group by room_name
        order by c desc
        limit 10
        """,
        (f"-{limit_hours} hours",),
    )
    top_room_traffic = [dict(r) for r in cur.fetchall()]

    cur.execute(
        """
        select reason, count(*) c
        from ingestion_audit
        where datetime(created_at) >= datetime('now', ?)
        group by reason
        order by c desc
        """,
        (f"-{limit_hours} hours",),
    )
    skip_reasons = [dict(r) for r in cur.fetchall()]

    cur.execute(
        """
        select count(*)
        from ingestion_audit
        where datetime(created_at) >= datetime('now', ?)
          and reason like 'error:%'
        """,
        (f"-{limit_hours} hours",),
    )
    error_count = cur.fetchone()[0]

    cur.execute(
        """
        select count(*)
        from events
        where datetime(created_at) >= datetime('now', '-1 hours')
        """
    )
    events_last_hour = cur.fetchone()[0]

    if not last_message_at:
        pipeline_status = "DOWN"
        pipeline_desc = "최근 메시지가 없어 파이프라인 입력을 확인해야 합니다."
    elif events_last_hour == 0:
        pipeline_status = "WARN"
        pipeline_desc = "최근 1시간 이벤트가 없습니다. 수집 또는 파싱 상태를 점검하세요."
    else:
        pipeline_status = "OK"
        pipeline_desc = "최근 1시간 이벤트가 확인되어 파이프라인이 동작 중입니다."

    conn.close()
    return {
        "hours": limit_hours,
        "kpi": {
            "messages": int(message_count or 0),
            "last_message_at": last_message_at,
            "events_last_hour": int(events_last_hour or 0),
            "ingestion_errors": int(error_count or 0),
        },
        "data_quality": {
            "skip_reasons": skip_reasons,
            "error_count": int(error_count or 0),
        },
        "top_room_traffic": top_room_traffic,
        "pipeline_status": {
            "status": pipeline_status,
            "description": pipeline_desc,
        },
    }


def _serve_html(file_name: str):
    html_path = WEB_ROOT / file_name
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return f"<h1>{file_name} not found</h1>"


@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return _serve_html("dashboard.html")


@app.get("/dashboard_v1.html", response_class=HTMLResponse)
def dashboard_v1():
    return _serve_html("dashboard_v1.html")


@app.get("/dashboard_v2.html", response_class=HTMLResponse)
def dashboard_v2():
    return _serve_html("dashboard_v2.html")


@app.get("/dashboard_v3.html", response_class=HTMLResponse)
def dashboard_v3():
    return _serve_html("dashboard_v3.html")


@app.get("/dashboard_v4.html", response_class=HTMLResponse)
def dashboard_v4():
    return _serve_html("dashboard_v4.html")


@app.get("/dashboard_v5.html", response_class=HTMLResponse)
def dashboard_v5():
    return _serve_html("dashboard_v5.html")


@app.get("/admin/control-tower", response_class=HTMLResponse)
def admin_control_tower():
    return _serve_html("admin_control_tower.html")


@app.get("/admin/seller", response_class=HTMLResponse)
def admin_seller():
    return _serve_html("admin_seller.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api:app", host="0.0.0.0", port=8877, reload=False)
