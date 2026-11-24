"""Der Sync in einzelnen Phasen – ohne Terminal-Ein-/Ausgabe, nutzbar von CLI und GUI.

1. prepare        = read_folder + load_playlist + search_tracks
   read_folder    Ordner einlesen (lokal)
   load_playlist  aktuellen Stand der Playlist von Spotify laden (nur lesend, mit Schutz bei leerem Ordner)
   search_tracks  Tracks auf Spotify suchen
2. summarize_run  Zusammenfassung nach Treffer-Status samt offenen Tracks
3. plan_changes   Änderungsplan berechnen (beliebig oft, z. B. nach dem Review)
4. apply_changes  Änderungsplan übernehmen – erst hier wird die Playlist auf Spotify verändert
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from .config import Config
from .db import Database
from .models import LocalFile
from .plan import Plan
from .review import pending_reviews
from .scanner import scan_folder
from .spotify import SpotifyClient
from .sync import (
    build_plan,
    description_text,
    match_files,
    playlist_files,
    playlist_name,
    summarize,
)

# Fortschritt: (Schritt, erledigt, gesamt) mit Schritt „scan“, „playlist“ oder „search“; gesamt 0 = unbestimmt
ProgressFn = Callable[[str, int, int], None]
# Abbruch: liefert True, sobald der Sync abgebrochen werden soll (z. B. threading.Event.is_set)
CancelFn = Callable[[], bool]


class SyncCancelled(Exception):
    """Der Sync wurde abgebrochen; die Playlist auf Spotify ist unverändert."""


class EmptyFolderError(Exception):
    """Schutz: Der Ordner ist leer, die Playlist aber nicht – der Sync würde sie leeren."""

    def __init__(self) -> None:
        super().__init__(
            "Der Ordner enthält keine Audiodateien, die Playlist aber schon.\n"
            "Abbruch, um die Playlist nicht versehentlich zu leeren."
        )


@dataclass
class SyncRun:
    """Zustand eines Syncs zwischen den Phasen."""

    folder: str
    files: list[tuple[LocalFile, str | None]]  # (Datei, Fingerprint)
    playlist_id: str | None  # None → Playlist wird beim Übernehmen neu angelegt
    playlist_name: str | None  # aktueller Name auf Spotify
    current: list[str]  # Tracks aktuell in der Playlist
    playlist_lost: bool = False  # verknüpfte Playlist existiert auf Spotify nicht mehr
    found: int = 0  # Audiodateien im Ordner
    fresh: int = 0  # davon neu eingelesen


@dataclass(frozen=True)
class SyncSummary:
    groups: dict[str, list[LocalFile]]  # Treffer-Status → Dateien
    pending: list[tuple[LocalFile, str]]  # offene Tracks (Datei, Fingerprint), je Track einmal


@dataclass(frozen=True)
class ChangePlan:
    """Änderungsplan samt allem, was zum Anzeigen und Übernehmen nötig ist."""

    plan: Plan
    labels: dict[str, str]  # Spotify-ID → Dateiname
    new_name: str | None  # Name der neu anzulegenden Playlist, sonst None
    rename: str | None  # neuer Name einer bestehenden Playlist, sonst None

    @property
    def needs_write(self) -> bool:
        return self.plan.has_changes or self.new_name is not None


def _noop(step: str, done: int, total: int) -> None:
    pass


def _checker(cancel: CancelFn | None) -> Callable[[], None]:
    def check() -> None:
        if cancel and cancel():
            raise SyncCancelled()

    return check


def read_folder(
    folder: str,
    db: Database,
    cfg: Config,
    *,
    on_progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
) -> SyncRun:
    """Phase 1a: Ordner einlesen (nur lokal, ohne Spotify).

    Raises:
        SyncCancelled: Abbruch über cancel.
    """
    report = on_progress or _noop
    check = _checker(cancel)

    def scan_progress(done: int, total: int) -> None:
        check()
        report("scan", done, total)

    scan = scan_folder(folder, db, cfg.extensions, scan_progress)
    return SyncRun(
        folder=folder,
        files=scan.files,
        playlist_id=None,
        playlist_name=None,
        current=[],
        found=scan.found,
        fresh=scan.fresh,
    )


def load_playlist(
    run: SyncRun,
    db: Database,
    client: SpotifyClient,
    *,
    on_progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
) -> None:
    """Phase 1b: aktuellen Stand der verknüpften Playlist von Spotify laden (nur lesend).

    Existiert sie auf Spotify nicht mehr, wird sie beim Übernehmen neu angelegt (run.playlist_lost).

    Raises:
        EmptyFolderError: Ordner leer, Playlist aber nicht (Schutz vor versehentlichem Leeren).
        SyncCancelled: Abbruch über cancel.
    """
    report = on_progress or _noop
    check = _checker(cancel)
    row = db.get_playlist(run.folder)
    playlist_id = row["playlist_id"] if row else None
    playlist = None
    current: list[str] = []
    if playlist_id:
        report("playlist", 0, 0)
        check()
        playlist = client.get_playlist(playlist_id)
        if playlist is None:
            playlist_id = None
        else:
            check()
            current = client.playlist_track_ids(playlist_id)
    run.playlist_id = playlist_id
    run.playlist_name = (playlist or {}).get("name")
    run.current = current
    run.playlist_lost = row is not None and playlist_id is None
    if not run.files and playlist_id and db.managed_tracks(playlist_id) & set(current):
        raise EmptyFolderError()


def search_tracks(
    run: SyncRun,
    db: Database,
    client: SpotifyClient,
    cfg: Config,
    *,
    retry: bool = False,
    on_progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
) -> int:
    """Phase 1c: Tracks auf Spotify suchen; gibt die Anzahl gesuchter Tracks zurück.

    Jede Zuordnung wird sofort gespeichert. Ein Abbruch (SyncCancelled) ist vor jeder
    Spotify-Anfrage möglich und lässt die Playlist unverändert.
    """
    report = on_progress or _noop
    return match_files(
        run.files,
        db,
        client,
        cfg,
        retry=retry,
        on_progress=lambda done, total: report("search", done, total),
        before_request=_checker(cancel),
    )


def prepare(
    folder: str,
    db: Database,
    client: SpotifyClient,
    cfg: Config,
    *,
    retry: bool = False,
    on_progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
) -> SyncRun:
    """Phase 1 komplett: einlesen, Playlist laden, Tracks suchen. Ändert nichts auf Spotify."""
    run = read_folder(folder, db, cfg, on_progress=on_progress, cancel=cancel)
    load_playlist(run, db, client, on_progress=on_progress, cancel=cancel)
    search_tracks(run, db, client, cfg, retry=retry, on_progress=on_progress, cancel=cancel)
    return run


def summarize_run(run: SyncRun, db: Database) -> SyncSummary:
    """Phase 2: Zusammenfassung nach Treffer-Status samt offenen Tracks (aus der Datenbank)."""
    return SyncSummary(summarize(run.files, db), pending_reviews(run.files, db))


def plan_changes(run: SyncRun, db: Database, name: str | None = None) -> ChangePlan:
    """Phase 3: Änderungsplan aus den aktuellen Zuordnungen – beliebig oft, ohne Spotify-Anfragen.

    name: gewünschter Playlist-Name (Präfix wird ergänzt); bei einer neuen Playlist sonst der Ordnername.
    """
    plan = build_plan(run.files, db, run.current, run.playlist_id)
    labels = {sid: os.path.basename(f.path) for f, sid in playlist_files(run.files, db)}
    if run.playlist_id is None:
        return ChangePlan(plan, labels, playlist_name(name or os.path.basename(run.folder)), None)
    wanted = playlist_name(name) if name else None
    rename = wanted if wanted and wanted != run.playlist_name else None
    return ChangePlan(plan, labels, None, rename)


def apply_changes(run: SyncRun, change: ChangePlan, db: Database, client: SpotifyClient) -> str:
    """Phase 4: Änderungsplan übernehmen – Playlist anlegen bzw. angleichen; gibt die Playlist-ID zurück."""
    playlist_id = run.playlist_id
    if playlist_id is None:
        playlist_id = client.create_playlist(change.new_name, description_text(), public=False)
        db.save_playlist(run.folder, playlist_id, change.new_name)
        db.commit()
        run.playlist_id, run.playlist_name = playlist_id, change.new_name
    else:
        client.update_playlist(playlist_id, name=change.rename, description=description_text())
    if change.plan.has_changes:
        client.replace_playlist_items(playlist_id, change.plan.final)
    db.set_managed_tracks(playlist_id, change.plan.desired)
    db.commit()
    return playlist_id
