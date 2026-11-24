"""OAuth 2.0 Authorization Code mit PKCE – kein Client-Secret nötig."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .filenames import is_wsl

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
LOGIN_TIMEOUT_S = 180


class AuthError(Exception):
    pass


def open_browser(url: str) -> None:
    """Öffnet den Browser – unter WSL den Windows-Standardbrowser."""
    try:
        if is_wsl() and shutil.which("explorer.exe"):
            subprocess.Popen(
                ["explorer.exe", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        else:
            webbrowser.open(url)
    except Exception:
        pass  # URL steht ohnehin in der Ausgabe


class Auth:
    def __init__(self, client_id: str, redirect_uri: str, scopes, token_path: Path):
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.scope = " ".join(scopes)
        self.token_path = token_path
        self._token: dict | None = None

    # ---- Token-Verwaltung -----------------------------------------------

    def access_token(self) -> str:
        token = self._load()
        if token is None:
            raise AuthError("Nicht angemeldet. Bitte zuerst `djsync login` ausführen.")
        granted = set((token.get("scope") or "").split())
        missing = set(self.scope.split()) - granted
        if missing:
            raise AuthError(
                "djsync benötigt zusätzliche Spotify-Berechtigungen "
                f"({', '.join(sorted(missing))}). Bitte `djsync login` erneut ausführen."
            )
        if token.get("expires_at", 0) - 60 < time.time():
            token = self.refresh()
        return token["access_token"]

    def refresh(self) -> dict:
        token = self._load()
        if not token or not token.get("refresh_token"):
            raise AuthError("Kein Refresh-Token vorhanden. Bitte `djsync login` ausführen.")
        r = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
                "client_id": self.client_id,
            },
            timeout=30,
        )
        if r.status_code != 200:
            raise AuthError(
                f"Token-Erneuerung fehlgeschlagen ({r.status_code}). Bitte `djsync login` ausführen."
            )
        new = r.json()
        new.setdefault("refresh_token", token["refresh_token"])
        if "scope" in token:
            new.setdefault("scope", token["scope"])
        return self._store(new)

    def _load(self) -> dict | None:
        if self._token is None and self.token_path.exists():
            self._token = json.loads(self.token_path.read_text(encoding="utf-8"))
        return self._token

    def _store(self, token: dict) -> dict:
        token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(token, fh)
        self._token = token
        return token

    # ---- Login ------------------------------------------------------------

    def login(self) -> None:
        verifier = secrets.token_urlsafe(64)[:128]
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        )
        state = secrets.token_urlsafe(16)
        url = AUTHORIZE_URL + "?" + urlencode(
            {
                "client_id": self.client_id,
                "response_type": "code",
                "redirect_uri": self.redirect_uri,
                "scope": self.scope,
                "code_challenge_method": "S256",
                "code_challenge": challenge,
                "state": state,
            }
        )
        print("Öffne diese URL im Browser und bestätige den Zugriff:\n")
        print(f"  {url}\n")
        open_browser(url)
        print(f"Warte bis zu {LOGIN_TIMEOUT_S // 60} Minuten auf die Bestätigung …")

        callback = self._wait_for_callback()
        if callback is None:
            try:
                callback = input(
                    "Keine Rückmeldung erhalten. Füge die URL ein, auf die der Browser weitergeleitet hat:\n> "
                ).strip()
            except EOFError:
                raise AuthError(
                    "Login nicht abgeschlossen. Bitte `djsync login` in einem eigenen Terminal ausführen."
                ) from None

        params = parse_qs(urlparse(callback).query)
        if params.get("state", [None])[0] != state:
            raise AuthError("Ungültiger state-Parameter – Login abgebrochen.")
        if "error" in params:
            raise AuthError(f"Spotify hat den Zugriff abgelehnt: {params['error'][0]}")
        code = params.get("code", [None])[0]
        if not code:
            raise AuthError("Kein Autorisierungscode erhalten.")

        r = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "code_verifier": verifier,
            },
            timeout=30,
        )
        if r.status_code != 200:
            raise AuthError(f"Token-Abruf fehlgeschlagen ({r.status_code}): {r.text[:300]}")
        self._store(r.json())

    def _wait_for_callback(self) -> str | None:
        """Startet einen lokalen Server auf der Redirect-URI und wartet auf den Callback."""
        parsed = urlparse(self.redirect_uri)
        host, port = parsed.hostname or "127.0.0.1", parsed.port or 80
        received: dict[str, str] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if urlparse(self.path).path != parsed.path:
                    self.send_response(404)
                    self.end_headers()
                    return
                received["url"] = self.path
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    "<h2>djsync: Anmeldung abgeschlossen.</h2><p>Du kannst dieses Fenster schließen.</p>".encode()
                )

            def log_message(self, *args):
                pass

        try:
            server = HTTPServer((host, port), Handler)
        except OSError as e:
            print(f"Konnte {host}:{port} nicht öffnen ({e}).")
            return None
        server.timeout = 1
        deadline = time.time() + LOGIN_TIMEOUT_S
        try:
            while "url" not in received and time.time() < deadline:
                server.handle_request()
        finally:
            server.server_close()
        return received.get("url")
