"""Normalisierung, Fingerprints und Bewertung von Spotify-Kandidaten.

Reine Logik ohne I/O – vollständig per Unit-Test abgedeckt.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .models import APPROXIMATE, EXACT, NOT_FOUND, Candidate, LocalFile

# Wörter, an denen man eine Versions-/Mix-Angabe erkennt
MIX_KEYWORDS = frozenset(
    {
        "mix", "remix", "edit", "version", "dub", "rework", "bootleg", "vip",
        "remaster", "remastered", "instrumental", "acapella", "flip", "refix",
        "reprise", "extended", "radio", "club", "live", "rmx",
    }
)
# Mix-Angaben, die gleichbedeutend mit „keine Angabe“ sind (nach normalize_mix)
NEUTRAL_MIXES = frozenset({"", "original", "album"})
# Füllwörter, die beim Vergleich von Mix-Namen ignoriert werden
_MIX_FILLER = frozenset({"mix", "version"})
_MIX_SYNONYMS = {"rmx": "remix"}

ARTIST_MATCH_THRESHOLD = 0.85

_BRACKETS_RE = re.compile(r"[\(\[]([^\(\)\[\]]*)[\)\]]")
_FEAT_PREFIX_RE = re.compile(r"^(?:feat|ft|featuring)\b\.?\s*", re.I)
_FEAT_INLINE_RE = re.compile(r"\s+(?:feat|ft|featuring)\b\.?\s+(.+)$", re.I)
_DASH_SUFFIX_RE = re.compile(r"\s+[-–—]\s+((?:(?!\s[-–—]\s).)+)$")
_ARTIST_SPLIT_RE = re.compile(
    r"\s*(?:,|;|/|&|\+|\s:\s|\band\b|\bx\b|\bvs\b\.?|\bfeat\b\.?|\bft\b\.?|\bfeaturing\b|\bwith\b)\s*",
    re.I,
)
_RAW_ARTIST_SPLIT_RE = re.compile(
    r"\s*[,;/]\s*|\s+(?:&|\+|:|and|x|vs\.?|feat\.?|ft\.?|featuring|with)\s+",
    re.I,
)


# --------------------------------------------------------------------------
# Normalisierung
# --------------------------------------------------------------------------


def normalize_text(s: str) -> str:
    """Kleinschreibung, Akzente entfernen, Satzzeichen zu Leerzeichen."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^\w\s]|_", " ", s)
    return " ".join(s.split())


def normalize_isrc(isrc: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", isrc).upper()


def split_artists(s: str) -> list[str]:
    """'A feat. B & C' → ['a', 'b', 'c'] (normalisiert, ohne Duplikate)."""
    parts = (normalize_text(p) for p in _ARTIST_SPLIT_RE.split(s or ""))
    return _dedupe(p for p in parts if p)


def is_mix(text: str) -> bool:
    return bool(set(normalize_text(text).split()) & MIX_KEYWORDS)


def normalize_mix(mix: str) -> str:
    words = normalize_text(mix).split()
    if "remaster" in words or "remastered" in words:
        return ""
    words = [_MIX_SYNONYMS.get(w, w) for w in words]
    n = " ".join(w for w in words if w not in _MIX_FILLER)
    return "" if n in NEUTRAL_MIXES else n


@dataclass(frozen=True)
class ParsedTitle:
    base: str
    mix: str
    featured: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RawTitle:
    """Wie ParsedTitle, aber in Original-Schreibweise (für Suchanfragen)."""

    base: str
    mix: str
    featured: list[str] = field(default_factory=list)


def split_title(title: str) -> RawTitle:
    """Zerlegt einen Titel in Basistitel, Mix-Angabe und Featured-Artists – ohne Normalisierung.

    Versteht sowohl Beatport-Stil „Track (Extended Mix)“ als auch
    Spotify-Stil „Track - Extended Mix“.
    """
    featured: list[str] = []
    mix = ""

    def repl(m: re.Match) -> str:
        nonlocal mix
        content = m.group(1).strip()
        if _FEAT_PREFIX_RE.match(content):
            featured.append(_FEAT_PREFIX_RE.sub("", content).strip())
            return " "
        if is_mix(content):
            if not normalize_mix(mix):
                mix = content
            return " "
        return m.group(0)

    remaining = _BRACKETS_RE.sub(repl, title or "").strip()

    m = _DASH_SUFFIX_RE.search(remaining)
    if m and not mix and is_mix(m.group(1)):
        mix = m.group(1).strip()
        remaining = remaining[: m.start()]

    m = _FEAT_INLINE_RE.search(remaining)
    if m:
        featured.append(m.group(1).strip())
        remaining = remaining[: m.start()]

    return RawTitle(" ".join(remaining.split()), mix, featured)


def parse_title(title: str) -> ParsedTitle:
    """Wie split_title, aber normalisiert – für Vergleiche und Fingerprints."""
    raw = split_title(title)
    featured = [a for f in raw.featured for a in split_artists(f)]
    return ParsedTitle(normalize_text(raw.base), normalize_mix(raw.mix), _dedupe(featured))


def split_artists_raw(s: str) -> list[str]:
    """Wie split_artists, aber in Original-Schreibweise. Trennt an „&“ & Co. nur,
    wenn Leerzeichen drumherum stehen – damit Namen wie „&ME“ erhalten bleiben."""
    parts = (p.strip() for p in _RAW_ARTIST_SPLIT_RE.split(s or ""))
    return _dedupe(p for p in parts if p)


def fingerprint(f: LocalFile) -> str | None:
    """Stabiler Schlüssel eines Tracks, unabhängig von Dateiname und Ordner."""
    if f.isrc and normalize_isrc(f.isrc):
        return "isrc:" + normalize_isrc(f.isrc)
    p = parse_title(f.title or "")
    if not p.base:
        return None
    artists = sorted(set(split_artists(f.artist or "") + p.featured))
    return "tag:" + "|".join([",".join(artists), p.base, p.mix])


# --------------------------------------------------------------------------
# Bewertung
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Score:
    value: float
    exact: bool
    title: float
    artist: float
    mix: float
    duration_ok: bool


@dataclass
class MatchResult:
    status: str
    spotify_id: str | None
    ranked: list[tuple[Candidate, Score]]


def _ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _coverage(a: list[str], b: list[str]) -> float:
    """Anteil der Namen in a, die (unscharf) auch in b vorkommen."""
    if not a:
        return 0.0
    hits = sum(1 for x in a if any(_ratio(x, y) >= ARTIST_MATCH_THRESHOLD for y in b))
    return hits / len(a)


def score_candidate(f: LocalFile, c: Candidate, duration_tolerance_ms: int = 3000) -> Score:
    if f.isrc and c.isrc and normalize_isrc(f.isrc) == normalize_isrc(c.isrc):
        return Score(1.0, True, 1.0, 1.0, 1.0, True)

    lp = parse_title(f.title or "")
    cp = parse_title(c.name)
    la = _dedupe(_comparable_artists([f.artist]) + lp.featured)
    ca = _dedupe(_comparable_artists(c.artists) + cp.featured)

    title = _ratio(lp.base, cp.base)
    artist = max(_coverage(la, ca), _coverage(ca, la))
    if lp.mix == cp.mix:
        mix = 1.0
    elif not lp.mix or not cp.mix:
        mix = 0.0
    else:
        mix = _ratio(lp.mix, cp.mix)

    duration_ok = (
        f.duration_ms is None
        or c.duration_ms is None
        or abs(f.duration_ms - c.duration_ms) <= duration_tolerance_ms
    )
    value = 0.45 * title + 0.35 * artist + 0.20 * mix - (0.0 if duration_ok else 0.1)
    exact = title >= 0.92 and artist >= 0.999 and mix >= 0.9 and duration_ok
    return Score(round(value, 4), exact, title, artist, mix, duration_ok)


def choose_best(
    f: LocalFile,
    candidates: list[Candidate],
    *,
    duration_tolerance_ms: int = 3000,
    min_score: float = 0.7,
) -> MatchResult:
    unique = list({c.id: c for c in candidates}.values())
    ranked = sorted(
        ((c, score_candidate(f, c, duration_tolerance_ms)) for c in unique),
        key=lambda cs: (cs[1].exact, cs[1].value),
        reverse=True,
    )
    if ranked and ranked[0][1].exact:
        return MatchResult(EXACT, ranked[0][0].id, ranked)
    # bester Kandidat, der die Mindestanforderungen erfüllt – nicht zwingend der mit dem höchsten Score
    for c, s in ranked:
        if s.value >= min_score and s.title >= 0.75 and s.artist >= 0.5:
            return MatchResult(APPROXIMATE, c.id, ranked)
    return MatchResult(NOT_FOUND, None, ranked)


# Beatport-Unterscheidungskürzel wie „SLV (DE)“ oder „Flex (UK)“ – Spotify führt den Artist ohne
_COUNTRY_TAG_RE = re.compile(r"\s*\((?:[A-Z]{2}|USA)\)")


def _comparable_artists(raw_names) -> list[str]:
    """Normalisierte Artist-Namen für den Vergleich, ohne Länderkürzel."""
    return _dedupe(n for raw in raw_names for n in split_artists(_COUNTRY_TAG_RE.sub("", raw or "")))


def _dedupe(items) -> list:
    return list(dict.fromkeys(items))
