"""Ordner: auflisten (Startbildschirm), hinzufügen, umbenennen, entfernen. Relink: siehe relink.py."""

from __future__ import annotations

import os

from ...db import Database
from ...filenames import normalize_folder
from ...spotify import SpotifyError
from ...sync import playlist_name
from .base import ApiArea, ApiError, check_folder, choose_folder

PLAYLIST_URL = "https://open.spotify.com/playlist/{}"
GONE = "Spotify kennt die Playlist nicht mehr."


def folder_entry(db: Database, row) -> dict:
    """Ein Ordner, wie ihn `FoldersApi.list()` liefert."""
    return {
        "folder": row["folder"],
        "name": row["name"],
        "playlist_id": row["playlist_id"],
        "playlist_url": PLAYLIST_URL.format(row["playlist_id"]) if row["playlist_id"] else None,
        "last_sync": row["last_sync"],
        "open_count": db.open_count(row["folder"]),
        "reachable": os.path.isdir(row["folder"]),
    }


class FoldersApi(ApiArea):
    def list(self) -> list[dict]:
        """Alle Ordner für den Startbildschirm, sortiert nach Playlist-Name.

        Die Anzahl offener Tracks ist der Stand vom letzten Sync bzw. Review; kein Ordner wird
        dafür neu eingelesen. Je Ordner:
          folder        Pfad des Ordners
          name          Playlist-Name (gewählt, auch wenn die Playlist noch nicht existiert)
          playlist_id   Spotify-ID oder None, solange noch kein Sync bestätigt wurde
          playlist_url  Link zur Playlist oder None
          last_sync     ISO-Zeitpunkt des letzten Syncs oder None (nie bzw. vor der GUI)
          open_count    Anzahl offener Tracks
          reachable     ob der Ordner gerade erreichbar ist (z. B. Laufwerk eingebunden)
        """
        with self._ctx.db() as db:
            result = [folder_entry(db, r) for r in db.all_folders()]
        return sorted(result, key=lambda e: (e["name"].casefold(), e["folder"]))

    def suggest(self, path: str) -> dict:
        """Prüft einen gewählten oder hineingezogenen Pfad, bevor der Name abgefragt wird.
        Gibt {folder, name} zurück: interner Pfad und vorgeschlagener Playlist-Name."""
        folder = normalize_folder(path)
        _check_dir(folder)
        with self._ctx.db() as db:
            _check_new(db, folder)
        return {"folder": folder, "name": playlist_name(os.path.basename(folder) or folder)}

    def choose(self) -> str | None:
        """Öffnet den Ordnerdialog des Systems. Gibt den gewählten Pfad zurück (danach
        `suggest`), None bei Abbruch. Nur in der App nutzbar, nicht in Tests."""
        return choose_folder()

    def add(self, path: str, name: str) -> dict:
        """Nimmt einen Ordner mit dem gewählten Playlist-Namen auf. Auf Spotify passiert noch
        nichts: die Playlist entsteht erst beim ersten bestätigten Sync. Gibt den Eintrag wie
        in `list()` zurück."""
        folder = normalize_folder(path)
        name = _clean_name(name)
        _check_dir(folder)
        with self._ctx.db() as db:
            _check_new(db, folder)
            db.add_folder(folder, name)
            db.commit()
            return folder_entry(db, db.get_folder(folder))

    def rename(self, folder: str, name: str) -> dict:
        """Ändert den Playlist-Namen. Existiert die Playlist schon, wird sie sofort auch auf
        Spotify umbenannt; scheitert das, bleibt der alte Name auch lokal stehen."""
        name = _clean_name(name)
        with self._ctx.db() as db:
            row = check_folder(db, folder)
            if row["playlist_id"]:
                with self._spotify("Die Playlist konnte auf Spotify nicht umbenannt werden", not_found=GONE) as client:
                    client.update_playlist(row["playlist_id"], name=name)
            db.rename_folder(folder, name)
            db.commit()
            return folder_entry(db, db.get_folder(folder))

    def remove(self, folder: str, delete_playlist: bool) -> None:
        """Entfernt den Ordner aus djsync. Die Oberfläche fragt jedes Mal, ob die Playlist auf
        Spotify bleibt (delete_playlist=False) oder entfernt wird. Zuordnungen bleiben erhalten,
        weil sie für den Track in allen Ordnern gelten."""
        with self._ctx.db() as db:
            row = check_folder(db, folder)
            if delete_playlist and row["playlist_id"]:
                with self._spotify("Die Playlist konnte auf Spotify nicht entfernt werden") as client:
                    try:
                        client.unfollow_playlist(row["playlist_id"])
                    except SpotifyError as e:
                        if e.status != 404:  # schon weg: Ziel erreicht
                            raise
            db.remove_folder(folder)
            db.commit()


def install_drop(window, events) -> None:
    """Drag & Drop von Ordnern ins Fenster. Der Browser verrät keine vollen Pfade, pywebview
    schon – aber nur auf der Python-Seite. Deshalb fängt Python das Ablegen ab und meldet die
    Pfade als Event „folders.dropped“ {paths: [...]} an die Oberfläche."""
    from webview.dom import DOMEventHandler

    def on_drop(event) -> None:
        files = (event.get("dataTransfer") or {}).get("files") or []
        paths = [f["pywebviewFullPath"] for f in files if f.get("pywebviewFullPath")]
        if paths:
            events.emit("folders.dropped", {"paths": paths})

    doc = window.dom.document
    # preventDefault bei dragover/drop, sonst öffnet das Fenster die Datei selbst
    doc.events.dragover += DOMEventHandler(lambda e: None, True, True, debounce=500)
    doc.events.drop += DOMEventHandler(on_drop, True, True)


def _check_dir(folder: str) -> None:
    if os.path.isdir(folder):
        return
    if os.path.exists(folder):
        raise ApiError(f"„{folder}“ ist kein Ordner.")
    raise ApiError(f"Der Ordner „{folder}“ existiert nicht oder ist nicht erreichbar.")


def _check_new(db: Database, folder: str) -> None:
    if db.get_folder(folder) is not None:
        raise ApiError(f"Der Ordner „{folder}“ ist schon in djsync.")


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ApiError("Bitte einen Playlist-Namen angeben.")
    return name
