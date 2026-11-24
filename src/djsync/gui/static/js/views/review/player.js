// Anhören im Review: Player für den ausgewählten Track.
//
//   const player = createPlayer({ folder, startS, skipS });
//   player.element        – Bedienelemente; index.js hängt sie nach jedem Rendern in .review-player
//   player.select(fp)     – neuer Track (oder null): Wiedergabe stoppt, Quellen werden neu angelegt
//   player.toggle()       – Abspielen/Pause (Leertaste)
//   player.skip(±1)       – um die Sprungweite vor- bzw. zurückspringen (→ / ←)
//   player.destroy()      – beim Verlassen des Reviews
//
// Quellen: Der Player spielt immer genau eine Quelle (die aktive). Heute gibt es nur die lokale
// Datei („local“). Weitere Quellen (#18: Spotify-Vorschläge) meldet man pro Track an:
//
//   player.addSource(source)        – z. B. in einer Funktion aus sourceFactories
//   player.switchTo(id)             – A/B-Wechsel: übernimmt die Position der aktiven Quelle
//
// Eine Quelle ist ein Objekt mit
//   id, label                        – z. B. "local" / "Lokale Datei", "spotify:<id>" / "Vorschlag 2"
//   async prepare()                  – Laden vor dem ersten Abspielen (darf ApiError werfen)
//   async play(positionS?)           – abspielen, optional ab Position (Sekunden)
//   pause(), seek(s)
//   position, duration, playing      – Getter; duration ist NaN, solange unbekannt
//   unload()                         – Wiedergabe beenden und Ressourcen freigeben
//   onchange                         – wird vom Player gesetzt; die Quelle ruft es bei Änderungen

import { api, errorMessage } from "../../api.js";
import { h } from "../../dom.js";

// Funktionen ({ player, folder, fingerprint }) → void, gerufen nach jedem Trackwechsel.
// #18 kann hier Spotify-Quellen für die Vorschläge anmelden.
export const sourceFactories = [];

// Lokale Datei über den Medien-Server der API-Schicht (AIFF kommt als umgewandelte WAV).
export function localSource(folder, fingerprint) {
  const audio = new Audio();
  audio.preload = "auto";
  let prepared = null;
  const source = {
    id: "local",
    label: "Lokale Datei",
    onchange: () => {},
    prepare() {
      prepared ??= api("player.local", folder, fingerprint).then(
        (r) =>
          new Promise((resolve, reject) => {
            audio.addEventListener("loadedmetadata", () => resolve(), { once: true });
            audio.addEventListener(
              "error",
              () => reject({ name: "ApiError", message: "Die Datei lässt sich nicht abspielen." }),
              { once: true },
            );
            audio.src = r.url;
          }),
      );
      prepared.catch(() => (prepared = null)); // erneuter Versuch beim nächsten Abspielen
      return prepared;
    },
    async play(positionS) {
      await source.prepare();
      if (positionS != null) source.seek(positionS);
      await audio.play();
    },
    pause: () => audio.pause(),
    seek(s) {
      const end = Number.isFinite(audio.duration) ? audio.duration : Infinity;
      audio.currentTime = Math.max(0, Math.min(s, end - 0.5));
    },
    get position() {
      return audio.currentTime;
    },
    get duration() {
      return audio.duration;
    },
    get playing() {
      return !audio.paused;
    },
    unload() {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      prepared = null;
    },
  };
  for (const name of ["play", "pause", "timeupdate", "durationchange", "ended"]) {
    audio.addEventListener(name, () => source.onchange());
  }
  return source;
}

// Sekunden → „m:ss“
function clock(s) {
  const t = Math.floor(s);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

export function createPlayer({ folder, startS, skipS }) {
  let fingerprint = null;
  let sources = new Map();
  let active = null; // Quelle
  let started = new Set(); // Quellen, die schon gespielt haben (Startstelle nur beim ersten Mal)
  let status = null; // { text, error }
  let busy = false;

  const playButton = h("button", { class: "button primary player-play", title: "Abspielen/Pause (Leertaste)", onclick: click(() => toggle()) });
  const backButton = h("button", { class: "button", title: "Zurückspringen (←)", onclick: click(() => skip(-1)) }, `−${skipS} s`);
  const fwdButton = h("button", { class: "button", title: "Vorspringen (→)", onclick: click(() => skip(1)) }, `+${skipS} s`);
  const bar = h("input", {
    type: "range",
    class: "player-bar",
    min: 0,
    max: 0,
    step: 1,
    value: 0,
    "aria-label": "Position",
    onchange: (e) => {
      active?.seek(Number(e.target.value));
      e.target.blur(); // sonst landen Leertaste/Pfeile im Regler statt bei den Kürzeln
    },
  });
  const time = h("span", { class: "player-time mono" });
  const sourceLabel = h("span", { class: "player-source" });
  const statusLine = h("span", { class: "player-status", "aria-live": "polite" });
  const element = h(
    "div",
    { class: "player" },
    h("div", { class: "player-controls" }, playButton, backButton, fwdButton, bar, time),
    h("div", { class: "player-info" }, sourceLabel, statusLine),
  );

  // Knöpfe nach dem Klick nicht fokussiert lassen: sonst löst die Leertaste sie zusätzlich aus
  function click(fn) {
    return (e) => {
      e.currentTarget.blur();
      fn();
    };
  }

  function update() {
    const playing = active?.playing ?? false;
    playButton.textContent = playing ? "❚❚ Pause" : "▶ Abspielen";
    playButton.disabled = !active || busy;
    backButton.disabled = fwdButton.disabled = bar.disabled = !active || !started.has(active);
    const pos = active?.position ?? 0;
    const dur = active?.duration;
    bar.max = Number.isFinite(dur) ? Math.floor(dur) : 0;
    if (document.activeElement !== bar) bar.value = Math.floor(pos);
    time.textContent = Number.isFinite(dur) ? `${clock(pos)} / ${clock(dur)}` : "";
    sourceLabel.textContent = sources.size > 1 && active ? active.label : "";
    statusLine.textContent = status?.text ?? "";
    statusLine.classList.toggle("error", Boolean(status?.error));
  }

  function addSource(source) {
    source.onchange = () => {
      if (source === active) update();
    };
    sources.set(source.id, source);
    active ??= source;
    update();
  }

  function select(fp) {
    for (const s of sources.values()) s.unload();
    sources = new Map();
    active = null;
    started = new Set();
    status = null;
    busy = false;
    fingerprint = fp;
    if (fp) {
      addSource(localSource(folder, fp));
      for (const factory of sourceFactories) factory({ player: player, folder, fingerprint: fp });
    }
    update();
  }

  // Abspielen ab `positionS`; ohne Angabe beim ersten Mal an der Startstelle, sonst weiter
  async function play(source, positionS) {
    const fp = fingerprint;
    busy = true;
    status = source.playing || started.has(source) ? null : { text: "Wird vorbereitet …" };
    update();
    try {
      await source.prepare();
      if (fp !== fingerprint || source !== active) return; // inzwischen gewechselt
      let pos = positionS;
      if (pos == null && !started.has(source)) {
        // Kurze Tracks: Startstelle hinter dem Ende → von vorn
        pos = Number.isFinite(source.duration) && startS >= source.duration ? 0 : startS;
      }
      started.add(source);
      await source.play(pos);
      status = null;
    } catch (err) {
      if (fp === fingerprint) status = { text: errorMessage(err), error: true };
    } finally {
      busy = false;
      update();
    }
  }

  function toggle() {
    if (!active || busy) return;
    if (active.playing) active.pause();
    else play(active);
  }

  function skip(direction) {
    if (!active || !started.has(active)) return;
    active.seek(active.position + direction * skipS);
    update();
  }

  // A/B-Wechsel: die neue Quelle spielt an der Position der bisherigen weiter
  async function switchTo(id) {
    const next = sources.get(id);
    if (!next || next === active) return;
    const previous = active;
    const wasPlaying = previous?.playing ?? false;
    const position = previous && started.has(previous) ? previous.position : null;
    previous?.pause();
    active = next;
    update();
    if (wasPlaying) await play(next, position);
    else if (position != null) {
      // nur vormerken: beim nächsten Abspielen dort weiter
      started.add(next);
      await next.prepare().then(() => next.seek(position), () => {});
      update();
    }
  }

  function destroy() {
    select(null);
  }

  const player = {
    element,
    select,
    toggle,
    skip,
    switchTo,
    addSource,
    destroy,
    get fingerprint() {
      return fingerprint;
    },
    get active() {
      return active;
    },
    get sources() {
      return [...sources.values()];
    },
  };
  update();
  return player;
}
