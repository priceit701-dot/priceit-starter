from typing import Optional
from pathlib import Path
from collections import defaultdict, deque
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
    "상품별", "상품", "최고집", "전국", "1위", "전국1위",
]

PRODUCT_KEYWORDS = [
    "사과", "부사", "감귤", "딸기", "토마토", "감자", "고구마", "양파", "마늘", "오이",
    "상추", "시금치", "구좌당근", "당근", "키위", "쌀", "잡곡", "아몬드", "호두", "버즈", "애플워치",
]


SELLER_KEYWORD_STOPWORDS = {
    "상품", "상품별", "공지", "안내", "긴급", "최고집", "팜허브", "전국", "전국1위", "특가", "신상품", "배송",
}


def _load_seller_product_keywords() -> list[str]:
    catalog_path = Path(__file__).resolve().parent.parent / "data" / "seller_product_catalog_20260212.json"
    if not catalog_path.exists():
        return []
    try:
        import json

        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        kws = payload.get("keywords") or []
        out = []
        for k in kws:
            s = str(k).strip()
            if not s or len(s) < 2:
                continue
            ns = re.sub(r"[^0-9a-z가-힣]", "", s.lower())
            if not ns or s in SELLER_KEYWORD_STOPWORDS:
                continue
            if any(sw in s for sw in ["공지", "안내", "배송", "출고", "긴급", "마감"]):
                continue
            out.append(s)
        return out
    except Exception:
        return []


_PRODUCT_KEYWORDS_SELLER = _load_seller_product_keywords()
if _PRODUCT_KEYWORDS_SELLER:
    PRODUCT_KEYWORDS = sorted(set(PRODUCT_KEYWORDS + _PRODUCT_KEYWORDS_SELLER), key=lambda x: (-len(x), x))


def _norm_for_match(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^0-9a-z가-힣]", "", s)
    return s


_PRODUCT_KEYWORD_NORM_MAP = {}
for kw in PRODUCT_KEYWORDS:
    nk = _norm_for_match(kw)
    if nk and nk not in _PRODUCT_KEYWORD_NORM_MAP:
        _PRODUCT_KEYWORD_NORM_MAP[nk] = kw


def _load_seller_terms_map() -> dict[str, str]:
    p = Path(__file__).resolve().parent.parent / "data" / "seller_product_terms_20260212.json"
    if not p.exists():
        return {}
    try:
        import json

        obj = json.loads(p.read_text(encoding="utf-8"))
        terms = obj.get("terms") or {}
        out = {}
        for k, v in terms.items():
            nk = _norm_for_match(str(k))
            vv = str(v).strip()
            if nk and vv:
                out[nk] = vv
        return out
    except Exception:
        return {}


_SELLER_TERMS_MAP = _load_seller_terms_map()

ROOM_CONTEXT_WINDOW = 5
ROOM_CONTEXT_ELIGIBLE_TYPES = {"SOLD_OUT", "DELAY_NOTICE", "NOTICE", "PRICE_UP", "PRICE_DOWN", "RESTOCK"}
NOTICE_BLOCK_PATTERNS = [
    r"^\s*[#📢📌🔔🚨⚠️⭐️✨🔥]+\s*(?:긴급|중요)?\s*(?:공지|안내|알림|배송|출고|발주)",
    r"^\s*(?:긴급|중요)?\s*(?:공지|안내|알림|배송|출고|발주)",
    r"\b(?:필독|마감|전달사항|배송안내|출고안내|공지사항)\b",
]

STATUS_TOKENS = ["입고", "재입고", "출고", "품절", "일시품절", "가격변동", "가격인상", "가격인하", "인상", "인하"]


def _looks_like_notice_header(s: str) -> bool:
    t = _clean_text(s)
    if not t:
        return True
    for pat in NOTICE_BLOCK_PATTERNS:
        if re.search(pat, t, flags=re.IGNORECASE):
            return True
    emoji_hits = len(re.findall(r"[📢📌🔔🚨⚠️⭐✨🔥]", t))
    if emoji_hits >= 2 and not any(pk in t for pk in PRODUCT_KEYWORDS):
        return True
    return False


def _load_catalog_item_candidates() -> list[str]:
    catalog_path = Path(__file__).resolve().parent.parent / "data" / "seller_product_catalog_20260212.json"
    if not catalog_path.exists():
        return []
    try:
        import json

        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        out = set()
        for row in payload.get("base_name_top100") or []:
            nm = str((row or {}).get("name") or "").strip()
            if nm:
                out.add(nm)
        for nm in payload.get("keywords") or []:
            s = str(nm or "").strip()
            if not s:
                continue
            s = re.sub(r"\[[^\]]+\]", " ", s)
            s = re.sub(r"\([^\)]*\)", " ", s)
            s = re.sub(r"\b\d+(?:\.\d+)?\s*(?:kg|g|ml|l|L|개|입|팩|봉|박스|과)\b", " ", s)
            s = re.sub(r"\b(?:세트|선물세트|가정용|정품|특품|상품|일반|혼합과|중과|대과|소과|중소과|중대과)\b", " ", s)
            s = re.sub(r"\s+", " ", s).strip(" -:/")
            if len(s) >= 2:
                out.add(s)
        cleaned = []
        for s in out:
            if any(sw in s for sw in ["공지", "안내", "출고", "배송", "발주", "가격변동"]):
                continue
            cleaned.append(s)
        return sorted(cleaned, key=lambda x: (-len(x), x))
    except Exception:
        return []


CATALOG_ITEM_CANDIDATES = _load_catalog_item_candidates()
_CATALOG_ITEM_NORM_MAP = {}
for item in CATALOG_ITEM_CANDIDATES:
    ni = _norm_for_match(item)
    if ni and ni not in _CATALOG_ITEM_NORM_MAP:
        _CATALOG_ITEM_NORM_MAP[ni] = item


def _is_noise_item_name(value: Optional[str]) -> bool:
    s = _clean_text(value)
    if not s:
        return True
    if _looks_like_notice_header(s):
        return True
    if len(s) <= 2:
        return True
    if re.fullmatch(r"[\W_]+", s):
        return True
    if re.match(r"^\d{1,2}월\s*\d{1,2}일", s):
        return True
    if any(x in s for x in ["드립니다", "확인", "마감", "흐름", "관련", "사고", "연휴", "됩니다", "필독"]):
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


def _extract_catalog_item_from_text(message_text: Optional[str]) -> Optional[str]:
    s = _clean_text(message_text)
    if not s:
        return None
    ns = _norm_for_match(s)
    if not ns:
        return None
    best = None
    best_len = 0
    for ni, item in _CATALOG_ITEM_NORM_MAP.items():
        if ni and ni in ns and len(ni) > best_len:
            best = item
            best_len = len(ni)
    return best


def _extract_template_item_from_text(message_text: Optional[str]) -> Optional[str]:
    s = _clean_text(message_text)
    if not s:
        return None
    patterns = [
        r"(?:\d{1,2}월\s*\d{1,2}일\s*)?(?:\[[^\]]+\]\s*)?(?P<item>[가-힣A-Za-z][가-힣A-Za-z0-9\s]{1,24}?)\s*(?:재입고|입고|출고|품절|일시품절)",
        r"(?:\[[^\]]+\]\s*)?(?P<item>[가-힣A-Za-z][가-힣A-Za-z0-9\s]{1,24}?)\s*(?:가격\s*변동|가격\s*인상|가격\s*인하|인상|인하)",
    ]
    for pat in patterns:
        m = re.search(pat, s)
        if not m:
            continue
        cand = re.sub(r"\s+", " ", (m.group("item") or "")).strip(" -:/")
        if not cand:
            continue
        if any(tok in cand for tok in STATUS_TOKENS):
            continue
        if _is_noise_item_name(cand):
            continue
        if any(pk in cand for pk in PRODUCT_KEYWORDS):
            return cand
        catalog_hit = _extract_catalog_item_from_text(cand)
        if catalog_hit:
            return catalog_hit
        if re.search(r"[가-힣]{2,}", cand):
            return cand
    return None


def _extract_market_item_from_text(message_text: Optional[str]) -> Optional[str]:
    s = _clean_text(message_text)
    if not s:
        return None

    if _looks_like_notice_header(s):
        return None

    # 1) 원문 포함 매칭 (긴 키워드 우선)
    s_plain = re.sub(r"[\[\]{}()<>|]", " ", s)
    s_plain = re.sub(r"\s+", " ", s_plain)
    for kw in PRODUCT_KEYWORDS:
        if kw and kw in s_plain:
            return kw

    # 2) 판매중 상품리스트(term map) 정규화 매칭 우선
    ns = _norm_for_match(s)
    if ns and _SELLER_TERMS_MAP:
        best = None
        best_len = 0
        for nkw, canonical in _SELLER_TERMS_MAP.items():
            if nkw and nkw in ns and len(nkw) > best_len:
                best = canonical
                best_len = len(nkw)
        if best:
            return best

    # 3) seller catalog normalize 매칭
    cat = _extract_catalog_item_from_text(s)
    if cat:
        return cat

    # 4) 일반 키워드 정규화 매칭 (공백/슬래시/특수문자 제거)
    if ns:
        best = None
        best_len = 0
        for nkw, kw in _PRODUCT_KEYWORD_NORM_MAP.items():
            if nkw and nkw in ns and len(nkw) > best_len:
                best = kw
                best_len = len(nkw)
        if best:
            return best

    # 5) 팜허브 빈출 템플릿 매핑 (입고/출고/품절/가격변동)
    tmpl = _extract_template_item_from_text(s)
    if tmpl and not _is_noise_item_name(tmpl):
        return tmpl

    # 6) 농산물 패턴 fallback (예: 제주 구좌당근 입고)
    m = re.search(r"([가-힣]{2,12})(?:\s*(?:입고|품절|인상|인하|출고|지연))", s)
    if m:
        cand = m.group(1)
        if cand and not _is_noise_item_name(cand):
            return cand

    return None


def _sanitize_item_candidate(value: Optional[str]) -> str:
    s = _clean_text(value)
    if not s:
        return ""
    s = re.sub(r"^[#📢📌🔔🚨⚠️⭐✨🔥\-\s]+", "", s)
    s = re.sub(r"\s+", " ", s).strip(" -:/")
    return s


def _best_item_name(product_name: Optional[str], profile_item_name: Optional[str], vendor: Optional[str], message_text: Optional[str] = None) -> tuple[str, str]:
    p = _sanitize_item_candidate(re.sub(r"\[[^\]]+\]", "", _clean_text(product_name)).strip())
    prof = _sanitize_item_candidate(re.sub(r"\[[^\]]+\]", "", _clean_text(profile_item_name)).strip())
    v = _sanitize_item_candidate(vendor)

    if prof and not _is_noise_item_name(prof):
        return prof, "profile"
    if p and not _is_noise_item_name(p):
        return p, "product_name"

    extracted = _sanitize_item_candidate(_extract_market_item_from_text(message_text))
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

    # 룸 문맥 기반 상품명 복원: 최근 N건 명시 상품 후보를 관리해 공지형/상태형 문구에 안전하게 상속
    scoped_events_chrono = sorted(scoped_events, key=lambda x: (x.get("created_at") or "", x.get("id") or 0))
    room_recent_named_items = defaultdict(lambda: deque(maxlen=ROOM_CONTEXT_WINDOW))
    resolved_item_name_by_event_id = {}
    for ev in scoped_events_chrono:
        item_fields = _extract_item_fields(ev.get("message_text"), vendor=ev.get("vendor"))
        best_name, source = _best_item_name(ev.get("product_name"), item_fields.get("item_name"), ev.get("vendor"), ev.get("message_text"))
        room = ev.get("room_name") or ""
        et = ev.get("event_type") or ""
        msg = _clean_text(ev.get("message_text"))

        is_explicit_name = best_name != "미분류 상품" and source in {"profile", "product_name", "message_keyword"}
        if is_explicit_name and not _is_noise_item_name(best_name):
            dq = room_recent_named_items[room]
            if best_name in dq:
                dq.remove(best_name)
            dq.appendleft(best_name)

        needs_context = best_name == "미분류 상품" or _looks_like_notice_header(msg)
        if needs_context and et in ROOM_CONTEXT_ELIGIBLE_TYPES:
            # 같은 메시지 내 템플릿 후보(입고/출고/품절/가격변동) 우선
            tmpl = _extract_template_item_from_text(msg)
            if tmpl and not _is_noise_item_name(tmpl):
                best_name = tmpl
                source = "template"
            else:
                # 최근 N건에서 가장 최근 명시 상품 상속
                recent = room_recent_named_items.get(room) or []
                inherited = next((x for x in recent if x and not _is_noise_item_name(x)), None)
                if inherited:
                    best_name = inherited
                    source = "room_context_recent"

        if best_name != "미분류 상품" and not _is_noise_item_name(best_name):
            dq = room_recent_named_items[room]
            if best_name in dq:
                dq.remove(best_name)
            dq.appendleft(best_name)

        resolved_item_name_by_event_id[ev.get("id")] = {"item_name": best_name, "source": source}

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
        rid = row.get("id")
        if rid in resolved_item_name_by_event_id:
            return resolved_item_name_by_event_id[rid]["item_name"]
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
