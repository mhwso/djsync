"""Startbefehl der GUI: öffnet das pywebview-Fenster mit der statischen Oberfläche."""

from __future__ import annotations

from pathlib import Path

from .api import Api
from .api.folders import install_drop
from .context import AppContext
from .events import WebviewEvents

STATIC_DIR = Path(__file__).resolve().parent / "static"


def main() -> int:
    import webview  # erst hier: Tests und CLI brauchen pywebview nicht

    events = WebviewEvents()
    api = Api(AppContext.default(events=events))
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
    # Eingebauter HTTP-Server statt file://, damit die ES-Module der Oberfläche laden
    webview.start(http_server=True)
    return 0
