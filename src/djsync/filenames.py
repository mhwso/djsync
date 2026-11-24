from __future__ import annotations

import os
import platform
import re
from pathlib import PurePosixPath

_TRACKNUMBER_RE = re.compile(r"^\s*\d{1,3}\s*[-._)]\s*")
_SEPARATOR_RE = re.compile(r"\s+[-–—]\s+")
_WINDOWS_PATH_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")


def parse_filename(stem: str) -> tuple[str | None, str | None]:
    """'01 - Artist - Title (Extended Mix)' → ('Artist', 'Title (Extended Mix)')."""
    name = _TRACKNUMBER_RE.sub("", stem).strip()
    if not name:
        return None, None
    parts = _SEPARATOR_RE.split(name, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return None, name


def is_wsl() -> bool:
    return "microsoft" in platform.release().lower()


def normalize_folder(arg: str, *, wsl: bool | None = None, sep: str = os.sep) -> str:
    """Nutzereingabe → interner Ordnerpfad (absolut, immer mit „/“, ohne Schrägstrich am Ende).

    Unter WSL wird „D:\\Musik“ zu „/mnt/d/Musik“, unter Windows zu „D:/Musik“.
    Anführungszeichen (z. B. vom Hineinziehen ins Fenster) werden entfernt.
    """
    arg = arg.strip().strip('"').strip("'").strip()
    if wsl is None:
        wsl = is_wsl()
    if wsl:
        arg = windows_to_wsl(arg)
    path = os.path.abspath(os.path.expanduser(arg)) if sep == os.sep else arg
    if sep == "\\":
        path = path.replace("\\", "/")
    path = path.rstrip("/")
    if re.fullmatch(r"[A-Za-z]:", path):
        return path + "/"  # „D:“ allein hieße „aktuelles Verzeichnis auf D:“
    return path or "/"


def to_internal_path(path: str) -> str:
    """Pfad aus os.walk & Co. in die interne Form mit „/“ bringen."""
    return path.replace(os.sep, "/") if os.sep != "/" else path


def windows_to_wsl(path: str) -> str:
    """'D:\\Musik\\Techno' → '/mnt/d/Musik/Techno'; andere Pfade unverändert."""
    m = _WINDOWS_PATH_RE.match(path)
    if not m:
        return path
    rest = m.group(2).replace("\\", "/").strip("/")
    return str(PurePosixPath("/mnt", m.group(1).lower(), rest)) if rest else f"/mnt/{m.group(1).lower()}"
