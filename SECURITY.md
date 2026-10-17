# Security policy

## Scope

Alia runs entirely on your machine. It starts `llama-server` bound to
`127.0.0.1` and opens Qwen Code against it. Nothing is sent to a cloud API.

Things we treat as security bugs:

- the server or the web shell listening on anything other than loopback by default
- Alia killing, signalling or reusing a process it did not start
- path or argument injection through `profiles.json`, environment variables or CLI flags
- any network call that is not a model download the user confirmed

Note that `--yolo` deliberately lets the agent run shell commands without asking.
That is a documented mode, not a vulnerability.

## Opt-in sandbox (`alia --sandbox`)

`alia --sandbox` turns on Qwen Code 0.25.1's `tools.executionSandbox` with
`filesystem: "workspace-write"` and `network: "closed"`, enforced by bubblewrap
(`bwrap` must be installed; Landlock alone cannot close the network, so Alia does
not accept it). Only the tool processes are confined; the model traffic of Qwen
Code itself stays on the host, so the local model server keeps working.

What it protects against:

- tool commands writing outside the project directory (the rest of the host is read-only for them)
- tool commands opening network connections, including to other services on 127.0.0.1

What it does not protect against:

- **reads**: host files such as `~/.ssh` stay readable for tool commands, and pathname Unix sockets stay reachable;
  a prompt injection can still copy a secret into a project file
- what the agent writes inside the project: review diffs as usual; approval modes still apply,
  and `--yolo` approves every confined command without asking
- `--yolo` without `--sandbox`: arbitrary commands with your full user rights
- anything that needs a network from tools (e.g. `pip install`, tests against a local service) fails in the sandbox

Limits of Qwen Code 0.25.1 (checked in its bundle):

- MCP servers are not supported with the sandbox at all (they are not started outside it either);
  Alia refuses `--sandbox` while `alia mcp` servers are enabled. Bundle: `chunks/chunk-H7X3QFRG.js`
  line 3, `admitShellSandbox` throws "Tool execution sandbox does not support … MCP …" when
  `mcpServers` is non-empty.
- `qwen serve` rejects the sandbox, so `alia web --sandbox` is an error. Bundle:
  `chunks/run-qwen-serve-OSNAVHMF.js` line 47 calls
  `assertExecutionSandboxSupported(bootSettings, "serve / ACP / web terminals")`, which throws
  "tools.executionSandbox does not yet support serve / ACP / web terminals".
- File checkpoints (`/rewind` code restore) are off in the sandbox. Before the session Alia stores
  uncommitted tracked changes with `git stash create` in `refs/alia/pre-session` and prints
  `git stash apply --index refs/alia/pre-session` (restores staged and unstaged changes). `git stash create`
  runs on a temporary copy of the index (`GIT_INDEX_FILE`), so the working tree, `.git/index` and the stash
  list are not touched (with `core.splitIndex` enabled, git may still write a `sharedindex.*` file in `.git`);
  untracked files are not included (Alia warns). If it fails (for example during an
  unfinished merge), Alia stops before anything starts. The ref is written with a reflog, so a snapshot
  replaced by a later session stays reachable through `git reflog refs/alia/pre-session` until the reflog
  entry expires (`gc.reflogExpireUnreachable`, 30 days by default) and `git gc` runs. Before the sandbox
  starts, Alia also runs a short `bwrap` probe and refuses `--sandbox` if bwrap cannot create a sandbox.
  The snapshot's git calls run with `LC_ALL=C`, so their error messages are the same on every host.
- The workspace (the current directory, symlinks resolved) must not be `$HOME` or a directory above it,
  and must not contain or lie inside Alia's `QWEN_HOME` or the Qwen Code installation directory. Qwen Code
  refuses such a workspace ("overlaps protected state or installation"); Alia stops earlier with a message
  naming both paths. A project below `$HOME` is fine.

## Reporting

Please report privately via
[GitHub Security Advisories](https://github.com/BEKO2210/alia/security/advisories/new)
or by e-mail to nullmesh@protonmail.com. Expect a first reply within a week.

## Supported versions

Only the latest release receives fixes.
