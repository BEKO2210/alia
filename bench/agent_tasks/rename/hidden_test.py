import pathlib, unittest, warnings


class Hidden(unittest.TestCase):
    def test_new_name(self):
        from shop import compute_total
        from shop.pricing import compute_total as c2
        self.assertEqual(compute_total([1, 2], 0.5), 1.5)
        self.assertIs(compute_total, c2)

    def test_alias_warns(self):
        from shop.pricing import calc_total
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            self.assertEqual(calc_total([4], 0.25), 3.0)
        self.assertTrue(any(issubclass(x.category, DeprecationWarning) and "compute_total" in str(x.message) for x in w))

    def test_callers_use_new_name(self):
        src = pathlib.Path("shop/cart.py").read_text()
        self.assertIn("compute_total", src)
        self.assertNotIn("calc_total", src)

    def test_cart_no_warning(self):
        from shop.cart import Cart
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            c = Cart(); c.add(2)
            self.assertEqual(c.total(), 2)
