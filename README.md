<div align="center">

# 🎧 djsync

**Spiegelt lokale Musikordner als Spotify-Playlists – ein Ordner, eine Playlist.**

[![Neueste Version](https://img.shields.io/github/v/release/mhwso/djsync?label=Version&color=1DB954)](https://github.com/mhwso/djsync/releases/latest)
[![Veröffentlicht](https://img.shields.io/github/release-date/mhwso/djsync?label=ver%C3%B6ffentlicht)](https://github.com/mhwso/djsync/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/mhwso/djsync/total?label=Downloads)](https://github.com/mhwso/djsync/releases)
[![Tests](https://img.shields.io/github/actions/workflow/status/mhwso/djsync/ci.yml?branch=main&label=Tests)](https://github.com/mhwso/djsync/actions/workflows/ci.yml)
[![Windows-Release](https://img.shields.io/github/actions/workflow/status/mhwso/djsync/release.yml?label=Windows-Build)](https://github.com/mhwso/djsync/actions/workflows/release.yml)
<br>
[![Python](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fmhwso%2Fdjsync%2Fmain%2Fpyproject.toml&label=Python)](pyproject.toml)
[![Plattform](https://img.shields.io/badge/Plattform-Windows%20%7C%20Linux%2FWSL-informational)](#installation)
[![Spotify](https://img.shields.io/badge/Spotify-Web%20API-1DB954?logo=spotify&logoColor=white)](https://developer.spotify.com/documentation/web-api)
[![Lizenz](https://img.shields.io/badge/Lizenz-GPL--3.0--or--later-blue)](LICENSE)
[![Letzter Commit](https://img.shields.io/github/last-commit/mhwso/djsync?label=letzter%20Commit)](https://github.com/mhwso/djsync/commits/main)

[Herunterladen](https://github.com/mhwso/djsync/releases/latest) · [Anleitung](ANLEITUNG.md) · [Fehler melden](https://github.com/mhwso/djsync/issues) · [Sicherheit](SECURITY.md)

</div>

---

Der Ordner ist die einzige Quelle: neue Dateien landen in der Playlist, gelöschte
verschwinden daraus, die neuesten Downloads stehen oben.

## ✨ Funktionen

- **Ein Ordner, eine Playlist** – rekursiver Scan, neueste Dateien zuerst
- **Treffsichere Suche** – zuerst per ISRC, dann über Artist, Titel und Mix inklusive Dauer
- **Review** für unsichere Treffer – Vorschlag wählen, Spotify-Link einfügen oder als „nicht auf Spotify“ markieren
- **Änderungsplan vor jedem Schreiben** – nichts passiert ohne Bestätigung
- **Sicher** – entfernt nur selbst hinzugefügte Tracks, bricht bei leerem oder fehlendem Ordner ab
- **Relink** nach dem Verschieben oder Umbenennen eines Ordners

<a id="installation"></a>

## 🪟 Windows: djsync.exe (ohne Installation)

Für alle, die kein Terminal nutzen wollen – siehe [ANLEITUNG.md](ANLEITUNG.md) zum Weitergeben.

1. `djsync.exe` aus dem neuesten [Release](../../releases/latest) herunterladen.
2. Doppelklick → djsync führt durch die Einrichtung (eigene Spotify-App, Anmeldung).
3. Musikordner ins Fenster ziehen, Enter – oder den Ordner direkt auf `djsync.exe` ziehen.

Alle Befehle unten funktionieren auch mit der .exe (`djsync.exe sync "D:\Musik\House"`).

## 🐧 Einrichtung (Entwicklung, WSL/Linux)

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

## 🚀 Benutzung

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

### 🎯 Treffer

| Status | Bedeutung |
|---|---|
| ✓ exakt | Artist, Titel, Mix und Dauer (±3 s) stimmen; „Original Mix“ = ohne Angabe |
| ~ ungefähr | andere Version gefunden (z. B. Radio Edit statt Extended) – wird hinzugefügt, im Review markiert |
| ✎ manuell | von dir im Review gewählt oder per Link gesetzt |
| ✗ nicht gefunden | wird nach `retry_missing_days` (oder mit `--retry`) erneut gesucht |
| ⊘ nicht auf Spotify | von dir markiert, wird nie wieder gesucht |

Zuordnungen hängen am Track (ISRC bzw. Artist+Titel+Mix), nicht am Dateinamen –
umbenannte Dateien und Duplikate in anderen Ordnern übernehmen sie automatisch.

### 🛡️ Sicherheit

- djsync entfernt nur Tracks, die es selbst hinzugefügt hat. Von Hand ergänzte Tracks bleiben (am Ende der Playlist).
- Ist der Ordner nicht erreichbar oder leer, die Playlist aber gefüllt, bricht djsync ab.
- Neue Playlists sind privat und heißen „DJSYNC - <Ordnername>“ (bzw. „DJSYNC - <--name>“).

## 💾 Daten

| | Linux/WSL | Windows |
|---|---|---|
| Konfiguration inkl. Client-ID | `~/.config/djsync/config.toml` | `%APPDATA%\djsync\config.toml` |
| Datenbank und Login-Token | `~/.local/share/djsync/` | `%APPDATA%\djsync\` |

Die Client-ID wird in dieser Reihenfolge gesucht: Umgebungsvariable `SPOTIFY_CLIENT_ID`,
`.env` im Projektordner, `client_id` in `config.toml`.

## 🛠️ Entwicklung

```bash
uv run pytest
```

### Windows-Release

Ein Versions-Tag (`v0.2.0` usw.) baut per GitHub Actions `djsync.exe` und hängt sie an ein
Release. Der Workflow lässt sich auch manuell unter „Actions“ starten; die .exe liegt dann
als Artefakt am Lauf.

Lokal unter Windows (PowerShell, Python 3.11+): `.\scripts\build_exe.ps1` → `dist\djsync.exe`.

## 📄 Lizenz

djsync steht unter der [GNU General Public License v3.0 oder später](LICENSE) (`GPL-3.0-or-later`).
Die Windows-Version enthält unter anderem [mutagen](https://github.com/quodlibet/mutagen) (GPL-2.0-or-later).
