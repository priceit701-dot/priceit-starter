from dataclasses import dataclass
from typing import Optional, List, Tuple
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.parser import parse_message


PRICE_RE = re.compile(r"(?P<price>[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})\s*원")
UP_KEYWORDS = ["인상", "올랐", "상승", "⬆️", "🔺", "가격인상"]
DOWN_KEYWORDS = ["인하", "내렸", "떨", "할인", "⬇️", "🔻", "가격인하", "특가"]
SOLD_OUT_KEYWORDS = ["품절", "sold out", "솔드아웃", "일시품절", "품절요청"]
RESTOCK_KEYWORDS = ["재입고", "입고", "복구", "판매재개", "재개"]

TARGET = {"PRICE_UP", "PRICE_DOWN", "NEW_ITEM", "SOLD_OUT", "DELAY_NOTICE"}


@dataclass
class ParsedEvent:
    event_type: str


def old_parse_message(text: str) -> Optional[ParsedEvent]:
    lower = text.lower()
    prices = [int(m.group("price").replace(",", "")) for m in PRICE_RE.finditer(text)]

    if "님이 들어왔습니다" in text or "님이 나갔습니다" in text:
        return None
    if "환영합니다 대표님" in text or "오픈채팅봇" in text:
        return None

    if any(k in text for k in ["출고 지연", "배송 지연", "원물 부족", "미출", "입고 지연", "연휴"]):
        return ParsedEvent("DELAY_NOTICE")

    if any(k in text for k in SOLD_OUT_KEYWORDS) or any(k in lower for k in SOLD_OUT_KEYWORDS):
        return ParsedEvent("SOLD_OUT")
    if ("대량발주" in text and "불가" in text) or ("수급" in text and "어려" in text):
        return ParsedEvent("SOLD_OUT_RISK")

    if any(k in text for k in RESTOCK_KEYWORDS) or any(k in lower for k in RESTOCK_KEYWORDS):
        return ParsedEvent("RESTOCK")

    if any(k in text for k in ["신규상품", "신규등록", "전격 오픈", "new"]):
        return ParsedEvent("NEW_ITEM")

    if "가격변동" in text or "단가반영" in text or "적용시기" in text:
        has_up = any(k in text for k in ["인상", "⬆️", "🔺"])
        has_down = any(k in text for k in ["인하", "⬇️", "🔻", "특가"])
        if has_up and not has_down:
            return ParsedEvent("PRICE_UP")
        if has_down and not has_up:
            return ParsedEvent("PRICE_DOWN")

    if any(k in text for k in UP_KEYWORDS):
        return ParsedEvent("PRICE_UP")

    if any(k in text for k in DOWN_KEYWORDS):
        return ParsedEvent("PRICE_DOWN")

    if len(prices) == 1:
        return ParsedEvent("PRICE_SEEN")

    return None


def score(samples: List[Tuple[str, Optional[str]]], parser_func):
    tp = fp = fn = 0
    for text, gold in samples:
        pred_obj = parser_func(text)
        pred = pred_obj.event_type if pred_obj else None

        gold_is_target = gold in TARGET
        pred_is_target = pred in TARGET

        if gold_is_target and pred == gold:
            tp += 1
        elif not gold_is_target and pred_is_target:
            fp += 1
        elif gold_is_target and pred != gold:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def main():
    # (메시지, 정답 이벤트)
    samples = [
        ("#가격인상", "PRICE_UP"),
        ("#가격인하/옵션추가", "PRICE_DOWN"),
        ("#가격변동 *재공지", None),
        ("[청도반시 전옵션 가격 즉시대폭인하]", "PRICE_DOWN"),
        ("[골드키위 대왕점보 옵션 가격인상 안내]", "PRICE_UP"),
        ("📌신규상품 'A급 남해 보물초 시금치'", "NEW_ITEM"),
        ("📌신규상품 '정품 감말랭이'", "NEW_ITEM"),
        ("#신규오픈", "NEW_ITEM"),
        ("[정품 홍로 신규상품 안내]", "NEW_ITEM"),
        ("[명품나주배선물세트 품절예정 안내]", "SOLD_OUT"),
        ("[품절 안내] 샤인머스켓 특품", "SOLD_OUT"),
        ("[과일선물세트 출고지연안내]", "DELAY_NOTICE"),
        ("팜허브 내일부터 순차출고 재개합니다", "DELAY_NOTICE"),
        ("금일 발송건 송장 등록 완료입니다. 송장번호 미등록건 익일부터 순차출고 예정입니다.", "DELAY_NOTICE"),
        ("🔔 09/22(월) 팜허브 상품변동 요약", None),
        ("📌 팜허브 '시나노골드'", None),
        ("오늘 입고된 a급 가정용 홍로사과입니다", None),
        ("단가 130,000원으로 오기입된게 있어 다시 올려드립니다", None),
        ("[출고 일정 안내]", "DELAY_NOTICE"),
        ("#9/12_팜허브신규변동알림", None),
    ]

    before = score(samples, old_parse_message)

    def new_adapter(text):
        p = parse_message(text)
        if not p:
            return None
        return ParsedEvent(p.event_type)

    after = score(samples, new_adapter)

    print("=== Parser Target Event Benchmark (Farmhub notice style) ===")
    print("samples:", len(samples))
    print("before:", before)
    print("after :", after)


if __name__ == "__main__":
    main()
