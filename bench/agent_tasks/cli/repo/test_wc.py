import unittest
from wc import count


class T(unittest.TestCase):
    def test_count(self):
        self.assertEqual(count("a b\nc\n"), (2, 3, 6))


if __name__ == "__main__":
    unittest.main()
