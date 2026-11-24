"""Berechnet, wie eine Playlist geändert werden muss, um dem Ordner zu entsprechen."""

from __future__ import annotations

from dataclasses import dataclass

from .models import LocalFile


@dataclass(frozen=True)
class Plan:
    final: list[str]  # gewünschter Endzustand der Playlist (Spotify-IDs, in Reihenfolge)
    desired: list[str]  # davon die Tracks, die aus dem Ordner stammen (von djsync verwaltet)
    added: list[str]
    removed: list[str]
    reordered: bool

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.reordered)


def desired_order(files: list[tuple[LocalFile, str]]) -> list[str]:
    """Neueste Datei (mtime) zuerst, bei Gleichstand nach Dateiname; ohne Duplikate."""
    ordered = sorted(files, key=lambda fs: (-fs[0].mtime, fs[0].path.rsplit("/", 1)[-1].lower()))
    return list(dict.fromkeys(spotify_id for _, spotify_id in ordered))


def compute_plan(desired: list[str], current: list[str], managed: set[str]) -> Plan:
    """
    desired:  Tracks laut Ordner, bereits sortiert
    current:  Tracks aktuell in der Playlist (Reihenfolge wie auf Spotify)
    managed:  Tracks, die djsync selbst hinzugefügt hat – nur diese darf es entfernen

    Von Hand hinzugefügte Tracks bleiben erhalten und stehen am Ende.
    """
    desired = list(dict.fromkeys(desired))
    desired_set = set(desired)
    current_set = set(current)

    unmanaged = [t for t in dict.fromkeys(current) if t not in desired_set and t not in managed]
    final = desired + unmanaged

    added = [t for t in desired if t not in current_set]
    removed = [t for t in dict.fromkeys(current) if t in managed and t not in desired_set]

    final_set = set(final)
    kept_current = [t for t in current if t in final_set]
    kept_final = [t for t in final if t in current_set]
    reordered = kept_current != kept_final

    return Plan(final=final, desired=desired, added=added, removed=removed, reordered=reordered)
