"""Die Python-API-Schicht der GUI – die einzige Grenze zwischen Oberfläche und Kern.

pywebview stellt das `Api`-Objekt dem JS-Teil als `window.pywebview.api` bereit. Jeder
fachliche Bereich ist ein eigenes Unterobjekt mit eigener Datei in diesem Paket, im JS also
z. B. `pywebview.api.folders.list()`.

Neuer Bereich: Datei `<bereich>.py` mit einer Unterklasse von `ApiArea` anlegen und unten in
`Api.__init__` als Attribut eintragen. Neue Methode: öffentliche Methode im passenden Bereich.

Konventionen:
- Rückgabewerte sind JSON-fähig (dict, list, str, int, float, bool, None), Zeitpunkte als
  ISO-8601-Text, Pfade in der internen Form mit „/“.
- Erwartbare Fehler werden als `ApiError` mit deutscher, anzeigbarer Meldung geworfen. Im JS
  lehnt pywebview das Promise dann mit `{name: "ApiError", message}` ab.
- Langlaufende Vorgänge melden Fortschritt über `self._ctx.events.emit(...)`.
- Attribute und Methoden mit „_“ am Anfang sieht der JS-Teil nicht.
"""

from __future__ import annotations

from ..context import AppContext
from .base import ApiArea, ApiError
from .folders import FoldersApi
from .setup import SetupApi

__all__ = ["Api", "ApiArea", "ApiError"]


class Api:
    def __init__(self, ctx: AppContext):
        self._ctx = ctx
        self.folders = FoldersApi(ctx)
        self.setup = SetupApi(ctx)
