# Round 03: header of the architecture page

**EN:** Failed (attempt 2, the scored run). Alia was asked to tidy up the header of the architecture page it had
built: the current logo, one `<h1>`, a page description, larger navigation links and a compact phone header. It
added the description, but the logo path points to a file that does not exist, the logo became a link to an
invented domain (`alia-ai.dev`), and the navigation and phone layout stayed unchanged. The run ended when Qwen
Code's loop guard stopped a repeated tool call. The frozen acceptance tests caught it: 0 of 4 passed. Attribution
is verified (17 of 17 changed lines by Alia, no interventions). Nothing from this round is merged into the site.

**DE:** Gescheitert (Versuch 2, der gewertete Lauf). Alia sollte die Kopfzeile der Architektur-Seite aufräumen,
die sie selbst gebaut hatte: aktuelles Logo, eine `<h1>`, eine Seitenbeschreibung, größere Navigations-Links und
eine kompakte Handy-Kopfzeile. Die Beschreibung kam hinzu, aber der Logo-Pfad zeigt auf eine Datei, die es nicht
gibt, das Logo wurde zu einem Link auf eine erfundene Domain (`alia-ai.dev`), und Navigation und Handy-Layout
blieben unverändert. Der Lauf endete, als Qwen Codes Schleifenschutz einen wiederholten Werkzeugaufruf stoppte.
Die eingefrorenen Abnahmetests haben das erkannt: 0 von 4 bestanden. Die Urheberschaft ist verifiziert (17 von 17
geänderten Zeilen von Alia, keine Eingriffe). Nichts aus dieser Runde fließt in die Website.

## Attempt 1 (not scored) / Versuch 1 (nicht gewertet)

**EN:** Attempt 1 passed the first version of the tests (4/4): the dragon logo, one `<h1>`, a description and a
68 px phone header. On a phone, though, two of the four navigation links ran off the right edge and could not be
tapped. The header clips its overflow, so the page width stayed correct and the test missed it. That was a gap in
the test, so the attempt is not scored. The test now also requires every navigation link to be fully visible and
tappable; it fails on attempt 1 and passes on a reference fix, and it was re-frozen before attempt 2.

**DE:** Versuch 1 bestand die erste Fassung der Tests (4/4): Dragon-Logo, eine `<h1>`, eine Beschreibung und eine
68 px hohe Handy-Kopfzeile. Am Handy liefen aber zwei der vier Navigations-Links über den rechten Rand und waren
nicht antippbar. Die Kopfzeile schneidet Überstehendes ab, deshalb blieb die Seitenbreite korrekt und der Test
übersah es. Das war eine Lücke im Test, darum wird der Versuch nicht gewertet. Der Test verlangt jetzt zusätzlich,
dass jeder Navigations-Link vollständig sichtbar und antippbar ist; er scheitert an Versuch 1, besteht mit einer
Referenz-Korrektur und wurde vor Versuch 2 neu eingefroren.
