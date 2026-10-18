# Alia self-evolution rounds

Each real round lives in `evolution/rounds/NN-slug/` and contains:

- `round.json`: validated public metadata and measured results.
- `task.md`: exactly the prompt Alia receives.
- `acceptance/`: tests written and frozen before the run. `round.json` records every file's SHA-256.
- `summary.md`: the public English and German summary.
- `reviews/*.md`: human review reports.

Full transcripts are private and never stored in this repository. Only their SHA-256 digest and event counts are
published. Failed and aborted rounds remain part of the public record.

## Verifying attribution

The runner builds Alia's commit itself, in its own repository, from a copy of the files the agent left (never
by running git inside the agent's repository), and keeps it in the integration repository as
`refs/evolution/round-NN`. Build the round branch on top of that commit; fixes by anyone else go into separate
commits that are listed in `interventions`.

Then run `python3 tools/alia_round.py verify NN --head <commit> [--private-root DIR]`, where `<commit>` is the
final round-branch state. The command writes a public-safe `attribution` result to `round.json`. It cross-checks
the private transcript hash and tool calls, the commit's parent, trailer, fixed runner identity, paths and
numstat, and every other commit against declared interventions. A Git author name by itself is never evidence
that Alia made a change. A passed round is publishable only when all attribution checks are verified.

## How Alia is kept blind to the tests

- `start_commit` is the commit before the round folder is added; the runner refuses a start commit that already
  contains it.
- Alia gets a fresh one-commit repository built from `git archive` of the start tree without `evolution/`: no
  shared object store, no history, no `FETCH_HEAD`.
- The agent runs in an outer bubblewrap jail (`tools/alia_jail.py`): an empty root with read-only `/usr`, `/etc`,
  `/sys`; a throw-away home; only the work copy (read-write) and the program files a run needs (launcher copy
  without `.git`, Qwen Code, the llama.cpp build, the model file) are mounted. The integration checkout, the
  private round folder and every other repository do not exist inside. The environment is cleared; PID, IPC,
  network and other namespaces are new (loopback only); only stdin (`/dev/null`), stdout and stderr are passed.
  `python3 tools/alia_jail.py probe --tools --gpu` checks this with a fake agent and no model.
- The acceptance tests are copied in only after the run, outside the work copy, and run with `python3 -I`
  against a copy of the agent's files.
- After the run no git command runs in the agent's repository: its `.git` (hooks, config, attributes are all
  agent-controlled) is renamed to `agent-git.untrusted`. Links that point out of the work copy are not copied
  and mark the round `invalid`.
- Before and after the agent runs, the runner verifies the task and acceptance bytes against both their recorded
  SHA-256 values and `acceptance.frozen_commit` in Git.
- In addition, a transcript that mentions the integration checkout or the round data marks the round `invalid`.
  This is a second line of defence, not the isolation itself.

The real runner acquires `~/reel/gpu.lock` itself and starts only when the configured wall-time fits in the GPU
window. It keeps failed private copies for inspection; `python3 tools/alia_round.py run NN --clean` removes only
that round's folder below the private root before a retry.
