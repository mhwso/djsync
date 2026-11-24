// Anzeige-Texte und Formatierung für das Review (Begriffe aus GLOSSARY.md).

export const STATUS_LABELS = {
  exact: "Exakt",
  approximate: "Ungefähr",
  manual: "Manuell",
  not_found: "Nicht gefunden",
  not_on_spotify: "Nicht auf Spotify",
};

export const FILTERS = [
  { id: "open", label: "Offen" },
  { id: "decided", label: "Entschieden" },
  { id: "exact", label: "Exakt" },
];

// Badge-Klasse je Treffer-Status (Farben aus base.css)
export function statusClass(track) {
  if (track.open) return "open";
  if (track.decided) return "decided";
  return "ok";
}

// 225000 → „3:45“, unbekannt → „–:––“
export function duration(ms) {
  if (!ms) return "–:––";
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// 0.8731 → „87 %“
export function percent(score) {
  return `${Math.round(score * 100)} %`;
}
