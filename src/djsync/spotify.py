"""Schlanker Client für die Spotify Web API (Stand: Dev-Mode-Änderungen 2026).

Nutzt bewusst die neuen Endpunkte:
  - POST /me/playlists           (statt /users/{id}/playlists)
  - /playlists/{id}/items        (statt /playlists/{id}/tracks)
  - GET /search mit limit ≤ 10
"""

from __future__ import annotations

import time

import httpx

from .auth import Auth
from .models import Candidate

API = "https://api.spotify.com/v1"
SEARCH_LIMIT = 10
WRITE_CHUNK = 100
MAX_RETRY_AFTER_S = 120


class SpotifyError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class SpotifyClient:
    def __init__(self, auth: Auth, *, transport: httpx.BaseTransport | None = None):
        self.auth = auth
        # transport: in Tests z. B. httpx.MockTransport statt echter Netzwerkzugriffe
        self.http = httpx.Client(timeout=30, transport=transport)

    def close(self) -> None:
        self.http.close()

    # ---- Low-Level ------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs):
        url = path if path.startswith("http") else API + path
        refreshed = False
        for attempt in range(6):
            headers = {"Authorization": f"Bearer {self.auth.access_token()}"}
            r = self.http.request(method, url, headers=headers, **kwargs)

            if r.status_code == 401 and not refreshed:
                self.auth.refresh()
                refreshed = True
                continue
            if r.status_code == 429:
                if _error_reason(r) == "QUOTA_EXCEEDED":
                    raise SpotifyError(
                        "Spotify-API-Kontingent für deinen Developer-Account ist aufgebraucht. "
                        "Später erneut versuchen.",
                        429,
                    )
                wait = int(r.headers.get("Retry-After", "2"))
                if wait > MAX_RETRY_AFTER_S:
                    raise SpotifyError(f"Rate-Limit: Spotify verlangt {wait}s Pause. Später erneut versuchen.", 429)
                time.sleep(wait + 0.5)
                continue
            if r.status_code >= 500:
                time.sleep(2**attempt)
                continue
            if r.status_code >= 400:
                raise SpotifyError(f"{method} {url} → {r.status_code}: {r.text[:300]}", r.status_code)
            return r.json() if r.content else None
        raise SpotifyError(f"{method} {url}: zu viele Fehlversuche")

    def _paginate(self, path: str, params: dict | None = None):
        page = self._request("GET", path, params=params)
        while page:
            yield from page.get("items") or []
            nxt = page.get("next")
            page = self._request("GET", nxt) if nxt else None

    # ---- Tracks -----------------------------------------------------------

    def search_tracks(self, query: str, limit: int = SEARCH_LIMIT) -> list[Candidate]:
        data = self._request(
            "GET",
            "/search",
            params={"q": query, "type": "track", "limit": min(limit, SEARCH_LIMIT), "market": "from_token"},
        )
        items = ((data or {}).get("tracks") or {}).get("items") or []
        return [Candidate.from_spotify(t) for t in items if t and t.get("id")]

    def get_track(self, track_id: str) -> Candidate:
        return Candidate.from_spotify(self._request("GET", f"/tracks/{track_id}"))

    # ---- Playlists --------------------------------------------------------

    def create_playlist(self, name: str, description: str, public: bool = False) -> str:
        data = self._request(
            "POST", "/me/playlists", json={"name": name, "description": description, "public": public}
        )
        return data["id"]

    def get_playlist(self, playlist_id: str) -> dict | None:
        try:
            return self._request("GET", f"/playlists/{playlist_id}", params={"fields": "id,name,description"})
        except SpotifyError as e:
            if e.status == 404:
                return None
            raise

    def update_playlist(self, playlist_id: str, *, name: str | None = None, description: str | None = None) -> None:
        body = {k: v for k, v in {"name": name, "description": description}.items() if v is not None}
        if body:
            self._request("PUT", f"/playlists/{playlist_id}", json=body)

    def unfollow_playlist(self, playlist_id: str) -> None:
        """Entfernt die Playlist aus der eigenen Bibliothek – bei Spotify das Löschen einer Playlist."""
        self._request("DELETE", f"/playlists/{playlist_id}/followers")

    def playlist_track_ids(self, playlist_id: str) -> list[str]:
        ids = []
        for entry in self._paginate(f"/playlists/{playlist_id}/items", {"limit": 50}):
            # Feld heißt seit 2026 „item“, früher „track“
            obj = entry.get("item") or entry.get("track")
            if obj and obj.get("type", "track") == "track" and obj.get("id") and not obj.get("is_local"):
                ids.append(obj["id"])
        return ids

    def replace_playlist_items(self, playlist_id: str, track_ids: list[str]) -> None:
        """Setzt den kompletten Inhalt der Playlist in der angegebenen Reihenfolge."""
        uris = [f"spotify:track:{t}" for t in track_ids]
        self._request("PUT", f"/playlists/{playlist_id}/items", json={"uris": uris[:WRITE_CHUNK]})
        for i in range(WRITE_CHUNK, len(uris), WRITE_CHUNK):
            self._request("POST", f"/playlists/{playlist_id}/items", json={"uris": uris[i : i + WRITE_CHUNK]})


def _error_reason(r: httpx.Response) -> str | None:
    try:
        return (r.json().get("error") or {}).get("reason")
    except Exception:
        return None
