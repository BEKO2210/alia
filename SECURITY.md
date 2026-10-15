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

## Reporting

Please report privately via
[GitHub Security Advisories](https://github.com/BEKO2210/alia/security/advisories/new)
or by e-mail to nullmesh@protonmail.com. Expect a first reply within a week.

## Supported versions

Only the latest release receives fixes.
