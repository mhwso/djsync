// Rechte Spalte bei Mehrfachauswahl: Massenoperationen für alle ausgewählten Tracks.
//
// renderBulk(tracks, actions, progress) baut die Ansicht neu auf; Zustand hält index.js.
//   tracks:   Listeneinträge der ausgewählten Tracks (aus review.tracks)
//   actions:  { notOnSpotify(), searchAgain(), cancelSearch(), clearSelection() }
//   progress: null oder { done, total } während „erneut suchen“ läuft

import { h } from "../../dom.js";
import { plural } from "../../format.js";

export function renderBulk(tracks, actions, progress) {
  const open = tracks.filter((t) => t.open).length;
  const body = [
    h("h2", { class: "review-filename" }, plural(tracks.length, "Track ausgewählt", "Tracks ausgewählt")),
    h(
      "p",
      { class: "muted" },
      open === tracks.length
        ? "Alle ausgewählten Tracks sind offen."
        : `Davon ${plural(open, "offener Track", "offene Tracks")}. „Erneut suchen“ überspringt entschiedene und exakte Tracks.`,
    ),
  ];
  if (progress) {
    body.push(
      h(
        "div",
        { class: "review-bulk-progress" },
        h("progress", { max: progress.total || 1, value: progress.done }),
        h("span", { class: "muted" }, progress.total ? `${progress.done} von ${progress.total} gesucht` : "Suche startet …"),
        h("button", { class: "button", onclick: () => actions.cancelSearch() }, "Abbrechen"),
      ),
    );
  } else {
    body.push(
      h(
        "div",
        { class: "review-actions" },
        h("button", { class: "button", title: "Alle ausgewählten als „nicht auf Spotify“ markieren (n)", onclick: () => actions.notOnSpotify() }, "Nicht auf Spotify"),
        h(
          "button",
          { class: "button", title: "Offene ausgewählte Tracks erneut auf Spotify suchen (e)", disabled: open === 0, onclick: () => actions.searchAgain() },
          "Erneut suchen",
        ),
        h("button", { class: "button", title: "Nur den aktuellen Track auswählen (Esc)", onclick: () => actions.clearSelection() }, "Auswahl aufheben"),
      ),
    );
  }
  return h("div", { class: "review-detail-body review-bulk" }, body);
}

// Ergebnis einer Massenoperation als Satz, z. B. „2 Tracks bearbeitet, 1 übersprungen.“
export function bulkSummary(result) {
  const text = `${plural(result.done, "Track bearbeitet", "Tracks bearbeitet")}, ${result.skipped} übersprungen.`;
  return result.cancelled ? `Suche abgebrochen. ${text}` : text;
}
