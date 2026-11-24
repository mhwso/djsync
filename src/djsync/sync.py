"""Matching gegen Spotify und Abgleich Ordner → Playlist."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from .config import Config
from .db import Database
from .matching import choose_best, normalize_mix, split_artists_raw, split_title
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


def search_candidates(
    client: SpotifyClient, f: LocalFile, cfg: Config, before_request: Callable[[], None] | None = None
) -> list[Candidate]:
    """ISRC-Suche, danach Feldsuche, danach Freitext – bricht ab, sobald ein exakter Treffer da ist.

    before_request wird vor jeder Spotify-Anfrage aufgerufen; eine Ausnahme daraus bricht die Suche ab.
    """
    found: dict[str, Candidate] = {}

    def run(query: str) -> bool:
        if before_request:
            before_request()
        for c in client.search_tracks(query):
            found.setdefault(c.id, c)
        result = choose_best(f, list(found.values()), duration_tolerance_ms=cfg.duration_tolerance_ms)
        return result.status == EXACT

    if f.isrc and run(f"isrc:{f.isrc.strip()}"):
        return list(found.values())

    # Suchanfragen in Original-Schreibweise – normalisiert würde z. B. aus „&ME“ nur „me“
    t = split_title(f.title or "")
    base = _clean(t.base)
    if not base:
        return list(found.values())
    artists = split_artists_raw(f.artist or "") + t.featured
    primary = _clean(artists[0]) if artists else ""
    mix = _clean(t.mix) if normalize_mix(t.mix) else ""  # „Original Mix“ hilft der Suche nicht

    queries = []
    if primary:
        queries.append(f'track:"{base}" artist:"{primary}"')
    queries.append(" ".join(x for x in (primary, base) if x))
    if mix:
        queries.append(" ".join(x for x in (primary, base, mix) if x))
    for q in queries:
        if run(q):
            break
    return list(found.values())


PLAYLIST_PREFIX = "DJSYNC - "


def playlist_name(name: str) -> str:
    """„2026“ → „DJSYNC - 2026“; ein bereits vorhandenes Präfix wird nicht verdoppelt."""
    name = name.strip()
    if name.upper().startswith(PLAYLIST_PREFIX.strip().upper()):
        return name
    return PLAYLIST_PREFIX + name


def _clean(s: str) -> str:
    return s.replace('"', " ").strip()


# per `sync --retry` sofort neu suchbar; manuelle Entscheidungen bleiben unangetastet
RETRYABLE = frozenset({NOT_FOUND, APPROXIMATE})


def needs_search(record: MatchRecord | None, cfg: Config, retry: bool = False) -> bool:
    if record is None:
        return True
    if retry and record.status in RETRYABLE:
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
    files: list[tuple[LocalFile, str | None]],
    db: Database,
    client: SpotifyClient,
    cfg: Config,
    retry: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
    before_request: Callable[[], None] | None = None,
) -> int:
    """Sucht alle Tracks auf Spotify, die (erneut) gesucht werden müssen; gibt deren Anzahl zurück.

    on_progress(erledigt, gesamt) kommt einmal vorab (0, gesamt) und nach jedem Track.
    Jeder Track wird sofort gespeichert – ein Abbruch über before_request verliert nichts.
    """
    todo: dict[str, LocalFile] = {}
    for f, fp in files:
        if fp and fp not in todo and needs_search(db.get_match(fp), cfg, retry):
            todo[fp] = f
    if not todo:
        return 0
    report = on_progress or (lambda done, total: None)
    report(0, len(todo))
    for i, (fp, f) in enumerate(todo.items(), 1):
        candidates = search_candidates(client, f, cfg, before_request)
        result = choose_best(
            f, candidates, duration_tolerance_ms=cfg.duration_tolerance_ms, min_score=cfg.min_score
        )
        top = [c for c, _ in result.ranked[: cfg.review_candidates]]
        db.save_match(fp, result.status, result.spotify_id, top)
        db.commit()
        report(i, len(todo))
    return len(todo)


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
