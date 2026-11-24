"""Interaktiver Review für ungefähre und nicht gefundene Treffer (CLI).

Die Entscheidungen selbst liegen in `review_core`; hier sind nur Ein- und Ausgabe.
"""

from __future__ import annotations

import os

from . import ui
from .db import Database
from .matching import score_candidate
from .models import REVIEW_STATUSES, Candidate, LocalFile
from .review_core import (
    InvalidLinkError,
    TrackUnavailableError,
    accept_candidate,
    accept_link,
    mark_not_on_spotify,
    parse_track_link,  # noqa: F401 – bisheriger Importpfad
)
from .spotify import SpotifyClient


def fmt_duration(ms: int | None) -> str:
    if not ms:
        return " --:--"
    s = round(ms / 1000)
    return f"{s // 60:3d}:{s % 60:02d}"


def fmt_candidate(c: Candidate) -> str:
    return f"{', '.join(c.artists)} – {c.name}  {fmt_duration(c.duration_ms).strip()}"


def pending_reviews(files: list[tuple[LocalFile, str | None]], db: Database) -> list[tuple[LocalFile, str]]:
    seen: set[str] = set()
    result = []
    for f, fp in files:
        if not fp or fp in seen:
            continue
        record = db.get_match(fp)
        if record and record.status in REVIEW_STATUSES:
            seen.add(fp)
            result.append((f, fp))
    return result


def _ask(prompt: str) -> str | None:
    """Eingabe, aber None statt EOFError, wenn keine Eingabe mehr kommt."""
    try:
        return ui.ask(prompt)
    except EOFError:
        ui.info("")
        return None


def run_review(
    pending: list[tuple[LocalFile, str]], db: Database, client: SpotifyClient, *, duration_tolerance_ms: int
) -> int:
    """Gibt die Anzahl geänderter Zuordnungen zurück."""
    if not pending:
        ui.success("Nichts zu prüfen.")
        return 0
    ui.review_header(len(pending))
    changed = 0
    for i, (f, fp) in enumerate(pending, 1):
        record = db.get_match(fp)
        if record is None:
            continue
        rows = []
        for c in record.candidates:
            s = score_candidate(f, c, duration_tolerance_ms)
            rows.append((", ".join(c.artists), c.name, fmt_duration(c.duration_ms).strip(), s.value,
                         s.duration_ok, c.id == record.spotify_id))
        ui.review_track(i, len(pending), record.status, os.path.basename(f.path),
                        f"{f.artist or '?'} – {f.title or '?'}", fmt_duration(f.duration_ms).strip(), rows)
        options = f"[accent]1-{len(record.candidates)}[/] wählen · " if record.candidates else ""

        while True:
            choice = _ask(
                f"{options}[accent]l[/] Link · [accent]n[/] nicht auf Spotify · "
                "[accent]s[/] überspringen · [accent]q[/] beenden: "
            )
            if choice is None:  # Eingabe beendet (Strg+D) – wie „q“
                return changed
            choice = choice.strip().lower()
            if choice == "q":
                return changed
            if choice in ("s", ""):
                break
            if choice == "n":
                mark_not_on_spotify(db, fp)
                changed += 1
                break
            if choice == "l":
                link = _ask("Spotify-Link: ")
                if link is None:
                    return changed
                try:
                    c = accept_link(db, client, fp, link)
                except (InvalidLinkError, TrackUnavailableError) as e:
                    ui.warn(str(e))
                    continue
                ui.success(fmt_candidate(c))
                changed += 1
                break
            if choice.isdigit() and 1 <= int(choice) <= len(record.candidates):
                accept_candidate(db, fp, record.candidates[int(choice) - 1].id)
                changed += 1
                break
            ui.warn("Ungültige Eingabe.")
    return changed
