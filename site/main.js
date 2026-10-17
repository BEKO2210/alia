"use strict";

const DE = {
  "skip": "Zum Inhalt springen",
  "nav.features": "Funktionen",
  "nav.bench": "Messwerte",
  "nav.install": "Installation",
  "hero.pill": "v0.1.0 · Open Source · Apache-2.0",
  "hero.title": "Ein lokaler Coding\u2011Agent<br><span class=\"grad\">für die GPU, die du schon hast.</span>",
  "hero.lead": "Alia erkennt deine GPU, wählt ein vermessenes Modellprofil, startet llama.cpp und öffnet einen vollwertigen Coding\u2011Agenten im Terminal. Kein API-Key. Keine Cloud. Nichts verlässt deinen Rechner.",
  "hero.cta": "Loslegen",
  "hero.github": "Auf GitHub ansehen",
  "hero.meta": "Linux · NVIDIA · getestet auf einer RTX 3070 mit 8 GB VRAM",
  "term.replay": "Nochmal",
  "term.caption": "Drei echte Prompts auf einer RTX 3070, nichts von Hand bearbeitet: Alia schreibt ein Live-GPU-Dashboard (eine Python-Datei, nur Standardbibliothek), poliert das Layout und findet und behebt dann per grep den eigenen Fehler. Die Terminal-Teile laufen wie angegeben schneller; die Polier-Runde war langsam, weil der Server auslagerte. Der letzte Clip zeigt das Ergebnis in Echtzeit.",
  "stat.tg": "Ausgabe mit einem 35B-MoE-Modell bei 4K Kontext, exakte Startkonfiguration",
  "stat.vram": "VRAM reichen: die Experten kommen aus dem Arbeitsspeicher",
  "stat.code": "Tokens im ersten Prompt (vorher 22,8K)",
  "stat.cloud": "API-Keys, Konten oder Cloud-Aufrufe",
  "feat.eyebrow": "Warum Alia",
  "feat.title": "Alles, was ein Coding\u2011Agent braucht.<br><span class=\"mut2\">Nichts, was nach Hause telefoniert.</span>",
  "f1.t": "Profile passend zur Hardware",
  "f1.d": "Alia liest VRAM und RAM aus und startet das beste <em>vermessene</em> Profil für deinen Rechner. Mit <code>alia use</code> legst du ein anderes fest, <code>alia profiles</code> vergleicht sie.",
  "chip.measured": "vermessen",
  "chip.unmeasured": "unvermessen",
  "f2.t": "35B auf einer 8-GB-Karte",
  "f2.d": "Ein Mixture-of-Experts-Modell nutzt pro Token nur 3B Parameter. Attention bleibt auf der GPU, die Experten liegen im RAM.",
  "f3.t": "Spekulatives Decoding",
  "f3.d": "Der MTP-Kopf des Modells entwirft zwei Tokens im Voraus. 75 % werden übernommen: +14 % Tempo bei 4K, +10 % bei 32K.",
  "f4.t": "Ein echter Agent",
  "f4.d": "Basiert auf Qwen Code: bearbeitet Dateien, führt Befehle aus, liest Fehler und behebt sie. Mit <code>alia -c</code> setzt du Sitzungen fort. Fragt vor jeder Aktion, außer du wählst <code>--auto-edit</code> oder <code>--yolo</code>.",
  "f5.t": "Terminal oder Browser",
  "f5.d": "<code>alia web</code> öffnet denselben Agenten als Web-Shell, nur auf 127.0.0.1.",
  "f6.t": "Belege statt Behauptungen",
  "f6.d": "Jede Benchmark-Zahl auf dieser Seite verweist auf JSONL-Rohdaten; Lücken in der Konfiguration sind ausdrücklich gekennzeichnet.",
  "f8.t": "Von Grund auf schlank",
  "f8.d": "17 ungenutzte Tools gesperrt, keine Hintergrund-Memory-Aufrufe, keine Folgefragen, Skills aus <code>~/.agents/skills</code> nicht geladen. Der erste Prompt sank von 22,8K auf 10,9K Tokens. Eine Ein-Wort-Antwort dauert auf dem warmen Server ca. 3 s (vorher 7 s).",
  "f7.t": "Browser und Websuche, Opt-in",
  "f7.d": "Optional über MCP, standardmäßig aus: <code>alia mcp enable browser</code> (Playwright-MCP, Text-Snapshots) und <code>alia mcp enable search</code> (DuckDuckGo, kein API-Key, ratenbegrenzt). <code>alia mcp test</code> prüft beides. Im Test las das 35B-Modell eine JS-gerenderte Seite in 26 s und fand eine Paketversion samt Quelle in 24 s.",
  "bench.eyebrow": "Messwerte",
  "bench.title": "Gemessen, nicht geschätzt.",
  "bench.sub": "Ausgabetempo, während sich der Kontext füllt, jeweils mit der exakten Startkonfiguration des Profils. RTX 3070 8 GB, Ryzen 7 5800X, 16 GB RAM, llama.cpp a0e6dc7.",
  "bench.default": "Standard",
  "bench.fast": "schnell",
  "bench.d4": "4K Kontext",
  "bench.d32": "32K Kontext",
  "bench.d60": "60K Kontext",
  "q.code": "Code-Aufgaben",
  "q.tools": "Tool-Aufrufe",
  "q.json": "JSON mit / ohne Schema",
  "q.pp": "Prompt-Tempo 4K / 32K",
  "q.dl": "Download",
  "q.note9b": "* Gemessen über Ollama mit Qwens eigener GGUF, nicht mit der unsloth-GGUF und der llama-server-Konfiguration, mit der dieses Profil startet.",
  "bench.fine": "Alle Werte nutzen die Flags und die Kontextgröße, mit denen das Profil startet (35B: 65.536, 9B: 33.408); der 35B-Wert bei 60K stammt aus einem früheren Lauf mit denselben Flags ohne <code>--jinja</code>, das nur die Chat-Vorlage wählt. Langer Kontext braucht freien RAM: Mit offenem Browser und anderen Programmen wurde das 35B-Modell von der SSD gestreamt und fiel auf 24,6 Tok/s bei 32K und 9,7 bei 60K. Für lange Kontexte sind 32 GB RAM empfohlen. Die Qualitätswerte stammen aus separaten Läufen. <a href=\"https://github.com/BEKO2210/alia/tree/main/bench/results\">Rohdaten und Methodik →</a>",
  "shots.eyebrow": "Im Einsatz",
  "shots.title": "Dein Terminal. Oder dein Browser.",
  "shots.term": "Terminal",
  "shots.web": "Web-Shell",
  "show.eyebrow": "Showcase",
  "show.title": "Alia, von Alia erklärt.",
  "show.sub": "Wir haben Alia gebeten, die eigene Architektur zu visualisieren. Lokal auf der RTX 3070 hat es den eigenen Quellcode gelesen und die ganze Seite geschrieben: interaktives Diagramm, animierter Request-Flow und die gemessenen Werte. Alle Prompts sind veröffentlicht.",
  "show.open": "Seite öffnen",
  "show.prompts": "Prompts lesen",
  "stack.eyebrow": "Wie es gebaut ist",
  "stack.title": "Auf bewährtem Open Source gebaut.",
  "stack.sub": "Alia erfindet weder die Agenten-Schleife noch die Inferenz neu. Es ergänzt, was fehlte: Hardware-Erkennung, vermessene Profile, einen sicheren Server-Lebenszyklus und einen Befehl, der alles startet.",
  "stack.alia": "Hardware-Erkennung · Profile · Server-Lebenszyklus · Branding",
  "stack.qwen": "Agenten-Schleife, Tools, Terminal-UI, Web-Shell",
  "stack.llama": "CUDA-Inferenz, Experten-Offload, MTP-Entwürfe",
  "stack.model": "Open-Weight-Modell, dynamische 3-Bit-Quantisierung",
  "stack.hw": "Deine GPU",
  "inst.eyebrow": "Installation",
  "inst.title": "In vier Schritten startklar.",
  "inst.s1": "Agent und Downloader",
  "inst.s2": "llama.cpp mit CUDA",
  "inst.s3": "Alia",
  "inst.s4": "Starten &amp; Befehle",
  "inst.note": "Der erste Start zeigt den genauen Modell-Download (14,07 GB beim Standardprofil) und fragt, bevor etwas geladen wird. Status prüfen mit <code>alia status</code>, fortsetzen mit <code>alia -c</code> oder Tools verwalten mit <code>alia mcp</code>.",
  "copy": "Kopieren",
  "final.title": "Dein eigener Coding\u2011Agent.",
  "final.sub": "Kostenlos, Open Source und läuft auf der Hardware, die du schon hast.",
  "final.cta": "Auf GitHub folgen",
  "final.contrib": "Dein GPU-Profil beitragen",
  "foot.credit": "Gebaut auf llama.cpp, Qwen Code und Qwen3.6.",
  "foot.security": "Sicherheit",
};

const nodes = [...document.querySelectorAll("[data-i18n]")];
const EN = Object.fromEntries(nodes.map((n) => [n.dataset.i18n, n.innerHTML]));

function storage(fn) { try { return fn(); } catch { return null; } }

function setLang(lang) {
  const dict = lang === "de" ? DE : EN;
  for (const n of nodes) n.innerHTML = dict[n.dataset.i18n] ?? EN[n.dataset.i18n];
  document.documentElement.lang = lang;
  for (const b of document.querySelectorAll("[data-lang]")) b.setAttribute("aria-pressed", String(b.dataset.lang === lang));
  storage(() => localStorage.setItem("alia-lang", lang));
}
for (const b of document.querySelectorAll("[data-lang]")) b.addEventListener("click", () => setLang(b.dataset.lang));
const saved = storage(() => localStorage.getItem("alia-lang"));
setLang(saved || ((navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en"));

/* copy buttons */
for (const btn of document.querySelectorAll(".copy")) {
  btn.addEventListener("click", async () => {
    const text = btn.parentElement.querySelector("code").textContent;
    try { await navigator.clipboard.writeText(text); } catch { return; }
    const old = btn.textContent;
    btn.textContent = "✓";
    setTimeout(() => { btn.textContent = old; }, 1400);
  });
}

/* screenshot tabs */
const tabs = [...document.querySelectorAll("[role=tab]")];
function selectTab(tab) {
  for (const t of tabs) {
    const on = t === tab;
    t.setAttribute("aria-selected", String(on));
    t.tabIndex = on ? 0 : -1;
    document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
  }
}
tabs.forEach((t, i) => {
  t.addEventListener("click", () => selectTab(t));
  t.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
    selectTab(next); next.focus();
  });
});

/* benchmark bars grow when visible */
const chart = document.querySelector(".chart");
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
if (chart && !reduce && "IntersectionObserver" in window) {
  chart.classList.add("pre");
  new IntersectionObserver((entries, obs) => {
    if (entries.some((e) => e.isIntersecting)) { chart.classList.remove("pre"); obs.disconnect(); }
  }, { threshold: .35 }).observe(chart);
}

/* hero demo video: plays only while visible, never for reduced motion */
const demo = document.getElementById("demo");
document.getElementById("replay").addEventListener("click", () => { demo.currentTime = 0; demo.play(); });
if (reduce) {
  demo.controls = true;
} else if ("IntersectionObserver" in window) {
  new IntersectionObserver((entries) => {
    for (const e of entries) { if (e.isIntersecting) demo.play().catch(() => { demo.controls = true; }); else demo.pause(); }
  }, { threshold: .25 }).observe(demo);
} else {
  demo.controls = true;
}
