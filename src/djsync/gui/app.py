"""Startbefehl der GUI: öffnet das pywebview-Fenster mit der statischen Oberfläche."""

from __future__ import annotations

import socket
from pathlib import Path

from .api import Api
from .api.folders import install_drop
from .context import AppContext
from .events import WebviewEvents
from .windows import WebviewWindows

STATIC_DIR = Path(__file__).resolve().parent / "static"


def free_port() -> int:
    """Ein freier Port auf 127.0.0.1 für den HTTP-Server von pywebview.

    Ohne Angabe nimmt pywebview mit festem Profil immer Port 42001. Der liegt z. B. bei WSL im
    Netzwerkmodus „mirrored“ in einem für Linux reservierten Bereich, der Start scheitert dann
    mit WinError 10013 (#8). Den Port vergibt deshalb das System."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    import webview  # erst hier: Tests und CLI brauchen pywebview nicht

    events = WebviewEvents()
    ctx = AppContext.default(events=events, windows=WebviewWindows())
    api = Api(ctx)
    window = webview.create_window(
        "djsync",
        url=str(STATIC_DIR / "index.html"),
        js_api=api,
        width=1100,
        height=720,
        min_size=(760, 480),
    )
    events.window = window
    window.events.loaded += lambda: install_drop(window, events)
    window.events.closed += ctx.media.close  # lokalen Medien-Server zum Anhören beenden
    ctx.webview_dir.mkdir(parents=True, exist_ok=True)
    webview.start(
        # Eingebauter HTTP-Server statt file://, damit die ES-Module der Oberfläche laden
        http_server=True,
        http_port=free_port(),
        # Festes WebView2-Profil: Die Anmeldung im eingebetteten Spotify-Player übersteht so
        # einen Neustart (ADR 0003). Im Standard (private_mode) wäre sie jedes Mal weg.
        private_mode=False,
        storage_path=str(ctx.webview_dir),
    )
    return 0
