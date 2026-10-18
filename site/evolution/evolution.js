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
  "status.planned": "geplant",
  "status.running": "läuft",
  "status.passed": "bestanden",
  "status.failed": "fehlgeschlagen",
  "status.aborted": "abgebrochen",
  "status.invalid": "ungültig",
  "round.interventions": "Eingriffe",
  "round.reviews": "Prüfungen",
  "round.outOfScope": "Außerhalb des Umfangs",
  "round.breaches": "Isolationsverstöße",
  "round.share": "Anteil von Alia: {alia} von {total} geänderten Zeilen",
  "round.verified": "verifiziert",
  "round.notVerified": "nicht verifiziert",
  "before.title": "Vor der Self-Evolution",
  "before.text": "Zuvor schrieb Alia anhand menschlicher Prompts eine Architektur-Übersicht.",
  "before.link": "Architektur-Seite ansehen",
  "foot.note": "Lokaler Agent. Öffentliche Belege. Menschliche Freigabe.",
  "foot.back": "Hauptseite"
};

const nodes = [...document.querySelectorAll("[data-i18n]")];
const EN = Object.fromEntries(nodes.map((node) => [node.dataset.i18n, node.innerHTML]));
Object.assign(EN, {
  "status.planned": "planned", "status.running": "running", "status.passed": "passed",
  "status.failed": "failed", "status.aborted": "aborted", "status.invalid": "invalid",
  "round.interventions": "Interventions", "round.reviews": "Reviews",
  "round.outOfScope": "Out of scope", "round.breaches": "Isolation breaches",
  "round.share": "Alia's share: {alia} of {total} changed lines",
  "round.verified": "verified", "round.notVerified": "not verified"
});
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

function label(key) { return (language === "de" ? DE : EN)[key] ?? EN[key] ?? key; }

function addList(card, title, items, render) {
  if (!items?.length) return;
  const section = document.createElement("div");
  section.className = "round-detail";
  addText(section, "strong", title);
  const list = document.createElement("ul");
  for (const item of items) {
    const row = document.createElement("li");
    render(row, item);
    list.append(row);
  }
  section.append(list);
  card.append(section);
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
    addText(meta, "span", label(`status.${round.status}`), `round-status ${round.status}`);
    const result = round.result || {};
    const acceptance = result.acceptance_passed == null || result.acceptance_total == null
      ? "—" : `${result.acceptance_passed}/${result.acceptance_total}`;
    addText(meta, "span", `${language === "de" ? "Abnahme" : "Acceptance"} ${acceptance}`);
    if (round.run?.wall_seconds != null) addText(meta, "span", `${round.run.wall_seconds} s`);
    const attribution = round.attribution;
    const verified = attribution?.verified === true;
    addText(
      meta,
      "span",
      label(verified ? "round.verified" : "round.notVerified"),
      `attribution-badge ${verified ? "verified" : "not-verified"}`,
    );
    card.append(meta);
    if (attribution) {
      const total = attribution.alia_lines + attribution.other_lines;
      addText(
        card,
        "p",
        label("round.share").replace("{alia}", attribution.alia_lines).replace("{total}", total),
        "round-share",
      );
    }
    if (value(round.summary)) addText(card, "p", value(round.summary), "round-summary");
    addList(card, label("round.interventions"), round.interventions, (row, item) => {
      row.append(document.createTextNode(`${item.by}: ${item.what}`));
      if (item.commit) {
        const link = addText(row, "a", " ↗");
        link.href = `https://github.com/BEKO2210/alia/commit/${item.commit}`;
        link.setAttribute("aria-label", language === "de" ? "Eingriffs-Commit" : "Intervention commit");
      }
    });
    addList(card, label("round.reviews"), round.reviews, (row, item) => {
      row.textContent = `${item.by}: ${item.verdict}`;
    });
    addList(card, label("round.outOfScope"), result.out_of_scope_paths, (row, item) => { row.textContent = item; });
    addList(card, label("round.breaches"), result.isolation_breaches, (row, item) => { row.textContent = item; });
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
