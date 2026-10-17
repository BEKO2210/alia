import unittest
from cache import LRUCache


class Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


class Hidden(unittest.TestCase):
    def test_expiry(self):
        k = Clock(); c = LRUCache(3, ttl=10, clock=k)
        c.put("a", 1); k.t = 9.9
        self.assertEqual(c.get("a"), 1)
        k.t = 10.0
        self.assertIsNone(c.get("a")); self.assertNotIn("a", c); self.assertEqual(len(c), 0)

    def test_read_does_not_extend(self):
        k = Clock(); c = LRUCache(3, ttl=5, clock=k)
        c.put("a", 1); k.t = 4; c.get("a"); k.t = 6
        self.assertEqual(c.get("a", "x"), "x")

    def test_rewrite_extends(self):
        k = Clock(); c = LRUCache(3, ttl=5, clock=k)
        c.put("a", 1); k.t = 4; c.put("a", 2); k.t = 8
        self.assertEqual(c.get("a"), 2)

    def test_expired_do_not_evict_live(self):
        k = Clock(); c = LRUCache(2, ttl=5, clock=k)
        c.put("old", 1); k.t = 1; c.put("live", 2); k.t = 5.5
        c.put("new", 3)
        self.assertEqual(c.get("live"), 2); self.assertEqual(c.get("new"), 3); self.assertEqual(len(c), 2)

    def test_no_ttl(self):
        k = Clock(); c = LRUCache(1, clock=k); c.put("a", 1); k.t = 1e9
        self.assertEqual(c.get("a"), 1)
