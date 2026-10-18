#!/usr/bin/env python3
"""Reject protected engine paths in self-evolution pull requests."""

from __future__ import annotations

import sys


PROTECTED_FILES = {"alia", "profiles.json", "install.sh", "tests/test_alia.py", ".github/workflows/pages.yml"}
PROTECTED_PREFIXES = ("i18n/", "bench/")


def protected_paths(paths: list[str]) -> list[str]:
    normalized = [path.strip().removeprefix("./") for path in paths if path.strip()]
    return sorted(path for path in normalized if path in PROTECTED_FILES or path.startswith(PROTECTED_PREFIXES))


def main() -> int:
    blocked = protected_paths(sys.stdin.read().splitlines())
    if blocked:
        print("self-evolution changes protected paths:", file=sys.stderr)
        for path in blocked:
            print(f"  {path}", file=sys.stderr)
        return 1
    print("self-evolution path guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
