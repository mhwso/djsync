"""Gemeinsames Test-Gerüst für die GUI-API-Schicht und die CLI.

Fixtures:
  paths      – temporärer Konfigurations- und Datenordner, Client-ID und gültiger Login
  spotify    – FakeSpotify (HTTP-Ebene, leerer Katalog), siehe tests/fake_spotify.py
  github     – FakeGitHub (HTTP-Ebene), siehe tests/fakes.py
  events     – RecordingEvents, fängt Fortschritts-Events der API-Schicht ab
  windows    – RecordingWindows, fängt zusätzlich geöffnete Fenster ab (Login im Player)
  ctx        – AppContext mit echter SQLite-Datei im temporären Datenordner
  api        – das API-Objekt, wie es pywebview der Oberfläche bereitstellt
  music      – legt Musikordner mit kleinen Testdateien an
  run_cli    – führt `djsync …` gegen dieselben Pfade und Fakes aus
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from djsync import cli, config
from djsync.gui.api import Api
from djsync.gui.context import AppContext
from djsync.spotify import SpotifyClient
from fake_spotify import FakeSpotify
from fakes import FakeGitHub, RecordingEvents, RecordingWindows, router, write_token

CLIENT_ID = "c" * 32


@dataclass
class Paths:
    config_dir: Path
    data_dir: Path

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def db_file(self) -> Path:
        return self.data_dir / "djsync.db"

    @property
    def token_file(self) -> Path:
        return self.data_dir / "token.json"


@pytest.fixture
def paths(tmp_path, monkeypatch) -> Paths:
    p = Paths(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    # Nichts aus der echten Umgebung des Entwicklers lesen
    monkeypatch.setattr(config, "CONFIG_FILE", p.config_file)
    monkeypatch.setattr(config, "PROJECT_ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    config.save_client_id(CLIENT_ID, p.config_file)
    write_token(p.token_file)
    return p


@pytest.fixture
def spotify() -> FakeSpotify:
    return FakeSpotify()


@pytest.fixture
def github() -> FakeGitHub:
    return FakeGitHub()


@pytest.fixture
def events() -> RecordingEvents:
    return RecordingEvents()


@pytest.fixture
def windows() -> RecordingWindows:
    return RecordingWindows()


@pytest.fixture
def ctx(paths, spotify, github, events, windows) -> AppContext:
    return AppContext(
        config_file=paths.config_file,
        data_dir=paths.data_dir,
        transport=router(spotify, github),
        events=events,
        windows=windows,
    )


@pytest.fixture
def api(ctx) -> Api:
    return Api(ctx)


class Music:
    """Legt echte Verzeichnisse mit kleinen Dateien an. Inhalt ist kein echtes Audio:
    Artist und Titel kommen dann aus dem Dateinamen („Artist - Titel.mp3“)."""

    def __init__(self, root: Path):
        self.root = root

    def folder(self, name: str, *files: str) -> str:
        folder = self.root / name
        folder.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(files):
            path = folder / f
            path.write_bytes(b"\0" * 16)
            # feste, verschiedene mtimes → stabile Reihenfolge in der Playlist
            mtime = 1_700_000_000 + i
            os.utime(path, (mtime, mtime))
        return str(folder)


@pytest.fixture
def music(tmp_path) -> Music:
    return Music(tmp_path / "music")


@pytest.fixture
def run_cli(paths, spotify, github, monkeypatch):
    """`run_cli("sync", ordner, "--yes")` → Exit-Code; nutzt dieselbe DB und dieselben Fakes."""
    transport = router(spotify, github)
    monkeypatch.setattr(cli, "DB_FILE", paths.db_file)
    monkeypatch.setattr(cli, "TOKEN_FILE", paths.token_file)
    monkeypatch.setattr(cli, "SpotifyClient", lambda auth: SpotifyClient(auth, transport=transport))

    def run(*argv: str) -> int:
        return cli.main(list(argv))

    return run
