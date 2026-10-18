import unittest

from tools.evolution_guard import protected_paths


class EvolutionGuardTests(unittest.TestCase):
    def test_protected_exact_and_tree_paths(self):
        paths = ["site/index.html", "./alia", "i18n/de.json", "bench/new.py", "tests/test_alia.py"]
        self.assertEqual(protected_paths(paths), ["alia", "bench/new.py", "i18n/de.json", "tests/test_alia.py"])

    def test_similar_names_are_allowed(self):
        self.assertEqual(protected_paths(["tools/alia", "benchmark.txt", "site/i18n/demo.json"]), [])


if __name__ == "__main__":
    unittest.main()
