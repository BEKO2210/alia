#!/usr/bin/env python3
"""Path guard for self-evolution pull requests (changed paths on stdin, one per line).

  git diff --no-renames --name-only origin/main...HEAD \
    | python3 tools/evolution_guard.py --branch "$HEAD_REF" --messages messages.txt

It runs on every pull request. A PR is an Alia round PR when its branch is `evolution/round-N...` (N >= 1),
OR any commit message carries an `Alia-Round:` trailer, OR it changes a round folder `evolution/rounds/NN-slug/` - so renaming the
branch does not switch the guard off. Round PRs may only change an allowlist: the site, the round folders and
the known-defect baseline; everything else, including CI, the tests and this guard, is refused.
Other `evolution/*` branches (infrastructure, reviewed by a human) may not touch the Alia engine; all other
PRs pass. CI runs this script from the base branch, so a pull request cannot weaken the guard it is checked by.
"""
from __future__ import annotations

import argparse
import re
import sys

ENGINE_FILES = {"alia", "profiles.json", "install.sh", "tests/test_alia.py", ".github/workflows/pages.yml"}
ENGINE_PREFIXES = ("i18n/", "bench/")
ROUND_ALLOWED_FILES = {"sitetests/known_defects.json"}
ROUND_ALLOWED_PREFIXES = ("site/", "evolution/rounds/")
ROUND_BRANCH = re.compile(r"^evolution/round-(\d+)(?:-|$)")
ROUND_TRAILER = re.compile(r"^Alia-Round:", re.MULTILINE)
ROUND_FOLDER = re.compile(r"^evolution/rounds/\d+-")  # round data, not e.g. evolution/rounds/.gitkeep


def normalize(paths: list[str]) -> list[str]:
    return [path.strip().removeprefix("./") for path in paths if path.strip()]


def protected_paths(paths: list[str]) -> list[str]:
    return sorted(path for path in normalize(paths) if path in ENGINE_FILES or path.startswith(ENGINE_PREFIXES))


def outside_round_allowlist(paths: list[str]) -> list[str]:
    return sorted(path for path in normalize(paths)
                  if ".." in path.split("/")
                  or not (path in ROUND_ALLOWED_FILES or path.startswith(ROUND_ALLOWED_PREFIXES)))


def is_round_branch(branch: str) -> bool:
    match = ROUND_BRANCH.match(branch)
    return bool(match) and int(match.group(1)) >= 1


def is_round_pr(paths: list[str], branch: str, messages: str) -> bool:
    return (is_round_branch(branch) or bool(ROUND_TRAILER.search(messages))
            or any(ROUND_FOLDER.match(path) for path in normalize(paths)))


def blocked(paths: list[str], branch: str, messages: str = "") -> list[str]:
    if is_round_pr(paths, branch, messages):
        return outside_round_allowlist(paths)
    if branch.startswith("evolution/"):
        return protected_paths(paths)
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--branch", default="", help="head branch of the pull request")
    parser.add_argument("--messages", type=argparse.FileType("r", encoding="utf-8"),
                        help="file with the PR's commit messages")
    args = parser.parse_args(argv)
    paths = sys.stdin.read().splitlines()
    messages = args.messages.read() if args.messages else ""
    round_pr = is_round_pr(paths, args.branch, messages)
    refused = blocked(paths, args.branch, messages)
    if refused:
        kind = "outside the round allowlist" if round_pr else "protected engine paths"
        print(f"self-evolution change touches {kind}:", file=sys.stderr)
        for path in refused:
            print(f"  {path}", file=sys.stderr)
        return 1
    mode = "Alia round" if round_pr else "infrastructure" if args.branch.startswith("evolution/") else "not evolution"
    print(f"self-evolution path guard passed ({mode}, {len(normalize(paths))} path(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
