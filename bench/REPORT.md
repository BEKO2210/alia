# RTX 3070 (8 GB) + 16 GB RAM: best local coding model — measurement report

As of 2026-10-15, measured on **pop-os**: RTX 3070 8 GB (driver 580.159.03,
240 W), Ryzen 7 5800X, 16 GB DDR4 (+ zRAM), NVMe behind LUKS, Pop!_OS,
Ollama 0.40.2, and llama.cpp a0e6dc7 (local build, CUDA 12.8, sm_86).
Every number comes from the raw files in `results/` and can be reproduced with
the scripts in this directory. Grok independently reviewed the data in
`reviews/grok-bench-review.md`; its methodological findings are incorporated
below.

**Statistics:** median of 3–5 runs. “p95” in the raw data is the maximum when
n ≤ 11 (Grok finding #1), so this report does not use it. Dense-model σ is below
1%; MoE with experts in RAM has σ around 3–6%.

---

## Phase 1 — Testing the “Qwen3.5-9B Q4_K_M, 54–58 t/s” claim

| Question | Result | Evidence |
|---|---|---|
| Does Qwen3.5-9B Q4_K_M exist? | Yes. Apache-2.0, VLM, 32 layers (24 Gated DeltaNet + 8 full-attention), native 262K | HF model card + `config.json` |
| File size | 5.63 GB (Ollama/lmstudio), 5.68 GB (unsloth), 6.17 GB (bartowski), plus 0.92 GB vision projector | HF API |
| Does it fit in 8 GB? | Yes, **only without the projector**. With the projector, Ollama already puts 13% of the layers on CPU at 4K | measured, `ollama ps` |
| KV cache | Only 8 layers: f16 32 KiB/token, q8_0 17 KiB/token (32K = 0.53 GiB), plus about 50 MiB fixed state | calculated + Ollama log “checkpoint 50.251 MiB” |
| Is 54–58 t/s realistic? | No primary source was found for the estimate sites. **Measured: 64.5 t/s @4K, 56.1 @32K text-only; 53.0 @4K, 20.1 @32K with projector** | `perf-20261015-001001.jsonl` |
| Context fully in VRAM | 9B text-only: 32K yes; 64K/128K **no** (128K KV 2.18 GB → OOM) | context probe, llama-server log |
| Is Q4_K_M the best compromise? | Yes for 9B because it fits completely. For 35B MoE on 16 GB RAM, **IQ3_XXS** is the maximum | Phase 3 |

## Phase 2 — Model comparison under the same conditions

Quality uses 10 coding tasks (8 Python, 2 C++) with executed unit tests, 8
tool-call cases (German/English, including “no tool needed”), and 3 ERP JSON
extractions with and without a schema. Temperature 0, thinking disabled.
The quality JSONL records do not contain the server context or server arguments,
so no quality score is attributed to a 32K or launch-matching configuration.

| Model | Code | Tools | JSON schema / prompt only | Output t/s @4K / @32K | Note |
|---|---:|---:|---:|---:|---|
| **Qwen3.6-35B-A3B UD-IQ3_XXS (MoE, experts in RAM)** | **9/10** | 7/8 | 3/3 · 3/3 | **53.6 / 48.5** final | Winner |
| gemma4:12b-it-qat | 9/10 | 8/8 | 3/3 · 3/3 | 17.4 / 12.2 | 20% on CPU; slow |
| qwen3.5:9b text-only | 8/10 | 8/8 | 3/3 · 3/3 | 64.5 / 56.1 | Fastest “good” model |
| gemma4:e4b-it-qat | 8/10 | 7/8 | 3/3 · 3/3 | 90.8 / 61.9 | Strong for its size; 128K in VRAM |
| Ministral-3-14B IQ3_XXS | 7/10 | 8/8 | 3/3 · 0/3 | 12.6 / 3.4 | Correct JSON wrapped in fences |
| qwen3:8b | 6/10 | 8/8 | 3/3 · 3/3 | — | Frozen (Statim) |
| qwen3.5:4b | 5/10 | 7/8 | 3/3 · 3/3 | 99.5 / 82.0 | |
| phi4-mini | 5/10 | 3/8 | 2/3 · 0/3 | 112.6 / 59.3 | Unsuitable for agents |
| granite4.2:8b | 4/10 | 8/8 | 3/3 · 3/3 | 61.0 / 3.7 | Collapses after 16K; KV too large |
| Ornith-1.5-9B | 4/10 | 6/8 | 3/3 · 3/3 | about qwen3.5:9b | Needs thinking; see below |
| Gemma-4-26B-A4B IQ3_XXS (MoE) | — | — | — | 40.4 / 37.3 | Quality run stopped after enough testing |

Thinking on five difficult tasks: Ornith 0/5 → 3/5, Qwen3.5-9B 3/5 → 2/5,
Qwen3.6 4/5 → 3/5. **This is not robust:** the thinking budget was 12,288
tokens in a 16K context and at least one run was truncated (Grok #11). Only the
conclusion that Ornith needs thinking is clear.

| Purpose | Model |
|---|---|
| General assistant | Qwen3.6-35B-A3B; fast and small: gemma4:e4b |
| Autonomous coding agent, Python/C++, debugging, repository analysis | **Qwen3.6-35B-A3B** at 64K |
| Local automation / ERP tool calls and JSON | Qwen3.6; for speed qwen3.5:9b-text, **always with a JSON schema** |
| Fastest usable model | gemma4:e4b (91 t/s, Code 8/10) |

## Phase 3 — GPU optimization, one change at a time

| Change | Measured effect | Decision |
|---|---|---|
| **Omit the vision projector** (`qwen3.5:9b-text`) | 32K **20.1 → 56.1 t/s** (×2.8); Ornith Agent 20.9 → 60.0 | Largest single lever |
| **MoE experts in RAM** (`--fit`, Qwen3.6 35B) | 35B model at 47–49 t/s on 8 GB | Makes the winner possible |
| **New llama.cpp + `-ub 2048`** | Prompt 704 → 1523 t/s @4K, 661 → 1639 @32K; output −4% | Required for agent use; 32K TTFT 50 s → 20 s |
| **MTP** (`--spec-type draft-mtp --spec-draft-n-max 2`, MTP GGUF) | Output +14% @4K (47.0 → 53.6), +10% @32K (44.2 → 48.5); 75% acceptance; prompt −10–28% | On |
| `--moe-cache-mib 1024` | Output ±0 to −2%, prompt −16%; **with MTP, −10%** | Off; insufficient VRAM |
| KV f16 vs q8_0 vs q4_0, 9B | Same speed ±1%; VRAM f16 +390 MB, q4_0 −260 MB | q8_0 |
| `-ub 1024`/`2048`, dense 9B | Prompt +12% @32K; no gain above 1024 | 1024 |
| Flash Attention off, 9B, all layers on GPU, 33K | Does not load; compute buffer +1.16 GB → OOM | FA on |
| `-lm none`, `--cache-ram`, ik_llama.cpp | Not measured; testing stopped | Open |

Qwen3.6 memory telemetry in the final setup: runner 670–830 major faults/s,
up to 106 MB/s NVMe reads, RSS 10.5–11.5 GB. **Experts are evicted from the page
cache:** RAM, not the GPU, is the real bottleneck.

Thermals/clocks across the published JSONL: maximum 76 °C. The minimum sampled
busy SM clock is 1710 MHz in the Ollama perf data and 1725 MHz in the
llama-server data; the selected 60K profile run records 1815 MHz. These samples
do not include throttle-reason telemetry, so they cannot establish whether
thermal or power throttling occurred.

## Phase 4 — Benchmark suite

| File | Purpose |
|---|---|
| `bench.py perf` | Ollama cold start, TTFT, PP/TG by context depth, VRAM, RSS, GPU share, faults/NVMe |
| `bench.py ctx` | Largest GPU-resident context per model |
| `bench.py quality [--think] [--tasks …] [--openai URL]` | Executed code tests, tools and JSON through Ollama or llama-server |
| `bench_llamacpp.py --configs … --extra …` | llama-server flag A/B, including MTP acceptance |
| `serve_quality.sh` | Start a GGUF with llama-server and measure quality |
| `summarize.py` | Render tables from raw data |

Historical JSONL files store p95 as the maximum at small n. The current harness
stores min/max and only emits p95 for n ≥ 20, and summaries now retain failed
llama-server configurations. Remaining limits: the first run after server start is warm-up;
llama-server VRAM is per server, not per depth; prompt-only JSON treats Markdown
fences as failure. See the public review for the full audit.

## Phase 5 — Production setup

Implemented as **Alia** in this repository: `alia` detects hardware, selects the
measured profile, starts llama-server with these flags, and opens Qwen Code in
the terminal or through `alia web`.

```bash
LD_LIBRARY_PATH=~/src/llama.cpp/build/bin ~/src/llama.cpp/build/bin/llama-server \
  -m ~/models/gguf/mtp/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf -c 65536 \
  -fa on -ctk q8_0 -ctv q8_0 -np 1 --jinja -b 2048 -ub 2048 \
  --spec-type draft-mtp --spec-draft-n-max 2 -ctkd q8_0 -ctvd q8_0 \
  --host 127.0.0.1 --port 8090
# Sampling for precise coding: temp 0.6, top_p 0.95, top_k 20,
# min_p 0, presence penalty 0
```

Profile context is 64K (60K filled: 38.2 t/s, prompt 1041 t/s). 128K runs
(120K: 25.0 t/s, about 3.7 minutes to first token) but is too slow as default.
`--cache-ram` is intentionally absent: it was not successfully measured. The
4K/32K headline points used server context 33792; see `profiles.json` for
per-metric provenance rather than treating them as measurements of this 64K argv.

The original machine also changed OpenCode and Hermes to the projector-free
Ornith text model (×2.9 at 32K) and removed a dead model entry. Those unrelated
local configuration changes are not part of this repository.

## Phase 6 — Conclusion

1. **Best overall and best coding model:** Qwen3.6-35B-A3B UD-IQ3_XXS with its
   MTP GGUF and experts in RAM (Code 9/10, Tools 7/8, JSON 3/3 with schema plus 3/3 prompt-only; quality server context unrecorded).
2. **Fastest usable:** gemma4:e4b-it-qat, 91 t/s @4K and Code 8/10.
3. **Largest practical context:** Qwen3.6 at 64K and 38 t/s; fully in VRAM,
   gemma4:e4b reaches 128K.
4. **Quantization:** Q4_K_M for dense models without a projector; UD-IQ3_XXS
   for 35B MoE on 16 GB RAM.
5. **Measured median, exact launch configuration (ctx 65536):** 46.5 t/s @4K,
   35.2 @32K, 38.2 @60K; prompt 1.0–1.3k t/s. 4K is stable (46.5–49.7 over three
   runs); 32K/60K depend on free RAM (see the re-measurement section). The
   ctx-33792 runs reached 53.6 / 48.5 because a smaller KV cache leaves more
   VRAM for experts.
6. **Largest optimizations:** remove the projector (×2.8), keep MoE experts in
   RAM to run 35B near 50 t/s, use current llama.cpp with `-ub 2048` (prompt
   ×2.2), and add MTP (+10–14%).

**Largest hardware lever:** 64 GB RAM (Q4 quantization, no page faults), followed
by a 24 GB GPU. This final sentence is an estimate, not a measurement.

## Re-measurement with the exact launch configuration (2026-10-15, 10:06–10:55)

Reviewers pointed out that the headline numbers came from server context 33,792
while the default profile launches with 65,536, and that the 9B numbers came from
Ollama's bundled binary. Both profiles were therefore measured again with exactly
their launch flags, Alia's llama.cpp build (a0e6dc7) and the GGUF Alia downloads.

| Run | Profile | ctx | 4K TG / PP | 32K TG / PP | 60K TG / PP | Note |
|---|---|---:|---:|---:|---:|---|
| `llamacpp-20261015-100648` | 35B IQ3_XXS + MTP | 65536 | 46.5 / 1008 | 35.2 / 1301 | — | 3 reps, runner RSS 11.1 GB |
| `llamacpp-20261015-101143` | 35B IQ3_XXS + MTP | 65536 | 48.1 / 1216 | 24.6 / 305 | 9.7 / 161 | 5 reps, RAM pressure |
| `llamacpp-20261015-024711` | 35B IQ3_XXS + MTP | 65536 | 49.7 / 665 | — | 38.2 / 1041 | earlier run, same flags without `--jinja` |
| `llamacpp-20261015-101002` | 9B Q4_K_M (unsloth) | 33408 | 66.1 / 2980 | 57.7 / 2707 | — | 5 reps |

**Why run 101143 collapsed:** the runner's resident set fell from 11.1 to 7.4 GB and
NVMe reads rose to 626 MB/s. With a browser (1.4 GB swapped to zRAM) and other
desktop apps holding RAM, the 13 GB model no longer fits in the page cache and
experts stream from the SSD. GPU clock (1830 MHz) and temperature (≤ 64 °C) were
unchanged, and the hourly GAP job had finished at 10:03, before the run. On a
16 GB machine, deep-context speed of the 35B profile is therefore not guaranteed;
32 GB RAM is recommended for long contexts.
