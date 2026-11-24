# Vorschläge über den eingebetteten Spotify-Player anhören

Spotify liefert für Apps im Development Mode keine `preview_url` mehr. Spotify-Vorschläge werden deshalb im eingebetteten Spotify-Player (Embed-iframe, gesteuert über die iFrame-API) abgespielt, mit „In Spotify öffnen“ als Alternative. Damit ganze Tracks laufen und der A/B-Vergleich an gleicher Position mit der lokalen Datei funktioniert, meldet sich der Nutzer während der Einrichtung im eingebetteten Player an.

## Considered Options

- **Spotify Connect** (Fernsteuerung eines laufenden Spotify-Clients): abgelehnt, weil es einen zusätzlichen Scope und eine erneute Anmeldung erfordert, einen laufenden Client voraussetzt und das gerade Gehörte unterbricht.

## Consequences

Ob der eingebettete Player in WebView2 ganze Tracks abspielt (DRM), ist ungeklärt und wird vor der Umsetzung mit einem Prototyp geprüft. Gelingt das nicht, wird die Abspielmethode neu entschieden.
