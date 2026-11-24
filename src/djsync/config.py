from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default) / "djsync"


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config")
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share")

CONFIG_FILE = CONFIG_DIR / "config.toml"
# Projektordner (bei `uv run` bzw. `uv tool install --editable .`): src/djsync/config.py → ../../
PROJECT_DIR = Path(__file__).resolve().parents[2]
PROJECT_ENV_FILE = PROJECT_DIR / ".env"
DB_FILE = DATA_DIR / "djsync.db"
TOKEN_FILE = DATA_DIR / "token.json"

DEFAULT_EXTENSIONS = (".mp3", ".flac", ".m4a", ".wav", ".aiff", ".aif")
SCOPES = (
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-private",
    "playlist-modify-public",
    # Nötig für market=from_token bei /search (sonst 403 "Insufficient client scope")
    "user-read-private",
)


class ConfigError(Exception):
    pass


@dataclass
class Config:
    client_id: str
    redirect_uri: str = "http://127.0.0.1:8888/callback"
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS
    duration_tolerance_s: float = 3.0
    min_score: float = 0.7
    retry_missing_days: int = 14
    review_candidates: int = 5
    extra: dict = field(default_factory=dict)

    @property
    def duration_tolerance_ms(self) -> int:
        return int(self.duration_tolerance_s * 1000)


def _read_env_file(path: Path) -> dict[str, str]:
    """Minimaler .env-Parser: KEY=VALUE. Ändert os.environ nicht."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        values[key] = value.strip().strip('"').strip("'")
    return values


def load_config() -> Config:
    env = _read_env_file(PROJECT_ENV_FILE)
    data: dict = {}
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open("rb") as fh:
            data = tomllib.load(fh)

    # Die Client-ID kommt ausschließlich aus der Projekt-.env.
    client_id = env.get("SPOTIFY_CLIENT_ID")
    if not client_id:
        raise ConfigError(
            f"Keine Spotify Client-ID gefunden. Lege {PROJECT_ENV_FILE} an mit:\n"
            "  SPOTIFY_CLIENT_ID=<deine Client-ID>"
        )

    cfg = Config(client_id=client_id)
    cfg.redirect_uri = (
        env.get("SPOTIFY_REDIRECT_URI") or data.pop("redirect_uri", None) or cfg.redirect_uri
    )
    data.pop("redirect_uri", None)
    if "extensions" in data:
        cfg.extensions = tuple(
            e.lower() if e.startswith(".") else "." + e.lower() for e in data.pop("extensions")
        )
    for key in ("duration_tolerance_s", "min_score", "retry_missing_days", "review_candidates"):
        if key in data:
            setattr(cfg, key, type(getattr(cfg, key))(data.pop(key)))
    cfg.extra = data
    return cfg
