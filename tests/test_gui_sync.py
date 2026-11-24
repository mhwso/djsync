"""Sync in der GUI: starten, Fortschritt, Zusammenfassung, Änderungsplan, bestätigen/verwerfen."""

import os
import threading
import time

import httpx
import pytest
from fake_spotify import track

from djsync import review_core
from djsync.filenames import normalize_folder
from djsync.gui.api import ApiError


def wait_for(api, *states, timeout=5.0):
    """Wartet, bis der Sync im Hintergrund einen der Zustände erreicht, und gibt den Status zurück."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = api.sync.status()
        if status and status["state"] in states:
            return status
        time.sleep(0.01)
    raise AssertionError(f"Sync hat {states} nicht erreicht: {api.sync.status()}")


def test_first_confirmed_sync_creates_playlist_with_chosen_name(api, music, spotify):
    spotify.catalog += [track("id_one", "Alpha", "One"), track("id_two", "Beta", "Two")]
    folder = music.folder("Mix", "Alpha - One.mp3", "Beta - Two.mp3")
    api.folders.add(folder, "Meine Party")

    api.sync.start(folder)
    wait_for(api, "ready")
    plan = api.sync.plan()
    assert plan["create"] is True
    assert plan["name"] == "Meine Party"
    assert spotify.writes() == []  # bis zur Bestätigung ändert sich nichts

    result = api.sync.confirm()

    [(playlist_id, playlist)] = spotify.playlists.items()
    assert playlist["name"] == "Meine Party"
    assert playlist["items"] == ["id_two", "id_one"]  # neueste Datei zuerst
    assert result["playlist_url"] == f"https://open.spotify.com/playlist/{playlist_id}"
    [entry] = api.folders.list()
    assert entry["playlist_id"] == playlist_id
    assert entry["name"] == "Meine Party"
    assert entry["last_sync"]
    assert api.sync.status() is None


def test_folder_may_come_in_any_spelling(api, music, spotify, events):
    folder = _mix_folder(music, spotify)
    api.folders.add(folder, "DJSYNC - Mix")
    other = str(music.root / "Mix" / ".." / "Mix") + os.sep

    api.sync.start(other)

    assert wait_for(api, "ready")["folder"] == normalize_folder(folder)
    assert events.named("sync.ready") == [{"folder": normalize_folder(folder)}]
    api.sync.confirm()
    [entry] = api.folders.list()
    assert entry["folder"] == normalize_folder(folder) and entry["last_sync"]


def _mix_folder(music, spotify):
    """Ordner mit je einem exakten, einem ungefähren und einem nicht gefundenen Track."""
    spotify.catalog += [track("id_one", "Alpha", "One"), track("id_two", "Alpha", "Two")]
    return music.folder("Mix", "Alpha - One.mp3", "Alpha - Two (Extended Mix).mp3", "Nobody - Missing.mp3")


def test_progress_and_summary_by_match_status(api, music, spotify, events):
    folder = _mix_folder(music, spotify)
    api.folders.add(folder, "DJSYNC - Mix")

    api.sync.start(folder)
    wait_for(api, "ready")

    progress = events.named("sync.progress")
    assert {"folder": normalize_folder(folder), "step": "scan", "done": 3, "total": 3} in progress
    assert progress[-1] == {"folder": normalize_folder(folder), "step": "search", "done": 3, "total": 3}
    assert events.named("sync.ready") == [{"folder": normalize_folder(folder)}]
    summary = api.sync.summary()
    assert summary["found"] == 3
    assert summary["searched"] == 3
    assert summary["counts"] == {"exact": 1, "approximate": 1, "manual": 0, "not_found": 1, "not_on_spotify": 0}
    assert sorted(t["file"] for t in summary["open"]) == ["Alpha - Two (Extended Mix).mp3", "Nobody - Missing.mp3"]


def test_existing_playlist_is_aligned_and_own_tracks_stay(api, run_cli, music, spotify):
    spotify.catalog += [track("id_one", "Alpha", "One"), track("id_two", "Beta", "Two")]
    folder = music.folder("Mix", "Alpha - One.mp3")
    assert run_cli("sync", folder, "--yes") == 0
    [(playlist_id, playlist)] = spotify.playlists.items()
    playlist["items"].append("id_mine")  # von Hand hinzugefügt
    music.folder("Mix", "Alpha - One.mp3", "Beta - Two.mp3")

    api.sync.start(folder)
    wait_for(api, "ready")
    plan = api.sync.plan()

    assert plan["create"] is False
    assert plan["name"] == "DJSYNC - Mix"
    assert plan["added"] == [{"id": "id_two", "label": "Beta - Two.mp3"}]
    assert plan["removed"] == []
    api.sync.confirm()
    assert list(spotify.playlists) == [playlist_id]
    assert spotify.playlists[playlist_id]["items"] == ["id_two", "id_one", "id_mine"]


def test_discard_leaves_everything_unchanged(api, music, spotify):
    folder = _mix_folder(music, spotify)
    api.folders.add(folder, "Party")
    api.sync.start(folder)
    wait_for(api, "ready")

    api.sync.discard()

    assert api.sync.status() is None
    assert spotify.writes() == []
    [entry] = api.folders.list()
    assert entry["playlist_id"] is None
    assert entry["last_sync"] is None


def test_plan_is_recomputed_after_review_decisions(api, ctx, music, spotify):
    folder = _mix_folder(music, spotify)
    api.folders.add(folder, "Mix")
    api.sync.start(folder)
    wait_for(api, "ready")
    assert [t["id"] for t in api.sync.plan()["added"]] == ["id_two", "id_one"]  # ungefähr kommt mit
    [approximate] = [t for t in api.sync.summary()["open"] if t["file"].startswith("Alpha - Two")]

    with ctx.db() as db:  # Review-Entscheidung wie aus #14
        review_core.mark_not_on_spotify(db, approximate["fingerprint"])

    assert [t["id"] for t in api.sync.plan()["added"]] == ["id_one"]
    assert api.sync.summary()["counts"]["not_on_spotify"] == 1


def test_cancel_during_search_leaves_playlist_unchanged(api, run_cli, music, spotify, events):
    spotify.catalog += [track("id_one", "Alpha", "One"), track("id_two", "Beta", "Two")]
    folder = music.folder("Mix", "Alpha - One.mp3")
    assert run_cli("sync", folder, "--yes") == 0
    [(playlist_id, playlist)] = spotify.playlists.items()
    before = dict(playlist, items=list(playlist["items"]))
    writes, searches = len(spotify.writes()), len(spotify.searches())
    music.folder("Mix", "Alpha - One.mp3", "Beta - Two.mp3", "Gamma - Three.mp3")

    def cancel_on_search(request):
        if request.url.path == "/v1/search":
            api.sync.cancel()

    spotify.on_request = cancel_on_search
    api.sync.start(folder)
    status = wait_for(api, "cancelled", "ready")

    assert status["state"] == "cancelled"
    assert events.named("sync.cancelled") == [{"folder": normalize_folder(folder)}]
    assert len(spotify.searches()) == searches + 1  # nach der laufenden Anfrage ist Schluss
    assert spotify.writes()[writes:] == []
    assert spotify.playlists[playlist_id] == before
    with pytest.raises(ApiError):
        api.sync.plan()
    spotify.on_request = None
    api.sync.start(folder)  # danach lässt sich neu starten
    assert wait_for(api, "ready")["state"] == "ready"


def test_second_sync_is_rejected_while_one_is_running(api, music, spotify):
    spotify.catalog += [track("id_one", "Alpha", "One")]
    first = music.folder("Eins", "Alpha - One.mp3")
    second = music.folder("Zwei", "Alpha - One.mp3")
    api.folders.add(first, "Eins")
    api.folders.add(second, "Zwei")
    searching, release = threading.Event(), threading.Event()

    def block(request):
        searching.set()
        release.wait(5)

    spotify.on_request = block
    api.sync.start(first)
    assert searching.wait(5)

    with pytest.raises(ApiError, match="läuft bereits ein Sync"):
        api.sync.start(second)
    with pytest.raises(ApiError, match="läuft bereits ein Sync"):
        api.sync.start(first)
    release.set()
    wait_for(api, "ready")
    with pytest.raises(ApiError, match="läuft bereits ein Sync"):
        api.sync.start(second)  # auch ein eingelesener, noch nicht bestätigter Sync zählt
    api.sync.discard()
    api.sync.start(second)
    assert wait_for(api, "ready")["folder"] == normalize_folder(second)


def _failing_folder(api, music, spotify):
    spotify.catalog += [track("id_one", "Alpha", "One")]
    folder = music.folder("Mix", "Alpha - One.mp3")
    api.folders.add(folder, "Mix")
    return folder


@pytest.mark.parametrize(
    ("respond", "message"),
    [
        (
            lambda r: httpx.Response(429, json={"error": {"status": 429, "reason": "QUOTA_EXCEEDED"}}),
            "Kontingent",
        ),
        (lambda r: httpx.Response(429, headers={"Retry-After": "3600"}), "Rate-Limit"),
        (lambda r: httpx.Response(403, json={"error": {"status": 403}}), "verweigert den Zugriff"),
    ],
)
def test_spotify_errors_while_searching_are_reported(api, music, spotify, events, respond, message):
    folder = _failing_folder(api, music, spotify)
    spotify.on_request = respond

    api.sync.start(folder)
    status = wait_for(api, "failed")

    assert message in status["error"]
    assert events.named("sync.failed") == [{"folder": normalize_folder(folder), "message": status["error"]}]


def test_network_error_is_reported(api, music, spotify):
    folder = _failing_folder(api, music, spotify)

    def offline(request):
        raise httpx.ConnectError("offline", request=request)

    spotify.on_request = offline
    api.sync.start(folder)

    assert "nicht erreichbar" in wait_for(api, "failed")["error"]


def test_missing_login_is_reported(api, music, spotify, paths):
    folder = _failing_folder(api, music, spotify)
    paths.token_file.unlink()

    api.sync.start(folder)

    assert "Einrichtung" in wait_for(api, "failed")["error"]


def test_error_while_confirming_keeps_the_plan(api, music, spotify):
    folder = _failing_folder(api, music, spotify)
    api.sync.start(folder)
    wait_for(api, "ready")
    spotify.on_request = lambda r: httpx.Response(429, headers={"Retry-After": "3600"}) if r.method != "GET" else None

    with pytest.raises(ApiError, match="Rate-Limit"):
        api.sync.confirm()

    assert api.sync.status()["state"] == "ready"
    spotify.on_request = None
    api.sync.confirm()
    [entry] = api.folders.list()
    assert spotify.playlists[entry["playlist_id"]]["name"] == "Mix"


def test_unreachable_or_unknown_folder_is_rejected(api, music, tmp_path):
    with pytest.raises(ApiError, match="nicht in djsync"):
        api.sync.start(str(tmp_path / "Unbekannt"))
    folder = music.folder("Weg")
    api.folders.add(folder, "Weg")
    (tmp_path / "music" / "Weg").rmdir()

    with pytest.raises(ApiError, match="nicht erreichbar"):
        api.sync.start(folder)
    assert api.sync.status() is None


# --- Review aus dem Sync heraus (#16) ---

MISSING_ID = "4uLU6hMCjMI75M1A2tKUQC"  # gültige Track-ID, die die Suche nicht findet


def test_no_review_hint_without_open_tracks(api, music, spotify):
    spotify.catalog += [track("id_one", "Alpha", "One")]
    folder = music.folder("Mix", "Alpha - One.mp3")
    api.folders.add(folder, "Mix")
    api.sync.start(folder)
    wait_for(api, "ready")

    assert api.sync.summary()["open"] == []


def test_review_first_returns_to_plan_of_same_sync_with_decisions(api, music, spotify, events):
    folder = _mix_folder(music, spotify)
    spotify.catalog.append(track(MISSING_ID, "Somebody", "Else"))  # von der Suche nicht gefunden
    api.folders.add(folder, "Mix")
    api.sync.start(folder)
    wait_for(api, "ready")
    assert len(api.sync.summary()["open"]) == 2  # Hinweis „erst prüfen“ / „direkt weiter“
    searches = len(spotify.searches())
    progress = len(events.named("sync.progress"))

    # „erst prüfen“: Review des Ordners, während der Sync bereitsteht
    review = api.review.tracks(folder)
    missing = next(t["fingerprint"] for t in review["tracks"] if t["filename"] == "Nobody - Missing.mp3")
    api.review.accept_link(folder, missing, f"https://open.spotify.com/track/{MISSING_ID}")
    two = next(t["fingerprint"] for t in review["tracks"] if t["filename"].startswith("Alpha - Two"))
    api.review.not_on_spotify(folder, two)

    # zurück zum Änderungsplan desselben Syncs – ohne erneutes Einlesen oder Suchen
    assert api.sync.status()["state"] == "ready"
    summary = api.sync.summary()
    plan = api.sync.plan()
    assert summary["open"] == []
    assert summary["counts"]["manual"] == 1
    assert summary["counts"]["not_on_spotify"] == 1
    assert sorted(t["id"] for t in plan["added"]) == [MISSING_ID, "id_one"]
    assert len(spotify.searches()) == searches
    assert len(events.named("sync.progress")) == progress

    api.sync.confirm()
    [playlist] = spotify.playlists.values()
    assert sorted(playlist["items"]) == [MISSING_ID, "id_one"]


def test_continue_directly_shows_plan_without_review(api, music, spotify):
    folder = _mix_folder(music, spotify)
    api.folders.add(folder, "Mix")
    api.sync.start(folder)
    wait_for(api, "ready")
    assert len(api.sync.summary()["open"]) == 2

    plan = api.sync.plan()  # „direkt weiter“

    assert sorted(t["id"] for t in plan["added"]) == ["id_one", "id_two"]  # ungefähr kommt mit
    assert api.review.tracks(api.sync.status()["folder"])["open_count"] == 2  # nichts entschieden
    api.sync.confirm()
    [playlist] = spotify.playlists.values()
    assert sorted(playlist["items"]) == ["id_one", "id_two"]
