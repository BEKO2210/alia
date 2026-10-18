#!/usr/bin/env python3
"""Outer bubblewrap jail for evolution rounds: the agent sees only what is mounted, not the host.

Nothing of the host home is visible except the round's work copy (read-write) and the program files a
real run needs (read-only, each bound on its own): the launcher copy, Qwen Code, the llama.cpp build and
the model file. The integration checkout, the private round folder (acceptance tests, transcript) and
every other repository are simply not in the mount namespace. The environment is cleared, PID, IPC, UTS,
cgroup and network namespaces are new (only loopback), and the jail dies with its parent.

    python3 tools/alia_jail.py probe   # access test with a fake agent, no model
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GPU_DEVICES = ("/dev/nvidia0", "/dev/nvidiactl", "/dev/nvidia-uvm", "/dev/nvidia-uvm-tools", "/dev/nvidia-modeset")
PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def jail_args(work: Path, home: Path, read_only: list[Path] | tuple[Path, ...] = (), gpu: bool = False,
              env: dict[str, str] | None = None) -> list[str]:
    """bwrap argv prefix. `read_only` paths are bound at their own absolute path; nothing else of $HOME."""
    args = [
        "bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
        "--ro-bind", "/usr", "/usr", "--ro-bind", "/etc", "/etc",
        "--symlink", "usr/bin", "/bin", "--symlink", "usr/sbin", "/sbin",
        "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--tmpfs", "/run", "--tmpfs", "/home",
        "--ro-bind", "/sys", "/sys",
    ]
    if Path("/usr/lib32").exists():
        args += ["--symlink", "usr/lib32", "/lib32"]
    # A private, writable, throw-away home (state and config of the jailed launcher live here).
    args += ["--tmpfs", str(home)]
    for path in read_only:
        # A bound symlink would mount its target file at the link's place and break relative imports
        # (npm bin links); recreate the link instead. Its target must be bound on its own.
        if path.is_symlink():
            args += ["--symlink", os.readlink(path), str(path)]
        else:
            args += ["--ro-bind", str(path), str(path)]
    args += ["--bind", str(work), str(work)]
    if gpu:
        for device in GPU_DEVICES:
            if Path(device).exists():
                args += ["--dev-bind", device, device]
    variables = {"PATH": PATH, "HOME": str(home), "LANG": "C.UTF-8", "TERM": "dumb", **(env or {})}
    for key, value in variables.items():
        args += ["--setenv", key, value]
    return args + ["--chdir", str(work)]


def run_jailed(prefix: list[str], argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    # close_fds (the default) plus stdin from /dev/null: no host file descriptor reaches the agent except
    # stdout/stderr, which the caller points at private files outside the jail.
    return subprocess.run([*prefix, "--", *argv], stdin=subprocess.DEVNULL, close_fds=True, check=False, **kwargs)


PROBE = r'''
import json, os, subprocess, sys
targets = json.loads(sys.argv[1])
out = {}
def can_read(path):
    try:
        with open(path, "rb") as handle:
            handle.read(1)
        return True
    except OSError:
        return False
out["read"] = {label: can_read(path) for label, path in targets["absolute"].items()}
out["exists"] = {label: os.path.exists(path) for label, path in targets["absolute"].items()}
out["relative"] = {rel: can_read(rel) for rel in targets["relative"]}
out["symlink"] = can_read("probe-link")
out["home_listing"] = sorted(os.listdir(os.path.expanduser("~")))
out["root_listing"] = sorted(os.listdir("/"))
git = subprocess.run(["git", "cat-file", "-p", targets["blob"]], capture_output=True, text=True)
out["git_alternates_blob"] = git.returncode == 0 and targets["canary"] in git.stdout
hits = []
for base in ("/", os.path.expanduser("~")):
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if root != "/" or d not in ("proc", "sys", "dev", "usr")]
        for name in files:
            path = os.path.join(root, name)
            try:
                with open(path, "rb") as handle:
                    if targets["canary"].encode() in handle.read(1_000_000):
                        hits.append(path)
            except OSError:
                pass
out["canary_files"] = sorted(set(hits))
out["env_leaks"] = sorted(k for k, v in os.environ.items() if any(m in v for m in targets["markers"]))
out["fds"] = sorted(f"{fd}->{os.readlink(f'/proc/self/fd/{fd}')}" for fd in os.listdir("/proc/self/fd")
                    if os.path.exists(f"/proc/self/fd/{fd}"))
cwds = []
for pid in os.listdir("/proc"):
    if pid.isdigit():
        try:
            cwds.append(os.readlink(f"/proc/{pid}/cwd"))
        except OSError:
            pass
out["proc_cwds"] = sorted(set(cwds))
import socket
def connect(address):
    s = socket.socket(socket.AF_UNIX)
    try:
        s.connect(address)
        return True
    except OSError:
        return False
    finally:
        s.close()
out["x11_abstract_socket"] = connect("\0/tmp/.X11-unix/X0")
out["dbus_session"] = os.path.exists(f"/run/user/{os.getuid()}/bus")
def tcp(port):
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()
out["host_ollama_port"] = tcp(11434)
out["write_outside_work"] = {}
for path in ("/usr/escape.txt", "/etc/escape.txt", "/sys/escape.txt"):
    try:
        with open(path, "w") as handle:
            handle.write("x")
        out["write_outside_work"][path] = True
    except OSError:
        out["write_outside_work"][path] = False
tools = {}
for name, argv in targets["tools"].items():
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        tools[name] = {"exit": done.returncode, "out": (done.stdout + done.stderr).strip().splitlines()[:2]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        tools[name] = {"exit": None, "out": [str(exc)]}
out["tools"] = tools
print(json.dumps(out))
'''


def probe(args: argparse.Namespace) -> int:
    """Plant a canary where the hidden tests live, run the probe agent jailed, report what it could reach."""
    repo = Path(__file__).resolve().parents[1]
    home = Path.home()
    canary = "ALIA-JAIL-CANARY-" + os.urandom(6).hex()
    with tempfile.TemporaryDirectory(prefix="alia-jail-", dir=args.private_root) as private:
        private_round = Path(private) / "99-probe"
        work = private_round / "work"
        acceptance = private_round / "acceptance-run"
        work.mkdir(parents=True)
        acceptance.mkdir()
        (acceptance / "test_hidden.py").write_text(f"# {canary}\n", encoding="utf-8")
        hidden_in_repo = repo / "evolution" / "rounds" / "99-probe" / "acceptance"
        hidden_in_repo.mkdir(parents=True)
        (hidden_in_repo / "test_hidden.py").write_text(f"# {canary}\n", encoding="utf-8")
        try:
            # A decoy object store outside the jail holds the canary; the work copy points at it via alternates.
            # (Not the real repository's store: the probe must not write into it.)
            decoy = private_round / "decoy.git"
            subprocess.run(["git", "init", "-q", "--bare", str(decoy)], check=True)
            blob = subprocess.run(["git", "--git-dir", str(decoy), "hash-object", "-w", "--stdin"], input=canary,
                                  check=True, capture_output=True, text=True).stdout.strip()
            subprocess.run(["git", "init", "-q", str(work)], check=True)
            objects = str(decoy / "objects")
            (work / ".git/objects/info/alternates").write_text(objects + "\n", encoding="utf-8")
            (work / "probe-link").symlink_to(hidden_in_repo / "test_hidden.py")
            (work / "probe.py").write_text(PROBE, encoding="utf-8")
            real = [p for p in args.bind if p.exists()]
            targets = {
                "canary": canary,
                "blob": blob,
                "markers": [str(repo), str(private_round / "acceptance-run")],
                "absolute": {
                    "hidden-test-in-integration-repo": str(hidden_in_repo / "test_hidden.py"),
                    "hidden-test-in-private-round": str(acceptance / "test_hidden.py"),
                    "integration-round-json": str(repo / "evolution" / "README.md"),
                    "repo-git-config": str(repo / ".git"),
                    "decoy-object-store": objects,
                    "ssh-dir": str(home / ".ssh"),
                    "codex-auth": str(home / ".codex" / "auth.json"),
                    "alia-config": str(home / ".config" / "alia" / "config.json"),
                },
                "relative": ["../acceptance-run/test_hidden.py", "../../../../evolution/README.md",
                             "../../../" + repo.name + "/evolution/README.md"],
                "tools": {name: argv for name, argv in TOOLS.items() if args.tools},
            }
            prefix = jail_args(work, home, read_only=real, gpu=args.gpu)
            done = run_jailed(prefix, ["python3", "probe.py", json.dumps(targets)], capture_output=True, text=True)
        finally:
            shutil.rmtree(repo / "evolution" / "rounds" / "99-probe")
            rounds = repo / "evolution" / "rounds"
            if rounds.is_dir() and not any(rounds.iterdir()):
                rounds.rmdir()
        if done.returncode != 0:
            print(done.stderr, file=sys.stderr)
            return 1
        result = json.loads(done.stdout)
    result["leaks"] = leaks(result, canary)
    print(json.dumps(result, indent=2))
    return 1 if result["leaks"] else 0


def leaks(result: dict, canary: str) -> list[str]:
    found = [f"read {label}" for label, ok in result["read"].items() if ok]
    found += [f"exists {label}" for label, ok in result["exists"].items() if ok]
    found += [f"relative {rel}" for rel, ok in result["relative"].items() if ok]
    found += ["symlink to hidden test"] if result["symlink"] else []
    found += ["git alternates expose hidden blob"] if result["git_alternates_blob"] else []
    found += [f"canary in {path}" for path in result["canary_files"]]
    found += [f"env {key}" for key in result["env_leaks"]]
    found += ["X11 socket"] if result["x11_abstract_socket"] else []
    found += ["D-Bus session"] if result["dbus_session"] else []
    found += ["host port 11434"] if result["host_ollama_port"] else []
    found += [f"wrote {path}" for path, ok in result["write_outside_work"].items() if ok]
    return found


HOME = Path.home()
TOOLS = {
    "python3": ["python3", "--version"],
    "git": ["git", "--version"],
    "node": ["node", "--version"],
    "qwen": [str(HOME / ".npm-global/bin/qwen"), "--version"],
    "llama-server": [str(HOME / "src/llama.cpp/build/bin/llama-server"), "--version"],
    "nvidia-smi": ["nvidia-smi", "-L"],
    "nested-bwrap": ["bwrap", "--unshare-all", "--die-with-parent", "--ro-bind", "/", "/", "true"],
}
REAL_BINDS = (
    HOME / ".npm-global/bin/qwen",
    HOME / ".npm-global/lib/node_modules/@qwen-code",
    HOME / "src/llama.cpp/build/bin",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("probe", help="access test with a fake agent (no model)")
    p.add_argument("--private-root", type=Path, default=Path.home() / "alia-evolution-private",
                   help="where the temporary round folder goes (outside every repository)")
    p.add_argument("--tools", action="store_true", help="also check that Qwen Code, llama-server etc. start")
    p.add_argument("--gpu", action="store_true", help="bind the NVIDIA devices (for --tools)")
    p.add_argument("--bind", type=Path, nargs="*", default=list(REAL_BINDS), help="read-only program paths")
    args = parser.parse_args(argv)
    args.private_root.mkdir(parents=True, exist_ok=True)
    return probe(args)


if __name__ == "__main__":
    raise SystemExit(main())
