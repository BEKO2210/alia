import unittest
from decimal import Decimal
from invoice import invoice_total


class InvoiceTest(unittest.TestCase):
    def test_net(self):
        items = [{"price": "10.00", "qty": 2, "category": "tools"}]
        self.assertEqual(invoice_total(items)["net"], Decimal("20.00"))


if __name__ == "__main__":
    unittest.main()
