# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- Qwen Code starts lean: 17 tools a local single-slot agent does not use
  (cron, worktrees, goals, team messages, memory, image zoom, MCP resources)
  are denied, and background memory extraction is off. The first prompt
  shrinks from 22.8K to 12.8K tokens; a one-word reply takes 11.7 s instead
  of 29.9 s cold and 2.0 s instead of 7.0 s warm. Three agent tasks ran in
  173 s instead of 292 s, all passing.

### Fixed

- The 9B fast profile now launches with a 65,536-token context instead of
  33,408. Qwen Code 0.25.1 keeps 20,000 tokens for compaction summaries, so the
  old window compacted after 408 tokens and stopped requests at 10,408
  ("Context is too large to send safely"). Measured at the new size: 65.7 /
  57.5 / 50.2 tok/s at 4K / 32K / 60K, peak VRAM 7.7 GB including the desktop.

### Added

- `alia doctor` shows Qwen Code's auto-compaction and hard limit for the
  selected profile, and startup warns when a profile's context is too small
  for Qwen Code.
- Startup warns when less RAM is available than the 35B default profile needs
  to keep its experts in memory (11 GB, from the runner's resident set in the
  full-speed runs); `alia doctor` shows the available RAM.
- `bench/agent_bench.py`: eight repository tasks solved headless by Qwen Code
  with Alia's settings and scored by hidden tests.

## [0.1.0] - 2026-10-15

First public release.

### Added

- `alia` launcher: detects GPU VRAM and RAM, picks the matching hardware
  profile, starts `llama-server` on loopback, waits for health and opens
  Qwen Code with the Alia brand.
- Measured default profile for 8 GB VRAM / 16 GB RAM: Qwen3.6-35B-A3B
  UD-IQ3_XXS with MTP speculative decoding (n=2), expert offload, 64K context.
- Commands: `doctor`, `profiles`, `use`, `stop`, `logs`, `web`; flags
  `--lang`, `--fast`, `--auto-edit`, `--yolo`, `--wait-gpu`.
- English and German UI, following the system language.
- Benchmark harness and raw results in `bench/`.

[0.1.0]: https://github.com/BEKO2210/alia/releases/tag/v0.1.0
