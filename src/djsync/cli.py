from __future__ import annotations

import argparse
import os
import sys
from contextlib import ExitStack

from . import sync_phases as phases
from . import ui
from .auth import Auth, AuthError
from .config import DB_FILE, IS_WINDOWS, SCOPES, TOKEN_FILE, ConfigError, load_config
from .db import Database
from .filenames import normalize_folder
from .models import APPROXIMATE, NOT_FOUND, NOT_ON_SPOTIFY, LocalFile
from .plan import Plan
from .relink import RelinkError, UnknownFolderError, relink_folder
from .review import pending_reviews, run_review
from .spotify import SpotifyClient, SpotifyError
from .sync import summarize
from .wizard import cmd_setup, run_interactive


class Abort(Exception):
    pass


# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------


def resolve_folder(arg: str) -> str:
    return normalize_folder(arg)


def setup(need_client: bool = True):
    db = Database(DB_FILE)
    if not need_client:
        return None, db, None
    cfg = load_config()
    client = SpotifyClient(Auth(cfg.client_id, cfg.redirect_uri, SCOPES, TOKEN_FILE))
    return cfg, db, client


def confirm(prompt: str) -> bool:
    return ui.confirm(prompt)


def print_summary(groups: dict[str, list[LocalFile]]) -> None:
    ui.summary({status: len(files) for status, files in groups.items()})


def print_files(status: str, files: list[LocalFile]) -> None:
    ui.file_list(status, [os.path.basename(f.path) for f in files])


def print_plan(plan: Plan, labels: dict[str, str], new_name: str | None) -> None:
    ui.plan(
        new_name,
        added=[labels.get(t, t) for t in plan.added],
        removed=[labels.get(t, "spotify:track:" + t) for t in plan.removed],
        reordered=plan.reordered,
        has_changes=plan.has_changes,
    )


# --------------------------------------------------------------------------
# Befehle
# --------------------------------------------------------------------------


def cmd_login(args) -> None:
    cfg = load_config()
    auth = Auth(cfg.client_id, cfg.redirect_uri, SCOPES, TOKEN_FILE)
    auth.login()
    client = SpotifyClient(auth)
    me = client._request("GET", "/me")
    ui.success(f"Angemeldet als [bold]{me.get('display_name') or me.get('id')}[/].")


class _TerminalProgress:
    """Zeigt den Fortschritt der Sync-Phasen als Spinner bzw. Ladebalken im Terminal."""

    BARS = {"scan": "Lese Dateien", "search": "Suche auf Spotify"}
    SPINNERS = {"list": "Suche Audiodateien …", "playlist": "Lade Playlist von Spotify …"}

    def __init__(self) -> None:
        self._stack: ExitStack | None = None
        self._step: str | None = None
        self._advance = None

    def __call__(self, step: str, done: int, total: int) -> None:
        if step != self._step:
            self.close()
            self._step = step
            self._stack = ExitStack()
            if step in self.BARS:
                self._advance = self._stack.enter_context(ui.progress(self.BARS[step], total))
            else:
                self._stack.enter_context(ui.spinner(self.SPINNERS[step]))
        if done and self._advance:
            self._advance()

    def close(self) -> None:
        if self._stack:
            self._stack.close()
        self._stack, self._step, self._advance = None, None, None

    def __enter__(self) -> _TerminalProgress:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def cmd_sync(args) -> None:
    folder = resolve_folder(args.folder)
    if not os.path.isdir(folder):
        raise Abort(f"Ordner nicht erreichbar: {folder}\nIst das Laufwerk eingebunden?")
    cfg, db, client = setup()

    ui.info(f"[muted]Ordner[/]  {folder}")
    with _TerminalProgress() as progress:
        progress("list", 0, 0)  # Spinner, bis die Dateien aufgelistet sind
        run = phases.read_folder(folder, db, cfg, on_progress=progress)
    ui.success(f"{run.found} Audiodateien gefunden [muted]({run.fresh} neu eingelesen)[/]")

    try:
        with _TerminalProgress() as progress:
            progress("playlist", 0, 0)
            phases.load_playlist(run, db, client, on_progress=progress)
    except phases.EmptyFolderError as e:
        raise Abort(str(e)) from None
    if run.playlist_lost:
        ui.warn("Die verknüpfte Playlist existiert nicht mehr und wird neu angelegt.")

    with _TerminalProgress() as progress:
        searched = phases.search_tracks(run, db, client, cfg, retry=args.retry, on_progress=progress)
    if searched:
        ui.success(f"{searched} Tracks auf Spotify gesucht")

    pending = phases.summarize_run(run, db).pending
    interactive = sys.stdin.isatty() and not (args.yes or args.dry_run or args.no_review)
    if pending and interactive:
        ui.info("")
        if confirm(f"{len(pending)} Tracks sind ungefähr oder nicht gefunden. Jetzt prüfen?"):
            run_review(pending, db, client, duration_tolerance_ms=cfg.duration_tolerance_ms)

    groups = phases.summarize_run(run, db).groups
    print_summary(groups)
    if not interactive or not pending:
        print_files(NOT_FOUND, groups[NOT_FOUND])
        print_files(APPROXIMATE, groups[APPROXIMATE])

    change = phases.plan_changes(run, db, name=args.name)
    print_plan(change.plan, change.labels, change.new_name)

    if args.dry_run:
        ui.info("\n[muted]Probelauf – auf Spotify wurde nichts geändert.[/]")
        return

    if change.needs_write and not args.yes:
        ui.info("")
        if not confirm("Änderungen auf Spotify übernehmen?"):
            ui.info("[muted]Abgebrochen – nichts geändert.[/]")
            return

    with ui.spinner("Übertrage Änderungen zu Spotify …"):
        playlist_id = phases.apply_changes(run, change, db, client)
    ui.playlist_link(playlist_id)


def _review_scope(db: Database, folder_arg: str | None) -> list[tuple[LocalFile, str | None]]:
    folders = [resolve_folder(folder_arg)] if folder_arg else [r["folder"] for r in db.synced_folders()]
    files = []
    for folder in folders:
        files.extend(db.files_under(folder).values())
    return files


def cmd_review(args) -> None:
    if not sys.stdin.isatty():
        raise Abort(
            "Das Review braucht ein interaktives Terminal.\n"
            "Bitte `djsync review` direkt in einem Terminal ausführen."
        )
    cfg, db, client = setup()
    files = _review_scope(db, args.folder)
    if args.folder and not files:
        raise Abort("Für diesen Ordner sind keine Dateien bekannt. Zuerst `djsync sync` ausführen.")
    changed = run_review(
        pending_reviews(files, db), db, client, duration_tolerance_ms=cfg.duration_tolerance_ms
    )
    if changed:
        ui.success(f"{changed} Zuordnungen geändert. Mit [bold]djsync sync <ordner>[/] in die Playlist übernehmen.")


def cmd_status(args) -> None:
    _, db, _ = setup(need_client=False)
    # Auch Ordner, die in der App aufgenommen, aber noch nie synchronisiert wurden
    rows = db.all_folders()
    if args.folder:
        folder = resolve_folder(args.folder)
        rows = [r for r in rows if r["folder"] == folder]
        if not rows:
            raise Abort(f"Ordner ist mit keiner Playlist verknüpft: {folder}")
    if not rows:
        ui.info("[muted]Noch keine Ordner synchronisiert.[/]")
        return
    for r in rows:
        files = list(db.files_under(r["folder"]).values())
        groups = summarize(files, db)
        ui.info("")
        ui.info(f"[accent]{r['name']}[/]" + ("" if os.path.isdir(r["folder"]) else "  [warn](Ordner nicht erreichbar)[/]"))
        ui.info(f"[muted]{r['folder']}[/]")
        if r["playlist_id"]:
            url = f"https://open.spotify.com/playlist/{r['playlist_id']}"
            ui.info(f"[link={url}][muted]{url}[/][/link]")
        else:
            ui.info("[muted]Noch keine Playlist – sie entsteht beim ersten Sync.[/]")
        print_summary(groups)
        if args.folder:
            print_files(NOT_FOUND, groups[NOT_FOUND])
            print_files(APPROXIMATE, groups[APPROXIMATE])
            print_files(NOT_ON_SPOTIFY, groups[NOT_ON_SPOTIFY])


def cmd_relink(args) -> None:
    old, new = resolve_folder(args.old), resolve_folder(args.new)
    _, db, _ = setup(need_client=False)
    try:
        moved = relink_folder(db, old, new)
    except UnknownFolderError:
        raise Abort(f"Der Ordner {old} ist mit keiner Playlist verknüpft.") from None
    except RelinkError as e:
        raise Abort(str(e)) from None
    ui.success(f"Verknüpfung aktualisiert ({moved} Dateien übernommen). Jetzt [bold]djsync sync \"{new}\"[/] ausführen.")


# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="djsync", description="Spiegelt lokale Musikordner als Spotify-Playlists.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("setup", help="eigene Spotify-App einrichten und anmelden (einmalig)")
    s.set_defaults(func=cmd_setup)

    s = sub.add_parser("login", help="bei Spotify anmelden")
    s.set_defaults(func=cmd_login)

    s = sub.add_parser("sync", help="Ordner mit seiner Playlist abgleichen")
    s.add_argument("folder", help="Musikordner (auch Windows-Pfad wie D:\\Musik\\Techno)")
    s.add_argument("--name", help="Name der Playlist (Standard: Ordnername)")
    s.add_argument("--yes", "-y", action="store_true", help="ohne Rückfrage übernehmen, kein Review")
    s.add_argument("--dry-run", "-n", action="store_true", help="nur anzeigen, nichts ändern")
    s.add_argument("--no-review", action="store_true", help="Review überspringen")
    s.add_argument(
        "--retry",
        action="store_true",
        help="nicht gefundene und ungefähre Treffer sofort neu suchen (manuelle bleiben)",
    )
    s.set_defaults(func=cmd_sync)

    s = sub.add_parser("review", help="ungefähre und fehlende Treffer prüfen")
    s.add_argument("folder", nargs="?", help="nur diesen Ordner (Standard: alle)")
    s.set_defaults(func=cmd_review)

    s = sub.add_parser("status", help="Übersicht über synchronisierte Ordner")
    s.add_argument("folder", nargs="?", help="Details zu diesem Ordner")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("relink", help="Ordner nach Umbenennen/Verschieben neu verknüpfen")
    s.add_argument("old")
    s.add_argument("new")
    s.set_defaults(func=cmd_relink)
    return p


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    _prepare_console()
    parser = build_parser()
    # Doppelklick (keine Argumente) oder Ordner auf die .exe gezogen → geführter Modus
    if not argv and sys.stdin.isatty():
        return run_interactive(None)
    if len(argv) == 1 and argv[0] not in _commands(parser) and os.path.isdir(normalize_folder(argv[0])):
        return run_interactive(argv[0])
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (Abort, ConfigError, AuthError, SpotifyError) as e:
        ui.error(str(e))
        return 1
    except KeyboardInterrupt:
        ui.err_console.print("\n[muted]Abgebrochen.[/]")
        return 130
    return 0


def _commands(parser: argparse.ArgumentParser) -> set[str]:
    for action in parser._subparsers._group_actions:  # noqa: SLF001
        return set(action.choices)
    return set()


def _prepare_console() -> None:
    """Windows-Konsole: ANSI-Steuerzeichen aktivieren, nicht darstellbare Zeichen ersetzen."""
    for stream in (sys.stdout, sys.stderr):
        try:
            # Windows: umgeleitete Ausgabe sonst in der alten Codepage (✓ → ?); im Konsolenfenster egal
            stream.reconfigure(encoding="utf-8" if IS_WINDOWS else None, errors="replace")
        except (AttributeError, ValueError):
            pass
    if not IS_WINDOWS:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        for handle_id in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
