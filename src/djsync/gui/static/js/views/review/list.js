// Linke Spalte des Reviews: Filter und Track-Liste.
//
// Die Liste kennt nur Darstellung und Klicks; was eine Auswahl bedeutet, entscheidet die
// Ansicht (index.js) über onSelect. Mehrfachauswahl (#15) setzt hier an: renderList bekommt
// dann eine Menge ausgewählter Fingerprints statt eines einzelnen.

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

export function renderList(tracks, selected, onSelect) {
  if (tracks.length === 0) {
    return h("p", { class: "review-list-empty muted" }, "Keine Tracks für diesen Filter.");
  }
  return h(
    "ul",
    { class: "review-list", role: "listbox", "aria-label": "Tracks" },
    tracks.map((t) =>
      h(
        "li",
        {
          class: "review-item" + (t.fingerprint === selected ? " selected" : "") + (t.decided ? " decided" : ""),
          role: "option",
          "aria-selected": t.fingerprint === selected ? "true" : "false",
          "data-fingerprint": t.fingerprint,
          title: t.filename,
          onclick: () => onSelect(t.fingerprint),
        },
        h("span", { class: "review-item-name" }, trackLabel(t)),
        h("span", { class: `badge ${statusClass(t)}` }, t.decided ? "✓ " : "", STATUS_LABELS[t.status] ?? t.status),
      ),
    ),
  );
}
