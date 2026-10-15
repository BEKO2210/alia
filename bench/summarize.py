#!/usr/bin/env python3
"""Turn results/*.jsonl into Markdown tables.  python3 summarize.py results/perf-*.jsonl results/quality-*.jsonl"""
import json
import sys


def fmt(st, nd=0):
    if not st:
        return "–"
    spread = (
        f"min {st['min']:.{nd}f}, max {st['max']:.{nd}f}"
        if "min" in st and "max" in st else "Spanne nicht aufgezeichnet"
    )
    p95 = f", p95 {st['p95']:.{nd}f}" if st.get("n", 0) >= 20 and "p95" in st else ""
    return f"{st['median']:.{nd}f} ({spread}{p95}, σ {st['stdev']:.{nd}f})"


def main(paths):
    perf, cold, ctx, qual, lcpp = [], {}, [], [], []
    for p in paths:
        for line in open(p):
            r = json.loads(line)
            if r.get("engine") == "llama-server" or (
                r.get("mode") is None and "model" in r and "config" in r and "error" in r
            ):
                lcpp.append(r)
            elif r.get("mode") == "perf" and r.get("phase") == "depth":
                perf.append(r)
            elif r.get("mode") == "perf" and r.get("phase") == "cold":
                cold.setdefault(r["model"], r)  # first cold load = smallest ctx
            elif r.get("mode") == "ctx":
                ctx.append(r)
            elif r.get("mode") == "quality" and r.get("kind") == "summary":
                qual.append(r)
    if perf:
        print("| Modell | num_ctx | Prompt-Tokens | GPU-Anteil | PP t/s median (Spanne, p95 wenn n≥20, σ) | TG t/s median (Spanne, p95 wenn n≥20, σ) "
              "| TTFT s median (Spanne, p95 wenn n≥20, σ) | VRAM peak MiB | RSS peak MiB |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for r in perf:
            flag = " ⚠cache" if r.get("suspect_cache") else ""
            share = r["resident"]["size_vram"] / r["resident"]["size"] if r.get("resident") else None
            print(f"| {r['model']}{flag} | {r['num_ctx']} | {r['prompt_tokens']:.0f} | "
                  f"{'–' if share is None else f'{share:.0%}'} | {fmt(r['pp_tps'])} | {fmt(r['tg_tps'], 1)} | "
                  f"{fmt(r['ttft_s'], 2)} | {r['vram_peak_mib']:.0f} | "
                  f"{r['rss_peak_mib']} |")
        print()
        print("| Modell | Kaltstart load_s | Kaltstart TTFT s | VRAM-Basis MiB | max °C | max W |")
        print("|---|---:|---:|---:|---:|---:|")
        for m, r in cold.items():
            temps = [x["temp_max_c"] for x in perf if x["model"] == m]
            pw = [x["power_max_w"] for x in perf if x["model"] == m]
            print(f"| {m} | {r['load_s']:.1f} | {r['ttft_s']:.2f} | {r['vram_base_mib']:.0f} | "
                  f"{max(temps, default=0):.0f} | {max(pw, default=0):.0f} |")
        print()
    if ctx:
        print("| Modell | num_ctx | ganz auf GPU | size GB | size_vram GB | TG t/s (kurz) | VRAM peak MiB |")
        print("|---|---:|---|---:|---:|---:|---:|")
        for r in ctx:
            res = r.get("resident") or {}
            if "error" in r:
                print(f"| {r['model']} | {r['num_ctx']} | Fehler: {r['error'][:60]} | | | | |")
                continue
            print(f"| {r['model']} | {r['num_ctx']} | {'ja' if r['fully_gpu'] else 'nein'} | "
                  f"{res.get('size', 0) / 1e9:.2f} | {res.get('size_vram', 0) / 1e9:.2f} | {r['tg_tps']:.1f} | "
                  f"{r['vram_peak_mib']:.0f} |")
        print()
    if qual:
        print("| Modell | Code (Tests bestanden) | Tool-Calls | JSON mit Schema | JSON nur Prompt |")
        print("|---|---:|---:|---:|---:|")
        for r in qual:
            if r["tool"] == "–":  # --tasks run: tool/JSON were skipped
                r = {**r, "tool": "–", "json_schema": "–", "json_prompt": "–"}
            think = " (thinking)" if r.get("think") else ""
            print(f"| {r['model']}{think} | {r['code']} | {r['tool']} | {r['json_schema']} | {r['json_prompt']} |")
        print()
    if lcpp:
        print("| Modell | Config | Tiefe | PP t/s median (Spanne, p95 wenn n≥20, σ) | TG t/s median (Spanne, p95 wenn n≥20, σ) | Cache-Tokens | VRAM peak MiB | Draft akz. |")
        print("|---|---|---:|---:|---:|---:|---:|---|")
        for r in lcpp:
            if "error" in r:
                print(f"| {r['model']} | {r['config']} | – | Fehler: {r['error'][:50]} | | | | |")
                continue
            acc = [d for d in r.get("draft", []) if d[0]]
            rate = f"{sum(a for _, a in acc) / sum(n for n, _ in acc):.0%}" if acc else "–"
            cache = "–" if r.get("cache_tokens") is None else f"{r['cache_tokens']:.0f}"
            print(f"| {r['model']} | {r['config']} | {r['depth']:.0f} | {fmt(r['pp_tps'])} | "
                  f"{fmt(r['tg_tps'], 1)} | {cache} | {r['vram_peak_mib']:.0f} | {rate} |")


if __name__ == "__main__":
    main(sys.argv[1:])
