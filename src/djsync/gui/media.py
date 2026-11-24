"""Lokaler Medien-Server: stellt Audiodateien der WebView bereit, ohne Upload.

Die Oberfläche läuft über den HTTP-Server von pywebview; `file://`-Adressen darf sie von dort
nicht laden. Deshalb startet beim ersten Anhören ein kleiner HTTP-Server nur auf 127.0.0.1
(freier Port). Er liefert ausschließlich Dateien, die die API-Schicht vorher freigegeben hat,
jeweils unter einem zufälligen Kürzel – beliebige Pfade lassen sich darüber nicht abrufen.

Range-Anfragen werden unterstützt, sonst kann das <audio>-Element nicht springen.
"""

from __future__ import annotations

import re
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

CONTENT_TYPES = {
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
}

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
_CHUNK = 64 * 1024


class MediaServer:
    """Gibt einzelne Dateien frei und liefert sie über http://127.0.0.1:<port>/media/<kürzel>/<name>."""

    def __init__(self) -> None:
        self._tokens: dict[Path, str] = {}  # Pfad → Kürzel (gleiche Datei, gleiche Adresse)
        self._files: dict[str, Path] = {}  # Kürzel → Pfad
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None

    def url_for(self, path: Path) -> str:
        """Gibt die Datei frei und liefert ihre Adresse; startet den Server bei Bedarf."""
        path = Path(path)
        with self._lock:
            token = self._tokens.get(path)
            if token is None:
                token = secrets.token_urlsafe(16)
                self._tokens[path] = token
                self._files[token] = path
            port = self._start()
        return f"http://127.0.0.1:{port}/media/{token}/{quote(path.name)}"

    def close(self) -> None:
        with self._lock:
            if self._server is not None:
                self._server.shutdown()
                self._server.server_close()
                self._server = None

    def _lookup(self, token: str) -> Path | None:
        with self._lock:
            return self._files.get(token)

    def _start(self) -> int:
        if self._server is None:
            server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(self))
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, name="djsync-media", daemon=True).start()
            self._server = server
        return self._server.server_address[1]


def _handler(media: MediaServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self) -> None:
            self._serve(body=False)

        def do_GET(self) -> None:
            self._serve(body=True)

        def _serve(self, body: bool) -> None:
            parts = self.path.split("/")  # "", "media", kürzel, name
            path = media._lookup(parts[2]) if len(parts) >= 3 and parts[1] == "media" else None
            if path is None or not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            size = path.stat().st_size
            start, end = 0, size - 1
            status = HTTPStatus.OK
            requested = self.headers.get("Range")
            if requested:
                span = _parse_range(requested, size)
                if span is None:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                start, end = span
                status = HTTPStatus.PARTIAL_CONTENT
            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream"))
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if not body:
                return
            try:
                with path.open("rb") as f:
                    f.seek(start)
                    _copy(f, self.wfile, length)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # die WebView bricht Anfragen beim Springen ab – kein Fehler

        def log_message(self, format: str, *args) -> None:
            pass  # kein Protokoll auf der (unter Windows fehlenden) Konsole

    return Handler


def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """Ein einzelner Bereich „bytes=a-b“, „bytes=a-“ oder „bytes=-n“ → (start, ende) oder None."""
    m = _RANGE_RE.match(header.strip())
    if not m or size == 0 or (not m.group(1) and not m.group(2)):
        return None
    if not m.group(1):  # die letzten n Bytes
        n = int(m.group(2))
        return (max(size - n, 0), size - 1) if n else None
    start = int(m.group(1))
    end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
    return (start, end) if start <= end else None


def _copy(src, dst, length: int) -> None:
    while length > 0:
        chunk = src.read(min(_CHUNK, length))
        if not chunk:
            break
        dst.write(chunk)
        length -= len(chunk)

