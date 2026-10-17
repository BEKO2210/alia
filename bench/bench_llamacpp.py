#!/usr/bin/env python3
"""A/B benchmark of llama-server launch flags on one GGUF (stdlib only).

Starts llama-server once per config, measures prompt processing and generation at several context depths through
/completion (cache_prompt=false + random nonce, so every run re-processes the full prompt), samples VRAM, stops the
server by its own PID. Default binary: the llama-server that ships with Ollama (same engine Ollama uses).

  flock -w 600 ~/reel/gpu.lock python3 bench_llamacpp.py --gguf /path/model.gguf --configs base,ub2048,kvf16
  python3 bench_llamacpp.py --list            # show configs

Results: results/llamacpp-<timestamp>.jsonl
"""
import argparse
import datetime as dt
import json
import os
import random
import shlex
import signal
import sys
import statistics
import subprocess
import time
import urllib.request
from pathlib import Path

from bench import Sampler, filler, stats, unload_all, vram_now

BIN = os.environ.get("LLAMA_SERVER", "/usr/local/lib/ollama/llama-server")
existing_library_path = os.environ.get("LD_LIBRARY_PATH")
if BIN.startswith("/usr/local/lib/ollama/"):  # Ollama's bundled build loads its CUDA backend from cuda_v12/
    library_path = "/usr/local/lib/ollama/cuda_v12:/usr/local/lib/ollama"
    ENV = {**os.environ,
           "LD_LIBRARY_PATH": library_path + (os.pathsep + existing_library_path if existing_library_path else ""),
           "GGML_BACKEND_PATH": "/usr/local/lib/ollama/cuda_v12/libggml-cuda.so"}
else:  # own build, e.g. LLAMA_SERVER=~/src/llama.cpp/build/bin/llama-server
    library_path = os.path.dirname(BIN)
    ENV = {**os.environ,
           "LD_LIBRARY_PATH": library_path + (os.pathsep + existing_library_path if existing_library_path else "")}
    ENV.pop("GGML_BACKEND_PATH", None)
PORT = 8099
OUT = Path(__file__).resolve().parent / "results"

# Base mirrors what Ollama 0.40.2 passes to its runner (seen in the runner's cmdline), plus explicit -ngl 99.
BASE = ["-ngl", "99", "-fa", "on", "-ctk", "q8_0", "-ctv", "q8_0", "-b", "512", "-ub", "512", "-np", "1"]
CONFIGS = {
    "base":     [],
    "ub1024":   ["-b", "1024", "-ub", "1024"],
    "ub2048":   ["-b", "2048", "-ub", "2048"],
    "kvf16":    ["-ctk", "f16", "-ctv", "f16"],
    "kvq4":     ["-ctk", "q4_0", "-ctv", "q4_0"],
    "fa_off":   ["-fa", "off", "-ctk", "f16", "-ctv", "f16"],
    "mtp":      ["--spec-type", "draft-mtp", "--spec-draft-n-max", "3"],
    "ngl_half": ["-ngl", "16"],
    "fit":      [],  # no -ngl: llama.cpp --fit (default on) picks GPU layers / MoE experts for the free VRAM
    # fit + the model's own MTP head, draft KV in q8_0 like the main KV (flags as in J. P. Wile's RTX 3070 command)
    # n-max 2: PR #22673 / unsloth docs measured n-max 3-4 worse than 2 on MoE
    "fit_mtp":  ["--spec-type", "draft-mtp", "--spec-draft-n-max", "2", "-ctkd", "q8_0", "-ctvd", "q8_0"],
    "fit_mtp3": ["--spec-type", "draft-mtp", "--spec-draft-n-max", "3", "-ctkd", "q8_0", "-ctvd", "q8_0"],
}


def post(path, payload, timeout=900):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def wait_ready(proc, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server exited with {proc.returncode}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                if r.status == 200:
                    return time.time() - t0
        except Exception:
            pass
        time.sleep(0.25)
    raise TimeoutError("llama-server not ready")


def port_busy():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def main():
    # SIGTERM -> SystemExit, so the finally block stops our llama-server instead of orphaning it on the port
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    ap = argparse.ArgumentParser()
    ap.add_argument("--gguf")
    ap.add_argument("--name", default=None)
    ap.add_argument("--configs", default="base")
    ap.add_argument("--depths", default="4096,32768")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--n-predict", type=int, default=128)
    ap.add_argument("--ctx", type=int, default=0, help="-c; default max(depth)+n_predict+512")
    ap.add_argument("--task", default="summary", choices=["summary", "code"],
                    help="code = ask for a long Python implementation (spec decoding favours code)")
    ap.add_argument("--extra", default="", help="extra llama-server args for every config, e.g. '-ncmoe 24'")
    ap.add_argument("--cache-test", action="store_true",
                    help="agent pattern: same long prefix twice with cache_prompt=true, second turn adds a short question")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    # Ollama's bundled build is the default for A/B against Ollama; profile numbers need LLAMA_SERVER=Alia's build.
    print(f"llama-server: {BIN}", flush=True)
    if a.list:
        for k, v in CONFIGS.items():
            print(f"{k:9s} {' '.join(BASE)} {' '.join(v)}")
        return
    depths = [int(x) for x in a.depths.split(",")]
    ctx = a.ctx or max(depths) + a.n_predict + 512
    OUT.mkdir(exist_ok=True)
    path = OUT / f"llamacpp-{dt.datetime.now():%Y%m%d-%H%M%S}.jsonl"
    name = a.name or Path(a.gguf).name[:24]
    with path.open("w") as f:
        for cfg in a.configs.split(","):
            base_args = [x for x in BASE if x not in ("-ngl", "99")] if cfg.startswith("fit") else BASE
            args = [BIN, "-m", a.gguf, "-c", str(ctx), *base_args, *CONFIGS[cfg], *shlex.split(a.extra),
                    "--host", "127.0.0.1",
                    "--port", str(PORT), "--no-webui", "--seed", "42"]
            unload_all()  # an idle Ollama model would still hold VRAM -> cudaMalloc OOM
            if port_busy():  # an orphaned server would answer /health and get measured instead (seen once)
                raise SystemExit(f"port {PORT} already in use - stop that llama-server first")
            base = vram_now()
            log = open(OUT / f"llama-server-{name}-{cfg}.log", "w")
            proc = subprocess.Popen(args, env=ENV, stdout=log, stderr=subprocess.STDOUT)
            try:
                load_s = wait_ready(proc)
                ntok = len(post("/tokenize", {"content": filler(8000)})["tokens"])
                cpt = 8000 / ntok
                for d in depths:
                    runs = []
                    with Sampler() as s:
                        for _ in range(a.reps):
                            ask = ("\nSchreibe eine kurze Python-Funktion, die alle handle_* Funktionen oben "
                                   "zusammenfasst." if a.task == "summary" else
                                   "\nImplement a complete Python module with a class InventoryService that "
                                   "provides reserve, release, restock and report methods with docstrings and "
                                   "type hints, plus unit tests using unittest.")
                            p = f"[run {random.random()}]\n" + filler(int(d * cpt * 0.98)) + ask
                            if a.cache_test:  # turn 1 fills the cache, turn 2 = same prefix + follow-up
                                post("/completion", {"prompt": p, "n_predict": a.n_predict, "temperature": 0,
                                                     "cache_prompt": True, "seed": 42})
                                p += "\nZweite Frage: welche Funktion prüft den Lagerbestand zuerst?"
                            r = post("/completion", {"prompt": p, "n_predict": a.n_predict, "temperature": 0,
                                                     "cache_prompt": a.cache_test, "seed": 42})
                            t = r["timings"]
                            runs.append({"pp": t["prompt_per_second"], "tg": t["predicted_per_second"],
                                         "pn": t["prompt_n"], "gn": t["predicted_n"],
                                         "cache_n": t.get("cache_n"),
                                         "draft_n": t.get("draft_n"), "draft_acc": t.get("draft_n_accepted")})
                    cache_tokens = [r["cache_n"] for r in runs if r["cache_n"] is not None]
                    rec = {"engine": "llama-server", "bin": BIN, "model": name, "config": cfg, "cache_test": a.cache_test,
                           "prompt_ms": [round(r["pn"] / r["pp"] * 1000) if r["pp"] else None for r in runs], "args": args[1:], "ctx": ctx,
                           "load_s": load_s, "vram_base_mib": base, "depth": d,
                           "prompt_tokens": statistics.median(r["pn"] for r in runs),
                           "cache_tokens": statistics.median(cache_tokens) if cache_tokens else None,
                           "pp_tps": stats([r["pp"] for r in runs]), "tg_tps": stats([r["tg"] for r in runs]),
                           "draft": [(r["draft_n"], r["draft_acc"]) for r in runs], **s.summary()}
                    f.write(json.dumps(rec) + "\n")
                    f.flush()
                    print(f"  {name:20s} {cfg:9s} depth {d:>6} pp {rec['pp_tps']['median']:8.0f}  "
                          f"tg {rec['tg_tps']['median']:6.1f}  vram {rec['vram_peak_mib']:.0f} MiB", flush=True)
            except Exception as e:
                f.write(json.dumps({"engine": "llama-server", "model": name, "config": cfg,
                                    "args": args[1:], "ctx": ctx, "error": str(e)}) + "\n")
                print(f"  {name} {cfg}: ERROR {e}", flush=True)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                log.close()
                time.sleep(2)
    print(f"raw results: {path}")


if __name__ == "__main__":
    main()
