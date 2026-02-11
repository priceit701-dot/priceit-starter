import unittest

from src.parser import parse_message


class ParserRuleTests(unittest.TestCase):
    def test_price_up_header(self):
        p = parse_message("#가격인상")
        self.assertIsNotNone(p)
        self.assertEqual(p.event_type, "PRICE_UP")

    def test_delay_notice_not_restock(self):
        p = parse_message("팜허브 입고 지연으로 순차출고 예정입니다")
        self.assertIsNotNone(p)
        self.assertEqual(p.event_type, "DELAY_NOTICE")

    def test_new_item_with_price(self):
        p = parse_message("📌신규상품 'A급 남해 보물초 시금치' 11,700원")
        self.assertIsNotNone(p)
        self.assertEqual(p.event_type, "NEW_ITEM")
        self.assertEqual(p.new_price, 11700)

    def test_sold_out(self):
        p = parse_message("[품절 안내] 샤인머스켓 특품")
        self.assertIsNotNone(p)
        self.assertEqual(p.event_type, "SOLD_OUT")


if __name__ == "__main__":
    unittest.main()
