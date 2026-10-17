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
