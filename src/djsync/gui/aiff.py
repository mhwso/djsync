"""AIFF/AIF → WAV, damit WebView2 die Datei abspielen kann (es spielt kein AIFF).

Bewusst ohne zusätzliche Bibliothek: `aifc` ist seit Python 3.13 nicht mehr in der
Standardbibliothek, und Bibliotheken wie soundfile bringen eine native DLL mit, die PyInstaller
mitbündeln müsste. AIFF ist unkomprimiertes PCM mit Big-Endian-Samples, WAV dasselbe mit
Little-Endian – die Umwandlung besteht also nur aus Header lesen, Bytes je Sample umdrehen und
einen WAV-Header schreiben. Unterstützt werden AIFF und AIFF-C mit „NONE“, „twos“ (Big-Endian)
und „sowt“ (Little-Endian), 8 bis 32 Bit; komprimiertes AIFF-C wird abgelehnt.

Die Datei wird in Blöcken gelesen, nie ganz in den Speicher.
"""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

AIFF_SUFFIXES = (".aiff", ".aif")

_BIG_ENDIAN = (b"NONE", b"twos")
_LITTLE_ENDIAN = (b"sowt",)
_BLOCK = 1 << 20  # ca. 1 MiB je Lesevorgang
_UNSIGNED_8BIT = bytes((b + 128) & 0xFF for b in range(256))  # AIFF 8 Bit ist signiert, WAV nicht


class AiffError(Exception):
    """Die Datei ist kein lesbares (unkomprimiertes) AIFF."""


@dataclass(frozen=True)
class _Format:
    channels: int
    frames: int
    bits: int
    rate: int
    little_endian: bool
    data_offset: int  # Beginn der Samples in der Datei

    @property
    def width(self) -> int:
        return (self.bits + 7) // 8

    @property
    def data_size(self) -> int:
        return self.frames * self.channels * self.width


def cached_wav(source: Path, cache_dir: Path) -> Path:
    """Die WAV-Fassung von `source` im Zwischenspeicher; wandelt nur um, wenn sie fehlt.

    Der Dateiname enthält Pfad sowie Größe und Änderungszeit der Quelle: eine geänderte
    Quelldatei ergibt eine neue Umwandlung, ältere Fassungen derselben Quelle werden entfernt.
    """
    stat = source.stat()
    path_key = hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:16]
    target = cache_dir / f"{path_key}-{stat.st_size:x}-{stat.st_mtime_ns:x}.wav"
    if target.is_file():
        return target
    cache_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=cache_dir, prefix=f"{path_key}-", suffix=".part")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out, source.open("rb") as src:
            _convert(src, out)
        try:
            os.replace(tmp, target)
        except OSError:
            # gleichzeitig schon umgewandelt und unter Windows gerade geöffnet → die nehmen
            if not target.is_file():
                raise
    finally:
        tmp.unlink(missing_ok=True)
    for old in cache_dir.glob(f"{path_key}-*.wav"):
        if old != target:
            try:
                old.unlink()
            except OSError:
                pass  # wird vielleicht gerade abgespielt; beim nächsten Mal
    return target


def _convert(src: BinaryIO, out: BinaryIO) -> None:
    fmt = _read_format(src)
    out.write(_wav_header(fmt))
    frame = fmt.channels * fmt.width
    block = max(_BLOCK // frame, 1) * frame
    remaining = fmt.data_size
    src.seek(fmt.data_offset)
    while remaining > 0:
        data = src.read(min(block, remaining))
        if not data:
            break  # abgeschnittene Datei: was da ist, wird abgespielt
        data = data[: len(data) - len(data) % fmt.width]
        out.write(_to_wav_samples(data, fmt))
        remaining -= len(data)
    if remaining > 0:  # Header passend zur tatsächlichen Länge korrigieren
        written = fmt.data_size - remaining
        out.seek(0)
        out.write(_wav_header(_Format(fmt.channels, written // frame, fmt.bits, fmt.rate, fmt.little_endian, 0)))


def _to_wav_samples(data: bytes, fmt: _Format) -> bytes:
    w = fmt.width
    if w == 1:
        return data.translate(_UNSIGNED_8BIT)
    if fmt.little_endian:
        return data
    swapped = bytearray(len(data))
    for i in range(w):  # Byte i jedes Samples ← Byte w-1-i (über Slices, schnell)
        swapped[i::w] = data[w - 1 - i :: w]
    return bytes(swapped)


def _wav_header(fmt: _Format) -> bytes:
    block_align = fmt.channels * fmt.width
    fmt_chunk = struct.pack(
        "<HHIIHH", 1, fmt.channels, fmt.rate, fmt.rate * block_align, block_align, fmt.width * 8
    )
    return (
        b"RIFF"
        + struct.pack("<I", 4 + 8 + len(fmt_chunk) + 8 + fmt.data_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt_chunk))
        + fmt_chunk
        + b"data"
        + struct.pack("<I", fmt.data_size)
    )


def _read_format(src: BinaryIO) -> _Format:
    header = src.read(12)
    if len(header) < 12 or header[:4] != b"FORM" or header[8:12] not in (b"AIFF", b"AIFC"):
        raise AiffError("keine AIFF-Datei")
    is_aifc = header[8:12] == b"AIFC"
    comm: tuple[int, int, int, int, bool] | None = None
    data_offset: int | None = None
    while True:
        chunk = src.read(8)
        if len(chunk) < 8:
            break
        cid, size = chunk[:4], struct.unpack(">I", chunk[4:])[0]
        start = src.tell()
        if cid == b"COMM":
            comm = _parse_comm(src.read(size), is_aifc)
        elif cid == b"SSND":
            head = src.read(8)  # Offset und Blockgröße
            if len(head) < 8:
                raise AiffError("abgeschnittene AIFF-Datei")
            offset = struct.unpack(">I", head[:4])[0]
            data_offset = start + 8 + offset
        src.seek(start + size + (size & 1))  # Chunks sind auf gerade Länge aufgefüllt
    if comm is None or data_offset is None:
        raise AiffError("unvollständige AIFF-Datei")
    channels, frames, bits, rate, little = comm
    if not (1 <= channels and 1 <= bits <= 32 and rate > 0):
        raise AiffError("ungültiges Format")
    return _Format(channels, frames, bits, rate, little, data_offset)


def _parse_comm(data: bytes, is_aifc: bool) -> tuple[int, int, int, int, bool]:
    if len(data) < 18:
        raise AiffError("ungültiger COMM-Chunk")
    channels, frames, bits = struct.unpack(">hIh", data[:8])
    rate = _extended(data[8:18])
    little = False
    if is_aifc:
        compression = data[18:22]
        if compression in _LITTLE_ENDIAN:
            little = True
        elif compression not in _BIG_ENDIAN:
            raise AiffError(f"komprimiertes AIFF-C ({compression.decode('latin-1').strip()}) wird nicht unterstützt")
    return channels, frames, bits, rate, little


def _extended(data: bytes) -> int:
    """80-Bit-Gleitkommazahl (IEEE 754 extended, Big-Endian) → ganze Abtastrate."""
    exponent, mantissa = struct.unpack(">HQ", data)
    exponent &= 0x7FFF
    if exponent == 0 and mantissa == 0:
        return 0
    return round(mantissa * 2.0 ** (exponent - 16383 - 63))
