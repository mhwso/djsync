"""Interaktiver Review für ungefähre und nicht gefundene Treffer."""

from __future__ import annotations

import os
import re

from .db import Database
from .matching import score_candidate
from .models import APPROXIMATE, MANUAL, NOT_ON_SPOTIFY, REVIEW_STATUSES, Candidate, LocalFile
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
    """input(), aber None statt EOFError, wenn keine Eingabe mehr kommt."""
    try:
        return input(prompt)
    except EOFError:
        print()
        return None


def run_review(
    pending: list[tuple[LocalFile, str]], db: Database, client: SpotifyClient, *, duration_tolerance_ms: int
) -> int:
    """Gibt die Anzahl geänderter Zuordnungen zurück."""
    if not pending:
        print("Nichts zu prüfen.")
        return 0
    print(f"\nReview: {len(pending)} Tracks prüfen.\n")
    changed = 0
    for i, (f, fp) in enumerate(pending, 1):
        record = db.get_match(fp)
        if record is None:
            continue
        label = "~ ungefähr" if record.status == APPROXIMATE else "✗ nicht gefunden"
        print(f"[{i}/{len(pending)}] {label}")
        print(f"  Datei: {os.path.basename(f.path)}")
        print(f"  Tags:  {f.artist or '?'} – {f.title or '?'}  {fmt_duration(f.duration_ms).strip()}")
        for n, c in enumerate(record.candidates, 1):
            s = score_candidate(f, c, duration_tolerance_ms)
            marker = "  ← aktuell" if c.id == record.spotify_id else ""
            print(f"   {n}) {fmt_candidate(c)}  [{s.value:.2f}]{marker}")
        options = f"1-{len(record.candidates)} / " if record.candidates else ""

        while True:
            choice = _ask(f"  Auswahl [{options}l=Link / n=nicht auf Spotify / s=überspringen / q=beenden]: ")
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
                link = _ask("  Spotify-Link: ")
                if link is None:
                    return changed
                track_id = parse_track_link(link)
                if not track_id:
                    print("  Kein gültiger Track-Link.")
                    continue
                try:
                    c = client.get_track(track_id)
                except SpotifyError as e:
                    print(f"  Track nicht abrufbar: {e}")
                    continue
                print(f"  → {fmt_candidate(c)}")
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
            print("  Ungültige Eingabe.")
        print()
    return changed
