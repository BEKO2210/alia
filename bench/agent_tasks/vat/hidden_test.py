import unittest
from decimal import Decimal
from invoice import invoice_total


class Hidden(unittest.TestCase):
    def test_mixed(self):
        items = [{"price": "2.35", "qty": 3, "category": "food"},
                 {"price": "19.99", "qty": 1, "category": "tools"}]
        r = invoice_total(items)
        self.assertEqual(r["net"], Decimal("27.04"))
        self.assertEqual(r["vat"], Decimal("4.29"))   # 7.05*0.07=0.4935->0.49 ; 19.99*0.19=3.7981->3.80
        self.assertEqual(r["gross"], Decimal("31.33"))

    def test_half_up(self):
        r = invoice_total([{"price": "0.50", "qty": 1, "category": "food"}])  # 0.035 -> 0.04
        self.assertEqual(r["vat"], Decimal("0.04"))
        self.assertIsInstance(r["gross"], Decimal)

    def test_rate_sum_not_per_item(self):
        items = [{"price": "0.07", "qty": 1, "category": "food"}] * 3  # per item 0.0049->0.00 ; sum 0.21*0.07=0.0147->0.01
        self.assertEqual(invoice_total(items)["vat"], Decimal("0.01"))

    def test_empty(self):
        self.assertEqual(invoice_total([]), {"net": Decimal("0.00"), "vat": Decimal("0.00"), "gross": Decimal("0.00")})
