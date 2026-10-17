# Alia architecture

Alia is a local coding agent built from three layers. It does not have its own agent loop: Qwen Code is the
engine, and Alia makes it run well on local hardware.

```
alia  (launcher and optimizer, one stdlib-Python file)
 │  detects GPU/RAM · picks a measured profile · downloads the GGUF · RAM and Ollama preflight
 │  starts llama-server · generates Qwen Code settings · GPU lock · doctor · bench
 ▼
Qwen Code 0.25.1  (agent engine, pinned)
 │  agent loop · tools · MCP · skills · sessions · permissions · web shell (`qwen serve`)
 ▼
llama.cpp llama-server  (local inference, 127.0.0.1:8090, one slot)
    GGUF via mmap · CPU expert offload for MoE · flash attention · q8_0 KV cache · MTP drafts
```

## What Alia owns

| Part | Where | Notes |
|---|---|---|
| Hardware detection and profile choice | `detect_hardware`, `choose_profile`, `profiles.json` | Profiles carry context size, RAM need and measured tok/s where available (two 35B Q4 profiles are still unmeasured) |
| Model files | `ensure_model`, `find_model` | Hugging Face download, size check |
| Server lifecycle | `start_server`, `stop_server`, `wait_for_health`, `GpuStartLock` | PID + start-tick checks, never kills foreign processes |
| Preflight | `unload_ollama`, `ram_warning`, compaction warning | Ollama and llama-server cannot share 8 GB VRAM |
| Qwen Code configuration | `generate_settings`, `qwen_environment` | Isolated `QWEN_HOME`; trims tools and side requests that block the single slot |
| Diagnostics | `alia doctor`, `alia logs` | |
| Benchmarks | `bench/` | Speed (llama-bench, server) and agentic tasks with hidden tests |

## Design rules

- **Qwen Code first.** Use its settings, flags and extension points; patch it only when no interface exists.
- **One inference slot.** Every extra model request (suggestions, classifiers, memory agents, parallel
  subagents) waits for the same slot and can evict its prompt cache. Alia keeps them off or serialized.
- **Measured, not claimed.** Profile numbers and every tuning change come from `bench/` runs on the exact launch
  configuration; agent changes are gated on the frozen task set in `bench/agent_tasks`.
- **mmap stays.** On 16 GB machines the CPU experts must remain reclaimable page cache
  (`--load-mode none` drove RAM critical in a test).
- **Local only.** No cloud model or API key is required.

See [ALIA_GAP_ANALYSIS.md](ALIA_GAP_ANALYSIS.md) for what Qwen Code already covers and what is missing.
