import argparse
import sys


def count(text):
    return len(text.splitlines()), len(text.split()), len(text)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)
    totals = [0, 0, 0]
    for name in args.files:
        with open(name, encoding="utf-8") as handle:
            lines, words, chars = count(handle.read())
        totals = [totals[0] + lines, totals[1] + words, totals[2] + chars]
        print(f"{lines:7} {words:7} {chars:7} {name}")
    if len(args.files) > 1:
        print(f"{totals[0]:7} {totals[1]:7} {totals[2]:7} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
