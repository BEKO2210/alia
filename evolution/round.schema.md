# Round data schema (version 1)

`round.json` is a JSON object with these public fields. Unknown measurements use `null`, never zero.

- `schema`: integer schema version; `round`: positive integer; `slug`: folder slug; `title`: `{en, de}` strings.
- `level`: integer 1–5; `status`: `planned`, `running`, `passed`, `failed`, or `aborted`.
- `task_sha256`: SHA-256 of `task.md`.
- `acceptance`: `files` maps each `acceptance/...` path to its SHA-256; `frozen_commit` is a Git commit.
- `agent`: `name`, `alia_version`, `launcher_commit`, `profile`, `model`, and `hardware`.
- `start_commit`, `agent_commit`, `merged_commit`: Git commits; the latter two may be `null`.
- `run`: `started`, `wall_seconds`, `wall_limit_seconds`, `exit_code`, `tool_calls`, and `transcript_sha256`.
- `result`: `acceptance_passed`, `acceptance_total`, `site_checks`, `files_changed`, `lines_added`,
  `lines_removed`, and `out_of_scope_paths`.
- `interventions`: objects with `by`, nullable `commit`, and `what`.
- `reviews`: objects with `by`, `verdict`, and `file`.
- `summary`: `{en, de}` strings.

The generator validates hashes, folder identity, types, status semantics, and public-data privacy before publishing.
