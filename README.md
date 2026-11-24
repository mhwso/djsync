# djsync

Spiegelt einen lokalen Musikordner als Spotify-Playlist – ein Ordner, eine Playlist.
Der Ordner ist die einzige Quelle: neue Dateien landen in der Playlist, gelöschte
verschwinden daraus, die neuesten Downloads stehen oben.

## Einrichtung

1. **uv installieren** (falls noch nicht vorhanden): https://docs.astral.sh/uv/
2. **Spotify-App** im [Developer-Dashboard](https://developer.spotify.com/dashboard):
   - Redirect-URI `http://127.0.0.1:8888/callback` eintragen
   - Client-ID kopieren (ein Client-Secret wird dank PKCE nicht benötigt)
   - Hinweis: Apps im Development Mode benötigen ein aktives Premium-Abo des App-Besitzers.
3. **Client-ID hinterlegen** – in `.env` im Projektordner (wird von git ignoriert):
   ```bash
   cp .env.example .env   # dann SPOTIFY_CLIENT_ID eintragen
   ```
   Optional: `config.example.toml` nach `~/.config/djsync/config.toml` kopieren.
4. **Installieren und anmelden:**
   ```bash
   uv tool install --editable .
   djsync login
   ```

## Benutzung

```bash
djsync sync "D:\Musik\Techno 2026-11"      # Windows-Pfade werden nach /mnt/d/… übersetzt
djsync sync /mnt/d/Musik/House --name "House Promos"
djsync sync /mnt/d/Musik/House --dry-run   # nur anzeigen, was sich ändern würde
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
| ✗ nicht gefunden | wird nach `retry_missing_days` erneut gesucht |
| ⊘ nicht auf Spotify | von dir markiert, wird nie wieder gesucht |

Zuordnungen hängen am Track (ISRC bzw. Artist+Titel+Mix), nicht am Dateinamen –
umbenannte Dateien und Duplikate in anderen Ordnern übernehmen sie automatisch.

### Sicherheit

- djsync entfernt nur Tracks, die es selbst hinzugefügt hat. Von Hand ergänzte Tracks bleiben (am Ende der Playlist).
- Ist der Ordner nicht erreichbar oder leer, die Playlist aber gefüllt, bricht djsync ab.
- Neue Playlists sind privat.

## Daten

- Client-ID: `.env` im Projektordner
- Konfiguration: `~/.config/djsync/config.toml`
- Datenbank und Login-Token: `~/.local/share/djsync/`

## Entwicklung

```bash
uv run pytest
```
