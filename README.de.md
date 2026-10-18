<p align="center"><img src="site/logo-terminal.svg" width="360" alt="ALIA"></p>

<p align="center"><b>Deine Hardware. Deine KI. Keine Cloud.</b><br><a href="README.md">English</a> | Deutsch</p>
<p align="center">
  <a href="https://github.com/BEKO2210/alia/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/BEKO2210/alia/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/BEKO2210/alia/actions/workflows/codeql.yml"><img alt="CodeQL" src="https://github.com/BEKO2210/alia/actions/workflows/codeql.yml/badge.svg"></a>
  <a href="https://codecov.io/gh/BEKO2210/alia"><img alt="Coverage" src="https://codecov.io/gh/BEKO2210/alia/graph/badge.svg"></a>
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-5C9DFF"></a>
  <a href="https://beko2210.github.io/alia/"><img alt="Website" src="https://img.shields.io/badge/website-alia-A78BFA"></a>
</p>

Alia ist ein vollständig lokaler Coding-Agent-Starter ausschließlich für Linux. Er erkennt NVIDIA-GPU, VRAM und RAM, wählt ein Hardwareprofil, startet `llama-server` und öffnet Qwen Code im gebrandeten Terminal oder als Web Shell. Alia implementiert weder einen eigenen Agent-Loop noch eine Inferenz-Engine.


![Alia-Startbildschirm](docs/screenshots/terminal-start.png)

![Alia im Terminal](docs/screenshots/terminal-agent.png)

![Alia Web Shell](docs/screenshots/web-shell.png)

> **Gemessen auf RTX 3070 8 GB, Ryzen 7 5800X, 16 GB RAM — Startkonfiguration**
>
> Qwen3.6 35B-A3B IQ3_XXS (Standard, Kontext 65.536): **49,9 / 39,1 / 37,4 Tok/s** Ausgabe und 1.034 / 1.451 / 1.330 Tok/s Prompt-Verarbeitung bei 4K / 32K / 60K (Lauf `llamacpp-20261017-234751`, Alias llama.cpp-Build, exakte Profil-Flags). Das 4K-Tempo ist stabil (46,5–49,9 Tok/s über vier Läufe). Das Tempo bei langem Kontext hängt am freien RAM: Verdrängen andere Programme das 13-GB-Modell aus dem Page-Cache, wird es von der SSD gestreamt und fällt auf 24,6 Tok/s bei 32K und 9,7 bei 60K (Lauf `llamacpp-20261015-101143`). **Für lange Kontexte 32 GB RAM nutzen** oder den Browser schließen. Alia warnt beim Start, wenn weniger als 11 GB RAM verfügbar sind, und `alia doctor` zeigt den freien RAM.
>
> Qwen3.5 9B Q4_K_M (schnell, Kontext 65.536): **66,2 / 57,8 / 51,4 Tok/s** Ausgabe und 2.964 / 2.695 / 2.424 Tok/s Prompt-Verarbeitung bei 4K / 32K / 60K (Lauf `llamacpp-20261017-235521`).

TG ist die Token-Generierungsrate, PP die Prompt-Verarbeitungsrate. MTP bedeutet Multi-Token Prediction, also spekulative Decodierung über die MTP-Köpfe des Modells. Exakter Lauf und Kontext stehen für jede numerische Metrik direkt in `profiles.json`.
Die Qualitätswerte (35B: Code 9/10, Tools 7/8, JSON 3/3 mit Schema und 3/3 nur per Prompt; 9B: Code 8/10, Tools 8/8) stammen aus separaten Qualitätsläufen ohne aufgezeichneten Serverkontext und ohne Serverargumente; der 9B-Qualitätslauf lief über Ollama.

## Unterstützte Plattform und Voraussetzungen

Alia v0.2.0 unterstützt natives Linux mit NVIDIA-GPU. Es verwendet `/proc`, `flock` und den Linux-Prozessstartzeitpunkt; Windows, macOS, AMD-GPUs, reiner CPU-Betrieb und WSL2 werden nicht unterstützt. Python 3.12+ ist die unterstützte Laufzeit für das in diesem Release getestete Prozessmanagement.

Die exakte Qwen-Code-Version und das Hugging-Face-CLI installieren:

```bash
npm install -g @qwen-code/qwen-code@0.25.1
python3 -m pip install -U "huggingface_hub[cli]"
```

Einen CUDA-fähigen `llama-server` bauen. Commit `a0e6dc7` ist die von Alia minimal unterstützte und vermessene llama.cpp-Revision und enthält `--spec-type draft-mtp`:

```bash
git clone https://github.com/ggml-org/llama.cpp.git ~/src/llama.cpp
cd ~/src/llama.cpp
git checkout a0e6dc7
cmake -S . -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j"$(nproc)" --target llama-server
```

Erforderlich sind ein funktionierender NVIDIA-Treiber, ein von llama.cpp unterstütztes CUDA-Toolkit, CMake, C++-Compiler, Git, Node.js/npm sowie Python/pip. Der vermessene Build nutzte CUDA 12.8 auf einer RTX 3070. Alia sucht `~/src/llama.cpp/build/bin/llama-server`; für einen anderen getesteten Build kann `ALIA_LLAMA_SERVER=/absoluter/pfad/zu/llama-server` gesetzt werden. Der frühere Fallback auf Ollamas mitgeliefertes Binary wurde entfernt, weil dessen Flags und MTP-Unterstützung keine stabile öffentliche Schnittstelle sind.

Die Modell-Repositories sind öffentlich und benötigen normalerweise keine Hugging-Face-Anmeldung. Falls Hugging Face Authentifizierung verlangt oder ein Rate-Limit greift, vorher `hf auth login` ausführen.

## Installation

```bash
git clone https://github.com/BEKO2210/alia alia
cd alia
./install.sh
alia doctor
```

`install.sh` prüft Python 3.12+, Qwen Code 0.25.1, `hf` und `llama-server` und erzeugt danach `~/.local/bin/alia`. Bei jedem fehlgeschlagenen Dateisystemschritt bricht es ab. Falls nötig, das Verzeichnis zu `PATH` hinzufügen:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Downloads und Speicherplatz

Der erste Start zeigt den exakten `hf download`-Befehl und fragt `Jetzt herunterladen? [y/N]`; ohne Bestätigung wird nichts geladen. Etwa 10 % freien Zusatzplatz über der Dateigröße einplanen:

| Profil/Modell | Download | Empfohlener freier Platz | Ca. bei 100 Mbit/s |
|---|---:|---:|---:|
| 35B IQ3_XXS, Standard | 14,07 GB | 16 GB | 19 Minuten |
| Ornith-1.5 35B-A3B, Qualität | 14,37 GB + Template | 16 GB | 20 Minuten |
| 9B Q4_K_M, schnell | 5,7 GB | 7 GB | 8 Minuten |
| 35B Q4_K_XL, unvermessen | 20,8 GB | 23 GB | 28 Minuten |

Die tatsächliche Dauer hängt von Hugging Face und der Verbindung ab. Eine nach Abbruch zu kleine GGUF-Datei wird beim nächsten Start abgelehnt. Downloads landen unter `~/.local/share/alia/models`. Ein dokumentierter generischer Kandidat wie `~/models/gguf/Qwen3.5-9B-Q4_K_M.gguf` verhindert einen zweiten Download.

## Verwendung

```bash
alia                              # Hardware erkennen, Server und Agent starten
alia --lang de_DE.UTF-8           # Sprache für diesen Aufruf setzen
alia --continue                   # neueste Qwen-Sitzung fortsetzen
alia --resume [ID]                # Qwen-Sitzung optional per ID fortsetzen
alia --fast                       # Denken für einfache, schnelle Aufgabe aus
alia --wait-gpu 60                # auf optionale gemeinsame GPU-Sperre warten
alia --auto-edit                  # Dateiänderungen automatisch erlauben
alia --yolo                       # alle Tools erlauben; rote Warnung
alia --sandbox                    # Tool-Befehle einsperren: nur Projekt schreibbar, kein Tool-Netz (braucht bwrap)
alia -- -p "Erkläre main.py"      # Argumente unverändert an qwen geben
alia web                          # Web Shell auf 127.0.0.1:4170
alia web --port 4317 --no-open --workspace "$PWD"
alia doctor                       # prüft auch Modell, hf, Speicher und Port
alia status                       # Server, Zustand, Laufzeit, Profil und Modell
alia profiles
alia use rtx8gb-qwen35-9b-fast
alia use auto
alia lang de_DE.UTF-8             # Deutsch dauerhaft; Locale-Formen gehen
alia lang en
alia lang auto
alia mcp                          # optionale MCP-Server anzeigen (Browser, Suche)
alia mcp enable browser           # aktivieren; gilt ab der nächsten Sitzung
alia mcp disable search
alia mcp test                     # aktive MCP-Server starten und Tools auflisten
alia logs
alia stop
alia --help
alia --version
```

Sprachvorrang: `--lang` → `ALIA_LANG` → Konfiguration → `LC_ALL` → `LC_MESSAGES` → `LANG` → Englisch. Modellantworten folgen der Eingabesprache, sofern keine andere Sprache ausdrücklich verlangt wird.

Alia liest Projektanweisungen aus `QWEN.md`, `AGENTS.md` und `CLAUDE.md`. Halte diese Dateien kurz: Sie werden mit jeder Anfrage erneut gesendet, und `alia doctor` zeigt ihre geschätzte Größe.

`--fast` schreibt `chat_template_kwargs.enable_thinking: false`; normale Läufe lassen Denken aktiviert. Im Standardmodus wird vor Änderungen und Befehlen gefragt. `--auto-edit` genehmigt nur Änderungen. `--yolo` genehmigt alle Tool-Aufrufe und gehört nur in vollständig vertrauenswürdige Workspaces.

Zur Koordination mit anderen GPU-Jobs kann `gpu_lock` in `~/.config/alia/config.json` oder `ALIA_GPU_LOCK` auf eine Sperrdatei zeigen. `--wait-gpu S` begrenzt die Wartezeit. Zusätzlich hält Alia immer eine eigene Statussperre über Wiederverwendungsprüfung, Start und Gesundheitsprüfung.

```json
{"gpu_lock": "~/.cache/shared-gpu.lock"}
```

Laufzeitdaten liegen unter `~/.local/state/alia`, Modelle unter `~/.local/share/alia/models`, Einstellungen unter `~/.config/alia/config.json`. Qwen nutzt ein isoliertes Alia-`QWEN_HOME`; systemweite Benutzer-Skills sind deaktiviert, Projekt-Skills bleiben verfügbar.

### Browser und Websuche (opt-in)

Qwen Code hat keinen eigenen Browser, und die eingebaute Websuche braucht einen Cloud-Schlüssel. Alia kann deshalb zwei optionale MCP-Server einbinden. Beide sind standardmäßig aus; `alia mcp enable browser|search` schaltet einen ein, `alia mcp disable NAME` wieder aus, `alia mcp` listet sie. Änderungen gelten ab der nächsten Sitzung von `alia` oder `alia web`.

- `browser` — Headless-Browser mit Playwright ([@playwright/mcp](https://github.com/microsoft/playwright-mcp) 0.0.83): Seiten öffnen, Text-Snapshots lesen, klicken, tippen und Formulare ausfüllen. Screenshots und JavaScript-Ausführung sind nicht freigegeben. Benötigt `npx` (Node.js) und Google Chrome; ohne Chrome einmal `npx playwright install chromium` ausführen. Ausgaben landen unter `~/.cache/alia/playwright`.
- `search` — Websuche und Seitenabruf über DuckDuckGo ([duckduckgo-mcp-server](https://pypi.org/project/duckduckgo-mcp-server/) 0.7.0), ohne API-Schlüssel. Benötigt `uvx` (uv). Die Suche liest html.duckduckgo.com aus und kann daher brechen oder blockiert werden; Alia begrenzt sie auf 10 Suchen und 10 Seitenabrufe pro Minute.

Jeder MCP-Tool-Aufruf läuft durch die normale Bestätigung; `--yolo` genehmigt sie ohne Nachfrage. Die erste Sitzung lädt die fest versionierten Pakete herunter. `alia mcp test [NAME]` startet die aktiven Server (oder nur NAME) genau wie eine Sitzung und listet ihre Tools; für einen ersten Download wartet es bis zu 90 s. Alia lädt die MCP-Tool-Schemas vorab (`alwaysLoadTools`), damit das Modell sie ohne Umweg über `tool_search` aufrufen kann.

### Sandbox (opt-in)

`alia --sandbox` sperrt die Befehle des Agenten mit bubblewrap ein: Sie dürfen nur im Projekt schreiben und haben kein Netzwerk; das Modell selbst spricht weiter mit dem lokalen Server. Host-Dateien wie `~/.ssh` bleiben lesbar, und Tools, die Netz brauchen (etwa `pip install`), scheitern. Installiere `bwrap` (Paket `bubblewrap`); `alia doctor` zeigt, ob es verfügbar ist. Qwen Code 0.25.1 unterstützt die Sandbox weder mit MCP-Servern noch in `alia web`, daher bricht Alia in beiden Fällen mit einer Fehlermeldung ab. Starte sie aus einem Projektverzeichnis unterhalb deines Home-Verzeichnisses: Qwen Code lehnt einen Workspace ab, der `$HOME` selbst ist, darüber liegt oder sich mit Alias Qwen-Zustand oder der Qwen-Code-Installation überschneidet; Alia prüft das vorher. Weil `/rewind` in der Sandbox keine Dateien wiederherstellen kann, speichert Alia offene Änderungen an versionierten Dateien vor der Sitzung in `refs/alia/pre-session` (nicht versionierte Dateien sind nicht enthalten) und zeigt den Befehl zum Wiederherstellen. Details: [SECURITY.md](SECURITY.md).

## Mitgelieferte Profile

| Profil | Ziel | Modell/Download | TG 4K / 32K | PP 4K / 32K | Status |
|---|---|---|---:|---:|---|
| `rtx8gb-16gb-qwen36-35b` | 8 GB VRAM, 16 GB RAM | 35B IQ3_XXS, 14,07 GB | 49,9 / 39,1 | 1.034 / 1.451 | gemessen, Startkonfiguration; 32K braucht freien RAM |
| `rtx8gb-16gb-ornith15-35b-quality` | 8 GB VRAM, 16 GB RAM | Ornith-1.5 35B-A3B I-Mini, 14,37 GB + Template | — | — | Agent-Aufgaben 16/16, Mittel 248 s, 41,8 Gen.-Tok/s |
| `rtx8gb-16gb-qwen36-35b-128k` | 8 GB VRAM, 16 GB RAM | dasselbe GGUF wie der Standard, ctx 131.072 | — | — | Agent-Aufgaben 3/3, 44,1 Gen.-Tok/s (≈20 % unter den 54,6 des Standards) |
| `rtx8gb-qwen35-9b-fast` | 8 GB VRAM, 12 GB RAM | 9B Q4_K_M, 5,7 GB | 66,2 / 57,8 | 2.964 / 2.695 | gemessen, Startkonfiguration |
| `rtx12-16gb-qwen36-35b-q4` | 12–16 GB VRAM, 32 GB RAM | 35B Q4_K_XL, 20,8 GB | — | — | unvermessen; nie auf Zielhardware gelaufen |
| `rtx24gb-qwen36-35b-q4` | ab 20 GB VRAM, 32 GB RAM | 35B Q4_K_XL, 20,8 GB | — | — | unvermessen; nie auf Zielhardware gelaufen |

Die automatische Auswahl bevorzugt das höchstrangige passende vermessene Profil und warnt vor einem unvermessenen oder unpassend fixierten Profil. Messmethodik und Grenzen stehen in [`bench/REPORT.md`](bench/REPORT.md), die Rohdatenübersicht in [`bench/results/README.md`](bench/results/README.md), das unabhängige Review in [`bench/reviews/grok-bench-review.md`](bench/reviews/grok-bench-review.md).

### Profil auswählen

Das standardmäßige Qwen3.6-Profil ist die schnelle Wahl: Es löste 13/16 eingefrorenen Agent-Aufgaben in etwa 104 Sekunden pro Aufgabe. Für höhere Qualität `alia use rtx8gb-16gb-ornith15-35b-quality` ausführen; Ornith löste 16/16 in etwa 248 Sekunden pro Aufgabe, ist damit ungefähr 2,4-mal langsamer und lädt ein 14,37-GB-GGUF plus Chat-Template herunter. Mit `alia use auto` geht es zur automatischen Auswahl zurück.

Für große Aufgaben verdoppelt `alia use rtx8gb-16gb-qwen36-35b-128k` das Fenster: Qwen Code komprimiert dann erst bei etwa 98K statt 32,5K Tokens, bei rund 20 % weniger Tempo (llama.cpp lagert mehr Experten auf die CPU aus, damit der größere KV-Cache passt).

Jedes mitgelieferte Profil begrenzt llama-servers Prompt-Cache im Host-RAM auf 2.048 MiB; das verhindert das Swap-Wachstum, das mit dem Standardwert von 8.192 MiB auf einem 16-GB-Rechner beobachtet wurde.

### Mehr Kontext mit Subagenten

Ein Subagent bekommt ein eigenes volles Fenster; eine große Aufgabe aufzuteilen ist darum oft besser als ein größerer Kontext. Einfach in Worten darum bitten, etwa „nutze einen Subagenten, der jeden Aufrufer von `parse_config` findet und Datei:Zeile meldet". Während der Subagent läuft, hält llama-server den Zustand des Hauptagenten im Prompt-Cache im Arbeitsspeicher statt auf der GPU. In einem gemessenen Lauf machte der Hauptagent nach einem Subagenten mit 10,8K Tokens mit 21 neu ausgewerteten Tokens (0,4 s) weiter, statt seinen 15K-Token-Verlauf neu zu lesen (Lauf `agent-20261017-211634`). Ein `fork`-Subagent (`subagent_type "fork"`) erbt den Verlauf des Hauptagenten und startet fast ohne Kosten; er passt, wenn der Subagent das bisherige Gespräch braucht.

## Profil hinzufügen

Ein Objekt zu `profiles.json` hinzufügen. Nur generische `~/models/...`-Kandidaten verwenden. Jede numerische Messmetrik braucht einen `metric_sources`-Eintrag mit `bench/results/*.jsonl`-Lauf und Serverkontext; Unterschiede bei Binary, Kontext oder Flags gegenüber der Startkonfiguration müssen genannt werden.

```bash
python3 -m json.tool profiles.json >/dev/null
python3 -m unittest discover -s tests -v
./alia profiles
```

## Sicherheit

Alia erzwingt für `llama-server` `127.0.0.1:8090`, lehnt Host-/Port-Overrides aus Profilen ab, deaktiviert die llama.cpp-Weboberfläche und übergibt den lokalen API-Schlüssel an Server und Qwen. Das Statusverzeichnis hat Modus `0700`, Status-, Settings-, Sperr- und Logdateien `0600`. Stoppsignale treffen nur die gespeicherte PID nach Prüfung ihrer Linux-Startzeit. Lebt der Prozess nach SIGKILL weiter, bleiben die Statusdateien erhalten. Alia verwendet nie `pkill`.

Loopback trennt keine gegenseitig unvertrauenswürdigen lokalen Benutzer. Der feste lokale API-Schlüssel ist für ausreichend privilegierte lokale Prozesse sichtbar; die Qwen Web Shell hat keine zusätzliche Bearer-Token-Sperre. Keinen Port über SSH-Forwarding, Reverse Proxy, Container oder Firewalländerungen freigeben. Keine parallelen Alia-Sitzungen mit verschiedenen Freigabemodi starten, da sie eine Settings-Datei teilen. `--yolo` erlaubt beliebige Tools ohne Rückfrage. Ollama-Unload spricht nur Ollamas Loopback-API an: ein nicht laufendes Ollama wird ignoriert, aber Alia bricht ab, wenn erkannte Modelle nicht binnen 10 Sekunden entladen sind.

## Showcase

[Alia, von Alia erklärt](https://beko2210.github.io/alia/showcase/architecture/) ist eine Seite, die Alia lokal auf der RTX 3070 über die eigene Architektur geschrieben hat: Es hat den eigenen Quellcode gelesen und das interaktive Diagramm, den animierten Request-Flow und den Benchmark-Teil gebaut. [Alle Prompts](site/showcase/architecture/PROMPTS.md) sind veröffentlicht, auch das, was schiefging.

## Entwicklung und Screenshots

Die Unit-Tests brauchen keine GPU, starten keinen Server und laden keine Modelle:

```bash
python3 -m unittest discover -s tests -v
```

`tools/screenshot.sh` ist nur für Entwicklung und benötigt zusätzlich tmux sowie Chrome/Chromium. Es liest ein vorhandenes Pane und startet weder Alia noch tmux.

## Danksagung und Lizenzen

- [Qwen Code](https://github.com/QwenLM/qwen-code), Apache-2.0
- [llama.cpp](https://github.com/ggml-org/llama.cpp), MIT
- Qwen-Modelle und GGUF-Repositories unter ihren jeweiligen Lizenzen

Siehe [`LICENSE`](LICENSE) und [`NOTICE`](NOTICE). Alia startet externe Komponenten, verteilt sie aber nicht weiter.
