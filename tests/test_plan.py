from djsync.models import LocalFile
from djsync.plan import compute_plan, desired_order


def f(name, mtime):
    return LocalFile(f"/m/{name}", 1, mtime, None, None, None, None)


def test_desired_order_newest_first_then_name():
    files = [(f("b.mp3", 1), "B"), (f("c.mp3", 3), "C"), (f("a.mp3", 1), "A")]
    assert desired_order(files) == ["C", "A", "B"]


def test_desired_order_dedupes_same_track():
    files = [(f("a.mp3", 2), "X"), (f("a-copy.mp3", 1), "X")]
    assert desired_order(files) == ["X"]


def test_new_playlist_adds_everything():
    p = compute_plan(["A", "B"], [], set())
    assert p.added == ["A", "B"] and p.removed == [] and p.final == ["A", "B"]
    assert p.has_changes


def test_no_changes():
    p = compute_plan(["A", "B"], ["A", "B"], {"A", "B"})
    assert not p.has_changes


def test_removes_only_managed_tracks():
    p = compute_plan(["A"], ["A", "B", "MANUAL"], {"A", "B"})
    assert p.removed == ["B"]
    assert p.final == ["A", "MANUAL"]


def test_unmanaged_tracks_kept_at_end():
    p = compute_plan(["NEW", "A"], ["MANUAL", "A"], {"A"})
    assert p.final == ["NEW", "A", "MANUAL"]
    assert p.added == ["NEW"]
    assert p.reordered  # MANUAL wandert ans Ende


def test_reorder_detected():
    p = compute_plan(["B", "A"], ["A", "B"], {"A", "B"})
    assert p.reordered and not p.added and not p.removed


def test_pure_append_at_top_is_not_reorder():
    p = compute_plan(["NEW", "A", "B"], ["A", "B"], {"A", "B"})
    assert p.added == ["NEW"] and not p.reordered


def test_duplicates_in_playlist_are_cleaned():
    p = compute_plan(["A"], ["A", "A"], {"A"})
    assert p.final == ["A"] and p.has_changes


def test_retry_researches_only_automatic_results():
    from djsync.config import Config
    from djsync.db import now_iso
    from djsync.models import APPROXIMATE, EXACT, MANUAL, NOT_FOUND, NOT_ON_SPOTIFY, MatchRecord
    from djsync.sync import needs_search

    cfg = Config(client_id="x")

    def rec(status):
        return MatchRecord(fingerprint="tag:a|b|", status=status, spotify_id=None, candidates=[], searched_at=now_iso())

    assert not needs_search(rec(NOT_FOUND), cfg)
    assert not needs_search(rec(APPROXIMATE), cfg)
    assert needs_search(rec(NOT_FOUND), cfg, retry=True)
    assert needs_search(rec(APPROXIMATE), cfg, retry=True)
    for status in (EXACT, MANUAL, NOT_ON_SPOTIFY):
        assert not needs_search(rec(status), cfg, retry=True)


def test_playlist_name_is_prefixed_once():
    from djsync.sync import playlist_name

    assert playlist_name("2026") == "DJSYNC - 2026"
    assert playlist_name("House Promos") == "DJSYNC - House Promos"
    assert playlist_name("DJSYNC - House") == "DJSYNC - House"
