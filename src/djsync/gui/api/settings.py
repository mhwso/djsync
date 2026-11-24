"""Einstellungen: lesen und (geprüft) in config.toml speichern. Die CLI liest dieselbe Datei."""

from __future__ import annotations

from ...config import SETTINGS, Config, SettingsError, save_settings
from .base import ApiArea, ApiError


def _as_dict(cfg: Config) -> dict:
    values = {key: getattr(cfg, key) for key in SETTINGS}
    values["extensions"] = list(cfg.extensions)
    return values


class SettingsApi(ApiArea):
    def get(self) -> dict:
        """Aktuelle Werte: extensions (Liste, z. B. ".mp3"), duration_tolerance_s, min_score,
        retry_missing_days, review_candidates, start_position_s (Startstelle), skip_s (Sprungweite)."""
        return _as_dict(self._ctx.load_config())

    def save(self, values: dict) -> dict:
        """Prüft alle Werte und speichert sie in config.toml; gibt die gespeicherten Werte zurück.

        Ungültige Werte: ApiError mit einer Zeile je Fehler („Startstelle: …“), nichts wird gespeichert.
        """
        try:
            save_settings(values, self._ctx.config_file)
        except SettingsError as e:
            raise ApiError(str(e)) from None
        return self.get()
