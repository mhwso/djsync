"""Anhören im Review: abspielbare Adresse der lokalen Datei eines Tracks.

Die Datei wird über den lokalen Medien-Server (`gui/media.py`) bereitgestellt, nichts wird
hochgeladen. WebView2 spielt kein AIFF; AIFF/AIF wird deshalb in WAV umgewandelt und im
Zwischenspeicher unter dem Datenordner abgelegt (`gui/aiff.py`).
"""

from __future__ import annotations

from pathlib import Path

from ..aiff import AIFF_SUFFIXES, AiffError, cached_wav
from ..context import AppContext
from .base import ApiArea, ApiError
from .review import ReviewApi


class PlayerApi(ApiArea):
    def __init__(self, ctx: AppContext):
        super().__init__(ctx)
        self._review = ReviewApi(ctx)  # für die Track-Suche; privat, für JS unsichtbar

    def local(self, folder: str, fingerprint: str) -> dict:
        """Abspielbare Adresse der lokalen Datei des Tracks. Rückgabe:
          url        – http://127.0.0.1:…, nur für diese Datei freigegeben
          converted  – True, wenn aus AIFF in WAV umgewandelt (bzw. aus dem Zwischenspeicher)
        Die Startstelle und Sprungweite kommen aus `settings.get`.
        """
        with self._ctx.db() as db:
            path = Path(self._review._find(db, folder, fingerprint).file.path)
        if not path.is_file():
            raise ApiError(f"Die Datei „{path.name}“ ist nicht (mehr) vorhanden.")
        converted = path.suffix.lower() in AIFF_SUFFIXES
        if converted:
            try:
                path = cached_wav(path, self._ctx.cache_dir / "wav")
            except AiffError as e:
                raise ApiError(f"„{path.name}“ lässt sich nicht abspielen: {e}") from e
        return {"url": self._ctx.media.url_for(path), "converted": converted}
