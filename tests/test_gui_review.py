"""Review eines Ordners über die API-Schicht der GUI."""

import httpx
import pytest
from fake_spotify import track

from djsync.gui.api import ApiError


@pytest.fixture
def folder(run_cli, music, spotify):
    """Synchronisierter Ordner: ein exakter, ein ungefährer, ein nicht gefundener Track."""
    spotify.catalog += [
        track("id_one", "Alpha", "One"),
        track("id_two", "Alpha", "Two"),
        track("id_two_cover", "Tribute Band", "Two"),
    ]
    path = music.folder(
        "Mix",
        "Alpha - One.mp3",
        "Alpha - Two (Extended Mix).mp3",
        "Nobody - Missing.mp3",
    )
    assert run_cli("sync", path, "--yes") == 0
    return path


def names(listing):
    return [t["filename"] for t in listing["tracks"]]


def fingerprint(api, folder, filename, filter="open"):
    return next(t["fingerprint"] for t in api.review.tracks(folder, filter)["tracks"] if t["filename"] == filename)


def test_open_tracks_are_listed_by_default(api, folder):
    listing = api.review.tracks(folder)

    assert listing["open_count"] == 2
    assert names(listing) == ["Alpha - Two (Extended Mix).mp3", "Nobody - Missing.mp3"]
    two, missing = listing["tracks"]
    assert two["status"] == "approximate" and two["artist"] == "Alpha" and two["title"] == "Two (Extended Mix)"
    assert missing["status"] == "not_found"
    assert not two["decided"]


def test_detail_shows_file_tags_and_suggestions(api, folder):
    fp = fingerprint(api, folder, "Alpha - Two (Extended Mix).mp3")

    detail = api.review.track(folder, fp)

    assert detail["filename"] == "Alpha - Two (Extended Mix).mp3"
    assert detail["path"] == f"{folder}/Alpha - Two (Extended Mix).mp3"
    assert (detail["artist"], detail["title"], detail["isrc"], detail["duration_ms"]) == (
        "Alpha",
        "Two (Extended Mix)",
        None,
        None,
    )
    assert detail["status"] == "approximate"
    ids = [c["id"] for c in detail["candidates"]]
    assert set(ids) == {"id_two", "id_two_cover"}
    first = detail["candidates"][0]
    assert first["selected"] is True  # die aktuelle Zuordnung
    assert first["artists"] == ["Alpha"] and first["album"] == "Album"
    assert first["url"] == f"https://open.spotify.com/track/{first['id']}"
    assert 0 < first["score"] < 1 and first["duration_ok"] is True
    assert [c["number"] for c in detail["candidates"]] == [1, 2]


def test_detail_of_track_without_suggestions(api, folder):
    fp = fingerprint(api, folder, "Nobody - Missing.mp3")

    detail = api.review.track(folder, fp)

    assert detail["status"] == "not_found" and detail["candidates"] == []


def test_unknown_track_is_reported(api, folder):
    with pytest.raises(ApiError, match="Track"):
        api.review.track(folder, "gibt-es-nicht")


def test_accepting_a_suggestion_saves_and_moves_to_next_open_track(api, folder):
    two = fingerprint(api, folder, "Alpha - Two (Extended Mix).mp3")
    missing = fingerprint(api, folder, "Nobody - Missing.mp3")

    result = api.review.accept(folder, two, "id_two_cover")

    assert result["track"]["status"] == "manual" and result["track"]["decided"] is True
    assert result["track"]["spotify_id"] == "id_two_cover"
    assert result["open_count"] == 1
    assert result["next"] == missing
    # sofort gespeichert: Liste und Startbildschirm sehen den neuen Stand
    assert names(api.review.tracks(folder)) == ["Nobody - Missing.mp3"]
    assert names(api.review.tracks(folder, "decided")) == ["Alpha - Two (Extended Mix).mp3"]
    assert api.folders.list()[0]["open_count"] == 1


def test_unknown_suggestion_is_reported(api, folder):
    two = fingerprint(api, folder, "Alpha - Two (Extended Mix).mp3")

    with pytest.raises(ApiError, match="Vorschlag"):
        api.review.accept(folder, two, "id_one")


LINK_ID = "4uLU6hMCjMI75M1A2tKUQC"


def test_link_assigns_a_track_that_is_not_among_the_suggestions(api, folder, spotify):
    spotify.catalog.append(track(LINK_ID, "Nobody", "Missing (Bootleg)"))
    missing = fingerprint(api, folder, "Nobody - Missing.mp3")

    result = api.review.accept_link(folder, missing, f"https://open.spotify.com/intl-de/track/{LINK_ID}?si=x")

    assert result["track"]["status"] == "manual" and result["track"]["spotify_id"] == LINK_ID
    assert result["track"]["candidates"][0]["id"] == LINK_ID
    assert result["track"]["candidates"][0]["selected"] is True
    assert result["open_count"] == 1


def test_invalid_link_is_reported_clearly(api, folder):
    missing = fingerprint(api, folder, "Nobody - Missing.mp3")

    with pytest.raises(ApiError, match="Kein gültiger Track-Link"):
        api.review.accept_link(folder, missing, "https://example.com/nix")
    assert api.review.track(folder, missing)["status"] == "not_found"  # unverändert


def test_unavailable_track_is_reported(api, folder, spotify):
    spotify.unavailable.add(LINK_ID)
    missing = fingerprint(api, folder, "Nobody - Missing.mp3")

    with pytest.raises(ApiError, match="nicht abrufbar"):
        api.review.accept_link(folder, missing, f"spotify:track:{LINK_ID}")


def test_not_on_spotify_decides_track_and_keeps_suggestions(api, folder):
    two = fingerprint(api, folder, "Alpha - Two (Extended Mix).mp3")

    result = api.review.not_on_spotify(folder, two)

    assert result["track"]["status"] == "not_on_spotify" and result["track"]["decided"] is True
    assert result["track"]["spotify_id"] is None
    assert len(result["track"]["candidates"]) == 2
    assert result["open_count"] == 1


def test_decided_track_can_be_changed(api, folder):
    two = fingerprint(api, folder, "Alpha - Two (Extended Mix).mp3")
    api.review.not_on_spotify(folder, two)

    result = api.review.accept(folder, two, "id_two")

    assert result["track"]["status"] == "manual" and result["track"]["spotify_id"] == "id_two"


def test_decided_track_can_be_reset_to_open(api, folder):
    two = fingerprint(api, folder, "Alpha - Two (Extended Mix).mp3")
    api.review.accept(folder, two, "id_two_cover")

    result = api.review.reset(folder, two)

    assert result["track"]["status"] == "approximate" and result["track"]["open"] is True
    assert result["track"]["spotify_id"] == result["track"]["candidates"][0]["id"]  # erster Vorschlag
    assert result["open_count"] == 2
    assert names(api.review.tracks(folder, "decided")) == []


def test_open_track_cannot_be_reset(api, folder):
    two = fingerprint(api, folder, "Alpha - Two (Extended Mix).mp3")

    with pytest.raises(ApiError, match="entschiedene"):
        api.review.reset(folder, two)


def test_skip_moves_to_next_open_track_and_wraps_around(api, folder):
    two = fingerprint(api, folder, "Alpha - Two (Extended Mix).mp3")
    missing = fingerprint(api, folder, "Nobody - Missing.mp3")

    assert api.review.next_open(folder) == two  # Einstieg: erster offener Track
    assert api.review.next_open(folder, two) == missing
    assert api.review.next_open(folder, missing) == two  # vorn weiter
    assert api.review.track(folder, two)["status"] == "approximate"  # Überspringen ändert nichts


def test_no_next_track_when_nothing_else_is_open(api, folder):
    two = fingerprint(api, folder, "Alpha - Two (Extended Mix).mp3")
    missing = fingerprint(api, folder, "Nobody - Missing.mp3")
    api.review.not_on_spotify(folder, missing)

    result = api.review.not_on_spotify(folder, two)

    assert result["next"] is None and result["open_count"] == 0
    assert api.review.next_open(folder) is None


def test_exact_filter_shows_exact_matches(api, folder):
    listing = api.review.tracks(folder, "exact")

    assert names(listing) == ["Alpha - One.mp3"]
    assert listing["open_count"] == 2  # unabhängig vom Filter
    one = listing["tracks"][0]
    assert one["status"] == "exact" and not one["open"] and not one["decided"]


def test_exact_track_can_be_decided_too(api, folder):
    one = fingerprint(api, folder, "Alpha - One.mp3", "exact")

    result = api.review.not_on_spotify(folder, one)

    assert result["track"]["decided"] is True
    assert names(api.review.tracks(folder, "exact")) == []


def test_unknown_filter_is_reported(api, folder):
    with pytest.raises(ApiError, match="Filter"):
        api.review.tracks(folder, "alle")


def test_unknown_folder_is_reported(api, folder, music):
    with pytest.raises(ApiError, match="Ordner"):
        api.review.tracks(str(music.root / "Anders"))


# ---- Massenoperationen ----------------------------------------------------


def all_fingerprints(api, folder):
    """Fingerprints aller Tracks des Ordners (offen, entschieden, exakt) je Dateiname."""
    return {
        t["filename"]: t["fingerprint"]
        for filter in ("open", "decided", "exact")
        for t in api.review.tracks(folder, filter)["tracks"]
    }


def statuses(api, folder):
    return {
        t["filename"]: t["status"]
        for filter in ("open", "decided", "exact")
        for t in api.review.tracks(folder, filter)["tracks"]
    }


def test_bulk_not_on_spotify_marks_all_selected_tracks(api, folder):
    fps = all_fingerprints(api, folder)
    selection = [fps["Alpha - Two (Extended Mix).mp3"], fps["Nobody - Missing.mp3"], fps["Alpha - One.mp3"]]

    result = api.review.bulk_not_on_spotify(folder, selection)

    assert (result["done"], result["skipped"], result["open_count"]) == (3, 0, 0)
    assert statuses(api, folder) == {
        "Alpha - One.mp3": "not_on_spotify",
        "Alpha - Two (Extended Mix).mp3": "not_on_spotify",
        "Nobody - Missing.mp3": "not_on_spotify",
    }


def test_bulk_not_on_spotify_skips_already_marked_and_unknown_tracks(api, folder):
    fps = all_fingerprints(api, folder)
    missing = fps["Nobody - Missing.mp3"]
    api.review.not_on_spotify(folder, missing)

    result = api.review.bulk_not_on_spotify(folder, [missing, fps["Alpha - One.mp3"], "gibt-es-nicht"])

    assert (result["done"], result["skipped"]) == (1, 2)


def test_bulk_search_only_searches_open_tracks_of_a_mixed_selection(api, folder, spotify):
    fps = all_fingerprints(api, folder)
    api.review.not_on_spotify(folder, fps["Alpha - Two (Extended Mix).mp3"])  # entschieden
    spotify.catalog.append(track("id_missing", "Nobody", "Missing"))  # inzwischen auf Spotify
    spotify.requests.clear()

    result = api.review.bulk_search(folder, list(fps.values()))

    assert (result["done"], result["skipped"], result["cancelled"]) == (1, 2, False)
    assert result["open_count"] == 0
    assert statuses(api, folder) == {
        "Alpha - One.mp3": "exact",
        "Alpha - Two (Extended Mix).mp3": "not_on_spotify",
        "Nobody - Missing.mp3": "exact",
    }
    queries = [r.url.params["q"] for r in spotify.searches()]
    assert queries and all("Missing" in q for q in queries)


def test_bulk_search_forces_new_search_of_approximate_tracks(api, folder, spotify, events):
    fps = all_fingerprints(api, folder)
    two = fps["Alpha - Two (Extended Mix).mp3"]
    # Das Cover ist von Spotify verschwunden, ein neuer Track ist hinzugekommen
    spotify.catalog[:] = [t for t in spotify.catalog if t["id"] != "id_two_cover"]
    spotify.catalog.append(track("id_two_live", "Alpha", "Two"))

    result = api.review.bulk_search(folder, [two, fps["Nobody - Missing.mp3"]])

    assert (result["done"], result["skipped"]) == (2, 0)
    detail = api.review.track(folder, two)
    assert detail["status"] == "approximate"
    assert {c["id"] for c in detail["candidates"]} == {"id_two", "id_two_live"}
    assert events.named("review.search_progress") == [
        {"done": 0, "total": 2},
        {"done": 1, "total": 2},
        {"done": 2, "total": 2},
    ]


def test_bulk_search_can_be_cancelled(api, folder, spotify):
    fps = all_fingerprints(api, folder)
    spotify.on_request = lambda request: api.review.cancel_search()

    result = api.review.bulk_search(folder, [fps["Alpha - Two (Extended Mix).mp3"], fps["Nobody - Missing.mp3"]])

    assert result["cancelled"] is True
    assert result["done"] < 2
    assert statuses(api, folder)["Nobody - Missing.mp3"] == "not_found"


# ---- Fehler beim Zugriff auf Spotify ------------------------------------------


def offline(request):
    raise httpx.ConnectError("offline", request=request)


def test_link_without_internet_is_reported_clearly(api, folder, spotify):
    missing = fingerprint(api, folder, "Nobody - Missing.mp3")
    spotify.on_request = offline

    with pytest.raises(ApiError, match="nicht erreichbar"):
        api.review.accept_link(folder, missing, f"spotify:track:{LINK_ID}")
    spotify.on_request = None
    assert api.review.track(folder, missing)["status"] == "not_found"  # unverändert


def test_link_without_login_asks_to_sign_in_again(api, folder, paths):
    missing = fingerprint(api, folder, "Nobody - Missing.mp3")
    paths.token_file.unlink()

    with pytest.raises(ApiError, match="Einrichtung"):
        api.review.accept_link(folder, missing, f"spotify:track:{LINK_ID}")


def test_link_without_client_id_is_reported_clearly(api, folder, paths):
    missing = fingerprint(api, folder, "Nobody - Missing.mp3")
    paths.config_file.unlink()

    with pytest.raises(ApiError):
        api.review.accept_link(folder, missing, f"spotify:track:{LINK_ID}")


def test_bulk_search_without_internet_is_reported_clearly(api, folder, spotify):
    fps = all_fingerprints(api, folder)
    spotify.on_request = offline

    with pytest.raises(ApiError, match="nicht erreichbar"):
        api.review.bulk_search(folder, [fps["Nobody - Missing.mp3"]])


def test_spotify_connections_are_closed_after_use(api, folder, ctx, monkeypatch):
    clients = []
    open_client = ctx.spotify

    def recording(*args, **kwargs):
        clients.append(open_client(*args, **kwargs))
        return clients[-1]

    monkeypatch.setattr(ctx, "spotify", recording)
    fps = all_fingerprints(api, folder)
    missing = fps["Nobody - Missing.mp3"]

    api.review.bulk_search(folder, [missing])
    with pytest.raises(ApiError):
        api.review.accept_link(folder, missing, "https://example.com/nix")

    assert len(clients) == 2
    assert all(c.http.is_closed for c in clients)
