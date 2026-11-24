"""Matching gegen Spotify und Abgleich Ordner → Playlist."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from .config import Config
from .db import Database
from .matching import choose_best, parse_title, split_artists
from .models import (
    APPROXIMATE,
    EXACT,
    MANUAL,
    NOT_FOUND,
    NOT_ON_SPOTIFY,
    PLAYLIST_STATUSES,
    Candidate,
    LocalFile,
    MatchRecord,
)
from .plan import Plan, compute_plan, desired_order
from .spotify import SpotifyClient

SETTLED = frozenset({EXACT, APPROXIMATE, MANUAL, NOT_ON_SPOTIFY})


def search_candidates(client: SpotifyClient, f: LocalFile, cfg: Config) -> list[Candidate]:
    """ISRC-Suche, danach Feldsuche, danach Freitext – bricht ab, sobald ein exakter Treffer da ist."""
    found: dict[str, Candidate] = {}

    def run(query: str) -> bool:
        for c in client.search_tracks(query):
            found.setdefault(c.id, c)
        result = choose_best(f, list(found.values()), duration_tolerance_ms=cfg.duration_tolerance_ms)
        return result.status == EXACT

    if f.isrc and run(f"isrc:{f.isrc.strip()}"):
        return list(found.values())

    p = parse_title(f.title or "")
    artists = split_artists(f.artist or "") + p.featured
    base = _clean(p.base)
    if not base:
        return list(found.values())
    primary = _clean(artists[0]) if artists else ""

    if primary and run(f'track:"{base}" artist:"{primary}"'):
        return list(found.values())
    run(" ".join(x for x in (primary, base, _clean(p.mix)) if x))
    return list(found.values())


def _clean(s: str) -> str:
    return s.replace('"', " ").strip()


def needs_search(record: MatchRecord | None, cfg: Config) -> bool:
    if record is None:
        return True
    if record.status in SETTLED:
        return False
    # nicht gefunden: nach einer Weile erneut suchen, Spotifys Katalog wächst
    try:
        searched = datetime.fromisoformat(record.searched_at or "")
    except ValueError:
        return True
    return datetime.now(timezone.utc) - searched > timedelta(days=cfg.retry_missing_days)


def match_files(
    files: list[tuple[LocalFile, str | None]], db: Database, client: SpotifyClient, cfg: Config
) -> None:
    todo: dict[str, LocalFile] = {}
    for f, fp in files:
        if fp and fp not in todo and needs_search(db.get_match(fp), cfg):
            todo[fp] = f
    if not todo:
        return
    for i, (fp, f) in enumerate(todo.items(), 1):
        if sys.stderr.isatty():
            print(f"\rSuche auf Spotify … {i}/{len(todo)}", end="", file=sys.stderr, flush=True)
        candidates = search_candidates(client, f, cfg)
        result = choose_best(
            f, candidates, duration_tolerance_ms=cfg.duration_tolerance_ms, min_score=cfg.min_score
        )
        top = [c for c, _ in result.ranked[: cfg.review_candidates]]
        db.save_match(fp, result.status, result.spotify_id, top)
        db.commit()
    if sys.stderr.isatty():
        print("\r\033[K", end="", file=sys.stderr)
    print(f"{len(todo)} Tracks auf Spotify gesucht.")


def summarize(files: list[tuple[LocalFile, str | None]], db: Database) -> dict[str, list[LocalFile]]:
    groups: dict[str, list[LocalFile]] = {s: [] for s in (EXACT, APPROXIMATE, MANUAL, NOT_FOUND, NOT_ON_SPOTIFY)}
    for f, fp in files:
        record = db.get_match(fp) if fp else None
        groups[record.status if record else NOT_FOUND].append(f)
    return groups


def playlist_files(files: list[tuple[LocalFile, str | None]], db: Database) -> list[tuple[LocalFile, str]]:
    result = []
    for f, fp in files:
        record = db.get_match(fp) if fp else None
        if record and record.status in PLAYLIST_STATUSES and record.spotify_id:
            result.append((f, record.spotify_id))
    return result


def build_plan(
    files: list[tuple[LocalFile, str | None]], db: Database, current: list[str], playlist_id: str | None
) -> Plan:
    desired = desired_order(playlist_files(files, db))
    managed = db.managed_tracks(playlist_id) if playlist_id else set()
    return compute_plan(desired, current, managed)


def description_text() -> str:
    return f"DJ Sync · zuletzt aktualisiert {datetime.now().date().isoformat()}"
