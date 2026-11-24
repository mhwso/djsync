# djsync – Anleitung

djsync macht aus einem Musikordner auf deinem PC eine Spotify-Playlist. Neue Dateien
im Ordner landen in der Playlist (die neuesten oben), gelöschte verschwinden wieder.

**Du brauchst:** Windows 10/11 und Spotify **Premium**.

## 1. Herunterladen

`djsync.exe` herunterladen und z. B. auf den Desktop legen. Eine Installation ist nicht nötig.

> Windows zeigt beim ersten Start evtl. „Der Computer wurde durch Windows geschützt“.
> Das liegt daran, dass das Programm nicht signiert ist: auf **Weitere Informationen**
> und dann **Trotzdem ausführen** klicken.

## 2. Einrichten (einmalig, ca. 2 Minuten)

Doppelklick auf `djsync.exe`. Das Programm führt dich durch die Einrichtung:

1. Es öffnet das [Spotify-Developer-Dashboard](https://developer.spotify.com/dashboard).
   Dort mit deinem Spotify-Konto anmelden.
2. **Create app** klicken und eintragen:
   - App name: `djsync`
   - Description: `Playlists aus Musikordnern`
   - Redirect URI: `http://127.0.0.1:8888/callback` (genau so) → **Add**
   - Haken bei **Web API**, Bedingungen akzeptieren, **Save**
3. In der App auf **Settings** gehen, die **Client ID** kopieren und im djsync-Fenster
   einfügen (Rechtsklick fügt ein), Enter.
4. Im Browser den Zugriff für djsync bestätigen.

## 3. Ordner synchronisieren

- Doppelklick auf `djsync.exe`, den Musikordner **in das Fenster ziehen**, Enter.
- Oder den Ordner direkt **auf `djsync.exe` ziehen**.

djsync sucht alle Tracks auf Spotify und zeigt an, was es tun würde. Tracks, die nur
ungefähr passen (z. B. Radio Edit statt Extended Mix) oder fehlen, kannst du prüfen.
Mit `j` bestätigen – dann entsteht die private Playlist **„DJSYNC - <Ordnername>“**.

Später einfach wieder denselben Ordner synchronisieren: djsync gleicht die Playlist an.

## Gut zu wissen

| Zeichen | Bedeutung |
|---|---|
| ✓ exakt | genau diese Version gefunden |
| ~ ungefähr | andere Version gefunden – kommt trotzdem in die Playlist |
| ✗ nicht gefunden | gibt es (noch) nicht auf Spotify, wird später erneut gesucht |

- djsync entfernt nur Tracks, die es selbst hinzugefügt hat.
- Deine Einstellungen liegen unter `%APPDATA%\djsync`. Diesen Ordner löschen = alles zurücksetzen.
