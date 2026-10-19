# Round 01: copy buttons

**EN:** Planned. Alia gets the task in `task.md` and must make the install section's copy buttons stop covering
code at 390 and 1280 px in English and German, without changing the commands. The acceptance tests were frozen
before the run.

**DE:** Geplant. Alia bekommt die Aufgabe aus `task.md` und muss dafür sorgen, dass die Kopier-Buttons im
Installationsbereich bei 390 und 1280 px auf Englisch und Deutsch keinen Code mehr verdecken, ohne die Befehle zu
ändern. Die Abnahmetests wurden vor dem Lauf eingefroren.

## Attempt 1 (not scored) / Versuch 1 (nicht gewertet)

**EN:** Alia's first run changed only `site/style.css`: the copy button became its own column beside the code
(Alia's commit `a3b3493`, kept as `refs/evolution/round-01-attempt1`). It was not scored for two reasons that were
not Alia's: the runner stopped because a stale ref from the dry run blocked storing Alia's commit, and review found
that the frozen acceptance test counted code text that is scrolled out of view (clipped, invisible) as covered,
which would have failed a correct layout. The test now only counts visible text; it still fails on the unfixed page
and passes on a reference fix. It was re-frozen before attempt 2, which is the scored run.

**DE:** Alias erster Lauf änderte nur `site/style.css`: Der Kopier-Button wurde eine eigene Spalte neben dem Code
(Alias Commit `a3b3493`, aufbewahrt als `refs/evolution/round-01-attempt1`). Er wurde aus zwei Gründen nicht
gewertet, die nicht bei Alia lagen: Der Runner brach ab, weil eine alte Referenz aus dem Probelauf das Speichern von
Alias Commit blockierte, und die Prüfung ergab, dass der eingefrorene Abnahmetest weggescrollten (abgeschnittenen,
unsichtbaren) Code als verdeckt zählte, was ein korrektes Layout durchfallen ließe. Der Test zählt jetzt nur
sichtbaren Text; auf der ungefixten Seite schlägt er weiter fehl, mit einer Referenz-Korrektur besteht er. Er wurde
vor Versuch 2, dem gewerteten Lauf, neu eingefroren.
