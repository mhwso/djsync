// Vorschläge anhören und A/B-Vergleich (ADR 0003).
//
//   const listening = createListening({ container, player, onChange });
//   listening.attach(detail)     – nach dem Laden der Detailansicht: je Vorschlag eine Quelle
//   listening.toggleAB()         – lokale Datei ↔ Vorschlag, an derselben Position (Taste a)
//   listening.cycle(±1)          – anderen Vorschlag für den Vergleich wählen (v / Umschalt+V)
//   listening.listen(id)         – Abspielknopf eines Vorschlags
//   listening.target             – ID des Vorschlags, mit dem verglichen wird
//   listening.destroy()
//
// Alle Vorschläge teilen sich einen eingebetteten Spotify-Player (js/spotify-embed.js) in
// `container`. Er liegt außerhalb der Detailansicht, weil ein iframe beim Umhängen neu lädt.
// Spielt der Player nur eine Vorschau, zeigt der Player-Hinweis den Weg zur Einrichtung und
// die Einrichtung erfährt davon (setup.report_player_login).

import { api } from "../../api.js";
import { createEmbed, isPreview } from "../../spotify-embed.js";

const PREVIEW_NOTICE = {
  text: "Nur 30-Sekunden-Vorschau: Für ganze Tracks im Spotify-Player anmelden.",
  href: "#/setup",
  link: "Zur Einrichtung",
};

const sourceId = (candidateId) => `spotify:${candidateId}`;

// Eine Quelle für player.js: ein Vorschlag im geteilten Player
function spotifySource(embed, candidate, onPlayed) {
  const uri = `spotify:track:${candidate.id}`;
  let pending = null; // Position, die vor dem ersten Abspielen vorgemerkt wurde (A/B im Pausenzustand)
  const mine = () => embed.state.uri === uri;
  const source = {
    id: sourceId(candidate.id),
    label: `Vorschlag ${candidate.number}`,
    onchange: () => {},
    prepare: () => embed.load(uri),
    async play(positionS) {
      await embed.load(uri);
      const position = positionS ?? pending;
      pending = null;
      await embed.play(position, { expectedMs: candidate.duration_ms });
    },
    pause() {
      if (mine()) embed.pause();
    },
    seek(s) {
      if (mine() && embed.state.started) embed.seek(s);
      else pending = s;
    },
    get position() {
      return mine() && embed.state.started ? embed.state.position : (pending ?? 0);
    },
    get duration() {
      return mine() ? embed.state.duration : NaN;
    },
    get playing() {
      return mine() && embed.state.started && !embed.state.paused;
    },
    get notice() {
      return mine() && isPreview(embed.state.duration, candidate.duration_ms) ? PREVIEW_NOTICE : null;
    },
    unload() {
      if (mine()) embed.pause();
      pending = null;
      off();
    },
  };
  const off = embed.subscribe(() => {
    if (!mine()) return;
    if (source.playing && Number.isFinite(embed.state.duration)) onPlayed(source, candidate);
    source.onchange();
  });
  return source;
}

export function createListening({ container, player, onChange = () => {} }) {
  const embed = createEmbed(container);
  let candidates = [];
  let target = null; // ID des Vorschlags für den A/B-Vergleich
  let reported = null; // zuletzt an die Einrichtung gemeldetes Ergebnis (true = ganze Tracks)

  // Ganzer Track oder Vorschau? Einmal je Wechsel an die Einrichtung melden
  function onPlayed(source, candidate) {
    const full = !isPreview(embed.state.duration, candidate.duration_ms);
    if (reported === full) return;
    // Kurze Tracks sind keine Vorschau, sagen aber auch nichts über die Anmeldung
    if (full && embed.state.duration <= 35) return;
    reported = full;
    api("setup.report_player_login", full).catch(() => {});
  }

  function attach(detail) {
    if (!detail || player.fingerprint !== detail.fingerprint) return;
    if (player.sources.some((s) => s.id.startsWith("spotify:"))) return; // schon angemeldet
    candidates = detail.candidates;
    for (const c of candidates) player.addSource(spotifySource(embed, c, onPlayed));
    target = (candidates.find((c) => c.selected) ?? candidates[0])?.id ?? null;
    onChange();
  }

  function hasSources() {
    return player.sources.some((s) => s.id === sourceId(target));
  }

  function toggleAB() {
    if (!hasSources()) return;
    player.switchTo(player.active?.id === "local" ? sourceId(target) : "local");
  }

  function cycle(direction) {
    if (!hasSources() || candidates.length === 0) return;
    const i = candidates.findIndex((c) => c.id === target);
    target = candidates[(i + direction + candidates.length) % candidates.length].id;
    // Läuft gerade ein Vorschlag, gleich auf den neuen wechseln (gleiche Position)
    if (player.active?.id.startsWith("spotify:")) player.switchTo(sourceId(target));
    onChange();
  }

  function listen(candidateId) {
    target = candidateId;
    player.listen(sourceId(candidateId));
    onChange();
  }

  return {
    attach,
    toggleAB,
    cycle,
    listen,
    get target() {
      return hasSources() ? target : null;
    },
    destroy: () => embed.destroy(),
  };
}
