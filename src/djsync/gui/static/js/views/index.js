// Verzeichnis der Ansichten. Neue Ansicht: Datei in diesem Ordner anlegen, die ein Objekt
// { title, render(root, params, { navigate }) } exportiert, und hier eintragen.
// Eigene Styles gehören nach css/views/<name>.css und werden in index.html eingebunden.

import folders from "./folders.js";
import review from "./review/index.js";
import setup from "./setup.js";
import settings from "./settings.js";
import sync from "./sync.js";

export const DEFAULT_VIEW = "folders";

export const views = {
  folders,
  review,
  setup,
  settings,
  sync,
};
