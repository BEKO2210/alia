# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-18

### Added

- Gate tasks `bench/live_tasks/subagent` and `fork_agent`; in the measured run the main agent resumed after a sub-agent with 21 evaluated tokens because llama-server kept its state in the host-RAM prompt cache. The README explains how to use sub-agents for more context.
- The site shows agent-task results per profile (default, quality, 128K).
- `alia --sandbox` runs tool commands in Qwen Code's bubblewrap sandbox (project writes only, no tool network), checks for `bwrap` and conflicting MCP servers before startup, stores uncommitted tracked changes in `refs/alia/pre-session`, and `alia doctor` shows a `Sandbox` row; `alia web --sandbox` is rejected.
- Prompt-injection gate tasks `bench/live_tasks/inject_readme`, `inject_tool_output`, and `inject_comment`.
- `SECURITY.md` documents what the sandbox protects and what it does not.
- Opt-in long-context profile `rtx8gb-16gb-qwen36-35b-128k`: Qwen Code compacts at ~98K instead of ~32.5K tokens, about 20 % slower.
- Optional per-profile chat templates, including one-confirmation downloads alongside a missing model and exact server-reuse tracking.
- The opt-in `rtx8gb-16gb-ornith15-35b-quality` profile, measured at 16/16 agent tasks versus 13/16 for the faster automatic default.
- `bench/agent_bench.py --mcp browser,search` and gate tasks in `bench/live_tasks/` (browser page that needs JavaScript, key-less search, `CLAUDE.md` context).
- Project context discovery reports `QWEN.md`, `AGENTS.md`, and `CLAUDE.md` with estimated token sizes in `alia doctor`, and warns at startup when they consume more than 25% of the profile's auto-compaction budget.
- Opt-in MCP servers for a headless browser (`@playwright/mcp` 0.0.83) and key-less DuckDuckGo web search (`duckduckgo-mcp-server` 0.7.0), managed with `alia mcp [list]`, `alia mcp enable NAME`, and `alia mcp disable NAME`.
- `alia doctor` shows the enabled MCP servers and marks a missing `npx` or `uvx`.
- `alia mcp test [NAME]` starts the enabled MCP servers like a session does, runs `initialize` and `tools/list`, and reports the allowed tools or the error; `alia doctor` points to it when MCP servers are enabled.
- `alia status` reports managed-server health, PID, profile, port, uptime, and model.
- `alia doctor` reports whether Ollama is unavailable, idle, or has loaded models.
- `alia doctor` shows Qwen Code's auto-compaction and hard limit for the
  selected profile, and startup warns when a profile's context is too small
  for Qwen Code.
- Startup warns when less RAM is available than the 35B default profile needs
  to keep its experts in memory (11 GB, from the runner's resident set in the
  full-speed runs); `alia doctor` shows the available RAM.
- `bench/agent_bench.py`: eight repository tasks solved headless by Qwen Code
  with Alia's settings and scored by hidden tests.

### Changed

- Every bundled profile caps llama-server's host-RAM prompt cache at 2,048 MiB to avoid swap growth on 16 GB systems.
- Published speeds are re-measured with Alia's llama.cpp build and exactly each profile's launch flags (`--jinja`, `--cache-ram 2048`): 35B 49.9 / 39.1 / 37.4 tok/s and 9B 66.2 / 57.8 / 51.4 tok/s at 4K / 32K / 60K. Interim numbers from a run that used Ollama's bundled llama-server by mistake are withdrawn.
- Every agent-task figure in `profiles.json` names its `bench/results/agent-*.jsonl` runs and context; speed sources measured before the cache cap say so. The test for unsourced metrics covers `agent_*` and all `*_tps` keys again.
- `bench/agent_bench.py --server-args` rejects input that is not a JSON list of strings.
- Generated Qwen Code settings load `CLAUDE.md` alongside `QWEN.md` and `AGENTS.md` for project instructions.
- MCP servers load their tool schemas upfront (`alwaysLoadTools`), so the model no longer wastes its first call on a deferred tool before `tool_search`.
- Alia writes detected shell constraints into a managed block in the isolated global `QWEN.md`.
- `alia doctor` reports the `python3` path and whether a `python` command exists.
- Host-wide user skills are disabled in Alia sessions; repository project skills remain available.
- Background sub-agents are serialized to match llama-server's single request slot.
- Slow deep-context streams may run for 30 minutes before Qwen Code aborts them.
- `alia --continue` and `alia --resume [ID]` pass session selection to Qwen Code.
- Model-load progress learns the selected profile's last load time.
- `alia doctor` reports the llama-server build.
- Low-RAM startup warnings suggest the lighter 9B profile when applicable, and `alia doctor` marks low available RAM.
- Interactive sessions disable follow-up suggestions that would make an extra full-context request.
- Qwen Code's pinned release no longer checks for updates or opens the feedback dialog.
- Optional automatic-title and tool-summary model requests are disabled in the environment.
- Tool output limits are reduced while full results remain available in Qwen Code's saved files.
- Qwen Code starts lean: 17 tools a local single-slot agent does not use
  (cron, worktrees, goals, team messages, memory, image zoom, MCP resources)
  are denied, and background memory extraction is off. The first prompt
  shrinks from 22.8K to 12.8K tokens; a one-word reply takes 11.7 s instead
  of 29.9 s cold and 2.0 s instead of 7.0 s warm. Three agent tasks ran in
  173 s instead of 292 s, all passing.

### Fixed

- Alia's status lines no longer appear after Qwen Code's output when stdout is a file or pipe; a headless `alia -- -p "..."` answer now comes last instead of being hidden above them.
- Ollama unloading now retries models reloaded by other clients during the bounded wait.
- The 9B fast profile now launches with a 65,536-token context instead of
  33,408. Qwen Code 0.25.1 keeps 20,000 tokens for compaction summaries, so the
  old window compacted after 408 tokens and stopped requests at 10,408
  ("Context is too large to send safely"). Measured at the new size with the
  launch flags: 66.2 / 57.8 / 51.4 tok/s at 4K / 32K / 60K, peak VRAM 7.2 GB
  including the desktop.

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

[Unreleased]: https://github.com/BEKO2210/alia/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/BEKO2210/alia/releases/tag/v0.2.0
[0.1.0]: https://github.com/BEKO2210/alia/releases/tag/v0.1.0
