"""Geführte Einrichtung und Doppelklick-Modus – für Nutzer ohne Terminal-Erfahrung."""

from __future__ import annotations

import argparse
import sys

from .auth import AuthError, open_browser
from .config import CONFIG_FILE, IS_WINDOWS, TOKEN_FILE, ConfigError, has_client_id, is_valid_client_id, save_client_id
from .spotify import SpotifyError

DASHBOARD_URL = "https://developer.spotify.com/dashboard"
REDIRECT_URI = "http://127.0.0.1:8888/callback"

SETUP_TEXT = f"""
Einrichtung: eigene Spotify-App anlegen (einmalig, ca. 2 Minuten)

djsync braucht Zugriff auf deine Spotify-Playlists. Dafür legst du im
Spotify-Developer-Dashboard eine kleine „App“ an. Voraussetzung: Spotify Premium.

  1. Im Browser öffnet sich gleich {DASHBOARD_URL}
     Melde dich dort mit deinem Spotify-Konto an.
  2. Klicke auf „Create app“.
       App name:     djsync
       Description:  Playlists aus Musikordnern
       Redirect URI: {REDIRECT_URI}   (genau so eintragen, dann „Add“)
  3. Bei „Which API/SDKs are you planning to use?“ den Haken bei „Web API“ setzen,
     den Bedingungen zustimmen und „Save“ klicken.
  4. In der neuen App auf „Settings“ gehen und die „Client ID“ kopieren
     (32 Zeichen, z. B. 3f2a…). Ein „Client secret“ wird nicht gebraucht.
"""


class Cancelled(Exception):
    pass


def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        print()
        raise Cancelled from None


def cmd_setup(args) -> None:
    from .cli import cmd_login

    if not sys.stdin.isatty():
        raise ConfigError("Die Einrichtung braucht ein interaktives Terminal.")
    print(SETUP_TEXT)
    ask("Enter drücken, um das Spotify-Dashboard zu öffnen … ")
    open_browser(DASHBOARD_URL)
    while True:
        value = ask("\nClient ID hier einfügen: ").strip()
        if is_valid_client_id(value):
            break
        print("Das sieht nicht nach einer Client ID aus (32 Zeichen aus 0–9 und a–f). Bitte erneut kopieren.")
    save_client_id(value)
    print(f"Gespeichert in {CONFIG_FILE}.\n")
    print("Jetzt noch bei Spotify anmelden – im Browser den Zugriff bestätigen.\n")
    cmd_login(args)


def run_interactive(folder: str | None) -> int:
    """Doppelklick auf djsync.exe oder Ordner auf die .exe gezogen."""
    from .cli import Abort, cmd_login, cmd_sync

    print("djsync – Musikordner als Spotify-Playlist\n")
    try:
        if not has_client_id():
            cmd_setup(None)
        elif not TOKEN_FILE.exists():
            print("Bitte bei Spotify anmelden – im Browser den Zugriff bestätigen.\n")
            cmd_login(None)

        while True:
            if folder is None:
                folder = ask(
                    "\nZiehe deinen Musikordner in dieses Fenster und drücke Enter\n"
                    "(oder Enter ohne Eingabe zum Beenden): "
                ).strip()
                if not folder:
                    return 0
            try:
                cmd_sync(_sync_args(folder))
            except (Abort, SpotifyError) as e:
                print(f"\nFehler: {e}")
            folder = None
    except (Cancelled, KeyboardInterrupt):
        print("\nAbgebrochen.")
        return 130
    except (ConfigError, AuthError, SpotifyError) as e:
        print(f"\nFehler: {e}")
        return 1
    finally:
        _pause()


def _sync_args(folder: str) -> argparse.Namespace:
    return argparse.Namespace(folder=folder, name=None, yes=False, dry_run=False, no_review=False, retry=False)


def _pause() -> None:
    """Hält das Fenster offen, damit man das Ergebnis lesen kann."""
    if IS_WINDOWS and sys.stdin.isatty():
        try:
            input("\nEnter drücken zum Schließen … ")
        except (EOFError, KeyboardInterrupt):
            pass
