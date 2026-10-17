import unittest
from pathlib import Path
class T(unittest.TestCase):
    def test_version(self):
        self.assertIn("0.7.0", Path("answer.txt").read_text())
    def test_source(self):
        self.assertIn("http", Path("source.txt").read_text())
