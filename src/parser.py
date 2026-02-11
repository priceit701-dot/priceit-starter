import json
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

PRICE_RE = re.compile(r"(?P<price>[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})\s*원")
PRODUCT_PRICE_RE = re.compile(r"[✔🍅\-\s]*([^;\n]+?)\s*;\s*([0-9][0-9,]*)\s*원")
VENDOR_RE = re.compile(r"\[(?P<vendor>[^\]]+)\]")

UP_KEYWORDS = ["인상", "올랐", "상승"]
DOWN_KEYWORDS = ["인하", "내렸", "떨", "할인"]
SOLD_OUT_KEYWORDS = ["품절", "sold out", "솔드아웃"]
RESTOCK_KEYWORDS = ["재입고", "입고", "복구"]


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
    return None


def _parse_product(text: str):
    cleaned = re.sub(r"\[[^\]]+\]", "", text)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # first 50 chars as MVP product hint
    return cleaned[:50] if cleaned else None


def parse_message(text: str) -> Optional[ParsedEvent]:
    lower = text.lower()
    vendor = _parse_vendor(text)
    product_name = _parse_product(text)
    prices = _parse_price(text)

    # Notice / delay style announcements
    if "공지" in text or "일일공지" in text:
        if "원물 부족" in text or "출고" in text or "소요" in text:
            return ParsedEvent(vendor, product_name, "DELAY_NOTICE", None, None, None, 0.93)
        return ParsedEvent(vendor, product_name, "NOTICE", None, None, None, 0.75)

    # Structured product line: "상품명 ; 11,700원"
    mpp = PRODUCT_PRICE_RE.search(text)
    if mpp:
        p_name = mpp.group(1).strip()
        p_price = int(mpp.group(2).replace(",", ""))
        et = "NEW_ITEM" if ("신상품" in text or "전격 오픈" in text) else "PRICE_SEEN"
        return ParsedEvent(vendor, p_name, et, None, p_price, None, 0.95)

    if any(k in text for k in SOLD_OUT_KEYWORDS) or any(k in lower for k in SOLD_OUT_KEYWORDS):
        return ParsedEvent(vendor, product_name, "SOLD_OUT", None, None, "SOLD_OUT", 0.92)

    if "원물 부족" in text or "대량발주" in text and "불가" in text:
        return ParsedEvent(vendor, product_name, "SOLD_OUT_RISK", None, None, "RISK", 0.86)

    if any(k in text for k in RESTOCK_KEYWORDS) or any(k in lower for k in RESTOCK_KEYWORDS):
        return ParsedEvent(vendor, product_name, "RESTOCK", None, None, "IN_STOCK", 0.90)

    if "🔺인상" in text:
        return ParsedEvent(vendor, product_name, "PRICE_UP", None, prices[0] if prices else None, None, 0.84)

    if "🔽인하" in text or "슈퍼특가" in text:
        return ParsedEvent(vendor, product_name, "PRICE_DOWN", None, prices[0] if prices else None, None, 0.84)

    if any(k in text for k in UP_KEYWORDS):
        if len(prices) >= 2:
            return ParsedEvent(vendor, product_name, "PRICE_UP", prices[-2], prices[-1], None, 0.88)
        if len(prices) == 1:
            return ParsedEvent(vendor, product_name, "PRICE_UP", None, prices[0], None, 0.72)

    if any(k in text for k in DOWN_KEYWORDS):
        if len(prices) >= 2:
            return ParsedEvent(vendor, product_name, "PRICE_DOWN", prices[-2], prices[-1], None, 0.88)
        if len(prices) == 1:
            return ParsedEvent(vendor, product_name, "PRICE_DOWN", None, prices[0], None, 0.72)

    if len(prices) == 1:
        return ParsedEvent(vendor, product_name, "PRICE_SEEN", None, prices[0], None, 0.55)

    return None
