# H1: verification rules in Alia's harness (pilot)

**Question.** Does a short set of working rules in Qwen Code's global `QWEN.md` (`candidate-b.md`,
SHA-256 `d272b73d7c03…`) make Alia's website fixes more reliable? The rules come from round 01, where Alia changed
HTML without checking the script that depended on it and then reported success.

**Setup.** Three frozen tasks (`tasks/`), each run once per arm on 2026-10-19 with Alia 0.1.0 and
Qwen3.6-35B-A3B UD-IQ3_XXS on an RTX 3070 (8 GB). The arms ran in alternating order (1a 1b 2b 2a 3a 3b).
Arm a used the current harness. Arm b used the same harness plus `candidate-b.md`, seeded by
`alia_round.py run --harness`. The launcher was not changed. The judges were the frozen acceptance tests and the
site checks; no model judged the runs. A run passes only if it ends cleanly, passes all acceptance tests and
causes no new site-check failure.

| Task | Arm | Status | Acceptance | Site failures | Change | Wall | Tool calls |
|---|---|---|---|---|---|---|---|
| 01 JSON labels | a | failed | 1/3 | 0 | +3 −1 | 90 s | 6 |
| 01 JSON labels | b | failed | 3/3 | 1 | +4 −2 | 105 s | 9 |
| 02 Replay button | a | passed | 3/3 | 0 | +6 −1 | 91 s | 5 |
| 02 Replay button | b | failed | 3/3 | 0 | +6 −1 | 180 s | 16 |
| 03 Link targets | a | passed | 3/3 | 0 | +3 −3 | 244 s | 15 |
| 03 Link targets | b | passed | 3/3 | 0 | +2 −2 | 200 s | 11 |

**What happened.**

- **01a.**
  - Alia gave the Qwen3.5 9B row its own key and a correct German text.
  - It also inserted a copy of the Qwen3.6 row into the 9B card.
  - It reported "The JavaScript already handles this automatically" without having checked it.
- **01b.**
  - The fix is correct in both languages (3/3).
  - It left the German entry for the old key `q.json` in `main.js` unused. That is a new site-check failure (`i18n-unused-de`).
- **02b.**
  - The CSS change is correct (3/3).
  - While checking it, Alia repeated the same `glob` call; `glob` only lists files and does not search their content.
  - Qwen Code's always-on loop guard then stopped the run (exit 1).
- **03.** Both arms passed. Arm b changed fewer lines and needed fewer calls.
- **Checks in arm b.** No run of arm b executed a test or the project's site checks. The candidate rule "run the existing checks" had no visible effect.

**Result.**

- Arm a passed 2 of 3 tasks, arm b 1 of 3.
- Acceptance tests: 7/9 in arm a, 9/9 in arm b.
- The candidate made the edits themselves more correct, but it introduced a new failure: unproductive checking that ran into the loop guard. It also did not lead Alia to run any checks.
- With one run per task and arm, this is a pilot, not a measurement.
- **Decision: `candidate-b.md` is not adopted.**

**Next candidate (B2), to be tested on new tasks so it is not fitted to these three:**

- Name the checking tool: search contents with `grep -n` through the shell.
- Forbid repeating a check that gave no new information.
- Ask Alia to remove what its own change made unused.

Commits (kept as local refs `refs/evolution/experiments/h1/{a,b}/round-NN`, pushed as tags `evolution/h1-ARM-NN`): 01a `4413f90`, 02a `e9702d3`,
03a `5926d4f`, 01b `216cbc5`, 02b `aaf4583`, 03b `22d3a98`. Tasks frozen at `73bbcf8` (hashes recorded in `41d8638`). Transcripts are private.

**Side finding.** Task 01 describes a real defect of the live page. `main.js` builds its English dictionary from
the HTML, so the second `q.json` entry overwrites the first. As a result, both cards also show "JSON schema" in
English. This is a candidate for a real round.
