"""Update-Prüfung: Gibt es auf GitHub ein neueres Release als die laufende Version?

Die Oberfläche ruft das bei jedem Start im Hintergrund auf. Installiert wird von Hand über den
Installer aus dem Release, djsync zeigt nur einen Hinweis mit Link.
"""

from __future__ import annotations

import re

import httpx

from ... import __version__
from .base import ApiArea

REPO = "mhwso/djsync"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
_VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+)*)$")


class UpdatesApi(ApiArea):
    def check(self) -> dict | None:
        """Neueres Release als `{version, current, url}`, sonst None.

        Fehler (offline, Rate-Limit, noch kein Release, unlesbare Antwort) zählen als „kein
        Update“: Die Prüfung darf den Start nie stören.
        """
        try:
            with self._ctx.http() as http:
                response = http.get(LATEST_RELEASE_URL, headers={"Accept": "application/vnd.github+json"})
                response.raise_for_status()
                release = response.json()
            tag = release["tag_name"]
            latest = _parse(tag)
            url = release["html_url"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None
        current = _parse(__version__)
        if latest is None or current is None or latest <= current:
            return None
        return {"version": tag.removeprefix("v"), "current": __version__, "url": url}


def _parse(version: object) -> tuple[int, ...] | None:
    """„v0.3.0“ → (0, 3); alles andere (z. B. Vorabversionen) → None.

    Nullen am Ende fallen weg, damit 0.3 und 0.3.0 als gleich gelten."""
    m = _VERSION_RE.match(version) if isinstance(version, str) else None
    if not m:
        return None
    parts = [int(part) for part in m.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)
