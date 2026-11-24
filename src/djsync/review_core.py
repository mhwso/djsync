"""Entscheidungen im Review – ohne Terminal-Ein-/Ausgabe, von CLI und GUI gemeinsam genutzt.

Jede Entscheidung wird sofort in der Datenbank gespeichert.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .db import Database
from .models import (
    APPROXIMATE,
    DECIDED_STATUSES,
    EXACT,
    MANUAL,
    NOT_FOUND,
    NOT_ON_SPOTIFY,
    REVIEW_STATUSES,
    Candidate,
    LocalFile,
    MatchRecord,
)
from .spotify import SpotifyClient, SpotifyError

_LINK_RE = re.compile(r"(?:open\.spotify\.com/(?:intl-[a-z]+/)?track/|spotify:track:)([A-Za-z0-9]{22})")
_ID_RE = re.compile(r"^[A-Za-z0-9]{22}$")


# Filter für die Track-Liste im Review
OPEN = "open"  # ungefähr oder nicht gefunden
DECIDED = "decided"  # manuell oder nicht auf Spotify
EXACT_FILTER = "exact"  # exakte Treffer
FILTERS = {OPEN: REVIEW_STATUSES, DECIDED: DECIDED_STATUSES, EXACT_FILTER: frozenset({EXACT})}


@dataclass(frozen=True)
class ReviewTrack:
    """Ein Track im Review: eine seiner Dateien im Ordner samt gespeicherter Zuordnung."""

    file: LocalFile
    fingerprint: str
    record: MatchRecord


class ReviewError(Exception):
    """Eine Review-Entscheidung lässt sich nicht ausführen."""


class InvalidLinkError(ReviewError):
    """Der eingegebene Text ist kein Spotify-Track-Link."""


class TrackUnavailableError(ReviewError):
    """Der verlinkte Track lässt sich bei Spotify nicht abrufen."""


def parse_track_link(text: str) -> str | None:
    """Spotify-Track-ID aus Link, URI oder nackter ID – sonst None."""
    text = text.strip()
    m = _LINK_RE.search(text)
    if m:
        return m.group(1)
    return text if _ID_RE.match(text) else None


def _record(db: Database, fingerprint: str) -> MatchRecord:
    record = db.get_match(fingerprint)
    if record is None:
        raise ReviewError("Für diesen Track ist keine Zuordnung gespeichert.")
    return record


def accept_candidate(db: Database, fingerprint: str, spotify_id: str) -> None:
    """Übernimmt einen gespeicherten Vorschlag als Zuordnung (→ manuell)."""
    record = _record(db, fingerprint)
    if all(c.id != spotify_id for c in record.candidates):
        raise ReviewError("Kein gespeicherter Vorschlag mit dieser Spotify-ID.")
    db.save_match(fingerprint, MANUAL, spotify_id)
    db.commit()


def accept_link(db: Database, client: SpotifyClient, fingerprint: str, link: str) -> Candidate:
    """Ruft den verlinkten Track ab, reiht ihn vorn in die Vorschläge ein (→ manuell) und liefert ihn."""
    record = _record(db, fingerprint)
    track_id = parse_track_link(link)
    if not track_id:
        raise InvalidLinkError("Kein gültiger Track-Link.")
    try:
        c = client.get_track(track_id)
    except SpotifyError as e:
        raise TrackUnavailableError(f"Track nicht abrufbar: {e}") from e
    candidates = [c] + [x for x in record.candidates if x.id != c.id]
    db.save_match(fingerprint, MANUAL, c.id, candidates)
    db.commit()
    return c


def mark_not_on_spotify(db: Database, fingerprint: str) -> None:
    """Markiert den Track als „nicht auf Spotify“; die Vorschläge bleiben gespeichert."""
    _record(db, fingerprint)
    db.save_match(fingerprint, NOT_ON_SPOTIFY, None)
    db.commit()


def reset_to_open(db: Database, fingerprint: str) -> str:
    """Setzt einen entschiedenen Track auf „offen“ zurück, ohne neu zu suchen.

    Mit gespeicherten Vorschlägen wird er „ungefähr“ und der erste Vorschlag zur Zuordnung –
    wie nach einer Suche, deren Vorschläge nach Score sortiert sind. Ohne Vorschläge wird er
    „nicht gefunden“. Gibt den neuen Treffer-Status zurück.
    """
    record = _record(db, fingerprint)
    if record.status not in DECIDED_STATUSES:
        raise ReviewError("Nur entschiedene Tracks lassen sich auf „offen“ zurücksetzen.")
    if record.candidates:
        status, spotify_id = APPROXIMATE, record.candidates[0].id
    else:
        status, spotify_id = NOT_FOUND, None
    db.save_match(fingerprint, status, spotify_id)
    db.commit()
    return status


def _folder_tracks(db: Database, folder: str) -> list[ReviewTrack]:
    """Alle Tracks des Ordners mit gespeicherter Zuordnung, nach Dateipfad sortiert.

    Liegt derselbe Track mehrfach im Ordner, zählt nur seine erste Datei.
    """
    seen: set[str] = set()
    result = []
    for _path, (f, fp) in sorted(db.files_under(folder).items()):
        if not fp or fp in seen:
            continue
        record = db.get_match(fp)
        if record is None:
            continue
        seen.add(fp)
        result.append(ReviewTrack(f, fp, record))
    return result


def review_tracks(db: Database, folder: str, filter: str = OPEN) -> list[ReviewTrack]:
    """Tracks des Ordners, deren Treffer-Status zum Filter (OPEN, DECIDED, EXACT_FILTER) passt."""
    if filter not in FILTERS:
        raise ValueError(f"Unbekannter Filter: {filter}")
    statuses = FILTERS[filter]
    return [t for t in _folder_tracks(db, folder) if t.record.status in statuses]


def next_open_track(db: Database, folder: str, after: str | None = None) -> ReviewTrack | None:
    """Nächster offener Track nach dem Track mit Fingerprint `after`, am Ende geht es vorn weiter.

    Der Track `after` selbst wird nie geliefert; None, wenn sonst nichts mehr offen ist.
    """
    tracks = _folder_tracks(db, folder)
    start = next((i + 1 for i, t in enumerate(tracks) if t.fingerprint == after), 0)
    for t in tracks[start:] + tracks[:start]:
        if t.fingerprint != after and t.record.status in REVIEW_STATUSES:
            return t
    return None
