from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import REVIEW_STATUSES, Candidate, LocalFile, MatchRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path        TEXT PRIMARY KEY,
    size        INTEGER NOT NULL,
    mtime       REAL NOT NULL,
    artist      TEXT,
    title       TEXT,
    isrc        TEXT,
    duration_ms INTEGER,
    fingerprint TEXT
);
CREATE INDEX IF NOT EXISTS files_fingerprint ON files(fingerprint);

CREATE TABLE IF NOT EXISTS matches (
    fingerprint TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    spotify_id  TEXT,
    candidates  TEXT NOT NULL DEFAULT '[]',
    searched_at TEXT NOT NULL
);

-- Ein Ordner kann vor dem ersten Sync existieren: Playlist-Name gewählt, playlist_id noch NULL.
-- Die Playlist wird erst beim ersten bestätigten Sync auf Spotify angelegt.
CREATE TABLE IF NOT EXISTS folders (
    folder      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    playlist_id TEXT UNIQUE,
    created_at  TEXT NOT NULL,
    last_sync   TEXT
);

CREATE TABLE IF NOT EXISTS managed_tracks (
    playlist_id TEXT NOT NULL,
    spotify_id  TEXT NOT NULL,
    PRIMARY KEY (playlist_id, spotify_id)
);
"""

SCHEMA_VERSION = 1


def _migrate(conn: sqlite3.Connection) -> None:
    """Bringt eine bestehende Datenbank auf SCHEMA_VERSION (PRAGMA user_version)."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        # Version 0: Ordner gab es nur über die Tabelle playlists mit Pflicht-playlist_id.
        # Der Zeitpunkt des letzten Syncs ist dort nicht bekannt und bleibt leer.
        has_old = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'playlists'"
        ).fetchone()
        if has_old:
            conn.execute(
                """INSERT OR IGNORE INTO folders (folder, name, playlist_id, created_at, last_sync)
                   SELECT folder, name, playlist_id, created_at, NULL FROM playlists"""
            )
            conn.execute("DROP TABLE playlists")
        conn.execute("PRAGMA user_version = 1")
    conn.commit()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _like_prefix(folder: str) -> str:
    escaped = folder.rstrip("/").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return escaped + "/%"


class Database:
    def __init__(self, path: Path | str):
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        _migrate(self.conn)

    def close(self) -> None:
        self.conn.close()

    # ---- files -----------------------------------------------------------

    def files_under(self, folder: str) -> dict[str, tuple[LocalFile, str | None]]:
        rows = self.conn.execute(
            "SELECT * FROM files WHERE path LIKE ? ESCAPE '\\'", (_like_prefix(folder),)
        )
        return {r["path"]: (_row_to_file(r), r["fingerprint"]) for r in rows}

    def upsert_file(self, f: LocalFile, fingerprint: str | None) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO files
               (path, size, mtime, artist, title, isrc, duration_ms, fingerprint)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (f.path, f.size, f.mtime, f.artist, f.title, f.isrc, f.duration_ms, fingerprint),
        )

    def delete_files(self, paths) -> None:
        self.conn.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in paths])

    def move_files(self, old_folder: str, new_folder: str) -> int:
        old = old_folder.rstrip("/")
        new = new_folder.rstrip("/")
        cur = self.conn.execute(
            "UPDATE OR REPLACE files SET path = ? || substr(path, ?) WHERE path LIKE ? ESCAPE '\\'",
            (new, len(old) + 1, _like_prefix(old)),
        )
        return cur.rowcount

    # ---- matches ---------------------------------------------------------

    def get_match(self, fingerprint: str) -> MatchRecord | None:
        r = self.conn.execute("SELECT * FROM matches WHERE fingerprint = ?", (fingerprint,)).fetchone()
        if not r:
            return None
        return MatchRecord(
            fingerprint=r["fingerprint"],
            status=r["status"],
            spotify_id=r["spotify_id"],
            candidates=[Candidate.from_dict(d) for d in json.loads(r["candidates"])],
            searched_at=r["searched_at"],
        )

    def save_match(
        self,
        fingerprint: str,
        status: str,
        spotify_id: str | None,
        candidates: list[Candidate] | None = None,
    ) -> None:
        if candidates is None:
            existing = self.get_match(fingerprint)
            candidates = existing.candidates if existing else []
        self.conn.execute(
            """INSERT OR REPLACE INTO matches (fingerprint, status, spotify_id, candidates, searched_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                fingerprint,
                status,
                spotify_id,
                json.dumps([c.to_dict() for c in candidates], ensure_ascii=False),
                now_iso(),
            ),
        )

    # ---- Ordner und Playlists ------------------------------------------------

    def get_playlist(self, folder: str) -> sqlite3.Row | None:
        """Der Ordner-Eintrag (folder, name, playlist_id, created_at, last_sync), auch ohne Playlist."""
        return self.conn.execute("SELECT * FROM folders WHERE folder = ?", (folder,)).fetchone()

    def all_playlists(self) -> list[sqlite3.Row]:
        """Ordner, deren Playlist schon auf Spotify existiert."""
        return list(self.conn.execute("SELECT * FROM folders WHERE playlist_id IS NOT NULL ORDER BY folder"))

    def all_folders(self) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM folders ORDER BY folder"))

    def save_playlist(self, folder: str, playlist_id: str, name: str) -> None:
        self.conn.execute(
            """INSERT INTO folders (folder, name, playlist_id, created_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(folder) DO UPDATE SET name = excluded.name, playlist_id = excluded.playlist_id""",
            (folder, name, playlist_id, now_iso()),
        )

    def mark_synced(self, folder: str) -> None:
        self.conn.execute("UPDATE folders SET last_sync = ? WHERE folder = ?", (now_iso(), folder))

    def open_count(self, folder: str) -> int:
        """Anzahl offener Tracks (ungefähr, nicht gefunden) im Ordner – Stand der Datenbank, ohne Einlesen."""
        placeholders = ", ".join("?" * len(REVIEW_STATUSES))
        return self.conn.execute(
            f"""SELECT COUNT(DISTINCT f.fingerprint) FROM files f
                JOIN matches m ON m.fingerprint = f.fingerprint
                WHERE f.path LIKE ? ESCAPE '\\' AND m.status IN ({placeholders})""",
            (_like_prefix(folder), *sorted(REVIEW_STATUSES)),
        ).fetchone()[0]

    def relink_playlist(self, old_folder: str, new_folder: str) -> bool:
        cur = self.conn.execute(
            "UPDATE folders SET folder = ? WHERE folder = ?", (new_folder, old_folder)
        )
        return cur.rowcount > 0

    def managed_tracks(self, playlist_id: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT spotify_id FROM managed_tracks WHERE playlist_id = ?", (playlist_id,)
        )
        return {r[0] for r in rows}

    def set_managed_tracks(self, playlist_id: str, spotify_ids) -> None:
        self.conn.execute("DELETE FROM managed_tracks WHERE playlist_id = ?", (playlist_id,))
        self.conn.executemany(
            "INSERT INTO managed_tracks (playlist_id, spotify_id) VALUES (?, ?)",
            [(playlist_id, s) for s in dict.fromkeys(spotify_ids)],
        )

    def commit(self) -> None:
        self.conn.commit()


def _row_to_file(r: sqlite3.Row) -> LocalFile:
    return LocalFile(
        path=r["path"],
        size=r["size"],
        mtime=r["mtime"],
        artist=r["artist"],
        title=r["title"],
        isrc=r["isrc"],
        duration_ms=r["duration_ms"],
    )
