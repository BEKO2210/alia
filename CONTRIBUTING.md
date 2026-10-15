# Contributing to Alia

Thank you for helping Alia support more hardware. Code fixes and documentation
improvements are welcome; new hardware profiles must be backed by reproducible
evidence.

## Add a hardware profile

1. Record the GPU and VRAM, system RAM, CPU, OS, driver, llama.cpp commit, model
   repository and exact GGUF filename.
2. Run the scripts in `bench/` with the exact server flags proposed for the
   profile. Use `bench.py` for performance and quality, and
   `bench_llamacpp.py` for llama.cpp flag comparisons. See `bench/REPORT.md` for
   the existing methodology and known limits.
3. Keep the raw `.jsonl` output. Add only completed, valid runs to
   `bench/results/`, document them in `bench/results/README.md`, and include the
   exact commands used. Do not add server logs, PID files, failed runs, secrets,
   or personal absolute paths.
4. Add the profile to `profiles.json`. A measured profile needs its measured
   TG/PP and quality values plus a `source` pointing to the raw evidence. If the
   measurements are incomplete, mark the profile `unmeasured` and explain why.
5. Open a “New hardware profile” issue or pull request with the hardware facts,
   llama.cpp commit, command lines, summary, and raw JSONL evidence.

## Evidence and honesty rules

- Never label an estimate, extrapolation, vendor claim, or result from different
  hardware as measured.
- Never select only favorable repetitions or silently discard failures. Explain
  exclusions and retain relevant failure evidence outside the valid-results set.
- State sample counts and material methodological limitations. With very small
  samples, do not present a maximum as a statistically meaningful p95.
- Keep unmeasured profiles visibly unmeasured. Missing evidence is better than a
  precise-looking number that cannot be reproduced.
- Preserve raw records. Summaries and screenshots are not substitutes for JSONL.

## Checks

```bash
python3 -m json.tool profiles.json >/dev/null
python3 -m unittest discover -s tests -v
python3 bench/summarize.py bench/results/*.jsonl
```

Do not run GPU benchmarks while another workload owns the GPU. Use a shared
`flock` file when the machine has one.
