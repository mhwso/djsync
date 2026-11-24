# djsync – Anleitung

djsync macht aus einem Musikordner auf deinem PC eine Spotify-Playlist. Neue Dateien
im Ordner landen in der Playlist (die neuesten oben), gelöschte verschwinden wieder.

**Du brauchst:** Windows 10/11 und Spotify **Premium**.

## 1. Installieren

1. Auf der [Release-Seite](https://github.com/mhwso/djsync/releases/latest) die Datei
   `djsync-setup-<version>.exe` herunterladen und starten.
2. Den Schritten folgen. Adminrechte sind nicht nötig, djsync wird nur für dich installiert
   und bekommt einen Eintrag im Startmenü.

> Windows zeigt evtl. „Der Computer wurde durch Windows geschützt“. Das liegt daran, dass
> der Installer nicht signiert ist: auf **Weitere Informationen** und dann **Trotzdem
> ausführen** klicken.

**Du hast bisher die `djsync.exe` ohne Installation benutzt?** Dann musst du nichts neu
einrichten: Anmeldung, Einstellungen und alle Zuordnungen liegen unter `%APPDATA%\djsync` und
werden übernommen. Die alte `djsync.exe` kannst du löschen.

## 2. Einrichten (einmalig, ca. 2 Minuten)

djsync über das Startmenü öffnen. Beim ersten Start führt dich das Programm durch die
Einrichtung:

1. Im [Spotify-Developer-Dashboard](https://developer.spotify.com/dashboard) mit deinem
   Spotify-Konto anmelden.
2. **Create app** klicken und eintragen:
   - App name: `djsync`
   - Description: `Playlists aus Musikordnern`
   - Redirect URI: `http://127.0.0.1:8888/callback` (genau so) → **Add**
   - Haken bei **Web API**, Bedingungen akzeptieren, **Save**
3. In der App auf **Settings** gehen, die **Client ID** kopieren und in djsync einfügen.
4. Im Browser den Zugriff für djsync bestätigen.
5. *Optional, aber empfohlen:* **Im Spotify-Player anmelden**. In einem eigenen Fenster von
   djsync meldest du dich noch einmal bei Spotify an, danach **Anmeldung prüfen** klicken.
   Ohne diesen Schritt hörst du Vorschläge im Review nur als 30-Sekunden-Vorschau. Die
   Anmeldung bleibt gespeichert, auch nach einem Neustart.

## 3. Ordner synchronisieren

Musikordner in djsync hinzufügen und synchronisieren. djsync sucht alle Tracks auf Spotify
und zeigt dir vorher, was es an der Playlist ändern würde. Tracks, die nur ungefähr passen
(z. B. Radio Edit statt Extended Mix) oder fehlen, kannst du im Review prüfen. Erst wenn du
bestätigst, entsteht die private Playlist **„DJSYNC - <Ordnername>“**.

Später einfach wieder denselben Ordner synchronisieren: djsync gleicht die Playlist an.

## 4. Im Review anhören und vergleichen

Ob ein Vorschlag wirklich derselbe Mix ist wie deine Datei, hörst du am besten direkt:

- **Leertaste** spielt die lokale Datei ab bzw. pausiert. Sie beginnt an der Startstelle
  (Standard: 60 s), **→** und **←** springen vor und zurück.
- **▶ Anhören** neben einem Vorschlag spielt ihn im eingebetteten Spotify-Player.
- **a** schaltet zwischen deiner Datei und dem Vorschlag um, und zwar an derselben Stelle. So
  hörst du sofort, ob es passt. **v** wählt den nächsten Vorschlag zum Vergleich.
- **Spotify** öffnet den Vorschlag in der Spotify-App bzw. im Browser.

Erscheint „Nur 30-Sekunden-Vorschau“, bist du im Spotify-Player nicht (mehr) angemeldet: über
den Link zur Einrichtung und dort Schritt 5 erledigen. Alle Tastenkürzel zeigt **?** im Review.
Startstelle und Sprungweite lassen sich unter **Einstellungen** ändern.

## Updates

Bei jedem Start schaut djsync nach, ob es eine neuere Version gibt. Wenn ja, erscheint oben
ein Hinweis mit Link zur Release-Seite. Dort den neuen Installer herunterladen und ausführen –
deine Daten bleiben erhalten. Ohne Internet startet djsync ganz normal, nur ohne Hinweis.

## Deinstallieren

In den Windows-Einstellungen unter **Apps** djsync auswählen und deinstallieren. Dabei fragt
djsync, ob auch deine Daten (`%APPDATA%\djsync`: Einstellungen, Anmeldung, Zuordnungen)
gelöscht werden sollen. Wähle **Nein**, wenn du djsync später wieder installieren willst.

## Gut zu wissen

| Zeichen | Bedeutung |
|---|---|
| ✓ exakt | genau diese Version gefunden |
| ~ ungefähr | andere Version gefunden – kommt trotzdem in die Playlist |
| ✗ nicht gefunden | gibt es (noch) nicht auf Spotify, wird später erneut gesucht |

- djsync entfernt nur Tracks, die es selbst hinzugefügt hat.
- Deine Einstellungen liegen unter `%APPDATA%\djsync`. Diesen Ordner löschen = alles zurücksetzen.
