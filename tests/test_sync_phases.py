"""Sync-Phasen gegen Spotify-Fake (HTTP) und echte SQLite-Datei."""

import os

import pytest
from fake_spotify import FakeSpotify, track

from djsync import sync_phases as phases
from djsync.config import Config
from djsync.db import Database
from djsync.models import EXACT, MANUAL, NOT_FOUND


@pytest.fixture
def env(tmp_path):
    folder = tmp_path / "Techno"
    folder.mkdir()
    db = Database(tmp_path / "djsync.db")
    cfg = Config(client_id="client")
    return folder, db, cfg


def add_file(folder, name: str, mtime: float) -> None:
    """Kleine Testdatei ohne Tags – Artist und Titel kommen aus dem Dateinamen."""
    path = folder / name
    path.write_bytes(b"keine echten Audiodaten")
    os.utime(path, (mtime, mtime))


CATALOG = [
    track("id_alpha", "Artist", "Alpha"),
    track("id_beta", "Artist", "Beta"),
    track("id_gamma", "Artist", "Gamma"),
]


def test_sync_creates_new_playlist(env, tmp_path):
    folder, db, cfg = env
    add_file(folder, "Artist - Alpha.mp3", 100)
    add_file(folder, "Artist - Beta.mp3", 200)
    spotify = FakeSpotify(CATALOG)
    client = spotify.client(tmp_path)

    run = phases.read_folder(str(folder), db, cfg)
    phases.load_playlist(run, db, client)
    phases.search_tracks(run, db, client, cfg)
    change = phases.plan_changes(run, db)
    assert change.new_name == "DJSYNC - Techno"
    assert spotify.writes() == []  # bis zur Übernahme bleibt Spotify unverändert

    playlist_id = phases.apply_changes(run, change, db, client)

    pl = spotify.playlists[playlist_id]
    assert pl["name"] == "DJSYNC - Techno"
    assert pl["items"] == ["id_beta", "id_alpha"]  # neueste Datei zuerst
    assert db.get_playlist(str(folder))["playlist_id"] == playlist_id
    assert db.managed_tracks(playlist_id) == {"id_alpha", "id_beta"}


def sync_once(folder, db, client, cfg):
    run = phases.prepare(str(folder), db, client, cfg)
    return phases.apply_changes(run, phases.plan_changes(run, db), db, client)


def test_sync_aligns_existing_playlist_and_keeps_own_tracks(env, tmp_path):
    folder, db, cfg = env
    add_file(folder, "Artist - Alpha.mp3", 100)
    add_file(folder, "Artist - Beta.mp3", 200)
    spotify = FakeSpotify(CATALOG)
    client = spotify.client(tmp_path)
    playlist_id = sync_once(folder, db, client, cfg)
    spotify.playlists[playlist_id]["items"].append("id_own")  # vom Nutzer selbst hinzugefügt

    os.remove(folder / "Artist - Beta.mp3")
    add_file(folder, "Artist - Gamma.mp3", 300)
    run = phases.prepare(str(folder), db, client, cfg)
    change = phases.plan_changes(run, db)

    assert change.new_name is None
    assert change.plan.added == ["id_gamma"]
    assert change.plan.removed == ["id_beta"]
    assert phases.apply_changes(run, change, db, client) == playlist_id
    assert spotify.playlists[playlist_id]["items"] == ["id_gamma", "id_alpha", "id_own"]
    assert len(spotify.playlists) == 1


def test_sync_recreates_playlist_deleted_on_spotify(env, tmp_path):
    folder, db, cfg = env
    add_file(folder, "Artist - Alpha.mp3", 100)
    spotify = FakeSpotify(CATALOG)
    client = spotify.client(tmp_path)
    old_id = sync_once(folder, db, client, cfg)
    del spotify.playlists[old_id]

    run = phases.prepare(str(folder), db, client, cfg)
    assert run.playlist_lost
    new_id = sync_once(folder, db, client, cfg)
    assert new_id != old_id and spotify.playlists[new_id]["items"] == ["id_alpha"]


def test_empty_folder_does_not_empty_filled_playlist(env, tmp_path):
    folder, db, cfg = env
    add_file(folder, "Artist - Alpha.mp3", 100)
    spotify = FakeSpotify(CATALOG)
    client = spotify.client(tmp_path)
    playlist_id = sync_once(folder, db, client, cfg)

    os.remove(folder / "Artist - Alpha.mp3")
    with pytest.raises(phases.EmptyFolderError):
        phases.prepare(str(folder), db, client, cfg)
    assert spotify.playlists[playlist_id]["items"] == ["id_alpha"]


def test_empty_folder_is_fine_for_new_playlist(env, tmp_path):
    folder, db, cfg = env
    spotify = FakeSpotify(CATALOG)
    client = spotify.client(tmp_path)
    playlist_id = sync_once(folder, db, client, cfg)
    assert spotify.playlists[playlist_id]["items"] == []


def test_progress_is_reported_for_scan_and_search(env, tmp_path):
    folder, db, cfg = env
    add_file(folder, "Artist - Alpha.mp3", 100)
    add_file(folder, "Artist - Beta.mp3", 200)
    client = FakeSpotify(CATALOG).client(tmp_path)
    events = []

    def report(step, done, total):
        events.append((step, done, total))

    run = phases.read_folder(str(folder), db, cfg, on_progress=report)
    phases.load_playlist(run, db, client, on_progress=report)
    assert phases.search_tracks(run, db, client, cfg, on_progress=report) == 2

    assert [e for e in events if e[0] == "scan"][-1] == ("scan", 2, 2)
    assert [e for e in events if e[0] == "search"] == [("search", 0, 2), ("search", 1, 2), ("search", 2, 2)]


def test_cancel_between_spotify_requests_leaves_playlist_unchanged(env, tmp_path):
    folder, db, cfg = env
    add_file(folder, "Artist - Alpha.mp3", 100)
    spotify = FakeSpotify(CATALOG)
    client = spotify.client(tmp_path)
    playlist_id = sync_once(folder, db, client, cfg)

    add_file(folder, "Artist - Beta.mp3", 200)
    add_file(folder, "Artist - Gamma.mp3", 300)
    state = {"cancelled": False}

    def cancel_after_first_search(request):
        if request.url.path == "/v1/search":
            state["cancelled"] = True

    def is_cancelled():
        return state["cancelled"]

    run = phases.read_folder(str(folder), db, cfg, cancel=is_cancelled)
    phases.load_playlist(run, db, client, cancel=is_cancelled)
    spotify.on_request = cancel_after_first_search
    searches_before = len(spotify.searches())
    with pytest.raises(phases.SyncCancelled):
        phases.search_tracks(run, db, client, cfg, cancel=is_cancelled)

    assert len(spotify.searches()) == searches_before + 1  # danach keine weitere Anfrage
    assert spotify.playlists[playlist_id]["items"] == ["id_alpha"]
    assert db.managed_tracks(playlist_id) == {"id_alpha"}


def test_cancel_before_loading_playlist(env, tmp_path):
    folder, db, cfg = env
    add_file(folder, "Artist - Alpha.mp3", 100)
    spotify = FakeSpotify(CATALOG)
    client = spotify.client(tmp_path)
    sync_once(folder, db, client, cfg)
    run = phases.read_folder(str(folder), db, cfg)
    spotify.requests.clear()

    with pytest.raises(phases.SyncCancelled):
        phases.load_playlist(run, db, client, cancel=lambda: True)
    assert spotify.requests == []


def test_summary_lists_open_tracks_and_plan_follows_review_decisions(env, tmp_path):
    folder, db, cfg = env
    add_file(folder, "Artist - Alpha.mp3", 100)
    add_file(folder, "Artist - Unbekannt.mp3", 200)
    spotify = FakeSpotify(CATALOG)
    client = spotify.client(tmp_path)
    run = phases.prepare(str(folder), db, client, cfg)

    summary = phases.summarize_run(run, db)
    assert [os.path.basename(f.path) for f in summary.groups[EXACT]] == ["Artist - Alpha.mp3"]
    assert [os.path.basename(f.path) for f in summary.groups[NOT_FOUND]] == ["Artist - Unbekannt.mp3"]
    assert [os.path.basename(f.path) for f, _ in summary.pending] == ["Artist - Unbekannt.mp3"]
    assert phases.plan_changes(run, db).plan.added == ["id_alpha"]

    # Review-Entscheidung, danach nur den Plan neu berechnen – ohne Einlesen und Suchen
    _, fp = summary.pending[0]
    db.save_match(fp, MANUAL, "id_gamma")
    db.commit()
    requests_before = len(spotify.requests)
    change = phases.plan_changes(run, db)

    assert change.plan.added == ["id_gamma", "id_alpha"]
    assert change.labels["id_gamma"] == "Artist - Unbekannt.mp3"
    assert phases.summarize_run(run, db).pending == []
    assert len(spotify.requests) == requests_before


def test_name_renames_existing_playlist_on_apply(env, tmp_path):
    folder, db, cfg = env
    add_file(folder, "Artist - Alpha.mp3", 100)
    spotify = FakeSpotify(CATALOG)
    client = spotify.client(tmp_path)
    playlist_id = sync_once(folder, db, client, cfg)

    run = phases.prepare(str(folder), db, client, cfg)
    assert phases.plan_changes(run, db, name="DJSYNC - Techno").rename is None
    change = phases.plan_changes(run, db, name="Neu")
    assert change.rename == "DJSYNC - Neu" and not change.needs_write
    phases.apply_changes(run, change, db, client)
    assert spotify.playlists[playlist_id]["name"] == "DJSYNC - Neu"
