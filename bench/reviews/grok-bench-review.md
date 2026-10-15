# Review der lokalen LLM-Benchmarks

Stand der gelesenen Skripte: `bench.py` 2026-10-15 02:11, `bench_llamacpp.py` und `run10.sh` 02:13, `summarize.py` 01:56, `run11.sh` 02:25, `run12-final.sh` 02:29. Rohdaten unter `results/perf-*.jsonl`, `results/llamacpp-*.jsonl`, `results/quality-*.jsonl`. `results/invalid/` und `results/failed/` sind nicht eingegangen. `bench.py`, `bench_llamacpp.py`, `serve_quality.sh` und `run*.sh` wurden nicht ausgeführt, Ollama und llama-server nicht angesprochen.

Schwere: **hoch** = die Zahl oder der Pass/Fail ist in die falsche Richtung verzerrt oder ein ganzer Lauf verschwindet. **mittel** = die Zahl ist nur mit Zusatzwissen lesbar oder ein realistisches korrektes Verhalten fällt durch. **niedrig** = Latenz, Benennung, Randfall.

Nachrechnung und Unit-Tests stehen in den folgenden Abschnitten.

## Befunde Messung

### 1. p95 ist bei den verwendeten Stichproben das Maximum, und bei t/s die schnelle Seite — hoch

`bench.py:245-251`, ausgegeben in `summarize.py:7-10` und `:35-38`.

```python
p95 = xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))]
```

Für n = 1…11 ist der Index das letzte Element der sortierten Liste. Default `--reps 5`, llama.cpp `--reps 3`, `run11.sh:19` `--reps 1`. p95 ist damit der größte Messwert. Bei Durchsatz ist das der schnellste Lauf, bei TTFT der langsamste. Dieselbe Spaltenüberschrift „p95“ mischt beide Richtungen.

Belegt an `final-1-ub2048`, Tiefe 4096, `prompt_ms` = [10079, 2663, 2574] bei ~4058 Prompt-Tokens: ungefähr 403, 1524 und 1577 t/s. Gespeichert: Median 1522.7, p95 1584.9, σ 665. Der langsame erste Lauf (CUDA-Autotune direkt nach dem Start, kein verworfener Warmup) steckt in σ und fehlt in p95. Dieselbe Form bei `gemma4-26b-a4b` Tiefe 4096 (`prompt_ms` 6652 / 4141 / 4170, σ 211, p95 986 ≈ schnellster Lauf) und bei `final-2` (σ 607, p95 1622 bei Median 1280).

`statistics.stdev` ist die Stichproben-Standardabweichung (Teiler n−1). Bei n = 3 ist sie ein Ausreißer-Detektor, kein Stabilitätsmaß. `summarize.py` rundet PP-σ auf 0 Nachkommastellen: `kvq4` Tiefe 4096 hat σ 0.257 und erscheint als „σ 0“. TG von `qwen3.5:9b` bei 32k hat σ 0.05 und erscheint als „σ 0.0“. Die Tabelle zeigt n nicht.

Fix: Rohwerte je Rep speichern. In der Tabelle Median und min–max. p95 erst ab n ≥ 20, und für t/s das untere Ende (langsamer Lauf) ausweisen, wenn die Spalte wie eine Latenz-Tail gelesen werden soll. Einen ungewerteten Warmup-Rep vor der Serie verwerfen. σ unter der Anzeigeauflösung als „–“ drucken.

### 2. Abgestürzte llama-server-Läufe fehlen in der Zusammenfassung — hoch

`bench_llamacpp.py:164-165` schreibt bei Fehlern nur `{"model", "config", "error"}`, ohne `engine`. `summarize.py:18-19` nimmt in die llama.cpp-Tabelle nur Zeilen mit `engine == "llama-server"`. Der Fehlerzweig `summarize.py:73-75` ist damit tot. `summarize.py` auf allen vollständig geparsten Zeilen enthält das Wort „Fehler“ null Mal und weder `fa_off` noch die Kontext-OOMs.

Betroffene Records und Logzeilen:

| Datei | Config | Log |
|---|---|---|
| `llamacpp-20261015-021754.jsonl` | `fa_off` | `n_gpu_layers already set by user to 99, abort`, danach cudaMalloc 1157 MiB OOM (Compute-Buffer) |
| `llamacpp-20261015-022343.jsonl` | `mtp` | `context type MTP requested but model doesn't contain MTP layers` |
| `llamacpp-20261015-022433.jsonl` | `qwen9b-ctx128k` / `base` | KV-Cache 2176 MiB, OOM, Fit abgebrochen weil `-ngl 99` |
| `llamacpp-20261015-022437.jsonl` | `qwen9b-ctx192k` / `kvq4` und `base` | dasselbe, 3264 MiB bzw. Compute-Buffer |

Wer nur die Markdown-Tabelle liest, sieht diese Configs nicht als gescheitert, sondern als nie gelaufen. `run8.sh:6-9` läuft mit `set -u` ohne `set -e` weiter und druckt am Ende `RUN8 DONE`.

Fix: Fehler-Record mit `engine`, `args`, den letzten Logzeilen. `summarize.py` über `error` einsortieren, nicht über `engine`.

### 3. `fa_off` ist kein Flash-Attention-Vergleich, und `-ngl 99` verhindert `--fit` — hoch

`bench_llamacpp.py:41` setzt in `BASE` immer `-ngl 99`. `CONFIGS["fa_off"]` (`:48`) hängt `-fa off` **und** `-ctk f16 -ctv f16` an. Gegen `base` (KV q8_0, FA an) ändern sich zwei Dinge. Der passende Vergleichspartner ist `kvf16`, und der ist auf dieser Karte auch der einzige, der lud: VRAM-Peak 6954 MiB. `fa_off` braucht ohne FA einen größeren Compute-Buffer und läuft mit erzwungenen 99 GPU-Layern in den OOM oben.

Dieselbe `-ngl 99`-Zeile erklärt die Kontextläufe in `run8.sh:8-9`. Das Log sagt wörtlich, dass Fit abbricht, weil der User `n_gpu_layers` gesetzt hat. Ein 128k-/192k-Lauf, der mit CPU-Offload vielleicht läuft, wird als OOM gemessen und dann (Befund 2) verworfen. `run11.sh:19` macht den langen Kontext richtigerweise mit `configs fit` (kein `-ngl`), aber mit `--reps 1`: Median = p95 = der einzige Wert, σ = 0.

Fix: `fa_off` nur `-fa off` auf derselben KV-Quantisierung wie die Vergleichszeile, oder die Zeile `fa_off_vs_kvf16` nennen. Für „passt der Kontext auf die Karte“ `fit` ohne `-ngl`. Für „alles auf der GPU“ `-ngl 99` lassen und OOM als Ergebniszeile behalten.

### 4. VRAM und RSS hängen nicht an der gemessenen Tiefe und nicht an der eigenen PID — hoch für VRAM, mittel für RSS

`bench_llamacpp.py:114` setzt `-c` auf `max(depths) + n_predict + 512`. Beide Tiefen eines Laufs teilen sich diesen Cache. Belegt: `qwen3.6-35b-a3b` fit 6768 MiB bei Tiefe 4096 und bei 32768; `final-1-ub2048` 6741 und 6742 MiB bei `ctx=33792`. Die Spalte „VRAM peak“ darf nicht als Kurve über die Kontexttiefe gelesen werden. Der Ollama-Pfad (`bench.py:265`, `unload_all` pro Tiefe, `num_ctx = depth + n_predict + 512`) macht das richtig und zeigt den Anstieg, z. B. `qwen3.5:9b-text` 5962 → 6566 MiB.

`Sampler` (`bench.py:96-106`, `:145-160`) summiert RSS jeder Prozess-Cmdline, die `llama-server` oder `ollama`+`runner` enthält, und `nvidia-smi memory.used` ist die ganze Karte (`:175`, `:185-188`). Ein zweiter llama-server auf einem anderen Port, ein `tail` auf ein Log mit `llama-server` im Pfad, oder der Desktop (Basis in den llama.cpp-Records konstant 722 MiB) steckt im Peak. `summarize.py` druckt den Absolutwert, nicht Peak minus `vram_base_mib`. `gemma4:e4b-it-qat` RSS 3766 MiB bei 4k und 2401 MiB bei 8k ist mit einem an die PID gebundenen Zähler nicht erklärbar.

Der Port-Check (`bench_llamacpp.py:81-88`, `:125-126`, `serve_quality.sh:12-14`) verhindert, dass ein Waisenprozess auf 8099 die Tokens liefert. Er verhindert nicht, dass ein Prozess auf einem anderen Port VRAM und RSS mitmisst.

Fix: `-c` pro Tiefe neu starten, wenn VRAM-gegen-Tiefe die Frage ist. Peak als Delta zur Basis ausweisen. RSS nur für `proc.pid` und dessen Kinder.

### 5. Prompt-Länge, Cache und die Spalte „Tiefe“ — mittel

`bench_llamacpp.py:151-157` speichert `timings.prompt_n` als `prompt_tokens`. In llama.cpp (`tools/server/server-common.cpp`) ist `prompt_n` die **neu gerechnete** Tokenzahl, `cache_n` die getroffene. `cache_n` wird verworfen. `summarize.py:78` druckt `prompt_tokens` unter der Überschrift „Tiefe“. Bei `cache_prompt=false` liegt der Wert nah an der Zieltiefe (in den Daten 0.94–1.015). Im `--cache-test`-Pfad (`bench_llamacpp.py:144-149`) ist der zweite Request nur der Suffix; die Tabelle zeigt dann eine kleine „Tiefe“ und eine PP-Rate für ein paar Tokens.

Ollama-seitig ist der alte Prefix-Cache-Bug entschärft: Nonce plus `filler()` mit neuem `random.Random()` pro Aufruf (`bench.py:205-217`), Warnung bei `prompt_eval_count < 0.9 * depth` (`:286-289`). In den perf-Records ist `suspect_cache` überall false. Die Kalibrierung `chars * 0.98` ist keine Obergrenze. `qwen3.5:4b-mtp-q4_K_M` bei Ziel 32768 hat Median 33186 Tokens, `num_ctx` 33408, Rest 222 Tokens bei `n_predict` 128. Ein etwas dichterer Tokenizer schiebt den Prompt über `num_ctx`. Aktuelles llama.cpp antwortet dann mit `exceed_context_size` (kein stilles Halbieren mehr); ein älterer Ollama-Runner verschiebt den Kontext und halbiert den Prompt. Die Warnung fängt nur den Fall `< 90 %` ab, nicht den Überlauf.

`granite4.2:8b` landet bei 31305 von 32768 (0.955), `ornith-1.5:9b-text-agent32k` bei 30969 (0.945). Die Spalte Prompt-Tokens zeigt das. PP-Vergleiche auf dem Label „32768“ sind dann ein paar Prozent Kontext kürzer.

Fix: `cache_n`, `prompt_n` und die Ziel-Tiefe getrennt speichern. Kalibrierung so wählen, dass Prompt + `n_predict` unter `num_ctx` bleibt (nach dem Lauf prüfen, nicht nur 90 %). Cache-Test als eigene Tabelle mit Trefferquote `cache_n / (cache_n + prompt_n)`.

### 6. TG mischt kurze und lange Generierungen; die beiden Engines zählen den ersten Token verschieden — mittel / niedrig

`ornith-1.5:9b-agent32k` `gen_tokens` [128, 128, 72], `ornith-1.5:9b-text-agent32k` [128, 42, 41] (`perf-20261015-004430.jsonl`, n = 3). Der TG-Median mischt Läufe, die am EOS stoppen, mit Läufen über volle 128 Tokens. `summarize.py` zeigt die Längen nicht. Alle anderen perf-Tiefen haben fünfmal 128.

llama-server `predicted_per_second` teilt `(n_gen - 1) / t_gen` (`server-common.h`, erster Token kommt aus dem Prompt-Batch). `bench.py:241` teilt `eval_count / eval_duration`. Bei 128 Tokens sind das etwa 0,8 %, bei 512 etwa 0,2 %. Für den Vergleich Ollama-Tabelle gegen llama.cpp-Tabelle ist das ein kleiner systematischer Versatz, kein Erklärer für große Lücken.

Zusätzlich ist TG über Läufe hinweg nicht gepaart: `run7` nutzt die Default-Aufgabe `summary` und `n_predict` 128, `run12-final.sh:8` setzt `--task code --n-predict 512`. Speculative Decoding hängt am erzeugten Text, und der Filler ist jedes Rep anders. Innerhalb von run12 ist der Aufgaben-Typ gleich; gegen run7 nicht.

Fix: TG nur über Läufe mit `gen_tokens` in einem festen Fenster mitteln, Längen in die Tabelle. Dieselbe `n_predict` und dieselbe Aufgabe, wenn Configs verglichen werden.

### 7. Weitere Messpunkte — niedrig bis mittel

- **Erster Kaltstart ist der richtige, die Tabelle sagt nicht, dass es der erste von mehreren ist.** `summarize.py:22` behält pro Modell den ersten `phase=cold`. `gemma4:e4b-it-qat` load_s = 10.20, 11.38, 3.40, 3.01 über die vier Kontextgrößen; die Tabelle zeigt 10.2 s. Die späteren „cold“-Records sind Reloads mit warmem Page-Cache. Das steht im Kommentar von `bench.py:14-16`, nicht in der Tabelle.
- **`phi4-mini`:** alle vier perf-Tiefen haben `resident: {}`. `resident()` (`bench.py:80-84`) vergleicht exakt `name` oder `name:latest`. GPU-Anteil wird „–“, nvidia-smi zeigt 3756 → 5714 MiB und die t/s sind da. Der Namensvergleich verfehlt jeden anderen Tag.
- **Dauer 0 bzw. fehlend** (`bench.py:237-241`): fehlende `prompt_eval_duration` wird als 1 Nanosekunde gelesen (absurd hohe t/s), echte 0 wirft `ZeroDivisionError` und bricht die Serie ab, bevor `suspect_cache` laufen kann.
- **`nvme_read_mb`** (`bench.py:123-124`) teilt durch 2^20, die Einheit ist MiB. Der Zähler ist systemweit, nicht der Prozess. `runner_majflt` ist korrekt Feld 12 von `/proc/pid/stat` (Index 9 nach der comm-Klammer); der Kommentar `:165` sagt schon, dass ein im Fenster startender Runner zu niedrig zählt.
- **Doppelte Flags.** Die args von `final-1-ub2048` enthalten `-b 512 -ub 512` aus `BASE` und danach `-b 2048 -ub 2048` aus `--extra`. Der aktuelle Parser setzt den Wert bei jedem Auftreten neu, der letzte gewinnt. Ein First-wins-Binary würde still -ub 512 messen. `run11.sh:11-16` und `run12-final.sh:9-11` sind zusätzlich kumulativ (jede Zeile enthält die vorigen Änderungen). Der Kommentar sagt das. Ein Vergleich von Schritt E gegen Schritt A ist kein Ein-Faktor-Versuch.
- **Docstring** `bench.py:19` sagt, Thinking sei für quality aus. `--think` schaltet es an.
- **„Reproducible“** (`bench.py:2`) gilt für `seed=42` und `temperature=0`, nicht für Nonce und Filler (`random.Random()` ohne Seed).

`qwen3.5:9b` gegen `qwen3.5:9b-text` ist in den Zahlen ehrlich, in der Lesart leicht schief. Bei 4k: size 6.187e9 / size_vram 5.410e9 (Anteil 0.874) gegen text 5.281e9 voll auf der GPU. Das Modelfile `modelfiles/qwen3.5-9b-text.Modelfile` dokumentiert den 0.92-GB-Projektor. Die Text-Variante bleibt bei 32k bei TG 56 t/s und 100 % GPU, die Vision-Variante fällt auf TG 20 t/s und Anteil 0.776, weil der KV-Cache in den RAM wandert (`size` steigt, `size_vram` bleibt ~5.38e9). Die Spalte GPU-Anteil zeigt das. `ornith-1.5:9b-agent32k` hat bei 32k dieselben size/size_vram-Bytes wie `qwen3.5:9b` (6938123299 / 5383085095), die Text-Variante dieselben wie `qwen3.5:9b-text`. Dieselben Gewichte, anderer Chat-Zusatz.

Das Qwen-Text-Modelfile setzt `TEMPLATE {{ .Prompt }}`. Damit fällt beim Chat der System-Prompt weg, den die anderen Modelle bekommen. Orniths Modelfile sagt im SYSTEM-Text „Think step by step“, während der Bench `think=false` setzt. Beides sind Vergleichsverzerrungen außerhalb der Py-Dateien, sie hängen an den Modellen, die `run2.sh` in eine Tabelle legt.

## Befunde Qualität

### 8. JSON ohne Schema scheitert an Markdown-Fences, der Name-Check ist ein Teilstring — hoch

`bench.py:574-586` macht `json.loads` auf `message.content`. Die Prompt-Variante bittet um „nur das JSON-Objekt, ohne Codeblock“ (`:570`), entfernt einen Fence aber nicht. Ein korrektes Objekt in ` ```json ` wirft beim Parsen und zählt als Fail (`valid=False`).

Belegt, `quality-20261015-014932.jsonl`, ministral3-14b, alle drei `json_prompt`-Fälle, `valid=False`, Rohtext beginnt mit `` ```json `` und enthält `Bäckerei Krause` / `88231`, `ACME GmbH` / `1002`, `Özdemir & Söhne` / `77`. Die Schema-Variante desselben Modells ist 3/3. Die Spalte „JSON nur Prompt“ ist für dieses Modell ein Fence-Zähler. Dieselbe Form bei phi4-mini, drei `json_prompt`-Fails, Rohtext beginnt mit `` ```json ``.

Der Name-Check (`bench.py:528-529`, `:582-583`):

```python
norm(exp) in norm(got) or norm(got) in norm(exp)
```

`norm` lässt Buchstaben, Ziffern und `&` stehen. Jeder nichtleere Teilstring des Soll-Namens besteht: für „Bäckerei Krause“ bestehen `a`, `e`, `Krause`, `Bäckerei`. Vertauschte volle Tokens bestehen nicht. phi4-mini Schema-Fall 1 ist `valid=True` und `pass=False` mit `"kunde": "Krause Bäckerei"` bei sonst passender Struktur im angeschnittenen Rohtext. Zu locker in der einen Richtung, zu streng in der anderen.

Fix: Fences und ein optionales `<think>…</think>` vor `json.loads` abstreifen. Namen als Token-Menge vergleichen (oder eine normalisierte Gleichheit), mit einer Mindestlänge.

### 9. Code-Extraktion nimmt den längsten Fence und ignoriert die Sprache — hoch

`bench.py:465-467`. `lang` wird nicht benutzt. Der Regex verlangt eine Sprache aus `[A-Za-z0-9+]*` und danach sofort `\n`. Gewonnen hat der längste Block.

Konkrete Fälle, am Regex nachgestellt:

- Lösung in einem kurzen `python`-Block, Erklärung im längeren `text`-Block: die Erklärung wird kompiliert.
- Thinking-Kanal im Content mit einem langen Scratch-Block und einem kurzen korrekten Block: der Scratch-Block gewinnt.
- ` ```python def f(): ` ohne Zeilenumbruch nach dem Tag: kein Treffer, der ganze Text inklusive Fences wird ausgeführt.
- Ein C++-Block verliert gegen einen längeren `md`-Block.

Der OpenAI-Pfad (`bench.py:492-514`) liest nur `content`. `reasoning_content` und `message.thinking` werden verworfen, `<think>` im Content nicht entfernt. Für Code-Aufgaben wird der Modelltext nicht geloggt, nur die letzten 400 Zeichen stderr (`:489`, `:548`). Ein Extraktionsfehler ist an den Records nicht mehr von einem echten Compile-Fehler zu unterscheiden. JSON loggt `raw` (500 Zeichen), Code nicht.

Fix: den ersten Fence der erwarteten Sprache nehmen, sonst den ersten beliebigen. Thinking-Tags vorher ausschneiden. Den extrahierten Quelltext ins jsonl schreiben.

### 10. Der Harness führt den Modelltext als Programm aus, inklusive Top-Level und `eval` — hoch

`bench.py:477-489` hängt die Tests hinter den Modelltext und startet `python3 t.py` bzw. `g++` und `./t`. Timeout fängt nur `subprocess.TimeoutExpired` (`:470-474`). `FileNotFoundError` (kein `g++`) bricht die restliche Suite ab.

Nachgestellt unter `/tmp/grok-bench-review/`:

- Korrekte `merge_intervals` plus `sys.exit(0)` auf Top-Level: Exit 0, die Asserts laufen nie. **Falscher Pass.**
- Dieselbe Funktion plus ein falsches Demo-`assert`: Exit 1. **Falscher Fail.** phi4-minis `calc`-Stderr zeigt `print(calc("3 + 5"))` im Traceback, das Demo ist also mitgelaufen.
- `RingBuffer` mit eigenem `main`: `g++` meldet `redefinition of ‘int main()’`. Ein korrektes Template mit dem üblichen Demo-`main` fällt durch, obwohl der Prompt „no main()“ sagt. `#define main student_main` um den Modelltext herum kompiliert und besteht den Test.
- `calc` per `eval(expr, {"__builtins__": {}}, {})` besteht alle sieben Asserts, inklusive `2*-(1+1) == -4` und `8/4/2 == 1`. Der Prompt verbietet `eval`/`exec`/`ast` (`bench.py:347`). Der Harness prüft den Quelltext nicht.

Fix: per AST nur Imports, Funktions- und Klassendefinitionen ausführen. `eval`/`exec`/`compile` im Quelltext als Fail werten (umgehbar, aber der Einzeiler fällt). Beim C++-Text `#define main student_main` vor dem Modelltext und `#undef` davor vor dem Test-`main`.

### 11. Thinking-Budget schneidet die Antwort ab — hoch

`bench.py:42` und `:521-522`: mit `--think` ist `num_predict` bzw. `max_tokens` 12288, `num_ctx` bleibt 16384 (`:517`). `serve_quality.sh:17` startet llama-server mit `-c 16384`.

`quality-20261015-015119.jsonl`, `qwen3.5:9b-text`, Aufgabe `cpp_ringbuf`: `gen_tokens` = 12288, also exakt das Limit. Der Compilerfehler liegt in Zeile 5 der Testdatei (`‘r’ was not declared`), und `#include <cassert>` kommt aus Zeile 3. Vor dem Harness stehen damit etwa zwei Zeilen Modelltext. Der Rest der 12288 Tokens ist Thinking und wird nicht benotet (`extract_code` sieht nur `content`). Die Aufgabe gilt als nicht bestanden, weil das Budget leer war.

`qwen3.6-35b-a3b-think` (`quality-20261015-020353.jsonl`) hat bei `toposort` einen `NameError` in Zeile 3 der Testdatei: im benoteten Text gibt es die Funktion nicht. `gen_tokens` ist auf dem OpenAI-Pfad immer `null`, weil `chat_openai` `eval_count` nicht zurückgibt. Ob das Budget voll war, steht im Record nicht. `wall_s` fehlt in den älteren Quality-Dateien; der aktuelle `bench.py:545-549` schreibt es.

Fix: `num_ctx` mindestens Prompt + Thinking-Budget + Antwort. Getrennte Zähler für Thinking- und Antwort-Tokens. Ein Lauf, der das Limit trifft, als `truncated` markieren und nicht als falsche Lösung zählen. Content und Thinking ins jsonl.

### 12. Tool-Calls: genau einer, Argumente müssen schon ein Dict sein — mittel

`bench.py:554-561`. `len(calls) == 1` und exakter Funktionsname. `check()` bekommt `arguments` ungeprüft. Der OpenAI-Pfad parst JSON-Strings (`:508-512`), der Ollama-Pfad nicht. Ein String wirft in `a.get(...)`, die `except`-Klausel macht daraus einen Fail.

Belegt, kein String-Fall, aber der Fan-out: `ornith-1.5:9b-text-agent32k` und `qwen3.5:4b` beantworten „Check stock for SKU X9“ mit drei `get_stock`-Calls, `sku=X9`, Warehouse `berlin` / `hamburg` / `muenchen`. Jeder einzelne Call erfüllt den Checker. Die Länge 3 kippt den Fall. Das Warehouse ist im Prompt nicht genannt und im Schema optional. Drei Lager abzufragen ist eine zulässige Lesart.

`int(a.get("customer_id"))` akzeptiert den String `"4711"` und `4711.0`. `"parse_order" in pattern` akzeptiert `parse_orders`. Beides lässt zu viel durch, Schwere niedrig.

Fix: bestehen, wenn mindestens ein Call Name und Argumente trifft und kein Call ein anderes Tool ist. Argumente auf beiden Pfaden `json.loads`, wenn sie ein String sind.

### 13. `--tasks` schreibt in einer älteren Datei 0/8, und summarize hängt an `/10` — mittel

Aktueller `bench.py:589-593` schreibt bei gesetztem `TASKS` für Tool und JSON „–“. `quality-20261015-015119.jsonl` (Datei 02:01, `bench.py` danach 02:11 geändert) hat bei `--tasks calc,toposort,min_window,csv_total,cpp_ringbuf` trotzdem `tool=0/8`, `json_schema=0/3`, `json_prompt=0/3`, und es gibt keine Tool-/JSON-Zeilen. Das liest sich als „alles falsch“ und ist „nicht gelaufen“. Code-Zähler 2/5 und 3/5 stimmen mit den `pass`-Zeilen.

`summarize.py:64-65` ersetzt Tool und JSON durch „–“, wenn `code` nicht auf `/10` endet. Heute sind es 10 Aufgaben (`merge_intervals`, `lru`, `calc`, `toposort`, `min_window`, `fix_bug`, `dijkstra`, `csv_total`, `cpp_rle`, `cpp_ringbuf`), deshalb sieht die Markdown-Zeile richtig aus. Eine elfte Aufgabe würde echte Tool-Scores ausblenden. Ein `--tasks` mit allen zehn Namen würde in der alten Schreibweise 0/8 anzeigen, weil der String auf `/10` endet.

`serve_quality.sh:21-24` wartet ohne Frist auf `/health`. Ein hängender Prozess, der nicht stirbt, blockiert die Lock-Kette. `run7.sh`, `run8.sh`, `run9.sh`, `run11.sh`, `run12-final.sh` haben `set -u` und kein `set -e`.

Fix: den Summary-String aus den wirklich gelaufenen Fällen bauen. In `summarize.py` das Feld `tool == "–"` auswerten, nicht die Endung `/10`. In `serve_quality.sh` eine Frist um die Health-Schleife.

### 14. Unit-Tests, die eine falsche Lösung durchlassen oder eine wortgetreue Lösung kippen — mittel

Die Referenzlösungen (Abschnitt Unit-Tests) bestehen alle zehn Aufgaben. Diese drei Tests tun etwas anderes, als der Prompt sagt:

- **`lru`** (`bench.py:339-344`). Der Prompt sagt, `put` auf einem vorhandenen Key mache den Eintrag zum zuletzt benutzten. Über `get` steht das nicht. Eine `LRUCache`, deren `get` die Reihenfolge nicht anfasst, fällt bei `c.get(2)==-1` durch: nach `put(1)`, `put(2)`, `get(1)`, `put(3)` fliegt 1 hinaus, 2 bleibt. Die LeetCode-Semantik (get zählt als Benutzung) besteht. Fix: im Prompt „get und put zählen beide als Benutzung“.
- **`calc`** (`bench.py:345-349`). Der Prompt nennt `+ - * /`, Klammern, unäres Minus, Leerzeichen, Rückgabetyp float. Dezimalzahlen stehen nur im Assert `1.5 * 2`. Ein Parser nur für ganze Zahlen wirft dort. Die anderen sechs Asserts treffen Python-Arithmetik (Präzedenz, linksassoziativ, unäres Minus nach `*`). Fix: „Dezimalzahlen mit Punkt“ in den Prompt.
- **`csv_total`** (`bench.py:378-383`). `1.234,50` + `0,5` = 1235.00 und `"Schmidt"` = 10.00 sind als deutsche Schreibweise richtig (nachgerechnet). Der Prompt sagt „German decimal comma“, nicht dass der Punkt ein Tausendertrenner ist. Ein Parser, der nur das Komma umsetzt, wirft auf `1.234,50`. Fix: ein Beispiel `1.234,50` → `1234.50` in den Prompt.
- **`toposort`** (`bench.py:350-357`). `sorted(alle Knoten)` plus `ValueError` auf dem Zwei-Zyklus `a↔b` besteht alle vier Asserts. Die lexikographisch kleinste Ordnung von `{b: ['c'], a: []}` ist `['a','c','b']`, die alphabetische Liste ist `['a','b','c']`. Diesen Graphen gibt es im Test nicht. Eine korrekte Kahn-Variante mit Min-Heap besteht die vorhandenen Asserts ebenfalls. Fix: den Graphen `{b:['c'], a:[]}` mit Erwartung `['a','c','b']` aufnehmen.
- **`dijkstra`** (`bench.py:373-377`) ist arithmetisch richtig (`[0, 3, 1]`, `inf` für den unerreichbaren Knoten). Dieselbe Distanzliste liefert auch eine ungerichtete Lesart, weil keine Rückkante fehlt, die eine Abkürzung wäre. Schwere niedrig. `float`-Distanzen bestehen gegen die int-Liste, weil `0.0 == 0`.

`min_window('xyzabcxbca','abc')=='abc'` ist das linke der beiden Fenster der Länge 3 (`abc` bei Index 3, `bca` bei Index 7). `merge_intervals` inklusive berührender Intervalle, `bsearch` (exklusives `hi`), `cpp_rle` (`12` z → `12z`) und `cpp_ringbuf` (push 1,2,3 bei Kapazität 2 → pop 2, dann 3, dann `std::out_of_range`) treffen die Spezifikation. Nachgestellt mit `python3` und `g++ -std=c++17 -O1`.

## Nachrechnung

Skript: `/tmp/grok-bench-review/recompute.py` (stdlib). Gegengeprüft mit `python3 summarize.py` auf jeder vollständig geparsten Zeile. Während des Reviews lief `run12-final.sh` weiter. `final-4-mtp2-nocache` steht nicht in `run12-final.sh` und hatte zum Lesen nur die Tiefe 4096 (`prompt_ms` 10979 / 2847 / 3724, Draft 75 %). `quality-20261015-022801.jsonl` (gemma4-26b über llama-server) hatte noch keinen Summary-Record. Beide fehlen deshalb in der Tabelle unten bzw. sind nur als eine Zeile sichtbar, wenn die Datei schon eine volle JSON-Zeile hatte.

### Perf

Die perf-jsonl speichert pro Tiefe nur das Aggregat (`median`, `p95`, `stdev`, `n`), nicht die fünf bzw. drei Einzel-t/s. Ein Median lässt sich daraus nicht neu aus den Rohläufen rechnen. Geprüft auf allen 34 `phase=depth`-Zeilen in `perf-20261015-001001.jsonl` (32) und `perf-20261015-004430.jsonl` (2):

- `p95 >= median` überall, `n` ist 5 bzw. 3. Das folgt aus der Formel in Befund 1, es ist kein zweiter Rechenweg.
- `summarize.py` rundet die gespeicherten Floats. Stichprobe `qwen3.5:9b-text`, Tiefe 4096: gespeichert PP 2494.8 / p95 2499.8 / σ 12.7, TG 64.54 / 64.74 / 0.24. Die Tabelle druckt `2495 (p95 2500, σ 13)` und `64.5 (p95 64.7, σ 0.2)`. Dieselbe Rundung auf den übrigen 33 Zeilen, keine abweichende Zelle.
- `suspect_cache` ist auf allen 34 Zeilen false. Prompt-Tokens / Ziel zwischen 0.944 (`ornith-1.5:9b-agent32k`, 30923/32768) und 1.013 (`qwen3.5:4b-mtp`, 33186/32768).
- `gen_tokens` ist 32-mal `[128,128,128,128,128]`, einmal `[128,128,72]`, einmal `[128,42,41]`.

Die Kaltstart-Tabelle zeigt nur den ersten Load. Abweichung zur Datei, nicht zur Rundung: `gemma4:e4b-it-qat` steht mit 10.2 s / TTFT 10.36 s da; die drei späteren Reloads sind 11.38 / 3.40 / 3.01 s. `phi4-mini` erster TTFT 10.04 s bei `load_s` 5.40 s; die Reloads liegen bei ~2.1 s. Basis-VRAM in allen Cold-Records 722 MiB.

### llama.cpp

Wo `prompt_ms` gespeichert ist, Rückrechnung `prompt_tokens / (ms/1000)` mit dem **Median** der Tokenzahl (die Einzel-`prompt_n` fehlen). Abweichung zum gespeicherten PP-Median unter etwa 1 %, erklärbar durch Tokenzahl-Streuung pro Rep und durch `round` auf ganze Millisekunden (`bench_llamacpp.py:155`). Kein Fall, in dem Median oder p95 einer anderen Formel folgen als `stats()`.

Draft-Rate selbst gerechnet als Summe `draft_n_accepted` / Summe `draft_n`:

| Lauf | Tiefe (prompt_n) | Brüche | Rate | summarize |
|---|---:|---|---:|---|
| final-3 fit_mtp | 4096 | (304+305+311) / (414+411+399) = 920/1224 | 75.16 % | 75 % |
| final-3 fit_mtp | 32837 | (314+315+309) / (392+391+402) = 938/1185 | 79.16 % | 79 % |
| final-4 fit_mtp | 4069 | eine Tiefe, Rate 0.752 | 75.2 % | 75 % |

Alle übrigen llama.cpp-Zeilen haben `draft = [[None, None], …]`, die Tabelle druckt „–“. Das stimmt.

Nicht in der Tabelle, obwohl die Zeilen in den Dateien stehen: `fa_off`, `mtp` (4b, „model doesn't contain MTP layers“), `qwen9b-ctx128k/base`, `qwen9b-ctx192k/kvq4`, `qwen9b-ctx192k/base`. Alle `error` ohne `engine`. `summarize.py` auf diesem Satz enthält „Fehler“ null Mal.

Die Spalte „Tiefe“ ist `prompt_tokens`, nicht das angeforderte `depth`. Beispiel gemma4-26b: angefordert 32768, angezeigt 32765. Bei den fit-Läufen von Qwen3.6 ist der Abstand größer (4041 statt 4096, 32654 statt 32768), weil der Tokenizer den 0.98-Filler so trifft.

### Quality

Pass-Zähler neu aus den `kind=code|tool|json_*`-Zeilen mit `pass=true`, gegen `kind=summary`.

| Modell | neu gezählt | Summary-Record | summarize.py |
|---|---|---|---|
| qwen3.5:9b-text | 8/10, 8/8, 3/3, 3/3 | gleich | gleich |
| ornith-1.5:9b-text-agent32k | 4/10, 6/8, 3/3, 3/3 | gleich | gleich |
| qwen3.5:4b | 5/10, 7/8, 3/3, 3/3 | gleich (`…011043`) | gleich |
| gemma4:e4b-it-qat | 8/10, 7/8, 3/3, 3/3 | gleich | gleich |
| gemma4:12b-it-qat | 9/10, 8/8, 3/3, 3/3 | gleich | gleich |
| granite4.2:8b | 4/10, 8/8, 3/3, 3/3 | gleich | gleich |
| phi4-mini | 5/10, 3/8, 2/3, 0/3 | gleich | gleich |
| qwen3:8b | 6/10, 8/8, 3/3, 3/3 | gleich | gleich |
| qwen3.6-35b-a3b | 9/10, 7/8, 3/3, 3/3 | gleich | gleich |
| ministral3-14b | 7/10, 8/8, 3/3, 0/3 | gleich | gleich |
| qwen3.5:9b-text thinking | Code 2/5, Tool-Zeilen 0, JSON-Zeilen 0 | Record sagt `tool=0/8`, `json_schema=0/3`, `json_prompt=0/3` | druckt „–“ wegen `/5` |
| ornith thinking | Code 3/5, sonst 0 Zeilen | ebenfalls `0/8`, `0/3`, `0/3` | „–“ |
| qwen3.6-35b-a3b-think | Code 3/5, keine Tool-/JSON-Zeilen | Record sagt schon „–“ | „–“ |

Die einzige inhaltliche Abweichung zwischen Zählung und Summary-Record ist `quality-20261015-015119.jsonl`: der Record behauptet gelaufene und voll verlorene Tool-/JSON-Suiten, die Datei enthält diese Zeilen nicht. `summarize.py` verdeckt das über die `/10`-Regel.

Dateien ohne Summary, von `summarize.py` ausgelassen:

- `quality-20261015-005434.jsonl`: `qwen3.5:9b-text` 2 Code-Zeilen, beide pass, Abbruch vor dem Summary (`--think` ohne `--tasks`).
- `quality-20261015-005015.jsonl`: zusätzlich zu den zwei Summaries oben vier Code-Zeilen für `qwen3.5:4b` (2 pass / 2 fail) ohne Summary. Der vollständige Lauf liegt in `…011043` (5/10). Wer `pass`-Zeilen über Dateien summiert, zählt diese vier doppelt.
- `quality-20261015-022801.jsonl`: zum Lesen ohne Summary.

## Unit-Tests, ausgeführt

Referenz in `/tmp/grok-bench-review/refs.py`, Harness-Asserts 1:1 aus `bench.py`. `python3 run_refs.py` und `g++ -std=c++17 -O1`.

| Aufgabe | Referenz | Ergebnis |
|---|---|---|
| merge_intervals | sortieren, überlappend und berührend (`s <= end`) mergen | pass |
| lru | OrderedDict, get und put schieben nach hinten | pass |
| lru, get ändert die Reihenfolge nicht | wortgetreu zum Prompt | fail bei `c.get(2)==-1` |
| calc | rekursiver Abstieg, unäres Minus, linksassoziativ | pass, alle 7 Asserts |
| calc via `eval` | vom Prompt verboten | pass, alle 7 Asserts |
| calc ohne Dezimalpunkt | Prompt nennt keinen Punkt | `ValueError` auf `1.5 * 2` |
| toposort | Kahn mit Min-Heap | pass |
| toposort als `sorted(Knoten)` plus ValueError auf a↔b | kein Toposort | pass auf den vorhandenen Asserts; auf `{b:['c'], a:[]}` liefert die Referenz `['a','c','b']`, die Sortierung `['a','b','c']` |
| min_window | Sliding Window, bei gleicher Länge das linke | pass, `BANC`, `''`, `aa`, `abc` |
| bsearch | `hi` exklusiv, `lo = mid+1`, `hi = mid` | pass, sechs Asserts |
| dijkstra | Distanz `[0.0, 3.0, 1.0]` | pass gegen `[0, 3, 1]` und gegen `float('inf')` |
| csv_total | `csv` mit `;`, Punkt weg, Komma → Punkt, `round(., 2)` | `{'Müller': 1235.0, 'Schmidt': 10.0}` |
| cpp_rle | Zähler dann Zeichen, `std::to_string` | `./rle` Exit 0 |
| cpp_ringbuf | Ring, ältestes überschreiben | `./ring` Exit 0 |
| cpp_ringbuf mit zweitem `main` | übliches Demo | `g++`: `redefinition of ‘int main()’` |
| dasselbe mit `#define main student_main` um den Modelltext | — | Exit 0 |
| korrekte Funktion plus `sys.exit(0)` | — | Exit 0, Asserts laufen nicht |
| korrekte Funktion plus falsches Top-Level-assert | — | Exit 1 |

`fix_bug`: die korrigierte exklusive Binärsuche besteht. Die im Prompt stehende Variante `lo = mid` hängt bei `a[mid] < target` und `mid == lo`; der Harness macht daraus nach 20 s einen Fail. Der Test kippt eine korrekte Reparatur nicht.

## Was geprüft wurde und trägt

Ollama-Dauern werden als Nanosekunden gelesen (`/ 1e9`). Die resultierenden Raten liegen auf einer RTX 3070 im erwartbaren Band (9B Q4 Prefill ~2100–2500 t/s, Decode ~56–67 t/s bei voller GPU). Ein Faktor-1000-Fehler ist in den Daten nicht drin. Der Zufalls-Filler und der Port-Check vor `llama-server` sind im Code und greifen. `runner_majflt` trifft das richtige `/proc`-Feld. Page-Cache-warmer Kaltstart ist im Docstring benannt. Die Quality-Passzahlen der abgeschlossenen Summaries stimmen mit den Einzelzeilen überein, bis auf den `0/8`-Record von 01:51–02:01, den die aktuelle Schreibweise in `bench.py:591` nicht mehr erzeugt.

