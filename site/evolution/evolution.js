"use strict";

const DE = {
  "skip": "Zum Inhalt springen",
  "nav.back": "Zurück zu Alia",
  "hero.eyebrow": "Öffentlich entwickelt",
  "hero.title": "Alia Self-Evolution",
  "hero.lead": "Alia, der lokale Agent, verbessert diese Website selbst in kleinen, nummerierten Runden.",
  "rules.eyebrow": "Die Regeln",
  "rules.title": "Gemessene Arbeit unter menschlicher Kontrolle.",
  "rules.frozen": "Aufgabe und Abnahmetests werden vor dem Lauf eingefroren.",
  "rules.isolated": "Alia arbeitet allein in einer isolierten Kopie.",
  "rules.failed": "Fehlgeschlagene Runden bleiben sichtbar.",
  "rules.review": "Jede Änderung wird von einem Menschen geprüft und zusammengeführt.",
  "rules.private": "Vollständige Transkripte bleiben privat; hier stehen nur öffentliche Zusammenfassungen.",
  "rounds.eyebrow": "Rundenprotokoll",
  "rounds.title": "Ergebnisse",
  "rounds.empty": "Noch keine Runde abgeschlossen. Runde 1 kommt als Nächstes.",
  "before.title": "Vor der Self-Evolution",
  "before.text": "Zuvor schrieb Alia anhand menschlicher Prompts eine Architektur-Übersicht.",
  "before.link": "Architektur-Seite ansehen",
  "foot.note": "Lokaler Agent. Öffentliche Belege. Menschliche Freigabe.",
  "foot.back": "Hauptseite"
};

const nodes = [...document.querySelectorAll("[data-i18n]")];
const EN = Object.fromEntries(nodes.map((node) => [node.dataset.i18n, node.innerHTML]));
let language = "en";
let roundData = [];

function storage(fn) { try { return fn(); } catch { return null; } }

function setLang(lang) {
  language = lang;
  const dictionary = lang === "de" ? DE : EN;
  for (const node of nodes) node.innerHTML = dictionary[node.dataset.i18n] ?? EN[node.dataset.i18n];
  document.documentElement.lang = lang;
  for (const button of document.querySelectorAll("[data-lang]")) {
    button.setAttribute("aria-pressed", String(button.dataset.lang === lang));
  }
  storage(() => localStorage.setItem("alia-lang", lang));
  renderRounds();
}

function value(valueByLanguage) {
  return valueByLanguage?.[language] ?? valueByLanguage?.en ?? "";
}

function addText(parent, tag, text, className) {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  parent.append(element);
  return element;
}

function renderRounds() {
  const root = document.getElementById("rounds");
  if (!roundData.length) return;
  root.replaceChildren();
  for (const round of roundData) {
    const card = document.createElement("article");
    card.className = "round-card";
    addText(card, "h3", `${language === "de" ? "Runde" : "Round"} ${round.round}: ${value(round.title)}`);
    const meta = document.createElement("div");
    meta.className = "round-meta";
    addText(meta, "span", `${language === "de" ? "Stufe" : "Level"} ${round.level}`);
    addText(meta, "span", round.status, `round-status ${round.status}`);
    const result = round.result || {};
    const acceptance = result.acceptance_passed == null || result.acceptance_total == null
      ? "—" : `${result.acceptance_passed}/${result.acceptance_total}`;
    addText(meta, "span", `${language === "de" ? "Abnahme" : "Acceptance"} ${acceptance}`);
    if (round.run?.wall_seconds != null) addText(meta, "span", `${round.run.wall_seconds} s`);
    card.append(meta);
    if (round.agent_commit) {
      const link = addText(card, "a", language === "de" ? "Commit ansehen" : "View commit");
      link.href = `https://github.com/BEKO2210/alia/commit/${round.agent_commit}`;
    }
    root.append(card);
  }
}

for (const button of document.querySelectorAll("[data-lang]")) button.addEventListener("click", () => setLang(button.dataset.lang));
const saved = storage(() => localStorage.getItem("alia-lang"));
setLang(saved || ((navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en"));

fetch("data/rounds.json")
  .then((response) => {
    if (!response.ok) throw new Error(`round data request failed: ${response.status}`);
    return response.json();
  })
  .then((rounds) => { roundData = Array.isArray(rounds) ? rounds : []; renderRounds(); })
  .catch((error) => console.error(error));
