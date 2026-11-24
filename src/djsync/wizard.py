"""Geführte Einrichtung und Doppelklick-Modus – für Nutzer ohne Terminal-Erfahrung."""

from __future__ import annotations

import argparse
import sys

from . import __version__, ui
from .auth import AuthError, open_browser
from .config import (
    CONFIG_FILE,
    IS_WINDOWS,
    TOKEN_FILE,
    ConfigError,
    has_client_id,
    is_valid_client_id,
    save_client_id,
)
from .spotify import SpotifyError

DASHBOARD_URL = "https://developer.spotify.com/dashboard"
REDIRECT_URI = "http://127.0.0.1:8888/callback"


class Cancelled(Exception):
    pass


def ask(prompt: str) -> str:
    try:
        return ui.ask(prompt)
    except EOFError:
        ui.info("")
        raise Cancelled from None


def cmd_setup(args) -> None:
    from .cli import cmd_login

    if not sys.stdin.isatty():
        raise ConfigError("Die Einrichtung braucht ein interaktives Terminal.")
    ui.setup_steps(DASHBOARD_URL, REDIRECT_URI)
    ask("Enter drücken, um das Spotify-Dashboard zu öffnen … ")
    open_browser(DASHBOARD_URL)
    ui.info("")
    while True:
        value = ask("Client ID hier einfügen: ").strip()
        if is_valid_client_id(value):
            break
        ui.warn("Das sieht nicht nach einer Client ID aus (32 Zeichen aus 0–9 und a–f). Bitte erneut kopieren.")
    save_client_id(value)
    ui.success(f"Client ID gespeichert [muted]({CONFIG_FILE})[/]")
    ui.info("")
    cmd_login(args)


def run_interactive(folder: str | None) -> int:
    """Doppelklick auf djsync.exe oder Ordner auf die .exe gezogen."""
    from .cli import Abort, cmd_login, cmd_sync

    ui.banner(__version__)
    try:
        if not has_client_id():
            cmd_setup(None)
        elif not TOKEN_FILE.exists():
            cmd_login(None)

        while True:
            if folder is None:
                ui.info("")
                ui.info("Ziehe deinen [bold]Musikordner[/] in dieses Fenster und drücke Enter.")
                folder = ask("[muted](Enter ohne Eingabe beendet)[/] ").strip()
                if not folder:
                    return 0
            try:
                cmd_sync(_sync_args(folder))
            except (Abort, SpotifyError) as e:
                ui.error(str(e))
            folder = None
    except (Cancelled, KeyboardInterrupt):
        ui.info("\n[muted]Abgebrochen.[/]")
        return 130
    except (ConfigError, AuthError, SpotifyError) as e:
        ui.error(str(e))
        return 1
    finally:
        _pause()


def _sync_args(folder: str) -> argparse.Namespace:
    return argparse.Namespace(folder=folder, name=None, yes=False, dry_run=False, no_review=False, retry=False)


def _pause() -> None:
    """Hält das Fenster offen, damit man das Ergebnis lesen kann."""
    if IS_WINDOWS and sys.stdin.isatty():
        try:
            ui.console.input("\n[muted]Enter drücken zum Schließen …[/] ")
        except (EOFError, KeyboardInterrupt):
            pass
