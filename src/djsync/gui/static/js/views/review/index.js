// Review eines Ordners: links die Track-Liste mit Filtern, rechts die Detailansicht.
//
//   #/review?folder=<Pfad>[&filter=open|decided|exact]
//
// Jede Entscheidung wird sofort gespeichert (API review.*); danach springt die Auswahl zum
// nächsten offenen Track. Review-Entscheidungen verändern die Playlist nicht.
//
// Mehrfachauswahl (Strg-/Umschalt-Klick, Umschalt+↑/↓, Strg+A): Bei mehr als einem
// ausgewählten Track zeigt die rechte Spalte statt der Detailansicht die Massenoperationen
// (bulk.js) – „nicht auf Spotify“ und „erneut suchen“ für alle ausgewählten Tracks.
//
// Erweiterungspunkte:
//   - leave(): Rückkehr nach dem Review (#16 leitet hier zum Änderungsplan zurück)
//   - onSelect: wird bei jedem Wechsel des ausgewählten Tracks gerufen
//   - player.js: Anhören der lokalen Datei; weitere Quellen (#18 Spotify, A/B) über sourceFactories
//   - keys.js / detail.js: Kürzel, Player-Knöpfe

import { api, errorMessage, on } from "../../api.js";
import { h } from "../../dom.js";
import { plural } from "../../format.js";
import { bulkSummary, renderBulk } from "./bulk.js";
import { renderDetail, renderDone } from "./detail.js";
import { handleKey, helpDialog } from "./keys.js";
import { FILTERS } from "./labels.js";
import { renderFilters, renderList } from "./list.js";
import { createPlayer } from "./player.js";

// Funktionen (fingerprint | null) → void, gerufen nach jedem Wechsel des ausgewählten Tracks
export const onSelect = [];

export default {
  title: "Review",

  async render(root, params, { navigate }) {
    const folder = params.folder;
    const state = {
      filter: FILTERS.some((f) => f.id === params.filter) ? params.filter : "open",
      listing: null, // Antwort von review.tracks
      selected: null, // Fingerprint des Tracks, auf dem die Tastatur steht (Detailansicht)
      marked: new Set(), // Fingerprints aller ausgewählten Tracks (Mehrfachauswahl)
      anchor: null, // Ausgangspunkt für Umschalt-Auswahl
      detail: null, // Antwort von review.track
      link: { open: false, value: "", error: null },
      message: null, // Fehlermeldung über der Detailansicht
      notice: null, // Ergebnis einer Massenoperation
      progress: null, // { done, total } während „erneut suchen“
      busy: false,
    };

    const count = h("span", { class: "review-count" });
    const filters = h("div");
    const list = h("div", { class: "review-list-wrap" });
    const message = h("div", { class: "review-message", "aria-live": "polite" });
    const detail = h("div", { class: "review-detail" });
    const help = helpDialog();

    // Anhören: Startstelle und Sprungweite aus den Einstellungen (sonst die Standardwerte)
    const settings = await api("settings.get").catch(() => ({}));
    const player = createPlayer({ folder, startS: settings.start_position_s ?? 60, skipS: settings.skip_s ?? 30 });

    root.append(
      h(
        "div",
        { class: "view-head review-head" },
        h("h1", {}, "Review"),
        h("span", { class: "review-folder mono muted", title: folder }, folder),
        count,
        h("button", { class: "button", title: "Tastenkürzel (?)", onclick: () => toggleHelp() }, "Tastenkürzel"),
        h("button", { class: "button", title: "Review verlassen (q)", onclick: () => leave() }, "Fertig"),
      ),
      h("div", { class: "review" }, h("aside", { class: "review-side" }, filters, list), h("section", { class: "review-main" }, message, detail)),
      help,
    );

    // ---- Darstellung -----------------------------------------------------

    function renderSide() {
      const n = state.listing?.open_count ?? 0;
      count.replaceChildren(h("span", { class: `badge ${n ? "open" : "ok"}` }, n ? plural(n, "offener Track", "offene Tracks") : "Nichts offen"));
      filters.replaceChildren(renderFilters(state.filter, setFilter));
      list.replaceChildren(renderList(state.listing?.tracks ?? [], state.marked, state.selected, clickTrack));
      list.querySelector(".review-item.cursor")?.scrollIntoView({ block: "nearest" });
    }

    function renderMain() {
      message.replaceChildren(
        state.message ? h("p", { class: "notice error" }, state.message) : "",
        state.notice ? h("p", { class: "notice" }, state.notice) : "",
      );
      if (state.marked.size > 1 || state.progress) {
        detail.replaceChildren(renderBulk(markedTracks(), bulkActions, state.progress));
      } else if (state.detail) {
        detail.replaceChildren(renderDetail(state.detail, actions, state.link));
        // Die Bedienelemente bleiben dieselben, die Wiedergabe läuft beim Neuzeichnen weiter
        detail.querySelector(".review-player")?.append(player.element);
      } else if (state.filter === "open" && (state.listing?.open_count ?? 0) === 0) {
        detail.replaceChildren(renderDone(leave));
      } else {
        detail.replaceChildren(h("p", { class: "muted review-placeholder" }, "Wähle links einen Track."));
      }
    }

    function fail(err) {
      state.message = errorMessage(err);
      renderMain();
    }

    // ---- Laden und Auswahl -----------------------------------------------

    async function loadList() {
      state.listing = await api("review.tracks", folder, state.filter);
    }

    async function select(fingerprint) {
      state.selected = fingerprint;
      state.marked = new Set(fingerprint ? [fingerprint] : []);
      state.anchor = fingerprint;
      state.link = { open: false, value: "", error: null };
      state.message = null;
      state.notice = null;
      state.detail = null;
      if (fingerprint !== player.fingerprint) player.select(fingerprint); // Trackwechsel stoppt die Wiedergabe
      for (const fn of onSelect) fn(fingerprint);
      renderSide();
      if (fingerprint) {
        try {
          state.detail = await api("review.track", folder, fingerprint);
        } catch (err) {
          return fail(err);
        }
      }
      renderMain();
    }

    // Nach einer Entscheidung: Liste neu laden, zum nächsten offenen Track springen. Ist er
    // im aktuellen Filter nicht sichtbar (z. B. „exakt“), bleibt der entschiedene Track gewählt.
    async function after(result) {
      await loadList();
      const visible = (fp) => state.listing.tracks.some((t) => t.fingerprint === fp);
      if (result.next && visible(result.next)) return select(result.next);
      if (visible(result.track.fingerprint)) {
        state.detail = result.track;
        state.link = { open: false, value: "", error: null };
        state.message = null;
        renderSide();
        return renderMain();
      }
      return select(result.next ?? null);
    }

    async function decide(method, ...args) {
      if (!state.selected || state.busy) return;
      state.busy = true;
      try {
        await after(await api(`review.${method}`, folder, state.selected, ...args));
      } catch (err) {
        fail(err);
      } finally {
        state.busy = false;
      }
    }

    // ---- Mehrfachauswahl --------------------------------------------------

    function markedTracks() {
      return (state.listing?.tracks ?? []).filter((t) => state.marked.has(t.fingerprint));
    }

    // Auswahl setzen; bei genau einem Track die normale Detailansicht
    function mark(fingerprints, cursor) {
      if (fingerprints.size <= 1) return select(cursor ?? [...fingerprints][0] ?? null);
      state.marked = fingerprints;
      state.selected = cursor;
      state.detail = null;
      state.link = { open: false, value: "", error: null };
      state.message = null;
      player.select(null); // Mehrfachauswahl: kein Track zum Anhören
      for (const fn of onSelect) fn(null);
      renderSide();
      renderMain();
    }

    // Fingerprints der Liste von a bis b (beide eingeschlossen, Reihenfolge egal)
    function range(a, b) {
      const fps = (state.listing?.tracks ?? []).map((t) => t.fingerprint);
      let i = fps.indexOf(a);
      const j = fps.indexOf(b);
      if (i < 0) i = j;
      return new Set(fps.slice(Math.min(i, j), Math.max(i, j) + 1));
    }

    function clickTrack(fingerprint, event) {
      if (event.ctrlKey || event.metaKey) {
        const marked = new Set(state.marked);
        if (marked.has(fingerprint)) marked.delete(fingerprint);
        else marked.add(fingerprint);
        state.anchor = fingerprint;
        const cursor = marked.has(fingerprint) ? fingerprint : [...marked][0];
        return marked.size ? mark(marked, cursor) : undefined;
      }
      if (event.shiftKey && state.anchor) {
        const anchor = state.anchor;
        mark(range(anchor, fingerprint), fingerprint);
        state.anchor = anchor;
        return;
      }
      return select(fingerprint);
    }

    function extend(step) {
      const tracks = state.listing?.tracks ?? [];
      if (tracks.length === 0) return;
      const i = tracks.findIndex((t) => t.fingerprint === state.selected);
      const j = Math.max(0, Math.min(tracks.length - 1, (i < 0 ? 0 : i) + step));
      const anchor = state.anchor ?? tracks[j].fingerprint;
      mark(range(anchor, tracks[j].fingerprint), tracks[j].fingerprint);
      state.anchor = anchor;
    }

    function selectAll() {
      const tracks = state.listing?.tracks ?? [];
      if (tracks.length === 0) return;
      const anchor = state.anchor;
      mark(new Set(tracks.map((t) => t.fingerprint)), state.selected ?? tracks[0].fingerprint);
      state.anchor = anchor;
    }

    // Nach einer Massenoperation: Liste neu laden, Auswahl auf die noch sichtbaren Tracks
    // beschränken, Ergebnis anzeigen.
    async function afterBulk(result) {
      await loadList();
      const visible = new Set(state.listing.tracks.map((t) => t.fingerprint));
      const marked = new Set([...state.marked].filter((fp) => visible.has(fp)));
      if (marked.size > 1) {
        await mark(marked, visible.has(state.selected) ? state.selected : [...marked][0]);
      } else if (marked.size === 1) {
        await select([...marked][0]);
      } else {
        const next = await api("review.next_open", folder, null);
        await select(next && visible.has(next) ? next : (state.listing.tracks[0]?.fingerprint ?? null));
      }
      state.notice = bulkSummary(result);
      renderMain();
    }

    async function bulk(method) {
      if (state.marked.size === 0 || state.busy) return;
      state.busy = true;
      state.message = null;
      state.notice = null;
      try {
        if (method === "bulk_search") {
          state.progress = { done: 0, total: 0 };
          renderMain();
        }
        const result = await api(`review.${method}`, folder, [...state.marked]);
        state.progress = null;
        await afterBulk(result);
      } catch (err) {
        state.progress = null;
        fail(err);
      } finally {
        state.busy = false;
      }
    }

    const bulkActions = {
      notOnSpotify: () => bulk("bulk_not_on_spotify"),
      searchAgain: () => bulk("bulk_search"),
      cancelSearch: () => api("review.cancel_search").catch(fail),
      clearSelection: () => (state.marked.size > 1 && !state.busy ? select(state.selected) : undefined),
    };

    const offProgress = on("review.search_progress", (data) => {
      if (!state.progress) return;
      state.progress = data;
      renderMain();
    });

    async function setFilter(filter) {
      state.filter = filter;
      try {
        await loadList();
      } catch (err) {
        return fail(err);
      }
      const keep = state.listing.tracks.find((t) => t.fingerprint === state.selected);
      await select(keep ? keep.fingerprint : (state.listing.tracks[0]?.fingerprint ?? null));
    }

    function leave() {
      navigate("folders");
    }

    function toggleHelp() {
      if (help.open) help.close();
      else help.showModal();
    }

    // ---- Aktionen (Maus und Tastatur) ------------------------------------

    const actions = {
      accept: (id) => decide("accept", id),
      openLink() {
        if (!state.detail) return;
        state.link = { open: true, value: "", error: null };
        renderMain();
      },
      async submitLink(text) {
        if (!state.selected || state.busy) return;
        state.busy = true;
        try {
          await after(await api("review.accept_link", folder, state.selected, text));
        } catch (err) {
          // Ungültiger Link: Eingabe bleibt offen, Meldung direkt darunter
          state.link = { open: true, value: text, error: errorMessage(err) };
          renderMain();
        } finally {
          state.busy = false;
        }
      },
      cancelLink() {
        state.link = { open: false, value: "", error: null };
        renderMain();
      },
      notOnSpotify: () => (state.marked.size > 1 ? bulkActions.notOnSpotify() : decide("not_on_spotify")),
      searchAgain: () => bulkActions.searchAgain(),
      async skip() {
        try {
          const next = await api("review.next_open", folder, state.selected);
          if (next) {
            if (state.filter !== "open" && !state.listing.tracks.some((t) => t.fingerprint === next)) {
              state.filter = "open";
              await loadList();
            }
            await select(next);
          }
        } catch (err) {
          fail(err);
        }
      },
      reset() {
        if (state.detail?.decided) decide("reset");
      },
    };

    const keyContext = {
      ...actions,
      move(step) {
        const tracks = state.listing?.tracks ?? [];
        if (tracks.length === 0) return;
        const i = tracks.findIndex((t) => t.fingerprint === state.selected);
        const j = Math.max(0, Math.min(tracks.length - 1, (i < 0 ? 0 : i) + step));
        if (tracks[j].fingerprint !== state.selected) select(tracks[j].fingerprint);
      },
      acceptNumber(n) {
        const c = state.detail?.candidates.find((x) => x.number === n);
        if (c) actions.accept(c.id);
      },
      nextFilter() {
        const i = FILTERS.findIndex((f) => f.id === state.filter);
        setFilter(FILTERS[(i + 1) % FILTERS.length].id);
      },
      extend,
      selectAll,
      clearSelection: bulkActions.clearSelection,
      toggleHelp,
      leave,
      togglePlay: () => player.toggle(),
      skipPlay: (direction) => player.skip(direction),
    };

    function onKey(event) {
      // Bei offener Übersicht nur „?“ (Esc schließt den Dialog von selbst)
      if (help.open && event.key !== "?") return;
      handleKey(event, keyContext);
    }

    // ---- Start -----------------------------------------------------------

    document.addEventListener("keydown", onKey);
    try {
      await loadList();
      const first = state.filter === "open" ? await api("review.next_open", folder, null) : state.listing.tracks[0]?.fingerprint;
      await select(first ?? null);
    } catch (err) {
      renderSide();
      fail(err);
    }

    return () => {
      document.removeEventListener("keydown", onKey);
      player.destroy();
      offProgress();
      for (const fn of onSelect) fn(null);
    };
  },
};
