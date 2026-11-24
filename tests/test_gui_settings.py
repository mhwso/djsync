"""Einstellungen über die API-Schicht der GUI: lesen, prüfen, in config.toml speichern."""

import pytest

from djsync.gui.api import ApiError
from fake_spotify import track


def test_defaults_include_start_position_and_skip_width(api):
    assert api.settings.get() == {
        "extensions": [".mp3", ".flac", ".m4a", ".wav", ".aiff", ".aif"],
        "duration_tolerance_s": 3.0,
        "min_score": 0.7,
        "retry_missing_days": 14,
        "review_candidates": 5,
        "start_position_s": 60,
        "skip_s": 30,
    }


VALID = {
    "extensions": ["flac", ".AIFF"],
    "duration_tolerance_s": 5,
    "min_score": 0.8,
    "retry_missing_days": 7,
    "review_candidates": 3,
    "start_position_s": 90,
    "skip_s": 15,
}


def test_valid_settings_are_saved(api, paths):
    saved = api.settings.save(VALID)

    expected = {**VALID, "extensions": [".flac", ".aiff"], "duration_tolerance_s": 5.0}
    assert saved == expected
    assert api.settings.get() == expected
    # Client-ID bleibt erhalten
    assert 'client_id = "' in paths.config_file.read_text(encoding="utf-8")


def test_saving_keeps_other_entries_of_config_toml(api, paths):
    text = paths.config_file.read_text(encoding="utf-8")
    paths.config_file.write_text(
        text + '# eigener Kommentar\nextensions = [\n  ".mp3",\n  ".wav",\n]\nmin_score = 0.6\n\n[sonstiges]\nx = 1\n',
        encoding="utf-8",
    )

    api.settings.save(VALID)

    text = paths.config_file.read_text(encoding="utf-8")
    assert "# eigener Kommentar" in text
    assert "[sonstiges]\nx = 1" in text
    assert api.settings.get()["extensions"] == [".flac", ".aiff"]
    assert api.settings.get()["min_score"] == 0.8


def test_cli_reads_settings_saved_in_gui(api, run_cli, music, spotify):
    spotify.catalog += [track("id_one", "Alpha", "One"), track("id_two", "Alpha", "Two")]
    folder = music.folder("Mix", "Alpha - One.flac", "Alpha - Two.mp3")
    api.settings.save({**VALID, "extensions": [".flac"]})

    assert run_cli("sync", folder, "--yes") == 0

    [playlist] = spotify.playlists.values()
    assert playlist["items"] == ["id_one"]


@pytest.mark.parametrize(
    "key, value, message",
    [
        ("extensions", [], "Dateiendungen"),
        ("extensions", [".mp 3"], "Dateiendungen"),
        ("duration_tolerance_s", -1, "Toleranz der Dauer"),
        ("min_score", 1.5, "Mindestbewertung"),
        ("retry_missing_days", 2.5, "Tage bis zur erneuten Suche"),
        ("review_candidates", 0, "Anzahl der Vorschläge"),
        ("start_position_s", "abc", "Startstelle"),
        ("skip_s", 0, "Sprungweite"),
    ],
)
def test_invalid_settings_are_reported_and_not_saved(api, paths, key, value, message):
    before = paths.config_file.read_text(encoding="utf-8")

    with pytest.raises(ApiError, match=message):
        api.settings.save({**VALID, key: value})

    assert paths.config_file.read_text(encoding="utf-8") == before
    assert api.settings.get()["skip_s"] == 30
