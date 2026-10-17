import unittest
from cache import LRUCache


class T(unittest.TestCase):
    def test_lru(self):
        c = LRUCache(2); c.put("a", 1); c.put("b", 2); c.get("a"); c.put("c", 3)
        self.assertIn("a", c); self.assertNotIn("b", c)


if __name__ == "__main__":
    unittest.main()
