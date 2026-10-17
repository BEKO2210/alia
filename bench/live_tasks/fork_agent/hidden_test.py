import unittest
from pathlib import Path


class T(unittest.TestCase):
    def test_answer(self):
        text = Path("answer.txt").read_text()
        self.assertIn("pricing.py", text)
        self.assertIn("apply_discount", text)
