"""Alles, was die API-Schicht von außen braucht: Pfade, HTTP-Transport, Events, Fenster.

In der App kommt alles aus `AppContext.default()`. Tests bauen den Kontext mit temporären
Ordnern, einem httpx.MockTransport (Spotify/GitHub-Fakes), aufzeichnenden Events und Fenstern.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .. import config
from ..auth import Auth
from ..config import SCOPES, Config
from ..db import Database
from ..spotify import SpotifyClient
from .events import Events, NullEvents
from .media import MediaServer
from .windows import NullWindows, Windows


@dataclass
class AppContext:
    config_file: Path
    data_dir: Path
    transport: httpx.BaseTransport | None = None  # None = echtes Netzwerk
    events: Events = field(default_factory=NullEvents)
    media: MediaServer = field(default_factory=MediaServer)  # startet erst beim ersten Anhören
    windows: Windows = field(default_factory=NullWindows)

    @classmethod
    def default(cls, events: Events | None = None, windows: Windows | None = None) -> AppContext:
        return cls(
            config_file=config.CONFIG_FILE,
            data_dir=config.DATA_DIR,
            events=events or NullEvents(),
            windows=windows or NullWindows(),
        )

    @property
    def db_file(self) -> Path:
        return self.data_dir / "djsync.db"

    @property
    def token_file(self) -> Path:
        return self.data_dir / "token.json"

    @property
    def webview_dir(self) -> Path:
        """WebView2-Profil (Cookies): hält die Anmeldung im eingebetteten Spotify-Player."""
        return self.data_dir / "webview"

    @property
    def player_login_file(self) -> Path:
        """Vorhanden, wenn der eingebettete Player zuletzt ganze Tracks gespielt hat."""
        return self.data_dir / "player-login"

    @property
    def cache_dir(self) -> Path:
        """Zwischenspeicher (z. B. aus AIFF umgewandelte WAV-Dateien); darf jederzeit gelöscht werden."""
        return self.data_dir / "cache"

    @contextmanager
    def db(self) -> Iterator[Database]:
        """Eigene Verbindung pro Aufruf: pywebview ruft jede API-Methode in einem neuen Thread auf,
        und SQLite-Verbindungen dürfen nicht zwischen Threads wandern."""
        db = Database(self.db_file)
        try:
            yield db
        finally:
            db.close()

    def load_config(self) -> Config:
        return config.load_config(self.config_file)

    def spotify(self, cfg: Config | None = None) -> SpotifyClient:
        cfg = cfg or self.load_config()
        auth = Auth(cfg.client_id, cfg.redirect_uri, SCOPES, self.token_file, transport=self.transport)
        return SpotifyClient(auth, transport=self.transport)

    def http(self) -> httpx.Client:
        """HTTP-Client für sonstige Abfragen (z. B. GitHub-Releases)."""
        return httpx.Client(timeout=10, transport=self.transport, follow_redirects=True)
