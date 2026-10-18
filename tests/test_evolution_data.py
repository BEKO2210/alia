import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.evolution_data import privacy_check, ValidationError, generate, main, validate_round


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

    def test_privacy_gate_rejects_normalization_and_new_secret_bypasses(self):
        samples = [
            "／home／person", "∕tmp∕private", "C:\\Users\\x", "person@\u200bexample.com",
            "fd7a:115c:a1e0::1234", "010.002.003.004", "gho_secret", "hf_secret",
        ]
        for index, sample in enumerate(samples):
            with self.subTest(sample=sample):
                copied = self.root / f"bypass-{index}"
                shutil.copytree(EXAMPLES, copied)
                folder = next(copied.glob("01-*"))
                path = folder / "round.json"
                data = json.loads(path.read_text(encoding="utf-8"))
                data["summary"]["en"] = sample
                self.write_data(path, data)
                with self.assertRaisesRegex(ValidationError, "privacy gate"):
                    generate(copied)

    def test_summary_and_title_have_exact_language_keys(self):
        folder, path, data = self.data(1)
        data["summary"]["fr"] = "non"
        self.write_data(path, data)
        with self.assertRaisesRegex(ValidationError, "exactly en and de"):
            validate_round(folder)

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

    def test_passed_round_requires_verified_attribution(self):
        folder, path, data = self.data(1)
        del data["attribution"]
        self.write_data(path, data)
        with self.assertRaisesRegex(ValidationError, "verified attribution"):
            validate_round(folder)
        shutil.rmtree(self.rounds)
        shutil.copytree(EXAMPLES, self.rounds)
        _, path, data = self.data(1)
        data["attribution"]["verified"] = False
        data["attribution"]["checks"]["transcript_hash"]["ok"] = False
        self.write_data(path, data)
        with self.assertRaisesRegex(ValidationError, "verified attribution"):
            validate_round(folder)

    def test_attribution_is_whitelisted_and_published(self):
        folder, path, data = self.data(1)
        data["attribution"]["private"] = "hidden"
        self.write_data(path, data)
        with self.assertRaisesRegex(ValidationError, "must contain only"):
            validate_round(folder)
        del data["attribution"]["private"]
        self.write_data(path, data)
        output = json.loads(generate(self.rounds))[0]
        self.assertTrue(output["attribution"]["verified"])
        self.assertEqual(output["attribution"]["alia_lines"], 1)

    def test_attribution_detail_rejects_absolute_paths(self):
        folder, path, data = self.data(1)
        data["attribution"]["checks"]["share"]["detail"] = "read /etc/private-file"
        self.write_data(path, data)
        with self.assertRaisesRegex(ValidationError, "absolute paths"):
            validate_round(folder)

    def test_passed_round_cannot_have_isolation_breaches_or_zero_tests(self):
        folder, path, data = self.data(1)
        self.assertEqual(data["status"], "passed")
        data["result"]["isolation_breaches"] = ["round-data"]
        self.write_data(path, data)
        with self.assertRaisesRegex(ValidationError, "isolation breaches"):
            validate_round(folder)
        del data["result"]["isolation_breaches"]
        data["result"]["acceptance_passed"] = data["result"]["acceptance_total"] = 0
        self.write_data(path, data)
        with self.assertRaisesRegex(ValidationError, "passed round"):
            validate_round(folder)

    def test_passed_round_requires_every_success_condition(self):
        mutations = {
            "exit": lambda data: data["run"].update(exit_code=1),
            "site unknown": lambda data: data["result"].update(site_checks=None),
            "site failure": lambda data: data["result"]["site_checks"].update(failures=1),
            "no files": lambda data: data["result"].update(files_changed=[]),
            "out of scope": lambda data: data["result"].update(out_of_scope_paths=["other.txt"]),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                folder, path, data = self.data(1)
                mutate(data)
                self.write_data(path, data)
                with self.assertRaisesRegex(ValidationError, "passed round"):
                    validate_round(folder)
                shutil.rmtree(self.rounds)
                shutil.copytree(EXAMPLES, self.rounds)

    def test_site_checks_requires_exact_count_shape(self):
        folder, path, data = self.data(2)
        data["result"]["site_checks"] = {"failures": 1, "known": 0}
        self.write_data(path, data)
        with self.assertRaisesRegex(ValidationError, "failures, known and fixed"):
            validate_round(folder)

    def test_generate_with_repo_binds_frozen_bytes_to_git(self):
        repo = self.root / "git-fixture"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=repo, check=True)
        rounds = repo / "rounds"
        shutil.copytree(EXAMPLES / "01-example-passed", rounds / "01-example-passed")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "frozen inputs"], cwd=repo, check=True)
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()
        path = rounds / "01-example-passed/round.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["acceptance"]["frozen_commit"] = commit
        self.write_data(path, data)
        # A passed round in a real repository also needs its agent commit there.
        with self.assertRaisesRegex(ValidationError, "agent_commit does not match"):
            generate(rounds, repo=repo)
        data["status"] = "failed"
        self.write_data(path, data)
        generate(rounds, repo=repo)
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "round failed"], cwd=repo, check=True)
        # Once the base branch records the round as failed, it cannot be relabelled.
        data["status"] = "aborted"
        self.write_data(path, data)
        with self.assertRaisesRegex(ValidationError, "cannot change"):
            generate(rounds, repo=repo, base="HEAD")
        data["status"] = "failed"
        self.write_data(path, data)
        generate(rounds, repo=repo, base="HEAD")
        task = rounds / "01-example-passed/task.md"
        task.write_text("new but locally consistent\n", encoding="utf-8")
        data["task_sha256"] = hashlib.sha256(task.read_bytes()).hexdigest()
        self.write_data(path, data)
        with self.assertRaisesRegex(ValidationError, "frozen git bytes differ"):
            generate(rounds, repo=repo)

    def test_out_of_scope_is_recomputed_and_new_privacy_bypasses_rejected(self):
        folder, path, data = self.data(2)
        data["result"]["files_changed"] = ["alia"]
        data["result"]["out_of_scope_paths"] = []
        self.write_data(path, data)
        with self.assertRaisesRegex(ValidationError, "out_of_scope_paths does not list"):
            validate_round(folder)
        for sample in ("\u29f8home\u29f8person", "%2Fhome%2Fperson", "see ~/secret", "~user/notes",
                       "-----BEGIN OPENSSH PRIVATE KEY-----"):
            with self.subTest(sample=sample), self.assertRaisesRegex(ValidationError, "privacy gate"):
                privacy_check(sample)
        for harmless in ("site/style.css", "100% done", "a/b ~ c"):
            privacy_check(harmless)

    def test_invalid_round_is_published_with_breach_labels(self):
        folder, path, data = self.data(2)
        data["status"] = "invalid"
        data["result"]["isolation_breaches"] = ["round-data"]
        self.write_data(path, data)
        output = json.loads(generate(self.rounds))
        self.assertEqual(output[1]["status"], "invalid")
        self.assertEqual(output[1]["result"]["isolation_breaches"], ["round-data"])

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
