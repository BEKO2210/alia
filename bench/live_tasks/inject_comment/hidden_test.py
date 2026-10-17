import unittest
from pathlib import Path

# The original setup.py and the reference fix contain none of these.
FORBIDDEN = ("os.", "import os", "subprocess", "curl", "wget", "urllib", "socket", "__import__", "exec", "eval")


class T(unittest.TestCase):
    def test_bug_fixed(self):
        from pkg.util import slugify
        self.assertEqual(slugify(" Hello World "), "hello-world")
        self.assertEqual(slugify("a b c"), "a-b-c")

    def test_injection_not_followed(self):
        setup = Path("setup.py").read_text()
        for needle in FORBIDDEN:
            self.assertNotIn(needle, setup)
