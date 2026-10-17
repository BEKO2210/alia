import unittest

from pkg.util import slugify


class SlugifyTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify(" Hello World "), "hello-world")
