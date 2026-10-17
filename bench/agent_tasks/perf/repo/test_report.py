import unittest
from report import merge_events


class T(unittest.TestCase):
    def test_small(self):
        a = [{"id": "x", "ts": 5, "source": "a"}, {"id": "y", "ts": 1, "source": "a"}]
        b = [{"id": "x", "ts": 3, "source": "b"}]
        self.assertEqual([e["source"] for e in merge_events([a, b])], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
