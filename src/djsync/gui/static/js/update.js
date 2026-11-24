// Update-Hinweis: Beim Start fragt die Oberfläche einmal nach einem neueren GitHub-Release
// (updates.check). Gibt es eins, erscheint unter der Kopfzeile ein schmaler Hinweis mit Link zum
// Release. Er blockiert nichts und lässt sich schließen. Fehler werden ignoriert – die
// API-Schicht liefert dann ohnehin null.

import { api } from "./api.js";
import { h } from "./dom.js";

export async function showUpdateNotice() {
  let update;
  try {
    update = await api("updates.check");
  } catch (err) {
    console.warn("Update-Prüfung fehlgeschlagen", err);
    return;
  }
  if (!update) return;

  const banner = h(
    "div",
    { class: "update-notice", role: "status" },
    h(
      "span",
      {},
      h("strong", {}, `djsync ${update.version} ist verfügbar`),
      h("span", { class: "muted" }, ` (installiert: ${update.current}). `),
      // target=_blank öffnet pywebview im System-Browser
      h("a", { href: update.url, target: "_blank" }, "Zum Release mit dem Installer"),
    ),
    h(
      "button",
      { class: "update-close", type: "button", title: "Hinweis schließen", "aria-label": "Hinweis schließen", onClick: () => banner.remove() },
      "×",
    ),
  );
  document.querySelector(".app-header")?.after(banner);
}
