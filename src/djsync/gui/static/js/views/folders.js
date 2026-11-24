// Startbildschirm: alle Ordner mit Playlist-Name, letztem Sync und Anzahl offener Tracks.
// Die Zahlen sind der Stand vom letzten Sync bzw. Review, es wird nichts neu eingelesen.

import { api, errorMessage } from "../api.js";
import { h } from "../dom.js";
import { absoluteTime, plural, relativeTime } from "../format.js";

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

function folderRow(folder) {
  const name = folder.playlist_url
    ? h("a", { href: folder.playlist_url, target: "_blank", title: "Playlist in Spotify öffnen" }, folder.name)
    : folder.name;
  return h(
    "li",
    { class: "folder" + (folder.reachable ? "" : " unreachable") },
    h(
      "div",
      { class: "folder-main" },
      h("div", { class: "folder-name" }, name),
      h("div", { class: "folder-path mono muted", title: folder.folder }, folder.folder),
    ),
    h("div", { class: "folder-sync" }, lastSync(folder)),
    state(folder),
  );
}

export default {
  title: "Ordner",

  async render(root) {
    const body = h("div", { class: "view-body" }, h("p", { class: "muted" }, "Lade Ordner …"));
    root.append(h("div", { class: "view-head" }, h("h1", {}, "Ordner")), body);

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
          "Sobald ein Ordner synchronisiert ist, erscheint er hier mit seiner Playlist.",
        ),
      );
      return;
    }
    body.replaceChildren(h("ul", { class: "folder-list" }, folders.map(folderRow)));
  },
};
