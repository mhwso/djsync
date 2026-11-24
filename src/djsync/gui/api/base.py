from __future__ import annotations

from ..context import AppContext


class ApiError(Exception):
    """Erwartbarer Fehler mit einer Meldung, die die Oberfläche so anzeigen kann."""


class ApiArea:
    """Basis für einen fachlichen Bereich der API (Ordner, Sync, Review, …)."""

    def __init__(self, ctx: AppContext):
        self._ctx = ctx
