import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.alia_round import final_status, hash_file, out_of_scope


RUNNER = Path(__file__).parents[1] / "tools/alia_round.py"


def bwrap_usable():
    try:
        return subprocess.run(["bwrap", "--unshare-all", "--die-with-parent", "--ro-bind", "/", "/", "true"],
                              capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# Without user namespaces (GitHub runners) the fake agent runs unjailed; the jail is covered where it works.
JAIL = bwrap_usable()


def run(args, cwd, check=True):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=True)


class AliaRoundTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def init_git(self, path):
        path.mkdir()
        run(["git", "init", "-q"], path)
        run(["git", "config", "user.name", "Fixture"], path)
        run(["git", "config", "user.email", "fixture@example.invalid"], path)

    def make_productive(self):
        productive = self.root / "productive"
        self.init_git(productive)
        (productive / "marker.txt").write_text("untouched\n", encoding="utf-8")
        run(["git", "add", "marker.txt"], productive)
        run(["git", "commit", "-qm", "productive"], productive)
        return productive

    def make_repo(self, acceptance_passes=True, initial_status="planned"):
        repo = self.root / "round-repo"
        self.init_git(repo)
        (repo / "site").mkdir()
        (repo / "site/index.html").write_text("<!doctype html><title>fixture</title>\n", encoding="utf-8")
        package = repo / "sitetests"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "__main__.py").write_text(
            "import argparse\np=argparse.ArgumentParser(); p.add_argument('--site'); p.add_argument('--out'); p.parse_args(); print('site checks: 0 failure(s)')\n",
            encoding="utf-8",
        )
        run(["git", "add", "."], repo)
        run(["git", "commit", "-qm", "start"], repo)
        start = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
        folder = repo / "evolution/rounds/01-example"
        acceptance = folder / "acceptance"
        acceptance.mkdir(parents=True)
        (folder / "task.md").write_text("Change the fixture site.\n", encoding="utf-8")
        assertion = "self.assertTrue(marker.exists())" if acceptance_passes else "self.assertTrue(False)"
        (acceptance / "test_acceptance.py").write_text(
            "import os\nimport unittest\nfrom pathlib import Path\n\n"
            "class Acceptance(unittest.TestCase):\n"
            "    def test_change(self):\n"
            "        marker = Path(os.environ['SITE_ROOT']) / 'agent.txt'\n"
            f"        {assertion}\n",
            encoding="utf-8",
        )
        data = {
            "round": 1,
            "slug": "example",
            "status": initial_status,
            "start_commit": start,
            "task_sha256": hash_file(folder / "task.md"),
            "acceptance": {"files": {"acceptance/test_acceptance.py": hash_file(acceptance / "test_acceptance.py")}, "frozen_commit": start},
            "allowed_paths": ["site/"],
            "run": {"wall_limit_seconds": 30},
            "result": {},
            "agent": {},
            "agent_commit": None,
        }
        (folder / "round.json").write_text(json.dumps(data), encoding="utf-8")
        return repo, folder

    steal_targets = ()

    def make_agent(self):
        agent = self.root / "fake_agent.py"
        agent.write_text(
            "import json\nimport pathlib\nimport sys\n"
            "root = pathlib.Path.cwd()\n"
            "if (root / 'evolution').exists(): raise SystemExit('evolution leaked')\n"
            "(root / 'site/agent.txt').write_text('agent change\\n')\n"
            "if sys.argv[1] == 'outside': (root / 'outside.txt').write_text('outside\\n')\n"
            "if sys.argv[1] == 'peek': print(json.dumps({'type': 'tool_result', 'output': sys.argv[2]}))\n"
            "if sys.argv[1] == 'steal':\n"
            f"    for target in {list(self.steal_targets)!r}:\n"
            "        try: (root / 'site' / ('stolen-' + pathlib.Path(target).name)).write_bytes(pathlib.Path(target).read_bytes())\n"
            "        except OSError: pass\n"
            "print(json.dumps({'type': 'tool_call'}))\n"
            "print(json.dumps({'type': 'result', 'private_text': 'TRANSCRIPT_SECRET'}))\n",
            encoding="utf-8",
        )
        return agent

    def invoke(self, repo, productive, mode="inside", *extra):
        private = self.root / "private"
        return run(
            [
                sys.executable,
                str(RUNNER),
                "run",
                "1",
                "--dry-run",
                "--private-root",
                str(private),
                "--productive-checkout",
                str(productive),
                "--agent-cmd",
                sys.executable,
                str(self.make_agent()),
                mode,
                *extra,
                *([] if JAIL else ["--no-jail"]),
            ],
            repo,
            check=False,
        )

    def snapshot(self, repo):
        head = run(["git", "rev-parse", "HEAD"], repo).stdout
        status = run(["git", "status", "--porcelain"], repo).stdout
        hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in repo.iterdir() if path.is_file()}
        return head, status, hashes

    def test_full_dry_run_passes_and_keeps_productive_checkout_unchanged(self):
        repo, folder = self.make_repo(acceptance_passes=True)
        productive = self.make_productive()
        before = self.snapshot(productive)
        completed = self.invoke(repo, productive)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertEqual(self.snapshot(productive), before)
        data = json.loads((folder / "round.json").read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "passed")
        self.assertEqual(data["result"]["acceptance_passed"], 1)
        self.assertNotIn("TRANSCRIPT_SECRET", json.dumps(data))
        work = self.root / "private/01-example/work"
        self.assertFalse((work / "evolution").exists())

    def test_full_dry_run_failure_and_out_of_scope_path(self):
        repo, folder = self.make_repo(acceptance_passes=False)
        productive = self.make_productive()
        completed = self.invoke(repo, productive, "outside")
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        data = json.loads((folder / "round.json").read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["result"]["out_of_scope_paths"], ["outside.txt"])

    def test_private_copy_holds_only_the_start_commit(self):
        repo, _ = self.make_repo()
        completed = self.invoke(repo, self.make_productive())
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        work = self.root / "private/01-example/work"
        start = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
        # Start commit plus Alia's own commit, nothing else; no shared object store with the repo.
        self.assertEqual(run(["git", "rev-list", "--all", "--count"], work).stdout.strip(), "2")
        self.assertEqual(run(["git", "rev-parse", "HEAD~1"], work).stdout.strip(), start)
        self.assertFalse((work / ".git/objects/info/alternates").exists())
        self.assertTrue((work / ".git").is_dir())

    def test_refuses_start_commit_containing_the_round(self):
        repo, folder = self.make_repo()
        run(["git", "add", "."], repo)
        run(["git", "commit", "-qm", "round data"], repo)
        data = json.loads((folder / "round.json").read_text(encoding="utf-8"))
        data["start_commit"] = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
        (folder / "round.json").write_text(json.dumps(data), encoding="utf-8")
        completed = self.invoke(repo, self.make_productive())
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("already contains", completed.stderr)

    def test_transcript_touching_round_data_marks_round_invalid(self):
        repo, folder = self.make_repo(acceptance_passes=True)
        completed = self.invoke(repo, self.make_productive(), "peek", f"cat {repo.resolve()}/{folder.relative_to(repo)}/acceptance/test_acceptance.py")
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        data = json.loads((folder / "round.json").read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "invalid")
        self.assertEqual(data["result"]["isolation_breaches"], ["integration-checkout", "round-data"])
        self.assertNotIn(str(repo.resolve()), json.dumps(data))

    @unittest.skipUnless(JAIL, "bubblewrap needs unprivileged user namespaces")
    def test_jail_hides_round_data_and_integration_checkout(self):
        repo, folder = self.make_repo(acceptance_passes=True)
        run(["git", "add", "."], repo)
        run(["git", "commit", "-qm", "round data"], repo)
        hidden = folder / "acceptance/test_acceptance.py"
        # The targets are written into the agent's source: paths passed as arguments would be bound read-only.
        self.steal_targets = (str(hidden), str(folder / "round.json"), str(repo / ".git/config"))
        completed = self.invoke(repo, self.make_productive(), "steal")
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        data = json.loads((folder / "round.json").read_text(encoding="utf-8"))
        self.assertEqual(data["result"]["files_changed"], ["site/agent.txt"])

    def test_refuses_productive_repository(self):
        repo, _ = self.make_repo()
        completed = self.invoke(repo, repo)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("productive checkout", completed.stderr)

    def test_refuses_hash_mismatch(self):
        repo, folder = self.make_repo()
        productive = self.make_productive()
        (folder / "task.md").write_text("changed\n", encoding="utf-8")
        completed = self.invoke(repo, productive)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("sha256 differs", completed.stderr)

    def test_failed_status_never_becomes_passed(self):
        self.assertEqual(final_status("failed", 0, ["site/a"], 1, 1, 0, []), "failed")

    def test_scope_matching_uses_path_boundaries(self):
        self.assertEqual(out_of_scope(["site/a", "site-other/a"], ["site/"]), ["site-other/a"])


if __name__ == "__main__":
    unittest.main()
