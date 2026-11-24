# djsync

djsync spiegelt einen lokalen Musikordner als Spotify-Playlist. Der Ordner ist die einzige Quelle der Wahrheit.

## Language

### Ordner und Playlist

**Ordner**:
Ein lokales Verzeichnis mit Audiodateien, das djsync als genau eine Playlist spiegelt.
_Avoid_: Quelle, Bibliothek

**Playlist**:
Die Spotify-Playlist, die zu genau einem Ordner gehört. Ihr Name ist frei wählbar und standardmäßig „DJSYNC - <Ordnername>“.

**Sync**:
Der Durchlauf, der einen Ordner einliest, Tracks auf Spotify sucht und die Playlist nach Bestätigung des Änderungsplans angleicht.

**Änderungsplan**:
Die vor dem Übernehmen angezeigte Liste der Tracks, die in die Playlist kommen, aus ihr verschwinden oder neu sortiert werden.
_Avoid_: Diff, Plan

### Zuordnung

**Track**:
Ein Musikstück, erkannt über seine ISRC bzw. Artist, Titel und Mix. Mehrere Dateien können derselbe Track sein.
_Avoid_: Song, Datei (wenn das Musikstück gemeint ist)

**Zuordnung**:
Die Verknüpfung eines Tracks mit einem Spotify-Track samt Treffer-Status. Sie gilt für den Track in allen Ordnern.
_Avoid_: Match, Mapping

**Treffer-Status**:
Der Zustand einer Zuordnung: exakt, ungefähr, manuell, nicht gefunden oder nicht auf Spotify.

**Vorschlag**:
Ein Spotify-Track, der bei der Suche als mögliche Zuordnung für einen Track gefunden wurde.
_Avoid_: Kandidat (im Code `Candidate`)

**Offen**:
Ein Track, dessen Zuordnung noch niemand geprüft hat: Treffer-Status „ungefähr“ oder „nicht gefunden“.
_Avoid_: unsicher, unklar

**Entschieden**:
Ein Track, dessen Zuordnung der Nutzer festgelegt hat: Treffer-Status „manuell“ oder „nicht auf Spotify“. Er lässt sich auf „offen“ zurücksetzen.

### Review

**Review**:
Das Prüfen und Festlegen der Zuordnungen der Tracks eines Ordners. Es beschränkt sich nicht auf offene Tracks, sondern umfasst jeden Treffer-Status.
_Avoid_: Prüfung, Kontrolle

**Startstelle**:
Die feste Position im Track, an der das Anhören beginnt.

**Sprungweite**:
Die Sekunden, um die beim Anhören per Taste vorgesprungen wird.

**Relink**:
Das Verknüpfen eines verschobenen oder umbenannten Ordners mit seinem neuen Pfad. Playlist und Zuordnungen bleiben erhalten.
