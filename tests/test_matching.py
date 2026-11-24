from djsync.matching import (
    choose_best,
    fingerprint,
    normalize_mix,
    parse_title,
    score_candidate,
    split_artists,
    split_artists_raw,
    split_title,
)
from djsync.models import APPROXIMATE, EXACT, NOT_FOUND, Candidate, LocalFile


def local(artist, title, duration_ms=None, isrc=None):
    return LocalFile("/m/x.mp3", 1, 0.0, artist, title, isrc, duration_ms)


def cand(id_, artists, name, duration_ms=None, isrc=None):
    return Candidate(id_, name, tuple(artists), duration_ms, isrc)


# ---- Parsing -------------------------------------------------------------


def test_parse_beatport_style():
    p = parse_title("Strobe (Extended Mix)")
    assert (p.base, p.mix) == ("strobe", "extended")


def test_parse_spotify_style():
    p = parse_title("Strobe - Extended Mix")
    assert (p.base, p.mix) == ("strobe", "extended")


def test_original_mix_is_neutral():
    assert parse_title("Track (Original Mix)").mix == ""
    assert parse_title("Track - Original Mix").mix == ""
    assert parse_title("Track").mix == ""


def test_remaster_is_neutral():
    assert normalize_mix("2015 Remaster") == ""


def test_remix_keeps_remixer():
    assert parse_title("Track (Someone Remix)").mix == "someone remix"
    assert parse_title("Track - Someone Remix").mix == "someone remix"


def test_non_mix_brackets_stay_in_title():
    assert parse_title("Intro (Part 2)").base == "intro part 2"


def test_featuring_extracted():
    p = parse_title("Song (feat. Singer) [Club Mix]")
    assert p.base == "song"
    assert p.mix == "club"
    assert p.featured == ["singer"]


def test_featuring_inline():
    p = parse_title("Song feat. Singer & Other")
    assert p.base == "song"
    assert p.featured == ["singer", "other"]


def test_split_artists_variants():
    assert split_artists("A & B, C feat. D") == ["a", "b", "c", "d"]
    assert split_artists("Café x Böse") == ["cafe", "bose"]


def test_dash_in_title_is_not_mix():
    assert parse_title("Back - To - Basics").base == "back to basics"


# ---- Fingerprint ---------------------------------------------------------


def test_fingerprint_prefers_isrc():
    assert fingerprint(local("A", "T", isrc="us-abc-12-34567")) == "isrc:USABC1234567"


def test_fingerprint_ignores_formatting():
    a = fingerprint(local("B & A", "Track (Original Mix)"))
    b = fingerprint(local("A, B", "track"))
    assert a == b


def test_fingerprint_distinguishes_versions():
    assert fingerprint(local("A", "T (Extended Mix)")) != fingerprint(local("A", "T (Radio Edit)"))


def test_fingerprint_none_without_title():
    assert fingerprint(local("A", None)) is None


# ---- Bewertung -----------------------------------------------------------


def test_exact_match_beatport_vs_spotify():
    f = local("Deadmau5", "Strobe (Extended Mix)", 637_000)
    c = cand("1", ["deadmau5"], "Strobe - Extended Mix", 638_500)
    assert score_candidate(f, c).exact


def test_exact_match_original_mix_vs_plain():
    f = local("Artist", "Track (Original Mix)", 400_000)
    c = cand("1", ["Artist"], "Track", 401_000)
    assert score_candidate(f, c).exact


def test_duration_outside_tolerance_is_not_exact():
    f = local("Artist", "Track", 400_000)
    c = cand("1", ["Artist"], "Track", 410_000)
    s = score_candidate(f, c)
    assert not s.exact and not s.duration_ok


def test_isrc_match_is_exact():
    f = local("x", "y", isrc="USABC1234567")
    c = cand("1", ["other"], "other", isrc="USABC1234567")
    assert score_candidate(f, c).exact


def test_remix_with_remixer_as_artist():
    f = local("Orig", "Track (Someone Remix)", 300_000)
    c = cand("1", ["Orig", "Someone"], "Track - Someone Remix", 300_000)
    assert score_candidate(f, c).exact


def test_choose_prefers_exact_version():
    f = local("Artist", "Track (Extended Mix)", 400_000)
    radio = cand("radio", ["Artist"], "Track - Radio Edit", 200_000)
    ext = cand("ext", ["Artist"], "Track - Extended Mix", 400_000)
    r = choose_best(f, [radio, ext])
    assert (r.status, r.spotify_id) == (EXACT, "ext")


def test_choose_other_version_is_approximate():
    f = local("Artist", "Track (Extended Mix)", 400_000)
    radio = cand("radio", ["Artist"], "Track - Radio Edit", 200_000)
    r = choose_best(f, [radio])
    assert (r.status, r.spotify_id) == (APPROXIMATE, "radio")


def test_choose_unrelated_is_not_found():
    f = local("Artist", "Track", 400_000)
    other = cand("x", ["Somebody Else"], "Completely Different", 200_000)
    r = choose_best(f, [other])
    assert r.status == NOT_FOUND and r.spotify_id is None
    assert [c.id for c, _ in r.ranked] == ["x"]


def test_choose_no_candidates():
    assert choose_best(local("A", "B"), []).status == NOT_FOUND


def test_choose_skips_higher_scored_candidate_with_wrong_title():
    # „In The House“ hat durch passenden Mix den höheren Score, aber der Titel passt nicht
    f = local("Angelo Ferreri", "In The City (Original Mix)", 343_000)
    house = cand("house", ["Angelo Ferreri", "Hatiras"], "In The House", 390_000)
    edit = cand("edit", ["Angelo Ferreri"], "In The City - Edit", 172_000)
    r = choose_best(f, [house, edit])
    assert (r.status, r.spotify_id) == (APPROXIMATE, "edit")


# ---- Rohform für Suchanfragen ---------------------------------------------


def test_split_title_keeps_original_spelling():
    t = split_title("What's Going On (feat. Singer) (Original Mix)")
    assert (t.base, t.mix, t.featured) == ("What's Going On", "Original Mix", ["Singer"])


def test_split_title_spotify_style():
    t = split_title("Yes Ron - Onno Remix")
    assert (t.base, t.mix) == ("Yes Ron", "Onno Remix")


def test_split_artists_raw_keeps_ampersand_names():
    assert split_artists_raw("&ME") == ["&ME"]
    assert split_artists_raw("Carbon, Wahrlich") == ["Carbon", "Wahrlich"]
    assert split_artists_raw("Leftwing & Kody feat. Jen Miras") == ["Leftwing", "Kody", "Jen Miras"]
    assert split_artists_raw("HANNS (DE)") == ["HANNS (DE)"]


def test_country_tag_in_artist_is_ignored():
    f = local("SLV (DE)", "Liminal Space (Original Mix)", 312_827)
    c = cand("1", ["SLV"], "Liminal Space", 312_827)
    assert score_candidate(f, c).exact


def test_country_tag_does_not_change_fingerprint():
    assert fingerprint(local("SLV (DE)", "X")) != fingerprint(local("SLV", "X"))


def test_specific_mix_wins_over_original_mix():
    assert parse_title("Sexgas (Arnaud Le Texier Rmx) (Original Mix)").mix == "arnaud le texier remix"
    assert parse_title("Sexgas - Arnaud Le Texier Remix").mix == "arnaud le texier remix"


def test_dash_suffix_with_hyphenated_remixer():
    p = parse_title("Right Moment - D-Unity Remix")
    assert (p.base, p.mix) == ("right moment", "d unity remix")


def test_colon_separated_artists():
    assert split_artists("Leftwing : Kody") == ["leftwing", "kody"]
    assert split_artists_raw("Leftwing : Kody") == ["Leftwing", "Kody"]
