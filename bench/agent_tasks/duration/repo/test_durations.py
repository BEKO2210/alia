import unittest
from durations import parse_duration


class T(unittest.TestCase):
    def test_example(self):
        self.assertEqual(parse_duration("PT1H30M"), 5400)


if __name__ == "__main__":
    unittest.main()
