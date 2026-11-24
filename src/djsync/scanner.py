"""Liest Audiodateien eines Ordners ein – mit Cache über Größe und mtime."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .db import Database
from .filenames import parse_filename, to_internal_path
from .matching import fingerprint
from .models import LocalFile


def iter_audio_files(folder: str, extensions) -> list[str]:
    exts = {e.lower() for e in extensions}
    result = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in files:
            # versteckte Dateien, u. a. macOS-„._“-Begleitdateien, überspringen
            if name.startswith("."):
                continue
            if os.path.splitext(name)[1].lower() in exts:
                result.append(to_internal_path(os.path.join(root, name)))
    return sorted(result)


def read_tags(path: str) -> dict:
    """Artist, Titel, ISRC und Dauer aus den Tags – robust für MP3/FLAC/M4A/WAV/AIFF."""
    from mutagen import File

    result: dict = {"artist": None, "title": None, "isrc": None, "duration_ms": None}
    try:
        audio = File(path, easy=True)
    except Exception:
        return result
    if audio is None:
        return result

    length = getattr(getattr(audio, "info", None), "length", None)
    if length:
        result["duration_ms"] = int(length * 1000)

    tags = audio.tags
    if tags is None:
        return result

    def first(*keys: str) -> str | None:
        for key in keys:
            try:
                value = tags.get(key)
            except Exception:
                value = None
            if not value:
                continue
            if isinstance(value, list):
                value = value[0] if value else None
            if hasattr(value, "text"):  # ID3-Frame (WAV/AIFF ohne Easy-Wrapper)
                value = value.text[0] if value.text else None
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    result["artist"] = first("artist", "TPE1", "\xa9ART")
    result["title"] = first("title", "TIT2", "\xa9nam")
    result["isrc"] = first("isrc", "TSRC")
    return result


def load_file(path: str, st: os.stat_result) -> LocalFile:
    tags = read_tags(path)
    fn_artist, fn_title = parse_filename(Path(path).stem)
    return LocalFile(
        path=path,
        size=st.st_size,
        mtime=st.st_mtime,
        artist=tags["artist"] or fn_artist,
        title=tags["title"] or fn_title,
        isrc=tags["isrc"],
        duration_ms=tags["duration_ms"],
    )


@dataclass
class ScanResult:
    files: list[tuple[LocalFile, str | None]]  # (Datei, Fingerprint)
    found: int  # Anzahl Audiodateien im Ordner
    fresh: int  # davon neu eingelesen (nicht aus dem Cache)


def scan_folder(
    folder: str,
    db: Database,
    extensions,
    on_progress: Callable[[int, int], None] | None = None,
) -> ScanResult:
    """Liest alle Audiodateien ein und hält den DB-Cache aktuell – ohne Terminal-Ausgabe.

    on_progress(erledigt, gesamt) kommt einmal nach dem Auflisten (0, gesamt) und vor jeder Datei;
    eine Ausnahme aus dem Rückruf bricht das Einlesen ab.
    """
    report = on_progress or (lambda done, total: None)
    cached = db.files_under(folder)
    paths = iter_audio_files(folder, extensions)
    report(0, len(paths))
    result = []
    fresh = 0
    for i, path in enumerate(paths, 1):
        report(i, len(paths))
        try:
            st = os.stat(path)
        except OSError:
            continue
        hit = cached.get(path)
        if hit and hit[0].size == st.st_size and hit[0].mtime == st.st_mtime:
            result.append(hit)
            continue
        f = load_file(path, st)
        fp = fingerprint(f)
        db.upsert_file(f, fp)
        result.append((f, fp))
        fresh += 1

    gone = set(cached) - set(paths)
    if gone:
        db.delete_files(gone)
    db.commit()
    return ScanResult(result, len(paths), fresh)
