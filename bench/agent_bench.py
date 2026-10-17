#!/usr/bin/env python3
"""Agentic coding benchmark: real repo tasks solved by Qwen Code with Alia's settings.

Starts llama-server with a GGUF and the launch flags of an Alia profile, runs Qwen Code headless
(`qwen PROMPT --yolo`) once per task in a fresh copy of agent_tasks/<task>/repo, then scores the
result with agent_tasks/<task>/hidden_test.py, which the agent never sees.

  flock -w 60 ~/reel/gpu.lock python3 agent_bench.py --name qwen36 --gguf ~/models/gguf/mtp/X.gguf
  ... --template ~/models/gguf/templates/x.jinja   # override the GGUF's chat template

Results: results/agent-<timestamp>.jsonl, agent diffs in results/agent-logs/<name>-<timestamp>/.
"""
import argparse
import datetime as dt
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TASKS = HERE / "agent_tasks"
# Gate tasks for features outside the frozen set (MCP browser/search, context files); run them by name.
LIVE_TASKS = HERE / "live_tasks"
WEB_PORT = 8766  # live_tasks/browser/prompt.txt points here
OUT = HERE / "results"
PORT = 8097

loader = importlib.machinery.SourceFileLoader("alia", str(ROOT / "alia"))
spec = importlib.util.spec_from_loader("alia", loader)
alia = importlib.util.module_from_spec(spec)
loader.exec_module(alia)


def wait_ready(proc: subprocess.Popen, timeout: float = 600) -> float:
    start = time.time()
    while time.time() - start < timeout:
        if proc.poll() is not None:
            raise SystemExit("llama-server exited during load")
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{PORT}/health", headers={"Authorization": f"Bearer {alia.API_KEY}"})
            with urllib.request.urlopen(request, timeout=2) as response:
                if response.status == 200:
                    return time.time() - start
        except OSError:
            pass
        time.sleep(1)
    raise SystemExit("llama-server not ready")


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def server_metrics() -> dict[str, float]:
    """Prometheus counters of the bench server; prompt_tokens_total counts only tokens it had to evaluate."""
    request = urllib.request.Request(f"http://127.0.0.1:{PORT}/metrics",
                                     headers={"Authorization": f"Bearer {alia.API_KEY}"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            text = response.read().decode()
    except OSError:
        return {}
    return {m.group(1): float(m.group(2)) for m in re.finditer(r"^llamacpp:(\w+) ([0-9.eE+-]+)$", text, re.M)}


def metrics_delta(before: dict[str, float], after: dict[str, float]) -> dict:
    keys = {"prompt_tokens_total": "evaluated_prompt_tokens", "prompt_seconds_total": "prompt_eval_s",
            "tokens_predicted_total": "generated_tokens", "tokens_predicted_seconds_total": "generation_s"}
    # A failed scrape on either side would turn the delta into a cumulative counter.
    return {name: round(after[key] - before[key], 1) for key, name in keys.items()
            if key in after and key in before}


def run_tests(workdir: Path) -> tuple[int, int, str]:
    result = subprocess.run(["python3", "-m", "unittest", "-v", "hidden_test"], cwd=workdir,
                            capture_output=True, text=True, timeout=120)
    ran = re.search(r"Ran (\d+) test", result.stderr)
    total = int(ran.group(1)) if ran else 0
    bad = re.search(r"FAILED \((.*)\)", result.stderr)
    failed = sum(int(n) for n in re.findall(r"=(\d+)", bad.group(1))) if bad else 0
    return total - failed, total, result.stderr[-3000:]


def qwen_stats(stdout: str) -> dict:
    try:
        result = [x for x in json.loads(stdout) if x.get("type") == "result"][-1]
    except (ValueError, IndexError, AttributeError, TypeError):
        return {}
    stats = result.get("stats", {})
    tokens = next(iter(stats.get("models", {}).values()), {}).get("tokens", {})
    tools = stats.get("tools", {})
    return {"turns": result.get("num_turns"), "output_tokens": tokens.get("candidates"),
            "thought_tokens": tokens.get("thoughts"), "tool_calls": tools.get("totalCalls"),
            "tool_fails": tools.get("totalFail"), "qwen_error": result.get("is_error"),
            "prompt_tokens": tokens.get("prompt")}


def probe(qenv: dict[str, str], wall: int) -> dict:
    """One trivial request in an empty directory: start-up overhead and first-prompt size."""
    with tempfile.TemporaryDirectory() as work:
        start = time.time()
        run = subprocess.run([*alia.build_qwen_command(["Reply with the single word OK.", "--yolo",
                                                        "--max-wall-time", f"{wall}s", "-o", "json"])],
                             cwd=work, env=qenv, capture_output=True, text=True, timeout=wall + 60)
        return {"seconds": round(time.time() - start, 1), "exit": run.returncode, **qwen_stats(run.stdout)}


def _terminate(signum, frame):
    raise SystemExit(f"stopped by signal {signum}")


def main() -> None:
    signal.signal(signal.SIGTERM, _terminate)  # run the finally block, so llama-server is never orphaned
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--gguf", required=True)
    ap.add_argument("--template", default=None, help="--chat-template-file for llama-server")
    ap.add_argument("--profile", default="rtx8gb-16gb-qwen36-35b")
    ap.add_argument("--tasks", default=None, help="comma list; default all")
    ap.add_argument("--wall", type=int, default=600, help="Qwen Code --max-wall-time per task, seconds")
    ap.add_argument("--server-arg", action="append", default=[],
                    help="extra llama-server argument for A/B runs, e.g. --server-arg=--no-reasoning-preserve")
    ap.add_argument("--server-args", default=None,
                    help="JSON list replacing the profile's server_args (other models, e.g. without MTP flags)")
    ap.add_argument("--mcp", default="", help="comma list of Alia MCP servers to enable, e.g. browser,search")
    ap.add_argument("--probe", action="store_true", help="time a cold and a warm one-word reply first")
    ap.add_argument("--repeat", type=int, default=1, metavar="N", help="run each task N times (noise check)")
    a = ap.parse_args()
    if a.repeat < 1:
        ap.error("--repeat must be at least 1")

    profile = next(p for p in alia.load_profiles() if p["id"] == a.profile)
    try:
        server_args = json.loads(a.server_args) if a.server_args is not None else profile["server_args"]
    except json.JSONDecodeError as exc:
        ap.error(f"--server-args must be a JSON list of strings: {exc}")
    if not isinstance(server_args, list) or not all(isinstance(arg, str) for arg in server_args):
        ap.error("--server-args must be a JSON list of strings")
    binary, env_extra = alia.find_llama_server()
    args = [str(binary), "-m", str(Path(a.gguf).expanduser()), "-c", str(profile["ctx"]),
            *map(str, server_args), "--no-webui", "--api-key", alia.API_KEY,
            "--host", "127.0.0.1", "--port", str(PORT), "--alias", profile["id"], "--metrics"]
    args += a.server_arg
    if a.template:
        args += ["--chat-template-file", str(Path(a.template).expanduser())]
    tasks = a.tasks.split(",") if a.tasks else sorted(p.name for p in TASKS.iterdir() if (p / "prompt.txt").exists())

    stamp = f"{dt.datetime.now():%Y%m%d-%H%M%S}"
    OUT.mkdir(exist_ok=True)
    logs = OUT / "agent-logs" / f"{a.name}-{stamp}"
    logs.mkdir(parents=True)
    out_path = OUT / f"agent-{stamp}.jsonl"

    alia.unload_ollama()
    free = alia.mem_available_gb()
    env = {**os.environ, **env_extra}
    with open(logs / "llama-server.log", "w") as log:
        proc = subprocess.Popen(args, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        load_s = wait_ready(proc)
        with tempfile.TemporaryDirectory() as home_dir:
            qwen_home = Path(home_dir) / "qwen-home"
            hw = alia.detect_hardware()
            mcp = [name for name in a.mcp.split(",") if name]
            settings = alia.generate_settings(profile, hw, qwen_home, approval_mode="yolo", language="en", mcp=mcp)
            text = settings.read_text().replace(f":{alia.PORT}/v1", f":{PORT}/v1")
            settings.write_text(text)
            qenv = alia.qwen_environment({"qwen_home": qwen_home})
            with out_path.open("w") as f:
                agent_rows = []
                f.write(json.dumps({"mode": "env", "name": a.name, "gguf": Path(a.gguf).name,
                                    "template": Path(a.template).name if a.template else None,
                                    "profile": profile["id"], "ctx": profile["ctx"], "mcp": a.mcp or None,
                                    "server_args": server_args + a.server_arg, "load_s": round(load_s, 1),
                                    "mem_available_gb": round(free, 1) if free else None,
                                    "wall_limit_s": a.wall, "ts": time.time()}) + "\n")
                for label in ("cold", "warm") if a.probe else ():
                    before = server_metrics()
                    row = {"mode": "probe", "name": a.name, "task": f"probe-{label}", **probe(qenv, 120)}
                    row.update(metrics_delta(before, server_metrics()))
                    f.write(json.dumps(row) + "\n")
                    print(f"{a.name:14} {row['task']:10} {row['seconds']:5.1f} s  "
                          f"prompt {row.get('prompt_tokens')} tokens", flush=True)
                for task in tasks:
                    source = TASKS / task if (TASKS / task).exists() else LIVE_TASKS / task
                    web = None
                    if (source / "web").is_dir():
                        web = subprocess.Popen(["python3", "-m", "http.server", str(WEB_PORT), "--bind", "127.0.0.1"],
                                               cwd=source / "web", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    for run_number in range(1, a.repeat + 1):
                        with tempfile.TemporaryDirectory() as work:
                            workdir = Path(work) / task
                            shutil.copytree(source / "repo", workdir)
                            (workdir / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
                            subprocess.run(["git", "init", "-q"], cwd=workdir, check=True)
                            subprocess.run(["git", "add", "-A"], cwd=workdir, check=True)
                            subprocess.run(["git", "-c", "user.name=bench", "-c", "user.email=bench@localhost",
                                            "commit", "-qm", "start"], cwd=workdir, check=True)
                            prompt = (source / "prompt.txt").read_text().strip()
                            before = server_metrics()
                            start = time.time()
                            try:
                                run = subprocess.run(
                                    [*alia.build_qwen_command([prompt, "--yolo", "--max-wall-time", f"{a.wall}s",
                                                               "-o", "json"])],
                                    cwd=workdir, env=qenv, capture_output=True, text=True, timeout=a.wall + 120)
                                code, stdout = run.returncode, run.stdout
                            except subprocess.TimeoutExpired as exc:
                                raw = exc.stdout or ""
                                code, stdout = "timeout", raw.decode(errors="replace") if isinstance(raw, bytes) else raw
                            seconds = time.time() - start
                            served = metrics_delta(before, server_metrics())
                            try:
                                subprocess.run(["git", "add", "-A"], cwd=workdir, timeout=120)
                                diff = subprocess.run(["git", "diff", "--cached", "HEAD"], cwd=workdir,
                                                      capture_output=True, text=True, timeout=120).stdout
                            except subprocess.TimeoutExpired:
                                diff = "git add/diff timed out\n"
                            log_name = f"{task}-run{run_number}" if a.repeat > 1 else task
                            (logs / f"{log_name}.diff").write_text(diff)
                            (logs / f"{log_name}.qwen.json").write_text(stdout[-200000:])
                            shutil.copy(source / "hidden_test.py", workdir / "hidden_test.py")
                            try:
                                passed, total, tail = run_tests(workdir)
                            except subprocess.TimeoutExpired:
                                passed, total, tail = 0, 0, "hidden tests timed out"
                            (logs / f"{log_name}.tests.txt").write_text(tail)
                        row = {"mode": "agent", "name": a.name, "task": task, "run": run_number,
                               "pass": total > 0 and passed == total, "tests_passed": passed,
                               "tests_total": total, "seconds": round(seconds, 1), "exit": code,
                               "ts": time.time()}
                        row.update(qwen_stats(stdout))
                        row.update(served)
                        agent_rows.append(row)
                        f.write(json.dumps(row) + "\n")
                        f.flush()
                        print(f"{a.name:14} {task:10} #{run_number} "
                              f"{'PASS' if row['pass'] else 'fail'} {passed}/{total} tests  "
                              f"{seconds:5.0f} s  exit {code}", flush=True)
                    if web is not None:
                        web.terminate()
                        web.wait()
                summary = {
                    "mode": "summary", "passed": sum(row["pass"] for row in agent_rows),
                    "tasks": len(agent_rows), "seconds": round(sum(row["seconds"] for row in agent_rows), 1),
                }
                for field in ("evaluated_prompt_tokens", "generated_tokens", "tool_calls", "tool_fails"):
                    values = [row[field] for row in agent_rows
                              if isinstance(row.get(field), (int, float))]
                    if values:
                        summary[field] = round(sum(values), 1)
                f.write(json.dumps(summary) + "\n")
                print(f"summary: {summary['passed']}/{summary['tasks']} PASS · {summary['seconds']:g} s · "
                      f"evaluated prompt {summary.get('evaluated_prompt_tokens', 0):g} tok · "
                      f"generated {summary.get('generated_tokens', 0):g} tok · "
                      f"tools {summary.get('tool_calls', 0):g} calls / "
                      f"{summary.get('tool_fails', 0):g} failed", flush=True)
    finally:
        stop(proc)
    print(f"raw results: {out_path}")


if __name__ == "__main__":
    main()
