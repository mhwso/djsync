"""Fakes für die Außengrenzen: Spotify und GitHub auf HTTP-Ebene (httpx.MockTransport).

Die Fakes halten einen kleinen, veränderbaren Zustand (Tracks, Playlists, Releases) und
protokollieren jede Anfrage in `requests`. Tests prüfen bevorzugt den Zustand bzw. die
Rückgabewerte der API-Schicht, `requests` ist für Fälle wie „es wurde nichts geschrieben“.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx

from djsync.config import SCOPES


class FakeSpotify:
    """Minimale Spotify Web API: Suche, Tracks, Playlists samt Inhalt, Entfolgen."""

    def __init__(self):
        self.user = {"id": "tester", "display_name": "Test"}
        self.tracks: dict[str, dict] = {}
        self.playlists: dict[str, dict] = {}
        self.requests: list[httpx.Request] = []
        self._errors: list[httpx.Response] = []
        self._next_id = 0

    # ---- Testdaten ----------------------------------------------------------

    def add_track(
        self,
        track_id: str,
        name: str,
        artists: tuple[str, ...] | list[str],
        *,
        duration_ms: int | None = None,
        isrc: str | None = None,
        album: str | None = None,
    ) -> dict:
        """Legt einen Spotify-Track an, den Suche und /tracks/{id} finden."""
        track = {
            "id": track_id,
            "type": "track",
            "name": name,
            "artists": [{"name": a} for a in artists],
            "duration_ms": duration_ms,
            "external_ids": {"isrc": isrc} if isrc else {},
            "album": {"name": album} if album else {},
        }
        self.tracks[track_id] = track
        return track

    def add_playlist(self, name: str, items: list[str] | None = None, playlist_id: str | None = None) -> str:
        """Legt eine bestehende Playlist an (z. B. für eine migrierte Datenbank)."""
        playlist_id = playlist_id or self._new_id("pl")
        self.playlists[playlist_id] = {
            "id": playlist_id,
            "name": name,
            "description": "",
            "items": list(items or []),
            "followed": True,
        }
        return playlist_id

    def queue_error(self, status: int, body: dict | None = None, headers: dict | None = None) -> None:
        """Die nächste Anfrage beantwortet der Fake mit diesem Fehler."""
        self._errors.append(httpx.Response(status, json=body or {"error": {"status": status}}, headers=headers))

    def writes(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method != "GET"]

    # ---- HTTP ---------------------------------------------------------------

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._errors:
            return self._errors.pop(0)
        path = request.url.path.removeprefix("/v1")
        method = request.method
        for pattern, route_method, handler in self._routes():
            m = re.fullmatch(pattern, path)
            if m and route_method == method:
                return handler(request, *m.groups())
        return httpx.Response(404, json={"error": {"status": 404, "message": f"{method} {path}"}})

    def _routes(self):
        return [
            (r"/me", "GET", lambda r: httpx.Response(200, json=self.user)),
            (r"/search", "GET", self._search),
            (r"/tracks/([^/]+)", "GET", self._get_track),
            (r"/me/playlists", "POST", self._create_playlist),
            (r"/playlists/([^/]+)", "GET", self._get_playlist),
            (r"/playlists/([^/]+)", "PUT", self._update_playlist),
            (r"/playlists/([^/]+)/items", "GET", self._get_items),
            (r"/playlists/([^/]+)/items", "PUT", self._replace_items),
            (r"/playlists/([^/]+)/items", "POST", self._add_items),
            (r"/playlists/([^/]+)/followers", "DELETE", self._unfollow),
        ]

    def _search(self, request):
        q = request.url.params.get("q", "")
        limit = int(request.url.params.get("limit", "10"))
        if q.startswith("isrc:"):
            isrc = q[5:].strip().upper()
            hits = [t for t in self.tracks.values() if (t["external_ids"].get("isrc") or "").upper() == isrc]
        else:
            words = re.sub(r'\b(track|artist):', " ", q).replace('"', " ").lower().split()
            hits = [t for t in self.tracks.values() if all(w in _haystack(t) for w in words)]
        return httpx.Response(200, json={"tracks": {"items": hits[:limit]}})

    def _get_track(self, request, track_id):
        track = self.tracks.get(track_id)
        if track is None:
            return httpx.Response(404, json={"error": {"status": 404}})
        return httpx.Response(200, json=track)

    def _create_playlist(self, request):
        body = json.loads(request.content)
        playlist_id = self.add_playlist(body["name"])
        self.playlists[playlist_id]["description"] = body.get("description", "")
        return httpx.Response(201, json={"id": playlist_id, "name": body["name"]})

    def _playlist(self, playlist_id):
        p = self.playlists.get(playlist_id)
        return p if p and p["followed"] else None

    def _get_playlist(self, request, playlist_id):
        p = self._playlist(playlist_id)
        if p is None:
            return httpx.Response(404, json={"error": {"status": 404}})
        return httpx.Response(200, json={k: p[k] for k in ("id", "name", "description")})

    def _update_playlist(self, request, playlist_id):
        p = self._playlist(playlist_id)
        if p is None:
            return httpx.Response(404, json={"error": {"status": 404}})
        body = json.loads(request.content)
        p.update({k: v for k, v in body.items() if k in ("name", "description")})
        return httpx.Response(200)

    def _get_items(self, request, playlist_id):
        p = self._playlist(playlist_id)
        if p is None:
            return httpx.Response(404, json={"error": {"status": 404}})
        items = [{"item": self.tracks.get(t) or {"id": t, "type": "track"}} for t in p["items"]]
        return httpx.Response(200, json={"items": items, "next": None})

    def _replace_items(self, request, playlist_id):
        self.playlists[playlist_id]["items"] = [u.rsplit(":", 1)[-1] for u in json.loads(request.content)["uris"]]
        return httpx.Response(200, json={"snapshot_id": "s"})

    def _add_items(self, request, playlist_id):
        self.playlists[playlist_id]["items"] += [u.rsplit(":", 1)[-1] for u in json.loads(request.content)["uris"]]
        return httpx.Response(201, json={"snapshot_id": "s"})

    def _unfollow(self, request, playlist_id):
        if playlist_id in self.playlists:
            self.playlists[playlist_id]["followed"] = False
        return httpx.Response(200)

    def _new_id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}{self._next_id:020d}"


def _haystack(track: dict) -> str:
    return " ".join([track["name"], *(a["name"] for a in track["artists"])]).lower()


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
