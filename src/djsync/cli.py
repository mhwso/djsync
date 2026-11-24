from __future__ import annotations

import argparse
import os
import sys

from .auth import Auth, AuthError
from .config import DB_FILE, SCOPES, TOKEN_FILE, ConfigError, load_config
from .db import Database
from .filenames import windows_to_wsl
from .models import APPROXIMATE, EXACT, MANUAL, NOT_FOUND, NOT_ON_SPOTIFY, LocalFile
from .plan import Plan
from .review import pending_reviews, run_review
from .scanner import scan_folder
from .spotify import SpotifyClient, SpotifyError
from .sync import build_plan, description_text, match_files, playlist_files, playlist_name, summarize

MAX_LISTED = 20


class Abort(Exception):
    pass


# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------


def resolve_folder(arg: str) -> str:
    path = os.path.abspath(os.path.expanduser(windows_to_wsl(arg)))
    return path.rstrip("/") or "/"


def setup(need_client: bool = True):
    db = Database(DB_FILE)
    if not need_client:
        return None, db, None
    cfg = load_config()
    client = SpotifyClient(Auth(cfg.client_id, cfg.redirect_uri, SCOPES, TOKEN_FILE))
    return cfg, db, client


def confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ("j", "ja", "y", "yes")
    except EOFError:
        print()
        return False


def print_summary(groups: dict[str, list[LocalFile]]) -> None:
    print(
        f"✓ exakt {len(groups[EXACT])} · ~ ungefähr {len(groups[APPROXIMATE])} · "
        f"✎ manuell {len(groups[MANUAL])} · ✗ nicht gefunden {len(groups[NOT_FOUND])} · "
        f"⊘ nicht auf Spotify {len(groups[NOT_ON_SPOTIFY])}"
    )


def print_files(title: str, files: list[LocalFile]) -> None:
    if not files:
        return
    print(f"\n{title} ({len(files)}):")
    for f in files[:MAX_LISTED]:
        print(f"  {os.path.basename(f.path)}")
    if len(files) > MAX_LISTED:
        print(f"  … und {len(files) - MAX_LISTED} weitere")


def print_plan(plan: Plan, labels: dict[str, str], new_name: str | None) -> None:
    print()
    if new_name:
        print(f"Neue private Playlist „{new_name}“ wird angelegt.")
    if not plan.has_changes:
        print("Playlist ist bereits aktuell.")
        return
    if plan.added:
        print(f"+ {len(plan.added)} hinzufügen")
        for t in plan.added[:MAX_LISTED]:
            print(f"    + {labels.get(t, t)}")
        if len(plan.added) > MAX_LISTED:
            print(f"    … und {len(plan.added) - MAX_LISTED} weitere")
    if plan.removed:
        print(f"− {len(plan.removed)} entfernen (Datei nicht mehr im Ordner)")
        for t in plan.removed[:MAX_LISTED]:
            print(f"    − {labels.get(t, 'spotify:track:' + t)}")
    if plan.reordered:
        print("↕ Reihenfolge wird angepasst (neueste Dateien oben)")


# --------------------------------------------------------------------------
# Befehle
# --------------------------------------------------------------------------


def cmd_login(args) -> None:
    cfg = load_config()
    auth = Auth(cfg.client_id, cfg.redirect_uri, SCOPES, TOKEN_FILE)
    auth.login()
    client = SpotifyClient(auth)
    me = client._request("GET", "/me")
    print(f"Angemeldet als {me.get('display_name') or me.get('id')}.")


def cmd_sync(args) -> None:
    folder = resolve_folder(args.folder)
    if not os.path.isdir(folder):
        raise Abort(f"Ordner nicht erreichbar: {folder}\nIst das Laufwerk eingebunden?")
    cfg, db, client = setup()

    files = scan_folder(folder, db, cfg.extensions)

    row = db.get_playlist(folder)
    playlist_id = row["playlist_id"] if row else None
    playlist = client.get_playlist(playlist_id) if playlist_id else None
    if playlist_id and playlist is None:
        print("Hinweis: Die verknüpfte Playlist existiert nicht mehr und wird neu angelegt.")
        playlist_id = None
    current = client.playlist_track_ids(playlist_id) if playlist_id else []

    if not files and playlist_id and db.managed_tracks(playlist_id) & set(current):
        raise Abort(
            "Der Ordner enthält keine Audiodateien, die Playlist aber schon.\n"
            "Abbruch, um die Playlist nicht versehentlich zu leeren."
        )

    match_files(files, db, client, cfg, retry=args.retry)

    pending = pending_reviews(files, db)
    interactive = sys.stdin.isatty() and not (args.yes or args.dry_run or args.no_review)
    if pending and interactive:
        if confirm(f"\n{len(pending)} Tracks sind ungefähr oder nicht gefunden. Jetzt prüfen? [j/N] "):
            run_review(pending, db, client, duration_tolerance_ms=cfg.duration_tolerance_ms)

    groups = summarize(files, db)
    print()
    print_summary(groups)
    if not interactive or not pending:
        print_files("Nicht gefunden", groups[NOT_FOUND])
        print_files("Ungefähre Treffer", groups[APPROXIMATE])

    plan = build_plan(files, db, current, playlist_id)
    labels = {sid: os.path.basename(f.path) for f, sid in playlist_files(files, db)}
    new_name = playlist_name(args.name or os.path.basename(folder)) if playlist_id is None else None
    print_plan(plan, labels, new_name)

    if args.dry_run:
        print("\n(Probelauf – auf Spotify wurde nichts geändert.)")
        return

    needs_write = plan.has_changes or playlist_id is None
    if needs_write and not args.yes and not confirm("\nÄnderungen auf Spotify übernehmen? [j/N] "):
        print("Abgebrochen – nichts geändert.")
        return

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
    print(f"Fertig. Playlist: https://open.spotify.com/playlist/{playlist_id}")


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
        print(f"{changed} Zuordnungen geändert. Mit `djsync sync <ordner>` in die Playlist übernehmen.")


def cmd_status(args) -> None:
    _, db, _ = setup(need_client=False)
    rows = db.all_playlists()
    if args.folder:
        folder = resolve_folder(args.folder)
        rows = [r for r in rows if r["folder"] == folder]
        if not rows:
            raise Abort(f"Ordner ist mit keiner Playlist verknüpft: {folder}")
    if not rows:
        print("Noch keine Ordner synchronisiert.")
        return
    for r in rows:
        files = list(db.files_under(r["folder"]).values())
        groups = summarize(files, db)
        reachable = "" if os.path.isdir(r["folder"]) else "  (Ordner nicht erreichbar)"
        print(f"\n{r['name']}{reachable}")
        print(f"  {r['folder']}")
        print(f"  https://open.spotify.com/playlist/{r['playlist_id']}")
        print("  ", end="")
        print_summary(groups)
        if args.folder:
            print_files("Nicht gefunden", groups[NOT_FOUND])
            print_files("Ungefähre Treffer", groups[APPROXIMATE])
            print_files("Nicht auf Spotify", groups[NOT_ON_SPOTIFY])


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
    print(f"Verknüpfung aktualisiert ({moved} Dateien übernommen). Jetzt `djsync sync \"{new}\"` ausführen.")


# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="djsync", description="Spiegelt lokale Musikordner als Spotify-Playlists.")
    sub = p.add_subparsers(dest="command", required=True)

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
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (Abort, ConfigError, AuthError, SpotifyError) as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
