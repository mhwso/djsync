// Brücke zur Python-API-Schicht (djsync/gui/api).
//
//   import { api, on } from "./api.js";
//   const folders = await api("folders.list");
//   const aus = on("sync.progress", (daten) => { … });  // aus() meldet wieder ab
//
// Fehler der API kommen als abgelehntes Promise mit { name, message }; bei name === "ApiError"
// ist message eine anzeigbare deutsche Meldung.

const ready = new Promise((resolve) => {
  if (window.pywebview && window.pywebview.api) resolve();
  else window.addEventListener("pywebviewready", () => resolve(), { once: true });
});

export async function api(path, ...args) {
  await ready;
  let target = window.pywebview.api;
  const parts = path.split(".");
  const method = parts.pop();
  for (const part of parts) target = target?.[part];
  if (typeof target?.[method] !== "function") {
    throw { name: "Error", message: `Unbekannte API-Methode: ${path}` };
  }
  return target[method](...args);
}

// ---- Events von Python (djsync/gui/events.py) --------------------------------

const listeners = new Map();

export function on(name, fn) {
  if (!listeners.has(name)) listeners.set(name, new Set());
  listeners.get(name).add(fn);
  return () => listeners.get(name)?.delete(fn);
}

function emit(name, data) {
  for (const fn of listeners.get(name) ?? []) {
    try {
      fn(data);
    } catch (e) {
      console.error(e);
    }
  }
}

// Python ruft window.djsync.emit(name, daten) per evaluate_js auf
window.djsync = { emit };

export function errorMessage(err) {
  if (err && err.name === "ApiError") return err.message;
  return "Unerwarteter Fehler: " + (err?.message ?? String(err));
}
