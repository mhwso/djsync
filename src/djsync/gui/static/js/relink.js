// Relink: einen verschobenen Ordner mit seinem neuen Pfad verknüpfen.
// Playlist und Zuordnungen bleiben erhalten.
//
//   import { relinkDialog, ensureReachable } from "../relink.js";
//   const neu = await relinkDialog(folder);          // Ordner-Aktion; neuer Pfad oder null
//   const pfad = await ensureReachable(folder);      // vor dem Sync: Pfad (ggf. neu) oder null
//
// ensureReachable fragt die API, ob der Ordner erreichbar ist, und bietet sonst Relink an.

import { api, errorMessage } from "./api.js";
import { h } from "./dom.js";

// Gibt den neuen Pfad zurück oder null, wenn abgebrochen wurde.
export function relinkDialog(folder, { unreachable = false } = {}) {
  return new Promise((resolve) => {
    const input = h("input", {
      type: "text",
      class: "relink-input mono",
      placeholder: "Neuer Ordner, z. B. D:\\Musik\\Techno",
      "aria-label": "Neuer Ordner",
    });
    const error = h("p", { class: "relink-error", role: "alert", hidden: true });
    const submit = h("button", { type: "submit", class: "button primary" }, "Verknüpfen");

    const choose = h(
      "button",
      {
        type: "button",
        class: "button",
        onclick: async () => {
          try {
            const chosen = await api("relink.choose_folder", input.value || "");
            if (chosen) input.value = chosen;
          } catch (err) {
            showError(errorMessage(err));
          }
          input.focus();
        },
      },
      "Durchsuchen …",
    );

    const dialog = h(
      "dialog",
      { class: "relink-dialog", "aria-labelledby": "relink-title" },
      h(
        "form",
        { method: "dialog" },
        h("h2", { id: "relink-title" }, unreachable ? "Ordner nicht erreichbar" : "Ordner neu verknüpfen"),
        h(
          "p",
          {},
          unreachable
            ? "Dieser Ordner ist nicht erreichbar. Ist das Laufwerk eingebunden? Falls der Ordner verschoben oder umbenannt wurde, verknüpfe ihn hier mit seinem neuen Pfad."
            : "Wurde der Ordner verschoben oder umbenannt? Playlist und Zuordnungen bleiben beim Neu-Verknüpfen erhalten.",
        ),
        h("p", { class: "mono muted relink-old", title: folder }, folder),
        h("div", { class: "relink-row" }, input, choose),
        error,
        h(
          "div",
          { class: "relink-actions" },
          h("button", { type: "button", class: "button", value: "cancel", onclick: () => close(null) }, "Abbrechen"),
          submit,
        ),
      ),
    );

    function showError(message) {
      error.textContent = message;
      error.hidden = false;
    }

    function close(result) {
      dialog.close();
      dialog.remove();
      resolve(result);
    }

    dialog.querySelector("form").addEventListener("submit", async (event) => {
      event.preventDefault();
      submit.disabled = true;
      try {
        const result = await api("relink.apply", folder, input.value);
        close(result.folder);
      } catch (err) {
        showError(errorMessage(err));
        submit.disabled = false;
        input.focus();
      }
    });
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      close(null);
    });

    document.body.append(dialog);
    dialog.showModal();
    input.focus();
  });
}

// Für den Sync (#13) und den Startbildschirm: erreichbarer Pfad des Ordners oder null.
export async function ensureReachable(folder) {
  const { reachable } = await api("relink.check", folder);
  if (reachable) return folder;
  return relinkDialog(folder, { unreachable: true });
}
