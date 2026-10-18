from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

from .browser import browser_checks
from .core import match_known, static_checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check the Alia static website")
    parser.add_argument("--site", type=Path, default=Path("site"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--static-only", action="store_true")
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    site = args.site.resolve()
    if not site.is_dir():
        raise SystemExit(f"site directory does not exist: {site}")
    if args.out is None:
        out = Path(tempfile.mkdtemp(prefix="alia-sitetests-"))
    else:
        out = args.out.resolve()
        out.mkdir(parents=True, exist_ok=True)
    findings = static_checks(site)
    if not args.static_only:
        findings.extend(asyncio.run(browser_checks(site, out)))
    known_path = Path(__file__).with_name("known_defects.json")
    known = json.loads(known_path.read_text(encoding="utf-8"))
    if args.static_only:
        known = [item for item in known if "viewport" not in item]
    new, matched, fixed = match_known(findings, known)
    report = {
        "failures": new,
        "known": matched,
        "fixed": fixed,
        "counts": {"failures": len(new), "known": len(matched), "fixed": len(fixed)},
    }
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"site checks: {len(new)} failure(s), {len(matched)} known, {len(fixed)} fixed (remove entry)")
    for label, items in (("FAIL", new), ("KNOWN", matched), ("FIXED", fixed)):
        for item in items:
            location = "/".join(str(item[key]) for key in ("page", "viewport", "lang") if item.get(key))
            print(f"{label} {item['check']} {location}: {item['detail']}")
    print(f"report: {out / 'report.json'}")
    return 1 if new else 0


def main() -> None:
    raise SystemExit(run(parse_args()))


if __name__ == "__main__":
    main()
