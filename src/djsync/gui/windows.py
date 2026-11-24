"""Zusätzliche Fenster der App, z. B. die Anmeldung im eingebetteten Spotify-Player.

Die API-Schicht öffnet sie über `ctx.windows.open(...)`. In der App ist das ein weiteres
pywebview-Fenster im selben Prozess und damit mit demselben WebView2-Profil: Cookies aus der
Anmeldung gelten auch für den eingebetteten Player im Hauptfenster (ADR 0003). In Tests
merkt sich `RecordingWindows` (tests/fakes.py) die geöffneten Fenster.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class Windows(Protocol):
    def open(self, title: str, url: str, on_closed: Callable[[], None] | None = None) -> None: ...


class NullWindows:
    """Öffnet nichts (z. B. ohne laufende GUI)."""

    def open(self, title: str, url: str, on_closed: Callable[[], None] | None = None) -> None:
        pass


class WebviewWindows:
    """Öffnet ein weiteres pywebview-Fenster."""

    def open(self, title: str, url: str, on_closed: Callable[[], None] | None = None) -> None:
        import webview  # erst hier: Tests und CLI brauchen pywebview nicht

        window = webview.create_window(title, url, width=520, height=760)
        if on_closed is not None:
            window.events.closed += on_closed
