#!/usr/bin/env python3
"""Freeze and run an isolated Alia self-evolution round."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alia_jail  # noqa: E402


class RoundError(RuntimeError):
    pass


def command(args: list[str], cwd: Path, *, check: bool = True, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    try:
        return subprocess.run(args, cwd=cwd, check=check, **kwargs)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RoundError(f"command failed: {' '.join(args)}: {exc}") from exc


def git_text(repo: Path, *args: str) -> str:
    return command(["git", *args], repo, capture_output=True, text=True).stdout.strip()


def repo_root() -> Path:
    return Path(git_text(Path.cwd(), "rev-parse", "--show-toplevel")).resolve()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_round(repo: Path, number: int) -> Path:
    matches = sorted((repo / "evolution/rounds").glob(f"{number:02d}-*"))
    if len(matches) != 1:
        raise RoundError(f"expected one folder for round {number:02d}, found {len(matches)}")
    return matches[0]


def read_round(folder: Path) -> dict[str, Any]:
    try:
        value = json.loads((folder / "round.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RoundError(f"cannot read {folder / 'round.json'}: {exc}") from exc
    if not isinstance(value, dict):
        raise RoundError("round.json must contain an object")
    return value


def write_round(folder: Path, data: dict[str, Any]) -> None:
    (folder / "round.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def frozen_files(folder: Path) -> dict[str, str]:
    acceptance = folder / "acceptance"
    if not acceptance.is_dir():
        raise RoundError(f"missing acceptance directory: {acceptance}")
    return {
        path.relative_to(folder).as_posix(): hash_file(path)
        for path in sorted(acceptance.rglob("*"))
        if path.is_file()
    }


def freeze(repo: Path, number: int) -> None:
    folder = find_round(repo, number)
    data = read_round(folder)
    task = folder / "task.md"
    if not task.is_file():
        raise RoundError(f"missing task: {task}")
    data["task_sha256"] = hash_file(task)
    acceptance = data.setdefault("acceptance", {})
    acceptance["files"] = frozen_files(folder)
    acceptance["frozen_commit"] = git_text(repo, "rev-parse", "HEAD")
    write_round(folder, data)
    print(f"froze round {number:02d}: {len(acceptance['files'])} acceptance file(s)")


def verify_frozen(folder: Path, data: dict[str, Any]) -> None:
    task_hash = data.get("task_sha256")
    if not isinstance(task_hash, str) or task_hash != hash_file(folder / "task.md"):
        raise RoundError("task.md is not frozen or its sha256 differs")
    acceptance = data.get("acceptance")
    if not isinstance(acceptance, dict) or not acceptance.get("frozen_commit"):
        raise RoundError("acceptance tests have no frozen commit")
    recorded = acceptance.get("files")
    if not isinstance(recorded, dict) or recorded != frozen_files(folder):
        raise RoundError("acceptance files are not frozen or their sha256 differs")


def inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def check_safe_locations(repo: Path, private_root: Path, work: Path, productive: Path) -> None:
    for label, path in (("repository", repo), ("private root", private_root), ("target worktree", work)):
        if inside(path, productive):
            raise RoundError(f"refusing: {label} {path} is the productive checkout or inside it ({productive})")


def productive_snapshot(path: Path) -> tuple[str, str]:
    return git_text(path, "rev-parse", "HEAD"), git_text(path, "status", "--porcelain=v1", "--untracked-files=all")


def resolved_productive(value: Path | None) -> Path:
    if value:
        return value.resolve()
    launcher = shutil.which("alia")
    if not launcher:
        raise RoundError("cannot resolve alia on PATH; use --productive-checkout")
    return Path(launcher).resolve().parent


SPARSE_PATTERNS = "/*\n!/evolution/\n"


def create_worktree(repo: Path, work: Path, start_commit: str, round_path: str) -> None:
    """Give Alia a standalone repository holding only the start commit, without evolution/.

    A `git worktree` would share the object store, so `git show` could reveal the frozen acceptance tests;
    a depth-1 fetch of the start commit carries no other history. The start commit must not contain this
    round's folder, so the tests are not even in that single commit.
    """
    if work.exists():
        raise RoundError(f"private worktree already exists: {work}")
    exists = subprocess.run(["git", "cat-file", "-e", f"{start_commit}:{round_path}"], cwd=repo, check=False,
                            capture_output=True)
    if exists.returncode == 0:
        raise RoundError(f"start_commit already contains {round_path}; start from the commit before the round data")
    work.parent.mkdir(parents=True, exist_ok=True)
    command(["git", "init", "-q", str(work)], work.parent)
    command(["git", "config", "core.sparseCheckout", "true"], work)
    (work / ".git" / "info").mkdir(parents=True, exist_ok=True)
    (work / ".git" / "info" / "sparse-checkout").write_text(SPARSE_PATTERNS, encoding="utf-8")
    upload_pack = "git -c uploadpack.allowAnySHA1InWant=true upload-pack"
    command(["git", "fetch", "-q", "--depth", "1", "--upload-pack", upload_pack, str(repo), start_commit], work,
            capture_output=True, text=True)
    command(["git", "checkout", "-q", "--detach", start_commit], work, capture_output=True, text=True)
    if (work / "evolution").exists():
        raise RoundError("sparse checkout exposed evolution data")
    if git_text(work, "rev-list", "--all", "--count").strip() != "1":
        raise RoundError("private repository holds more than the start commit")


# Strings whose appearance in the transcript means Alia looked outside its copy. The labels are public;
# the matched paths are not.
def breach_markers(repo: Path, folder: Path, private_round: Path) -> dict[str, str]:
    return {
        "integration-checkout": str(repo.resolve()),
        "round-data": f"evolution/rounds/{folder.name}",
        "acceptance-run": str(private_round / "acceptance-run"),
    }


def isolation_breaches(transcript: Path, markers: dict[str, str]) -> list[str]:
    try:
        text = transcript.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return sorted(label for label, marker in markers.items() if marker and marker in text)


def wait_for_gpu_window() -> None:
    while True:
        minute = datetime.now().minute
        if 6 <= minute <= 30:
            return
        delay = (6 - minute) * 60 if minute < 6 else (66 - minute) * 60
        print(f"waiting {delay}s for the :06-:30 GPU window", flush=True)
        time.sleep(delay)


def ensure_real_prerequisites() -> None:
    found = subprocess.run(["pgrep", "-x", "llama-server"], check=False, capture_output=True)
    if found.returncode == 0:
        raise RoundError("refusing: another llama-server process is running")
    available = None
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            available = int(line.split()[1]) * 1024
            break
    if available is None or available < 8 * 1024**3:
        raise RoundError("refusing: MemAvailable is below 8 GiB")


def prepare_launcher(productive: Path, private_round: Path, profile_id: str) -> tuple[Path, list[Path]]:
    """Copy the installed launcher (committed files only, no .git) and list the read-only paths it needs."""
    launcher = private_round / "launcher"
    launcher.mkdir()
    archive = command(["git", "archive", "HEAD", "alia", "profiles.json", "branding", "i18n"], productive,
                      capture_output=True)
    command(["tar", "-x", "-C", str(launcher)], launcher, input=archive.stdout)
    profiles = json.loads((launcher / "profiles.json").read_text(encoding="utf-8"))
    profile = next((item for item in profiles if item.get("id") == profile_id), None)
    if profile is None:
        raise RoundError(f"profile {profile_id} not in the installed launcher's profiles.json")
    files = [Path(os.path.expanduser(candidate)) for value in profile.values() if isinstance(value, dict)
             for candidate in value.get("local_candidates", [])]
    files = [path for path in files if path.is_file()]
    if not files:
        raise RoundError(f"no local model file for profile {profile_id}")
    config = private_round / "jail-config.json"
    config.write_text(json.dumps({"profile": profile_id}) + "\n", encoding="utf-8")
    return launcher, [launcher, *alia_jail.REAL_BINDS, *files]


def agent_binds(argv: list[str]) -> list[Path]:
    """Dry run: bind the fake agent's own files (absolute paths outside /usr) read-only into the jail."""
    paths = []
    for item in argv:
        path = Path(item)
        if path.is_absolute() and path.exists() and not inside(path, Path("/usr")):
            paths.append(path)
    return paths


def run_agent(
    work: Path,
    folder: Path,
    private_round: Path,
    data: dict[str, Any],
    dry_run: bool,
    agent_cmd: list[str] | None,
    gpu_lock: Path,
    productive: Path,
    jail: bool = True,
) -> tuple[int, float, Path, Path]:
    transcript = private_round / "transcript.jsonl"
    stderr_path = private_round / "agent.stderr.log"
    limit = data.get("run", {}).get("wall_limit_seconds") or 900
    if not isinstance(limit, int) or limit <= 0:
        raise RoundError("run.wall_limit_seconds must be a positive integer or null")
    home = Path.home()
    if dry_run:
        if not agent_cmd:
            raise RoundError("--agent-cmd is required with --dry-run")
        inner, binds, outer = agent_cmd, agent_binds(agent_cmd), []
    else:
        if not jail:
            raise RoundError("a real round always runs in the jail")
        profile_id = data.get("agent", {}).get("profile")
        if not isinstance(profile_id, str):
            raise RoundError("agent.profile must name the frozen profile")
        wait_for_gpu_window()
        ensure_real_prerequisites()
        launcher, binds = prepare_launcher(productive, private_round, profile_id)
        config = private_round / "jail-config.json"
        prompt = (folder / "task.md").read_text(encoding="utf-8")
        inner = [str(launcher / "alia"), "--yolo", "--sandbox", "--", "-p", prompt, "--max-wall-time", f"{limit}s",
                 "-o", "stream-json"]
        outer = ["flock", str(gpu_lock), "timeout", "--kill-after=30", str(limit + 60)]
    if jail:
        prefix = alia_jail.jail_args(work, home, read_only=binds, gpu=not dry_run)
        if not dry_run:
            # Pin the frozen profile: the jail's home is empty, so this file is the whole launcher config.
            index = prefix.index("--chdir")
            target = str(home / ".config/alia/config.json")
            prefix[index:index] = ["--ro-bind", str(config), target]
        args = [*outer, *prefix, "--", *inner]
    else:
        args = [*outer, *inner]
    started = time.monotonic()
    with transcript.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            # The jail runs in its own PID namespace and dies with bwrap, so the llama-server it started
            # ends with it; nothing is left on the host to stop.
            completed = subprocess.run(args, cwd=work, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       check=False, timeout=limit + 90)
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            exit_code = 124
    wall = round(time.monotonic() - started, 3)
    return exit_code, wall, transcript, stderr_path


def stream_counts(path: Path) -> tuple[int, dict[str, Any] | None]:
    calls = 0
    result = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type") or event.get("event")
        if kind in {"tool_call", "tool-call", "tool_use"}:
            calls += 1
        if kind in {"result", "final_result"}:
            result = event
    return calls, result


def changed_paths(work: Path, start: str) -> list[str]:
    tracked = git_text(work, "diff", "--name-only", start, "--").splitlines()
    untracked = git_text(work, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(filter(None, tracked + untracked)))


def diff_counts(work: Path, start: str, paths: list[str]) -> tuple[int, int]:
    added = removed = 0
    output = git_text(work, "diff", "--numstat", start, "--")
    tracked = set()
    for line in output.splitlines():
        plus, minus, path = line.split("\t", 2)
        tracked.add(path)
        if plus.isdigit():
            added += int(plus)
        if minus.isdigit():
            removed += int(minus)
    for relative in set(paths) - tracked:
        try:
            added += len((work / relative).read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError):
            pass
    return added, removed


def out_of_scope(paths: list[str], allowed: list[str]) -> list[str]:
    prefixes = [item.rstrip("/") + "/" for item in allowed]
    return [path for path in paths if not any(path == prefix[:-1] or path.startswith(prefix) for prefix in prefixes)]


def commit_changes(work: Path, number: int, paths: list[str]) -> str | None:
    if not paths:
        return None
    command(["git", "add", "-A"], work)
    message = f"feat(evolution): Alia round {number:02d}\n\nAlia-Round: {number:02d}"
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "Alia (Qwen3.6-35B, local)",
        "GIT_AUTHOR_EMAIL": "alia@alia.invalid",
        "GIT_COMMITTER_NAME": "Alia (Qwen3.6-35B, local)",
        "GIT_COMMITTER_EMAIL": "alia@alia.invalid",
    })
    command(["git", "commit", "-m", message], work, env=env, capture_output=True, text=True)
    return git_text(work, "rev-parse", "HEAD")


def parse_unittest(output: str) -> tuple[int, int]:
    match = re.search(r"Ran (\d+) tests?", output)
    total = int(match.group(1)) if match else 0
    failed = sum(int(value) for value in re.findall(r"(?:failures|errors|skipped)=(\d+)", output))
    return max(0, total - failed), total


def run_tests(repo: Path, work: Path, folder: Path, private_round: Path) -> tuple[int, int, int, str]:
    acceptance_run = private_round / "acceptance-run"
    shutil.copytree(folder / "acceptance", acceptance_run)
    env = os.environ.copy()
    env["SITE_ROOT"] = str(work / "site")
    unit = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(acceptance_run), "-v"],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    site_out = private_round / "site-report"
    site = subprocess.run(
        [sys.executable, "-m", "sitetests", "--site", str(work / "site"), "--out", str(site_out)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = f"ACCEPTANCE\n{unit.stdout}{unit.stderr}\nSITE\n{site.stdout}{site.stderr}"
    (private_round / "tests.txt").write_text(combined, encoding="utf-8")
    passed, total = parse_unittest(unit.stdout + unit.stderr)
    return passed, total, site.returncode, combined


def launcher_metadata(productive: Path, launcher: Path) -> tuple[str | None, str | None]:
    version = subprocess.run([sys.executable, str(launcher / "alia"), "--version"], check=False, capture_output=True,
                             text=True).stdout.strip() or None
    try:
        commit = git_text(productive, "rev-parse", "HEAD")
    except RoundError:
        commit = None
    return version, commit


def final_status(previous: str, exit_code: int, paths: list[str], passed: int, total: int, site_code: int, outside: list[str]) -> str:
    if previous == "failed":
        return "failed"
    if exit_code in {124, 137} and not paths:
        return "aborted"
    if exit_code == 0 and total > 0 and passed == total and site_code == 0 and not outside:
        return "passed"
    return "failed"


def execute(args: argparse.Namespace) -> None:
    repo = repo_root()
    folder = find_round(repo, args.number)
    data = read_round(folder)
    verify_frozen(folder, data)
    productive = resolved_productive(args.productive_checkout)
    private_root = (args.private_root or Path("~/alia-evolution-private")).expanduser().resolve()
    private_round = private_root / folder.name
    work = private_round / "work"
    check_safe_locations(repo, private_root, work, productive)
    before = productive_snapshot(productive)
    private_root.mkdir(parents=True, exist_ok=True)
    lock_path = private_root / ".round.lock"
    with lock_path.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RoundError("another evolution round is running") from exc
        start = data.get("start_commit")
        if not isinstance(start, str):
            raise RoundError("round.json has no start_commit")
        create_worktree(repo, work, start, folder.relative_to(repo).as_posix())
        started = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        exit_code, wall, transcript, _ = run_agent(
            work, folder, private_round, data, args.dry_run, args.agent_cmd, args.gpu_lock.expanduser(), productive,
            jail=not args.no_jail,
        )
        calls, _result_event = stream_counts(transcript)
        paths = changed_paths(work, start)
        allowed = data.get("allowed_paths", ["site/"])
        if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
            raise RoundError("allowed_paths must be a list of strings")
        outside = out_of_scope(paths, allowed)
        added, removed = diff_counts(work, start, paths)
        agent_commit = commit_changes(work, args.number, paths)
        passed, total, site_code, _ = run_tests(repo, work, folder, private_round)
        status = final_status(data.get("status", "planned"), exit_code, paths, passed, total, site_code, outside)
        breaches = isolation_breaches(transcript, breach_markers(repo, folder, private_round))
        if breaches:
            status = "invalid"
        data["status"] = status
        data["agent_commit"] = agent_commit
        run = data.setdefault("run", {})
        run.update({
            "started": started,
            "wall_seconds": wall,
            "exit_code": exit_code,
            "tool_calls": calls,
            "transcript_sha256": hash_file(transcript),
        })
        result = data.setdefault("result", {})
        result.update({
            "acceptance_passed": passed,
            "acceptance_total": total,
            "site_checks": {"failures": 0 if site_code == 0 else 1},
            "files_changed": paths,
            "lines_added": added,
            "lines_removed": removed,
            "out_of_scope_paths": outside,
            "isolation_breaches": breaches,
        })
        if not args.dry_run:
            version, launcher_commit = launcher_metadata(productive, private_round / "launcher")
            data.setdefault("agent", {}).update({"alia_version": version, "launcher_commit": launcher_commit})
    after = productive_snapshot(productive)
    if before != after:
        raise RoundError("productive checkout changed during the round")
    write_round(folder, data)
    print(f"round {args.number:02d}: {data['status']}; acceptance {passed}/{total}; site exit {site_code}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    freeze_parser = sub.add_parser("freeze")
    freeze_parser.add_argument("number", type=int, metavar="NN")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("number", type=int, metavar="NN")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--private-root", type=Path)
    run_parser.add_argument("--productive-checkout", type=Path)
    run_parser.add_argument("--gpu-lock", type=Path, default=Path("~/reel/gpu.lock"))
    run_parser.add_argument("--agent-cmd", nargs="+")
    run_parser.add_argument("--no-jail", action="store_true",
                            help="dry run only: run the fake agent without bubblewrap (CI without user namespaces)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.action == "freeze":
            freeze(repo_root(), args.number)
        else:
            execute(args)
        return 0
    except RoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
