// Dialoge der Ordnerverwaltung: hinzufügen, umbenennen, entfernen.
// Jede Funktion löst mit true auf, wenn sich etwas geändert hat (Liste neu laden), sonst false.

import { api, errorMessage } from "./api.js";
import { h } from "./dom.js";

// Modaler <dialog>. actions: [{ label, primary?, danger?, run: async () => {} }]
// run darf werfen: die Meldung erscheint im Dialog, der Dialog bleibt offen.
function modal({ title, body = [], actions, cancelLabel = "Abbrechen" }) {
  return new Promise((done) => {
    const error = h("p", { class: "notice error", hidden: true });
    const buttons = actions.map((action) =>
      h(
        "button",
        {
          type: action.submit ? "submit" : "button",
          class: "button" + (action.primary ? " primary" : "") + (action.danger ? " danger" : ""),
          onclick: action.submit ? null : () => trigger(action),
        },
        action.label,
      ),
    );
    const cancel = h("button", { type: "button", class: "button", onclick: () => close(false) }, cancelLabel);
    const form = h(
      "form",
      { method: "dialog", class: "dialog-form" },
      h("h2", {}, title),
      body,
      error,
      h("div", { class: "dialog-actions" }, cancel, buttons),
    );
    const dialog = h("dialog", { class: "dialog" }, form);

    const submit = actions.find((a) => a.submit);
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      if (submit) trigger(submit);
    });
    dialog.addEventListener("cancel", (e) => {
      e.preventDefault();
      close(false);
    });

    async function trigger(action) {
      for (const b of [...buttons, cancel]) b.disabled = true;
      error.hidden = true;
      try {
        await action.run();
        close(true);
      } catch (err) {
        error.textContent = errorMessage(err);
        error.hidden = false;
        for (const b of [...buttons, cancel]) b.disabled = false;
      }
    }

    function close(changed) {
      dialog.close();
      dialog.remove();
      done(changed);
    }

    document.body.append(dialog);
    dialog.showModal();
  });
}

function nameField(value) {
  const input = h("input", { type: "text", class: "input", value, required: true, spellcheck: "false" });
  const label = h("label", { class: "field" }, h("span", {}, "Playlist-Name"), input);
  return { input, label };
}

// path: gewählter oder hineingezogener Pfad. Wird erst geprüft (vorhanden? schon in djsync?),
// danach kann der vorgeschlagene Playlist-Name geändert werden.
export async function addFolder(path) {
  let suggestion;
  try {
    suggestion = await api("folders.suggest", path);
  } catch (err) {
    await modal({
      title: "Ordner hinzufügen",
      body: [h("p", { class: "notice error" }, errorMessage(err))],
      actions: [],
      cancelLabel: "Schließen",
    });
    return false;
  }
  const { input, label } = nameField(suggestion.name);
  const result = modal({
    title: "Ordner hinzufügen",
    body: [
      h("p", { class: "mono muted dialog-path" }, suggestion.folder),
      label,
      h("p", { class: "muted" }, "Die Playlist wird erst beim ersten Sync auf Spotify angelegt."),
    ],
    actions: [
      { label: "Hinzufügen", primary: true, submit: true, run: () => api("folders.add", suggestion.folder, input.value) },
    ],
  });
  input.select();
  return result;
}

// Ordnerdialog des Systems, danach wie addFolder
export async function chooseFolder() {
  let path;
  try {
    path = await api("folders.choose");
  } catch (err) {
    alert(errorMessage(err));
    return false;
  }
  return path ? addFolder(path) : false;
}

export async function renameFolder(folder) {
  const { input, label } = nameField(folder.name);
  const result = modal({
    title: "Playlist umbenennen",
    body: [
      h("p", { class: "mono muted dialog-path" }, folder.folder),
      label,
      folder.playlist_id
        ? h("p", { class: "muted" }, "Die Playlist wird sofort auch auf Spotify umbenannt.")
        : null,
    ],
    actions: [
      { label: "Umbenennen", primary: true, submit: true, run: () => api("folders.rename", folder.folder, input.value) },
    ],
  });
  input.select();
  return result;
}

// Fragt jedes Mal, ob die Playlist auf Spotify bleibt; ohne Playlist gibt es nichts zu fragen.
export function removeFolder(folder) {
  const remove = (deletePlaylist) => () => api("folders.remove", folder.folder, deletePlaylist);
  const body = [
    h("p", {}, "„", h("strong", {}, folder.name), "“ wird aus djsync entfernt."),
    h("p", { class: "mono muted dialog-path" }, folder.folder),
    h(
      "p",
      { class: "muted" },
      "Die Zuordnungen der Tracks bleiben erhalten, weil sie für den Track in allen Ordnern gelten.",
    ),
  ];
  if (!folder.playlist_id) {
    return modal({
      title: "Ordner entfernen",
      body,
      actions: [{ label: "Entfernen", danger: true, run: remove(false) }],
    });
  }
  body.push(h("p", {}, "Was soll mit der Playlist auf Spotify passieren?"));
  return modal({
    title: "Ordner entfernen",
    body,
    actions: [
      { label: "Playlist behalten", run: remove(false) },
      { label: "Playlist auf Spotify entfernen", danger: true, run: remove(true) },
    ],
  });
}
