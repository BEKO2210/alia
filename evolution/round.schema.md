# Round data schema (version 1)

`round.json` is a JSON object with these public fields. Unknown measurements use `null`, never zero.

- `schema`: integer schema version; `round`: positive integer; `slug`: folder slug; `title`: `{en, de}` strings.
- `level`: integer 1–5; `status`: `planned`, `running`, `passed`, `failed`, `aborted`, or `invalid` (the transcript shows access to round data or the integration
  checkout; see `result.isolation_breaches`, which holds labels, never paths).
- `task_sha256`: SHA-256 of `task.md`.
- `acceptance`: `files` maps each `acceptance/...` path to its SHA-256; `frozen_commit` is an existing Git commit
  containing byte-identical copies of `task.md` and every acceptance file.
- `agent`: `name`, `alia_version`, `launcher_commit`, `profile`, `model`, and `hardware`.
- `start_commit`, `agent_commit`, `merged_commit`: Git commits; the latter two may be `null`.
- `run`: `started`, `wall_seconds`, `wall_limit_seconds`, `exit_code`, `tool_calls`, and `transcript_sha256`.
- `result`: `acceptance_passed`, `acceptance_total`, `site_checks` (either `null` or exact integer counts for
  `failures`, `known`, and `fixed`), `files_changed`, `lines_added`,
  `lines_removed`, and `out_of_scope_paths`.
- `interventions`: objects with `by`, nullable `commit`, and `what`.
- `reviews`: objects with `by`, `verdict`, and `file`.
- `summary`: `{en, de}` strings.
- `attribution` is optional for non-passed rounds and required for passed rounds. It contains `verified`, the
  full `checked_head` commit, named `checks` (`transcript_hash`, `agent_commit_shape`,
  `transcript_covers_diff`, `transcript_tool_calls`, `foreign_commits_declared`, and `share`) with exact
  `{ok, detail}` results, plus non-negative `alia_lines` and `other_lines`. `verified` is true exactly when all
  checks pass. Details are public and must not contain private absolute paths.

The generator validates hashes, folder identity, types, status semantics, and public-data privacy before publishing.
A `passed` round requires verified attribution, exit code zero, at least one passing acceptance test with all tests passing, zero
site-suite failures, at least one in-scope changed file, and no out-of-scope paths or isolation breaches.
