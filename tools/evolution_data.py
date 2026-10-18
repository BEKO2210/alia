#!/usr/bin/env python3
"""Validate self-evolution rounds and generate their public data."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import ipaddress
import json
import re
import sys
from pathlib import Path
from typing import Any


STATUSES = {"planned", "running", "passed", "failed", "aborted"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
IP_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
FORBIDDEN_TEXT = ("/home/", "/Users/", "/root/", "/tmp/", "C:\\Users", "sk-", "ghp_", "github_pat_", "Bearer ")


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
    if not isinstance(value, expected) or isinstance(value, bool):
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
    if data["status"] == "passed":
        passed = data["result"]["acceptance_passed"]
        total = data["result"]["acceptance_total"]
        if passed is None or total is None or passed < total:
            raise ValidationError("passed round has failing or unknown acceptance tests")
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
    site_checks = require(value["site_checks"], int | dict, "result.site_checks", nullable=True)
    if isinstance(site_checks, dict) and not all(isinstance(key, str) and isinstance(item, int) and not isinstance(item, bool) for key, item in site_checks.items()):
        raise ValidationError("result.site_checks must map strings to integers")
    for key in ("files_changed", "out_of_scope_paths"):
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


PUBLIC_KEYS = (
    "schema", "round", "slug", "title", "level", "status", "task_sha256", "acceptance", "agent", "start_commit",
    "agent_commit", "run", "result", "interventions", "reviews", "summary", "merged_commit",
)


def public_round(data: dict[str, Any]) -> dict[str, Any]:
    public = {key: data[key] for key in PUBLIC_KEYS if key not in {"acceptance", "agent", "run", "result", "interventions", "reviews"}}
    public["acceptance"] = {
        "files": data["acceptance"]["files"],
        "frozen_commit": data["acceptance"]["frozen_commit"],
    }
    public["agent"] = {key: data["agent"][key] for key in ("name", "alia_version", "launcher_commit", "profile", "model", "hardware")}
    public["run"] = {key: data["run"][key] for key in ("started", "wall_seconds", "wall_limit_seconds", "exit_code", "tool_calls", "transcript_sha256")}
    public["result"] = {key: data["result"][key] for key in ("acceptance_passed", "acceptance_total", "site_checks", "files_changed", "lines_added", "lines_removed", "out_of_scope_paths")}
    public["interventions"] = [{key: item[key] for key in ("by", "commit", "what")} for item in data["interventions"]]
    public["reviews"] = [{key: item[key] for key in ("by", "verdict", "file")} for item in data["reviews"]]
    return public


def privacy_check(text: str) -> None:
    for marker in FORBIDDEN_TEXT:
        if marker.lower() in text.lower():
            raise ValidationError(f"privacy gate: forbidden string {marker!r}")
    for address in EMAIL_RE.findall(text):
        _local, domain = address.rsplit("@", 1)
        if domain != "users.noreply.github.com" and not domain.endswith(".invalid"):
            raise ValidationError("privacy gate: e-mail address")
    for raw in IP_RE.findall(text):
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if address.is_private or address in ipaddress.ip_network("100.64.0.0/10"):
            raise ValidationError("privacy gate: private or tailnet IP")


def generate(rounds_dir: Path) -> bytes:
    rounds = [validate_round(folder) for folder in rounds_dir.iterdir() if folder.is_dir() and (folder / "round.json").is_file()]
    rounds.sort(key=lambda item: item["round"])
    numbers = [item["round"] for item in rounds]
    if len(numbers) != len(set(numbers)):
        raise ValidationError("duplicate round number")
    text = json.dumps([public_round(item) for item in rounds], indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    privacy_check(text)
    return text.encode()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=Path, default=Path("evolution/rounds"))
    parser.add_argument("--out", type=Path, default=Path("site/evolution/data/rounds.json"))
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        content = generate(args.rounds)
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
    except (OSError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
