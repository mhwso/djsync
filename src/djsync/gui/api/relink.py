"""Relink: nicht erreichbare Ordner erkennen und mit einem neuen Pfad verknüpfen.

Die Oberfläche bietet Relink als Ordner-Aktion an und automatisch, wenn ein Ordner nicht
erreichbar ist – auf dem Startbildschirm und vor dem Sync (`check` aufrufen, siehe
static/js/relink.js).
"""

from __future__ import annotations

import os

from ...filenames import normalize_folder
from ...relink import RelinkError, relink_folder
from .base import ApiArea, ApiError


class RelinkApi(ApiArea):
    def check(self, folder: str) -> dict:
        """{folder, reachable}: ob der Ordner gerade erreichbar ist (z. B. vor dem Sync)."""
        return {"folder": folder, "reachable": os.path.isdir(folder)}

    def apply(self, folder: str, new_folder: str) -> dict:
        """Verknüpft `folder` mit `new_folder` (Eingabe wie im Explorer, z. B. „D:\\Musik“).

        Gibt {folder: neuer Pfad in interner Form, moved: Anzahl übernommener Dateien} zurück.
        """
        new = normalize_folder(new_folder) if new_folder.strip() else ""
        if not new:
            raise ApiError("Bitte einen neuen Ordner angeben.")
        with self._ctx.db() as db:
            try:
                moved = relink_folder(db, folder, new)
            except RelinkError as e:
                raise ApiError(str(e)) from None
        return {"folder": new, "moved": moved}

    def choose_folder(self, start: str = "") -> str | None:
        """Öffnet den Ordner-Dialog des Systems; gibt den gewählten Pfad zurück oder None."""
        import webview  # nur in der App vorhanden

        window = webview.windows[0] if webview.windows else None
        if window is None:
            return None
        directory = start if start and os.path.isdir(start) else ""
        result = window.create_file_dialog(webview.FileDialog.FOLDER, directory=directory)
        return normalize_folder(result[0], wsl=False) if result else None
