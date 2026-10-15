# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
