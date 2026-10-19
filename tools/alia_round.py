#!/usr/bin/env python3
"""Freeze and run an isolated Alia self-evolution round."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import alia_jail  # noqa: E402
from evolution_attribution import (  # noqa: E402
    ALIA_AUTHOR_EMAIL,
    ALIA_AUTHOR_NAME,
    verify_attribution,
)


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


EXPERIMENT_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
# Inside the jail: where the candidate harness file is mounted, and where the launcher keeps Qwen Code's home.
HARNESS_IN_JAIL = "/run/alia-harness.md"
QWEN_HOME_IN_HOME = ".local/state/alia/qwen-home"


def tasks_base(experiment: str | None) -> str:
    """Public rounds live in evolution/rounds; an experiment's tasks in evolution/experiments/<name>/tasks."""
    return f"evolution/experiments/{experiment}/tasks" if experiment else "evolution/rounds"


def find_round(repo: Path, number: int, experiment: str | None = None) -> Path:
    matches = sorted((repo / tasks_base(experiment)).glob(f"{number:02d}-*"))
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
    target = folder / "round.json"
    temporary = folder / ".round.json.tmp"
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def frozen_files(folder: Path) -> dict[str, str]:
    acceptance = folder / "acceptance"
    if not acceptance.is_dir():
        raise RoundError(f"missing acceptance directory: {acceptance}")
    return {
        path.relative_to(folder).as_posix(): hash_file(path)
        for path in sorted(acceptance.rglob("*"))
        if path.is_file() and not bytecode(path)
    }


def bytecode(path: Path) -> bool:
    """Python's byte-code cache, which a local test run leaves behind; it is never part of the frozen tests."""
    return "__pycache__" in path.parts or path.suffix == ".pyc"


def round_ref(number: int, dry_run: bool, experiment: str | None = None, arm: str | None = None) -> str:
    """Where the runner keeps the round commit; dry runs and experiment arms use their own namespaces, so they
    never block a real round."""
    if dry_run:
        return f"refs/evolution/dry-run/round-{number:02d}"
    if experiment:
        return f"refs/evolution/experiments/{experiment}/{arm}/round-{number:02d}"
    return f"refs/evolution/round-{number:02d}"


def check_round_ref_free(repo: Path, ref: str) -> None:
    exists = subprocess.run(["git", "rev-parse", "-q", "--verify", ref], cwd=repo, check=False, capture_output=True)
    if not exists.returncode:
        raise RoundError(f"{ref} already exists; delete it first if it is a leftover (git update-ref -d {ref})")


def freeze(repo: Path, number: int, experiment: str | None = None) -> None:
    folder = find_round(repo, number, experiment)
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


def verify_frozen(repo: Path, folder: Path, data: dict[str, Any]) -> None:
    task_hash = data.get("task_sha256")
    if not isinstance(task_hash, str) or task_hash != hash_file(folder / "task.md"):
        raise RoundError("task.md is not frozen or its sha256 differs")
    acceptance = data.get("acceptance")
    if not isinstance(acceptance, dict) or not acceptance.get("frozen_commit"):
        raise RoundError("acceptance tests have no frozen commit")
    recorded = acceptance.get("files")
    if not isinstance(recorded, dict) or recorded != frozen_files(folder):
        raise RoundError("acceptance files are not frozen or their sha256 differs")
    commit = acceptance["frozen_commit"]
    exists = subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=repo, check=False,
                            capture_output=True)
    if exists.returncode:
        raise RoundError(f"acceptance frozen commit does not exist: {commit}")
    expected = {"task.md": task_hash, **recorded}
    for relative, digest in expected.items():
        path = folder / relative
        repo_relative = path.relative_to(repo).as_posix()
        shown = subprocess.run(["git", "show", f"{commit}:{repo_relative}"], cwd=repo, check=False,
                               capture_output=True)
        if shown.returncode or hashlib.sha256(shown.stdout).hexdigest() != digest or shown.stdout != path.read_bytes():
            raise RoundError(f"frozen git bytes differ: {repo_relative}")


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


def productive_snapshot(path: Path) -> tuple[str, str, str, tuple[str | None, str | None]]:
    git_dir = Path(git_text(path, "rev-parse", "--git-dir"))
    if not git_dir.is_absolute():
        git_dir = path / git_dir
    metadata = tuple(hash_file(git_dir / name) if (git_dir / name).is_file() else None for name in ("HEAD", "config"))
    return (
        git_text(path, "rev-parse", "HEAD"),
        git_text(path, "status", "--porcelain=v1", "--untracked-files=all"),
        git_text(path, "ls-files", "-s"),
        metadata,
    )


def resolved_productive(value: Path | None) -> Path:
    if value:
        return value.resolve()
    launcher = shutil.which("alia")
    if not launcher:
        raise RoundError("cannot resolve alia on PATH; use --productive-checkout")
    return Path(launcher).resolve().parent


# Host git never runs with configuration, hooks or attributes the agent could have written: no system/global
# config, no hooks, no fsmonitor, no signing. Repository config of runner-owned repositories is ours.
SEALED_GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "commit.gpgsign=false",
              "-c", "core.attributesFile=/dev/null", "-c", "protocol.allow=never", "-c", "protocol.file.allow=always"]


def sealed_env(home: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    return {"PATH": alia_jail.PATH, "HOME": str(home), "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0", **(extra or {})}


def sealed_git(args: list[str], cwd: Path, home: Path, extra: dict[str, str] | None = None,
               **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    return command([*SEALED_GIT, *args], cwd, env=sealed_env(home, extra), **kwargs)


def create_worktree(repo: Path, work: Path, start_commit: str, round_path: str) -> None:
    """Give Alia a fresh one-commit repository of the start tree without evolution/.

    Built from `git archive`, so it shares nothing with the integration repository: no object store, no
    history, no evolution/ blobs (old rounds and examples included), no FETCH_HEAD naming the source path.
    The start commit must not contain this round's folder.
    """
    if work.exists():
        raise RoundError(f"private worktree already exists: {work}")
    home = work.parent
    exists = sealed_git(["cat-file", "-e", f"{start_commit}:{round_path}"], repo, home, check=False,
                        capture_output=True)
    if exists.returncode == 0:
        raise RoundError(f"start_commit already contains {round_path}; start from the commit before the round data")
    work.mkdir(parents=True)
    archive = sealed_git(["archive", "--format=tar", start_commit, "--", ".", ":(exclude)evolution"], repo, home,
                         capture_output=True)
    command(["tar", "-x", "-C", str(work)], work, input=archive.stdout)
    identity = {"GIT_AUTHOR_NAME": "Alia round start", "GIT_AUTHOR_EMAIL": "start@alia.invalid",
                "GIT_COMMITTER_NAME": "Alia round start", "GIT_COMMITTER_EMAIL": "start@alia.invalid"}
    sealed_git(["init", "-q"], work, home, capture_output=True)
    sealed_git(["add", "-A"], work, home, capture_output=True)
    sealed_git(["commit", "-q", "--no-verify", "-m", "start"], work, home, identity, capture_output=True)
    if (work / "evolution").exists():
        raise RoundError("agent copy contains evolution data")


def copy_agent_tree(work: Path, result: Path) -> tuple[list[str], list[str]]:
    """Copy the agent's files without its .git and without following links.

    Returns (links that point outside the work copy, which are not copied; other skipped entries: the top-level
    .git, nested .git directories, special files).
    """
    escaping: list[str] = []
    skipped: list[str] = []
    root = work.resolve()
    for current, dirs, files in os.walk(work, followlinks=False):
        here = Path(current)
        relative_dir = here.relative_to(work)
        keep = []
        for name in sorted(dirs):
            source, relative = here / name, (relative_dir / name).as_posix()
            if source.is_symlink():
                files.append(name)  # handled as a link below
            elif name == ".git":
                if relative_dir != Path("."):
                    skipped.append(relative)
            else:
                (result / relative).mkdir(parents=True, exist_ok=True)
                keep.append(name)
        dirs[:] = keep
        for name in files:
            source, relative = here / name, (relative_dir / name).as_posix()
            target = result / relative
            if source.is_symlink():
                link = os.readlink(source)
                if os.path.isabs(link) or not inside(source.parent / link, root):
                    escaping.append(relative)
                else:
                    os.symlink(link, target)
            elif source.is_file():
                shutil.copy2(source, target, follow_symlinks=False)
            else:
                skipped.append(relative)
    return sorted(escaping), sorted(skipped)


def collect_changes(repo: Path, private_round: Path, start: str, number: int, home: Path, ref: str | None = None,
                    message: str | None = None) -> tuple[list[str], int, int, str | None, list[str]]:
    """Commit the copied result in a runner-owned repository; never run git inside the agent's repository.

    Returns (changed paths, lines added, lines removed, agent commit or None, paths the agent wrote under
    evolution/, which the commit leaves out and the caller treats as out of scope).
    """
    result = private_round / "result"
    scratch = private_round / "result.git"
    sealed_git(["init", "-q", "--bare", str(scratch)], private_round, home, capture_output=True)
    sealed_git(["fetch", "-q", str(repo), f"{start}:refs/start"], scratch, home, capture_output=True)
    tree = ["--git-dir", str(scratch), "--work-tree", str(result)]
    sealed_git([*tree, "update-ref", "--no-deref", "HEAD", start], result, home, capture_output=True)
    sealed_git([*tree, "read-tree", start], result, home, capture_output=True)
    evolution = sorted(path.relative_to(result).as_posix() for path in (result / "evolution").rglob("*")
                       if not path.is_dir()) if (result / "evolution").exists() else []
    sealed_git([*tree, "add", "-A", "--", ".", ":(exclude)evolution"], result, home, capture_output=True)
    numstat = sealed_git([*tree, "diff", "--cached", "--no-renames", "--numstat", start, "--"], result, home,
                         capture_output=True, text=True).stdout
    paths, added, removed = [], 0, 0
    for line in numstat.splitlines():
        plus, minus, path = line.split("\t", 2)
        paths.append(path)
        added += int(plus) if plus.isdigit() else 0
        removed += int(minus) if minus.isdigit() else 0
    if not paths:
        return [], 0, 0, None, evolution
    identity = {"GIT_AUTHOR_NAME": ALIA_AUTHOR_NAME, "GIT_AUTHOR_EMAIL": ALIA_AUTHOR_EMAIL,
                "GIT_COMMITTER_NAME": ALIA_AUTHOR_NAME, "GIT_COMMITTER_EMAIL": ALIA_AUTHOR_EMAIL}
    message = message or f"feat(evolution): Alia round {number:02d}\n\nAlia-Round: {number:02d}"
    sealed_git([*tree, "commit", "-q", "--no-verify", "-m", message], result, home, identity, capture_output=True)
    commit = sealed_git([*tree, "rev-parse", "HEAD"], result, home, capture_output=True, text=True).stdout.strip()
    # Keep Alia's commit reachable in the integration repository for review, attribution and the PR.
    ref = ref or round_ref(number, dry_run=False)
    # A real round never overwrites an existing ref (checked before the run); a dry run may replace its own.
    force = "+" if ref.startswith("refs/evolution/dry-run/") else ""
    sealed_git(["fetch", "-q", str(scratch), f"{force}{commit}:{ref}"], repo, home, capture_output=True)
    return sorted(paths), added, removed, commit, evolution


# Strings whose appearance in the transcript means Alia looked outside its copy. The labels are public;
# the matched paths are not.
def breach_markers(repo: Path, folder: Path, private_round: Path) -> dict[str, str]:
    return {
        "integration-checkout": str(repo.resolve()),
        "round-data": folder.relative_to(repo).as_posix(),
        "acceptance-run": str(private_round / "acceptance-run"),
    }


def isolation_breaches(transcript: Path, markers: dict[str, str]) -> list[str]:
    try:
        text = transcript.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return sorted(label for label, marker in markers.items() if marker and marker in text)


def gpu_window_fits(minute: int, second: int, duration: int) -> bool:
    return minute >= 6 and minute * 60 + second + duration <= 30 * 60


def acquire_gpu_lock(path: Path, wall_limit: int, max_wait: int, window: bool = False) -> Any:
    """Hold the shared GPU lock. With `window`, also wait until the whole run fits between :06 and :30
    (clear of the hourly GPU job); Belkis allowed GPU use at any time (2026-10-18), so that is opt-in."""
    started = time.monotonic()
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        if time.monotonic() - started >= max_wait:
            raise RoundError(f"GPU lock/window wait exceeded {max_wait}s")
        lock = path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            remaining = max_wait - (time.monotonic() - started)
            if remaining <= 0:
                continue
            time.sleep(min(10, remaining))
            continue
        now = datetime.now()
        if not window or gpu_window_fits(now.minute, now.second, wall_limit + 60):
            return lock
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
        delay = (6 * 60 - (now.minute * 60 + now.second)) if now.minute < 6 else (
            66 * 60 - (now.minute * 60 + now.second)
        )
        print(f"waiting {delay}s for a GPU window that fits the run", flush=True)
        remaining = max_wait - (time.monotonic() - started)
        if remaining <= 0:
            continue
        time.sleep(min(60, delay, remaining))


def ollama_loaded_models(url: str = "http://127.0.0.1:11434/api/ps") -> list[str]:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return [item.get("name", "?") for item in json.loads(response.read()).get("models", [])]
    except (OSError, ValueError):
        return []


def ensure_real_prerequisites() -> None:
    found = subprocess.run(["pgrep", "-x", "llama-server"], check=False, capture_output=True)
    if found.returncode == 0:
        raise RoundError("refusing: another llama-server process is running")
    # Inside the jail (own network namespace) the launcher cannot unload Ollama models, so they must be gone.
    loaded = ollama_loaded_models()
    if loaded:
        raise RoundError(f"refusing: Ollama has loaded models occupying the GPU: {', '.join(loaded)}")
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
    gpu_max_wait: int,
    productive: Path,
    jail: bool = True,
    gpu_window: bool = False,
    harness: Path | None = None,
) -> tuple[int, float, Path, Path]:
    transcript = private_round / "transcript.jsonl"
    stderr_path = private_round / "agent.stderr.log"
    limit = data.get("run", {}).get("wall_limit_seconds") or 900
    if not isinstance(limit, int) or limit <= 0:
        raise RoundError("run.wall_limit_seconds must be a positive integer or null")
    home = Path.home()
    lock = None
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
        ensure_real_prerequisites()
        launcher, binds = prepare_launcher(productive, private_round, profile_id)
        config = private_round / "jail-config.json"
        prompt = (folder / "task.md").read_text(encoding="utf-8")
        inner = [str(launcher / "alia"), "--yolo", "--sandbox", "--", "-p", prompt, "--max-wall-time", f"{limit}s",
                 "-o", "stream-json"]
        outer = ["timeout", "--kill-after=30", str(limit + 60)]
    if harness is not None:
        if not jail:
            raise RoundError("--harness needs the jail (it seeds the jail's private home)")
        # Seed the candidate as the user-owned part of Qwen Code's global QWEN.md; the launcher keeps that part
        # and only appends its managed environment block. The launcher itself stays untouched.
        seed = 'mkdir -p "$1" && cp "$2" "$1/QWEN.md" && shift 2 && exec "$@"'
        inner = ["/bin/sh", "-c", seed, "seed-harness", str(home / QWEN_HOME_IN_HOME), HARNESS_IN_JAIL, *inner]
    if jail:
        prefix = alia_jail.jail_args(work, home, read_only=binds, gpu=not dry_run)
        if not dry_run:
            # Pin the frozen profile: the jail's home is empty, so this file is the whole launcher config.
            index = prefix.index("--chdir")
            target = str(home / ".config/alia/config.json")
            prefix[index:index] = ["--ro-bind", str(config), target]
        if harness is not None:
            index = prefix.index("--chdir")
            prefix[index:index] = ["--ro-bind", str(harness), HARNESS_IN_JAIL]
        args = [*outer, *prefix, "--", *inner]
    else:
        args = [*outer, *inner]
    with transcript.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = None
        try:
            if not dry_run:
                lock = acquire_gpu_lock(gpu_lock, limit, gpu_max_wait, gpu_window)
            started = time.monotonic()
            process = subprocess.Popen(
                args, cwd=work, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                start_new_session=True, close_fds=True, env=alia_jail.HOST_ENV if jail else None,
            )
            exit_code = process.wait(timeout=limit + 90)
        except subprocess.TimeoutExpired:
            stop_process_group(process)
            exit_code = 124
        except BaseException:
            stop_process_group(process)
            raise
        finally:
            if lock is not None:
                fcntl.flock(lock, fcntl.LOCK_UN)
                lock.close()
    wall = round(time.monotonic() - started, 3)
    return exit_code, wall, transcript, stderr_path


def stop_process_group(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    except ProcessLookupError:
        pass


def stream_counts(path: Path) -> tuple[int | None, dict[str, Any] | None]:
    calls = 0
    result = None
    parsed = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type") or event.get("event")
        if kind not in {"system", "assistant", "user", "result", "final_result", "tool_call", "tool-call", "tool_use"}:
            continue
        parsed = True
        if kind == "assistant":
            message = event.get("message")
            content = message.get("content", []) if isinstance(message, dict) else []
            if isinstance(content, list):
                calls += sum(isinstance(item, dict) and item.get("type") == "tool_use" for item in content)
        elif kind in {"tool_call", "tool-call", "tool_use"}:
            calls += 1
        if kind in {"result", "final_result"}:
            result = event
    if not parsed:
        return None, None
    try:
        reported_calls = result["stats"]["tools"]["totalCalls"]
        if isinstance(reported_calls, int) and not isinstance(reported_calls, bool) and reported_calls >= 0:
            calls = reported_calls
    except (KeyError, TypeError):
        pass
    return calls, result


def out_of_scope(paths: list[str], allowed: list[str]) -> list[str]:
    prefixes = [item.rstrip("/") + "/" for item in allowed]
    return [path for path in paths if not any(path == prefix[:-1] or path.startswith(prefix) for prefix in prefixes)]


def parse_unittest(output: str) -> tuple[int | None, int | None]:
    match = re.search(r"Ran (\d+) tests?", output)
    if not match:
        return None, None
    total = int(match.group(1))
    failed = sum(int(value) for value in re.findall(r"(?:failures|errors|skipped)=(\d+)", output))
    return max(0, total - failed), total


def site_report_counts(path: Path) -> dict[str, int] | None:
    try:
        counts = json.loads(path.read_text(encoding="utf-8"))["counts"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None
    if not isinstance(counts, dict) or set(counts) != {"failures", "known", "fixed"} or not all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in counts.values()
    ):
        return None
    return {key: counts[key] for key in ("failures", "known", "fixed")}


def run_tests(
    repo: Path, work: Path, folder: Path, private_round: Path
) -> tuple[int | None, int | None, dict[str, int] | None, str]:
    acceptance_run = private_round / "acceptance-run"
    shutil.copytree(folder / "acceptance", acceptance_run, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # -E -P: no PYTHON* variables and no current directory on the path, so nothing the agent wrote can shadow a
    # module. Unlike -I, the user site stays, where a local Playwright for browser acceptance tests lives; the
    # agent never had write access there (jail). HOME is the runner's, for Playwright's browser cache.
    env = {"PATH": alia_jail.PATH, "LC_ALL": "C.UTF-8", "SITE_ROOT": str(work / "site"),
           **({"HOME": os.environ["HOME"]} if "HOME" in os.environ else {})}
    unit = subprocess.run(
        [sys.executable, "-E", "-P", "-m", "unittest", "discover", "-s", str(acceptance_run), "-t", str(acceptance_run),
         "-v"],
        cwd=acceptance_run,
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
    return passed, total, site_report_counts(site_out / "report.json"), combined


def launcher_metadata(productive: Path, launcher: Path) -> tuple[str | None, str | None]:
    version = subprocess.run([sys.executable, str(launcher / "alia"), "--version"], check=False, capture_output=True,
                             text=True).stdout.strip() or None
    try:
        commit = git_text(productive, "rev-parse", "HEAD")
    except RoundError:
        commit = None
    return version, commit


def final_status(
    previous: str,
    exit_code: int,
    paths: list[str],
    passed: int | None,
    total: int | None,
    site_checks: dict[str, int] | None,
    outside: list[str],
) -> str:
    if previous == "failed":
        return "failed"
    if exit_code in {55, 124, 137} and not paths:
        return "aborted"
    if (exit_code == 0 and paths and total is not None and total > 0 and passed == total
            and site_checks is not None and site_checks["failures"] == 0 and not outside):
        return "passed"
    return "failed"


def check_experiment_args(args: argparse.Namespace) -> None:
    if args.experiment is None:
        if args.arm is not None or (args.harness is not None and not args.dry_run):
            raise RoundError("--arm and --harness belong to an experiment (--experiment NAME)")
        return
    if args.dry_run:
        raise RoundError("an experiment arm is a real run; test the harness seeding with --dry-run --harness")
    for label, value in (("--experiment", args.experiment), ("--arm", args.arm)):
        if not isinstance(value, str) or not EXPERIMENT_NAME.match(value):
            raise RoundError(f"{label} must match {EXPERIMENT_NAME.pattern}")


def execute(args: argparse.Namespace) -> None:
    check_experiment_args(args)
    repo = repo_root()
    experiment = args.experiment
    folder = find_round(repo, args.number, experiment)
    private_root = (args.private_root or Path("~/alia-evolution-private")).expanduser().resolve()
    # An experiment arm keeps everything, its record included, in the private folder; the task folder and the
    # public round records stay as they are.
    private_base = private_root / "experiments" / experiment / args.arm if experiment else private_root
    private_round = private_base / folder.name
    work = private_round / "work"
    if args.clean:
        if private_round.resolve().parent != private_base or not inside(private_round, private_root):
            raise RoundError(f"refusing to clean path outside private root: {private_round}")
        if private_round.exists():
            shutil.rmtree(private_round)
            print(f"removed private round folder: {private_round}")
        else:
            print(f"private round folder does not exist: {private_round}")
        return
    data = read_round(folder)
    verify_frozen(repo, folder, data)
    productive = resolved_productive(args.productive_checkout)
    check_safe_locations(repo, private_root, work, productive)
    before = productive_snapshot(productive)
    private_root.mkdir(parents=True, exist_ok=True)
    lock_path = private_root / ".round.lock"
    with lock_path.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RoundError("another evolution round is running") from exc
        try:
            start = data.get("start_commit")
            if not isinstance(start, str):
                raise RoundError("round.json has no start_commit")
            ref = round_ref(args.number, args.dry_run, experiment, args.arm)
            if not args.dry_run:
                # Fail now, not after a long model run that could then not store Alia's commit.
                check_round_ref_free(repo, ref)
            create_worktree(repo, work, start, folder.relative_to(repo).as_posix())
            harness = None
            if args.harness is not None:
                # A private copy: the run uses exactly the bytes whose hash goes into the record.
                harness = private_round / "harness.md"
                shutil.copyfile(args.harness.expanduser(), harness)
            started = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            exit_code, wall, transcript, _ = run_agent(
                work, folder, private_round, data, args.dry_run, args.agent_cmd, args.gpu_lock.expanduser(),
                args.gpu_max_wait, productive, jail=not args.no_jail, gpu_window=args.gpu_window, harness=harness,
            )
            verify_frozen(repo, folder, data)
            # Breaches first, from the transcript the jail wrote; nothing after this runs agent-controlled code.
            breaches = isolation_breaches(transcript, breach_markers(repo, folder, private_round))
            calls, _result_event = stream_counts(transcript)
            result_tree = private_round / "result"
            result_tree.mkdir()
            escaping, skipped = copy_agent_tree(work, result_tree)
            # The agent's .git may hold hooks or config aimed at whoever runs git there next; disarm it.
            if (work / ".git").is_dir():
                os.rename(work / ".git", work / "agent-git.untrusted")
            if escaping:
                breaches = sorted({*breaches, "symlink-escape"})
            message = None
            if experiment:
                message = (f"feat(evolution): Alia, experiment {experiment} arm {args.arm}, task {args.number:02d}"
                           f"\n\nAlia-Experiment: {experiment}/{args.arm}/{args.number:02d}")
            paths, added, removed, agent_commit, evolution_paths = collect_changes(
                repo, private_round, start, args.number, private_round, ref, message)
            allowed = data.get("allowed_paths", ["site/"])
            if not isinstance(allowed, list) or not all(isinstance(item, str) for item in allowed):
                raise RoundError("allowed_paths must be a list of strings")
            outside = sorted({*out_of_scope(paths, allowed), *evolution_paths, *skipped})
            passed, total, site_checks, _ = run_tests(repo, result_tree, folder, private_round)
            status = final_status(
                data.get("status", "planned"), exit_code, paths, passed, total, site_checks, outside
            )
            if breaches:
                status = "invalid"
            data["status"] = status
            data["agent_commit"] = agent_commit
            data.pop("attribution", None)
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
                "site_checks": site_checks,
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
            if experiment:
                data["experiment"] = {
                    "name": experiment, "arm": args.arm, "ref": ref,
                    "harness_sha256": hash_file(harness) if harness else None,
                }
                write_round(private_round, data)
            else:
                write_round(folder, data)
        except BaseException:
            print(f"private round kept for inspection: {private_round}", file=sys.stderr)
            raise
    name = f"experiment {experiment} arm {args.arm} task" if experiment else "round"
    print(f"{name} {args.number:02d}: {data['status']}; acceptance {passed}/{total}; site {site_checks}")


def verify(args: argparse.Namespace) -> bool:
    repo = repo_root()
    folder = find_round(repo, args.number)
    data = read_round(folder)
    private_root = (args.private_root or Path("~/alia-evolution-private")).expanduser().resolve()
    attribution = verify_attribution(repo, folder, data, args.head, private_root)
    data["attribution"] = attribution
    write_round(folder, data)
    for name, result in attribution["checks"].items():
        print(f"{name}: {'ok' if result['ok'] else 'CONTRADICTION'} - {result['detail']}")
    print(f"attribution: {'verified' if attribution['verified'] else 'not verified'}")
    return attribution["verified"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    freeze_parser = sub.add_parser("freeze")
    freeze_parser.add_argument("number", type=int, metavar="NN")
    freeze_parser.add_argument("--experiment", help="freeze a task of evolution/experiments/NAME/tasks")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("number", type=int, metavar="NN")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--private-root", type=Path)
    run_parser.add_argument("--productive-checkout", type=Path)
    run_parser.add_argument("--gpu-lock", type=Path, default=Path("~/reel/gpu.lock"))
    run_parser.add_argument("--gpu-max-wait", type=int, default=3600)
    run_parser.add_argument("--gpu-window", action="store_true",
                            help="only start when the whole run fits between minute 06 and 30")
    run_parser.add_argument("--clean", action="store_true")
    run_parser.add_argument("--agent-cmd", nargs="+")
    run_parser.add_argument("--no-jail", action="store_true",
                            help="dry run only: run the fake agent without bubblewrap (CI without user namespaces)")
    run_parser.add_argument("--experiment", help="run a task of evolution/experiments/NAME/tasks as a private arm")
    run_parser.add_argument("--arm", help="experiment arm label, e.g. a (current harness) or b (candidate)")
    run_parser.add_argument("--harness", type=Path,
                            help="candidate harness: seeded as the user-owned part of Qwen Code's global QWEN.md")
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("number", type=int, metavar="NN")
    verify_parser.add_argument("--head", required=True)
    verify_parser.add_argument("--private-root", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.action == "freeze":
            if args.experiment is not None and not EXPERIMENT_NAME.match(args.experiment):
                raise RoundError(f"--experiment must match {EXPERIMENT_NAME.pattern}")
            freeze(repo_root(), args.number, args.experiment)
        elif args.action == "run":
            execute(args)
        else:
            return 0 if verify(args) else 1
        return 0
    except RoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
