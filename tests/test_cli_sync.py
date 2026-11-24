"""`djsync sync` von außen: Optionen, Schutzabfragen und Ausgaben bleiben wie bisher."""

import builtins
import os
import sys

import pytest
from fake_spotify import FakeSpotify, track

from djsync import cli
from djsync.config import Config
from djsync.db import Database

CATALOG = [track("id_alpha", "Artist", "Alpha"), track("id_beta", "Artist", "Beta")]


class Tty:
    def isatty(self):
        return True


@pytest.fixture
def env(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "Techno"
    folder.mkdir()
    db = Database(tmp_path / "djsync.db")
    spotify = FakeSpotify(CATALOG)
    client = spotify.client(tmp_path)
    monkeypatch.setattr(cli, "setup", lambda need_client=True: (Config(client_id="c"), db, client))
    return folder, db, spotify


def add_file(folder, name, mtime):
    path = folder / name
    path.write_bytes(b"x")
    os.utime(path, (mtime, mtime))


def answer(monkeypatch, *answers):
    monkeypatch.setattr(sys, "stdin", Tty())
    it = iter(answers)
    monkeypatch.setattr(builtins, "input", lambda *_a: next(it))


def test_yes_creates_playlist_with_name(env, capsys):
    folder, db, spotify = env
    add_file(folder, "Artist - Alpha.mp3", 100)

    assert cli.main(["sync", str(folder), "--yes", "--name", "Peak"]) == 0

    [pl] = spotify.playlists.values()
    assert pl["name"] == "DJSYNC - Peak" and pl["items"] == ["id_alpha"]
    out = capsys.readouterr().out
    assert "1 Audiodateien gefunden" in out
    assert "1 Tracks auf Spotify gesucht" in out
    assert "open.spotify.com/playlist/" in out


def test_dry_run_changes_nothing(env, capsys):
    folder, db, spotify = env
    add_file(folder, "Artist - Alpha.mp3", 100)

    assert cli.main(["sync", str(folder), "--dry-run"]) == 0

    assert spotify.playlists == {} and spotify.writes() == []
    assert "Probelauf" in capsys.readouterr().out


def test_declined_confirmation_changes_nothing(env, monkeypatch, capsys):
    folder, db, spotify = env
    add_file(folder, "Artist - Alpha.mp3", 100)
    answer(monkeypatch, "n")

    assert cli.main(["sync", str(folder)]) == 0

    assert spotify.writes() == []
    assert "nichts geändert" in capsys.readouterr().out


def test_review_offered_for_open_tracks_then_plan_includes_decision(env, monkeypatch):
    folder, db, spotify = env
    add_file(folder, "Artist - Alpha.mp3", 100)
    add_file(folder, "Artist - Unbekannt.mp3", 200)
    # Review starten, Track per Link zuordnen, dann übernehmen
    answer(monkeypatch, "j", "l", "spotify:track:" + "b" * 22, "j")

    assert cli.main(["sync", str(folder)]) == 0

    [pl] = spotify.playlists.values()
    assert pl["items"] == ["b" * 22, "id_alpha"]


def test_empty_folder_with_filled_playlist_aborts(env, capsys):
    folder, db, spotify = env
    add_file(folder, "Artist - Alpha.mp3", 100)
    assert cli.main(["sync", str(folder), "--yes"]) == 0
    os.remove(folder / "Artist - Alpha.mp3")

    assert cli.main(["sync", str(folder), "--yes"]) == 1

    [pl] = spotify.playlists.values()
    assert pl["items"] == ["id_alpha"]
    out = capsys.readouterr()
    assert "nicht versehentlich zu leeren" in out.out + out.err


def test_retry_searches_open_tracks_again(env):
    folder, db, spotify = env
    add_file(folder, "Artist - Unbekannt.mp3", 100)
    assert cli.main(["sync", str(folder), "--yes"]) == 0
    searches = len(spotify.searches())

    assert cli.main(["sync", str(folder), "--yes"]) == 0
    assert len(spotify.searches()) == searches  # nicht gefunden: erst nach Tagen erneut
    assert cli.main(["sync", str(folder), "--yes", "--retry"]) == 0
    assert len(spotify.searches()) > searches
