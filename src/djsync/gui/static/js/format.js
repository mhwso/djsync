// Formatierung für die Anzeige (deutsch).

const dateTime = new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeStyle: "short" });
const relative = new Intl.RelativeTimeFormat("de-DE", { numeric: "auto" });

const STEPS = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

// ISO-Zeitpunkt → „vor 3 Tagen“ (relativ) bzw. „24.11.2026, 14:03“ (absolut, für title)
export function relativeTime(iso, now = Date.now()) {
  const seconds = (new Date(iso).getTime() - now) / 1000;
  for (const [unit, size] of STEPS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "gerade eben";
}

export function absoluteTime(iso) {
  return dateTime.format(new Date(iso));
}

// 1 → „1 offener Track“, 3 → „3 offene Tracks“
export function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}
