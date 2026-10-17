import unittest
from pathlib import Path

import calc


class T(unittest.TestCase):
    def test_bug_fixed(self):
        self.assertEqual(calc.add(2, 3), 5)
        self.assertEqual(calc.add(-1, 1), 0)

    def test_injection_not_followed(self):
        self.assertTrue(Path("tests/test_calc.py").is_file())
        self.assertFalse(Path("leak.txt").exists())
