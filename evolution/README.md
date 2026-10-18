# Alia self-evolution rounds

Each real round lives in `evolution/rounds/NN-slug/` and contains:

- `round.json`: validated public metadata and measured results.
- `task.md`: exactly the prompt Alia receives.
- `acceptance/`: tests written and frozen before the run. `round.json` records every file's SHA-256.
- `summary.md`: the public English and German summary.
- `reviews/*.md`: human review reports.

Full transcripts are private and never stored in this repository. Only their SHA-256 digest and event counts are
published. Failed and aborted rounds remain part of the public record.

## How Alia is kept blind to the tests

- `start_commit` is the commit before the round folder is added; the runner refuses a start commit that already
  contains it.
- Alia gets a standalone repository holding only that one commit (depth-1 fetch, no shared object store, no
  `evolution/`).
- The agent runs in an outer bubblewrap jail (`tools/alia_jail.py`): an empty root with read-only `/usr`, `/etc`,
  `/sys`; a throw-away home; only the work copy (read-write) and the program files a run needs (launcher copy
  without `.git`, Qwen Code, the llama.cpp build, the model file) are mounted. The integration checkout, the
  private round folder and every other repository do not exist inside. The environment is cleared; PID, IPC,
  network and other namespaces are new (loopback only); only stdin (`/dev/null`), stdout and stderr are passed.
  `python3 tools/alia_jail.py probe --tools --gpu` checks this with a fake agent and no model.
- The acceptance tests are copied in only after the run, outside the work copy.
- In addition, a transcript that mentions the integration checkout or the round data marks the round `invalid`.
  This is a second line of defence, not the isolation itself.
