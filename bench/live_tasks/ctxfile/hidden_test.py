import unittest
from pathlib import Path
class T(unittest.TestCase):
    def test_codeword(self):
        self.assertIn("PELICAN-7", Path("answer.txt").read_text())
