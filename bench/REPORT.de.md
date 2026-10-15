# RTX 3070 (8 GB) + 16 GB RAM: bestes lokales Coding-Modell — Messbericht

Stand 2026-10-15, gemessen auf **pop-os**: RTX 3070 8 GB (Treiber 580.159.03, 240 W), Ryzen 7 5800X, 16 GB DDR4
(+ zRAM), NVMe hinter LUKS, Pop!_OS, Ollama 0.40.2, llama.cpp a0e6dc7 (eigener Build, CUDA 12.8, sm_86).
Alle Zahlen stammen aus `results/*.jsonl` (Rohdaten) und sind mit den Skripten in diesem Ordner reproduzierbar.
Unabhängig nachgeprüft von Grok (`reviews/grok-bench-review.md`): alle Qualitäts-Zählungen stimmen; seine
Methodik-Befunde sind unten eingearbeitet.

**Statistik:** Median aus 3–5 Läufen. „p95“ in den Rohdaten ist bei n ≤ 11 das Maximum (Befund Grok #1) und wird
hier nicht verwendet. σ der dichten Modelle < 1 %; bei MoE mit Experten im RAM σ ≈ 3–6 %.

---

## Phase 1 — Die Behauptung „Qwen3.5-9B Q4_K_M, 54–58 t/s“ geprüft

| Frage | Ergebnis | Beleg |
|---|---|---|
| Existiert Qwen3.5-9B Q4_K_M? | Ja. Apache-2.0, VLM, 32 Schichten (24 Gated DeltaNet + 8 Full-Attention), 262K nativ | HF-Karte + config.json |
| Dateigröße | 5,63 GB (Ollama/lmstudio), 5,68 GB (unsloth), 6,17 GB (bartowski) + 0,92 GB Vision-Projektor | HF-API |
| Passt in 8 GB? | Ja, **aber nur ohne Projektor**. Mit Projektor legt Ollama schon bei 4K 13 % der Schichten auf die CPU | gemessen, `ollama ps` |
| KV-Cache | nur 8 Schichten: f16 32 KiB/Token, q8_0 17 KiB/Token (32K = 0,53 GiB) + ~50 MiB fester Zustand | berechnet + Ollama-Log „checkpoint 50.251 MiB“ |
| 54–58 t/s realistisch? | Keine Primärquelle gefunden (Schätzseiten). **Gemessen: 64,5 t/s @4K, 56,1 @32K (text-only); mit Projektor 53,0 @4K, 20,1 @32K** | perf-20261015-001001 |
| Kontext ganz im VRAM | 9B text-only: 32K ja (6,57 GB), 64K/128K **nein** (128K: KV 2,18 GB → OOM) | ctx-Probe, llama-server-Log |
| Q4_K_M bester Kompromiss? | Für 9B ja (passt komplett). Für 35B-MoE ist auf 16 GB RAM **IQ3_XXS** das Maximum | siehe Phase 3 |

## Phase 2 — Modellvergleich (alle gemessen, gleiche Bedingungen)

Qualität: 10 Code-Aufgaben (8 Python, 2 C++) mit ausgeführten Unit-Tests, 8 Tool-Call-Fälle (DE/EN, inkl. „kein
Tool nötig“), 3 ERP-Extraktionen als JSON mit und ohne Schema. Temperatur 0, Thinking aus.

| Modell | Code | Tools | JSON Schema / nur Prompt | Ausgabe t/s @4K / @32K | Bemerkung |
|---|---:|---:|---:|---:|---|
| **Qwen3.6-35B-A3B UD-IQ3_XXS (MoE, Experten im RAM)** | **9/10** | 7/8 | 3/3 · 3/3 | **53,6 / 48,5** (final) | Gewinner |
| gemma4:12b-it-qat | 9/10 | 8/8 | 3/3 · 3/3 | 17,4 / 12,2 | 20 % auf der CPU → langsam |
| qwen3.5:9b (text-only) | 8/10 | 8/8 | 3/3 · 3/3 | 64,5 / 56,1 | schnellster „guter“ |
| gemma4:e4b-it-qat | 8/10 | 7/8 | 3/3 · 3/3 | 90,8 / 61,9 | stark für die Größe, 128K im VRAM |
| Ministral-3-14B IQ3_XXS | 7/10 | 8/8 | 3/3 · 0/3 | 12,6 / 3,4 | JSON korrekt, aber in ```-Fences |
| qwen3:8b | 6/10 | 8/8 | 3/3 · 3/3 | – | eingefroren (Statim) |
| qwen3.5:4b | 5/10 | 7/8 | 3/3 · 3/3 | 99,5 / 82,0 | |
| phi4-mini | 5/10 | 3/8 | 2/3 · 0/3 | 112,6 / 59,3 | für Agenten ungeeignet |
| granite4.2:8b | 4/10 | 8/8 | 3/3 · 3/3 | 61,0 / 3,7 | bricht ab 16K ein (KV zu groß) |
| Ornith-1.5-9B | 4/10 | 6/8 | 3/3 · 3/3 | ≈ qwen3.5:9b | braucht Thinking (siehe unten) |
| Gemma-4-26B-A4B IQ3_XXS (MoE) | – | – | – | 40,4 / 37,3 | Qualitätslauf abgebrochen (Nutzer: genug getestet) |

Thinking (nur 5 schwere Aufgaben): Ornith 0/5 → 3/5, Qwen3.5-9B 3/5 → 2/5, Qwen3.6 4/5 → 3/5. **Nicht belastbar:**
Thinking-Budget 12 288 Tokens bei 16K Kontext — mindestens ein Lauf wurde abgeschnitten (Grok #11). Nur „Ornith
braucht Thinking“ ist klar.

Empfehlungen pro Zweck:

| Zweck | Modell |
|---|---|
| Allgemeiner Assistent | Qwen3.6-35B-A3B; schnell & klein: gemma4:e4b |
| Autonomer Coding-Agent, Python/C++, Debugging, Repo-Analyse | **Qwen3.6-35B-A3B** (64K Kontext) |
| Lokale Automation / ERP-Workflows (Tool-Calls, JSON) | Qwen3.6-35B-A3B; bei Tempo-Bedarf qwen3.5:9b-text — **immer mit JSON-Schema** (`format`/`response_format`) |
| Schnellstes brauchbares Modell | gemma4:e4b (91 t/s, Code 8/10) |

## Phase 3 — GPU-Optimierung (gemessen, eine Änderung pro Schritt)

| Maßnahme | Effekt (gemessen) | Urteil |
|---|---|---|
| **Vision-Projektor weglassen** (Ollama-Variante `qwen3.5:9b-text`) | 32K: **20,1 → 56,1 t/s** (×2,8); Ornith-Agent 20,9 → 60,0 | größter Einzelhebel |
| **MoE-Experten im RAM** (`--fit`, Qwen3.6-35B-A3B) | 35B-Modell mit 47–49 t/s auf 8 GB | macht den Gewinner erst möglich |
| **Neuer llama.cpp + `-ub 2048`** | Prompt 704 → 1523 t/s @4K, 661 → 1639 @32K; Ausgabe −4 % | Pflicht für Agenten (TTFT 32K: 50 s → 20 s) |
| **MTP (`--spec-type draft-mtp --spec-draft-n-max 2`, MTP-GGUF)** | Ausgabe +14 % @4K (47,0 → 53,6), +10 % @32K (44,2 → 48,5); Akzeptanz 75 %; Prompt −10–28 % | an |
| `--moe-cache-mib 1024` | Ausgabe ±0 bis −2 %, Prompt −16 %; **mit MTP zusammen −10 %** | aus (zu wenig VRAM) |
| KV-Cache f16 vs q8_0 vs q4_0 (9B) | Tempo gleich (±1 %), VRAM: f16 +390 MB, q4_0 −260 MB | q8_0 |
| `-ub 1024`/`2048` bei dichtem 9B | Prompt +12 % @32K, ab 1024 kein weiterer Gewinn | 1024 |
| Flash Attention aus (9B, alle Schichten GPU, 33K) | lädt nicht (Compute-Puffer +1,16 GB → OOM) | FA an |
| `-lm none` (pinned), `--cache-ram`, ik_llama.cpp | nicht gemessen (Testabbruch) | offen |

Speicher-Telemetrie bei Qwen3.6 (final): Runner 670–830 Major Faults/s, bis 106 MB/s NVMe-Reads, RSS 10,5–11,5 GB.
**Die Experten werden aus dem Page-Cache verdrängt** — der eigentliche Engpass ist der RAM (16 GB), nicht die GPU.

Thermik/Takt: max. 75 °C, 240 W (Power-Limit), SM-Takt unter Last ≥ 1830 MHz — keine Drosselung beobachtet.

## Phase 4 — Benchmark-Suite

| Datei | Zweck |
|---|---|
| `bench.py perf` | Ollama: Kaltstart, TTFT, PP/TG je Kontexttiefe (4K–32K), VRAM, RSS, GPU-Anteil, Faults/NVMe |
| `bench.py ctx` | höchster GPU-residenter Kontext je Modell |
| `bench.py quality [--think] [--tasks …] [--openai URL]` | Code (ausgeführte Tests), Tools, JSON — Ollama oder llama-server |
| `bench_llamacpp.py --configs … --extra …` | llama-server-Flags A/B, inkl. MTP-Akzeptanz |
| `serve_quality.sh` | GGUF über llama-server starten und Qualität messen |
| `summarize.py` | Tabellen aus den Rohdaten |

Bekannte Grenzen (Grok-Review): p95 bei kleinem n = Maximum; Fehlläufe fehlen in `summarize.py`; erster Lauf nach
Serverstart ist Aufwärmen; VRAM-Spalte bei llama-server gilt pro Server, nicht pro Tiefe; JSON-ohne-Schema wertet
Markdown-Fences als Fehler. Fixes sind in Arbeit.

## Phase 5 — Produktions-Setup

Umgesetzt als **Alia** (dieses Repository): `alia` erkennt die Hardware, wählt das gemessene Profil,
startet llama-server mit den Flags unten und öffnet Qwen Code (Terminal) bzw. `alia web` (Browser).

```bash
LD_LIBRARY_PATH=~/src/llama.cpp/build/bin ~/src/llama.cpp/build/bin/llama-server \
  -m ~/models/gguf/mtp/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf -c 65536 \
  -fa on -ctk q8_0 -ctv q8_0 -np 1 --jinja -b 2048 -ub 2048 \
  --spec-type draft-mtp --spec-draft-n-max 2 -ctkd q8_0 -ctvd q8_0 \
  --host 127.0.0.1 --port 8090
# Sampling (Qwen-Karte, präzises Coding): temp 0.6, top_p 0.95, top_k 20, min_p 0, presence 0
```

Kontext im Profil: 64K (60K gefüllt: 38,2 t/s, 1041 t/s Prompt). 128K läuft (120K: 25,0 t/s, ~3,7 min bis zum
ersten Token), ist als Standard zu langsam.
`--cache-ram` fehlt absichtlich, weil es nicht erfolgreich vermessen wurde. Die
4K-/32K-Schlagzeilenwerte nutzten Serverkontext 33792. Die Herkunft jeder
Metrik in `profiles.json` verhindert, dass sie für Messungen dieses 64K-argv
gehalten werden.

Bereits geändert (mit Backup `*.bak-20261015-013834`): OpenCode und Hermes nutzen `ornith-1.5:9b-text-agent32k`
(ohne Projektor, ×2,9 bei 32K). Toter Eintrag `qwen2.5-coder:7b-16k` entfernt.

## Phase 6 — Urteil

1. **Bestes Gesamtmodell:** Qwen3.6-35B-A3B UD-IQ3_XXS (MTP-GGUF) mit Experten im RAM.
2. **Bestes Coding-Modell:** dasselbe (9/10 Code, 7/8 Tools, 6/6 JSON).
3. **Schnellstes brauchbares:** gemma4:e4b-it-qat (91 t/s @4K, Code 8/10).
4. **Größter praktischer Kontext:** 64K mit Qwen3.6 (38 t/s); ganz im VRAM: gemma4:e4b bis 128K.
5. **Quantisierung:** dichte Modelle Q4_K_M (ohne Projektor); 35B-MoE auf 16 GB RAM UD-IQ3_XXS.
6. **Erwartung (gemessen, Median):** 53,6 t/s @4K · 48,5 @32K · 38,2 @60K; Prompt 1,0–1,5k t/s; Schwankung ±3–6 %.
7. **Produktions-Konfiguration:** siehe Phase 5 / Alia-Profil `rtx8gb-16gb-qwen36-35b`.
8. **Drei Optimierungen mit dem größten Effekt:** (1) Projektor weg / text-only (×2,8), (2) MoE-Experten im RAM statt
   kleinerem dichtem Modell (35B bei ~50 t/s), (3) neuer llama.cpp + `-ub 2048` (Prompt ×2,2), dazu MTP (+10–14 %).

**Größter Hardware-Hebel:** 64 GB RAM (Q4-Quant, keine Page-Faults), danach eine 24-GB-GPU (Schätzung, nicht gemessen).
