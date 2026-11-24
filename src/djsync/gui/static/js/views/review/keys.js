// Tastenkürzel des Reviews und ihre Übersicht.
//
// Jedes Kürzel ist ein Eintrag { keys, label, run(ctx, event) }; die Übersicht (Taste ?) wird
// aus derselben Liste erzeugt. Optional: `shift: true|false` verlangt (bzw. verbietet) die
// Umschalttaste, `ctrl: true` verlangt Strg (bzw. Cmd) – sonst greifen Kürzel mit Strg/Alt
// nicht. Weitere Kürzel mit addShortcuts([...]) ergänzen – möglichst ohne bestehende Tasten zu überschreiben.

import { h } from "../../dom.js";

const shortcuts = [
  { keys: ["Umschalt+↓"], match: ["ArrowDown"], shift: true, label: "Auswahl nach unten erweitern", run: (c) => c.extend(1) },
  { keys: ["Umschalt+↑"], match: ["ArrowUp"], shift: true, label: "Auswahl nach oben erweitern", run: (c) => c.extend(-1) },
  { keys: ["Strg+A"], match: ["a", "A"], ctrl: true, label: "Alle Tracks der Liste auswählen", run: (c) => c.selectAll() },
  { keys: ["↓", "j"], match: ["ArrowDown", "j"], label: "Nächster Track in der Liste", run: (c) => c.move(1) },
  { keys: ["↑", "k"], match: ["ArrowUp", "k"], label: "Vorheriger Track in der Liste", run: (c) => c.move(-1) },
  { keys: ["Pos1", "Ende"], match: ["Home", "End"], label: "Erster / letzter Track", run: (c, e) => c.move(e.key === "Home" ? -Infinity : Infinity) },
  { keys: ["1–5"], match: ["1", "2", "3", "4", "5"], label: "Vorschlag übernehmen", run: (c, e) => c.acceptNumber(Number(e.key)) },
  { keys: ["l"], match: ["l"], label: "Spotify-Link einfügen", run: (c) => c.openLink() },
  { keys: ["n"], match: ["n"], label: "Nicht auf Spotify (auch für alle ausgewählten)", run: (c) => c.notOnSpotify() },
  { keys: ["e"], match: ["e"], label: "Erneut suchen (offene ausgewählte Tracks)", run: (c) => c.searchAgain() },
  { keys: ["s"], match: ["s"], label: "Überspringen (nächster offener Track)", run: (c) => c.skip() },
  { keys: ["r"], match: ["r"], label: "Entschiedenen Track auf „offen“ zurücksetzen", run: (c) => c.reset() },
  { keys: ["f"], match: ["f"], label: "Filter wechseln (offen, ungefähr, nicht gefunden, entschieden, exakt)", run: (c) => c.nextFilter() },
  { keys: ["Leertaste"], match: [" "], label: "Abspielen / pausieren", run: (c) => c.togglePlay() },
  { keys: ["a"], match: ["a"], label: "A/B: lokale Datei ↔ Vorschlag an derselben Position", run: (c) => c.toggleAB() },
  { keys: ["v"], match: ["v"], label: "Nächsten Vorschlag zum Vergleich wählen", run: (c) => c.cycleCandidate(1) },
  { keys: ["Umschalt+V"], match: ["V"], shift: true, label: "Vorherigen Vorschlag zum Vergleich wählen", run: (c) => c.cycleCandidate(-1) },
  { keys: ["→", "←"], match: ["ArrowRight", "ArrowLeft"], label: "Um die Sprungweite vor- / zurückspringen", run: (c, e) => c.skipPlay(e.key === "ArrowRight" ? 1 : -1) },
  { keys: ["Esc"], match: ["Escape"], label: "Mehrfachauswahl aufheben", run: (c) => c.clearSelection() },
  { keys: ["?"], match: ["?"], label: "Diese Übersicht", run: (c) => c.toggleHelp() },
  { keys: ["q"], match: ["q"], label: "Review verlassen", run: (c) => c.leave() },
];

export function addShortcuts(entries) {
  shortcuts.push(...entries);
}

// Tastendruck → Kürzel ausführen. Gibt true zurück, wenn er verarbeitet wurde.
// In Eingabefeldern (Link) greifen die Kürzel nicht.
export function handleKey(event, ctx) {
  if (event.altKey) return false;
  const ctrl = event.ctrlKey || event.metaKey;
  const target = event.target;
  if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return false;
  const fits = (s) => s.match.includes(event.key) && Boolean(s.ctrl) === ctrl;
  // Kürzel mit ausdrücklicher Umschalttaste haben Vorrang (Umschalt+↓ vor ↓)
  const entry =
    shortcuts.find((s) => fits(s) && s.shift === event.shiftKey) ?? shortcuts.find((s) => fits(s) && s.shift === undefined);
  if (!entry) return false;
  event.preventDefault();
  entry.run(ctx, event);
  return true;
}

export function helpDialog() {
  const dialog = h(
    "dialog",
    { class: "review-help", "aria-label": "Tastenkürzel" },
    h("h2", {}, "Tastenkürzel im Review"),
    h(
      "dl",
      {},
      shortcuts.flatMap((s) => [h("dt", {}, s.keys.map((k) => h("kbd", {}, k))), h("dd", {}, s.label)]),
    ),
    h("form", { method: "dialog" }, h("button", { class: "button primary" }, "Schließen")),
  );
  return dialog;
}
