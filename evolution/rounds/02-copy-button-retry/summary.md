# Round 02: copy buttons, second try

**EN:** Passed. With the same task and frozen tests as the failed round 01, Alia changed two lines in
`site/style.css`: the copy button no longer floats over the code but sits in the normal flow below it, and the code
block no longer reserves space for the old overlay. The button covers no code on phones or desktops, in English or
German, also while scrolling, and still copies its block. Acceptance 3/3; the site suite has no new failures and
reports the 9 known overlaps as fixed. Wall time 235 s, 6 tool calls. All changed site lines are Alia's; Claude's
commits only set up the round and update the defect list. Open for a later round: the button touches the lower-left
corner of the block.

**DE:** Bestanden. Mit derselben Aufgabe und denselben eingefrorenen Tests wie in der gescheiterten Runde 01 änderte
Alia zwei Zeilen in `site/style.css`: Der Kopier-Button schwebt nicht mehr über dem Code, sondern steht im normalen
Fluss darunter, und der Codeblock reserviert keinen Platz mehr für das alte Overlay. Der Button verdeckt auf Handy
und Desktop, auf Englisch und Deutsch und auch beim Scrollen keinen Code und kopiert weiter seinen Block. Abnahme
3/3; die Website-Prüfung zeigt keine neuen Fehler und die 9 bekannten Überdeckungen als behoben. Laufzeit 235 s,
6 Tool-Calls. Alle geänderten Website-Zeilen stammen von Alia; Claudes Commits richten nur die Runde ein und
aktualisieren die Fehlerliste. Offen für eine spätere Runde: Der Button klebt an der unteren linken Ecke des Blocks.
