// Einstellungen: alle Werte aus config.toml, die CLI liest dieselbe Datei.
// Ungültige Werte meldet die API (settings.save), gespeichert wird dann nichts.

import { api, errorMessage } from "../api.js";
import { h } from "../dom.js";

// Schlüssel, Beschriftung, Hilfetext, Eingabe-Attribute
const FIELDS = [
  ["extensions", "Dateiendungen", "Welche Dateien zum Ordner gehören, durch Leerzeichen oder Komma getrennt.", { type: "text" }],
  ["duration_tolerance_s", "Toleranz der Dauer", "Sekunden, um die ein Vorschlag von der Datei abweichen darf.", { type: "number", min: 0, max: 60, step: "any" }],
  ["min_score", "Mindestbewertung", "Ab dieser Bewertung (0 bis 1) gilt ein Vorschlag als ungefährer Treffer.", { type: "number", min: 0, max: 1, step: "any" }],
  ["retry_missing_days", "Tage bis zur erneuten Suche", "Nach so vielen Tagen werden nicht gefundene Tracks beim Sync erneut gesucht.", { type: "number", min: 0, step: 1 }],
  ["review_candidates", "Anzahl der Vorschläge", "Wie viele Vorschläge pro Track gespeichert und im Review gezeigt werden.", { type: "number", min: 1, max: 20, step: 1 }],
  ["start_position_s", "Startstelle", "Sekunde, an der das Anhören im Review beginnt.", { type: "number", min: 0, max: 3600, step: 1 }],
  ["skip_s", "Sprungweite", "Sekunden, um die per Taste vorgesprungen wird.", { type: "number", min: 1, max: 600, step: 1 }],
];

function fieldValue(key, value) {
  return key === "extensions" ? value.join(" ") : String(value);
}

export default {
  title: "Einstellungen",

  async render(root) {
    const body = h("div", { class: "view-body" }, h("p", { class: "muted" }, "Lade Einstellungen …"));
    root.append(h("div", { class: "view-head" }, h("h1", {}, "Einstellungen")), body);

    let settings;
    try {
      settings = await api("settings.get");
    } catch (err) {
      body.replaceChildren(h("p", { class: "notice error" }, errorMessage(err)));
      return;
    }

    const inputs = {};
    const status = h("p", { class: "settings-status", role: "status" });
    const rows = FIELDS.map(([key, label, help, attrs]) => {
      const id = `setting-${key}`;
      inputs[key] = h("input", { id, name: key, ...attrs, value: fieldValue(key, settings[key]) });
      return h(
        "div",
        { class: "settings-field" },
        h("label", { for: id }, label),
        inputs[key],
        h("p", { class: "muted settings-help" }, help),
      );
    });

    const form = h(
      "form",
      { class: "settings-form", novalidate: true },
      rows,
      h("div", { class: "settings-actions" }, status, h("button", { type: "submit", class: "button primary" }, "Speichern")),
    );

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const values = Object.fromEntries(Object.entries(inputs).map(([key, input]) => [key, input.value]));
      status.className = "settings-status";
      status.textContent = "Speichere …";
      try {
        const saved = await api("settings.save", values);
        for (const [key, input] of Object.entries(inputs)) input.value = fieldValue(key, saved[key]);
        status.textContent = "Gespeichert.";
      } catch (err) {
        status.className = "settings-status error";
        status.textContent = errorMessage(err);
      }
    });

    body.replaceChildren(form);
  },
};
