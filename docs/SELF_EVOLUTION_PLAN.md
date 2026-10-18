# Alia Self-Evolution: phase A (audit, architecture, plan)

Status 2026-10-18: phase A only. Nothing on the site, in Alia or in CI changes until Belkis releases phase B.
Local branch `evolution/plan` (worktree `alia-evo`, from origin/main 1052a7c), not pushed. M1, F1, F2 and G are
unaffected and stay closed or independent.

## 1. Audit (evidence)

**Repository and deployment.**
- `BEKO2210/alia` (public). The site lives in `site/` and is plain HTML, CSS and vanilla JS, with no framework
  and no build step.
- `.github/workflows/pages.yml` deploys `site/` to https://beko2210.github.io/alia/ on every push to `main` that
  touches `site/**`. Deploys therefore happen only through Belkis's merges.
- The live page is byte-identical to origin/main.
- The local productive checkout is 6 commits behind origin/main and is left alone.

**Main page** (`site/index.html`, 301 lines; `main.js` 158; `style.css` 253):
- Sections: hero (demo video), stats, `#features`, `#benchmarks`, `#screens`, `#showcase` ("Alia, explained by
  Alia"), `#stack`, `#install`, final CTA, footer.
- i18n: EN lives in the HTML, DE is a dictionary in `main.js`.
- The site weighs 7.8 MB, 7.4 MB of it the two demo videos.

**The page where Alia explains itself already exists:** `site/showcase/architecture/` (953 lines, single file).
It holds:
- an interactive layer diagram;
- the request flow ("Alia is not in the token path");
- benchmark cards;
- component details.

Alia wrote it with Qwen3.6-35B on the RTX 3070 (15-16 Oct., PR #3/#5). `PROMPTS.md` holds all 17 prompts and a
"What did not work" section. This is the first piece of "Built by Alia" evidence. Its content is stale:
- it says v0.1.0;
- it shows 46.5 instead of 49.9 tok/s;
- it calls the Q4 profiles "unmeasured", although they are measured since #22;
- there is no link back to the main site, no favicon or meta description, and two `<h1>`.

**Tests and CI for the site: none.**
- `ci.yml` checks Python, ruff, shellcheck and JSON, plus a personal-data grep that also covers `site/`.
- There is no link check, no a11y check, no Lighthouse and no visual test.

**Real defects found** (Playwright screenshots at 390 and 1280 px):

| defect | detail |
|---|---|
| copy button covers code | install steps 1-3 at 390 px, step 2 at 1280 px. Cause: `.code pre` scrolls under the absolutely positioned button; `padding-right: 76px` only helps at the scroll end (`style.css:215,217`). Checked myself in the screenshot |
| one i18n key for two labels | key `q.json` carries "JSON with / without schema" (35B card) and "JSON schema" (9B card) (`index.html:178,188`), so one card shows the wrong label in each language |
| contrast below WCAG AA | `--mut2` #6b7486 on #07080c is 4.26:1 (AA needs 4.5:1), used by small captions |
| small tap targets | nav 23 px, Replay 22 px, Security 22 px |
| old poster | the desktop poster still shows the 0.1.0 banner |
| mobile video crops terminal lines | in the video itself, not in CSS |
| site files missing | no `og:image`, `og:url` or canonical; robots.txt, sitemap, favicon and 404 all 404 |
| copy and data | `CHANGELOG.md` has the [Unreleased] "Changed" block twice; the claim "every benchmark number links to raw JSONL" is too strong (one shared link) |

No broken links, no console errors, no horizontal scrolling. Every image has alt text, and the landmarks are
complete.

**Data sources for a static self-evolution section:**
- `profiles.json`: measured blocks, each with a `source` pointing to its JSONL;
- `CHANGELOG.md`;
- `bench/results/` (107 JSONL files plus a README);
- `docs/ALIA_ARCHITECTURE.md`;
- `site/showcase/architecture/PROMPTS.md`.

**AI team** (`ai-team status`, 18 Oct. 15:24):
- Claude 85 % of the 5-hour window and **28 % of the week left** (reset 19 Oct. 15:00);
- Codex data 19 h old, so no statement about its current availability;
- Grok, Cursor, Antigravity, Copilot: quota UNKNOWN (no CLI shows it).
- Headless commands and limits as in the team notes:
  - Cursor: only `composer-2.5`;
  - Antigravity: `gemini-3.8-flash-high`, at most about 10-15 screenshots per run;
  - Grok: no `spawn_subagent`;
  - Copilot: works as the PR review bot.

## 2. Architecture and design concept

**Principle: extend the existing site, do not build a second one.** It stays static, has no backend, no new
framework and no build step. The main page keeps its structure.

**Name and place.** `site/evolution/` gets the "Alia Self-Evolution" pages, in EN and DE with the same i18n
pattern as the main page. "Alia, explained by Alia" is already the showcase's title, so the new section gets its
own name.

| page | content |
|---|---|
| `evolution/` (overview) | what Alia is, how it works (interactive flow: task -> Qwen Code -> local model -> tools -> change -> tests -> result), entry to the other parts |
| `evolution/built-by-alia/` | every round as a card: task, level, Alia result (passed or failed), tests, Alia's share of the merged diff, reviews, links to commit, transcript and tests |
| `evolution/changelog/` | from `CHANGELOG.md` (planned / running / done / dropped from the round data) |
| `evolution/metrics/` | dashboard of real measured values: per-profile speeds from `profiles.json` (each with its source link), round statistics (success rate, solved per agent hour, tests, manual interventions, regressions); hardware and profile always shown, conditions never mixed |

- The existing showcase stays as "round 0", the first evidence of Alia's work. Its data errors are fixed in a
  round.
- A clearly visible link block above the footer of the main page leads to `evolution/`. The showcase gets a link
  back to the main page.

**Data, without a backend.**
- Every round leaves a folder `evolution/rounds/NN-slug/` in the repo (outside `site/`, not deployed itself):

  | file | content |
  |---|---|
  | `task.md` | the task, exactly what Alia received |
  | `acceptance/` | the acceptance tests; frozen before the Alia run (sha in `round.json`) and given to Alia only after it |
  | `alia.stream.jsonl` | the Alia transcript, cleaned: home path -> `~`, temp dirs -> `<tmp>`; the CI personal-data grep covers it |
  | `alia.diff` | Alia's change |
  | `tests.txt` | output of the acceptance and site tests |
  | `reviews/*.md` | reviewer reports |
  | `round.json` | level; agent and profile; Alia version and commit; wall time, tokens, tool calls; tests passed / total; manual interventions (count and what); regressions; reviewer verdicts; final commits; status |

- `tools/evolution_data.py` (stdlib) builds `site/evolution/data/rounds.json`, `changelog.json` and
  `metrics.json` from the round folders, `CHANGELOG.md` and `profiles.json`.
- CI regenerates the data and fails when the committed JSON differs, so the site cannot show numbers that do
  not come from the repo.

**Proof of Alia's own work** (not Claude's review, but data):
- Alia's code goes into separate commits with the author `Alia (Qwen3.6-35B, local) <alia@users.noreply...>` and
  a trailer `Alia-Round: NN`. Fixes by others are separate commits with their own author.
- The site computes Alia's share from the diffs of the round commits.
- A round where Alia fails stays visible as failed. Nothing is "fixed up" afterwards and shown as Alia's work.

## 3. Self-evolution workflow (one round)

**PLAN -> IMPLEMENT -> TEST -> REVIEW -> COMPARE -> APPROVE**

1. **PLAN** (Claude):
   - Write a small task with a clear level.
   - Write the acceptance tests: Playwright (Python) for DOM, behaviour and i18n; the site checks.
   - Commit both in the round folder, freeze the sha.
   - The tests are not in Alia's worktree.
2. **IMPLEMENT** (Alia):
   - Run `alia` headless with the default profile (Qwen3.6-35B) in its own worktree `evo/NN-alia`, exactly with
     `task.md`.
   - 900 s wall, `-o stream-json`, under `flock ~/reel/gpu.lock`, outside the GAP window, no other local model
     run at the same time, exclusive mode.
   - Nobody intervenes during the run.
3. **TEST:**
   - The acceptance tests are copied in after the run, together with the site suite (links, assets, i18n key
     parity, axe a11y, contrast, tap targets, 390/1280 screenshots against a baseline).
   - The results go into `round.json`.
4. **REVIEW:** one external reviewer per round, chosen by the type of task (section 4), plus the Copilot PR bot.
   Reviewers report; they do not change Alia's commit.
5. **COMPARE:**
   - Against the baseline: the state before the round (site suite, screenshots, Lighthouse budget for size).
   - Over all rounds: success rate and solved per agent hour of Alia with a fixed profile and hardware.
   - A failed round counts.
6. **APPROVE:**
   - If needed, fixes by Claude or others in their own commits, marked as manual interventions.
   - Then a PR `evolution/NN` to `main`, CI green, and **Belkis merges**, which deploys.
   - No automatic push to `main`, no automatic deploy.

**Path guard:** a CI rule makes evolution PRs touch only `site/`, `evolution/`, `tools/evolution_data.py` and
the site tests. The Alia engine (`alia`, `profiles.json`, `i18n/`, `tests/test_alia.py`) stays untouched.

## 4. Roles and delegation plan

Delegation runs one task at a time (team rule): each in its own worktree with a fixed file fence, and only after
Belkis's release.

| agent | role | concrete first tasks | notes |
|---|---|---|---|
| Claude | lead, orchestration, verification | round folders, tasks, acceptance tests, round runner, integration, screenshots and axe after every merge | 28 % weekly quota left: keep it to orchestration |
| Alia | implementation of levels 1-3 (later 4-5) | the real defects from the audit as the first rounds (section 5) | default profile, isolated worktree, nobody fixes during the run |
| Codex (`gpt-5.6-sol`, medium) | infrastructure | R0.1 site test suite and CI job; R0.2 `tools/evolution_data.py` plus data check | not Alia's tasks, so the measurement stays clean |
| Cursor (`composer-2.5` only) | frontend | metrics dashboard components (SVG charts) once the data exist, if not given to Alia | own CSS file as fence |
| Grok (`grok-4.7`) | critical review | phase-A plan, round runner and data model (gaming the metric, leak risks) | no `spawn_subagent`, sequential |
| Antigravity (`gemini-3.8-flash-high`) | UX review | screenshots after each visible release, at most 10-15 per run | report only, no code |
| Copilot | PR review bot | every evolution PR automatically | Belkis enables it in the UI |

## 5. Prioritised backlog

**Round 0: infrastructure (not by Alia; a prerequisite, so Alia is measured fairly):**
- R0.1 Site test suite: link/asset check (stdlib), i18n key parity of the EN HTML vs the DE dictionary,
  Playwright (Python) smoke at 390/1280, axe-core, contrast and tap targets. Plus a CI job `site`. (Codex)
- R0.2 Round format, `round.json` schema, `tools/evolution_data.py`, CI data check, path guard. (Codex, Claude
  reviews)
- R0.3 Round runner `tools/alia_round.sh`: worktree, headless Alia run, transcript cleaning, freezing and later
  copying the acceptance tests, `round.json`. (Claude)

**Alia rounds, ordered by level.** The first ones are the real defects from the audit:

| # | level | task | why first |
|---|---|---|---|
| 1 | 1 | copy button must not cover code (all install steps, 390 and 1280 px) | a visible, real bug, one CSS file |
| 2 | 1 | split `q.json` into two keys (EN+DE), right label in both cards | real i18n bug, two files |
| 3 | 1 | link block above the main page's footer to `evolution/`, plus a link back from the showcase | Belkis's must-have, small |
| 4 | 1 | contrast `--mut2` to at least 4.5:1, tap targets at least 24 px | measurable a11y |
| 5 | 2 | `evolution/` overview page (static, EN/DE, site style) | first visible page |
| 6 | 2 | `CHANGELOG.md`: remove the duplicate block; changelog page from `changelog.json` | data plus component |
| 7 | 3 | "Built by Alia" list from `rounds.json` (cards, status, links) | heart of the project |
| 8 | 3 | metrics dashboard from `metrics.json` (SVG, no library) | real values only |
| 9 | 3 | interactive flow task -> ... -> result (keyboard accessible) | the "how it works" |
| 10 | 2 | update the showcase's data (version, profile values from `profiles.json`) | removes stale claims |
| 11 | 4 | site basics: favicon, og:image/url, canonical, 404, sitemap, robots; deduplicate fonts | quality |
| 12 | 4 | video weight (mobile video smaller, poster updated) | about 3.4 MB on mobile |
| 13 | 5 | round timeline with filter (level, status, agent) and tests | multi-file feature |

## 6. First visible version (v1)

| | Belkis's requirement | done by |
|---|---|---|
| 1 | Link from the main page | round 3 |
| 2 | Overview page | round 5 |
| 3 | Interactive architecture | round 9, plus the showcase as round 0 |
| 4 | "Built by Alia" | round 7 |
| 5 | Changelog | round 6 |
| 6 | Metrics dashboard | round 8 |

v1 means round 0 plus rounds 1-9. A round that Alia fails still counts and is shown; the feature is then built by
another agent in a marked round.

## 7. Effort (estimate, not measured)

- Round 0: about 1 day, Codex plus Claude review.
- One Alia round about 30-60 min:
  - the Alia run itself 2-10 min (measured times on similar tasks: 45-250 s);
  - test, review and PR as overhead;
  - GPU only between :06 and :30 because of the GAP job.
- v1 (9 rounds): about 3-5 days elapsed, depending on Belkis's merges and the agents' quotas (only Claude's is
  known, 28 %).

## 8. Risks and open questions

**Risks:**
- **Proof of own work:** "Alia did it" rests only on separate commits, transcripts and the frozen acceptance
  tests. Any manual fix is counted visibly.
- **Leak through transcripts:** paths, user names or tokens could reach public files. Cleaning plus the existing
  CI personal-data grep; a round with a hit is not published.
- **Site in the engine's repository:** the path guard in CI. Evolution PRs never touch the engine.
- **Measurement quality:** the rounds are a long-term record, not a benchmark like M1. Tasks are chosen by need,
  not at random, so solved per hour is descriptive here. M1 stays methodologically separate.
- **Quota:** Claude has 28 % of the week left. The other agents' quotas are unknown.
- **Public failure:** failed rounds stay visible. That is wanted, but it is visible.

**Open questions for Belkis:**
1. Name and URL: "Alia Self-Evolution" at `/alia/evolution/`?
2. Should the Alia transcripts be published in full (cleaned), or only summarised with a link to the repo?
3. Which profile for the rounds: the default Qwen3.6-35B (proposal), fixed for v1?
4. Approval per round (each PR) or per batch of rounds?
5. Release of round 0, with delegation to Codex (infrastructure) and Grok (plan review)?
