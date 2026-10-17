# Raw benchmark evidence

These are the valid, completed raw JSONL files used by `../REPORT.md`. Files in
the source suite's `invalid/` and `failed/` directories, explicitly invalid
root-level results, incomplete quality runs, logs, and PID files are excluded.
Personal absolute paths in copied command metadata were replaced with `~`;
measurement values are unchanged.

## Ollama performance and context

- `perf-20261015-001001.jsonl` — performance depth sweeps for Qwen3.5 9B/4B,
  Gemma 4, Granite, Phi-4 Mini and related variants.
- `perf-20261015-004430.jsonl` — 32K Ornith projected/text-only comparison.
- `ctx-20261015-004649.jsonl` — GPU-resident context-size probes.

## Quality

- `quality-20261015-005015.jsonl` — Qwen3.5 9B and Ornith full quality suites.
- `quality-20261015-011043.jsonl` — full suites for Qwen3.5 4B, Gemma 4,
  Granite, Phi-4 Mini and Qwen3 8B.
- `quality-20261015-014745.jsonl` — Qwen3.6 35B-A3B full quality suite.
- `quality-20261015-014932.jsonl` — Ministral 3 14B full quality suite.
- `quality-20261015-015119.jsonl` — five-task thinking comparison for Qwen3.5
  and Ornith; its summary's skipped-suite counters are a known defect documented
  in the review.
- `quality-20261015-020353.jsonl` — Qwen3.6 five-task thinking run.

## llama.cpp performance

- `llamacpp-20261015-013906.jsonl` — initial Qwen3.6 `fit` baseline.
- `llamacpp-20261015-014243.jsonl` — Ministral 3 `fit` run.
- `llamacpp-20261015-021754.jsonl` — Qwen3.5 9B batch/KV A/B measurements;
  includes the documented Flash-Attention-off load failure.
- `llamacpp-20261015-022343.jsonl` — Qwen3.5 4B baseline and documented
  incompatible MTP attempt.
- `llamacpp-20261015-022454.jsonl` — Gemma 4 26B performance.
- `llamacpp-20261015-022945.jsonl` — Qwen3.6 35B `-ub 2048` baseline.
- `llamacpp-20261015-023241.jsonl` — MoE cache comparison.
- `llamacpp-20261015-023538.jsonl` — MoE cache plus MTP comparison.
- `llamacpp-20261015-023913.jsonl` — selected MTP/no-MoE-cache configuration.
- `llamacpp-20261015-024711.jsonl` — selected configuration at 4K and 60K.
- `llamacpp-20261015-025021.jsonl` — selected configuration at 120K (one run).
- `llamacpp-20261015-100648.jsonl` — 35B default profile, exact launch
  configuration (ctx 65536), 4K and 32K, 3 reps. Source of the published 4K/32K values.
- `llamacpp-20261015-101002.jsonl` — 9B fast profile, exact launch configuration
  (Alia's llama.cpp build, unsloth GGUF, ctx 33408), 4K and 32K, 5 reps.
- `llamacpp-20261015-101143.jsonl` — 35B default profile, exact launch
  configuration, 4K/32K/60K, 5 reps, under RAM pressure (model partly streamed
  from SSD). Published as the RAM-pressure case.
- `llamacpp-20261016-211736.jsonl` — 9B fast profile, exact launch configuration
  at the new ctx 65536, 4K/32K/60K, 5 reps. Source of the published 9B values;
  replaces `llamacpp-20261015-101002.jsonl`.

For measurement caveats and an independent recount, see
`../reviews/grok-bench-review.md`.

## Agentic coding tasks

- `agent-*.jsonl` — `../agent_bench.py`: Qwen Code solves the eight tasks in
  `../agent_tasks/` headless with Alia's settings; hidden tests score the result.
  One run per task by default, temperature 0.6, so single differences are noise.
  Use `--repeat N` to run every task N times; task rows identify repetitions with `run`.
  Use `--probe` for cold/warm one-word startup probes. Extra llama.cpp arguments use
  `--server-arg`, for example `--server-arg=-cms --server-arg=1024`; llama.cpp arguments
  passed there cannot use `--flag=value`.
  `--mcp browser,search` enables Alia's MCP servers; tasks not found in `agent_tasks/` are
  taken from `../live_tasks/` (gate tasks: `browser` serves `web/` on 127.0.0.1:8766,
  `search` needs internet, `ctxfile` checks that `CLAUDE.md` is in the context).
  Task rows include `evaluated_prompt_tokens`, `prompt_eval_s`, `generated_tokens`, and
  `generation_s` server metrics; the final summary row totals passes, time, and tokens.
  - `agent-20261017-011504` (smoke), `-011929`, `-020336` … `-021111`: Qwen3.6-35B
    default profile, before the lean settings; 7/8 tasks passed (`duration` hit
    the 10-minute limit).
  - `-021353` … `-023251`: Ornith-1.5-35B-A3B APEX-MTP I-Mini with its own chat
    template, 4/4 tasks passed before the run was interrupted.
  - `-030517`: Qwen3.6-35B with the lean Qwen Code settings (17 tools denied,
    background memory off): perf, rename and vat passed in 59 / 45 / 69 s
    (before: 71 / 85 / 136 s).
  - `-110513`: Qwen3.6-35B, micro round 1 baseline (lean settings, `--probe`): cold/warm
    probe 19.4 / 3.6 s; perf, rename, vat passed in 57 / 46 / 65 s.
  - `-110930`: same with `--server-arg=-cms --server-arg=1024` (context checkpoint every
    1,024 tokens): no gain. A new session still re-evaluates the whole ~13K-token first
    prompt, because the prompt differs from the previous session around token 7.6K and
    llama.cpp keeps hybrid-model checkpoints only near the end of earlier prompts.
  - `-112312`: micro round 1 settings (no follow-up suggestions, loop detection, smaller
    tool output): warm probe 2.9 s, all three passed; rename / vat 38 / 59 s. perf took
    228 s because the model benchmarked the old O(n²) code itself and hit the 120 s shell
    timeout (model time ~70 s). Cold probe 31.6 s: model pages were evicted by an
    earlier `--load-mode none` test that drove RAM critical (not kept).
  - `-114111` (round 2 branch, still with loop detection on): vat failed after 18 s —
    Qwen Code's heuristic loop detector halted a correct run as "repetitive_thoughts".
    Loop detection is therefore left off (Qwen Code's default).
  - `-114452`: micro round 2 (sub-agents serialized, 30-min stream lifetime, resume flags,
    status, doctor rows): all three passed; perf / rename / vat 88 / 59 / 59 s.
  - `-121153`: micro round 3 (environment notes in Qwen's global QWEN.md, host-wide user
    skills off): first prompt 12.4K → 10.9K tokens, all three passed, 74 / 44 / 58 s; still
    3 failed tool calls, 2 of them `python: command not found` — the model ignores the note.
  - `-121618`: plus a `python → python3` link on Alia's own PATH when the host has no
    `python`: all three passed (85 / 43 / 62 s), 2 failed calls left, both real test failures
    the model then fixed; no more `python: command not found`.
  - `-124330` (round 4 live gate, MCP browser + search enabled, ad-hoc tasks outside the
    frozen set): browser (local page whose stock line only JavaScript renders) and search
    (latest PyPI version with source) passed in 35 / 31 s via the MCP tools; perf, rename,
    vat passed. First prompt 11.4K tokens with both servers enabled.
  - `-125703` (round 5, ad-hoc task): a repo whose `CLAUDE.md` holds a codeword; the agent
    wrote it in 14 s without opening the file, so `context.fileName` loads `CLAUDE.md`.
    The frozen tasks in this file crashed on a stale task link (harness error, rerun below).
  - `-130307`: round 5 frozen tasks: all passed, 45 / 35 / 54 s.
  - `-131250` (round 7 live gate, MCP with `alwaysLoadTools`): browser / search passed in
    26 / 24 s (round 4: 35 / 31 s) with direct tool calls and no refused `tool_call`;
    first prompt 13.8K tokens with both servers enabled; perf, rename, vat passed.
  - Round 6 server-flag A/B on the 35B profile (perf, rename, vat; prompt and generation
    rates from the server metrics; baseline across rounds 1–5 ≈ 850 prompt tok/s,
    56 generation tok/s). None beat the profile, so its flags stay unchanged:

    | run | change | prompt tok/s | gen tok/s | tasks |
    |---|---|---|---|---|
    | `-125318` | `--spec-draft-n-max 3` (profile: 2) | 792 | 56.4 | 3/3 |
    | `-125812` | `-b 4096 -ub 4096` (profile: 2048) | 420 | 47.2 | 3/3 |
    | `-130837` | `--poll 0` | 855 | 55.8 | 2/3 (rename 3/4, model noise) |
    | `-131756` | `-t 7` (default 8) | 838 | 55.5 | 3/3 |

    Also tested and rejected: a headless warm-up request right after server start. The
    first interactive turn still re-evaluated all 13.3K tokens, because interactive Qwen
    Code sends a different and larger first prompt (13.3K vs 8.0K tokens, default approval
    mode) than headless mode, so the two share no reusable prefix.
  - `-133101`: harness check of `--mcp browser,search` with the three live tasks (main
    before round 7, so MCP schemas still deferred): all passed, 55 / 36 / 15 s.
  - **Model comparison, 2026-10-17** (`-143436` … `-193334`, one file per model and task, 2
    runs each, `--cache-ram 2048`, 10-minute wall per run). All candidates are MoE models with
    ~3–4B active parameters; dense 24B+ models are too slow on 8 GB VRAM (Qwen3.8-27B: 4.8
    tok/s). Pass = all hidden tests green; time = mean seconds per run; rates from the server
    metrics over all runs.

    | model | passed | mean time | gen tok/s | generated tokens | missed |
    |---|---|---|---|---|---|
    | Ornith-1.5-35B-A3B APEX-MTP I-Mini (own chat template) | **16/16** | 248 s | 41.8 | 141K | – |
    | Gemma-4-26B-A4B UD-IQ3_XXS (no MTP) | 15/16 | 245 s | 38.3 | 139K | rename 1× |
    | Qwen3.6-35B-A3B UD-IQ3_XXS (default profile) | 13/16 | 104 s | 54.6 | 69K | config 1×, duration 2× |
    | KAT-Coder-V2.5 APEX-MTP I-Mini | 10/16 | 106 s | 46.6 | 56K | cli, config 2×, duration, rename 2× |
    | gpt-oss-20b MXFP4 (no MTP) | 8/16 | 170 s | 33.2 | 82K | config, csvimport, duration, rename 2×, ttlcache 2×, vat |
    | Qwen3.5-9B Q4_K_M (9B profile) | 6/16 | ~150 s | 60.7 | 129K | most; one ttlcache run thought for 24K tokens without a tool call |

    Ornith and Gemma solve the hard `duration` task that the default never solved, at about
    2.4× the time, mostly from twice the generated (thinking) tokens. Decision: the default
    stays Qwen3.6-35B; Ornith-1.5 becomes the opt-in quality profile.
