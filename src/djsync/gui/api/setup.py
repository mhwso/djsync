"""Einrichtung: Status, Client-ID speichern, Anmeldung bei Spotify im System-Browser.

Nutzt dieselbe Logik wie `djsync setup`/`djsync login` (wizard.py, auth.py), nur ohne Terminal.

Die Anmeldung läuft wie in der CLI über PKCE mit lokalem Callback: `start_login()` öffnet den
System-Browser und kehrt sofort zurück, ein Hintergrund-Thread wartet auf die Weiterleitung.
Das Ergebnis meldet das Event `setup.login` mit {state, message}; `status()["login"]` liefert
denselben Stand zum Nachfragen. Zustände: idle, waiting, success, error, cancelled.
"""

from __future__ import annotations

import threading

import httpx

from ...auth import Auth, AuthError, CallbackServer, LoginRequest, open_browser
from ...config import SCOPES, ConfigError, is_valid_client_id, save_client_id
from ...wizard import DASHBOARD_URL, INVALID_CLIENT_ID, REDIRECT_URI
from .base import ApiArea, ApiError

LOGIN_EVENT = "setup.login"


class _Login:
    """Eine laufende Anmeldung im Browser."""

    def __init__(self, auth: Auth, request: LoginRequest, server: CallbackServer):
        self.auth = auth
        self.request = request
        self.server = server
        self.cancelled = threading.Event()
        self.thread: threading.Thread | None = None


class SetupApi(ApiArea):
    def __init__(self, ctx):
        super().__init__(ctx)
        self._lock = threading.Lock()
        self._login: _Login | None = None
        self._login_state = {"state": "idle", "message": None}

    def status(self) -> dict:
        """Stand der Einrichtung. Die Oberfläche zeigt die Einrichtung, wenn `needed` wahr ist.

          client_id      ob eine Client-ID eingerichtet ist
          logged_in      ob eine Anmeldung mit allen nötigen Berechtigungen vorliegt
          needed         ob noch etwas fehlt
          redirect_uri   exakt so im Spotify-Dashboard einzutragen
          dashboard_url  Spotify-Developer-Dashboard
          login          Stand der Anmeldung im Browser: {state, message}
        """
        auth = self._auth()
        client_id = auth is not None
        logged_in = client_id and auth.is_logged_in()
        return {
            "client_id": client_id,
            "logged_in": logged_in,
            "needed": not (client_id and logged_in),
            "redirect_uri": auth.redirect_uri if auth else REDIRECT_URI,
            "dashboard_url": DASHBOARD_URL,
            "login": dict(self._login_state),
        }

    def save_client_id(self, value: str) -> dict:
        """Prüft das Format der Client-ID und speichert sie in config.toml. Gibt den neuen Status zurück.

        Eine andere Client-ID als bisher gehört zu einer anderen App im Spotify-Dashboard, die
        bisherige Anmeldung gilt dann nicht mehr und wird verworfen."""
        client_id = (value or "").strip().lower()
        if not is_valid_client_id(client_id):
            raise ApiError(INVALID_CLIENT_ID)
        previous = self._auth()
        save_client_id(client_id, self._ctx.config_file)
        if previous is not None and previous.client_id != client_id:
            self._ctx.token_file.unlink(missing_ok=True)
        return self.status()

    def start_login(self) -> dict:
        """Öffnet die Spotify-Anmeldung im System-Browser und wartet im Hintergrund auf sie.

        Gibt {url} zurück, damit die Oberfläche die Adresse anzeigen kann, falls sich kein
        Browser öffnet. Eine noch wartende Anmeldung wird ersetzt."""
        auth = self._auth()
        if auth is None:
            raise ApiError("Bitte zuerst die Client-ID eingeben.")
        with self._lock:
            self._stop_login()
            request = auth.begin_login()
            try:
                server = CallbackServer(auth.redirect_uri)
            except AuthError as e:
                raise ApiError(str(e)) from None
            login = _Login(auth, request, server)
            login.thread = threading.Thread(target=self._wait_for_login, args=(login,), daemon=True)
            self._login = login
            self._login_state = {"state": "waiting", "message": None}
            login.thread.start()
        open_browser(request.url)
        return {"url": request.url}

    def cancel_login(self) -> None:
        """Bricht eine wartende Anmeldung ab (Event `setup.login` mit state „cancelled“)."""
        login = self._login
        if login is not None:
            login.cancelled.set()

    # ---- intern -------------------------------------------------------------

    def _stop_login(self) -> None:
        """Beendet eine noch wartende Anmeldung, damit der Port der Redirect-URI frei wird."""
        old, self._login = self._login, None
        if old is not None:
            old.cancelled.set()
            if old.thread is not None:
                old.thread.join(timeout=5)

    def _wait_for_login(self, login: _Login) -> None:
        try:
            callback = login.server.wait(cancel=login.cancelled.is_set)
        finally:
            login.server.close()
        if self._login is not login:
            return  # durch eine neue Anmeldung ersetzt – nichts melden
        if login.cancelled.is_set():
            self._finish(login, "cancelled", None)
        elif callback is None:
            self._finish(login, "error", "Keine Rückmeldung aus dem Browser erhalten. Bitte erneut anmelden.")
        else:
            try:
                login.auth.finish_login(login.request, callback)
            except AuthError as e:
                self._finish(login, "error", str(e))
            except httpx.HTTPError:
                self._finish(login, "error", "Spotify ist nicht erreichbar. Besteht eine Internetverbindung?")
            else:
                self._finish(login, "success", None)

    def _finish(self, login: _Login, state: str, message: str | None) -> None:
        with self._lock:
            if self._login is not login:
                return
            self._login = None
            self._login_state = {"state": state, "message": message}
        self._ctx.events.emit(LOGIN_EVENT, {"state": state, "message": message})

    def _auth(self) -> Auth | None:
        """Auth zur eingerichteten Client-ID, None ohne Client-ID."""
        try:
            cfg = self._ctx.load_config()
        except ConfigError:
            return None
        return Auth(cfg.client_id, cfg.redirect_uri, SCOPES, self._ctx.token_file, transport=self._ctx.transport)
