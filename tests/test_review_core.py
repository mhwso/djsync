"""Review-Entscheidungen im Kern: echte SQLite-Datei, Spotify als Fake auf HTTP-Ebene."""

import builtins
import json
import time

import httpx
import pytest

from djsync.auth import Auth
from djsync.db import Database
from djsync.models import (
    APPROXIMATE,
    EXACT,
    MANUAL,
    NOT_FOUND,
    NOT_ON_SPOTIFY,
    Candidate,
    LocalFile,
)
from djsync.review import pending_reviews, run_review
from djsync.review_core import (
    DECIDED,
    EXACT_FILTER,
    OPEN,
    InvalidLinkError,
    ReviewError,
    TrackUnavailableError,
    accept_candidate,
    accept_link,
    mark_not_on_spotify,
    next_open_track,
    reset_to_open,
    review_tracks,
)
from djsync.spotify import SpotifyClient

FOLDER = "/musik/Techno"


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "djsync.db")
    yield database
    database.close()


def reopen(db: Database) -> Database:
    """Neue Verbindung auf dieselbe Datei – zeigt, was wirklich gespeichert ist."""
    path = db.conn.execute("PRAGMA database_list").fetchone()["file"]
    return Database(path)


def cand(i: int) -> Candidate:
    return Candidate(f"{i:022d}", f"Titel {i}", ("Artist",), 300_000, None, "Album")


def add_track(db, name, fingerprint, status, spotify_id=None, candidates=()):
    db.upsert_file(LocalFile(f"{FOLDER}/{name}", 1, 1.0, "Artist", name, None, 300_000), fingerprint)
    db.save_match(fingerprint, status, spotify_id, list(candidates))
    db.commit()


def test_accept_candidate_sets_manual_and_persists(db):
    add_track(db, "a.mp3", "fp-a", APPROXIMATE, cand(1).id, [cand(1), cand(2)])

    accept_candidate(db, "fp-a", cand(2).id)

    record = reopen(db).get_match("fp-a")
    assert record.status == MANUAL
    assert record.spotify_id == cand(2).id
    assert record.candidates == [cand(1), cand(2)]


def test_accept_candidate_rejects_unknown_id(db):
    add_track(db, "a.mp3", "fp-a", APPROXIMATE, cand(1).id, [cand(1)])

    with pytest.raises(ReviewError):
        accept_candidate(db, "fp-a", cand(9).id)

    assert reopen(db).get_match("fp-a").status == APPROXIMATE


# ---- Spotify-Fake auf HTTP-Ebene ---------------------------------------------


def track_json(c: Candidate) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "artists": [{"name": a} for a in c.artists],
        "duration_ms": c.duration_ms,
        "external_ids": {"isrc": c.isrc} if c.isrc else {},
        "album": {"name": c.album},
    }


@pytest.fixture
def spotify(tmp_path):
    """SpotifyClient gegen einen Fake: bekannte Tracks liefern 200, alle anderen 404."""
    tracks: dict[str, Candidate] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        prefix = "/v1/tracks/"
        if request.method == "GET" and request.url.path.startswith(prefix):
            c = tracks.get(request.url.path[len(prefix):])
            if c:
                return httpx.Response(200, json=track_json(c))
            return httpx.Response(404, json={"error": {"status": 404, "message": "Not found"}})
        return httpx.Response(400)

    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps({"access_token": "t", "refresh_token": "r", "expires_at": time.time() + 3600}))
    auth = Auth("client", "http://127.0.0.1/cb", [], token_path)
    client = SpotifyClient(auth, transport=httpx.MockTransport(handler))
    client.tracks = tracks  # bekannte Tracks, im Test zu befüllen
    yield client
    client.close()


def test_accept_link_fetches_track_and_puts_it_first(db, spotify):
    add_track(db, "a.mp3", "fp-a", APPROXIMATE, cand(1).id, [cand(1), cand(2)])
    spotify.tracks[cand(7).id] = cand(7)

    result = accept_link(db, spotify, "fp-a", f"https://open.spotify.com/intl-de/track/{cand(7).id}?si=x")

    assert result == cand(7)
    record = reopen(db).get_match("fp-a")
    assert record.status == MANUAL
    assert record.spotify_id == cand(7).id
    assert record.candidates == [cand(7), cand(1), cand(2)]


def test_accept_link_does_not_duplicate_known_candidate(db, spotify):
    add_track(db, "a.mp3", "fp-a", APPROXIMATE, cand(1).id, [cand(1), cand(2)])
    spotify.tracks[cand(2).id] = cand(2)

    accept_link(db, spotify, "fp-a", f"spotify:track:{cand(2).id}")

    assert reopen(db).get_match("fp-a").candidates == [cand(2), cand(1)]


def test_accept_link_rejects_invalid_link(db, spotify):
    add_track(db, "a.mp3", "fp-a", APPROXIMATE, cand(1).id, [cand(1)])

    with pytest.raises(InvalidLinkError):
        accept_link(db, spotify, "fp-a", "https://open.spotify.com/album/xyz")

    assert reopen(db).get_match("fp-a").status == APPROXIMATE


def test_accept_link_reports_unavailable_track(db, spotify):
    add_track(db, "a.mp3", "fp-a", APPROXIMATE, cand(1).id, [cand(1)])

    with pytest.raises(TrackUnavailableError):
        accept_link(db, spotify, "fp-a", cand(8).id)

    assert reopen(db).get_match("fp-a").status == APPROXIMATE


def test_mark_not_on_spotify_persists_and_keeps_candidates(db):
    add_track(db, "a.mp3", "fp-a", APPROXIMATE, cand(1).id, [cand(1)])

    mark_not_on_spotify(db, "fp-a")

    record = reopen(db).get_match("fp-a")
    assert record.status == NOT_ON_SPOTIFY
    assert record.spotify_id is None
    assert record.candidates == [cand(1)]


def test_reset_with_candidates_becomes_approximate(db):
    add_track(db, "a.mp3", "fp-a", MANUAL, cand(2).id, [cand(2), cand(1)])

    assert reset_to_open(db, "fp-a") == APPROXIMATE

    record = reopen(db).get_match("fp-a")
    assert record.status == APPROXIMATE
    assert record.spotify_id == cand(2).id
    assert record.candidates == [cand(2), cand(1)]


def test_reset_without_candidates_becomes_not_found(db):
    add_track(db, "a.mp3", "fp-a", NOT_ON_SPOTIFY)

    assert reset_to_open(db, "fp-a") == NOT_FOUND

    record = reopen(db).get_match("fp-a")
    assert record.status == NOT_FOUND
    assert record.spotify_id is None


def test_reset_does_not_search_again(db, spotify):
    # Der Fake beantwortet keine Suche; ein Aufruf würde hier als 400 scheitern
    add_track(db, "a.mp3", "fp-a", NOT_ON_SPOTIFY, None, [cand(1)])

    assert reset_to_open(db, "fp-a") == APPROXIMATE
    assert reopen(db).get_match("fp-a").spotify_id == cand(1).id


@pytest.mark.parametrize("status", [EXACT, APPROXIMATE, NOT_FOUND])
def test_reset_rejects_tracks_that_are_not_decided(db, status):
    add_track(db, "a.mp3", "fp-a", status, cand(1).id, [cand(1)])

    with pytest.raises(ReviewError):
        reset_to_open(db, "fp-a")

    assert reopen(db).get_match("fp-a").status == status


# ---- Filter und nächster offener Track ----------------------------------------


@pytest.fixture
def folder(db):
    """Ein Ordner mit je einem Track pro Treffer-Status, dazu Fremdes und Doppeltes."""
    add_track(db, "e_manual.mp3", "fp-manual", MANUAL, cand(1).id, [cand(1)])
    add_track(db, "a_exact.mp3", "fp-exact", EXACT, cand(2).id, [cand(2)])
    add_track(db, "d_approx.mp3", "fp-approx", APPROXIMATE, cand(3).id, [cand(3)])
    add_track(db, "b_missing.mp3", "fp-missing", NOT_FOUND)
    add_track(db, "c_nos.mp3", "fp-nos", NOT_ON_SPOTIFY)
    # dieselbe Aufnahme ein zweites Mal im Ordner – taucht nur einmal auf
    add_track(db, "f_approx_copy.mp3", "fp-approx", APPROXIMATE, cand(3).id, [cand(3)])
    # Track in einem anderen Ordner
    db.upsert_file(LocalFile("/musik/House/x.mp3", 1, 1.0, "A", "X", None, None), "fp-other")
    db.save_match("fp-other", NOT_FOUND, None, [])
    db.commit()
    return FOLDER


def names(tracks):
    return [t.file.path.rsplit("/", 1)[1] for t in tracks]


def test_filter_open_lists_approximate_and_not_found_in_folder_order(db, folder):
    tracks = review_tracks(db, folder, OPEN)
    assert names(tracks) == ["b_missing.mp3", "d_approx.mp3"]
    assert [t.record.status for t in tracks] == [NOT_FOUND, APPROXIMATE]


def test_filter_open_is_default(db, folder):
    assert names(review_tracks(db, folder)) == ["b_missing.mp3", "d_approx.mp3"]


def test_filter_decided_lists_manual_and_not_on_spotify(db, folder):
    assert names(review_tracks(db, folder, DECIDED)) == ["c_nos.mp3", "e_manual.mp3"]


def test_filter_exact(db, folder):
    assert names(review_tracks(db, folder, EXACT_FILTER)) == ["a_exact.mp3"]


def test_unknown_filter_is_an_error(db, folder):
    with pytest.raises(ValueError):
        review_tracks(db, folder, "alle")


def test_decision_moves_track_between_filters(db, folder):
    mark_not_on_spotify(db, "fp-approx")
    assert names(review_tracks(db, folder, OPEN)) == ["b_missing.mp3"]
    assert names(review_tracks(db, folder, DECIDED)) == ["c_nos.mp3", "d_approx.mp3", "e_manual.mp3"]


def test_next_open_track_starts_at_first_open(db, folder):
    assert next_open_track(db, folder).fingerprint == "fp-missing"


def test_next_open_track_follows_folder_order(db, folder):
    assert next_open_track(db, folder, after="fp-missing").fingerprint == "fp-approx"


def test_next_open_track_after_decided_track(db, folder):
    # nach einer Entscheidung ist der aktuelle Track nicht mehr offen – weiter ab seiner Position
    mark_not_on_spotify(db, "fp-missing")
    assert next_open_track(db, folder, after="fp-missing").fingerprint == "fp-approx"


def test_next_open_track_wraps_around(db, folder):
    assert next_open_track(db, folder, after="fp-approx").fingerprint == "fp-missing"


def test_next_open_track_none_when_all_decided(db, folder):
    mark_not_on_spotify(db, "fp-missing")
    mark_not_on_spotify(db, "fp-approx")
    assert next_open_track(db, folder, after="fp-approx") is None


def test_next_open_track_does_not_return_current_track(db, folder):
    mark_not_on_spotify(db, "fp-missing")
    assert next_open_track(db, folder, after="fp-approx") is None


# ---- CLI-Review auf Basis des Kerns ---------------------------------------------


def scripted_input(monkeypatch, answers):
    """Beantwortet Eingaben der Reihe nach; danach Strg+D (EOFError)."""
    it = iter(answers)

    def fake_input(*_args):
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr(builtins, "input", fake_input)


def test_cli_review_keys_save_decisions(db, spotify, monkeypatch):
    add_track(db, "a.mp3", "fp-a", APPROXIMATE, cand(1).id, [cand(1), cand(2)])
    add_track(db, "b.mp3", "fp-b", NOT_FOUND)
    add_track(db, "c.mp3", "fp-c", APPROXIMATE, cand(3).id, [cand(3)])
    add_track(db, "d.mp3", "fp-d", NOT_FOUND)
    spotify.tracks[cand(7).id] = cand(7)
    # a: ungültige Eingabe, dann Vorschlag 2 · b: ungültiger Link, nicht abrufbar, gültiger Link
    # c: überspringen · d: nicht auf Spotify
    scripted_input(monkeypatch, ["9", "2", "l", "kein link", "l", cand(8).id, "l", cand(7).id, "s", "n"])
    pending = pending_reviews(list(db.files_under(FOLDER).values()), db)

    changed = run_review(sorted(pending, key=lambda p: p[0].path), db, spotify, duration_tolerance_ms=3000)

    assert changed == 3
    stored = reopen(db)
    assert (stored.get_match("fp-a").status, stored.get_match("fp-a").spotify_id) == (MANUAL, cand(2).id)
    assert (stored.get_match("fp-b").status, stored.get_match("fp-b").spotify_id) == (MANUAL, cand(7).id)
    assert stored.get_match("fp-c").status == APPROXIMATE
    assert stored.get_match("fp-d").status == NOT_ON_SPOTIFY


@pytest.mark.parametrize("answers", [["q"], []])
def test_cli_review_quit_and_ctrl_d_stop_without_changes(db, spotify, monkeypatch, answers):
    add_track(db, "a.mp3", "fp-a", APPROXIMATE, cand(1).id, [cand(1)])
    scripted_input(monkeypatch, answers)
    pending = pending_reviews(list(db.files_under(FOLDER).values()), db)

    assert run_review(pending, db, spotify, duration_tolerance_ms=3000) == 0
    assert reopen(db).get_match("fp-a").status == APPROXIMATE
