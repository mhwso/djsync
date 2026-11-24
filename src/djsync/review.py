"""Interaktiver Review für ungefähre und nicht gefundene Treffer."""

from __future__ import annotations

import os
import re

from . import ui
from .db import Database
from .matching import score_candidate
from .models import MANUAL, NOT_ON_SPOTIFY, REVIEW_STATUSES, Candidate, LocalFile
from .spotify import SpotifyClient, SpotifyError

_LINK_RE = re.compile(r"(?:open\.spotify\.com/(?:intl-[a-z]+/)?track/|spotify:track:)([A-Za-z0-9]{22})")
_ID_RE = re.compile(r"^[A-Za-z0-9]{22}$")


def parse_track_link(text: str) -> str | None:
    text = text.strip()
    m = _LINK_RE.search(text)
    if m:
        return m.group(1)
    return text if _ID_RE.match(text) else None


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
                db.save_match(fp, NOT_ON_SPOTIFY, None)
                db.commit()
                changed += 1
                break
            if choice == "l":
                link = _ask("Spotify-Link: ")
                if link is None:
                    return changed
                track_id = parse_track_link(link)
                if not track_id:
                    ui.warn("Kein gültiger Track-Link.")
                    continue
                try:
                    c = client.get_track(track_id)
                except SpotifyError as e:
                    ui.warn(f"Track nicht abrufbar: {e}")
                    continue
                ui.success(fmt_candidate(c))
                candidates = [c] + [x for x in record.candidates if x.id != c.id]
                db.save_match(fp, MANUAL, c.id, candidates)
                db.commit()
                changed += 1
                break
            if choice.isdigit() and 1 <= int(choice) <= len(record.candidates):
                c = record.candidates[int(choice) - 1]
                db.save_match(fp, MANUAL, c.id)
                db.commit()
                changed += 1
                break
            ui.warn("Ungültige Eingabe.")
    return changed
