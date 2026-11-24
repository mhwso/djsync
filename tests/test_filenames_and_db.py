from djsync.db import Database
from djsync.filenames import parse_filename, windows_to_wsl
from djsync.models import MANUAL, Candidate, LocalFile
from djsync.review import parse_track_link


def test_parse_filename_with_tracknumber():
    assert parse_filename("01 - Artist - Title (Extended Mix)") == ("Artist", "Title (Extended Mix)")


def test_parse_filename_without_separator():
    assert parse_filename("Just A Title") == (None, "Just A Title")


def test_windows_to_wsl():
    assert windows_to_wsl("D:\\Musik\\Techno") == "/mnt/d/Musik/Techno"
    assert windows_to_wsl("d:/Musik/") == "/mnt/d/Musik"
    assert windows_to_wsl("/home/x") == "/home/x"


def test_parse_track_link():
    tid = "4uLU6hMCjMI75M1A2tKUQC"
    assert parse_track_link(f"https://open.spotify.com/intl-de/track/{tid}?si=abc") == tid
    assert parse_track_link(f"spotify:track:{tid}") == tid
    assert parse_track_link(tid) == tid
    assert parse_track_link("https://open.spotify.com/album/xyz") is None


def _file(path):
    return LocalFile(path, 1, 1.0, "A", "T", None, None)


def test_files_under_respects_folder_boundary():
    db = Database(":memory:")
    db.upsert_file(_file("/m/Techno/a.mp3"), "fp")
    db.upsert_file(_file("/m/Techno 2/b.mp3"), "fp")
    db.upsert_file(_file("/m/Tech_o/c.mp3"), "fp")
    assert list(db.files_under("/m/Techno")) == ["/m/Techno/a.mp3"]


def test_move_files_rewrites_prefix():
    db = Database(":memory:")
    db.upsert_file(_file("/m/Old/sub/a.mp3"), "fp")
    assert db.move_files("/m/Old", "/m/New") == 1
    assert list(db.files_under("/m/New")) == ["/m/New/sub/a.mp3"]


def test_match_roundtrip_keeps_candidates():
    db = Database(":memory:")
    c = Candidate("id1", "Track", ("A",), 1000, "ISRC", "Album")
    db.save_match("fp", "approximate", "id1", [c])
    db.save_match("fp", MANUAL, "id1")  # Kandidaten bleiben erhalten
    m = db.get_match("fp")
    assert m.status == MANUAL and m.candidates == [c]


def test_managed_tracks():
    db = Database(":memory:")
    db.set_managed_tracks("pl", ["a", "b", "a"])
    assert db.managed_tracks("pl") == {"a", "b"}
