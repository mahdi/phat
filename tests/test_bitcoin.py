import unittest
from decimal import Decimal

from inky_dashboard.widgets.bitcoin import parse_market, trend_for_change


class BitcoinTests(unittest.TestCase):
    def test_parse_market_calculates_percentage_change(self):
        price, change = parse_market({"last": "105", "open": "100"})
        self.assertEqual(price, Decimal("105"))
        self.assertEqual(change, Decimal("5.00"))

    def test_downtrend_uses_down_arrow(self):
        self.assertEqual(trend_for_change(Decimal("-0.01")), ("▼", True))

    def test_flat_or_uptrend_uses_up_arrow(self):
        self.assertEqual(trend_for_change(Decimal("0")), ("▲", False))
        self.assertEqual(trend_for_change(Decimal("0.01")), ("▲", False))

    def test_zero_opening_price_is_rejected(self):
        with self.assertRaises(RuntimeError):
            parse_market({"last": "105", "open": "0"})


if __name__ == "__main__":
    unittest.main()
