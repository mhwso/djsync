"""OAuth 2.0 Authorization Code mit PKCE – kein Client-Secret nötig.

Die Anmeldung besteht aus drei Schritten, die CLI (`Auth.login`) und GUI gemeinsam nutzen:
`begin_login()` erzeugt die Adresse für den Browser, ein `CallbackServer` auf der Redirect-URI
wartet auf die Weiterleitung, `finish_login()` tauscht den Code gegen ein Token.
"""

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
from collections.abc import Callable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class LoginRequest:
    """Eine begonnene Anmeldung: Adresse für den Browser und die Geheimnisse für den Abschluss."""

    url: str
    state: str
    verifier: str


class Auth:
    def __init__(
        self,
        client_id: str,
        redirect_uri: str,
        scopes,
        token_path: Path,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.scope = " ".join(scopes)
        self.token_path = token_path
        self._transport = transport  # None = echtes Netzwerk; Tests setzen einen Fake
        self._token: dict | None = None

    # ---- Token-Verwaltung -----------------------------------------------

    def is_logged_in(self) -> bool:
        """Ob eine Anmeldung mit allen nötigen Berechtigungen vorliegt (ohne Netzwerk).

        Ein abgelaufenes Zugriffs-Token zählt als angemeldet, es wird bei Bedarf erneuert."""
        try:
            self._checked_token()
        except AuthError:
            return False
        return True

    def access_token(self) -> str:
        token = self._checked_token()
        if token.get("expires_at", 0) - 60 < time.time():
            token = self.refresh()
        return token["access_token"]

    def _checked_token(self) -> dict:
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
        return token

    def refresh(self) -> dict:
        token = self._load()
        if not token or not token.get("refresh_token"):
            raise AuthError("Kein Refresh-Token vorhanden. Bitte `djsync login` ausführen.")
        r = self._post_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
                "client_id": self.client_id,
            }
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

    def _post_token(self, data: dict) -> httpx.Response:
        with httpx.Client(transport=self._transport, timeout=30) as http:
            return http.post(TOKEN_URL, data=data)

    def _load(self) -> dict | None:
        if self._token is None and self.token_path.exists():
            self._token = json.loads(self.token_path.read_text(encoding="utf-8"))
        return self._token

    def _store(self, token: dict) -> dict:
        token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        # Erst in eine Nachbardatei schreiben, dann ersetzen: Wer gleichzeitig liest (z. B. der
        # Einrichtungsstatus der GUI), sieht nie eine halb geschriebene Datei.
        tmp = self.token_path.with_name(self.token_path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(token, fh)
        os.replace(tmp, self.token_path)
        self._token = token
        return token

    # ---- Login ------------------------------------------------------------

    def begin_login(self) -> LoginRequest:
        """Erzeugt die Adresse der Spotify-Anmeldung (PKCE) für den Browser."""
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
        return LoginRequest(url=url, state=state, verifier=verifier)

    def finish_login(self, request: LoginRequest, callback: str) -> None:
        """Wertet die Weiterleitung von Spotify aus und speichert das Token. Fehler → AuthError."""
        params = parse_qs(urlparse(callback).query)
        if params.get("state", [None])[0] != request.state:
            raise AuthError("Ungültiger state-Parameter – Login abgebrochen.")
        if "error" in params:
            raise AuthError(f"Spotify hat den Zugriff abgelehnt: {params['error'][0]}")
        code = params.get("code", [None])[0]
        if not code:
            raise AuthError("Kein Autorisierungscode erhalten.")

        r = self._post_token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "code_verifier": request.verifier,
            }
        )
        if r.status_code != 200:
            raise AuthError(f"Token-Abruf fehlgeschlagen ({r.status_code}): {r.text[:300]}")
        self._store(r.json())

    def login(self) -> None:
        """Anmeldung im Terminal (`djsync login`)."""
        request = self.begin_login()
        from . import ui

        ui.info("Im Browser öffnet sich die Spotify-Anmeldung – bitte den Zugriff bestätigen.")
        ui.info("[muted]Falls sich nichts öffnet, diese Adresse im Browser aufrufen:[/]")
        ui.console.print(request.url, style="muted", soft_wrap=True)  # nicht umbrechen, damit kopierbar

        callback = None
        try:
            server = CallbackServer(self.redirect_uri)
        except AuthError as e:
            print(e)
            server = None
        open_browser(request.url)
        if server is not None:
            with ui.spinner(f"Warte auf die Bestätigung im Browser (bis zu {LOGIN_TIMEOUT_S // 60} Minuten) …"):
                try:
                    callback = server.wait()
                finally:
                    server.close()
        if callback is None:
            try:
                callback = input(
                    "Keine Rückmeldung erhalten. Füge die URL ein, auf die der Browser weitergeleitet hat:\n> "
                ).strip()
            except EOFError:
                raise AuthError(
                    "Login nicht abgeschlossen. Bitte `djsync login` in einem eigenen Terminal ausführen."
                ) from None
        self.finish_login(request, callback)


class CallbackServer:
    """Lokaler Server auf der Redirect-URI, der auf die Weiterleitung von Spotify wartet.

    Der Port wird schon beim Erzeugen belegt (AuthError, wenn das nicht geht), damit die
    Weiterleitung nicht ins Leere läuft."""

    def __init__(self, redirect_uri: str):
        parsed = urlparse(redirect_uri)
        host, port = parsed.hostname or "127.0.0.1", parsed.port or 80
        received: dict[str, str] = {}
        self._received = received

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
            self._server = HTTPServer((host, port), Handler)
        except OSError as e:
            raise AuthError(
                f"Konnte {host}:{port} nicht öffnen ({e}). Läuft djsync noch in einem anderen Fenster?"
            ) from None
        self._server.timeout = 0.2

    def wait(self, timeout: float = LOGIN_TIMEOUT_S, cancel: Callable[[], bool] | None = None) -> str | None:
        """Adresse der Weiterleitung oder None bei Zeitüberschreitung bzw. Abbruch."""
        deadline = time.time() + timeout
        while "url" not in self._received and time.time() < deadline:
            if cancel is not None and cancel():
                return None
            self._server.handle_request()
        return self._received.get("url")

    def close(self) -> None:
        self._server.server_close()
