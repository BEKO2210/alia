# Alia self-evolution rounds

Each real round lives in `evolution/rounds/NN-slug/` and contains:

- `round.json`: validated public metadata and measured results.
- `task.md`: exactly the prompt Alia receives.
- `acceptance/`: tests written and frozen before the run. `round.json` records every file's SHA-256.
- `summary.md`: the public English and German summary.
- `reviews/*.md`: human review reports.

Full transcripts are private and never stored in this repository. Only their SHA-256 digest and event counts are
published. Failed and aborted rounds remain part of the public record.
