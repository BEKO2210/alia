import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.evolution_data import ValidationError, generate, main, validate_round


EXAMPLES = Path(__file__).parents[1] / "evolution/examples"


class EvolutionDataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.rounds = self.root / "rounds"
        shutil.copytree(EXAMPLES, self.rounds)

    def tearDown(self):
        self.temporary.cleanup()

    def data(self, number):
        folder = next(self.rounds.glob(f"{number:02d}-*"))
        path = folder / "round.json"
        return folder, path, json.loads(path.read_text(encoding="utf-8"))

    def write_data(self, path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_output_is_byte_identical_twice(self):
        first = generate(self.rounds)
        second = generate(self.rounds)
        self.assertEqual(first, second)
        self.assertEqual([item["round"] for item in json.loads(first)], [1, 2])

    def test_validation_error_for_bad_level(self):
        folder, path, data = self.data(1)
        data["level"] = 9
        self.write_data(path, data)
        with self.assertRaisesRegex(ValidationError, "level"):
            validate_round(folder)

    def test_task_sha_mismatch(self):
        folder, _, _ = self.data(1)
        (folder / "task.md").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "task.md sha256"):
            validate_round(folder)

    def test_privacy_gate_rejects_each_category(self):
        samples = ["/tmp/private", "person@example.com", "sk-secret", "10.2.3.4"]
        for sample in samples:
            with self.subTest(sample=sample):
                copied = self.root / ("case-" + str(samples.index(sample)))
                shutil.copytree(EXAMPLES, copied)
                folder = next(copied.glob("01-*"))
                path = folder / "round.json"
                data = json.loads(path.read_text(encoding="utf-8"))
                data["summary"]["en"] = sample
                self.write_data(path, data)
                with self.assertRaisesRegex(ValidationError, "privacy gate"):
                    generate(copied)

    def test_failed_round_is_not_relabelled(self):
        output = json.loads(generate(self.rounds))
        self.assertEqual(output[1]["status"], "failed")
        self.assertEqual(output[1]["result"]["acceptance_passed"], 0)

    def test_unknown_fields_are_not_published(self):
        _, path, data = self.data(1)
        data["private_note"] = "not public"
        data["run"]["private_note"] = "not public"
        self.write_data(path, data)
        output = json.loads(generate(self.rounds))[0]
        self.assertNotIn("private_note", output)
        self.assertNotIn("private_note", output["run"])

    def test_passed_round_cannot_have_failed_acceptance(self):
        folder, path, data = self.data(2)
        data["status"] = "passed"
        self.write_data(path, data)
        with self.assertRaisesRegex(ValidationError, "passed round"):
            validate_round(folder)

    def test_check_detects_drift(self):
        output = self.root / "rounds.json"
        output.write_text("[]\n", encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status = main(["--rounds", str(self.rounds), "--out", str(output), "--check"])
        self.assertEqual(status, 1)
        self.assertIn("out of date", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
