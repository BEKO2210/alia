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

For measurement caveats and an independent recount, see
`../reviews/grok-bench-review.md`.
