from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import httpx

from ...auth import AuthError
from ...config import Config, ConfigError
from ...db import Database
from ...filenames import normalize_folder
from ...spotify import SpotifyClient, SpotifyError
from ..context import AppContext


class ApiError(Exception):
    """Erwartbarer Fehler mit einer Meldung, die die Oberfläche so anzeigen kann."""


def spotify_message(e: Exception) -> str | None:
    """Verständliche Meldung für Fehler rund um Spotify (Konfiguration, Anmeldung, Netz, API).

    None, wenn der Fehler nicht dazugehört; der Aufrufer entscheidet dann selbst.
    """
    if isinstance(e, ConfigError):
        return str(e)
    if isinstance(e, AuthError):
        return "Die Anmeldung bei Spotify ist abgelaufen oder ungültig. Bitte über die Einrichtung neu anmelden."
    if isinstance(e, SpotifyError):
        if e.status == 429:  # Rate-Limit bzw. Kontingent: Meldung ist schon verständlich
            return str(e)
        if e.status in (401, 403):
            return "Spotify verweigert den Zugriff. Bitte über die Einrichtung neu anmelden."
        return f"Spotify meldet einen Fehler ({e.status or 'unbekannt'}). Bitte später erneut versuchen."
    if isinstance(e, httpx.HTTPError):
        return "Spotify ist nicht erreichbar. Besteht eine Internetverbindung?"
    return None


@contextmanager
def spotify_errors(what: str, not_found: str | None = None) -> Iterator[None]:
    """Übersetzt Fehler rund um Spotify in eine anzeigbare ApiError „<what>: <Meldung>“.

    not_found: eigene Meldung für eine 404-Antwort (z. B. „Spotify kennt die Playlist nicht mehr.“).
    """
    try:
        yield
    except ApiError:
        raise
    except Exception as e:
        if not_found and isinstance(e, SpotifyError) and e.status == 404:
            raise ApiError(f"{what}: {not_found}") from e
        message = spotify_message(e)
        if message is None:
            raise
        raise ApiError(f"{what}: {message}") from e


def internal_folder(folder: str) -> str:
    """Ordnerpfad von der Oberfläche → interne Form (siehe `normalize_folder`).

    Jede API-Methode, die einen Ordner entgegennimmt, bringt ihn hiermit (bzw. über
    `check_folder`) in die interne Form, bevor er Datenbank oder Dateisystem erreicht – so
    passt z. B. „C:\\Musik\\Mix“ unter Windows zum gespeicherten „C:/Musik/Mix“.
    """
    return normalize_folder(folder)


def check_folder(db: Database, folder: str):
    """Der gespeicherte Eintrag des Ordners; ApiError, wenn djsync ihn nicht kennt.

    `folder` darf in beliebiger Schreibweise kommen; den Pfad in interner Form liefert
    `row["folder"]` – damit weiterarbeiten.
    """
    folder = internal_folder(folder)
    row = db.get_folder(folder)
    if row is None:
        raise ApiError(f"Der Ordner „{folder}“ ist nicht in djsync.")
    return row


def check_reachable(folder: str) -> None:
    """ApiError, wenn der Ordner gerade nicht erreichbar ist (z. B. Laufwerk nicht eingebunden)."""
    if not os.path.isdir(folder):
        raise ApiError(f"Der Ordner „{folder}“ ist nicht erreichbar. Ist das Laufwerk eingebunden?")


def choose_folder(start: str = "") -> str | None:
    """Öffnet den Ordnerdialog des Systems (beginnt in `start`, falls vorhanden). Gibt den
    gewählten Pfad unverändert zurück, None bei Abbruch. Nur in der App nutzbar, nicht in Tests."""
    import webview  # erst hier: Tests und CLI brauchen pywebview nicht

    window = webview.active_window()
    if window is None:
        raise ApiError("Der Ordnerdialog ist gerade nicht verfügbar.")
    directory = start if start and os.path.isdir(start) else ""
    paths = window.create_file_dialog(webview.FileDialog.FOLDER, directory=directory)
    return paths[0] if paths else None


class ApiArea:
    """Basis für einen fachlichen Bereich der API (Ordner, Sync, Review, …)."""

    def __init__(self, ctx: AppContext):
        self._ctx = ctx

    @contextmanager
    def _spotify(self, what: str, cfg: Config | None = None, not_found: str | None = None) -> Iterator[SpotifyClient]:
        """Spotify-Client für die Dauer des Blocks; wird danach immer geschlossen. Fehler beim
        Anlegen (Konfiguration, Anmeldung) und im Block kommen als ApiError mit „<what>: …“ an."""
        with spotify_errors(what, not_found):
            client = self._ctx.spotify(cfg)
            try:
                yield client
            finally:
                client.close()
