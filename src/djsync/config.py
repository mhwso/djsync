from __future__ import annotations

import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


IS_WINDOWS = sys.platform == "win32"


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default) / "djsync"


if IS_WINDOWS:
    # %APPDATA%\djsync – Konfiguration, Datenbank und Login-Token an einem Ort
    CONFIG_DIR = DATA_DIR = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "djsync"
else:
    CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config")
    DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share")

CONFIG_FILE = CONFIG_DIR / "config.toml"
# Projektordner (bei `uv run` bzw. `uv tool install --editable .`): src/djsync/config.py → ../../
# In der gebauten .exe gibt es ihn nicht – dann zählt nur config.toml.
PROJECT_DIR = Path(__file__).resolve().parents[2]
PROJECT_ENV_FILE = PROJECT_DIR / ".env"
_CLIENT_ID_RE = re.compile(r"^[0-9a-f]{32}$")
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


# In der GUI änderbare Einstellungen (Schlüssel in config.toml = Attribut von Config)
SETTINGS = (
    "extensions",
    "duration_tolerance_s",
    "min_score",
    "retry_missing_days",
    "review_candidates",
    "start_position_s",
    "skip_s",
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
    # Anhören im Review: Startstelle und Sprungweite in Sekunden
    start_position_s: int = 60
    skip_s: int = 30
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


def load_config(config_file: Path | None = None) -> Config:
    """Liest die Konfiguration; ohne `config_file` aus dem Standardort (CONFIG_FILE)."""
    config_file = config_file or CONFIG_FILE
    env = _read_env_file(PROJECT_ENV_FILE)
    data: dict = {}
    if config_file.exists():
        with config_file.open("rb") as fh:
            data = tomllib.load(fh)

    # Reihenfolge: Umgebungsvariable, Projekt-.env (Entwicklung), config.toml (`djsync setup`)
    client_id = (
        os.environ.get("SPOTIFY_CLIENT_ID")
        or env.get("SPOTIFY_CLIENT_ID")
        or str(data.pop("client_id", "") or "")
    ).strip()
    data.pop("client_id", None)
    if not client_id:
        raise ConfigError("Keine Spotify Client-ID eingerichtet. Bitte zuerst `djsync setup` ausführen.")

    cfg = Config(client_id=client_id)
    cfg.redirect_uri = (
        env.get("SPOTIFY_REDIRECT_URI") or data.pop("redirect_uri", None) or cfg.redirect_uri
    )
    data.pop("redirect_uri", None)
    if "extensions" in data:
        cfg.extensions = tuple(
            e.lower() if e.startswith(".") else "." + e.lower() for e in data.pop("extensions")
        )
    for key in SETTINGS[1:]:
        if key in data:
            setattr(cfg, key, type(getattr(cfg, key))(data.pop(key)))
    cfg.extra = data
    return cfg


def has_client_id() -> bool:
    try:
        load_config()
    except ConfigError:
        return False
    return True


def is_valid_client_id(value: str) -> bool:
    return bool(_CLIENT_ID_RE.match(value.strip().lower()))


def save_client_id(client_id: str, path: Path = CONFIG_FILE) -> None:
    """Schreibt bzw. ersetzt `client_id = "…"` in config.toml, Rest der Datei bleibt erhalten."""
    line = f'client_id = "{client_id.strip()}"'
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if re.search(r"(?m)^\s*client_id\s*=.*$", text):
        text = re.sub(r"(?m)^\s*client_id\s*=.*$", line, text, count=1)
    else:
        text = line + "\n" + text
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---- Einstellungen prüfen und speichern (GUI) ---------------------------------

SETTING_LABELS = {
    "extensions": "Dateiendungen",
    "duration_tolerance_s": "Toleranz der Dauer",
    "min_score": "Mindestbewertung",
    "retry_missing_days": "Tage bis zur erneuten Suche",
    "review_candidates": "Anzahl der Vorschläge",
    "start_position_s": "Startstelle",
    "skip_s": "Sprungweite",
}

_EXTENSION_RE = re.compile(r"^\.[a-z0-9]{1,10}$")


class SettingsError(ConfigError):
    """Ungültige Einstellungen; `errors` ordnet jedem fehlerhaften Schlüssel eine Meldung zu."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("\n".join(f"{SETTING_LABELS[k]}: {m}" for k, m in errors.items()))


def _number(value, *, integer: bool, low: float, high: float | None, low_inclusive: bool = True):
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
    number = float(value)
    if integer:
        if number != int(number):
            raise ValueError
        number = int(number)
    if number < low or (number == low and not low_inclusive) or (high is not None and number > high):
        raise ValueError
    return number


# Schlüssel → (ganzzahlig, Untergrenze, Obergrenze, Untergrenze erlaubt, Meldung)
_NUMBER_RULES = {
    "duration_tolerance_s": (False, 0, 60, True, "Zahl zwischen 0 und 60 Sekunden"),
    "min_score": (False, 0, 1, True, "Zahl zwischen 0 und 1"),
    "retry_missing_days": (True, 0, 3650, True, "ganze Zahl zwischen 0 und 3650 Tagen"),
    "review_candidates": (True, 1, 20, True, "ganze Zahl zwischen 1 und 20"),
    "start_position_s": (True, 0, 3600, True, "ganze Zahl zwischen 0 und 3600 Sekunden"),
    "skip_s": (True, 1, 600, True, "ganze Zahl zwischen 1 und 600 Sekunden"),
}


def validate_settings(values: dict) -> dict:
    """Prüft und normalisiert alle Einstellungen aus SETTINGS. Wirft `SettingsError`."""
    errors: dict[str, str] = {}
    result: dict = {}
    for key in SETTINGS:
        if key not in values:
            errors[key] = "fehlt"
            continue
        value = values[key]
        if key == "extensions":
            items = value.replace(",", " ").split() if isinstance(value, str) else value
            exts = []
            try:
                for item in items:
                    e = str(item).strip().lower()
                    e = e if e.startswith(".") else "." + e
                    if not _EXTENSION_RE.match(e):
                        raise ValueError
                    if e not in exts:
                        exts.append(e)
            except (TypeError, ValueError):
                errors[key] = "nur Buchstaben und Ziffern, z. B. .mp3"
                continue
            if not exts:
                errors[key] = "mindestens eine Endung angeben"
                continue
            result[key] = exts
            continue
        integer, low, high, inclusive, message = _NUMBER_RULES[key]
        try:
            result[key] = _number(value, integer=integer, low=low, high=high, low_inclusive=inclusive)
        except (TypeError, ValueError, OverflowError):
            errors[key] = message
    if errors:
        raise SettingsError(errors)
    for key, (integer, *_rest) in _NUMBER_RULES.items():
        if not integer:
            result[key] = float(result[key])
    return result


def _toml_value(value) -> str:
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return repr(value)


def save_settings(values: dict, path: Path = CONFIG_FILE) -> dict:
    """Prüft die Einstellungen und schreibt sie in config.toml.

    Nur die Schlüssel der Einstellungen werden ersetzt bzw. vor der ersten Tabelle ergänzt;
    Client-ID, Kommentare und sonstige Einträge bleiben erhalten. Gibt die gespeicherten
    (normalisierten) Werte zurück, wirft `SettingsError` und schreibt dann nichts.
    """
    settings = validate_settings(values)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    # Nur der Kopf vor der ersten [Tabelle] enthält die Schlüssel der obersten Ebene
    table = re.search(r"(?m)^\s*\[", text)
    head, tail = (text[: table.start()], text[table.start():]) if table else (text, "")
    for key in SETTINGS:
        line = f"{key} = {_toml_value(settings[key])}"
        # Wert bis Zeilenende; Listen dürfen sich über mehrere Zeilen erstrecken
        pattern = re.compile(rf"(?ms)^[ \t]*{key}[ \t]*=[ \t]*(\[.*?\]|[^\n]*)[^\n]*$")
        if pattern.search(head):
            head = pattern.sub(lambda _m: line, head, count=1)
        else:
            head = head + ("" if not head or head.endswith("\n") else "\n") + line + "\n"
    if tail and not head.endswith("\n\n"):
        head += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(head + tail, encoding="utf-8")
    return settings
