from __future__ import annotations

import argparse
import os
import sys

from . import ui
from .auth import Auth, AuthError
from .config import DB_FILE, IS_WINDOWS, SCOPES, TOKEN_FILE, ConfigError, load_config
from .db import Database
from .filenames import normalize_folder
from .models import APPROXIMATE, NOT_FOUND, NOT_ON_SPOTIFY, LocalFile
from .plan import Plan
from .review import pending_reviews, run_review
from .scanner import scan_folder
from .spotify import SpotifyClient, SpotifyError
from .sync import (
    build_plan,
    description_text,
    match_files,
    playlist_files,
    playlist_name,
    summarize,
)
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


def cmd_sync(args) -> None:
    folder = resolve_folder(args.folder)
    if not os.path.isdir(folder):
        raise Abort(f"Ordner nicht erreichbar: {folder}\nIst das Laufwerk eingebunden?")
    cfg, db, client = setup()

    ui.info(f"[muted]Ordner[/]  {folder}")
    files = scan_folder(folder, db, cfg.extensions)

    row = db.get_playlist(folder)
    playlist_id = row["playlist_id"] if row else None
    with ui.spinner("Lade Playlist von Spotify …"):
        playlist = client.get_playlist(playlist_id) if playlist_id else None
        if playlist_id and playlist is None:
            playlist_id = None
        current = client.playlist_track_ids(playlist_id) if playlist_id else []
    if row and playlist_id is None:
        ui.warn("Die verknüpfte Playlist existiert nicht mehr und wird neu angelegt.")

    if not files and playlist_id and db.managed_tracks(playlist_id) & set(current):
        raise Abort(
            "Der Ordner enthält keine Audiodateien, die Playlist aber schon.\n"
            "Abbruch, um die Playlist nicht versehentlich zu leeren."
        )

    match_files(files, db, client, cfg, retry=args.retry)

    pending = pending_reviews(files, db)
    interactive = sys.stdin.isatty() and not (args.yes or args.dry_run or args.no_review)
    if pending and interactive:
        ui.info("")
        if confirm(f"{len(pending)} Tracks sind ungefähr oder nicht gefunden. Jetzt prüfen?"):
            run_review(pending, db, client, duration_tolerance_ms=cfg.duration_tolerance_ms)

    groups = summarize(files, db)
    print_summary(groups)
    if not interactive or not pending:
        print_files(NOT_FOUND, groups[NOT_FOUND])
        print_files(APPROXIMATE, groups[APPROXIMATE])

    plan = build_plan(files, db, current, playlist_id)
    labels = {sid: os.path.basename(f.path) for f, sid in playlist_files(files, db)}
    new_name = playlist_name(args.name or os.path.basename(folder)) if playlist_id is None else None
    print_plan(plan, labels, new_name)

    if args.dry_run:
        ui.info("\n[muted]Probelauf – auf Spotify wurde nichts geändert.[/]")
        return

    needs_write = plan.has_changes or playlist_id is None
    if needs_write and not args.yes:
        ui.info("")
        if not confirm("Änderungen auf Spotify übernehmen?"):
            ui.info("[muted]Abgebrochen – nichts geändert.[/]")
            return

    with ui.spinner("Übertrage Änderungen zu Spotify …"):
        if playlist_id is None:
            playlist_id = client.create_playlist(new_name, description_text(), public=False)
            db.save_playlist(folder, playlist_id, new_name)
            db.commit()
        else:
            wanted = playlist_name(args.name) if args.name else None
            rename = wanted if wanted and wanted != (playlist or {}).get("name") else None
            client.update_playlist(playlist_id, name=rename, description=description_text())

        if plan.has_changes:
            client.replace_playlist_items(playlist_id, plan.final)
        db.set_managed_tracks(playlist_id, plan.desired)
        db.commit()
    ui.playlist_link(playlist_id)


def _review_scope(db: Database, folder_arg: str | None) -> list[tuple[LocalFile, str | None]]:
    folders = [resolve_folder(folder_arg)] if folder_arg else [r["folder"] for r in db.all_playlists()]
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
    rows = db.all_playlists()
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
        url = f"https://open.spotify.com/playlist/{r['playlist_id']}"
        ui.info("")
        ui.info(f"[accent]{r['name']}[/]" + ("" if os.path.isdir(r["folder"]) else "  [warn](Ordner nicht erreichbar)[/]"))
        ui.info(f"[muted]{r['folder']}[/]")
        ui.info(f"[link={url}][muted]{url}[/][/link]")
        print_summary(groups)
        if args.folder:
            print_files(NOT_FOUND, groups[NOT_FOUND])
            print_files(APPROXIMATE, groups[APPROXIMATE])
            print_files(NOT_ON_SPOTIFY, groups[NOT_ON_SPOTIFY])


def cmd_relink(args) -> None:
    old, new = resolve_folder(args.old), resolve_folder(args.new)
    if not os.path.isdir(new):
        raise Abort(f"Neuer Ordner nicht erreichbar: {new}")
    _, db, _ = setup(need_client=False)
    if db.get_playlist(new):
        raise Abort(f"Der Ordner {new} ist bereits mit einer Playlist verknüpft.")
    if not db.relink_playlist(old, new):
        raise Abort(f"Der Ordner {old} ist mit keiner Playlist verknüpft.")
    moved = db.move_files(old, new)
    db.commit()
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
