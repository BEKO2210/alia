# Alia gap analysis

Status: October 2026, Alia 0.1.x on Qwen Code 0.25.1 and llama.cpp b11639. The question was which parts of a
"universal local agent" Alia must build itself, and which Qwen Code already provides. Every "exists" below was
checked in the Qwen Code 0.25.1 bundle (settings schema, `qwen --help` and subcommand help) and not taken from
documentation.

Rule that follows from it: **before Alia implements something, check whether Qwen Code offers it.** Prefer
generated settings, a wrapper flag or an extension; patch Qwen Code only when no interface exists.

| Area | Qwen Code 0.25.1 | Alia today | Gap / plan |
|---|---|---|---|
| Agent loop | todo_write, plan mode, `/goal`, budgets `--max-session-turns`, `--max-wall-time`, `--max-tool-calls`, `maxToolCallsPerTurn`, heuristic loop detection (`model.skipLoopDetection`, default **true** = off) | loop detection off on purpose: it halted a correct run of a thinking model | Budgets for unattended runs |
| Sessions | JSONL chat recording, `-c/--continue`, `-r/--resume`, `qwen sessions`, `/rewind`/`/restore` file backups (interactive only, off when the execution sandbox is on) | reachable only as `alia -- -c` | First-class resume flag (R2); git snapshot if sandbox is on (R9) |
| Tools | read/write/edit, glob, grep, shell, web_fetch, web_search, agent, skill, lsp, MCP; deferred tools behind `tool_search` | 17 unused tools denied, output limits lowered | Check tool_search round trips on a single slot (R3) |
| Browser | **none built in** (only a chrome-devtools hook inside `qwen serve`) | none | Ship a Playwright/Chrome DevTools MCP entry (R4) |
| Web search | `web_search` works only with the DashScope API; `web_fetch` runs an extra model pass per page | unusable without a key | Key-less search through an MCP server (R4) |
| Memory | QWEN.md / AGENTS.md context files, managed auto memory, `manage_memory`/`search_memory`, `/remember` | auto memory off, memory tools denied (they cost model calls on the one slot) | Project memory through context files first (R5) |
| MCP | full client: stdio/SSE/HTTP, include/exclude tools, trust, timeouts, `qwen mcp add` | none configured | Curated `mcpServers` entries (R4, R7) |
| Skills, extensions, hooks | `.qwen/skills`, `qwen extensions install`, ~23 hook events | none | Optional Alia skill pack (R7) |
| Subagents | `agent` tool (background by default, worktree isolation), custom agents, `agents.maxParallelAgents` | agent tool allowed, no limit set | Serialize to the single llama-server slot (R2/R8) |
| Sandbox | `tools.executionSandbox` (bwrap/landlock, read-only/workspace-write, network open/closed), docker/podman `-s` | none | Opt-in sandbox profile; keep 127.0.0.1:8090 reachable (R9) |
| Permissions | approval modes plan/default/auto-edit/auto/yolo, allow/ask/deny rules | default mode, deny list | `auto` costs a classifier model call per gated tool; keep it off (R9) |
| Observability | telemetry with local `outfile`, `-o json` stats, `--openai-logging` | off; bench measures server metrics | Local-only telemetry option (R6) |
| Model routing | fast/vision/compaction/advisor models, fallbacks on 429/503/529 | one provider entry | Needs a second local server; VRAM-bound on 8 GB (R6, later) |
| Web UI / API | `qwen serve` web shell, ACP, stream-json SDK mode | `alia web` | Covered |

## The real gaps

1. **Browser and key-less search** must come from MCP servers that Alia configures.
2. **One inference slot.** web_fetch passes, memory agents, the `auto` classifier, background subagents and
   follow-up suggestions all queue on it. Alia's job is to switch off or serialize what a local model cannot
   afford, not to add features.
3. **Guardrails exist but are settings.** Budgets and the sandbox need no new code. The heuristic loop detector
   stays off: it stopped a correct run because thinking models restate their plan.
4. **Checkpoints vs sandbox.** Qwen Code disables `/rewind` when its execution sandbox is on; a sandboxed Alia
   needs its own git snapshot before the session.
5. **Model routing** is a hardware question on 8 GB VRAM, not a code question.
