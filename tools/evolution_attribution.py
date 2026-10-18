"""Cross-check the evidence used to attribute an evolution round to Alia."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any


ALIA_AUTHOR_NAME = "Alia (Qwen3.6-35B, local)"
ALIA_AUTHOR_EMAIL = "alia@alia.invalid"
CHECK_NAMES = (
    "transcript_hash",
    "agent_commit_shape",
    "transcript_covers_diff",
    "transcript_tool_calls",
    "foreign_commits_declared",
    "share",
)


# No user/system config: diff drivers or textconv from config never run on agent content.
_GIT_ENV = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "LC_ALL": "C"}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "--no-pager", "-c", "core.hooksPath=/dev/null", "-c", "diff.external=", *args],
                          cwd=repo, capture_output=True, text=True, check=False, env=_GIT_ENV)


def _commit_exists(repo: Path, commit: Any) -> bool:
    if not isinstance(commit, str) or not commit:
        return False
    return _git(repo, "cat-file", "-e", f"{commit}^{{commit}}").returncode == 0


def _sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _numstat(repo: Path, commit: str) -> tuple[int, int] | None:
    shown = _git(repo, "show", "--format=", "--numstat", commit, "--")
    if shown.returncode:
        return None
    added = removed = 0
    for line in shown.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        plus, minus, _path = parts
        if plus.isdigit():
            added += int(plus)
        if minus.isdigit():
            removed += int(minus)
    return added, removed


def _diff_numstat(repo: Path, older: str, newer: str) -> tuple[int, int] | None:
    shown = _git(repo, "diff", "--numstat", older, newer, "--")
    if shown.returncode:
        return None
    added = removed = 0
    for line in shown.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            plus, minus, _path = parts
            added += int(plus) if plus.isdigit() else 0
            removed += int(minus) if minus.isdigit() else 0
    return added, removed


def _tool_uses(transcript: Path) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    try:
        lines = transcript.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return calls
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or (event.get("type") or event.get("event")) != "assistant":
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for item in content:
            if isinstance(item, dict) and item.get("type") == "tool_use":
                calls.append(item)
    return calls


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _command_tokens(command: str) -> set[str]:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;()<>")
        lexer.whitespace_split = True
        return set(lexer)
    except ValueError:
        return set()


def _transcript_cwd(transcript: Path) -> str | None:
    """The agent's working directory from Qwen Code's `system`/`init` event."""
    try:
        lines = transcript.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "system" and isinstance(event.get("cwd"), str):
            return event["cwd"].rstrip("/")
    return None


def _call_names_path(call: dict[str, Any], path: str, cwd: str | None) -> bool:
    """Exact names only: the repo-relative path, `./path`, or `<agent cwd>/path`.

    No basenames and no suffix matches: `echo a.txt` or `decoy/site/a.txt` must not cover `site/a.txt`.
    A file Alia changed through a command that never names it (a glob, a `cd` first) stays uncovered, which
    makes the attribution fail closed rather than credit Alia for an unexplained change.
    """
    input_data = call.get("input")
    if not isinstance(input_data, dict):
        return False
    wanted = {path, f"./{path}"} | ({f"{cwd}/{path}"} if cwd else set())
    if any(value in wanted for value in _strings(input_data)):
        return True
    command = input_data.get("command")
    return isinstance(command, str) and bool(wanted & _command_tokens(command))


def _check(ok: bool, success: str, failure: str) -> dict[str, Any]:
    return {"ok": ok, "detail": success if ok else failure}


def verify_attribution(
    repo: Path,
    folder: Path,
    data: dict[str, Any],
    head: str,
    private_root: Path,
) -> dict[str, Any]:
    """Return public-safe attribution evidence. Details never include private absolute paths."""
    transcript = private_root / folder.name / "transcript.jsonl"
    checks: dict[str, dict[str, Any]] = {}
    recorded_hash = data.get("run", {}).get("transcript_sha256")
    actual_hash = _sha256(transcript)
    hash_ok = actual_hash is not None and actual_hash == recorded_hash
    checks["transcript_hash"] = _check(
        hash_ok,
        "transcript.jsonl sha256 matches run.transcript_sha256",
        "transcript.jsonl is missing or its sha256 differs from run.transcript_sha256",
    )

    start = data.get("start_commit")
    agent = data.get("agent_commit")
    agent_exists = _commit_exists(repo, agent)
    shape_problems: list[str] = []
    agent_paths: list[str] = []
    agent_stats: tuple[int, int] | None = None
    if not agent_exists:
        shape_problems.append("agent_commit does not exist")
    else:
        parents = _git(repo, "show", "-s", "--format=%P", agent).stdout.strip().split()
        if parents != [start]:
            shape_problems.append("agent_commit must have start_commit as its single parent")
        message = _git(repo, "show", "-s", "--format=%B", agent).stdout
        round_number = int(data.get("round", 0))
        trailer = re.search(rf"(?m)^Alia-Round:\s*{round_number:02d}\s*$", message)
        if not trailer:
            shape_problems.append(f"agent_commit lacks trailer Alia-Round: {round_number:02d}")
        author = _git(repo, "show", "-s", "--format=%an%x00%ae", agent).stdout.rstrip("\n").split("\0", 1)
        if author != [ALIA_AUTHOR_NAME, ALIA_AUTHOR_EMAIL]:
            shape_problems.append("agent_commit author is not the runner's Alia identity")
        paths_result = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", agent, "--")
        agent_paths = sorted(filter(None, paths_result.stdout.splitlines()))
        recorded_paths = data.get("result", {}).get("files_changed")
        paths_match = isinstance(recorded_paths, list) and agent_paths == sorted(recorded_paths)
        if not paths_match:
            shape_problems.append("agent_commit paths differ from result.files_changed")
        agent_stats = _numstat(repo, agent)
        recorded_stats = (data.get("result", {}).get("lines_added"), data.get("result", {}).get("lines_removed"))
        if agent_stats != recorded_stats:
            shape_problems.append("agent_commit numstat differs from result line counts")
    checks["agent_commit_shape"] = _check(
        not shape_problems,
        f"agent_commit has one parent, the round trailer and Alia identity; {len(agent_paths)} changed path(s) match",
        "; ".join(shape_problems),
    )

    calls = _tool_uses(transcript)
    cwd = _transcript_cwd(transcript)
    uncovered = [path for path in agent_paths if not any(_call_names_path(call, path, cwd) for call in calls)]
    transcript_available = actual_hash is not None
    coverage_ok = transcript_available and agent_exists and not uncovered
    checks["transcript_covers_diff"] = _check(
        coverage_ok,
        f"tool calls name all {len(agent_paths)} path(s) changed by agent_commit",
        "transcript tool calls do not name changed path(s): " + ", ".join(uncovered)
        if uncovered else "transcript or agent_commit is unavailable",
    )

    recorded_calls = data.get("run", {}).get("tool_calls")
    calls_ok = (
        transcript_available
        and isinstance(recorded_calls, int)
        and not isinstance(recorded_calls, bool)
        and len(calls) == recorded_calls
    )
    checks["transcript_tool_calls"] = _check(
        calls_ok,
        f"transcript contains {len(calls)} tool_use item(s), matching run.tool_calls",
        f"transcript contains {len(calls)} tool_use item(s), but run.tool_calls is {recorded_calls!r}",
    )

    resolved = _git(repo, "rev-parse", "--verify", f"{head}^{{commit}}")
    checked_head = resolved.stdout.strip() if resolved.returncode == 0 else "0" * 40
    range_result = _git(repo, "rev-list", "--reverse", f"{start}..{checked_head}") if isinstance(start, str) else None
    commits = range_result.stdout.splitlines() if range_result is not None and range_result.returncode == 0 else []
    foreign_problems: list[str] = []
    if range_result is None or range_result.returncode:
        foreign_problems.append("start_commit..checked_head is not a valid commit range")
    if agent not in commits:
        foreign_problems.append("agent_commit is not in start_commit..checked_head")
    foreign = [commit for commit in commits if commit != agent]
    for commit in foreign:
        identity = _git(repo, "show", "-s", "--format=%an%x00%ae%x00%B", commit).stdout.split("\0", 2)
        name, email, message = identity if len(identity) == 3 else ("", "", "")
        if name == ALIA_AUTHOR_NAME or email == ALIA_AUTHOR_EMAIL or re.search(r"(?m)^Alia-Round:\s*", message):
            foreign_problems.append(f"forged Alia commit: {commit}")
    declared = {
        item.get("commit") for item in data.get("interventions", [])
        if isinstance(item, dict) and isinstance(item.get("commit"), str)
    }
    for commit in foreign:
        if commit not in declared:
            foreign_problems.append(f"undeclared intervention commit: {commit}")
    for commit in sorted(declared - set(foreign)):
        foreign_problems.append(f"declared intervention commit is outside the range: {commit}")
    checks["foreign_commits_declared"] = _check(
        not foreign_problems,
        f"{len(foreign)} non-Alia commit(s) are declared as interventions",
        "; ".join(foreign_problems),
    )

    alia_lines = sum(agent_stats) if agent_stats is not None else 0
    other_lines = 0
    missing_stats = False
    for commit in foreign:
        stats = _numstat(repo, commit)
        if stats is None:
            missing_stats = True
        else:
            other_lines += sum(stats)
    final_stats = _diff_numstat(repo, start, checked_head) if isinstance(start, str) else None
    share_ok = agent_stats is not None and not missing_stats and final_stats is not None
    final_lines = sum(final_stats) if final_stats is not None else 0
    checks["share"] = _check(
        share_ok,
        f"Alia {alia_lines} line(s); interventions {other_lines}; final diff {final_lines} line(s)",
        "could not calculate commit and final-diff line counts",
    )

    return {
        "verified": all(checks[name]["ok"] for name in CHECK_NAMES),
        "checked_head": checked_head,
        "checks": checks,
        "alia_lines": alia_lines,
        "other_lines": other_lines,
    }
