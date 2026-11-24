from __future__ import annotations

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


def windows_to_wsl(path: str) -> str:
    """'D:\\Musik\\Techno' → '/mnt/d/Musik/Techno'; andere Pfade unverändert."""
    m = _WINDOWS_PATH_RE.match(path)
    if not m:
        return path
    rest = m.group(2).replace("\\", "/").strip("/")
    return str(PurePosixPath("/mnt", m.group(1).lower(), rest)) if rest else f"/mnt/{m.group(1).lower()}"
