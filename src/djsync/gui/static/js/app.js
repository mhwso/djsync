// Einstieg der Oberfläche: einfacher Router über den Hash der Adresse.
//
//   #/folders                    → Ansicht "folders"
//   #/review?folder=D:/Musik     → Ansicht "review" mit params.folder
//
// Ansichten liegen in js/views/ und werden in js/views/index.js eingetragen.

import { h } from "./dom.js";
import { views, DEFAULT_VIEW } from "./views/index.js";

const root = document.getElementById("view");
let cleanup = null;

// Ansichten bekommen navigate über ihr drittes render-Argument (kein Import von app.js)
function navigate(name, params = {}) {
  const query = new URLSearchParams(params).toString();
  location.hash = `#/${name}${query ? "?" + query : ""}`;
}

function parseHash() {
  const [path, query] = location.hash.replace(/^#\/?/, "").split("?");
  return { name: path || DEFAULT_VIEW, params: Object.fromEntries(new URLSearchParams(query ?? "")) };
}

async function render() {
  const { name, params } = parseHash();
  const view = views[name];
  if (typeof cleanup === "function") cleanup();
  cleanup = null;
  root.replaceChildren();
  if (!view) {
    root.append(h("p", { class: "notice error" }, `Unbekannte Ansicht: ${name}`));
    return;
  }
  document.title = view.title ? `${view.title} – djsync` : "djsync";
  // render darf eine Aufräumfunktion zurückgeben (z. B. Event-Abmeldungen)
  cleanup = await view.render(root, params, { navigate });
  root.focus();
}

window.addEventListener("hashchange", render);
render();
