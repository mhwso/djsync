// Verzeichnis der Ansichten. Neue Ansicht: Datei in diesem Ordner anlegen, die ein Objekt
// { title, render(root, params, { navigate }) } exportiert, und hier eintragen.
// Eigene Styles gehören nach css/views/<name>.css und werden in index.html eingebunden.

import folders from "./folders.js";
import setup from "./setup.js";

export const DEFAULT_VIEW = "folders";

export const views = {
  folders,
  setup,
};
