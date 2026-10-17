import unittest
from pathlib import Path
class T(unittest.TestCase):
    def test_price(self):
        self.assertIn("37,90", Path("answer.txt").read_text())
    def test_stock_needs_js(self):
        self.assertIn("12", Path("stock.txt").read_text())
