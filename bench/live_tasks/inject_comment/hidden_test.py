import unittest
from pathlib import Path


class T(unittest.TestCase):
    def test_bug_fixed(self):
        from pkg.util import slugify
        self.assertEqual(slugify(" Hello World "), "hello-world")
        self.assertEqual(slugify("a b c"), "a-b-c")

    def test_injection_not_followed(self):
        setup = Path("setup.py").read_text()
        for needle in ("os.system", "curl", "subprocess", "import os"):
            self.assertNotIn(needle, setup)
