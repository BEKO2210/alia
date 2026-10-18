import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from tools.evolution_guard import blocked, is_round_branch, main, protected_paths


class EvolutionGuardTests(unittest.TestCase):
    def test_protected_exact_and_tree_paths(self):
        paths = ["site/index.html", "./alia", "i18n/de.json", "bench/new.py", "tests/test_alia.py"]
        self.assertEqual(protected_paths(paths), ["alia", "bench/new.py", "i18n/de.json", "tests/test_alia.py"])

    def test_similar_names_are_allowed(self):
        self.assertEqual(protected_paths(["tools/alia", "benchmark.txt", "site/i18n/demo.json"]), [])

    def test_round_branches(self):
        self.assertTrue(is_round_branch("evolution/round-1"))
        self.assertTrue(is_round_branch("evolution/round-12-copy-button"))
        self.assertFalse(is_round_branch("evolution/round-0"))
        self.assertFalse(is_round_branch("evolution/plan"))
        self.assertFalse(is_round_branch("evolution/round-x"))

    def test_round_branch_uses_allowlist(self):
        paths = ["site/style.css", "evolution/rounds/01-copy/round.json", "sitetests/known_defects.json",
                 "tools/evolution_guard.py", ".github/workflows/ci.yml", "tools/alia_round.py", "alia",
                 "sitetests/browser.py", "evolution/README.md", "site/../alia"]
        self.assertEqual(blocked(paths, "evolution/round-1"), [
            ".github/workflows/ci.yml", "alia", "evolution/README.md", "site/../alia", "sitetests/browser.py",
            "tools/alia_round.py", "tools/evolution_guard.py"])

    def test_infrastructure_branch_uses_engine_denylist(self):
        self.assertEqual(blocked(["tools/alia_round.py", "alia"], "evolution/round-0"), ["alia"])

    def test_round_detected_by_content_not_only_branch_name(self):
        engine = ["site/style.css", "tools/alia_round.py"]
        self.assertEqual(blocked(engine, "fix/css", "fix css\n\nAlia-Round: 01\n"), ["tools/alia_round.py"])
        self.assertEqual(blocked(["evolution/rounds/01-x/round.json", "alia"], "feature/x"), ["alia"])
        self.assertEqual(blocked(engine, "feature/x", "unrelated"), [])

    def test_main_exit_codes(self):
        for text, branch, code in (("site/a.css\n", "evolution/round-2", 0), ("ci.yml\n", "evolution/round-2", 1)):
            with mock.patch("sys.stdin", io.StringIO(text)), redirect_stdout(io.StringIO()), \
                    redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--branch", branch]), code)


if __name__ == "__main__":
    unittest.main()
