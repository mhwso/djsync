// Rechte Spalte des Reviews: Detailansicht des ausgewählten Tracks mit Vorschlägen und
// Entscheidungs-Knöpfen.
//
// renderDetail(detail, actions, link) baut die Ansicht neu auf; Zustand hält index.js.
//   actions: { accept(id), openLink(), submitLink(text), cancelLink(), notOnSpotify(), skip(), reset() }
//   link:    { open, value, error } – Eingabe „Link einfügen“
//
// Anhören (#17): Der Platzhalter .review-player nimmt später den Player für die lokale Datei
// auf; je Vorschlag gibt es mit candidateExtras eine Stelle für einen Abspielknopf.

import { h } from "../../dom.js";
import { STATUS_LABELS, duration, percent, statusClass } from "./labels.js";

// Zusätzliche Knöpfe je Vorschlag (z. B. Abspielen, #17). Funktion (candidate) → Node[].
export const candidateExtras = [];

function fileFacts(d) {
  const row = (label, value) => [h("dt", {}, label), h("dd", {}, value ?? h("span", { class: "muted" }, "–"))];
  return h(
    "dl",
    { class: "review-facts" },
    row("Artist", d.artist),
    row("Titel", d.title),
    row("Dauer", d.duration_ms ? duration(d.duration_ms) : null),
    row("ISRC", d.isrc),
    row("Treffer-Status", h("span", { class: `badge ${statusClass(d)}` }, STATUS_LABELS[d.status] ?? d.status)),
  );
}

function candidateRow(c, actions) {
  return h(
    "tr",
    { class: "review-candidate" + (c.selected ? " selected" : "") },
    h("td", {}, c.number <= 5 ? h("kbd", {}, String(c.number)) : null),
    h(
      "td",
      { class: "review-candidate-main" },
      h("div", { class: "review-candidate-title" }, c.name, c.selected ? h("span", { class: "badge ok" }, "Zugeordnet") : null),
      h("div", { class: "muted" }, c.artists.join(", "), c.album ? ` · ${c.album}` : ""),
    ),
    h(
      "td",
      { class: "num" + (c.duration_ok ? "" : " review-duration-off"), title: c.duration_ok ? null : "Dauer weicht ab" },
      duration(c.duration_ms),
    ),
    h("td", { class: "num" }, percent(c.score)),
    h(
      "td",
      { class: "review-candidate-actions" },
      candidateExtras.flatMap((extra) => extra(c)),
      h("a", { class: "button", href: c.url, target: "_blank", title: "In Spotify öffnen" }, "Spotify"),
      h("button", { class: "button primary", onclick: () => actions.accept(c.id) }, "Übernehmen"),
    ),
  );
}

function candidates(d, actions) {
  if (d.candidates.length === 0) {
    return h("p", { class: "muted" }, "Keine Vorschläge. Ordne den Track per Link zu oder markiere ihn als „nicht auf Spotify“.");
  }
  return h(
    "table",
    { class: "review-candidates" },
    h(
      "thead",
      {},
      h("tr", {}, h("th", {}, ""), h("th", {}, "Vorschlag"), h("th", { class: "num" }, "Dauer"), h("th", { class: "num" }, "Bewertung"), h("th", {}, "")),
    ),
    h("tbody", {}, d.candidates.map((c) => candidateRow(c, actions))),
  );
}

function linkForm(link, actions) {
  const input = h("input", {
    class: "review-link-input",
    type: "text",
    placeholder: "https://open.spotify.com/track/…",
    "aria-label": "Spotify-Link",
    value: link.value ?? "",
    onkeydown: (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        actions.cancelLink();
      }
    },
  });
  const form = h(
    "form",
    {
      class: "review-link",
      onsubmit: (e) => {
        e.preventDefault();
        actions.submitLink(input.value);
      },
    },
    input,
    h("button", { class: "button primary", type: "submit" }, "Zuordnen"),
    h("button", { class: "button", type: "button", onclick: actions.cancelLink }, "Abbrechen"),
    link.error ? h("p", { class: "notice error review-link-error", role: "alert" }, link.error) : null,
  );
  // Nach dem Einhängen fokussieren
  queueMicrotask(() => input.focus());
  return form;
}

function decisionBar(d, actions) {
  return h(
    "div",
    { class: "review-actions" },
    h("button", { class: "button", onclick: actions.openLink }, "Link einfügen ", h("kbd", {}, "l")),
    h("button", { class: "button", onclick: actions.notOnSpotify }, "Nicht auf Spotify ", h("kbd", {}, "n")),
    h("button", { class: "button", onclick: actions.skip }, "Überspringen ", h("kbd", {}, "s")),
    d.decided ? h("button", { class: "button", onclick: actions.reset }, "Auf „offen“ zurücksetzen ", h("kbd", {}, "r")) : null,
  );
}

export function renderDetail(d, actions, link) {
  return h(
    "article",
    { class: "review-detail-body" },
    h("h2", { class: "review-filename", title: d.path }, d.filename),
    fileFacts(d),
    h("section", { class: "review-player", "aria-label": "Anhören" }),
    h("h3", {}, "Vorschläge"),
    candidates(d, actions),
    link.open ? linkForm(link, actions) : null,
    decisionBar(d, actions),
  );
}

export function renderDone(onLeave) {
  return h(
    "div",
    { class: "empty" },
    h("strong", {}, "Nichts mehr offen"),
    "Alle Tracks dieses Ordners sind geprüft. Die Entscheidungen landen mit dem nächsten bestätigten Sync in der Playlist.",
    h("p", {}, h("button", { class: "button primary", onclick: onLeave }, "Zurück zu den Ordnern")),
  );
}
