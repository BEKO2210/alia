import argparse
import json
import sys


def count(text):
    return len(text.splitlines()), len(text.split()), len(text)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    totals = [0, 0, 0]
    rows, status = [], 0
    for name in args.files:
        try:
            with open(name, encoding="utf-8") as handle:
                lines, words, chars = count(handle.read())
        except OSError as exc:
            print(f"wc.py: {name}: {exc}", file=sys.stderr)
            status = 1
            continue
        totals = [totals[0] + lines, totals[1] + words, totals[2] + chars]
        rows.append({"file": name, "lines": lines, "words": words, "chars": chars})
        if not args.json:
            print(f"{lines:7} {words:7} {chars:7} {name}")
    if len(args.files) > 1:
        if args.json:
            rows.append({"file": "total", "lines": totals[0], "words": totals[1], "chars": totals[2]})
        else:
            print(f"{totals[0]:7} {totals[1]:7} {totals[2]:7} total")
    if args.json:
        print(json.dumps(rows))
    return status


if __name__ == "__main__":
    sys.exit(main())
