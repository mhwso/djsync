// Sync eines Ordners: Fortschritt → Zusammenfassung → Änderungsplan → übernehmen oder verwerfen.
//
// Starten über startSync(folder, navigate) (z. B. vom Startbildschirm): prüft vorher die
// Erreichbarkeit (bietet sonst Relink an) und öffnet diese Ansicht. Der Sync selbst läuft in
// Python im Hintergrund (api/sync.py) und meldet sich über die Events sync.*. Die Ansicht kann
// jederzeit verlassen und wieder geöffnet werden; sie holt sich den Stand über sync.status.
//
// Gibt es nach dem Suchen offene Tracks, fragt die Ansicht vor dem Änderungsplan „erst prüfen“
// oder „direkt weiter“. „Erst prüfen“ öffnet das Review mit from=sync; dessen „Fertig“ führt
// mit step=plan hierher zurück. Der Sync bleibt dabei in Python bereit (kein erneutes Einlesen
// oder Suchen), Zusammenfassung und Plan werden mit den Review-Entscheidungen neu berechnet.
//
// Tasten: Esc bricht ab bzw. verwirft, Strg+Enter übernimmt den Änderungsplan.

import { api, errorMessage, on } from "../api.js";
import { h } from "../dom.js";
import { plural } from "../format.js";
import { ensureReachable } from "../relink.js";

const STEPS = {
  scan: "Ordner einlesen",
  playlist: "Playlist laden",
  search: "Tracks auf Spotify suchen",
};

// Treffer-Status in der Reihenfolge der Zusammenfassung (Begriffe wie im Glossar)
const STATUSES = [
  ["exact", "exakt", "ok"],
  ["approximate", "ungefähr", "open"],
  ["manual", "manuell", "ok"],
  ["not_found", "nicht gefunden", "open"],
  ["not_on_spotify", "nicht auf Spotify", ""],
];

// Startet den Sync (nach Prüfung der Erreichbarkeit) und öffnet die Sync-Ansicht.
export async function startSync(folder, navigate) {
  const reachable = await ensureReachable(folder);
  if (!reachable) return;
  navigate("sync", { folder: reachable, start: "1" });
}

function button(label, onclick, cls = "") {
  return h("button", { type: "button", class: `button ${cls}`.trim(), onclick }, label);
}

// Fortschritt; update(p) aktualisiert die Anzeige, ohne den Abbrechen-Button neu zu bauen
function progressView(cancel) {
  const heading = h("h2", {});
  const bar = h("progress", {});
  const count = h("p", { class: "muted" });
  const el = h(
    "section",
    { class: "sync-card", "aria-live": "polite" },
    heading,
    bar,
    count,
    h("div", { class: "sync-actions" }, button("Abbrechen", cancel)),
  );
  function update(p) {
    const known = p && p.total > 0;
    heading.textContent = (p ? STEPS[p.step] ?? p.step : "Wird gestartet") + " …";
    if (known) {
      bar.max = p.total;
      bar.value = p.done;
    } else {
      bar.removeAttribute("value"); // unbestimmt
    }
    count.textContent = known ? `${p.done} von ${p.total}` : "Bitte warten";
  }
  return { el, update };
}

function summaryView(summary) {
  const badges = STATUSES.map(([key, label, cls]) =>
    h("span", { class: `badge ${summary.counts[key] ? cls : ""}`.trim() }, `${summary.counts[key] ?? 0} ${label}`),
  );
  const open = summary.open.length
    ? h(
        "details",
        { class: "sync-list" },
        h("summary", {}, plural(summary.open.length, "offener Track", "offene Tracks")),
        h("ul", {}, summary.open.map((t) => h("li", { class: "mono" }, t.file))),
      )
    : h("p", { class: "muted" }, "Keine offenen Tracks.");
  return h(
    "section",
    { class: "sync-card" },
    h("h2", {}, "Zusammenfassung"),
    h(
      "p",
      { class: "muted" },
      `${plural(summary.found, "Audiodatei", "Audiodateien")} im Ordner, ${summary.fresh} neu eingelesen, `,
      `${plural(summary.searched, "Track", "Tracks")} auf Spotify gesucht.`,
    ),
    h("div", { class: "sync-badges" }, badges),
    open,
  );
}

function trackList(title, tracks, sign) {
  if (!tracks.length) return null;
  return h(
    "details",
    { class: "sync-list", open: tracks.length <= 20 },
    h("summary", {}, `${sign} ${title}: ${tracks.length}`),
    h("ul", {}, tracks.map((t) => h("li", { class: "mono" }, t.label))),
  );
}

// Hinweis auf offene Tracks vor dem Änderungsplan
function reviewHint(open, review, proceed) {
  return h(
    "section",
    { class: "sync-card sync-hint" },
    h("h2", {}, "Offene Tracks prüfen?"),
    h(
      "p",
      {},
      `${plural(open, "Track ist", "Tracks sind")} noch offen. Du kannst sie jetzt im Review prüfen – `,
      "danach geht es mit dem Änderungsplan dieses Syncs weiter, ohne erneutes Einlesen oder Suchen. ",
      "Oder du siehst dir den Änderungsplan direkt an.",
    ),
    h("div", { class: "sync-actions" }, review, proceed),
  );
}

function planView(plan) {
  const lines = [];
  if (plan.playlist_lost) {
    lines.push(h("p", { class: "notice warn" }, "Die verknüpfte Playlist existiert auf Spotify nicht mehr und wird neu angelegt."));
  }
  if (plan.create) {
    lines.push(h("p", {}, "Neue private Playlist ", h("strong", {}, `„${plan.name}“`), " wird angelegt."));
  } else if (plan.rename) {
    lines.push(h("p", {}, "Die Playlist wird umbenannt in ", h("strong", {}, `„${plan.rename}“`), "."));
  }
  lines.push(trackList("neu", plan.added, "+"), trackList("entfernt", plan.removed, "−"));
  if (plan.reordered) lines.push(h("p", {}, "Die Reihenfolge wird angepasst."));
  if (!plan.added.length && !plan.removed.length && !plan.reordered && !plan.create) {
    lines.push(h("p", { class: "muted" }, "Die Playlist ist schon aktuell, es gibt keine Änderungen."));
  }
  return h(
    "section",
    { class: "sync-card" },
    h("h2", {}, "Änderungsplan"),
    h("p", { class: "muted" }, `Danach ${plural(plan.total, "Track", "Tracks")} in der Playlist.`),
    lines,
  );
}

export default {
  title: "Sync",

  async render(root, params, { navigate }) {
    const folder = params.folder;
    const title = h("h1", {}, "Sync");
    const body = h("div", { class: "view-body sync" });
    root.append(h("div", { class: "view-head" }, title, h("span", { class: "mono muted" }, folder ?? "")), body);
    const home = () => navigate("folders");
    let keys = null; // Tastenbelegung des aktuellen Schritts
    // Rückkehr aus dem Review: Hinweis „erst prüfen / direkt weiter“ nicht noch einmal zeigen
    let skipHint = params.step === "plan";

    function show(...children) {
      body.replaceChildren(...children.flat().filter(Boolean));
    }

    function fail(message, retry) {
      keys = { Escape: home };
      show(
        h("p", { class: "notice error", role: "alert" }, message),
        h(
          "div",
          { class: "sync-actions" },
          button("Zum Startbildschirm", home),
          // Anmeldung abgelaufen o. Ä.: die Meldung verweist auf die Einrichtung
          message.includes("Einrichtung") && button("Zur Einrichtung", () => navigate("setup")),
          retry && button("Erneut versuchen", retry, "primary"),
        ),
      );
    }

    async function start() {
      skipHint = false; // neuer Sync: Hinweis wieder anbieten
      try {
        await api("sync.start", folder);
      } catch (err) {
        // z. B. läuft schon ein Sync: dorthin anbieten
        const status = await api("sync.status").catch(() => null);
        if (status && status.folder !== folder && ["running", "ready"].includes(status.state)) {
          keys = { Escape: home };
          show(
            h("p", { class: "notice error", role: "alert" }, errorMessage(err)),
            h(
              "div",
              { class: "sync-actions" },
              button("Zum Startbildschirm", home),
              button("Zum laufenden Sync", () => navigate("sync", { folder: status.folder }), "primary"),
            ),
          );
        } else {
          fail(errorMessage(err), start);
        }
        return;
      }
      await refresh();
    }

    async function cancel() {
      try {
        await api("sync.cancel");
      } catch (err) {
        fail(errorMessage(err));
      }
    }

    async function discard() {
      try {
        await api("sync.discard");
        home();
      } catch (err) {
        fail(errorMessage(err));
      }
    }

    async function confirm(confirmButton) {
      confirmButton.disabled = true;
      confirmButton.textContent = "Übertrage …";
      try {
        const entry = await api("sync.confirm");
        done(entry);
      } catch (err) {
        confirmButton.disabled = false;
        confirmButton.textContent = "Übernehmen";
        body.prepend(h("p", { class: "notice error", role: "alert" }, errorMessage(err)));
      }
    }

    function done(entry) {
      keys = { Escape: home, Enter: home };
      title.textContent = "Sync abgeschlossen";
      show(
        h(
          "section",
          { class: "sync-card" },
          h("h2", {}, "Die Playlist ist auf dem neuen Stand."),
          h("p", {}, h("a", { href: entry.playlist_url, target: "_blank" }, `„${entry.name}“ in Spotify öffnen`)),
          entry.open_count > 0 &&
            h("p", { class: "muted" }, `${plural(entry.open_count, "Track ist", "Tracks sind")} noch offen.`),
        ),
        h("div", { class: "sync-actions" }, button("Zum Startbildschirm", home, "primary")),
      );
    }

    // Zusammenfassung, bei offenen Tracks zuerst der Hinweis „erst prüfen / direkt weiter“.
    async function ready() {
      let summary;
      try {
        summary = await api("sync.summary");
      } catch (err) {
        fail(errorMessage(err), start);
        return;
      }
      if (summary.open.length && !skipHint) {
        const review = button("Erst prüfen", () => navigate("review", { folder, from: "sync" }), "primary");
        const proceed = button("Direkt weiter", () => {
          skipHint = true;
          showPlan(summary);
        });
        keys = { Escape: discard };
        show(
          summaryView(summary),
          reviewHint(summary.open.length, review, proceed),
          h("div", { class: "sync-actions" }, button("Verwerfen", discard)),
        );
        review.focus();
        return;
      }
      await showPlan(summary);
    }

    // Änderungsplan. Er wird bei jedem Aufruf neu berechnet, damit Review-Entscheidungen einfließen.
    async function showPlan(summary) {
      let plan;
      try {
        plan = await api("sync.plan");
      } catch (err) {
        fail(errorMessage(err), start);
        return;
      }
      const confirmButton = button("Übernehmen", () => confirm(confirmButton), "primary");
      confirmButton.title = "Strg+Enter";
      keys = { Escape: discard, "Ctrl+Enter": () => confirm(confirmButton) };
      show(
        summaryView(summary),
        planView(plan),
        h("div", { class: "sync-actions" }, button("Verwerfen", discard), confirmButton),
      );
      confirmButton.focus();
    }

    async function refresh() {
      let status;
      try {
        status = await api("sync.status");
      } catch (err) {
        fail(errorMessage(err));
        return;
      }
      if (!status || status.folder !== folder) {
        keys = { Escape: home };
        show(
          h("p", { class: "muted" }, "Für diesen Ordner läuft gerade kein Sync."),
          h("div", { class: "sync-actions" }, button("Zum Startbildschirm", home), button("Sync starten", start, "primary")),
        );
        return;
      }
      if (status.state === "running") {
        showProgress(status.progress);
      } else if (status.state === "ready") {
        await ready();
      } else if (status.state === "cancelled") {
        keys = { Escape: home };
        show(
          h("p", { class: "notice" }, "Sync abgebrochen. Die Playlist ist unverändert."),
          h("div", { class: "sync-actions" }, button("Zum Startbildschirm", home), button("Erneut starten", start, "primary")),
        );
      } else if (status.state === "failed") {
        fail(status.error, start);
      }
    }

    let progress = null; // angezeigte Fortschrittsanzeige, solange der Sync läuft
    function showProgress(p) {
      keys = { Escape: cancel };
      if (!progress || !body.contains(progress.el)) {
        progress = progressView(cancel);
        show(progress.el);
      }
      progress.update(p);
    }

    const mine = (handler) => (data) => data?.folder === folder && handler(data);
    const offs = [
      on("sync.progress", mine(showProgress)),
      on("sync.ready", mine(refresh)),
      on("sync.cancelled", mine(refresh)),
      on("sync.failed", mine(refresh)),
    ];

    function onKey(event) {
      const key = (event.ctrlKey ? "Ctrl+" : "") + event.key;
      const action = keys?.[key];
      if (!action || event.target.closest?.("input, textarea, dialog")) return;
      event.preventDefault();
      action();
    }
    document.addEventListener("keydown", onKey);

    if (!folder) {
      fail("Kein Ordner angegeben.");
    } else if (params.start) {
      // Start-Parameter aus der Adresse nehmen, damit Neuladen nicht erneut startet
      history.replaceState(null, "", `#/sync?${new URLSearchParams({ folder })}`);
      await start();
    } else {
      await refresh();
    }

    return () => {
      offs.forEach((off) => off());
      document.removeEventListener("keydown", onKey);
    };
  },
};
