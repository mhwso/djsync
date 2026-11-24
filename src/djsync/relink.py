"""Relink: einen verschobenen oder umbenannten Ordner mit seinem neuen Pfad verknüpfen.

Playlist und Zuordnungen bleiben erhalten; nur die Pfade in der Datenbank ändern sich.
Gemeinsamer Kern für `djsync relink` und die GUI, ohne Terminal-Ein-/Ausgabe.
"""

from __future__ import annotations

import os

from .db import Database


class RelinkError(Exception):
    """Relink nicht möglich; `str(e)` ist die Nutzermeldung."""


class UnknownFolderError(RelinkError):
    """Der alte Ordner ist nicht in djsync."""


def relink_folder(db: Database, old: str, new: str) -> int:
    """Verknüpft den Ordner `old` mit `new` (beide in interner Form) und committet.

    Gibt die Anzahl übernommener Dateien zurück. Wirft `RelinkError`, wenn `new` nicht
    erreichbar oder bereits verknüpft ist oder `old` kein bekannter Ordner ist.
    """
    if not os.path.isdir(new):
        raise RelinkError(f"Neuer Ordner nicht erreichbar: {new}")
    if db.get_folder(new):
        raise RelinkError(f"Der Ordner {new} ist bereits mit einer Playlist verknüpft.")
    if not db.move_folder(old, new):
        raise UnknownFolderError(f"Der Ordner {old} ist kein Ordner von djsync.")
    moved = db.move_files(old, new)
    db.commit()
    return moved
