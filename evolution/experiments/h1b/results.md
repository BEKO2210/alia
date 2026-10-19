# H1b: second candidate, new tasks (pilot)

**Question.** H1 showed that `candidate-b.md` made edits more correct but caused unproductive checking. Does the
revised `candidate-b2.md` keep the benefit without the harm?

**Revision.** The candidate now says to search contents with `grep -n` through the shell (glob only lists
names), to remove what the change left unused, and never to repeat a tool call that brings nothing new.

**Setup.** As in H1, with three new tasks so the candidate is not fitted to the old ones (`tasks/`). The runs took
place on 2026-10-19 in mirrored order (1b 1a 2a 2b 3b 3a). The start commit was `653edd2`.

| Task | Arm | Status | Acceptance | Site failures | Change | Wall | Tool calls |
|---|---|---|---|---|---|---|---|
| 01 Copy confirmation | a | failed | 3/3 | 1 | +48 −8 | 251 s | 12 |
| 01 Copy confirmation | b | failed | 0/3 | 0 | none | 77 s | 10 |
| 02 Tab keys | a | passed | 2/2 | 0 | +2 −0 | 86 s | 6 |
| 02 Tab keys | b | passed | 2/2 | 0 | +2 −0 | 105 s | 12 |
| 03 Page title | a | failed | 0/3 | 14 | +9 −0 | 108 s | 7 |
| 03 Page title | b | failed | 1/3 | 2 | +5 −0 | 124 s | 11 |

**What happened.**

- **01a.** Correct behaviour, but a German dictionary key was left unused (`i18n-unused-de`).
- **01b.**
  - Before editing anything, Alia called `glob` with the pattern `site/index.html` six times in a row.
  - Qwen Code's loop guard stopped the run, so nothing was changed.
  - The candidate's own warning about glob did not prevent this.
- **02.** Both arms passed. Arm b used twice as many tool calls, and its only shell command was `git diff --stat`.
- **03a.**
  - Alia declared `const EN` a second time. That is a syntax error, so the page's whole script stopped running.
  - It then reported "Done".
- **03b.**
  - The page title follows the language.
  - The German keys landed in the visible-text dictionary instead of the page head, which left two unused keys.
- **grep.** No run in arm b used `grep`.

**Result.**

- Both arms passed 1 of 3 tasks.
- Acceptance tests: 5/8 in arm a, 3/8 in arm b.

**H1 and H1b together** (one run per task and arm, 6 tasks):

| | Current harness (a) | Candidates (b) |
|---|---|---|
| Tasks passed | 3/6 | 2/6 |
| Acceptance tests | 12/17 | 12/17 |
| Runs stopped by the loop guard | 0/6 | 2/6 |
| Unused or orphaned keys left behind | 2 | 2 |

**Decision.** Prose working rules in `QWEN.md` do not measurably help Alia, and they correlate with glob loops.
Neither candidate is adopted. The recurring failures are leftover translation keys, a script syntax error and
unverified "done" reports. These are exactly what the project's deterministic checks find, but Alia does not run
them on its own. The next experiment therefore feeds the deterministic site-check results back to Alia
(Harness²'s *scripts* component) instead of adding more instructions.

Commits (kept as local refs `refs/evolution/experiments/h1b/{a,b}/round-NN`, pushed as tags `evolution/h1b-ARM-NN`):
01a `bff2ae5`, 02a `155ae5b`, 03a `0650b6c`, 02b `f2689f1`, 03b `bc8034d`; 01b made no change. Tasks frozen at
`7e2cabf`. Transcripts are private.
