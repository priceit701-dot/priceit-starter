import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple

PRICE_RE = re.compile(r"(?P<price>[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})\s*원")
PRODUCT_PRICE_RE = re.compile(r"[✔🍅\-\s]*([^;\n]+?)\s*;\s*([0-9][0-9,]*)\s*원")
VENDOR_RE = re.compile(r"\[(?P<vendor>[^\]]+)\]")
QUOTED_PRODUCT_RE = re.compile(r"[‘'\"]\s*([^'‘’\"\n]+?)\s*[’'\"]")

UP_KEYWORDS = ["인상", "올랐", "상승", "⬆️", "🔺", "가격인상"]
DOWN_KEYWORDS = ["인하", "내렸", "떨", "할인", "⬇️", "🔻", "가격인하", "특가"]
SOLD_OUT_KEYWORDS = ["품절", "sold out", "솔드아웃", "일시품절", "품절요청", "품절예정"]
RESTOCK_KEYWORDS = ["재입고", "복구", "판매재개", "재개", "입고완료", "재입고완료"]
NEGATIVE_RESTOCK_HINTS = ["입고 지연", "원물 부족", "순차출고", "출고 지연", "배송 지연"]

HEADER_ONLY_PATTERNS = [
    "상품변동 요약",
    "출고 일정 안내",
    "배송안내",
    "발주마감시간 변경",
    "중요공지",
    "발주가이드",
]

DELAY_KEYWORDS = [
    "출고 지연",
    "배송 지연",
    "원물 부족",
    "미출",
    "입고 지연",
    "연휴",
    "순차출고",
    "출고일정",
    "출고 일정",
    "송장 미등록",
    "지연안내",
    "지연 안내",
]

STATUS_NOISE_WORDS = [
    "긴급공지", "중요공지", "공지", "안내", "속보", "알림", "발주", "출고", "배송",
    "품절", "품절예정", "일시품절", "재입고", "판매재개", "가격변동", "가격인상", "가격인하",
    "신규등록", "신규오픈", "신규상품", "입고완료", "적용시기", "특가", "지연", "일정", "요약", "품절안내", "긴급",
]

OPTION_PATTERNS: Dict[str, str] = {
    "weight": r"\b\d+(?:\.\d+)?\s?(?:kg|g|ml|l|리터|포|봉|박스|box|입|단|망|팩|개)\b",
    "grade": r"\b(?:특품|특|상품|상|중|하|A\+?|B|C|프리미엄|로얄|선별|못난이|가정용)\s?(?:급|등급)?\b",
    "origin": r"\b(?:국산|수입|국내산|중국산|미국산|칠레산|페루산|남해|제주|해남|밀양|고랭지|경남|전남|강원)\b",
    "pack": r"\b(?:벌크|소포장|대포장|개별포장|실속형|선물용|박스포장|박스|팩|봉지|진공포장|벌크포장)\b",
    "storage": r"\b(?:냉장|냉동|상온|신선|당일출고|새벽배송|산지직송)\b",
}

BRAND_CANDIDATES = ["팜허브", "쿠팡", "11번가", "G마켓", "옥션", "네이버", "스마트스토어"]

PRODUCT_HINTS = [
    "사과", "배", "감", "딸기", "바나나", "키위", "감귤", "오렌지", "포도", "참외", "토마토",
    "상추", "시금치", "양파", "마늘", "고구마", "감자", "양배추", "오이", "부추", "깻잎", "파", "배추", "버섯",
]


def _load_vendor_aliases():
    p = Path(__file__).resolve().parent.parent / "data" / "vendor_aliases.json"
    if not p.exists():
        return {}, {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        item_aliases = raw.get("__item_aliases__", {}) if isinstance(raw, dict) else {}
        vendor_aliases = {k: v for k, v in raw.items() if isinstance(k, str) and not k.startswith("__")}
        return vendor_aliases, item_aliases
    except Exception:
        return {}, {}


VENDOR_ALIASES, ITEM_ALIASES = _load_vendor_aliases()


@dataclass
class ItemProfile:
    item_name_raw: Optional[str]
    item_name_norm: Optional[str]
    option_tokens: List[str] = field(default_factory=list)
    brand: Optional[str] = None
    grade: Optional[str] = None
    origin: Optional[str] = None
    unit: Optional[str] = None


@dataclass
class ParsedEvent:
    vendor: Optional[str]
    product_name: Optional[str]
    event_type: str
    old_price: Optional[int]
    new_price: Optional[int]
    stock_status: Optional[str]
    confidence: float


def _parse_price(text: str):
    prices = [int(m.group("price").replace(",", "")) for m in PRICE_RE.finditer(text)]
    return prices


def _parse_vendor(text: str):
    m = VENDOR_RE.search(text)
    if m:
        raw = m.group("vendor").strip()
        low = raw.lower()
        for canonical, aliases in VENDOR_ALIASES.items():
            if low == canonical.lower() or any(low == a.lower() for a in aliases):
                return canonical
        return raw

    low_text = text.lower()
    for canonical, aliases in VENDOR_ALIASES.items():
        keys = [canonical] + aliases
        if any(k.lower() in low_text for k in keys):
            return canonical

    if "팜허브" in text:
        return "팜허브"
    return None


def _is_header_like(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if t.startswith("#") and "'" not in t and "‘" not in t and '"' not in t:
        return True
    return any(p in t for p in HEADER_ONLY_PATTERNS)


def _extract_quoted_product(text: str) -> Optional[str]:
    m = QUOTED_PRODUCT_RE.search(text)
    if m:
        product = m.group(1).strip()
        if product and len(product) > 1:
            return product
    return None


def _strip_status_noise(text: str) -> str:
    s = text
    s = re.sub(r"\[[^\]]*(공지|안내|품절|지연|긴급)[^\]]*\]", " ", s)
    s = re.sub(r"^[#📌🔔⭐🚨✅⚠️\s]+", "", s)
    for w in STATUS_NOISE_WORDS:
        s = s.replace(w, " ")
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"\d[\d,]*\s*원", " ", s)
    s = re.sub(r"[(){}<>|]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -:/")
    return s


def _normalize_option_token(category: str, token: str) -> str:
    t = token.strip()
    if category == "weight":
        t = re.sub(r"\s+", "", t)
        t = t.replace("리터", "L").replace("l", "L")
    elif category == "grade":
        t = t.replace("등급", "").replace("급", "")
        t = t.upper() if t.lower() in {"a", "a+", "b", "c"} else t
        grade_map = {
            "특": "특", "특품": "특", "상": "상", "상품": "상", "중": "중", "하": "하",
            "A": "A", "A+": "A+", "B": "B", "C": "C", "프리미엄": "프리미엄", "로얄": "로얄",
            "선별": "선별", "못난이": "못난이", "가정용": "가정용",
        }
        t = grade_map.get(t, t)
    elif category == "origin":
        t = t.replace("국내산", "국산")
    elif category == "pack":
        pack_map = {"box": "박스", "박스포장": "박스", "벌크포장": "벌크"}
        t = pack_map.get(t.lower(), t)
    return f"{category}:{t}"


def _extract_option_tokens(text: str) -> List[str]:
    found: List[Tuple[int, str]] = []
    cat_order = ["weight", "grade", "origin", "pack", "storage"]
    for idx, category in enumerate(cat_order):
        pattern = OPTION_PATTERNS[category]
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            token = _normalize_option_token(category, m.group(0))
            found.append((idx, token))
    seen = set()
    out: List[str] = []
    for _, t in sorted(found, key=lambda x: x[0]):
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _normalize_item_name(name: str) -> str:
    n = name.strip()
    for src, dst in ITEM_ALIASES.items():
        n = re.sub(re.escape(src), dst, n, flags=re.IGNORECASE)
    n = re.sub(r"\b(?:가격|즉시|대폭|인상|인하|변동|안내|공지|요청|예정|재개|판매|옵션추가|신규옵션|추가)\b", " ", n)
    n = re.sub(r"\b(?:특품|특|A\+?|B|C|상|중|하|프리미엄|로얄|선별|못난이|가정용)\s*급\b", " ", n, flags=re.IGNORECASE)
    n = re.sub(r"\b품\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip(" -:/")
    return n


def _pick_brand(text: str) -> Optional[str]:
    low = text.lower()
    for b in BRAND_CANDIDATES:
        if b.lower() in low:
            return b
    return None


def _pick_first(pattern: str, text: str) -> Optional[str]:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return m.group(0).strip() if m else None


def _line_score(line: str) -> int:
    score = 0
    if QUOTED_PRODUCT_RE.search(line):
        score += 5
    if PRODUCT_PRICE_RE.search(line):
        score += 5
    if any(h in line for h in PRODUCT_HINTS):
        score += 3
    if re.search(OPTION_PATTERNS["weight"], line, flags=re.IGNORECASE):
        score += 2
    if re.search(r"[가-힣]{2,}", line):
        score += 2
    if any(w in line for w in STATUS_NOISE_WORDS):
        score -= 2
    if any(h in line for h in HEADER_ONLY_PATTERNS):
        score -= 5
    return score


def _extract_best_candidate(text: str) -> Optional[str]:
    lines = [ln.strip() for ln in re.split(r"[\n•·]", text) if ln.strip()]
    if not lines:
        return None
    scored = sorted((( _line_score(ln), ln) for ln in lines), key=lambda x: x[0], reverse=True)
    best = scored[0][1] if scored and scored[0][0] >= 1 else None
    return best


def extract_item_profile(text: str, vendor: Optional[str] = None) -> ItemProfile:
    quoted = _extract_quoted_product(text)
    raw = None
    if quoted:
        raw = quoted
    else:
        mpp = PRODUCT_PRICE_RE.search(text)
        if mpp:
            raw = mpp.group(1).strip()

    if not raw:
        bracket = re.search(r"\[([^\]]+)\]", text)
        if bracket:
            btxt = bracket.group(1).strip()
            vendor_like = any(btxt.lower() == k.lower() or any(btxt.lower() == a.lower() for a in v) for k, v in VENDOR_ALIASES.items())
            if not vendor_like:
                cleaned_btxt = _strip_status_noise(btxt)
                if re.search(r"[가-힣]{2,}", cleaned_btxt):
                    raw = cleaned_btxt

    if not raw:
        best_line = _extract_best_candidate(text)
        if best_line:
            raw = _strip_status_noise(best_line)

    if not raw:
        cleaned = re.sub(r"\[[^\]]+\]", " ", text)
        raw = _strip_status_noise(cleaned)

    raw = raw[:80] if raw else None
    if raw and _is_header_like(raw):
        raw = None

    if raw:
        option_tokens = _extract_option_tokens(raw)
        name_wo_options = raw
        for tok in option_tokens:
            _, val = tok.split(":", 1)
            name_wo_options = re.sub(re.escape(val), " ", name_wo_options, flags=re.IGNORECASE)
        name_wo_options = re.sub(r"\b(?:신규|옵션|전옵션|즉시대폭|가격)\b", " ", name_wo_options)
        name_wo_options = re.sub(r"\s+", " ", name_wo_options).strip(" -:/")
        item_name_norm = _normalize_item_name(name_wo_options or raw)
    else:
        option_tokens = []
        item_name_norm = None

    grade = _pick_first(OPTION_PATTERNS["grade"], raw or "")
    origin = _pick_first(OPTION_PATTERNS["origin"], raw or "")
    unit = _pick_first(OPTION_PATTERNS["weight"], raw or "")

    return ItemProfile(
        item_name_raw=raw,
        item_name_norm=item_name_norm,
        option_tokens=option_tokens,
        brand=vendor or _pick_brand(text),
        grade=grade,
        origin=origin,
        unit=unit,
    )


def _parse_product(text: str):
    profile = extract_item_profile(text)
    return profile.item_name_norm or profile.item_name_raw


def parse_message(text: str) -> Optional[ParsedEvent]:
    lower = text.lower()
    vendor = _parse_vendor(text)
    profile = extract_item_profile(text, vendor=vendor)
    product_name = profile.item_name_norm or profile.item_name_raw
    prices = _parse_price(text)

    if "님이 들어왔습니다" in text or "님이 나갔습니다" in text:
        return None
    if "환영합니다 대표님" in text or "오픈채팅봇" in text:
        return None

    if any(k in text for k in DELAY_KEYWORDS):
        return ParsedEvent(vendor, product_name, "DELAY_NOTICE", None, None, None, 0.93)

    if any(k in text for k in SOLD_OUT_KEYWORDS) or any(k in lower for k in SOLD_OUT_KEYWORDS):
        return ParsedEvent(vendor, product_name, "SOLD_OUT", None, None, "SOLD_OUT", 0.92)
    if ("대량발주" in text and "불가" in text) or ("수급" in text and "어려" in text):
        return ParsedEvent(vendor, product_name, "NOTICE", None, None, "RISK", 0.86)

    if (any(k in text for k in RESTOCK_KEYWORDS) or any(k in lower for k in RESTOCK_KEYWORDS)) and not any(
        hint in text for hint in NEGATIVE_RESTOCK_HINTS
    ):
        return ParsedEvent(vendor, product_name, "RESTOCK", None, None, "IN_STOCK", 0.90)

    if any(k in text for k in ["신규상품", "신규등록", "신규오픈", "신규옵션", "전격 오픈", "new"]):
        if len(prices) == 1:
            return ParsedEvent(vendor, product_name, "NEW_ITEM", None, prices[0], None, 0.90)
        return ParsedEvent(vendor, product_name, "NEW_ITEM", None, None, None, 0.82)

    mpp = PRODUCT_PRICE_RE.search(text)
    if mpp:
        p_name = _normalize_item_name(mpp.group(1).strip())
        p_price = int(mpp.group(2).replace(",", ""))
        et = "NEW_ITEM" if ("신상품" in text or "신규" in text) else "PRICE_SEEN"
        return ParsedEvent(vendor, p_name, et, None, p_price, None, 0.95)

    if text.strip().startswith("#가격인상"):
        return ParsedEvent(vendor, product_name, "PRICE_UP", None, prices[0] if prices else None, None, 0.88)
    if text.strip().startswith("#가격인하"):
        return ParsedEvent(vendor, product_name, "PRICE_DOWN", None, prices[0] if prices else None, None, 0.88)
    if text.strip().startswith("#가격변동"):
        if any(k in text for k in ["인상", "⬆️", "🔺"]):
            return ParsedEvent(vendor, product_name, "PRICE_UP", None, prices[0] if prices else None, None, 0.84)
        if any(k in text for k in ["인하", "⬇️", "🔻", "특가"]):
            return ParsedEvent(vendor, product_name, "PRICE_DOWN", None, prices[0] if prices else None, None, 0.84)

    if "가격변동" in text or "단가반영" in text or "적용시기" in text:
        has_up = any(k in text for k in ["인상", "⬆️", "🔺"])
        has_down = any(k in text for k in ["인하", "⬇️", "🔻", "특가"])
        if has_up and not has_down:
            return ParsedEvent(vendor, product_name, "PRICE_UP", None, prices[0] if prices else None, None, 0.84)
        if has_down and not has_up:
            return ParsedEvent(vendor, product_name, "PRICE_DOWN", None, prices[0] if prices else None, None, 0.84)

    if any(k in text for k in UP_KEYWORDS):
        if len(prices) >= 2:
            return ParsedEvent(vendor, product_name, "PRICE_UP", prices[-2], prices[-1], None, 0.88)
        if len(prices) == 1:
            return ParsedEvent(vendor, product_name, "PRICE_UP", None, prices[0], None, 0.72)
        return ParsedEvent(vendor, product_name, "PRICE_UP", None, None, None, 0.72)

    if any(k in text for k in DOWN_KEYWORDS):
        if len(prices) >= 2:
            return ParsedEvent(vendor, product_name, "PRICE_DOWN", prices[-2], prices[-1], None, 0.88)
        if len(prices) == 1:
            return ParsedEvent(vendor, product_name, "PRICE_DOWN", None, prices[0], None, 0.72)
        return ParsedEvent(vendor, product_name, "PRICE_DOWN", None, None, None, 0.72)

    if "공지" in text or "안내" in text or "알림" in text or "일일공지" in text:
        return ParsedEvent(vendor, product_name, "NOTICE", None, None, None, 0.74)

    if len(prices) == 1:
        return ParsedEvent(vendor, product_name, "NOTICE", None, prices[0], None, 0.55)

    return None
