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
  "term.caption": "Eine echte Sitzung auf einer RTX 3070, im Browser abgespielt. Die Selbstkorrektur des Modells (python → python3) ist ungeschnitten; die Ladezeit läuft schneller als in echt.",
  "stat.tg": "Ausgabe bei 32K Kontext mit einem 35B-MoE-Modell",
  "stat.vram": "VRAM reichen: die Experten kommen aus dem Arbeitsspeicher",
  "stat.code": "Coding\u2011Aufgaben bestanden, per Unit-Test geprüft",
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
  "f4.d": "Basiert auf Qwen Code: bearbeitet Dateien, führt Befehle aus, liest Fehler und behebt sie. Fragt vor jeder Aktion, außer du wählst <code>--auto-edit</code> oder <code>--yolo</code>.",
  "f5.t": "Terminal oder Browser",
  "f5.d": "<code>alia web</code> öffnet denselben Agenten als Web-Shell, nur auf 127.0.0.1.",
  "f6.t": "Belege statt Behauptungen",
  "f6.d": "Jede Zahl auf dieser Seite verweist auf JSONL-Rohdaten und die exakten llama.cpp-Flags dazu.",
  "bench.eyebrow": "Messwerte",
  "bench.title": "Gemessen, nicht geschätzt.",
  "bench.sub": "Ausgabetempo, während sich der Kontext füllt. RTX 3070 8 GB, Ryzen 7 5800X, 16 GB RAM, llama.cpp a0e6dc7.",
  "bench.default": "Standard",
  "bench.fast": "schnell",
  "bench.d4": "4K Kontext",
  "bench.d32": "32K Kontext",
  "bench.d60": "60K Kontext",
  "bench.na": "9B-Profil endet bei 32K",
  "q.code": "Code-Aufgaben",
  "q.tools": "Tool-Aufrufe",
  "q.json": "JSON-Schema",
  "q.pp": "Prompt-Tempo 4K / 32K",
  "q.dl": "Download",
  "bench.fine": "Die Punkte bei 4K und 32K stammen aus Läufen mit Server-Kontext 33.792, der 60K-Punkt mit Kontext 65.536 – so startet das Standardprofil. Die Qualität wurde separat bei 32K bewertet. <a href=\"https://github.com/BEKO2210/alia/tree/main/bench/results\">Rohdaten und Methodik →</a>",
  "shots.eyebrow": "Im Einsatz",
  "shots.title": "Dein Terminal. Oder dein Browser.",
  "shots.term": "Terminal",
  "shots.web": "Web-Shell",
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
  "inst.s4": "Starten",
  "inst.note": "Der erste Start zeigt den genauen Modell-Download (14,07 GB beim Standardprofil) und fragt, bevor etwas geladen wird.",
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

/* terminal replay */
const body = document.getElementById("term-body");
const steps = [...body.querySelectorAll("[data-step]")];
const SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏";
let run = 0;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function finalState() {
  for (const s of steps) s.classList.add("show");
  for (const t of body.querySelectorAll(".typed")) t.textContent = t.dataset.text;
  const load = body.querySelector("[data-step=load]");
  load.querySelector(".spin").textContent = "✓";
  load.querySelector(".spin").className = "ok";
  load.querySelector(".bar").textContent = "██████████";
  load.querySelector(".secs").textContent = "24 s";
  load.hidden = true;
}

async function play() {
  const id = ++run;
  const alive = () => id === run;
  for (const s of steps) s.classList.remove("show");
  for (const t of body.querySelectorAll(".typed")) { t.textContent = ""; t.classList.remove("typing"); }
  const load = body.querySelector("[data-step=load]");
  load.hidden = false;
  const spin = load.querySelector(".spin, .ok");
  spin.className = "spin";
  await sleep(500);
  for (const s of steps) {
    if (!alive()) return;
    const typed = s.querySelector(".typed");
    s.classList.add("show");
    if (typed) {
      typed.classList.add("typing");
      await sleep(350);
      for (const ch of typed.dataset.text) {
        if (!alive()) return;
        typed.textContent += ch;
        await sleep(typed.dataset.text.length > 20 ? 22 : 90);
      }
      await sleep(450);
      typed.classList.remove("typing");
    } else if (s.dataset.step === "load") {
      for (let sec = 0; sec <= 24; sec++) {
        if (!alive()) return;
        spin.textContent = SPIN[sec % SPIN.length];
        const filled = Math.min(10, Math.floor(sec / 2.4));
        s.querySelector(".bar").textContent = "█".repeat(filled) + "░".repeat(10 - filled);
        s.querySelector(".secs").textContent = sec + " s";
        await sleep(70);
      }
      s.hidden = true;
      continue;
    } else {
      await sleep(s.classList.contains("banner") ? 500 : s.classList.contains("ind") ? 260 : 380);
    }
  }
}

document.getElementById("replay").addEventListener("click", () => play());
if (reduce) {
  finalState();
} else if ("IntersectionObserver" in window) {
  new IntersectionObserver((entries, obs) => {
    if (entries.some((e) => e.isIntersecting)) { obs.disconnect(); play(); }
  }, { threshold: .25 }).observe(body);
} else {
  finalState();
}
