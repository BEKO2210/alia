#!/usr/bin/env bash
set -euo pipefail

root_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
target=${1:-alia}
name=${2:-alia}
window_size=${3:-1600,1000}

if [[ ! $name =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Error: output name may contain only letters, digits, dot, _ and -." >&2
  exit 2
fi
if [[ ! $window_size =~ ^[0-9]+,[0-9]+$ ]]; then
  echo "Error: window size must be WIDTH,HEIGHT, for example 1600,1000." >&2
  exit 2
fi

output_dir="$root_dir/docs/screenshots"
output="$output_dir/$name.png"
temporary_html=$(mktemp --tmpdir alia-screenshot.XXXXXX.html)
trap 'rm -f -- "$temporary_html"' EXIT
mkdir -p -- "$output_dir"

tmux capture-pane -e -p -t "$target" \
  | python3 "$root_dir/tools/ansi2html.py" "${TITLE:-$target}" \
  >"$temporary_html"

chrome_bin=${CHROME:-$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)}
if [[ -z $chrome_bin ]]; then
  echo "Error: no Chrome/Chromium executable found. Set CHROME." >&2
  exit 1
fi
"$chrome_bin" \
  --headless=new \
  --hide-scrollbars \
  --screenshot="$output" \
  --window-size="$window_size" \
  "file://$temporary_html" >/dev/null

if [[ ! -s $output ]]; then
  echo "Error: browser did not create screenshot: $output" >&2
  exit 1
fi

printf '%s\n' "$output"
