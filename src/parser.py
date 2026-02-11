import json
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

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


def _load_vendor_aliases():
    p = Path(__file__).resolve().parent.parent / "data" / "vendor_aliases.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


VENDOR_ALIASES = _load_vendor_aliases()


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


def _parse_product(text: str):
    quoted = _extract_quoted_product(text)
    if quoted:
        return quoted

    if _is_header_like(text):
        return None

    bracket = re.search(r"\[([^\]]+)\]", text)
    if bracket:
        b = bracket.group(1).strip()
        b = re.sub(r"(안내|공지|예정|요약)$", "", b).strip(" :-")
        b = re.sub(r"(가격인상|가격인하|가격변동|출고지연|품절예정)", "", b).strip(" :-")
        if b and len(b) > 1 and b not in {"가격인상", "가격인하", "가격변동"}:
            return b

    cleaned = re.sub(r"\[[^\]]+\]", "", text)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"^[#📌🔔⭐🚨\s]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:")
    if not cleaned or _is_header_like(cleaned):
        return None
    return cleaned[:60]


def parse_message(text: str) -> Optional[ParsedEvent]:
    lower = text.lower()
    vendor = _parse_vendor(text)
    product_name = _parse_product(text)
    prices = _parse_price(text)

    # hard noise guard (import/collector 보조 안전장치)
    if "님이 들어왔습니다" in text or "님이 나갔습니다" in text:
        return None
    if "환영합니다 대표님" in text or "오픈채팅봇" in text:
        return None

    # Delay / logistics notices
    if any(k in text for k in DELAY_KEYWORDS):
        return ParsedEvent(vendor, product_name, "DELAY_NOTICE", None, None, None, 0.93)

    # Explicit sold-out / risk
    if any(k in text for k in SOLD_OUT_KEYWORDS) or any(k in lower for k in SOLD_OUT_KEYWORDS):
        return ParsedEvent(vendor, product_name, "SOLD_OUT", None, None, "SOLD_OUT", 0.92)
    if ("대량발주" in text and "불가" in text) or ("수급" in text and "어려" in text):
        return ParsedEvent(vendor, product_name, "SOLD_OUT_RISK", None, None, "RISK", 0.86)

    # Restock / resume
    if (any(k in text for k in RESTOCK_KEYWORDS) or any(k in lower for k in RESTOCK_KEYWORDS)) and not any(
        hint in text for hint in NEGATIVE_RESTOCK_HINTS
    ):
        return ParsedEvent(vendor, product_name, "RESTOCK", None, None, "IN_STOCK", 0.90)

    # 신규상품/신규등록
    if any(k in text for k in ["신규상품", "신규등록", "신규오픈", "신규옵션", "전격 오픈", "new"]):
        if len(prices) == 1:
            return ParsedEvent(vendor, product_name, "NEW_ITEM", None, prices[0], None, 0.90)
        return ParsedEvent(vendor, product_name, "NEW_ITEM", None, None, None, 0.82)

    # Structured product line: "상품명 ; 11,700원"
    mpp = PRODUCT_PRICE_RE.search(text)
    if mpp:
        p_name = mpp.group(1).strip()
        p_price = int(mpp.group(2).replace(",", ""))
        et = "NEW_ITEM" if ("신상품" in text or "신규" in text) else "PRICE_SEEN"
        return ParsedEvent(vendor, p_name, et, None, p_price, None, 0.95)

    # 팜허브 공지 헤더형 키워드
    if text.strip().startswith("#가격인상"):
        return ParsedEvent(vendor, product_name, "PRICE_UP", None, prices[0] if prices else None, None, 0.88)
    if text.strip().startswith("#가격인하"):
        return ParsedEvent(vendor, product_name, "PRICE_DOWN", None, prices[0] if prices else None, None, 0.88)
    if text.strip().startswith("#가격변동"):
        if any(k in text for k in ["인상", "⬆️", "🔺"]):
            return ParsedEvent(vendor, product_name, "PRICE_UP", None, prices[0] if prices else None, None, 0.84)
        if any(k in text for k in ["인하", "⬇️", "🔻", "특가"]):
            return ParsedEvent(vendor, product_name, "PRICE_DOWN", None, prices[0] if prices else None, None, 0.84)

    # 가격 변동 헤더
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

    # Generic notice
    if "공지" in text or "안내" in text or "알림" in text or "일일공지" in text:
        return ParsedEvent(vendor, product_name, "NOTICE", None, None, None, 0.74)

    if len(prices) == 1:
        return ParsedEvent(vendor, product_name, "PRICE_SEEN", None, prices[0], None, 0.55)

    return None
