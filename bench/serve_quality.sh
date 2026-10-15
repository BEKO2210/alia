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
if curl -s -o /dev/null http://127.0.0.1:8099/health; then
  echo "port 8099 busy - an orphaned llama-server would be measured instead"; exit 1
fi
env LD_LIBRARY_PATH=/usr/local/lib/ollama/cuda_v12:/usr/local/lib/ollama \
  GGML_BACKEND_PATH=/usr/local/lib/ollama/cuda_v12/libggml-cuda.so \
  /usr/local/lib/ollama/llama-server -m "$GGUF" -c 16384 -fa on -ctk q8_0 -ctv q8_0 -np 1 --jinja \
  --host 127.0.0.1 --port 8099 --no-webui "$@" > "results/serve-$NAME.log" 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null; wait $PID 2>/dev/null || true' EXIT
until curl -sf http://127.0.0.1:8099/health >/dev/null; do
  kill -0 $PID 2>/dev/null || { echo "llama-server died, see results/serve-$NAME.log"; exit 1; }
  sleep 1
done
python3 bench.py quality "$NAME" --openai http://127.0.0.1:8099 "${BENCH[@]}"
