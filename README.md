<p align="center"><img src="site/logo-terminal.svg" width="360" alt="ALIA"></p>

<p align="center"><b>Your hardware. Your AI. No cloud.</b><br>English | <a href="README.de.md">Deutsch</a></p>
<p align="center">
  <a href="https://github.com/BEKO2210/alia/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/BEKO2210/alia/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/BEKO2210/alia/actions/workflows/codeql.yml"><img alt="CodeQL" src="https://github.com/BEKO2210/alia/actions/workflows/codeql.yml/badge.svg"></a>
  <a href="https://codecov.io/gh/BEKO2210/alia"><img alt="Coverage" src="https://codecov.io/gh/BEKO2210/alia/graph/badge.svg"></a>
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-5C9DFF"></a>
  <a href="https://beko2210.github.io/alia/"><img alt="Website" src="https://img.shields.io/badge/website-alia-A78BFA"></a>
</p>

Alia is a Linux-only, fully local coding-agent launcher. It detects NVIDIA GPU, VRAM, and RAM, selects a hardware profile, starts `llama-server`, and opens a branded Qwen Code terminal or Web Shell. It does not implement its own agent loop or inference engine.


![Alia start screen](docs/screenshots/terminal-start.png)

![Alia in the terminal](docs/screenshots/terminal-agent.png)

![Alia Web Shell](docs/screenshots/web-shell.png)

> **Measured on an RTX 3070 8 GB, Ryzen 7 5800X, 16 GB RAM — launch configuration**
>
> Qwen3.6 35B-A3B IQ3_XXS (default, context 65,536): **46.5 / 35.2 / 38.2 tok/s** generation and 1,008 / 1,301 / 1,041 tok/s prompt processing at 4K / 32K / 60K (the 60K value is from an earlier run with the same flags except `--jinja`, which only selects the chat template). The 4K speed is stable (46.5–49.7 tok/s over three runs). Deep-context speed depends on free RAM: when other apps push the 13 GB model out of the page cache, it streams from the SSD and drops to 24.6 tok/s at 32K and 9.7 at 60K (run `llamacpp-20261015-101143`). **Use 32 GB RAM for long contexts**, or close the browser. Alia warns at startup when less than 11 GB RAM is available, and `alia doctor` shows the free RAM.
>
> Qwen3.5 9B Q4_K_M (fast, context 65,536): **65.7 / 57.5 / 50.2 tok/s** generation and 2,978 / 2,708 / 2,423 tok/s prompt processing at 4K / 32K / 60K.

TG means token generation rate; PP means prompt-processing rate. MTP is multi-token prediction (speculative decoding using the model's MTP heads). Exact run and context provenance lives beside every numeric metric in `profiles.json`.
Quality scores (35B: code 9/10, tools 7/8, JSON 3/3 with schema and 3/3 prompt-only; 9B: code 8/10, tools 8/8) come from separate quality runs whose server context and arguments were not recorded; the 9B quality run used Ollama.

## Supported platform and prerequisites

Alia v0.1.0 supports native Linux with an NVIDIA GPU. It relies on `/proc`, `flock`, and the Linux process-start timestamp; Windows, macOS, AMD GPUs, CPU-only use, and WSL2 are not supported. Python 3.12+ is the supported runtime for the process-management behavior tested by this release.

Install the exact Qwen Code version and Hugging Face CLI:

```bash
npm install -g @qwen-code/qwen-code@0.25.1
python3 -m pip install -U "huggingface_hub[cli]"
```

Build a CUDA-enabled `llama-server`. Commit `a0e6dc7` is Alia's minimum supported and measured llama.cpp revision and contains `--spec-type draft-mtp`:

```bash
git clone https://github.com/ggml-org/llama.cpp.git ~/src/llama.cpp
cd ~/src/llama.cpp
git checkout a0e6dc7
cmake -S . -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j"$(nproc)" --target llama-server
```

This requires a working NVIDIA driver, a CUDA toolkit supported by llama.cpp, CMake, a C++ compiler, Git, Node.js/npm, and Python/pip. The measured build used CUDA 12.8 on an RTX 3070. Alia looks at `~/src/llama.cpp/build/bin/llama-server`; set `ALIA_LLAMA_SERVER=/absolute/path/to/llama-server` for another tested build. The former Ollama-bundled-binary fallback was removed because its flags and MTP support are not stable public interfaces.

The model repositories are public and normally need no Hugging Face login. If Hugging Face asks for authentication or applies a rate limit, run `hf auth login` first.

## Installation

```bash
git clone https://github.com/BEKO2210/alia alia
cd alia
./install.sh
alia doctor
```

`install.sh` verifies Python 3.12+, Qwen Code 0.25.1, `hf`, and `llama-server`, then creates `~/.local/bin/alia`. It stops on any failed filesystem operation. Add that directory to `PATH` if needed:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Downloads and disk space

The first start prints the exact `hf download` command and asks `Download now? [y/N]`; nothing downloads without confirmation. Allow roughly 10% extra free space beyond the file size:

| Profile/model | Download | Recommended free space | Approx. at 100 Mbit/s |
|---|---:|---:|---:|
| 35B IQ3_XXS default | 14.07 GB | 16 GB | 19 minutes |
| 9B Q4_K_M fast | 5.7 GB | 7 GB | 8 minutes |
| 35B Q4_K_XL, unmeasured | 20.8 GB | 23 GB | 28 minutes |

Actual time depends on Hugging Face and your connection. An interrupted undersized GGUF is rejected on the next start. Downloaded files go under `~/.local/share/alia/models`. A documented generic candidate such as `~/models/gguf/Qwen3.5-9B-Q4_K_M.gguf` can avoid a second download.

## Usage

```bash
alia                              # detect hardware, start server and agent
alia --lang de_DE.UTF-8           # override language for this invocation
alia --fast                       # disable thinking for a simple, faster task
alia --wait-gpu 60                # wait for an optional shared GPU lock
alia --auto-edit                  # automatically allow file edits
alia --yolo                       # allow all tools; prints a red warning
alia -- -p "Explain main.py"      # pass arguments to qwen unchanged
alia web                          # Web Shell on 127.0.0.1:4170
alia web --port 4317 --no-open --workspace "$PWD"
alia doctor                       # includes model, hf, disk, and port checks
alia profiles
alia use rtx8gb-qwen35-9b-fast
alia use auto
alia lang de_DE.UTF-8             # persistent German; locale forms work
alia lang en
alia lang auto
alia logs
alia stop
alia --help
alia --version
```

Language precedence is `--lang` → `ALIA_LANG` → configuration → `LC_ALL` → `LC_MESSAGES` → `LANG` → English. Model replies follow the input language unless explicitly requested otherwise.

`--fast` writes `chat_template_kwargs.enable_thinking: false`; normal runs leave thinking enabled. The default approval mode asks before edits and commands. `--auto-edit` approves only edits. `--yolo` approves all tool calls and is only appropriate in a fully trusted workspace.

To coordinate with other GPU jobs, set `gpu_lock` in `~/.config/alia/config.json` or `ALIA_GPU_LOCK` to a lock-file path. `--wait-gpu S` bounds how long Alia waits. Alia also always takes its own state lock across reuse checks, startup, and health readiness.

```json
{"gpu_lock": "~/.cache/shared-gpu.lock"}
```

Runtime data is under `~/.local/state/alia`, models under `~/.local/share/alia/models`, and preferences under `~/.config/alia/config.json`. Qwen uses an isolated Alia `QWEN_HOME`.

## Bundled profiles

| Profile | Target | Model/download | TG 4K / 32K | PP 4K / 32K | Status |
|---|---|---|---:|---:|---|
| `rtx8gb-16gb-qwen36-35b` | 8 GB VRAM, 16 GB RAM | 35B IQ3_XXS, 14.07 GB | 46.5 / 35.2 | 1,008 / 1,301 | measured, launch config; 32K speed needs free RAM |
| `rtx8gb-qwen35-9b-fast` | 8 GB VRAM, 12 GB RAM | 9B Q4_K_M, 5.7 GB | 65.7 / 57.5 | 2,978 / 2,708 | measured, launch config |
| `rtx12-16gb-qwen36-35b-q4` | 12–16 GB VRAM, 32 GB RAM | 35B Q4_K_XL, 20.8 GB | — | — | unmeasured; never run on target hardware |
| `rtx24gb-qwen36-35b-q4` | 20+ GB VRAM, 32 GB RAM | 35B Q4_K_XL, 20.8 GB | — | — | unmeasured; never run on target hardware |

Automatic selection prefers the highest-ranked matching measured profile and warns before using an unmeasured or manually pinned mismatch. Benchmark methodology and limitations are in [`bench/REPORT.md`](bench/REPORT.md), raw-data inventory in [`bench/results/README.md`](bench/results/README.md), and independent review in [`bench/reviews/grok-bench-review.md`](bench/reviews/grok-bench-review.md).

## Adding a profile

Add an object to `profiles.json`. Use only generic `~/models/...` local candidates. Every numeric measured metric needs a `metric_sources` entry naming its `bench/results/*.jsonl` run and server context; disclose any binary, context, or flag difference from the launch configuration.

```bash
python3 -m json.tool profiles.json >/dev/null
python3 -m unittest discover -s tests -v
./alia profiles
```

## Security

Alia forces `llama-server` to `127.0.0.1:8090`, rejects profile attempts to override host/port, disables llama.cpp's Web UI, and supplies its local API key to both server and Qwen. The server state directory is mode `0700`; state, settings, lock, and log files are mode `0600`. Stop signals target only the recorded PID after checking its Linux start time. State is retained if the process remains alive after SIGKILL, and Alia never uses `pkill`.

Loopback is not an isolation boundary between mutually untrusted local accounts. The fixed local API key is visible to sufficiently privileged local processes, and Qwen Web Shell itself has no additional bearer-token gate. Do not expose either port through SSH forwarding, a reverse proxy, containers, or firewall changes. Do not run parallel Alia sessions with different approval modes because they share one settings file. `--yolo` allows arbitrary tools without confirmation. Ollama unloading talks only to Ollama's loopback API: an unavailable Ollama is ignored, but Alia aborts if discovered models do not unload within 10 seconds.

## Showcase

[Alia, explained by Alia](https://beko2210.github.io/alia/showcase/architecture/) is a page Alia wrote about its own architecture, running locally on the RTX 3070: it read its own source and built the interactive diagram, the animated request flow and the benchmark section. [All prompts](site/showcase/architecture/PROMPTS.md) are published, including what went wrong.

## Development and screenshots

The unit suite is GPU-free and does not start servers or download models:

```bash
python3 -m unittest discover -s tests -v
```

`tools/screenshot.sh` is developer-only and additionally needs tmux plus a Chrome/Chromium executable. It reads an existing pane; it does not launch Alia or tmux.

## Credits and licenses

- [Qwen Code](https://github.com/QwenLM/qwen-code), Apache-2.0
- [llama.cpp](https://github.com/ggml-org/llama.cpp), MIT
- Qwen models and GGUF repositories under their respective licenses

See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Alia launches external components; it does not redistribute them.
