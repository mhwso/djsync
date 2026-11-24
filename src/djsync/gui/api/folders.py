"""Ordner: auflisten (Startbildschirm). Hinzufügen, Umbenennen, Entfernen und Relink folgen."""

from __future__ import annotations

import os

from .base import ApiArea

PLAYLIST_URL = "https://open.spotify.com/playlist/{}"


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
            rows = db.all_folders()
            result = [
                {
                    "folder": r["folder"],
                    "name": r["name"],
                    "playlist_id": r["playlist_id"],
                    "playlist_url": PLAYLIST_URL.format(r["playlist_id"]) if r["playlist_id"] else None,
                    "last_sync": r["last_sync"],
                    "open_count": db.open_count(r["folder"]),
                    "reachable": os.path.isdir(r["folder"]),
                }
                for r in rows
            ]
        return sorted(result, key=lambda e: (e["name"].casefold(), e["folder"]))
