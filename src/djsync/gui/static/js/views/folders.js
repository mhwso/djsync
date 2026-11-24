// Startbildschirm: alle Ordner mit Playlist-Name, letztem Sync und Anzahl offener Tracks.
// Die Zahlen sind der Stand vom letzten Sync bzw. Review, es wird nichts neu eingelesen.

import { api, errorMessage, on } from "../api.js";
import { h } from "../dom.js";
import { addFolder, chooseFolder, removeFolder, renameFolder } from "../folder-dialogs.js";
import { absoluteTime, plural, relativeTime } from "../format.js";
import { relinkDialog } from "../relink.js";
import { startSync } from "./sync.js";

// Ordner, für die Relink in dieser Sitzung schon automatisch angeboten wurde
const offeredRelink = new Set();

function lastSync(folder) {
  if (folder.last_sync) {
    return h("span", { title: absoluteTime(folder.last_sync) }, "Letzter Sync ", relativeTime(folder.last_sync));
  }
  // Ohne Zeitpunkt: entweder noch nie synchronisiert oder aus der Zeit vor der GUI übernommen
  return h("span", { class: "muted" }, folder.playlist_id ? "Letzter Sync unbekannt" : "Noch nie synchronisiert");
}

function state(folder) {
  const badges = [];
  if (!folder.reachable) {
    badges.push(h("span", { class: "badge warn", title: "Ist das Laufwerk eingebunden?" }, "Nicht erreichbar"));
  }
  badges.push(
    folder.open_count > 0
      ? h("span", { class: "badge open" }, plural(folder.open_count, "offener Track", "offene Tracks"))
      : h("span", { class: "badge ok" }, "Nichts offen"),
  );
  return h("div", { class: "folder-state" }, badges);
}

function folderActions(folder, reload, navigate) {
  const run = (dialog) => async () => {
    if (await dialog(folder)) reload();
  };
  return h(
    "div",
    { class: "folder-actions" },
    h(
      "button",
      { type: "button", class: "button small primary", title: "Taste S", onclick: () => startSync(folder.folder, navigate) },
      "Sync",
    ),
    h(
      "button",
      {
        type: "button",
        class: "button small",
        title: "Verschobenen Ordner mit neuem Pfad verknüpfen",
        onclick: run((f) => relinkDialog(f.folder, { unreachable: !f.reachable })),
      },
      "Relink …",
    ),
    h("button", { type: "button", class: "button small", onclick: run(renameFolder) }, "Umbenennen"),
    h("button", { type: "button", class: "button small", onclick: run(removeFolder) }, "Entfernen"),
  );
}

function folderRow(folder, reload, navigate) {
  const name = folder.playlist_url
    ? h("a", { href: folder.playlist_url, target: "_blank", title: "Playlist in Spotify öffnen" }, folder.name)
    : folder.name;
  return h(
    "li",
    {
      class: "folder" + (folder.reachable ? "" : " unreachable"),
      tabindex: 0,
      // Taste S auf der ausgewählten Zeile startet den Sync
      onkeydown: (event) => {
        if (event.target === event.currentTarget && event.key.toLowerCase() === "s" && !event.ctrlKey && !event.altKey) {
          event.preventDefault();
          startSync(folder.folder, navigate);
        }
      },
    },
    h(
      "div",
      { class: "folder-main" },
      h("div", { class: "folder-name" }, name),
      h("div", { class: "folder-path mono muted", title: folder.folder }, folder.folder),
    ),
    h("div", { class: "folder-sync" }, lastSync(folder)),
    state(folder),
    folderActions(folder, reload, navigate),
  );
}

// Nicht erreichbare Ordner: Relink einmal pro Sitzung automatisch anbieten
async function offerRelink(folders, refresh) {
  for (const folder of folders) {
    if (folder.reachable || offeredRelink.has(folder.folder)) continue;
    offeredRelink.add(folder.folder);
    if (await relinkDialog(folder.folder, { unreachable: true })) {
      refresh();
      return;
    }
  }
}

export default {
  title: "Ordner",

  async render(root, params, ctx) {
    const body = h("div", { class: "view-body" }, h("p", { class: "muted" }, "Lade Ordner …"));
    const added = (changed) => changed && load();
    const addButton = h(
      "button",
      { type: "button", class: "button primary", onclick: async () => added(await chooseFolder()) },
      "Ordner hinzufügen",
    );
    root.append(h("div", { class: "view-head" }, h("h1", {}, "Ordner"), addButton), body);

    async function load() {
      let folders;
      try {
        folders = await api("folders.list");
      } catch (err) {
        body.replaceChildren(h("p", { class: "notice error" }, errorMessage(err)));
        return;
      }

      if (folders.length === 0) {
        body.replaceChildren(
          h(
            "div",
            { class: "empty" },
            h("strong", {}, "Noch keine Ordner"),
            "Ordner über „Ordner hinzufügen“ wählen oder einfach ins Fenster ziehen.",
          ),
        );
        return;
      }
      body.replaceChildren(
        h("ul", { class: "folder-list" }, folders.map((f) => folderRow(f, load, ctx.navigate))),
        h("p", { class: "muted drop-hint" }, "Weitere Ordner einfach ins Fenster ziehen."),
      );
      offerRelink(folders, load);
    }

    // Ins Fenster gezogene Ordner meldet Python (Browser kennen keine vollen Pfade)
    const off = on("folders.dropped", async ({ paths }) => {
      for (const path of paths) added(await addFolder(path));
    });

    await load();
    return off;
  },
};
