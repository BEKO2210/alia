import hashlib
from datetime import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from tools.alia_round import (
    final_status,
    RoundError,
    acquire_gpu_lock,
    check_round_ref_free,
    frozen_files,
    gpu_window_fits,
    hash_file,
    out_of_scope,
    parse_unittest,
    round_ref,
    site_report_counts,
    stop_process_group,
    stream_counts,
    write_round,
)


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
            "import argparse, json\nfrom pathlib import Path\n"
            "p=argparse.ArgumentParser(); p.add_argument('--site'); p.add_argument('--out'); a=p.parse_args(); "
            "o=Path(a.out); o.mkdir(parents=True); "
            "(o/'report.json').write_text(json.dumps({'counts': {'failures': 0, 'known': 2, 'fixed': 1}})); "
            "print('site checks: 0 failure(s)')\n",
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
        run(["git", "add", "evolution/rounds/01-example/task.md", "evolution/rounds/01-example/acceptance"], repo)
        run(["git", "commit", "-qm", "freeze round inputs"], repo)
        frozen = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
        data = {
            "round": 1,
            "slug": "example",
            "status": initial_status,
            "start_commit": start,
            "task_sha256": hash_file(folder / "task.md"),
            "acceptance": {"files": {"acceptance/test_acceptance.py": hash_file(acceptance / "test_acceptance.py")}, "frozen_commit": frozen},
            "allowed_paths": ["site/"],
            "run": {"wall_limit_seconds": 30},
            "result": {},
            "agent": {},
            "agent_commit": None,
        }
        (folder / "round.json").write_text(json.dumps(data), encoding="utf-8")
        return repo, folder

    steal_targets = ()
    mode_script = ""

    def make_agent(self):
        agent = self.root / "fake_agent.py"
        agent.write_text(
            "import json\nimport pathlib\nimport sys\n"
            "root = pathlib.Path.cwd()\n"
            "if (root / 'evolution').exists(): raise SystemExit('evolution leaked')\n"
            "(root / 'site/agent.txt').write_text('agent change\\n')\n"
            "if sys.argv[1] == 'outside': (root / 'outside.txt').write_text('outside\\n')\n"
            "if sys.argv[1] == 'peek': print(json.dumps({'type': 'tool_result', 'output': sys.argv[2]}))\n"
            "if sys.argv[1] == 'script':\n    pass\n"
            + "".join(f"    {line}\n" for line in self.mode_script.splitlines())
            + "if sys.argv[1] == 'steal':\n"
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
        before_run = json.loads((folder / "round.json").read_text(encoding="utf-8"))
        before_run["attribution"] = {"verified": True}
        (folder / "round.json").write_text(json.dumps(before_run), encoding="utf-8")
        productive = self.make_productive()
        before = self.snapshot(productive)
        completed = self.invoke(repo, productive)
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertEqual(self.snapshot(productive), before)
        data = json.loads((folder / "round.json").read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "passed")
        self.assertEqual(data["result"]["acceptance_passed"], 1)
        self.assertEqual(data["result"]["site_checks"], {"failures": 0, "known": 2, "fixed": 1})
        self.assertNotIn("attribution", data)
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
        data = json.loads((repo / "evolution/rounds/01-example/round.json").read_text(encoding="utf-8"))
        # A fresh one-commit repository built from `git archive`: no shared history, no FETCH_HEAD.
        agent_git = work / "agent-git.untrusted"  # disarmed after the run
        self.assertFalse((work / ".git").exists())
        self.assertEqual(run(["git", "--git-dir", str(agent_git), "rev-list", "--all", "--count"], work).stdout.strip(), "1")
        self.assertFalse((agent_git / "FETCH_HEAD").exists())
        self.assertFalse((agent_git / "objects/info/alternates").exists())
        self.assertFalse((work / "evolution").exists())
        # Alia's commit is built by the runner in its own repository and kept in the integration repo. A dry run
        # keeps it under refs/evolution/dry-run/, so it can never block the real round's ref.
        agent = data["agent_commit"]
        self.assertEqual(run(["git", "rev-parse", "refs/evolution/dry-run/round-01"], repo).stdout.strip(), agent)
        self.assertNotEqual(run(["git", "rev-parse", "-q", "--verify", "refs/evolution/round-01"], repo,
                                check=False).returncode, 0)
        self.assertEqual(run(["git", "rev-parse", f"{agent}~1"], repo).stdout.strip(), data["start_commit"])
        self.assertIn("Alia-Round: 01", run(["git", "show", "-s", "--format=%B", agent], repo).stdout)

    def test_agent_git_config_hooks_and_filters_never_run_on_the_host(self):
        repo, folder = self.make_repo(acceptance_passes=True)
        canary = self.root / "host-canary"
        self.mode_script = (
            "git = root / '.git'\n"
            "(git / 'hooks').mkdir(exist_ok=True)\n"
            f"payload = '#!/bin/sh\\ntouch {canary}\\n'\n"
            "for hook in ('pre-commit', 'commit-msg', 'post-commit', 'pre-auto-gc'):\n"
            "    (git / 'hooks' / hook).write_text(payload); (git / 'hooks' / hook).chmod(0o755)\n"
            "(root / 'payload.sh').write_text(payload); (root / 'payload.sh').chmod(0o755)\n"
            "with open(git / 'config', 'a') as c:\n"
            "    c.write('[core]\\n fsmonitor = ' + str(root / 'payload.sh') + '\\n[filter \"x\"]\\n clean = '"
            " + str(root / 'payload.sh') + '\\n[gpg]\\n program = ' + str(root / 'payload.sh') + '\\n')\n"
            "(root / '.gitattributes').write_text('* filter=x diff=x\\n')\n"
        )
        completed = self.invoke(repo, self.make_productive(), "script")
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertFalse(canary.exists(), "agent-written git config or hook ran on the host")
        data = json.loads((folder / "round.json").read_text(encoding="utf-8"))
        self.assertIn("site/agent.txt", data["result"]["files_changed"])

    def test_escaping_symlink_and_evolution_writes_are_caught(self):
        repo, folder = self.make_repo(acceptance_passes=True)
        self.mode_script = (
            "import os\n"
            "os.symlink('/etc/hostname', root / 'site' / 'host.txt')\n"
            "(root / 'evolution' / 'rounds').mkdir(parents=True)\n"
            "(root / 'evolution' / 'rounds' / 'fake.json').write_text('{}')\n"
        )
        completed = self.invoke(repo, self.make_productive(), "script")
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        data = json.loads((folder / "round.json").read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "invalid")
        self.assertIn("symlink-escape", data["result"]["isolation_breaches"])
        self.assertIn("evolution/rounds/fake.json", data["result"]["out_of_scope_paths"])

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

    def test_refuses_frozen_commit_that_lacks_frozen_files(self):
        repo, folder = self.make_repo()
        data = json.loads((folder / "round.json").read_text(encoding="utf-8"))
        data["acceptance"]["frozen_commit"] = data["start_commit"]
        (folder / "round.json").write_text(json.dumps(data), encoding="utf-8")
        completed = self.invoke(repo, self.make_productive())
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("frozen git bytes differ", completed.stderr)

    def test_real_round_ref_must_be_free(self):
        repo, _ = self.make_repo()
        self.assertEqual(round_ref(1, dry_run=False), "refs/evolution/round-01")
        self.assertEqual(round_ref(1, dry_run=True), "refs/evolution/dry-run/round-01")
        check_round_ref_free(repo, "refs/evolution/round-01")
        run(["git", "update-ref", "refs/evolution/round-01", "HEAD"], repo)
        with self.assertRaisesRegex(RoundError, "already exists"):
            check_round_ref_free(repo, "refs/evolution/round-01")

    def test_byte_code_cache_is_never_frozen(self):
        _, folder = self.make_repo()
        before = frozen_files(folder)
        cache = folder / "acceptance/__pycache__"
        cache.mkdir()
        (cache / "test_change.cpython-312.pyc").write_bytes(b"cache")
        self.assertEqual(frozen_files(folder), before)

    def test_failed_status_never_becomes_passed(self):
        checks = {"failures": 0, "known": 0, "fixed": 0}
        self.assertEqual(final_status("failed", 0, ["site/a"], 1, 1, checks, []), "failed")

    def test_no_change_never_passes_and_qwen_timeout_aborts(self):
        checks = {"failures": 0, "known": 0, "fixed": 0}
        self.assertEqual(final_status("planned", 0, [], 1, 1, checks, []), "failed")
        self.assertEqual(final_status("planned", 55, [], 1, 1, checks, []), "aborted")
        self.assertEqual(final_status("planned", 55, ["site/a"], 1, 1, checks, []), "failed")

    def test_stream_counts_nested_tool_use_and_unknown_stream(self):
        stream = self.root / "stream.jsonl"
        stream.write_text(
            '{"type":"assistant","message":{"content":[{"type":"tool_use"},{"type":"text"}]}}\n'
            '{"type":"result"}\n', encoding="utf-8"
        )
        self.assertEqual(stream_counts(stream)[0], 1)
        stream.write_text("not json\n", encoding="utf-8")
        self.assertEqual(stream_counts(stream), (None, None))

    def test_stream_result_stats_override_nested_count(self):
        stream = self.root / "stream.jsonl"
        stream.write_text(
            '{"type":"assistant","message":{"content":[{"type":"tool_use"}]}}\n'
            '{"type":"result","stats":{"tools":{"totalCalls":7}}}\n', encoding="utf-8"
        )
        self.assertEqual(stream_counts(stream)[0], 7)

    def test_unittest_and_site_unknowns_stay_unknown(self):
        self.assertEqual(parse_unittest("test process crashed"), (None, None))
        self.assertIsNone(site_report_counts(self.root / "missing-report.json"))

    def test_gpu_window_math(self):
        self.assertTrue(gpu_window_fits(6, 0, 900))
        self.assertTrue(gpu_window_fits(15, 0, 900))
        self.assertFalse(gpu_window_fits(15, 1, 900))
        self.assertFalse(gpu_window_fits(5, 59, 900))

    def test_gpu_lock_any_time_by_default_and_window_on_request(self):
        lock_path = self.root / "gpu.lock"
        lock = acquire_gpu_lock(lock_path, 900, 5)  # no window: returns at once whatever the minute
        lock.close()
        with mock.patch("tools.alia_round.datetime") as clock:
            clock.now.return_value = datetime(2026, 1, 1, 12, 40, 0)
            with self.assertRaises(RoundError), mock.patch("tools.alia_round.time.sleep"):
                acquire_gpu_lock(lock_path, 900, 0.01, window=True)

    def test_clean_removes_only_private_round_folder(self):
        repo, folder = self.make_repo()
        private = self.root / "private"
        target = private / folder.name
        target.mkdir(parents=True)
        (target / "kept-until-clean.txt").write_text("x", encoding="utf-8")
        completed = run(
            [sys.executable, str(RUNNER), "run", "1", "--private-root", str(private), "--clean"],
            repo, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(target.exists())
        self.assertTrue(private.exists())

    def test_round_json_write_is_atomic(self):
        folder = self.root / "atomic"
        folder.mkdir()
        write_round(folder, {"status": "failed"})
        self.assertEqual(json.loads((folder / "round.json").read_text(encoding="utf-8")), {"status": "failed"})
        self.assertFalse((folder / ".round.json.tmp").exists())

    def test_stop_process_group_terminates_session(self):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True
        )
        stop_process_group(process)
        self.assertIsNotNone(process.returncode)
        with self.assertRaises(ProcessLookupError):
            os.kill(process.pid, 0)

    def test_scope_matching_uses_path_boundaries(self):
        self.assertEqual(out_of_scope(["site/a", "site-other/a"], ["site/"]), ["site-other/a"])


if __name__ == "__main__":
    unittest.main()
