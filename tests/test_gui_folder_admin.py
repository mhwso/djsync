"""Ordnerverwaltung über die API-Schicht: hinzufügen, umbenennen, entfernen."""

from types import SimpleNamespace

import pytest

from djsync.gui.api import ApiError
from fake_spotify import track


def test_new_folder_appears_without_playlist(api, music, spotify):
    folder = music.folder("Techno 2026")

    entry = api.folders.add(folder, "Meine Techno-Liste")

    assert entry["folder"] == folder
    assert entry["name"] == "Meine Techno-Liste"
    assert entry["playlist_id"] is None
    assert entry["last_sync"] is None
    assert api.folders.list() == [entry]
    assert spotify.writes() == []  # auf Spotify wird noch nichts angelegt


def test_folder_already_in_djsync_is_rejected(api, music):
    folder = music.folder("Techno")
    api.folders.add(folder, "DJSYNC - Techno")

    with pytest.raises(ApiError, match="schon in djsync"):
        api.folders.add(folder + "/", "Noch einmal")  # gleicher Ordner, andere Schreibweise

    assert [e["name"] for e in api.folders.list()] == ["DJSYNC - Techno"]


def test_suggestion_for_dialog_or_drop(api, music):
    folder = music.folder("House")

    assert api.folders.suggest(folder + "/") == {"folder": folder, "name": "DJSYNC - House"}


def test_suggestion_rejects_folder_already_in_djsync(api, music):
    folder = music.folder("House")
    api.folders.add(folder, "DJSYNC - House")

    with pytest.raises(ApiError, match="schon in djsync"):
        api.folders.suggest(folder)


def test_suggestion_rejects_file(api, music):
    folder = music.folder("House", "Alpha - One.mp3")

    with pytest.raises(ApiError, match="kein Ordner"):
        api.folders.suggest(folder + "/Alpha - One.mp3")


def test_rename_without_playlist_only_changes_name_locally(api, music, spotify):
    folder = music.folder("Techno")
    api.folders.add(folder, "DJSYNC - Techno")

    entry = api.folders.rename(folder, "  Peak Time  ")

    assert entry["name"] == "Peak Time"
    assert [e["name"] for e in api.folders.list()] == ["Peak Time"]
    assert spotify.requests == []


def test_rename_with_playlist_renames_it_on_spotify_right_away(api, run_cli, music, spotify):
    spotify.catalog.append(track("id_one", "Alpha", "One"))
    folder = music.folder("Techno", "Alpha - One.mp3")
    assert run_cli("sync", folder, "--yes") == 0
    [entry] = api.folders.list()

    api.folders.rename(folder, "Peak Time")

    assert spotify.playlists[entry["playlist_id"]]["name"] == "Peak Time"
    assert [e["name"] for e in api.folders.list()] == ["Peak Time"]


def test_rename_reports_spotify_error_and_keeps_old_name(api, run_cli, music, spotify):
    folder = music.folder("Techno", "Alpha - One.mp3")
    assert run_cli("sync", folder, "--yes") == 0
    spotify.playlists.clear()  # Playlist inzwischen auf Spotify gelöscht

    with pytest.raises(ApiError, match="Spotify"):
        api.folders.rename(folder, "Peak Time")

    assert [e["name"] for e in api.folders.list()] == ["DJSYNC - Techno"]


def _synced_folder(run_cli, music, spotify):
    spotify.catalog.append(track("id_one", "Alpha", "One"))
    folder = music.folder("Techno", "Alpha - One.mp3")
    assert run_cli("sync", folder, "--yes") == 0
    return folder


def test_remove_and_keep_playlist_on_spotify(api, run_cli, music, spotify):
    folder = _synced_folder(run_cli, music, spotify)
    [entry] = api.folders.list()

    api.folders.remove(folder, False)

    assert api.folders.list() == []
    assert spotify.playlists[entry["playlist_id"]]["items"] == ["id_one"]
    assert [r.method for r in spotify.writes()] == ["POST", "PUT"]  # nur vom Sync


def test_remove_and_delete_playlist_on_spotify(api, run_cli, music, spotify):
    folder = _synced_folder(run_cli, music, spotify)
    [entry] = api.folders.list()

    api.folders.remove(folder, True)

    assert api.folders.list() == []
    assert entry["playlist_id"] not in spotify.playlists


def test_matches_survive_removing_the_folder(api, run_cli, music, spotify):
    folder = _synced_folder(run_cli, music, spotify)
    api.folders.remove(folder, True)

    # Neu aufgenommen: die Zuordnung ist noch da, Spotify wird nicht erneut durchsucht
    searches = len(spotify.searches())
    assert run_cli("sync", folder, "--yes") == 0
    assert len(spotify.searches()) == searches
    [entry] = api.folders.list()
    assert spotify.playlists[entry["playlist_id"]]["items"] == ["id_one"]


def test_remove_folder_without_playlist_never_asks_spotify(api, music, spotify):
    folder = music.folder("Techno")
    api.folders.add(folder, "DJSYNC - Techno")

    api.folders.remove(folder, True)

    assert api.folders.list() == []
    assert spotify.requests == []


def test_remove_and_delete_when_playlist_is_already_gone(api, run_cli, music, spotify):
    folder = _synced_folder(run_cli, music, spotify)
    spotify.playlists.clear()

    api.folders.remove(folder, True)

    assert api.folders.list() == []


class _Handlers(list):
    def __iadd__(self, handler):
        self.append(handler)
        return self


def test_dropped_folders_are_reported_to_the_ui(events):
    from djsync.gui.api.folders import install_drop

    doc_events = SimpleNamespace(dragover=_Handlers(), drop=_Handlers())
    window = SimpleNamespace(dom=SimpleNamespace(document=SimpleNamespace(events=doc_events)))
    install_drop(window, events)

    [handler] = doc_events.drop
    handler.callback({"dataTransfer": {"files": [{"name": "Techno", "pywebviewFullPath": "D:\\Musik\\Techno"}]}})
    handler.callback({"dataTransfer": {"files": [{"name": "ohne Pfad"}]}})

    assert events.named("folders.dropped") == [{"paths": ["D:\\Musik\\Techno"]}]
