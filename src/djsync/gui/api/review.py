"""Review eines Ordners: Track-Liste mit Filtern, Detailansicht und Entscheidungen.

Die Entscheidungen selbst liegen in `djsync.review_core`; jede wird sofort gespeichert.
Review-Entscheidungen verändern die Playlist nicht, sie landen erst mit dem nächsten
bestätigten Sync dort.
"""

from __future__ import annotations

import os

from ... import review_core
from ...db import Database
from ...matching import score_candidate
from ...models import DECIDED_STATUSES, REVIEW_STATUSES
from .base import ApiArea, ApiError

TRACK_URL = "https://open.spotify.com/track/{}"


def _summary(t: review_core.ReviewTrack) -> dict:
    """Ein Eintrag der Track-Liste (links)."""
    status = t.record.status
    return {
        "fingerprint": t.fingerprint,
        "filename": os.path.basename(t.file.path),
        "artist": t.file.artist,
        "title": t.file.title,
        "status": status,
        "open": status in REVIEW_STATUSES,
        "decided": status in DECIDED_STATUSES,
    }


def _detail(t: review_core.ReviewTrack, duration_tolerance_ms: int) -> dict:
    """Die Detailansicht eines Tracks (rechts)."""
    candidates = []
    for number, c in enumerate(t.record.candidates, 1):
        score = score_candidate(t.file, c, duration_tolerance_ms)
        candidates.append(
            {
                "number": number,
                "id": c.id,
                "name": c.name,
                "artists": list(c.artists),
                "album": c.album,
                "duration_ms": c.duration_ms,
                "score": score.value,
                "duration_ok": score.duration_ok,
                "selected": c.id == t.record.spotify_id,
                "url": TRACK_URL.format(c.id),
            }
        )
    return {
        **_summary(t),
        "path": t.file.path,
        "isrc": t.file.isrc,
        "duration_ms": t.file.duration_ms,
        "spotify_id": t.record.spotify_id,
        "candidates": candidates,
    }


class ReviewApi(ApiArea):
    def tracks(self, folder: str, filter: str = review_core.OPEN) -> dict:
        """Tracks des Ordners für die Liste, nach Dateipfad sortiert.

        filter: "open" (Standard), "decided" oder "exact". Rückgabe:
          folder, filter, open_count  – Anzahl offener Tracks im Ordner (unabhängig vom Filter)
          tracks                      – je Track: fingerprint, filename, artist, title, status,
                                        open, decided
        """
        if filter not in review_core.FILTERS:
            raise ApiError(f"Unbekannter Filter: {filter}")
        with self._ctx.db() as db:
            self._check_folder(db, folder)
            tracks = review_core.review_tracks(db, folder, filter)
            return {
                "folder": folder,
                "filter": filter,
                "open_count": db.open_count(folder),
                "tracks": [_summary(t) for t in tracks],
            }

    def track(self, folder: str, fingerprint: str) -> dict:
        """Detailansicht eines Tracks (rechts). Rückgabe wie ein Listeneintrag, dazu:
          path, isrc, duration_ms   – aus der lokalen Datei (Dauer None, wenn unbekannt)
          spotify_id                – aktuelle Zuordnung oder None
          candidates                – Vorschläge in gespeicherter Reihenfolge, je Vorschlag:
                                      number (1…, Taste), id, name, artists, album, duration_ms,
                                      score (Bewertung 0…1), duration_ok, selected, url
        """
        cfg = self._ctx.load_config()
        with self._ctx.db() as db:
            return _detail(self._find(db, folder, fingerprint), cfg.duration_tolerance_ms)

    def next_open(self, folder: str, after: str | None = None) -> str | None:
        """Fingerprint des nächsten offenen Tracks nach `after` (Überspringen, Taste s).

        Ohne `after` der erste offene Track (Einstieg ins Review). Am Ende geht es vorn weiter;
        `after` selbst wird nie geliefert. None, wenn sonst nichts offen ist.
        """
        with self._ctx.db() as db:
            self._check_folder(db, folder)
            following = review_core.next_open_track(db, folder, after=after)
            return following.fingerprint if following else None

    # ---- Entscheidungen ---------------------------------------------------
    # Jede Entscheidung wird sofort gespeichert und liefert den neuen Stand:
    #   track       – Detailansicht des entschiedenen Tracks (wie `track`)
    #   open_count  – Anzahl offener Tracks im Ordner
    #   next        – Fingerprint des nächsten offenen Tracks (mit Umlauf) oder None

    def accept(self, folder: str, fingerprint: str, spotify_id: str) -> dict:
        """Übernimmt einen gespeicherten Vorschlag als Zuordnung (Taste 1–5 bzw. Klick)."""
        return self._decide(folder, fingerprint, lambda db: review_core.accept_candidate(db, fingerprint, spotify_id))

    def accept_link(self, folder: str, fingerprint: str, link: str) -> dict:
        """Ordnet den Track per Spotify-Link, -URI oder -ID zu (Taste l).

        Ungültiger oder nicht abrufbarer Link → ApiError mit klarer Meldung, nichts geändert.
        """
        client = self._ctx.spotify()
        return self._decide(folder, fingerprint, lambda db: review_core.accept_link(db, client, fingerprint, link))

    def not_on_spotify(self, folder: str, fingerprint: str) -> dict:
        """Markiert den Track als „nicht auf Spotify“ (Taste n); die Vorschläge bleiben erhalten."""
        return self._decide(folder, fingerprint, lambda db: review_core.mark_not_on_spotify(db, fingerprint))

    def reset(self, folder: str, fingerprint: str) -> dict:
        """Setzt einen entschiedenen Track auf „offen“ zurück, ohne neu zu suchen."""
        return self._decide(folder, fingerprint, lambda db: review_core.reset_to_open(db, fingerprint))

    # ---- intern -----------------------------------------------------------

    def _decide(self, folder: str, fingerprint: str, action) -> dict:
        cfg = self._ctx.load_config()
        with self._ctx.db() as db:
            self._find(db, folder, fingerprint)
            try:
                action(db)
            except review_core.ReviewError as e:
                raise ApiError(str(e)) from e
            return self._state(db, folder, fingerprint, cfg.duration_tolerance_ms)

    def _state(self, db: Database, folder: str, fingerprint: str, duration_tolerance_ms: int) -> dict:
        following = review_core.next_open_track(db, folder, after=fingerprint)
        return {
            "track": _detail(self._find(db, folder, fingerprint), duration_tolerance_ms),
            "open_count": db.open_count(folder),
            "next": following.fingerprint if following else None,
        }

    def _find(self, db: Database, folder: str, fingerprint: str) -> review_core.ReviewTrack:
        self._check_folder(db, folder)
        t = review_core.find_track(db, folder, fingerprint)
        if t is None:
            raise ApiError("Diesen Track gibt es im Ordner nicht (mehr).")
        return t

    @staticmethod
    def _check_folder(db: Database, folder: str) -> None:
        if db.get_playlist(folder) is None:
            raise ApiError("Diesen Ordner kennt djsync nicht.")
