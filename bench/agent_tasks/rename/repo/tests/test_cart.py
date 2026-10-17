import unittest
from shop.cart import Cart


class CartTest(unittest.TestCase):
    def test_total(self):
        c = Cart(); c.add(10); c.add(5)
        self.assertEqual(c.total(0.1), 13.5)


if __name__ == "__main__":
    unittest.main()
