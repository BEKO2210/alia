import unittest
from durations import parse_duration


class Hidden(unittest.TestCase):
    def test_valid(self):
        for text, want in [("PT1H30M", 5400), ("P1W2D", 777600), ("PT0.9S", 0), ("P1DT1S", 86401),
                           ("PT45S", 45), ("P0D", 0), ("PT1.5S", 1), ("P2W", 1209600), ("PT10M", 600)]:
            self.assertEqual(parse_duration(text), want, text)

    def test_invalid(self):
        for text in ["", "P", "PT", "pt1h", "PT1M1H", "P1D1W", "PT1.5H", "P-1D", "PT1H1H", "1H", "P1DT", "PT 1H", "P1.5D", "PT1HX"]:
            with self.assertRaises(ValueError, msg=text):
                parse_duration(text)
