from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LocalFile:
    """Eine Audiodatei auf der Festplatte samt ausgelesener Metadaten."""

    path: str
    size: int
    mtime: float
    artist: str | None
    title: str | None
    isrc: str | None
    duration_ms: int | None


@dataclass(frozen=True)
class Candidate:
    """Ein Spotify-Track, der als Treffer für eine lokale Datei in Frage kommt."""

    id: str
    name: str
    artists: tuple[str, ...]
    duration_ms: int | None = None
    isrc: str | None = None
    album: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "artists": list(self.artists),
            "duration_ms": self.duration_ms,
            "isrc": self.isrc,
            "album": self.album,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Candidate:
        return cls(
            id=d["id"],
            name=d["name"],
            artists=tuple(d.get("artists") or ()),
            duration_ms=d.get("duration_ms"),
            isrc=d.get("isrc"),
            album=d.get("album"),
        )

    @classmethod
    def from_spotify(cls, t: dict) -> Candidate:
        return cls(
            id=t["id"],
            name=t.get("name") or "",
            artists=tuple(a.get("name", "") for a in t.get("artists") or ()),
            duration_ms=t.get("duration_ms"),
            isrc=(t.get("external_ids") or {}).get("isrc"),
            album=(t.get("album") or {}).get("name"),
        )


# Match-Status, wie er in der DB steht
EXACT = "exact"
APPROXIMATE = "approximate"
MANUAL = "manual"
NOT_FOUND = "not_found"
NOT_ON_SPOTIFY = "not_on_spotify"

# Status, deren Track in die Playlist gehört
PLAYLIST_STATUSES = frozenset({EXACT, APPROXIMATE, MANUAL})
# Status, die im Review auftauchen („offen“)
REVIEW_STATUSES = frozenset({APPROXIMATE, NOT_FOUND})
# Status, die der Nutzer festgelegt hat („entschieden“)
DECIDED_STATUSES = frozenset({MANUAL, NOT_ON_SPOTIFY})


@dataclass
class MatchRecord:
    fingerprint: str
    status: str
    spotify_id: str | None
    candidates: list[Candidate] = field(default_factory=list)
    searched_at: str | None = None
