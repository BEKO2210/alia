#!/usr/bin/env python3
"""Reproducible local-LLM benchmark for one GPU box (written for RTX 3070 8 GB, Ollama).

Stdlib only. Talks to Ollama's native API, samples nvidia-smi and the runner's RSS.

  python3 bench.py perf    qwen3.5:9b ornith-1.5:9b      # speed, VRAM, RAM, depth sweep
  python3 bench.py quality qwen3.5:9b                    # coding / tool calling / JSON
  python3 bench.py ctx     qwen3.5:9b                    # which num_ctx stays fully in VRAM

Wrap in the shared GPU lock:  flock -w 600 ~/reel/gpu.lock python3 bench.py perf ...
Results: results/<mode>-<timestamp>.jsonl (raw) + .md (summary).

Measurement notes
- "Cold start" = model not resident in VRAM. The GGUF may still sit in the Linux page cache; for a disk-cold
  number drop caches first:  sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
- Every perf request starts with a random nonce, so Ollama's prompt-prefix cache cannot skip prompt processing.
- Timings come from Ollama's own counters (nanoseconds): prompt_eval_duration, eval_duration, load_duration.
  TTFT is measured client-side (request sent -> first streamed token), so it includes HTTP + scheduling.
- Thinking is switched off (think=false) for perf and quality, so all models are compared on equal terms.
"""
import argparse
import datetime as dt
import json
import os
import random
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

HOST = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OUT = Path(__file__).resolve().parent / "results"
SEED = 42
OPENAI = None  # quality --openai URL: talk to a llama-server (OpenAI API) instead of Ollama
TASKS = None   # quality --tasks a,b: only these code tasks, skip tool/JSON (used for slow thinking runs)
THINK = False  # quality --think: let thinking models reason (num_predict raised to 12288)


# ----------------------------------------------------------------------------------------------------------------
# HTTP helpers
def api(path, payload=None, timeout=900):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(HOST + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def stream(path, payload, timeout=900):
    """Yield (t_wall, chunk) for a streamed Ollama request."""
    payload = dict(payload, stream=True)
    req = urllib.request.Request(HOST + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for line in r:
            if line.strip():
                yield time.perf_counter(), json.loads(line)


def capabilities(model):
    if OPENAI:
        return ["tools", "thinking"]  # llama-server --jinja: template decides; enable_thinking is ignored if unknown
    return api("/api/show", {"model": model}).get("capabilities", [])


def unload_all():
    for m in api("/api/ps").get("models", []):
        api("/api/generate", {"model": m["name"], "keep_alive": 0})
    for _ in range(100):
        if not api("/api/ps").get("models"):
            return
        time.sleep(0.2)
    raise RuntimeError("Ollama did not unload models")


def resident(model):
    for m in api("/api/ps").get("models", []):
        if model in (m["name"], m["model"]) or f"{model}:latest" in (m["name"], m["model"]):
            return {"size": m.get("size"), "size_vram": m.get("size_vram"), "context_length": m.get("context_length")}
    return None


# ----------------------------------------------------------------------------------------------------------------
# Samplers
class Sampler:
    """nvidia-smi at 200 ms + RSS of every Ollama runner (0.40+: a llama-server child) process."""

    def __init__(self):
        self.gpu, self.rss, self._stop = [], [], threading.Event()

    @staticmethod
    def _runner_pids():
        pids = []
        for pid in os.listdir("/proc"):
            if pid.isdigit():
                try:
                    cmd = open(f"/proc/{pid}/cmdline", "rb").read()
                except OSError:
                    continue
                if (b"ollama" in cmd and b"runner" in cmd) or b"llama-server" in cmd:
                    pids.append(pid)
        return pids

    @classmethod
    def _vmstat(cls):
        """System swap-in/out + major faults, runner-only major faults, bytes read from NVMe disks."""
        want = ("pswpin", "pswpout", "pgmajfault")
        out = {}
        for ln in open("/proc/vmstat"):
            k, v = ln.split()
            if k in want:
                out[k] = int(v)
        out["runner_majflt"] = 0
        for pid in cls._runner_pids():
            try:  # field 12 = majflt; split after the ")" of the comm field
                out["runner_majflt"] += int(open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[9])
            except (OSError, IndexError, ValueError):
                pass
        out["nvme_read_mb"] = sum(int(f[5]) * 512 for f in (ln.split() for ln in open("/proc/diskstats"))
                                  if re.fullmatch(r"nvme\d+n\d+", f[2])) / 2**20
        return out

    def __enter__(self):
        self.vm0, self.t0 = self._vmstat(), time.time()
        self.proc = subprocess.Popen(
            ["nvidia-smi", "--query-gpu=memory.used,utilization.gpu,temperature.gpu,power.draw,clocks.sm",
             "--format=csv,noheader,nounits", "-lms", "200"], stdout=subprocess.PIPE, text=True)
        self.t1 = threading.Thread(target=self._read_gpu, daemon=True)
        self.t2 = threading.Thread(target=self._read_rss, daemon=True)
        self.t1.start(), self.t2.start()
        return self

    def _read_gpu(self):
        for line in self.proc.stdout:
            try:
                mem, util, temp, pwr, clk = [float(x) for x in line.split(",")]
                self.gpu.append((mem, util, temp, pwr, clk))
            except ValueError:
                pass

    def _read_rss(self):
        while not self._stop.is_set():
            total = 0
            for pid in os.listdir("/proc"):
                if not pid.isdigit():
                    continue
                try:
                    cmd = open(f"/proc/{pid}/cmdline", "rb").read()
                    if (b"ollama" in cmd and b"runner" in cmd) or b"llama-server" in cmd:
                        for ln in open(f"/proc/{pid}/status"):
                            if ln.startswith("VmRSS:"):
                                total += int(ln.split()[1])
                except OSError:
                    pass
            self.rss.append(total / 1024)  # MiB
            time.sleep(0.25)

    def __exit__(self, *exc):
        vm1, dt = self._vmstat(), max(time.time() - self.t0, 1e-9)
        # swap-in/out (pages; on pop-os swap is zram first) and major faults (file pages re-read, e.g. mmap'd GGUF)
        # runner_majflt can undercount if a runner starts inside the window (its faults before the first snapshot)
        self.vm = {k + "_per_s": round((vm1[k] - self.vm0.get(k, 0)) / dt, 1) for k in vm1}
        self._stop.set()
        self.proc.terminate()
        self.proc.wait()
        self.t2.join()

    def summary(self):
        busy = [g for g in self.gpu if g[1] > 0] or self.gpu or [(0, 0, 0, 0, 0)]
        return {
            "vram_peak_mib": max((g[0] for g in self.gpu), default=None),
            "gpu_util_mean_busy": round(statistics.mean(g[1] for g in busy), 1),
            "temp_max_c": max((g[2] for g in self.gpu), default=None),
            "power_max_w": max((g[3] for g in self.gpu), default=None),
            "sm_clock_min_busy": min((g[4] for g in busy), default=None),
            "rss_peak_mib": round(max(self.rss, default=0)),
            **getattr(self, "vm", {}),
        }


def vram_now():
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout
    return float(out.split()[0])


# ----------------------------------------------------------------------------------------------------------------
# Perf
WORDS = ("order stock line sku qty warehouse invoice customer reserve release batch price tax total ship "
         "return label vendor audit ledger account credit debit payment status pending closed open item unit").split()
FILLER = (
    "def {f}_{i}(order, stock):\n"
    "    # {c1} {c2} for {c3} line {i}; raise if {c4} is insufficient.\n"
    "    qty = order.lines[{n}].{c5}\n"
    "    if stock.get(order.lines[{n}].{c6}, 0) < qty:\n"
    "        raise ValueError('{c1} {c4} {c3} {n}')\n"
    "    stock[order.lines[{n}].{c6}] -= qty\n\n"
)


def filler(n_chars, rng=None):
    """Synthetic code, random per call: llama-server reuses matching KV chunks even after a differing prefix, so
    identical filler across runs would be served from cache (seen: 115k 'prompt t/s')."""
    rng = rng or random.Random()
    parts, total, i = [], 0, 0
    while total < n_chars:
        w = [rng.choice(WORDS) for _ in range(7)]
        part = FILLER.format(f=w[0], i=i, n=rng.randrange(1000), c1=w[1], c2=w[2], c3=w[3], c4=w[4], c5=w[5],
                             c6=w[6])
        parts.append(part)
        total += len(part)
        i += 1
    return "".join(parts)[:n_chars]


def one_run(model, prompt, num_ctx, n_predict, think_ok, opts_extra=None):
    payload = {
        "model": model,
        "prompt": prompt,
        "options": {"num_ctx": num_ctx, "num_predict": n_predict, "temperature": 0, "seed": SEED,
                    **(opts_extra or {})},
        "keep_alive": "10m",
    }
    if think_ok:
        payload["think"] = False
    t0 = time.perf_counter()
    ttft, last = None, None
    for t, ch in stream("/api/generate", payload):
        if ttft is None and (ch.get("response") or ch.get("thinking")):
            ttft = t - t0
        last = ch
    wall = time.perf_counter() - t0
    pe_n, pe_d = last.get("prompt_eval_count", 0), last.get("prompt_eval_duration", 1)
    ev_n, ev_d = last.get("eval_count", 0), last.get("eval_duration", 1)
    return {
        "ttft_s": ttft, "wall_s": wall, "load_s": last.get("load_duration", 0) / 1e9,
        "prompt_tokens": pe_n, "pp_tps": pe_n / (pe_d / 1e9), "gen_tokens": ev_n, "tg_tps": ev_n / (ev_d / 1e9),
    }


def stats(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return {}
    p95 = xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))]  # nearest-rank on n samples
    return {"median": statistics.median(xs), "p95": p95, "stdev": statistics.stdev(xs) if len(xs) > 1 else 0.0,
            "n": len(xs)}


def perf(models, depths, reps, n_predict, log, opts_extra):
    """Per depth: unload, load with num_ctx = depth + headroom (what a user would set), then `reps` runs.

    Loading per depth matters: Ollama sizes the GPU/CPU split from num_ctx, so one big num_ctx for every depth
    would push layers to the CPU even for short prompts.
    """
    rows = []
    for model in models:
        think_ok = "thinking" in capabilities(model)
        cpt = None
        for d in depths:
            num_ctx = d + n_predict + 512  # headroom: overshoot past n_ctx makes llama-server drop half the prompt
            unload_all()
            base = vram_now()
            with Sampler() as s:
                cold = one_run(model, f"[{random.random()}] Sag Hallo.", num_ctx, 16, think_ok, opts_extra)
            res = resident(model) or {}
            rec = {"mode": "perf", "model": model, "phase": "cold", "num_ctx": num_ctx, "vram_base_mib": base,
                   **cold, **s.summary(), "resident": res,
                   "gpu_share": round(res["size_vram"] / res["size"], 3) if res.get("size") else None,
                   "opts": opts_extra}
            log(rec)
            rows.append(rec)
            if cpt is None:  # chars-per-token calibration on this model's tokenizer
                cal = one_run(model, filler(3000), num_ctx, 1, think_ok, opts_extra)
                cpt = 3000 / max(cal["prompt_tokens"], 1)
            runs = []
            with Sampler() as s:
                for _ in range(reps):
                    p = f"[run {random.random()}]\n" + filler(int(d * cpt * 0.98)) + \
                        "\nSchreibe eine kurze Python-Funktion, die alle handle_* Funktionen oben zusammenfasst."
                    runs.append(one_run(model, p, num_ctx, n_predict, think_ok, opts_extra))
            low = [r["prompt_tokens"] for r in runs if r["prompt_tokens"] < 0.9 * d]
            if low:
                print(f"  WARNING {model} depth {d}: prompt_eval_count {low} < 90 % of target -> cache hit?",
                      flush=True)
            rec = {"mode": "perf", "model": model, "phase": "depth", "depth_target": d, "num_ctx": num_ctx,
                   "load_s": cold["load_s"], "cold_ttft_s": cold["ttft_s"],
                   "gpu_share": rec["gpu_share"],
                   "prompt_tokens": statistics.median(r["prompt_tokens"] for r in runs),
                   "pp_tps": stats([r["pp_tps"] for r in runs]), "tg_tps": stats([r["tg_tps"] for r in runs]),
                   "ttft_s": stats([r["ttft_s"] for r in runs]), "gen_tokens": [r["gen_tokens"] for r in runs],
                   "suspect_cache": bool(low), **s.summary(), "resident": resident(model), "opts": opts_extra}
            log(rec)
            rows.append(rec)
            print(f"  {model:24s} ctx {num_ctx:>6} gpu {rec['gpu_share']}  load {cold['load_s']:5.1f}s  "
                  f"pp {rec['pp_tps']['median']:6.0f} t/s  tg {rec['tg_tps']['median']:6.1f} t/s  "
                  f"ttft {rec['ttft_s']['median']:6.2f}s  vram {rec['vram_peak_mib']:.0f} MiB  "
                  f"rss {rec['rss_peak_mib']} MiB", flush=True)
    return rows


# ----------------------------------------------------------------------------------------------------------------
# Context probe: which num_ctx is fully GPU-resident?
def ctx_probe(models, ctxs, log):
    rows = []
    for model in models:
        think_ok = "thinking" in capabilities(model)
        for c in ctxs:
            unload_all()
            try:
                with Sampler() as s:
                    r = one_run(model, "Sag Hallo.", c, 8, think_ok)
                res = resident(model) or {}
                full = res.get("size") and res.get("size_vram") == res.get("size")
                rec = {"mode": "ctx", "model": model, "num_ctx": c, "resident": res, "fully_gpu": bool(full),
                       "tg_tps": r["tg_tps"], **s.summary()}
            except Exception as e:  # OOM etc.
                rec = {"mode": "ctx", "model": model, "num_ctx": c, "error": str(e)}
            log(rec)
            rows.append(rec)
            print(f"  {model:28s} num_ctx {c:>7}  {rec.get('resident')}  fully_gpu={rec.get('fully_gpu')}",
                  flush=True)
    return rows


# ----------------------------------------------------------------------------------------------------------------
# Quality: coding (unit tests executed), tool calling, structured JSON
CODE_TASKS = [
    ("merge_intervals", "python",
     "Write a Python function merge_intervals(intervals) that merges overlapping closed intervals given as a list "
     "of [start, end] pairs (unsorted, may be empty, touching intervals like [1,2],[2,3] merge) and returns the "
     "merged list sorted by start.",
     "assert merge_intervals([])==[]\nassert merge_intervals([[5,6],[1,3],[2,4]])==[[1,4],[5,6]]\n"
     "assert merge_intervals([[1,2],[2,3]])==[[1,3]]\nassert merge_intervals([[1,10],[2,3],[4,5]])==[[1,10]]\n"),
    ("lru", "python",
     "Write a Python class LRUCache(capacity) with get(key) -> value or -1 and put(key, value), both O(1). "
     "put on an existing key updates it and makes it most recently used. Capacity may be 1.",
     "c=LRUCache(2);c.put(1,1);c.put(2,2);assert c.get(1)==1;c.put(3,3);assert c.get(2)==-1\n"
     "c.put(4,4);assert c.get(1)==-1;assert c.get(3)==3;assert c.get(4)==4\n"
     "d=LRUCache(1);d.put(1,1);d.put(1,5);assert d.get(1)==5;d.put(2,2);assert d.get(1)==-1\n"),
    ("calc", "python",
     "Write a Python function calc(expr: str) -> float that evaluates arithmetic with + - * / , parentheses, "
     "unary minus and spaces, honouring precedence and left associativity. Do not use eval/exec/ast.",
     "assert calc('1+2*3')==7\nassert calc('(1+2)*3')==9\nassert calc('-3+5')==2\nassert calc('2*-(1+1)')==-4\n"
     "assert calc('8/4/2')==1\nassert calc('10-4-3')==3\nassert abs(calc(' 1.5 * 2 ')-3)<1e-9\n"),
    ("toposort", "python",
     "Write a Python function toposort(deps: dict) where deps maps a node to a list of nodes it depends on. "
     "Return a list where every dependency appears before its dependents; nodes that only appear as "
     "dependencies are included too. Ties are broken alphabetically (lexicographically smallest order). "
     "Raise ValueError on a cycle.",
     "assert toposort({'b':['a'],'c':['b','a']})==['a','b','c']\nassert toposort({})==[]\n"
     "assert toposort({'x':[],'a':[]})==['a','x']\n"
     "try:\n    toposort({'a':['b'],'b':['a']})\n    assert False\nexcept ValueError:\n    pass\n"),
    ("min_window", "python",
     "Write a Python function min_window(s: str, t: str) -> str returning the shortest substring of s that "
     "contains every character of t including duplicates; return '' if none. If several have equal length, "
     "return the leftmost.",
     "assert min_window('ADOBECODEBANC','ABC')=='BANC'\nassert min_window('a','aa')==''\n"
     "assert min_window('aa','aa')=='aa'\n"
     "assert min_window('xyzabcxbca','abc')=='abc'\n"),
    ("fix_bug", "python",
     "This function should return the index of target in a sorted list or -1, but it is buggy. Return the "
     "fixed function with the same name and signature.\n\n"
     "def bsearch(a, target):\n    lo, hi = 0, len(a)\n    while lo < hi:\n        mid = (lo + hi) // 2\n"
     "        if a[mid] < target:\n            lo = mid\n        elif a[mid] > target:\n            hi = mid - 1\n"
     "        else:\n            return mid\n    return -1\n",
     "assert bsearch([],1)==-1\nassert bsearch([1],1)==0\nassert bsearch([1,3,5,7],7)==3\n"
     "assert bsearch([1,3,5,7],1)==0\nassert bsearch([1,3,5,7],4)==-1\nassert bsearch([1,3,5,7,9],8)==-1\n"),
    ("dijkstra", "python",
     "Write a Python function shortest(n, edges, src) for a directed graph with nodes 0..n-1 and edges as "
     "(u, v, w) with w >= 0. Return a list of shortest distances from src, using float('inf') for unreachable.",
     "assert shortest(3,[(0,1,4),(0,2,1),(2,1,2)],0)==[0,3,1]\n"
     "assert shortest(2,[],0)==[0,float('inf')]\nassert shortest(1,[],0)==[0]\n"),
    ("csv_total", "python",
     "Write a Python function totals(csv_text: str) -> dict. Input is CSV with header 'kunde;betrag' "
     "(semicolon separator, German decimal comma, values may be quoted, blank lines possible). Return a dict "
     "customer -> total rounded to 2 decimals.",
     "t='kunde;betrag\\nMüller;1.234,50\\n\\n\"Schmidt\";10,00\\nMüller;0,5\\n'\n"
     "assert totals(t)=={'Müller':1235.0,'Schmidt':10.0}\n"),
    ("cpp_rle", "cpp",
     "Write a C++17 function `std::string rle(const std::string& s)` that run-length encodes s as count followed "
     "by char, e.g. \"aaab\" -> \"3a1b\", empty -> empty. Only the function plus needed #includes, no main().",
     '#include <cassert>\nint main(){assert(rle("")=="");assert(rle("aaab")=="3a1b");'
     'assert(rle("abc")=="1a1b1c");assert(rle(std::string(12,\'z\'))=="12z");return 0;}\n'),
    ("cpp_ringbuf", "cpp",
     "Write a C++17 class template `RingBuffer<T>` with constructor RingBuffer(size_t capacity), "
     "void push(const T&) that overwrites the oldest element when full, T pop() that removes and returns the "
     "oldest (throw std::out_of_range when empty), size_t size() const and bool empty() const. Only the class plus "
     "needed #includes, no main().",
     "#include <cassert>\n#include <stdexcept>\nint main(){RingBuffer<int> r(2);assert(r.empty());r.push(1);"
     "r.push(2);r.push(3);assert(r.size()==2);assert(r.pop()==2);assert(r.pop()==3);bool t=false;"
     "try{r.pop();}catch(const std::out_of_range&){t=true;}assert(t);return 0;}\n"),
]

TOOLS = [
    {"type": "function", "function": {
        "name": "get_stock", "description": "Lagerbestand eines Artikels abfragen",
        "parameters": {"type": "object", "properties": {
            "sku": {"type": "string", "description": "Artikelnummer"},
            "warehouse": {"type": "string", "enum": ["berlin", "hamburg", "muenchen"]}},
            "required": ["sku"]}}},
    {"type": "function", "function": {
        "name": "create_invoice", "description": "Rechnung für einen Kunden anlegen",
        "parameters": {"type": "object", "properties": {
            "customer_id": {"type": "integer"},
            "items": {"type": "array", "items": {"type": "object", "properties": {
                "sku": {"type": "string"}, "qty": {"type": "integer"}}, "required": ["sku", "qty"]}},
            "currency": {"type": "string", "enum": ["EUR", "USD"]}},
            "required": ["customer_id", "items"]}}},
    {"type": "function", "function": {
        "name": "search_code", "description": "Search the repository for a regex",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string"}, "path": {"type": "string", "description": "directory, default ."}},
            "required": ["pattern"]}}},
]

# (prompt, expected tool name or None, check(args) -> bool)
TOOL_CASES = [
    ("Wie viele Stück von Artikel A-1001 haben wir in Hamburg?", "get_stock",
     lambda a: a.get("sku") == "A-1001" and a.get("warehouse") == "hamburg"),
    ("Check stock for SKU X9", "get_stock", lambda a: a.get("sku") == "X9"),
    ("Lege für Kunde 4711 eine Rechnung an: 3x B-20 und 1x C-7, in Euro.", "create_invoice",
     lambda a: int(a.get("customer_id", -1)) == 4711 and a.get("currency") == "EUR" and
     sorted((i.get("sku"), int(i.get("qty"))) for i in a.get("items", [])) == [("B-20", 3), ("C-7", 1)]),
    ("Invoice customer 12 for 5 units of Z-1 in USD.", "create_invoice",
     lambda a: int(a.get("customer_id", -1)) == 12 and a.get("currency") == "USD" and
     [(i.get("sku"), int(i.get("qty"))) for i in a.get("items", [])] == [("Z-1", 5)]),
    ("Find every place in src/ where the function parse_order is defined.", "search_code",
     lambda a: "parse_order" in a.get("pattern", "") and a.get("path", "").rstrip("/") in ("src", "./src")),
    ("Was ist die Hauptstadt von Frankreich?", None, None),
    ("Erkläre kurz, was eine Rechnung ist.", None, None),
    ("Wie viel ist 17 mal 3?", None, None),
]

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "kunde": {"type": "string"},
        "kundennummer": {"type": "integer"},
        "positionen": {"type": "array", "items": {"type": "object", "properties": {
            "sku": {"type": "string"}, "menge": {"type": "integer"}}, "required": ["sku", "menge"]}},
        "liefertermin": {"type": "string", "description": "ISO date YYYY-MM-DD"},
    },
    "required": ["kunde", "kundennummer", "positionen", "liefertermin"],
}

JSON_CASES = [
    ("Hallo, hier Bäckerei Krause (Kd-Nr. 88231). Bitte liefern Sie bis 3. November 2026: 20 Stück MEHL-405 "
     "und 4 Stück HEFE-42. Danke!",
     {"kunde": "Bäckerei Krause", "kundennummer": 88231, "liefertermin": "2026-11-03",
      "positionen": [("HEFE-42", 4), ("MEHL-405", 20)]}),
    ("Order from ACME GmbH, customer no. 1002: 1x SRV-9, 12x CBL-3. Deliver on 2026-12-01.",
     {"kunde": "ACME GmbH", "kundennummer": 1002, "liefertermin": "2026-12-01",
      "positionen": [("CBL-3", 12), ("SRV-9", 1)]}),
    ("Kunde 77, Firma Özdemir & Söhne, braucht am 15.01.2027 genau sieben Paletten PAL-EU.",
     {"kunde": "Özdemir & Söhne", "kundennummer": 77, "liefertermin": "2027-01-15",
      "positionen": [("PAL-EU", 7)]}),
]


def extract_code(text, lang):
    blocks = re.findall(r"```(?:[a-zA-Z0-9+]*)\n(.*?)```", text, re.S)
    return max(blocks, key=len) if blocks else text


def run_code(code, tests, lang):
    try:
        return _run_code(code, tests, lang)
    except subprocess.TimeoutExpired:
        return False, "timeout (endless loop?)"


def _run_code(code, tests, lang):
    with tempfile.TemporaryDirectory() as d:
        if lang == "python":
            Path(d, "t.py").write_text(code + "\n\n" + tests)
            r = subprocess.run([sys.executable, "t.py"], cwd=d, capture_output=True, text=True, timeout=20)
        else:
            Path(d, "t.cpp").write_text(code + "\n\n" + tests)
            c = subprocess.run(["g++", "-std=c++17", "-O1", "t.cpp", "-o", "t"], cwd=d, capture_output=True,
                               text=True, timeout=60)
            if c.returncode:
                return False, c.stderr[-400:]
            r = subprocess.run(["./t"], cwd=d, capture_output=True, text=True, timeout=20)
        return r.returncode == 0, (r.stderr or r.stdout)[-400:]


def chat_openai(messages, tools=None, format=None):
    """Same contract as chat(), via llama-server's /v1/chat/completions. Returns an Ollama-shaped dict."""
    payload = {"messages": messages, "temperature": 0, "seed": SEED, "max_tokens": 12288 if THINK else 2048,
               # enable_thinking: Qwen/Granite templates; reasoning_effort: gpt-oss (harmony) templates
               "chat_template_kwargs": {"enable_thinking": THINK, "reasoning_effort": "high" if THINK else "low"}}
    if tools:
        payload["tools"] = tools
    if format:
        payload["response_format"] = {"type": "json_schema",
                                      "json_schema": {"name": "order", "schema": format, "strict": True}}
    req = urllib.request.Request(OPENAI.rstrip("/") + "/v1/chat/completions", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        msg = json.loads(r.read())["choices"][0]["message"]
    calls = []
    for c in msg.get("tool_calls") or []:
        args = c["function"].get("arguments") or "{}"
        try:
            args = json.loads(args) if isinstance(args, str) else args
        except json.JSONDecodeError:
            args = {}
        calls.append({"function": {"name": c["function"]["name"], "arguments": args}})
    return {"message": {"content": msg.get("content") or "", "tool_calls": calls}}


def chat(model, messages, think_ok, num_ctx=16384, **extra):
    if OPENAI:
        return chat_openai(messages, extra.get("tools"), extra.get("format"))
    payload = {"model": model, "messages": messages, "stream": False, "keep_alive": "10m",
               "options": {"temperature": 0, "seed": SEED, "num_ctx": num_ctx,
                           "num_predict": 12288 if THINK else 2048}, **extra}
    if think_ok:
        payload["think"] = THINK
    return api("/api/chat", payload)


def norm(s):
    return re.sub(r"[^a-z0-9äöüß&]+", " ", str(s).lower()).strip()


def quality(models, log):
    rows = []
    for model in models:
        caps = capabilities(model)
        think_ok = "thinking" in caps
        unload_all()
        score = {"code": 0, "tool": 0, "json_schema": 0, "json_prompt": 0}
        for name, lang, task, tests in CODE_TASKS:
            if TASKS and name not in TASKS:
                continue
            sysmsg = "You are an expert programmer. Reply with one code block only."
            t0 = time.perf_counter()
            r = chat(model, [{"role": "system", "content": sysmsg}, {"role": "user", "content": task}], think_ok)
            wall = time.perf_counter() - t0  # time to an answer; "time to a correct solution" = sum(wall) / passes
            ok, err = run_code(extract_code(r["message"]["content"], lang), tests, lang)
            score["code"] += ok
            log({"mode": "quality", "kind": "code", "model": model, "task": name, "pass": ok, "err": err,
                 "gen_tokens": r.get("eval_count"), "wall_s": round(wall, 2)})
        if "tools" in caps and not TASKS:
            for prompt, exp, check in TOOL_CASES:
                r = chat(model, [{"role": "user", "content": prompt}], think_ok, tools=TOOLS)
                calls = r["message"].get("tool_calls") or []
                if exp is None:
                    ok = not calls
                else:
                    ok = len(calls) == 1 and calls[0]["function"]["name"] == exp
                    try:
                        ok = ok and check(calls[0]["function"]["arguments"])
                    except Exception:
                        ok = False
                score["tool"] += ok
                log({"mode": "quality", "kind": "tool", "model": model, "prompt": prompt, "pass": ok,
                     "calls": calls})
        for text, exp in ([] if TASKS else JSON_CASES):
            for kind in ("json_schema", "json_prompt"):
                instr = ("Extrahiere die Bestellung als JSON mit den Feldern kunde (Firmenname wie im Text), "
                         "kundennummer (int), positionen [{sku, menge}] und liefertermin (YYYY-MM-DD).")
                if kind == "json_prompt":
                    instr += " Antworte nur mit dem JSON-Objekt, ohne Erklärung, ohne Codeblock."
                extra = {"format": JSON_SCHEMA} if kind == "json_schema" else {}
                r = chat(model, [{"role": "system", "content": instr}, {"role": "user", "content": text}],
                         think_ok, **extra)
                raw = r["message"]["content"]
                try:
                    j = json.loads(raw)
                    valid = (isinstance(j.get("kundennummer"), int) and isinstance(j.get("positionen"), list)
                             and all(k in j for k in JSON_SCHEMA["required"]))
                    pos = sorted((p["sku"], int(p["menge"])) for p in j["positionen"])
                    correct = (valid and j["kundennummer"] == exp["kundennummer"] and
                               j["liefertermin"] == exp["liefertermin"] and pos == exp["positionen"] and
                               bool(norm(j["kunde"])) and
                               (norm(exp["kunde"]) in norm(j["kunde"]) or norm(j["kunde"]) in norm(exp["kunde"])))
                except Exception:
                    valid = correct = False
                score[kind] += correct
                log({"mode": "quality", "kind": kind, "model": model, "valid": valid, "pass": correct,
                     "raw": raw[:500]})
        rec = {"mode": "quality", "kind": "summary", "model": model, "think": THINK and think_ok,
               "code": f"{score['code']}/{len(TASKS) if TASKS else len(CODE_TASKS)}",
               "tool": "–" if TASKS else f"{score['tool']}/{len(TOOL_CASES)}" if "tools" in caps else "n/a",
               "json_schema": "–" if TASKS else f"{score['json_schema']}/{len(JSON_CASES)}",
               "json_prompt": "–" if TASKS else f"{score['json_prompt']}/{len(JSON_CASES)}"}
        log(rec)
        rows.append(rec)
        print("  " + json.dumps(rec, ensure_ascii=False), flush=True)
    return rows


# ----------------------------------------------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["perf", "quality", "ctx"])
    ap.add_argument("models", nargs="+")
    ap.add_argument("--depths", default="4096,8192,16384,32768")
    ap.add_argument("--ctxs", default="8192,32768,65536,131072,204800,262144")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--n-predict", type=int, default=128)
    ap.add_argument("--openai", default=None, help="quality: llama-server base URL, e.g. http://127.0.0.1:8099")
    ap.add_argument("--tasks", default=None, help="quality: comma list of code task names, skips tool/JSON")
    ap.add_argument("--think", action="store_true", help="quality: thinking on for models that support it")
    ap.add_argument("--opt", action="append", default=[], help="extra Ollama option k=v, e.g. num_batch=1024")
    a = ap.parse_args()
    global THINK, OPENAI, TASKS
    THINK, OPENAI = a.think, a.openai
    TASKS = a.tasks.split(",") if a.tasks else None
    opts = {}
    for kv in a.opt:
        k, v = kv.split("=", 1)
        opts[k] = json.loads(v) if re.fullmatch(r"[-0-9.]+|true|false", v) else v
    OUT.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = OUT / f"{a.mode}-{stamp}.jsonl"
    env = {"ollama": api("/api/version")["version"],
           "gpu": subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,power.limit",
                                  "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()}
    with path.open("w") as f:
        def log(rec):
            f.write(json.dumps({**rec, "ts": time.time()}, ensure_ascii=False) + "\n")
            f.flush()
        log({"mode": "env", **env, "argv": sys.argv})
        if a.mode == "perf":
            perf(a.models, [int(x) for x in a.depths.split(",")], a.reps, a.n_predict, log, opts)
        elif a.mode == "ctx":
            ctx_probe(a.models, [int(x) for x in a.ctxs.split(",")], log)
        else:
            quality(a.models, log)
    unload_all()
    print(f"raw results: {path}")


if __name__ == "__main__":
    main()
