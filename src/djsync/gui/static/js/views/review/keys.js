// Tastenkürzel des Reviews und ihre Übersicht.
//
// Jedes Kürzel ist ein Eintrag { keys, label, run(ctx, event) }; die Übersicht (Taste ?) wird
// aus derselben Liste erzeugt. Weitere Kürzel (z. B. Anhören #17, Mehrfachauswahl #15) mit
// addShortcuts([...]) ergänzen – möglichst ohne bestehende Tasten zu überschreiben.

import { h } from "../../dom.js";

const shortcuts = [
  { keys: ["↓", "j"], match: ["ArrowDown", "j"], label: "Nächster Track in der Liste", run: (c) => c.move(1) },
  { keys: ["↑", "k"], match: ["ArrowUp", "k"], label: "Vorheriger Track in der Liste", run: (c) => c.move(-1) },
  { keys: ["Pos1", "Ende"], match: ["Home", "End"], label: "Erster / letzter Track", run: (c, e) => c.move(e.key === "Home" ? -Infinity : Infinity) },
  { keys: ["1–5"], match: ["1", "2", "3", "4", "5"], label: "Vorschlag übernehmen", run: (c, e) => c.acceptNumber(Number(e.key)) },
  { keys: ["l"], match: ["l"], label: "Spotify-Link einfügen", run: (c) => c.openLink() },
  { keys: ["n"], match: ["n"], label: "Nicht auf Spotify", run: (c) => c.notOnSpotify() },
  { keys: ["s"], match: ["s"], label: "Überspringen (nächster offener Track)", run: (c) => c.skip() },
  { keys: ["r"], match: ["r"], label: "Entschiedenen Track auf „offen“ zurücksetzen", run: (c) => c.reset() },
  { keys: ["f"], match: ["f"], label: "Filter wechseln (offen, entschieden, exakt)", run: (c) => c.nextFilter() },
  { keys: ["Leertaste"], match: [" "], label: "Lokale Datei abspielen / pausieren", run: (c) => c.togglePlay() },
  { keys: ["→", "←"], match: ["ArrowRight", "ArrowLeft"], label: "Um die Sprungweite vor- / zurückspringen", run: (c, e) => c.skipPlay(e.key === "ArrowRight" ? 1 : -1) },
  { keys: ["?"], match: ["?"], label: "Diese Übersicht", run: (c) => c.toggleHelp() },
  { keys: ["q"], match: ["q"], label: "Review verlassen", run: (c) => c.leave() },
];

export function addShortcuts(entries) {
  shortcuts.push(...entries);
}

// Tastendruck → Kürzel ausführen. Gibt true zurück, wenn er verarbeitet wurde.
// In Eingabefeldern (Link) greifen die Kürzel nicht.
export function handleKey(event, ctx) {
  if (event.ctrlKey || event.metaKey || event.altKey) return false;
  const target = event.target;
  if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return false;
  const entry = shortcuts.find((s) => s.match.includes(event.key));
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
