"""Spotify-Fake auf HTTP-Ebene: ein httpx.MockTransport hinter dem echten SpotifyClient."""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from djsync.auth import Auth
from djsync.config import SCOPES
from djsync.spotify import SpotifyClient


def track(track_id: str, artist: str, name: str, *, isrc: str | None = None, duration_ms: int | None = None) -> dict:
    """Ein Track im Format der Spotify-API."""
    return {
        "id": track_id,
        "type": "track",
        "name": name,
        "artists": [{"name": artist}],
        "duration_ms": duration_ms,
        "external_ids": {"isrc": isrc} if isrc else {},
        "album": {"name": "Album"},
    }


class FakeSpotify:
    """Hält Katalog und Playlists im Speicher und protokolliert jede Anfrage."""

    def __init__(self, catalog: list[dict] | None = None):
        self.catalog = list(catalog or [])
        self.playlists: dict[str, dict] = {}  # id → {"name", "description", "items": [track_id]}
        self.requests: list[httpx.Request] = []
        self._next_id = 1
        self.on_request = None  # optionaler Haken, z. B. um während der Suche abzubrechen
        self.unavailable: set[str] = set()  # Track-IDs, deren Einzelabruf mit 404 scheitert
        # Anmeldung: POST accounts.spotify.com/api/token
        self.token_requests: list[dict[str, list[str]]] = []  # Formulardaten je Anfrage
        self.token_status = 200  # z. B. 400 für einen abgelehnten Code

    # ---- Testhilfen -------------------------------------------------------

    def add_playlist(self, name: str, items: list[str]) -> str:
        pid = f"pl{self._next_id}"
        self._next_id += 1
        self.playlists[pid] = {"name": name, "description": "", "items": list(items)}
        return pid

    def writes(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method != "GET"]

    def searches(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == "/v1/search"]

    def client(self, tmp_path: Path) -> SpotifyClient:
        token = tmp_path / "token.json"
        token.write_text(
            json.dumps(
                {
                    "access_token": "t",
                    "refresh_token": "r",
                    "scope": " ".join(SCOPES),
                    "expires_at": time.time() + 3600,
                }
            ),
            encoding="utf-8",
        )
        auth = Auth("client", "http://127.0.0.1:8888/callback", SCOPES, token)
        return SpotifyClient(auth, transport=httpx.MockTransport(self.handle))

    # ---- HTTP -------------------------------------------------------------

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.on_request:
            # Der Haken darf eine eigene Antwort liefern, z. B. einen Fehler wie 429
            response = self.on_request(request)
            if response is not None:
                return response
        if request.url.host == "accounts.spotify.com":
            return self._token(request)
        path = request.url.path.removeprefix("/v1")
        parts = path.strip("/").split("/")
        body = json.loads(request.content) if request.content else None

        if path == "/search":
            return httpx.Response(200, json={"tracks": {"items": self._search(request.url.params["q"])}})
        if path == "/me/playlists" and request.method == "POST":
            pid = self.add_playlist(body["name"], [])
            self.playlists[pid]["description"] = body.get("description", "")
            return httpx.Response(201, json={"id": pid})
        if parts[0] == "playlists":
            pl = self.playlists.get(parts[1])
            if pl is None:
                return httpx.Response(404, json={"error": {"status": 404, "message": "Not found"}})
            if len(parts) == 2 and request.method == "GET":
                return httpx.Response(200, json={"id": parts[1], "name": pl["name"], "description": pl["description"]})
            if len(parts) == 2 and request.method == "PUT":
                pl.update({k: v for k, v in body.items() if k in ("name", "description")})
                return httpx.Response(200)
            if len(parts) == 3 and parts[2] == "followers" and request.method == "DELETE":
                del self.playlists[parts[1]]  # eigene Playlist entfolgen = löschen
                return httpx.Response(200)
            if len(parts) == 3 and request.method == "GET":
                items = [{"item": self._by_id(t)} for t in pl["items"]]
                return httpx.Response(200, json={"items": items, "next": None})
            if len(parts) == 3 and request.method == "PUT":
                pl["items"] = [u.removeprefix("spotify:track:") for u in body["uris"]]
                return httpx.Response(200, json={"snapshot_id": "s"})
            if len(parts) == 3 and request.method == "POST":
                pl["items"] += [u.removeprefix("spotify:track:") for u in body["uris"]]
                return httpx.Response(201, json={"snapshot_id": "s"})
        if parts[0] == "tracks":
            # Einzelabruf (z. B. Link im Review); unbekannte IDs liefern einen Platzhalter-Track,
            # IDs in `unavailable` einen 404
            if parts[1] in self.unavailable:
                return httpx.Response(404, json={"error": {"status": 404, "message": "Non existing id"}})
            return httpx.Response(200, json=self._by_id(parts[1]))
        return httpx.Response(404, json={"error": {"status": 404, "message": f"unbekannt: {path}"}})

    def _token(self, request: httpx.Request) -> httpx.Response:
        """Token-Endpunkt (Anmeldung und Erneuerung): gibt ein Token mit allen Scopes aus."""
        form = parse_qs(request.content.decode())
        self.token_requests.append(form)
        if request.url.path != "/api/token" or self.token_status != 200:
            return httpx.Response(self.token_status if self.token_status != 200 else 404,
                                  json={"error": "invalid_grant"})
        return httpx.Response(200, json={
            "access_token": f"access-{len(self.token_requests)}",
            "refresh_token": "refresh",
            "expires_in": 3600,
            "scope": " ".join(SCOPES),
        })

    def _by_id(self, track_id: str) -> dict:
        for t in self.catalog:
            if t["id"] == track_id:
                return t
        return track(track_id, "Unbekannt", track_id)

    def _search(self, query: str) -> list[dict]:
        q = query.lower()
        if q.startswith("isrc:"):
            return [t for t in self.catalog if (t["external_ids"].get("isrc") or "").lower() == q[5:]]
        # grob wie Spotify: Track gilt als gefunden, wenn sein Titel in der Anfrage vorkommt
        return [t for t in self.catalog if t["name"].lower() in q]
