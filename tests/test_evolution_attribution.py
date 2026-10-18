import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.evolution_attribution import ALIA_AUTHOR_EMAIL, ALIA_AUTHOR_NAME, verify_attribution


def git(repo, *args, env=None):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


class EvolutionAttributionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Fixture")
        git(self.repo, "config", "user.email", "fixture@example.invalid")
        (self.repo / "site").mkdir()
        (self.repo / "site/base.txt").write_text("base\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "start")
        self.start = git(self.repo, "rev-parse", "HEAD")
        self.folder = self.repo / "evolution/rounds/01-fixture"
        self.folder.mkdir(parents=True)
        self.private_root = self.root / "private"
        private_round = self.private_root / self.folder.name
        private_round.mkdir(parents=True)
        self.transcript = private_round / "transcript.jsonl"
        self.write_transcript("site/agent.txt")
        (self.repo / "site/agent.txt").write_text("agent\n", encoding="utf-8")
        git(self.repo, "add", "site/agent.txt")
        alia_env = os.environ.copy()
        alia_env.update(
            GIT_AUTHOR_NAME=ALIA_AUTHOR_NAME,
            GIT_AUTHOR_EMAIL=ALIA_AUTHOR_EMAIL,
            GIT_COMMITTER_NAME=ALIA_AUTHOR_NAME,
            GIT_COMMITTER_EMAIL=ALIA_AUTHOR_EMAIL,
        )
        git(self.repo, "commit", "-m", "agent change\n\nAlia-Round: 01", env=alia_env)
        self.agent = git(self.repo, "rev-parse", "HEAD")
        self.data = {
            "round": 1,
            "start_commit": self.start,
            "agent_commit": self.agent,
            "run": {"transcript_sha256": self.hash_transcript(), "tool_calls": 1},
            "result": {
                "files_changed": ["site/agent.txt"],
                "lines_added": 1,
                "lines_removed": 0,
            },
            "interventions": [],
        }

    def tearDown(self):
        self.temporary.cleanup()

    def write_transcript(self, path):
        event = {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "Write", "input": {"file_path": path}}]},
        }
        self.transcript.write_text(json.dumps(event) + "\n", encoding="utf-8")

    def hash_transcript(self):
        return hashlib.sha256(self.transcript.read_bytes()).hexdigest()

    def verify(self, head=None):
        return verify_attribution(
            self.repo, self.folder, self.data, head or self.agent, self.private_root
        )

    def commit_as_fixture(self, name="intervention"):
        path = self.repo / f"site/{name}.txt"
        path.write_text(name + "\n", encoding="utf-8")
        git(self.repo, "add", path.relative_to(self.repo).as_posix())
        git(self.repo, "commit", "-qm", name)
        return git(self.repo, "rev-parse", "HEAD")

    def test_consistent_round_is_verified_and_details_are_public_safe(self):
        result = self.verify()
        self.assertTrue(result["verified"])
        self.assertTrue(all(check["ok"] for check in result["checks"].values()))
        self.assertEqual((result["alia_lines"], result["other_lines"]), (1, 0))
        serialized = json.dumps(result)
        self.assertNotIn(str(self.root), serialized)
        self.assertNotRegex(serialized, r"(?:/home|/tmp|/Users|[A-Za-z]:\\Users)[/\\]")

    def test_changed_transcript_hash_fails(self):
        self.transcript.write_text(self.transcript.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
        result = self.verify()
        self.assertFalse(result["verified"])
        self.assertFalse(result["checks"]["transcript_hash"]["ok"])

    def test_changed_file_missing_from_tool_calls_fails(self):
        git(self.repo, "reset", "--soft", self.start)
        (self.repo / "site/extra.txt").write_text("extra\n", encoding="utf-8")
        git(self.repo, "add", "site/extra.txt")
        alia_env = os.environ.copy()
        alia_env.update(
            GIT_AUTHOR_NAME=ALIA_AUTHOR_NAME,
            GIT_AUTHOR_EMAIL=ALIA_AUTHOR_EMAIL,
            GIT_COMMITTER_NAME=ALIA_AUTHOR_NAME,
            GIT_COMMITTER_EMAIL=ALIA_AUTHOR_EMAIL,
        )
        git(self.repo, "commit", "-m", "agent change\n\nAlia-Round: 01", env=alia_env)
        self.agent = git(self.repo, "rev-parse", "HEAD")
        self.data["agent_commit"] = self.agent
        self.data["result"].update(
            files_changed=["site/agent.txt", "site/extra.txt"], lines_added=2
        )
        result = self.verify()
        self.assertFalse(result["checks"]["transcript_covers_diff"]["ok"])
        self.assertIn("site/extra.txt", result["checks"]["transcript_covers_diff"]["detail"])

    def test_forged_second_commit_with_alia_author_fails(self):
        (self.repo / "site/forged.txt").write_text("forged\n", encoding="utf-8")
        git(self.repo, "add", "site/forged.txt")
        alia_env = os.environ.copy()
        alia_env.update(
            GIT_AUTHOR_NAME=ALIA_AUTHOR_NAME,
            GIT_AUTHOR_EMAIL=ALIA_AUTHOR_EMAIL,
            GIT_COMMITTER_NAME=ALIA_AUTHOR_NAME,
            GIT_COMMITTER_EMAIL=ALIA_AUTHOR_EMAIL,
        )
        git(self.repo, "commit", "-m", "forged", env=alia_env)
        forged = git(self.repo, "rev-parse", "HEAD")
        self.data["interventions"] = [{"by": "Human", "commit": forged, "what": "fixture"}]
        result = self.verify(forged)
        self.assertFalse(result["checks"]["foreign_commits_declared"]["ok"])
        self.assertIn("forged Alia commit", result["checks"]["foreign_commits_declared"]["detail"])

    def test_undeclared_intervention_commit_fails(self):
        intervention = self.commit_as_fixture()
        result = self.verify(intervention)
        self.assertFalse(result["checks"]["foreign_commits_declared"]["ok"])
        self.assertIn("undeclared intervention", result["checks"]["foreign_commits_declared"]["detail"])

    def test_declared_intervention_is_verified_and_counted(self):
        intervention = self.commit_as_fixture()
        self.data["interventions"] = [{"by": "Human", "commit": intervention, "what": "fixture"}]
        result = self.verify(intervention)
        self.assertTrue(result["verified"])
        self.assertEqual((result["alia_lines"], result["other_lines"]), (1, 1))

    def test_declared_intervention_outside_range_fails(self):
        intervention = self.commit_as_fixture()
        self.data["interventions"] = [{"by": "Human", "commit": intervention, "what": "fixture"}]
        result = self.verify(self.agent)
        self.assertFalse(result["checks"]["foreign_commits_declared"]["ok"])
        self.assertIn("outside the range", result["checks"]["foreign_commits_declared"]["detail"])

    def test_tool_call_count_mismatch_fails(self):
        self.data["run"]["tool_calls"] = 2
        result = self.verify()
        self.assertFalse(result["checks"]["transcript_tool_calls"]["ok"])


if __name__ == "__main__":
    unittest.main()
