#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${HOME}/.local/bin"
TARGET="${TARGET_DIR}/alia"

if ! command -v python3 >/dev/null 2>&1; then
  awk -F'"' '$2 == "install.missing_python" { print $4; found=1 } END { if (!found) print "install.missing_python" }' \
    "$SCRIPT_DIR/i18n/en.json" >&2
  exit 1
fi

message() {
  python3 - "$SCRIPT_DIR" "$1" "${2-}" "${3-}" <<'PY'
import json
import os
import sys
from pathlib import Path

root, key, first, second = sys.argv[1:]
config_path = Path.home() / ".config/alia/config.json"
try:
    config = json.loads(config_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    config = {}
if not isinstance(config, dict):
    config = {}
candidate = os.environ.get("ALIA_LANG") or config.get("lang")
if not candidate or str(candidate).lower() == "auto":
    candidate = next((os.environ.get(name) for name in ("LC_ALL", "LC_MESSAGES", "LANG") if os.environ.get(name)), "en")
language = str(candidate).lower().replace("_", "-").split(".", 1)[0].split("@", 1)[0].split("-", 1)[0]
i18n = Path(root) / "i18n"
if not (i18n / f"{language}.json").is_file():
    language = "en"
english = json.loads((i18n / "en.json").read_text(encoding="utf-8"))
messages = english if language == "en" else json.loads((i18n / f"{language}.json").read_text(encoding="utf-8"))
values = {"version": first, "target": first, "source": second}
print(messages.get(key, english.get(key, key)).format(**values))
PY
}

printf '%s\n\n' "$(message install.title)"

missing=0
python_version="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
if python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
  printf '%s\n' "$(message install.ok_python "$python_version")"
else
  printf '%s\n' "$(message install.missing_python_version "$python_version")"
  missing=1
fi

qwen_bin="$(command -v qwen || true)"
if [[ -z "$qwen_bin" && -x "${HOME}/.npm-global/bin/qwen" ]]; then
  qwen_bin="${HOME}/.npm-global/bin/qwen"
fi
qwen_version=""
if [[ -n "$qwen_bin" ]]; then
  qwen_version="$("$qwen_bin" --version 2>/dev/null || true)"
fi
if [[ "$qwen_version" =~ (^|[^0-9.])0\.25\.1($|[^0-9A-Za-z.-]) ]]; then
  printf '%s\n' "$(message install.ok_qwen)"
else
  printf '%s\n' "$(message install.missing_qwen)"
  missing=1
fi

llama_bin="${ALIA_LLAMA_SERVER:-}"
llama_bin="${llama_bin/#\~/$HOME}"
default_llama="${HOME}/src/llama.cpp/build/bin/llama-server"
if [[ ( -n "$llama_bin" && -f "$llama_bin" && -x "$llama_bin" ) || \
      ( -f "$default_llama" && -x "$default_llama" ) ]]; then
  printf '%s\n' "$(message install.ok_llama)"
else
  printf '%s\n' "$(message install.missing_llama)"
  missing=1
fi

if command -v hf >/dev/null 2>&1; then
  printf '%s\n' "$(message install.ok_hf)"
else
  printf '%s\n' "$(message install.missing_hf)"
  missing=1
fi

if [[ "$missing" -ne 0 ]]; then
  printf '\n%s\n' "$(message install.abort)"
  exit 1
fi

mkdir -p -- "$TARGET_DIR"
ln -sfn -- "${SCRIPT_DIR}/alia" "$TARGET"
printf '\n%s\n' "$(message install.installed "$TARGET" "${SCRIPT_DIR}/alia")"
printf '%s\n' "$(message install.path_hint)"
printf '%s\n' "$(message install.next)"
