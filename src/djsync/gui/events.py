"""Events von Python an die Oberfläche, z. B. Fortschritt eines Syncs.

Die API-Schicht meldet über `ctx.events.emit(name, daten)`. In der App landet das als
`djsync.on(name, fn)` im JS-Teil (siehe static/js/api.js), in Tests in `RecordingEvents`.
Die Daten müssen JSON-fähig sein.
"""

from __future__ import annotations

import json
from typing import Any, Protocol


class Events(Protocol):
    def emit(self, name: str, data: Any = None) -> None: ...


class NullEvents:
    """Verwirft alle Events (z. B. wenn kein Fenster offen ist)."""

    def emit(self, name: str, data: Any = None) -> None:
        pass


class WebviewEvents:
    """Leitet Events an das pywebview-Fenster weiter. `window` wird nach dem Erzeugen gesetzt."""

    def __init__(self):
        self.window = None

    def emit(self, name: str, data: Any = None) -> None:
        if self.window is None:
            return
        self.window.evaluate_js(
            f"window.djsync && window.djsync.emit({json.dumps(name)}, {json.dumps(data, ensure_ascii=False)})"
        )
