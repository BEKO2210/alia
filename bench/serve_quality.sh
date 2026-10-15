#!/usr/bin/env bash
# Start llama-server for one GGUF, run the quality suite against it via the OpenAI API, stop the server (own PID).
#   flock -w 1800 ~/reel/gpu.lock ./serve_quality.sh NAME /path/model.gguf [bench args...] -- [llama-server args]
#   e.g. ./serve_quality.sh qwen36 model.gguf --think --tasks calc,toposort -- -ncmoe 24
set -euo pipefail
cd "$(dirname "$0")"
NAME=$1; GGUF=$2; shift 2
BENCH=()
while [ $# -gt 0 ] && [ "$1" != "--" ]; do BENCH+=("$1"); shift; done
[ "${1:-}" = "--" ] && shift
python3 -c 'import bench; bench.unload_all()'
if curl -s --connect-timeout 1 --max-time 2 -o /dev/null http://127.0.0.1:8099/health; then
  echo "port 8099 busy - an orphaned llama-server would be measured instead"; exit 1
fi
env LD_LIBRARY_PATH=/usr/local/lib/ollama/cuda_v12:/usr/local/lib/ollama \
  GGML_BACKEND_PATH=/usr/local/lib/ollama/cuda_v12/libggml-cuda.so \
  /usr/local/lib/ollama/llama-server -m "$GGUF" -c 16384 -fa on -ctk q8_0 -ctv q8_0 -np 1 --jinja \
  --host 127.0.0.1 --port 8099 --no-webui "$@" > "results/serve-$NAME.log" 2>&1 &
PID=$!
cleanup() {
  kill "$PID" 2>/dev/null || true
  for _ in {1..20}; do
    kill -0 "$PID" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "$PID" 2>/dev/null; then
    kill -KILL "$PID" 2>/dev/null || true
  fi
  wait "$PID" 2>/dev/null || true
}
trap cleanup EXIT
deadline=$((SECONDS + 300))
until curl -sf --connect-timeout 1 --max-time 2 http://127.0.0.1:8099/health >/dev/null; do
  kill -0 $PID 2>/dev/null || { echo "llama-server died, see results/serve-$NAME.log"; exit 1; }
  if (( SECONDS >= deadline )); then
    echo "llama-server not ready after 300 s; see results/serve-$NAME.log" >&2
    exit 1
  fi
  sleep 1
done
python3 bench.py quality "$NAME" --openai http://127.0.0.1:8099 "${BENCH[@]}"
