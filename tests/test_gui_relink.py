"""Relink über die API-Schicht der GUI: verschobenen Ordner mit neuem Pfad verknüpfen."""

import os

import pytest

from djsync.filenames import normalize_folder
from djsync.gui.api import ApiError
from fake_spotify import track


def _synced_folder(api, run_cli, music, spotify):
    spotify.catalog += [track("id_one", "Alpha", "One"), track("id_two", "Alpha", "Two")]
    folder = music.folder("Mix", "Alpha - One.mp3", "Alpha - Two (Extended Mix).mp3", "Nobody - Missing.mp3")
    assert run_cli("sync", folder, "--yes") == 0
    [entry] = api.folders.list()
    return folder, entry


def test_relink_keeps_playlist_and_mappings(api, run_cli, music, spotify):
    old, before = _synced_folder(api, run_cli, music, spotify)
    new = str(music.root / "Verschoben")
    os.rename(old, new)
    assert api.relink.check(old) == {"folder": normalize_folder(old), "reachable": False}

    result = api.relink.apply(old, new)

    assert result == {"folder": normalize_folder(new), "moved": 3}
    [after] = api.folders.list()
    assert after == {**before, "folder": normalize_folder(new), "reachable": True}
    # Zuordnungen bleiben: ein erneuter Sync sucht nichts neu und ändert die Playlist nicht
    searches = len(spotify.searches())
    assert run_cli("sync", new, "--yes") == 0
    assert len(spotify.searches()) == searches
    assert list(spotify.playlists) == [before["playlist_id"]]


def test_relink_target_must_exist(api, run_cli, music, spotify):
    old, before = _synced_folder(api, run_cli, music, spotify)

    with pytest.raises(ApiError, match="nicht erreichbar"):
        api.relink.apply(old, str(music.root / "Gibt es nicht"))

    assert api.folders.list() == [before]


def test_relink_target_must_not_be_linked_already(api, run_cli, music, spotify):
    old, _ = _synced_folder(api, run_cli, music, spotify)
    other = music.folder("Anderer", "Alpha - One.mp3")
    assert run_cli("sync", other, "--yes") == 0
    before = api.folders.list()

    with pytest.raises(ApiError, match="bereits"):
        api.relink.apply(old, other)

    assert api.folders.list() == before


def test_cli_relink_uses_same_rules(api, run_cli, music, spotify):
    old, before = _synced_folder(api, run_cli, music, spotify)
    assert run_cli("relink", old, str(music.root / "Gibt es nicht")) != 0

    new = str(music.root / "Verschoben")
    os.rename(old, new)
    assert run_cli("relink", old, new) == 0
    assert api.folders.list() == [{**before, "folder": normalize_folder(new)}]


def test_relink_unknown_folder(api, music):
    target = music.folder("Ziel")

    with pytest.raises(ApiError, match="kein Ordner"):
        api.relink.apply(str(music.root / "Unbekannt"), target)


def test_cli_relink_of_unknown_folder_keeps_its_message(run_cli, music, capsys):
    target = music.folder("Ziel")

    assert run_cli("relink", str(music.root / "Unbekannt"), target) != 0

    out = capsys.readouterr()
    assert "mit keiner Playlist verknüpft" in out.out + out.err
