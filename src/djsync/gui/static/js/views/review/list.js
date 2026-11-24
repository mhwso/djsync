// Linke Spalte des Reviews: Filter und Track-Liste.
//
// Die Liste kennt nur Darstellung und Klicks; was eine Auswahl bedeutet, entscheidet die
// Ansicht (index.js) über onClick(fingerprint, event) – mit Umschalt/Strg im event für die
// Mehrfachauswahl. `selected` ist die Menge ausgewählter Fingerprints, `cursor` der Track,
// auf dem die Tastatur gerade steht.

import { h } from "../../dom.js";
import { FILTERS, STATUS_LABELS, statusClass } from "./labels.js";

export function renderFilters(current, onFilter) {
  return h(
    "div",
    { class: "review-filters", role: "tablist", "aria-label": "Filter" },
    FILTERS.map((f) =>
      h(
        "button",
        {
          class: "review-filter" + (f.id === current ? " active" : ""),
          role: "tab",
          "aria-selected": f.id === current ? "true" : "false",
          onclick: () => onFilter(f.id),
        },
        f.label,
      ),
    ),
  );
}

function trackLabel(t) {
  if (t.artist || t.title) return `${t.artist ?? "?"} – ${t.title ?? "?"}`;
  return t.filename;
}

export function renderList(tracks, selected, cursor, onClick) {
  if (tracks.length === 0) {
    return h("p", { class: "review-list-empty muted" }, "Keine Tracks für diesen Filter.");
  }
  return h(
    "ul",
    { class: "review-list", role: "listbox", "aria-label": "Tracks", "aria-multiselectable": "true" },
    tracks.map((t) =>
      h(
        "li",
        {
          class:
            "review-item" +
            (selected.has(t.fingerprint) ? " selected" : "") +
            (t.fingerprint === cursor ? " cursor" : "") +
            (t.decided ? " decided" : ""),
          role: "option",
          "aria-selected": selected.has(t.fingerprint) ? "true" : "false",
          "data-fingerprint": t.fingerprint,
          title: t.filename,
          onclick: (event) => onClick(t.fingerprint, event),
        },
        h("span", { class: "review-item-name" }, trackLabel(t)),
        h("span", { class: `badge ${statusClass(t)}` }, t.decided ? "✓ " : "", STATUS_LABELS[t.status] ?? t.status),
      ),
    ),
  );
}
