# Vorschläge über den eingebetteten Spotify-Player anhören

Spotify liefert für Apps im Development Mode keine `preview_url` mehr. Spotify-Vorschläge werden deshalb im eingebetteten Spotify-Player (Embed-iframe, gesteuert über die iFrame-API) abgespielt, mit „In Spotify öffnen“ als Alternative. Damit ganze Tracks laufen und der A/B-Vergleich an gleicher Position mit der lokalen Datei funktioniert, meldet sich der Nutzer während der Einrichtung im eingebetteten Player an.

## Considered Options

- **Spotify Connect** (Fernsteuerung eines laufenden Spotify-Clients): abgelehnt, weil es einen zusätzlichen Scope und eine erneute Anmeldung erfordert, einen laufenden Client voraussetzt und das gerade Gehörte unterbricht.

## Consequences

Ein Prototyp (#8) hat bestätigt, dass der eingebettete Player in WebView2 nach der Anmeldung ganze Tracks abspielt und sich über die iFrame-API steuern lässt (Track laden, Abspielen, Pausieren, Springen, Position auslesen). Damit die Anmeldung einen Neustart übersteht, braucht das Fenster ein festes WebView2-Profil (`private_mode=False` mit eigenem `storage_path`). Die Anmeldung läuft in einem pywebview-Fenster mit demselben Profil, weil pywebview Pop-ups sonst im externen Browser öffnet.
