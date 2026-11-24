// Eingebetteter Spotify-Player (Embed-iframe), gesteuert über die iFrame-API (ADR 0003).
//
//   const embed = createEmbed(container);   // container: leeres Element, sichtbar im DOM
//   await embed.load("spotify:track:…");      // legt den Player beim ersten Mal an
//   embed.play(); embed.pause(); embed.seek(60);
//   embed.state  → { uri, paused, position, duration } (Sekunden, duration NaN solange unbekannt)
//   const off = embed.subscribe(() => …);     // bei jeder Änderung
//   embed.destroy();
//
// Ohne Anmeldung im Player spielt Spotify nur eine 30-Sekunden-Vorschau; isPreview() erkennt
// das an der gemeldeten Dauer. Ein iframe lädt neu, wenn es im DOM verschoben wird – der
// Container darf deshalb beim Neuzeichnen nicht umgehängt werden.

const API_URL = "https://open.spotify.com/embed/iframe-api/v1";
const PREVIEW_MAX_S = 31; // Vorschauen sind 30 s lang
const CREATE_TIMEOUT_MS = 8000; // erstes Laden: iframe und Spotify-Skripte
const LOAD_TIMEOUT_MS = 1500; // ob nach loadUri immer „ready“ kommt, ist nicht dokumentiert
const START_TIMEOUT_MS = 6000;

let iframeApi = null; // Promise des IFrameAPI-Objekts, wird nur einmal geladen

function loadIframeApi() {
  iframeApi ??= new Promise((resolve, reject) => {
    window.onSpotifyIframeApiReady = resolve;
    const script = document.createElement("script");
    script.src = API_URL;
    script.async = true;
    script.onerror = () => {
      iframeApi = null; // erneuter Versuch beim nächsten Mal
      reject({ name: "ApiError", message: "Der Spotify-Player lässt sich nicht laden. Besteht eine Internetverbindung?" });
    };
    document.head.append(script);
  });
  return iframeApi;
}

// Spielt der Player nur eine Vorschau? expectedMs: echte Dauer des Tracks, falls bekannt
export function isPreview(durationS, expectedMs) {
  if (!Number.isFinite(durationS) || durationS <= 0) return false;
  return durationS <= PREVIEW_MAX_S && (expectedMs == null || expectedMs > (PREVIEW_MAX_S + 4) * 1000);
}

// Wartet, bis check() wahr ist (bei jeder Änderung geprüft), höchstens timeoutMs
function waitFor(subscribe, check, timeoutMs) {
  return new Promise((resolve) => {
    if (check()) return resolve(true);
    const timer = setTimeout(() => done(false), timeoutMs);
    const off = subscribe(() => check() && done(true));
    function done(ok) {
      clearTimeout(timer);
      off();
      resolve(ok);
    }
  });
}

export function createEmbed(container, { height = 80 } = {}) {
  let controller = null;
  let creating = null;
  let loaded = null; // URI im Player
  let startedUri = null; // URI, die seit dem Laden schon gespielt hat (dann resume statt play)
  let updatedAt = 0;
  let signals = 0; // zählt „ready“ und Positionsmeldungen – Zeichen, dass der Player reagiert
  const raw = { paused: true, position: 0, duration: NaN };
  const listeners = new Set();

  function notify() {
    for (const fn of listeners) fn();
  }

  function subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  function onUpdate(e) {
    const d = e.data ?? {};
    raw.paused = Boolean(d.isPaused);
    raw.position = (d.position ?? 0) / 1000;
    raw.duration = d.duration ? d.duration / 1000 : NaN;
    updatedAt = performance.now();
    signals++;
    notify();
  }

  async function create(uri) {
    const api = await loadIframeApi();
    const target = document.createElement("div"); // wird durch das iframe ersetzt
    container.replaceChildren(target);
    await new Promise((resolve) => {
      api.createController(target, { uri, width: "100%", height }, (c) => {
        controller = c;
        c.addListener("playback_update", onUpdate);
        c.addListener("ready", () => {
          signals++;
          notify();
        });
        resolve();
      });
    });
  }

  async function load(uri) {
    const before = signals;
    if (!controller) {
      // Erster Aufruf legt den Player an; gleichzeitige Aufrufe warten darauf und laden danach um
      const mine = !creating;
      creating ??= create(uri)
        .then(() => (loaded = uri))
        .finally(() => (creating = null));
      await creating;
      if (mine) {
        await waitFor(subscribe, () => signals > before, CREATE_TIMEOUT_MS);
        return;
      }
    }
    if (loaded === uri) return;
    Object.assign(raw, { paused: true, position: 0, duration: NaN });
    loaded = uri;
    startedUri = null;
    controller.loadUri(uri);
    notify();
    await waitFor(subscribe, () => signals > before, LOAD_TIMEOUT_MS);
  }

  // Abspielen; mit positionS erst nach dem Start springen (vorher ignoriert der Player seek).
  // Kein Sprung bei einer Vorschau – ihre 30 s sind ein Ausschnitt, Positionen des ganzen Tracks
  // passen nicht – und keiner hinter das Ende (dann von vorn). expectedMs: echte Dauer des Tracks.
  async function play(positionS, { expectedMs } = {}) {
    if (!controller || !loaded) return;
    if (startedUri === loaded) controller.resume();
    else controller.play();
    startedUri = loaded;
    raw.paused = false;
    updatedAt = performance.now();
    notify();
    if (positionS != null) {
      await waitFor(subscribe, () => !raw.paused && Number.isFinite(raw.duration), START_TIMEOUT_MS);
      const known = Number.isFinite(raw.duration);
      if (known && !isPreview(raw.duration, expectedMs) && positionS < raw.duration - 1) seek(positionS);
    }
  }

  function pause() {
    if (!controller) return;
    controller.pause();
    raw.position = state.position;
    raw.paused = true;
    notify();
  }

  function seek(s) {
    if (!controller) return;
    const end = Number.isFinite(raw.duration) ? raw.duration - 1 : Infinity;
    const target = Math.max(0, Math.min(s, end));
    controller.seek(target);
    raw.position = target;
    updatedAt = performance.now();
    notify();
  }

  const state = {
    get uri() {
      return loaded;
    },
    get started() {
      return startedUri !== null && startedUri === loaded;
    },
    get paused() {
      return raw.paused;
    },
    get duration() {
      return raw.duration;
    },
    // Zwischen zwei Meldungen des Players weiterzählen, damit die Anzeige flüssig läuft
    get position() {
      if (raw.paused) return raw.position;
      const p = raw.position + (performance.now() - updatedAt) / 1000;
      return Number.isFinite(raw.duration) ? Math.min(p, raw.duration) : p;
    },
  };

  function destroy() {
    listeners.clear();
    controller?.destroy();
    controller = null;
    loaded = startedUri = null;
    container.replaceChildren();
  }

  return { load, play, pause, seek, subscribe, destroy, state };
}
