import tempfile
import unittest
from pathlib import Path

from sitetests.core import contrast_ratio, known_identity, match_known, parse_js_dictionary, resolve_local_target


class ContrastMathTests(unittest.TestCase):
    def test_black_white_contrast_is_twenty_one(self):
        self.assertAlmostEqual(contrast_ratio((0, 0, 0), (255, 255, 255)), 21)

    def test_known_muted_color_is_below_aa(self):
        self.assertLess(contrast_ratio((107, 116, 134), (7, 8, 12)), 4.5)


class ParserTests(unittest.TestCase):
    def test_js_dictionary_handles_escaped_quotes(self):
        source = r'''const DE = {"plain": "Wert", "quote": "Sie sagt \"ja\"", 'single': 'geht\'s',};'''
        self.assertEqual(
            parse_js_dictionary(source),
            {"plain": "Wert", "quote": 'Sie sagt "ja"', "single": "geht's"},
        )

    def test_link_resolver_handles_query_anchor_and_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            page = site / "nested/index.html"
            target = site / "other/index.html"
            target.parent.mkdir()
            target.write_text('<p id="part">x</p>', encoding="utf-8")
            resolved, anchor = resolve_local_target(page, "../other/?v=1#part", site)
            self.assertEqual(resolved, target)
            self.assertEqual(anchor, "part")

    def test_external_link_has_no_local_target(self):
        self.assertIsNone(resolve_local_target(Path("site/index.html"), "https://example.invalid/a", Path("site")))


class KnownDefectTests(unittest.TestCase):
    def test_matching_uses_stable_identity_not_detail(self):
        current = [{"check": "contrast", "page": "index", "viewport": "390", "lang": "en", "selector": ".meta", "detail": "new measurement"}]
        known = [{**current[0], "detail": "old measurement"}]
        new, matched, fixed = match_known(current, known)
        self.assertEqual((new, fixed), ([], []))
        self.assertEqual(matched, current)
        self.assertEqual(known_identity(current[0]), known_identity(known[0]))

    def test_missing_known_defect_is_fixed(self):
        known = [{"check": "tap-target", "page": "index", "selector": ".nav", "detail": "small"}]
        self.assertEqual(match_known([], known), ([], [], known))


if __name__ == "__main__":
    unittest.main()
