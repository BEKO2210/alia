#!/usr/bin/env python3
"""Path guard for self-evolution pull requests (changed paths on stdin, one per line).

  git diff --no-renames --name-only origin/main...HEAD | python3 tools/evolution_guard.py --branch evolution/round-3

- Alia round branches (`evolution/round-N...`, N >= 1) may only change an allowlist: the site, the round
  folders and the known-defect baseline. Everything else, including CI, the tests and this guard, is refused.
- Other `evolution/*` branches (infrastructure, reviewed by a human) may not touch the Alia engine.
CI runs this script from the base branch, so a pull request cannot weaken the guard it is checked by.
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


def blocked(paths: list[str], branch: str) -> list[str]:
    return outside_round_allowlist(paths) if is_round_branch(branch) else protected_paths(paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--branch", default="", help="head branch of the pull request")
    args = parser.parse_args(argv)
    refused = blocked(sys.stdin.read().splitlines(), args.branch)
    if refused:
        kind = "outside the round allowlist" if is_round_branch(args.branch) else "protected engine paths"
        print(f"self-evolution change touches {kind}:", file=sys.stderr)
        for path in refused:
            print(f"  {path}", file=sys.stderr)
        return 1
    print("self-evolution path guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
