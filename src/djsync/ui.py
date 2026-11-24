"""Terminal-Darstellung: Farben, Ladebalken, Tabellen – zentral an einer Stelle.

Ohne Terminal (umgeleitete Ausgabe, Tests) schaltet rich Farben und Animationen
automatisch ab; es bleibt lesbarer Klartext.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from .models import APPROXIMATE, EXACT, MANUAL, NOT_FOUND, NOT_ON_SPOTIFY

ACCENT = "#1db954"  # Spotify-Grün

COLORS = {
    "accent": ACCENT,
    "exact": "green",
    "approx": "yellow",
    "manual": "cyan",
    "missing": "red",
    "skip": "bright_black",
    "added": "green",
    "removed": "red",
    "muted": "bright_black",
    "warn": "yellow",
}
# Jede Farbe auch fett als „<name>.b“ – Theme-Namen lassen sich nicht mit „bold“ kombinieren
THEME = Theme(
    {name: color for name, color in COLORS.items()}
    | {f"{name}.b": f"bold {color}" for name, color in COLORS.items()}
    | {"accent": f"bold {ACCENT}", "error": "bold red", "ok": "bold green", "title": "bold bright_white"}
)

console = Console(theme=THEME, highlight=False)
err_console = Console(theme=THEME, highlight=False, stderr=True)

# Status → (Symbol, Bezeichnung, Stil)
STATUS = {
    EXACT: ("✓", "exakt", "exact"),
    APPROXIMATE: ("~", "ungefähr", "approx"),
    MANUAL: ("✎", "manuell", "manual"),
    NOT_FOUND: ("✗", "nicht gefunden", "missing"),
    NOT_ON_SPOTIFY: ("⊘", "nicht auf Spotify", "skip"),
}

MAX_LISTED = 20


# ---- Allgemein --------------------------------------------------------------


def banner(version: str) -> None:
    title = Text.assemble(("djsync", "accent"), ("  ·  Musikordner als Spotify-Playlist", "muted"))
    console.print(Panel(title, subtitle=Text(f"v{version}", style="muted"), subtitle_align="right",
                        border_style=ACCENT, expand=False, padding=(0, 2)))


def info(message: str) -> None:
    console.print(message)


def success(message: str) -> None:
    console.print(f"[ok]✓[/] {message}")


def warn(message: str) -> None:
    console.print(f"[warn]![/] {message}")


def error(message: str) -> None:
    err_console.print(f"[error]✗ Fehler:[/] {message}")


def ask(prompt: str) -> str:
    """Eingabe mit farbigem Prompt; wirft EOFError wie input()."""
    return console.input(f"[accent]›[/] {prompt}")


def confirm(prompt: str) -> bool:
    try:
        answer = console.input(f"[accent]?[/] {prompt} [muted]\\[j/N][/] ")
    except EOFError:
        console.print()
        return False
    return answer.strip().lower() in ("j", "ja", "y", "yes")


@contextmanager
def progress(description: str, total: int) -> Iterator:
    """Ladebalken; liefert eine Funktion advance(), die einen Schritt weiterzählt."""
    bar = Progress(
        SpinnerColumn(style=ACCENT),
        TextColumn("{task.description}"),
        BarColumn(complete_style=ACCENT, finished_style=ACCENT, pulse_style="muted"),
        MofNCompleteColumn(),
        TextColumn("[muted]·[/]"),
        TimeRemainingColumn(compact=True),
        console=console,
        transient=True,
    )
    with bar:
        task = bar.add_task(description, total=total)
        yield lambda: bar.advance(task)


@contextmanager
def spinner(message: str) -> Iterator[None]:
    with console.status(message, spinner="dots", spinner_style=ACCENT):
        yield


# ---- Übersicht ----------------------------------------------------------------


def summary(counts: dict[str, int]) -> None:
    """Statuszeile plus farbiger Verteilungsbalken."""
    total = sum(counts.values())
    parts = []
    for status, (symbol, label, style) in STATUS.items():
        n = counts.get(status, 0)
        if n or status in (EXACT, APPROXIMATE, NOT_FOUND):
            parts.append(Text.assemble((f"{symbol} {n}", f"{style}.b"), (f" {label}", style)))
    line = Text("   ").join(parts)

    width = min(console.width - 4, 60)
    bar = Text()
    if total:
        used = 0
        for status, (_, _, style) in STATUS.items():
            n = counts.get(status, 0)
            cells = round(n / total * width) if n else 0
            cells = min(cells, width - used)
            bar.append("━" * cells, style=style)
            used += cells
        if used < width:
            bar.append("━" * (width - used), style="muted")
    console.print()
    console.print(line)
    if total:
        console.print(bar)


def file_list(status: str, names: list[str]) -> None:
    if not names:
        return
    symbol, label, style = STATUS[status]
    console.print()
    console.print(Text.assemble((f"{symbol} {label.capitalize()} ", f"{style}.b"), (f"({len(names)})", "muted")))
    for name in names[:MAX_LISTED]:
        console.print(Text.assemble(("  ", ""), (symbol, style), ("  ", ""), (name, "")))
    if len(names) > MAX_LISTED:
        console.print(f"  [muted]… und {len(names) - MAX_LISTED} weitere[/]")


def plan(new_name: str | None, added: list[str], removed: list[str], reordered: bool, has_changes: bool) -> None:
    rows: list = []
    if new_name:
        rows.append(Text.assemble(("Neue private Playlist ", ""), (f"„{new_name}“", "accent"), (" wird angelegt.", "")))
    if not has_changes:
        rows.append(Text("Playlist ist bereits aktuell.", style="ok"))
    if added:
        rows.append(Text(f"+ {len(added)} hinzufügen", style="added.b"))
        rows += [Text(f"   + {n}", style="added") for n in added[:MAX_LISTED]]
        if len(added) > MAX_LISTED:
            rows.append(Text(f"   … und {len(added) - MAX_LISTED} weitere", style="muted"))
    if removed:
        rows.append(Text(f"− {len(removed)} entfernen (Datei nicht mehr im Ordner)", style="removed.b"))
        rows += [Text(f"   − {n}", style="removed") for n in removed[:MAX_LISTED]]
    if reordered:
        rows.append(Text("↕ Reihenfolge wird angepasst (neueste Dateien oben)", style="manual"))
    console.print()
    console.print(Panel(Group(*rows), title="[title]Geplante Änderungen[/]", title_align="left",
                        border_style="muted", padding=(0, 1)))


def playlist_link(playlist_id: str) -> None:
    url = f"https://open.spotify.com/playlist/{playlist_id}"
    console.print()
    console.print(f"[ok]✓ Fertig.[/] Playlist: [link={url}][accent]{url}[/][/link]")


# ---- Review -------------------------------------------------------------------


def review_header(count: int) -> None:
    console.print()
    console.rule(f"[title]Review[/] [muted]· {count} Tracks prüfen[/]", style="muted")


def review_track(index: int, count: int, status: str, filename: str, tags: str, duration: str,
                 candidates: list[tuple[str, str, str, float, bool, bool]]) -> None:
    """candidates: (Artist, Titel, Dauer, Score, Dauer passt, aktuell gewählt)."""
    symbol, label, style = STATUS[status]
    table = Table(box=None, show_header=True, header_style="muted", pad_edge=False, padding=(0, 1))
    table.add_column("#", justify="right", style="accent")
    table.add_column("Spotify-Treffer")
    table.add_column("Dauer", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("")
    for n, (artists, name, dur, score, dur_ok, current) in enumerate(candidates, 1):
        score_style = "exact" if score >= 0.85 else "approx" if score >= 0.7 else "muted"
        table.add_row(
            str(n),
            Text.assemble((artists, "bold"), (" – ", "muted"), (name, "")),
            Text(dur, style="" if dur_ok else "missing"),
            Text(f"{score:.2f}", style=score_style),
            Text("← aktuell", style="accent") if current else "",
        )
    head = Text.assemble((filename, "bold"), ("\n", ""), ("Tags: ", "muted"), (tags, ""), ("  ", ""), (duration, "muted"))
    body = Group(head, Text(""), table) if candidates else Group(head, Text("\nKeine Kandidaten gefunden.", style="muted"))
    console.print()
    console.print(Panel(body, title=f"[{style}]{symbol} {label}[/]", title_align="left",
                        subtitle=f"[muted]{index}/{count}[/]", subtitle_align="right",
                        border_style=style, padding=(0, 1)))


# ---- Einrichtung ----------------------------------------------------------------


def setup_steps(dashboard_url: str, redirect_uri: str) -> None:
    steps = Table.grid(padding=(0, 1))
    steps.add_column(style="accent", justify="right")
    steps.add_column()
    steps.add_row("1", f"Im Browser öffnet sich gleich [link={dashboard_url}]{dashboard_url}[/link].\n"
                       "Melde dich dort mit deinem Spotify-Konto an.")
    steps.add_row("2", "Klicke auf [bold]Create app[/] und trage ein:\n"
                       "  App name:     [bold]djsync[/]\n"
                       "  Description:  [bold]Playlists aus Musikordnern[/]\n"
                       f"  Redirect URI: [accent]{redirect_uri}[/]  [muted](genau so, dann „Add“)[/]")
    steps.add_row("3", "Bei „Which API/SDKs are you planning to use?“ [bold]Web API[/] anhaken,\n"
                       "den Bedingungen zustimmen und [bold]Save[/] klicken.")
    steps.add_row("4", "In der App auf [bold]Settings[/] gehen und die [bold]Client ID[/] kopieren\n"
                       "[muted](32 Zeichen, z. B. 3f2a…). Ein „Client secret“ wird nicht gebraucht.[/]")
    intro = Text("djsync braucht Zugriff auf deine Spotify-Playlists. Dafür legst du im Spotify-Developer-"
                 "Dashboard eine kleine „App“ an. Voraussetzung: Spotify Premium.\n")
    console.print()
    console.print(Panel(Group(intro, steps), title="[bold]Einrichtung[/] [muted]· einmalig, ca. 2 Minuten[/]",
                        title_align="left", border_style=ACCENT, padding=(1, 2)))
