"""Startbildschirm: Ordnerliste über die API-Schicht der GUI."""

import sqlite3

from fake_spotify import track

from djsync.filenames import normalize_folder


def test_no_folders_yet(api):
    assert api.folders.list() == []


def _mix_folder(music, spotify):
    """Ordner mit je einem exakten, einem ungefähren und einem nicht gefundenen Track."""
    spotify.catalog += [track("id_one", "Alpha", "One"), track("id_two", "Alpha", "Two")]
    return music.folder(
        "Mix",
        "Alpha - One.mp3",
        "Alpha - Two (Extended Mix).mp3",
        "Nobody - Missing.mp3",
    )


def test_synced_folder_shows_playlist_last_sync_and_open_tracks(api, run_cli, music, spotify):
    folder = _mix_folder(music, spotify)
    assert run_cli("sync", folder, "--yes") == 0

    [entry] = api.folders.list()
    assert entry["folder"] == normalize_folder(folder)
    assert entry["name"] == "DJSYNC - Mix"
    assert entry["playlist_id"] in spotify.playlists
    assert entry["playlist_url"] == f"https://open.spotify.com/playlist/{entry['playlist_id']}"
    assert entry["last_sync"]  # ISO-Zeitpunkt
    assert entry["open_count"] == 2  # ungefähr + nicht gefunden
    assert entry["open_counts"] == {"approximate": 1, "not_found": 1}
    assert entry["reachable"] is True


# Schema vor der GUI (djsync 0.2.0): Ordner nur über playlists, playlist_id Pflicht
OLD_SCHEMA = """
CREATE TABLE files (
    path TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime REAL NOT NULL, artist TEXT, title TEXT,
    isrc TEXT, duration_ms INTEGER, fingerprint TEXT
);
CREATE INDEX files_fingerprint ON files(fingerprint);
CREATE TABLE matches (
    fingerprint TEXT PRIMARY KEY, status TEXT NOT NULL, spotify_id TEXT,
    candidates TEXT NOT NULL DEFAULT '[]', searched_at TEXT NOT NULL
);
CREATE TABLE playlists (
    folder TEXT PRIMARY KEY, playlist_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE managed_tracks (
    playlist_id TEXT NOT NULL, spotify_id TEXT NOT NULL, PRIMARY KEY (playlist_id, spotify_id)
);
"""


def _old_database(path, folder, playlist_id):
    folder = normalize_folder(folder)  # so hat auch die alte CLI den Ordner gespeichert
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.execute(
        "INSERT INTO playlists VALUES (?, ?, ?, ?)",
        (folder, playlist_id, "Meine Playlist", "2025-01-01T00:00:00+00:00"),
    )
    files = [("a.mp3", "fp-ungefähr"), ("a-kopie.mp3", "fp-ungefähr"), ("b.mp3", "fp-fehlt"), ("c.mp3", "fp-exakt")]
    for name, fp in files:
        conn.execute("INSERT INTO files VALUES (?, 1, 1.0, 'A', 'T', NULL, NULL, ?)", (f"{folder}/{name}", fp))
    for fp, status in [("fp-ungefähr", "approximate"), ("fp-fehlt", "not_found"), ("fp-exakt", "exact")]:
        conn.execute("INSERT INTO matches VALUES (?, ?, NULL, '[]', '2025-01-01T00:00:00+00:00')", (fp, status))
    conn.commit()
    conn.close()


def test_existing_database_is_taken_over(api, paths, music, spotify):
    folder = music.folder("Alt")
    playlist_id = spotify.add_playlist("Meine Playlist", [])
    _old_database(paths.db_file, folder, playlist_id)

    assert api.folders.list() == [
        {
            "folder": normalize_folder(folder),
            "name": "Meine Playlist",
            "playlist_id": playlist_id,
            "playlist_url": f"https://open.spotify.com/playlist/{playlist_id}",
            "last_sync": None,  # in der alten Datenbank nicht gespeichert
            "open_count": 2,  # derselbe Track in zwei Dateien zählt einmal
            "open_counts": {"approximate": 1, "not_found": 1},
            "reachable": True,
        }
    ]


def test_cli_keeps_working_with_taken_over_database(api, paths, run_cli, music, spotify):
    spotify.catalog.append(track("id_one", "Alpha", "One"))
    folder = music.folder("Alt", "Alpha - One.mp3")
    playlist_id = spotify.add_playlist("Meine Playlist", [])
    _old_database(paths.db_file, folder, playlist_id)

    assert run_cli("status") == 0
    assert run_cli("sync", folder, "--yes") == 0

    assert list(spotify.playlists) == [playlist_id]  # keine neue Playlist angelegt
    assert spotify.playlists[playlist_id]["items"] == ["id_one"]
    [entry] = api.folders.list()
    assert entry["playlist_id"] == playlist_id and entry["last_sync"]


def test_unreachable_folder_is_marked(api, paths, music, spotify):
    folder = music.folder("Extern")
    _old_database(paths.db_file, folder, spotify.add_playlist("Meine Playlist", []))
    (music.root / "Extern").rmdir()

    [entry] = api.folders.list()
    assert entry["reachable"] is False
    assert entry["open_count"] == 2  # Stand aus der Datenbank bleibt sichtbar
