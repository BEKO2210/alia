import unittest


class T(unittest.TestCase):
    def test_placeholder(self):
        import customers  # noqa: F401


if __name__ == "__main__":
    unittest.main()
