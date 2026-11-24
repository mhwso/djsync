"""Sync: starten, Fortschritt, abbrechen, Zusammenfassung, Änderungsplan, bestätigen, verwerfen.

Es gibt höchstens einen Sync gleichzeitig. Sein Zustand:

    running ──► ready ──► (confirm) ──► vorbei, Playlist angeglichen
       │          └─────► (discard) ──► vorbei, nichts geändert
       ├──► cancelled   (cancel; Playlist unverändert)
       └──► failed      (Spotify-Fehler, leerer Ordner …; Meldung in „error“)

Einlesen, Playlist laden und Suche laufen in einem Hintergrund-Thread (eigene DB-Verbindung)
und melden sich über Events:
    sync.progress   {folder, step, done, total}   step: scan | playlist | search; total 0 = unbestimmt
    sync.ready      {folder}                      Zusammenfassung und Änderungsplan abrufbar
    sync.cancelled  {folder}
    sync.failed     {folder, message}
    sync.done       {folder, playlist_id}         nach confirm

Im Zustand „ready“ sind `summary()` und `plan()` beliebig oft aufrufbar; `plan()` wird jedes Mal
aus der Datenbank neu berechnet, damit Review-Entscheidungen einfließen. Erst `confirm()`
verändert die Playlist auf Spotify.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field

import httpx

from ... import sync_phases as phases
from ...auth import AuthError
from ...config import ConfigError
from ...spotify import SpotifyError
from .base import ApiArea, ApiError
from .folders import PLAYLIST_URL, _entry

RUNNING, READY, APPLYING, CANCELLED, FAILED = "running", "ready", "applying", "cancelled", "failed"
# Solange ein Sync in einem dieser Zustände ist, wird kein weiterer gestartet
BUSY = {RUNNING, READY, APPLYING}


@dataclass
class _Session:
    folder: str
    cancel: threading.Event = field(default_factory=threading.Event)
    state: str = RUNNING
    progress: dict | None = None
    error: str | None = None
    searched: int = 0
    run: phases.SyncRun | None = None
    thread: threading.Thread | None = None


class SyncApi(ApiArea):
    def __init__(self, ctx):
        super().__init__(ctx)
        self._lock = threading.Lock()
        self._session: _Session | None = None

    # ---- Ablauf -----------------------------------------------------------

    def start(self, folder: str, retry: bool = False) -> dict:
        """Startet den Sync eines Ordners im Hintergrund und gibt den Status zurück.

        retry: auch kürzlich erfolglos gesuchte Tracks erneut suchen.
        """
        with self._ctx.db() as db:
            if db.get_playlist(folder) is None:
                raise ApiError(f"Der Ordner „{folder}“ ist nicht in djsync.")
        if not os.path.isdir(folder):
            raise ApiError(f"Der Ordner „{folder}“ ist nicht erreichbar. Ist das Laufwerk eingebunden?")
        with self._lock:
            current = self._session
            if current and current.state in BUSY:
                raise ApiError(f"Es läuft bereits ein Sync für „{current.folder}“. Bitte erst abschließen oder abbrechen.")
            session = _Session(folder)
            session.thread = threading.Thread(
                target=self._prepare, args=(session, retry), name="djsync-sync", daemon=True
            )
            self._session = session
        session.thread.start()
        return _status(session)

    def status(self) -> dict | None:
        """Stand des aktuellen Syncs oder None, wenn keiner läuft:
        {folder, state, progress: {step, done, total} | None, error, searched}."""
        session = self._session
        return _status(session) if session else None

    def cancel(self) -> dict | None:
        """Bricht den laufenden Sync ab, sobald die aktuelle Spotify-Anfrage fertig ist (Zustand
        danach „cancelled“). Die Playlist bleibt unverändert; schon gefundene Zuordnungen bleiben
        gespeichert. Ist der Sync schon fertig eingelesen, wirkt cancel wie discard."""
        with self._lock:
            session = self._session
            if session is None:
                return None
            if session.state == RUNNING:
                session.cancel.set()
                return _status(session)
            if session.state == APPLYING:
                raise ApiError("Die Änderungen werden gerade übertragen und lassen sich nicht mehr abbrechen.")
            self._session = None
            return None

    def summary(self) -> dict:
        """Zusammenfassung nach Treffer-Status (Zustand „ready“):
        {folder, found, fresh, searched, counts: {status: n}, open: [{file, fingerprint}]}."""
        session = self._ready()
        with self._ctx.db() as db:
            summary = phases.summarize_run(session.run, db)
        return {
            "folder": session.folder,
            "found": session.run.found,
            "fresh": session.run.fresh,
            "searched": session.searched,
            "counts": {status: len(files) for status, files in summary.groups.items()},
            "open": [{"file": os.path.basename(f.path), "fingerprint": fp} for f, fp in summary.pending],
        }

    def plan(self) -> dict:
        """Änderungsplan (Zustand „ready“), jedes Mal neu aus den aktuellen Zuordnungen berechnet:
        {folder, create, name, rename, playlist_lost, added, removed: [{id, label}], reordered,
         total, needs_write}."""
        session = self._ready()
        with self._ctx.db() as db:
            change = phases.plan_changes(session.run, db)
        run, plan = session.run, change.plan
        return {
            "folder": session.folder,
            "create": change.new_name is not None,
            "name": change.new_name or change.rename or run.playlist_name,
            "rename": change.rename,
            "playlist_lost": run.playlist_lost,
            "added": [{"id": t, "label": change.labels.get(t, t)} for t in plan.added],
            "removed": [{"id": t, "label": change.labels.get(t, "spotify:track:" + t)} for t in plan.removed],
            "reordered": plan.reordered,
            "total": len(plan.final),
            "needs_write": change.needs_write,
        }

    def confirm(self) -> dict:
        """Übernimmt den Änderungsplan: legt die Playlist beim ersten Sync mit dem gespeicherten
        Namen an bzw. gleicht sie an. Gibt den Ordner-Eintrag wie `folders.list()` zurück.
        Bei einem Fehler bleibt der Sync im Zustand „ready“ und lässt sich erneut bestätigen."""
        with self._lock:
            session = self._ready()
            session.state = APPLYING
        client = None
        try:
            with self._ctx.db() as db:
                change = phases.plan_changes(session.run, db)
                client = self._ctx.spotify()
                playlist_id = phases.apply_changes(session.run, change, db, client)
                entry = _entry(db, db.get_playlist(session.folder))
        except Exception as e:
            session.state = READY
            raise ApiError("Die Änderungen konnten nicht übertragen werden: " + _message(e)) from e
        finally:
            if client:
                client.close()
        with self._lock:
            self._session = None
        self._ctx.events.emit("sync.done", {"folder": session.folder, "playlist_id": playlist_id})
        return {**entry, "playlist_url": PLAYLIST_URL.format(playlist_id)}

    def discard(self) -> None:
        """Verwirft den eingelesenen Sync; auf Spotify bleibt alles unverändert."""
        with self._lock:
            session = self._session
            if session is None:
                return
            if session.state in (RUNNING, APPLYING):
                raise ApiError("Der Sync läuft noch. Bitte erst abbrechen.")
            self._session = None

    # ---- intern -----------------------------------------------------------

    def _ready(self) -> _Session:
        session = self._session
        if session is None or session.state != READY:
            raise ApiError("Es gibt keinen eingelesenen Sync. Bitte den Sync neu starten.")
        return session

    def _prepare(self, session: _Session, retry: bool) -> None:
        """Hintergrund-Thread: einlesen, Playlist laden, suchen. Ändert nichts auf Spotify."""
        events = self._ctx.events

        def progress(step: str, done: int, total: int) -> None:
            session.progress = {"step": step, "done": done, "total": total}
            events.emit("sync.progress", {"folder": session.folder, **session.progress})

        client = None
        try:
            cfg = self._ctx.load_config()
            client = self._ctx.spotify(cfg)
            with self._ctx.db() as db:  # eigene Verbindung: SQLite-Verbindungen bleiben in ihrem Thread
                cancel = session.cancel.is_set
                run = phases.read_folder(session.folder, db, cfg, on_progress=progress, cancel=cancel)
                phases.load_playlist(run, db, client, on_progress=progress, cancel=cancel)
                session.searched = phases.search_tracks(
                    run, db, client, cfg, retry=retry, on_progress=progress, cancel=cancel
                )
        except phases.SyncCancelled:
            session.state = CANCELLED
            events.emit("sync.cancelled", {"folder": session.folder})
        except Exception as e:  # jeder Fehler muss in der Oberfläche ankommen, nicht im Thread verschwinden
            session.error = _message(e)
            session.state = FAILED
            events.emit("sync.failed", {"folder": session.folder, "message": session.error})
        else:
            session.run = run
            session.state = READY
            events.emit("sync.ready", {"folder": session.folder})
        finally:
            if client:
                client.close()


def _status(session: _Session) -> dict:
    return {
        "folder": session.folder,
        "state": session.state,
        "progress": session.progress,
        "error": session.error,
        "searched": session.searched,
    }


def _message(e: Exception) -> str:
    """Verständliche Meldung für Fehler beim Sync."""
    if isinstance(e, phases.EmptyFolderError | ConfigError):
        return str(e)
    if isinstance(e, AuthError):
        return "Die Anmeldung bei Spotify ist abgelaufen oder ungültig. Bitte über die Einrichtung neu anmelden."
    if isinstance(e, SpotifyError):
        if e.status == 429:  # Rate-Limit bzw. Kontingent: Meldung ist schon verständlich
            return str(e)
        if e.status in (401, 403):
            return "Spotify verweigert den Zugriff. Bitte über die Einrichtung neu anmelden."
        return f"Spotify meldet einen Fehler ({e.status or 'unbekannt'}). Bitte später erneut versuchen."
    if isinstance(e, httpx.HTTPError):
        return "Spotify ist nicht erreichbar. Besteht eine Internetverbindung?"
    return f"Unerwarteter Fehler: {e}"
