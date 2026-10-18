#!/usr/bin/env python3
"""Validate self-evolution rounds and generate their public data."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import ipaddress
import json
import re
import subprocess
import sys
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Any


STATUSES = {"planned", "running", "passed", "failed", "aborted", "invalid"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", re.IGNORECASE)
IP_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
IPV6_RE = re.compile(r"(?<![\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![\w:])", re.IGNORECASE)
PATH_RE = re.compile(r"(?<![\w.-])(?:/home|/Users|/root|/tmp|[A-Za-z]:\\Users)(?=[/\\]|\b)", re.IGNORECASE)
ABSOLUTE_PATH_RE = re.compile(r"(?:^|[\s=(\"'])/(?!/)\S+|(?:^|[\s=(\"'])[A-Za-z]:[/\\]\S+")
HOME_TILDE_RE = re.compile(r"(?<![\w.-])~[\w.-]*/")
TOKEN_RE = re.compile(
    r"(?:sk-|ghp_|gho_|ghu_|ghs_|ghr_|github_pat_|hf_|xox[abpr]-|AKIA[0-9A-Z]{12,}|Bearer )"
)
ATTRIBUTION_CHECKS = {
    "transcript_hash", "agent_commit_shape", "transcript_covers_diff", "transcript_tool_calls",
    "foreign_commits_declared", "share",
}


class ValidationError(ValueError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(value: Any, expected: Any, field: str, nullable: bool = False) -> Any:
    if value is None and nullable:
        return value
    if not isinstance(value, expected) or (isinstance(value, bool) and expected is not bool):
        names = expected.__name__ if isinstance(expected, type) else str(expected)
        raise ValidationError(f"{field} must be {names}{' or null' if nullable else ''}")
    return value


def require_keys(data: dict[str, Any], keys: tuple[str, ...], field: str = "round") -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise ValidationError(f"{field} missing field(s): {', '.join(missing)}")


def check_sha(value: Any, field: str, *, git: bool = False, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    require(value, str, field)
    pattern = GIT_SHA_RE if git else SHA256_RE
    if not pattern.fullmatch(value):
        raise ValidationError(f"{field} is not a valid {'git' if git else 'sha256'} hash")


def validate_round(folder: Path) -> dict[str, Any]:
    try:
        data = json.loads((folder / "round.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{folder}: cannot read round.json: {exc}") from exc
    require(data, dict, "round")
    required = (
        "schema", "round", "slug", "title", "level", "status", "task_sha256", "acceptance", "agent",
        "start_commit", "agent_commit", "run", "result", "interventions", "reviews", "summary", "merged_commit",
    )
    require_keys(data, required)
    schema = require(data["schema"], int, "schema")
    if schema != 1:
        raise ValidationError(f"unsupported schema version: {schema}")
    number = require(data["round"], int, "round")
    if not 1 <= number:
        raise ValidationError("round must be positive")
    folder_number = folder.name.split("-", 1)[0]
    if not folder_number.isdigit() or int(folder_number) != number:
        raise ValidationError(f"round {number} does not match folder {folder.name}")
    require(data["slug"], str, "slug")
    if folder.name != f"{number:02d}-{data['slug']}":
        raise ValidationError(f"slug does not match folder {folder.name}")
    bilingual(data["title"], "title")
    level = require(data["level"], int, "level")
    if level not in range(1, 6):
        raise ValidationError("level must be from 1 to 5")
    require(data["status"], str, "status")
    if data["status"] not in STATUSES:
        raise ValidationError(f"status must be one of {sorted(STATUSES)}")
    check_sha(data["task_sha256"], "task_sha256")
    task = folder / "task.md"
    if not task.is_file() or sha256(task) != data["task_sha256"]:
        raise ValidationError("task.md sha256 does not match task_sha256")
    validate_acceptance(data["acceptance"], folder)
    validate_agent(data["agent"])
    for field in ("start_commit",):
        check_sha(data[field], field, git=True)
    for field in ("agent_commit", "merged_commit"):
        check_sha(data[field], field, git=True, nullable=True)
    validate_run(data["run"])
    validate_result(data["result"])
    if "attribution" in data:
        validate_attribution(data["attribution"])
    if data["status"] == "passed":
        if "attribution" not in data or not data["attribution"]["verified"]:
            raise ValidationError("passed round requires verified attribution")
        if data["run"]["exit_code"] != 0:
            raise ValidationError("passed round has a non-zero or unknown exit code")
        passed = data["result"]["acceptance_passed"]
        total = data["result"]["acceptance_total"]
        if passed is None or total is None or total == 0 or passed != total:
            raise ValidationError("passed round has failing, missing or unknown acceptance tests")
        site_checks = data["result"]["site_checks"]
        if site_checks is None or site_checks["failures"] != 0:
            raise ValidationError("passed round has failing, missing or unknown site checks")
        if not data["result"]["files_changed"]:
            raise ValidationError("passed round has no changed files")
        if data["result"]["out_of_scope_paths"] != []:
            raise ValidationError("passed round has out-of-scope changes or isolation breaches")
        if data["result"].get("isolation_breaches") != []:
            raise ValidationError("passed round has out-of-scope changes or isolation breaches (isolation_breaches must be recorded and empty)")
    if data["status"] not in {"planned", "running"}:
        # Recompute the scope from the changed files instead of trusting the stored list.
        allowed = data.get("allowed_paths", ["site/"])
        if not isinstance(allowed, list) or not all(isinstance(item, str) and item for item in allowed):
            raise ValidationError("allowed_paths must be a list of path prefixes")
        prefixes = tuple(item.rstrip("/") + "/" for item in allowed)
        changed = data["result"]["files_changed"] or []
        outside = sorted(path for path in changed if ".." in path.split("/") or not path.startswith(prefixes))
        if not set(outside) <= set(data["result"]["out_of_scope_paths"] or []):
            raise ValidationError(f"out_of_scope_paths does not list changed files outside {list(allowed)}")
    validate_records(data["interventions"], ("by", "commit", "what"), "interventions")
    for index, item in enumerate(data["interventions"]):
        check_sha(item["commit"], f"interventions[{index}].commit", git=True, nullable=True)
    validate_records(data["reviews"], ("by", "verdict", "file"), "reviews")
    for index, review in enumerate(data["reviews"]):
        review_path = (folder / review["file"]).resolve()
        try:
            review_path.relative_to((folder / "reviews").resolve())
        except ValueError as exc:
            raise ValidationError(f"reviews[{index}].file must be under reviews/") from exc
        if not review_path.is_file():
            raise ValidationError(f"reviews[{index}].file does not exist: {review['file']}")
    bilingual(data["summary"], "summary")
    if not (folder / "summary.md").is_file():
        raise ValidationError("missing summary.md")
    return data


def bilingual(value: Any, field: str) -> None:
    require(value, dict, field)
    require_keys(value, ("en", "de"), field)
    if set(value) != {"en", "de"}:
        raise ValidationError(f"{field} must contain exactly en and de")
    require(value["en"], str, f"{field}.en")
    require(value["de"], str, f"{field}.de")


def validate_acceptance(value: Any, folder: Path) -> None:
    require(value, dict, "acceptance")
    require_keys(value, ("files", "frozen_commit"), "acceptance")
    files = require(value["files"], dict, "acceptance.files")
    check_sha(value["frozen_commit"], "acceptance.frozen_commit", git=True)
    actual = {path.relative_to(folder).as_posix(): sha256(path) for path in sorted((folder / "acceptance").rglob("*")) if path.is_file()}
    if set(files) != set(actual):
        raise ValidationError(f"acceptance file list differs: recorded={sorted(files)}, actual={sorted(actual)}")
    for path, digest in files.items():
        check_sha(digest, f"acceptance.files[{path}]")
        if digest != actual[path]:
            raise ValidationError(f"acceptance file sha256 mismatch: {path}")


def validate_agent(value: Any) -> None:
    require(value, dict, "agent")
    keys = ("name", "alia_version", "launcher_commit", "profile", "model", "hardware")
    require_keys(value, keys, "agent")
    for key in ("name", "alia_version", "profile", "model", "hardware"):
        require(value[key], str, f"agent.{key}", nullable=True)
    check_sha(value["launcher_commit"], "agent.launcher_commit", git=True, nullable=True)


def validate_run(value: Any) -> None:
    require(value, dict, "run")
    keys = ("started", "wall_seconds", "wall_limit_seconds", "exit_code", "tool_calls", "transcript_sha256")
    require_keys(value, keys, "run")
    require(value["started"], str, "run.started", nullable=True)
    for key in ("wall_seconds", "wall_limit_seconds", "exit_code", "tool_calls"):
        require(value[key], int | float if key == "wall_seconds" else int, f"run.{key}", nullable=True)
    check_sha(value["transcript_sha256"], "run.transcript_sha256", nullable=True)


def validate_result(value: Any) -> None:
    require(value, dict, "result")
    keys = (
        "acceptance_passed", "acceptance_total", "site_checks", "files_changed", "lines_added", "lines_removed",
        "out_of_scope_paths",
    )
    require_keys(value, keys, "result")
    for key in ("acceptance_passed", "acceptance_total", "lines_added", "lines_removed"):
        item = require(value[key], int, f"result.{key}", nullable=True)
        if item is not None and item < 0:
            raise ValidationError(f"result.{key} must not be negative")
    passed, total = value["acceptance_passed"], value["acceptance_total"]
    if passed is not None and total is not None and passed > total:
        raise ValidationError("result.acceptance_passed exceeds acceptance_total")
    site_checks = require(value["site_checks"], dict, "result.site_checks", nullable=True)
    if site_checks is not None:
        if set(site_checks) != {"failures", "known", "fixed"}:
            raise ValidationError("result.site_checks must contain failures, known and fixed")
        if not all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in site_checks.values()):
            raise ValidationError("result.site_checks values must be non-negative integers")
    for key in ("files_changed", "out_of_scope_paths", "isolation_breaches"):
        if key not in value:
            continue
        items = require(value[key], list, f"result.{key}", nullable=True)
        if items is not None and not all(isinstance(item, str) for item in items):
            raise ValidationError(f"result.{key} must contain strings")


def validate_records(value: Any, keys: tuple[str, ...], field: str) -> None:
    require(value, list, field)
    for index, item in enumerate(value):
        require(item, dict, f"{field}[{index}]")
        require_keys(item, keys, f"{field}[{index}]")
        for key in keys:
            require(item[key], str, f"{field}[{index}].{key}", nullable=key == "commit")


def validate_attribution(value: Any) -> None:
    require(value, dict, "attribution")
    expected = {"verified", "checked_head", "checks", "alia_lines", "other_lines"}
    if set(value) != expected:
        raise ValidationError("attribution must contain only verified, checked_head, checks, alia_lines and other_lines")
    require(value["verified"], bool, "attribution.verified")
    check_sha(value["checked_head"], "attribution.checked_head", git=True)
    checks = require(value["checks"], dict, "attribution.checks")
    if set(checks) != ATTRIBUTION_CHECKS:
        raise ValidationError(f"attribution.checks must contain exactly {sorted(ATTRIBUTION_CHECKS)}")
    for name, result in checks.items():
        require(result, dict, f"attribution.checks.{name}")
        if set(result) != {"ok", "detail"}:
            raise ValidationError(f"attribution.checks.{name} must contain only ok and detail")
        require(result["ok"], bool, f"attribution.checks.{name}.ok")
        detail = require(result["detail"], str, f"attribution.checks.{name}.detail")
        if ABSOLUTE_PATH_RE.search(privacy_text(detail)):
            raise ValidationError(f"attribution.checks.{name}.detail must not contain absolute paths")
    if value["verified"] != all(result["ok"] for result in checks.values()):
        raise ValidationError("attribution.verified must equal the combined check results")
    for field in ("alia_lines", "other_lines"):
        amount = require(value[field], int, f"attribution.{field}")
        if amount < 0:
            raise ValidationError(f"attribution.{field} must not be negative")


PUBLIC_KEYS = (
    "schema", "round", "slug", "title", "level", "status", "task_sha256", "acceptance", "agent", "start_commit",
    "agent_commit", "run", "result", "interventions", "reviews", "summary", "merged_commit", "attribution",
)


def public_round(data: dict[str, Any]) -> dict[str, Any]:
    nested = {"acceptance", "agent", "run", "result", "interventions", "reviews", "attribution"}
    public = {key: data[key] for key in PUBLIC_KEYS if key not in nested}
    public["acceptance"] = {
        "files": data["acceptance"]["files"],
        "frozen_commit": data["acceptance"]["frozen_commit"],
    }
    public["agent"] = {key: data["agent"][key] for key in ("name", "alia_version", "launcher_commit", "profile", "model", "hardware")}
    public["run"] = {key: data["run"][key] for key in ("started", "wall_seconds", "wall_limit_seconds", "exit_code", "tool_calls", "transcript_sha256")}
    public["result"] = {key: data["result"][key] for key in ("acceptance_passed", "acceptance_total", "site_checks", "files_changed", "lines_added", "lines_removed", "out_of_scope_paths")}
    if "isolation_breaches" in data["result"]:
        public["result"]["isolation_breaches"] = data["result"]["isolation_breaches"]
    public["interventions"] = [{key: item[key] for key in ("by", "commit", "what")} for item in data["interventions"]]
    public["reviews"] = [{key: item[key] for key in ("by", "verdict", "file")} for item in data["reviews"]]
    if "attribution" in data:
        attribution = data["attribution"]
        public["attribution"] = {
            "verified": attribution["verified"],
            "checked_head": attribution["checked_head"],
            "checks": {
                name: {"ok": result["ok"], "detail": result["detail"]}
                for name, result in attribution["checks"].items()
            },
            "alia_lines": attribution["alia_lines"],
            "other_lines": attribution["other_lines"],
        }
    return public


def privacy_text(text: str) -> str:
    """Normalise before matching: percent-decoding, NFKC, every slash-like code point to "/", no format chars."""
    normalized = unicodedata.normalize("NFKC", urllib.parse.unquote(text))
    out = []
    for character in normalized:
        if unicodedata.category(character) == "Cf":
            continue
        name = unicodedata.name(character, "")
        out.append("/" if character != "/" and ("SOLIDUS" in name or "SLASH" in name) and "BACK" not in name
                   else character)
    return "".join(out)


def published_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from published_strings(key)
            yield from published_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from published_strings(item)


def privacy_check(text: str) -> None:
    text = privacy_text(text)
    if PATH_RE.search(text) or HOME_TILDE_RE.search(text):
        raise ValidationError("privacy gate: home or temporary path")
    if "-----BEGIN " in text and "PRIVATE KEY" in text:
        raise ValidationError("privacy gate: private key")
    if TOKEN_RE.search(text):
        raise ValidationError("privacy gate: token")
    for address in EMAIL_RE.findall(text):
        local, domain = address.lower().rsplit("@", 1)
        if address.lower() != "alia@alia.invalid" and not (local and domain == "users.noreply.github.com"):
            raise ValidationError("privacy gate: e-mail address")
    for raw in IP_RE.findall(text):
        try:
            octets = [int(part, 10) for part in raw.split(".")]
            if any(part > 255 for part in octets):
                continue
            address = ipaddress.ip_address(".".join(map(str, octets)))
        except (ValueError, IndexError):
            continue
        if address.is_private or address in ipaddress.ip_network("100.64.0.0/10"):
            raise ValidationError("privacy gate: private or tailnet IP")
    for raw in IPV6_RE.findall(text):
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if address in ipaddress.ip_network("fc00::/7") or address.is_link_local:
            raise ValidationError("privacy gate: private or link-local IP")


def verify_git_freeze(repo: Path, folder: Path, data: dict[str, Any]) -> None:
    commit = data["acceptance"]["frozen_commit"]
    exists = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=repo, capture_output=True, check=False
    )
    if exists.returncode:
        raise ValidationError(f"acceptance.frozen_commit does not exist: {commit}")
    expected = {"task.md": data["task_sha256"], **data["acceptance"]["files"]}
    for relative, digest in expected.items():
        path = folder / relative
        repo_relative = path.relative_to(repo).as_posix()
        shown = subprocess.run(
            ["git", "show", f"{commit}:{repo_relative}"], cwd=repo, capture_output=True, check=False
        )
        if shown.returncode or hashlib.sha256(shown.stdout).hexdigest() != digest or shown.stdout != path.read_bytes():
            raise ValidationError(f"frozen git bytes differ: {repo_relative}")


TERMINAL_FAILURES = {"failed", "aborted", "invalid"}


def check_against_base(repo: Path, folder: Path, data: dict[str, Any], base: str) -> None:
    """A round that the base branch records as failed, aborted or invalid can never be relabelled."""
    relative = folder.relative_to(repo).as_posix()
    shown = subprocess.run(["git", "show", f"{base}:{relative}/round.json"], cwd=repo, capture_output=True,
                           text=True, check=False)
    if shown.returncode:
        return
    try:
        before = json.loads(shown.stdout).get("status")
    except (json.JSONDecodeError, AttributeError):
        return
    if before in TERMINAL_FAILURES and data["status"] != before:
        raise ValidationError(f"{relative}: status {before} on {base} cannot change to {data['status']}")


def check_agent_commit(repo: Path, folder: Path, data: dict[str, Any]) -> None:
    """Public re-check of the git part of the attribution (the transcript part needs the private copy)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from evolution_attribution import verify_attribution  # noqa: PLC0415

    result = verify_attribution(repo, folder, data, "HEAD", repo / ".no-private-transcripts")
    shape = result["checks"]["agent_commit_shape"]
    if not shape["ok"]:
        raise ValidationError(f"{folder.name}: agent_commit does not match the round: {shape['detail']}")


def generate(rounds_dir: Path, repo: Path | None = None, base: str | None = None) -> bytes:
    folders = [folder for folder in rounds_dir.iterdir() if folder.is_dir() and (folder / "round.json").is_file()]
    rounds = [validate_round(folder) for folder in folders]
    if repo is not None:
        repo = repo.resolve()
        for folder, data in zip(folders, rounds, strict=True):
            if data["status"] != "planned":
                verify_git_freeze(repo, folder.resolve(), data)
            if data["status"] == "passed":
                check_agent_commit(repo, folder.resolve(), data)
            if base:
                check_against_base(repo, folder.resolve(), data, base)
    rounds.sort(key=lambda item: item["round"])
    numbers = [item["round"] for item in rounds]
    if len(numbers) != len(set(numbers)):
        raise ValidationError("duplicate round number")
    public = [public_round(item) for item in rounds]
    for item in published_strings(public):
        privacy_check(item)
    text = json.dumps(public, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return text.encode()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=Path)
    parser.add_argument("--out", type=Path, default=Path("site/evolution/data/rounds.json"))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--base", help="git ref whose failed/aborted/invalid rounds must keep their status")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repo = None
        if args.rounds is None:
            root = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"], check=True, capture_output=True, text=True
            ).stdout.strip()
            repo = Path(root).resolve()
        rounds = args.rounds or repo / "evolution/rounds"
        content = generate(rounds, repo=repo, base=args.base if repo else None)
        if args.check:
            existing = args.out.read_bytes() if args.out.exists() else b""
            if existing != content:
                diff = difflib.unified_diff(existing.decode(errors="replace").splitlines(), content.decode().splitlines(), fromfile=str(args.out), tofile="generated")
                print("round data is out of date:\n" + "\n".join(diff), file=sys.stderr)
                return 1
            print(f"round data is current: {args.out}")
            return 0
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(content)
        print(f"wrote {len(json.loads(content))} round(s) to {args.out}")
        return 0
    except (OSError, subprocess.CalledProcessError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
