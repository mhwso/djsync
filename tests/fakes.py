"""Weitere Fakes für das Test-Gerüst: GitHub auf HTTP-Ebene, Events, gemeinsamer Transport.

Der Spotify-Fake liegt in tests/fake_spotify.py; `router` verteilt Anfragen nach Host.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx
from fake_spotify import FakeSpotify

from djsync.config import SCOPES


class FakeGitHub:
    """GitHub-Release-Abfrage: GET /repos/{owner}/{repo}/releases/latest."""

    def __init__(self, latest_tag: str | None = "v0.0.0"):
        self.latest_tag = latest_tag
        self.offline = False  # True → Verbindungsfehler wie ohne Internet
        self.status = 200  # z. B. 403 für Rate-Limit, 500 für Serverfehler
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.offline:
            raise httpx.ConnectError("offline", request=request)
        m = re.fullmatch(r"/repos/([^/]+)/([^/]+)/releases/latest", request.url.path)
        if not m or self.latest_tag is None:
            return httpx.Response(404, json={"message": "Not Found"})
        if self.status != 200:
            return httpx.Response(self.status, json={"message": "Fehler"})
        owner, repo = m.groups()
        return httpx.Response(
            200,
            json={
                "tag_name": self.latest_tag,
                "html_url": f"https://github.com/{owner}/{repo}/releases/tag/{self.latest_tag}",
            },
        )


def router(spotify: FakeSpotify, github: FakeGitHub) -> httpx.MockTransport:
    """Ein Transport für alle HTTP-Clients: verteilt nach Host auf die Fakes."""

    def handle(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "api.spotify.com":
            return spotify.handle(request)
        if host == "api.github.com":
            return github.handle(request)
        raise AssertionError(f"Unerwartete Anfrage im Test: {request.method} {request.url}")

    return httpx.MockTransport(handle)


def write_token(path: Path) -> None:
    """Gültiger Login mit allen Scopes, läuft während des Tests nicht ab (kein Refresh nötig)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "access_token": "test-token",
                "refresh_token": "test-refresh",
                "scope": " ".join(SCOPES),
                "expires_at": time.time() + 24 * 3600,
            }
        ),
        encoding="utf-8",
    )


class RecordingEvents:
    """Ersatz für die pywebview-Events: merkt sich alle gemeldeten Events der Reihe nach."""

    def __init__(self):
        self.emitted: list[tuple[str, object]] = []

    def emit(self, name: str, data=None) -> None:
        self.emitted.append((name, data))

    def named(self, name: str) -> list:
        return [data for n, data in self.emitted if n == name]
