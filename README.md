# djsync

Spiegelt einen lokalen Musikordner als Spotify-Playlist – ein Ordner, eine Playlist.
Der Ordner ist die einzige Quelle: neue Dateien landen in der Playlist, gelöschte
verschwinden daraus, die neuesten Downloads stehen oben.

## Windows: djsync.exe (ohne Installation)

Für alle, die kein Terminal nutzen wollen – siehe [ANLEITUNG.md](ANLEITUNG.md) zum Weitergeben.

1. `djsync.exe` aus dem neuesten [Release](../../releases/latest) herunterladen.
2. Doppelklick → djsync führt durch die Einrichtung (eigene Spotify-App, Anmeldung).
3. Musikordner ins Fenster ziehen, Enter – oder den Ordner direkt auf `djsync.exe` ziehen.

Alle Befehle unten funktionieren auch mit der .exe (`djsync.exe sync "D:\Musik\House"`).

## Einrichtung (Entwicklung, WSL/Linux)

1. **uv installieren** (falls noch nicht vorhanden): https://docs.astral.sh/uv/
2. **Spotify-App** im [Developer-Dashboard](https://developer.spotify.com/dashboard):
   - Redirect-URI `http://127.0.0.1:8888/callback` eintragen
   - Client-ID kopieren (ein Client-Secret wird dank PKCE nicht benötigt)
   - Hinweis: Apps im Development Mode benötigen ein aktives Premium-Abo des App-Besitzers.
3. **Installieren, Client-ID hinterlegen und anmelden:**
   ```bash
   uv tool install --editable .
   djsync setup      # fragt die Client-ID ab, speichert sie in config.toml und meldet an
   ```
   Alternativ zur Entwicklung: `.env` im Projektordner mit `SPOTIFY_CLIENT_ID=…` (siehe `.env.example`).

## Benutzung

```bash
djsync sync "D:\Musik\Techno 2026-11"      # Windows-Pfade werden nach /mnt/d/… übersetzt
djsync sync /mnt/d/Musik/House --name "House Promos"
djsync sync /mnt/d/Musik/House --dry-run   # nur anzeigen, was sich ändern würde
djsync sync /mnt/d/Musik/House --retry     # nicht gefundene/ungefähre Treffer sofort neu suchen
djsync review [ordner]                      # ungefähre/fehlende Treffer prüfen
djsync status [ordner]                      # Übersicht bzw. Details
djsync relink /mnt/d/Alt /mnt/d/Neu         # nach Umbenennen/Verschieben des Ordners
```

Ablauf von `sync`: Ordner rekursiv scannen → auf Spotify suchen (ISRC, dann Artist/Titel)
→ optional Review → Änderungen anzeigen → nach Bestätigung (`j`) übernehmen.

### Treffer

| Status | Bedeutung |
|---|---|
| ✓ exakt | Artist, Titel, Mix und Dauer (±3 s) stimmen; „Original Mix“ = ohne Angabe |
| ~ ungefähr | andere Version gefunden (z. B. Radio Edit statt Extended) – wird hinzugefügt, im Review markiert |
| ✎ manuell | von dir im Review gewählt oder per Link gesetzt |
| ✗ nicht gefunden | wird nach `retry_missing_days` (oder mit `--retry`) erneut gesucht |
| ⊘ nicht auf Spotify | von dir markiert, wird nie wieder gesucht |

Zuordnungen hängen am Track (ISRC bzw. Artist+Titel+Mix), nicht am Dateinamen –
umbenannte Dateien und Duplikate in anderen Ordnern übernehmen sie automatisch.

### Sicherheit

- djsync entfernt nur Tracks, die es selbst hinzugefügt hat. Von Hand ergänzte Tracks bleiben (am Ende der Playlist).
- Ist der Ordner nicht erreichbar oder leer, die Playlist aber gefüllt, bricht djsync ab.
- Neue Playlists sind privat und heißen „DJSYNC - <Ordnername>“ (bzw. „DJSYNC - <--name>“).

## Daten

| | Linux/WSL | Windows |
|---|---|---|
| Konfiguration inkl. Client-ID | `~/.config/djsync/config.toml` | `%APPDATA%\djsync\config.toml` |
| Datenbank und Login-Token | `~/.local/share/djsync/` | `%APPDATA%\djsync\` |

Die Client-ID wird in dieser Reihenfolge gesucht: Umgebungsvariable `SPOTIFY_CLIENT_ID`,
`.env` im Projektordner, `client_id` in `config.toml`.

## Entwicklung

```bash
uv run pytest
```

### Windows-Release

Ein Versions-Tag (`v0.2.0` usw.) baut per GitHub Actions `djsync.exe` und hängt sie an ein
Release. Der Workflow lässt sich auch manuell unter „Actions“ starten; die .exe liegt dann
als Artefakt am Lauf.

Lokal unter Windows (PowerShell, Python 3.11+): `.\scripts\build_exe.ps1` → `dist\djsync.exe`.
