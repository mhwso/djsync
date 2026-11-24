# Sicherheit

## Sicherheitslücken melden

Bitte melde Sicherheitslücken **nicht** über öffentliche Issues, sondern vertraulich über GitHub:
[Sicherheitslücke melden](https://github.com/mhwso/djsync/security/advisories/new) (Reiter „Security“ → „Report a vulnerability“).

Hilfreich sind eine kurze Beschreibung, die betroffene Version und Schritte zum Nachvollziehen. Ich melde mich so bald wie möglich zurück.

## Unterstützte Versionen

Sicherheitskorrekturen gibt es nur für die jeweils neueste Version.

## Hinweise zu Zugangsdaten

djsync nutzt die Spotify-Anmeldung per PKCE ohne Client-Secret. Die Client-ID ist kein Geheimnis. Login-Tokens und die Datenbank liegen nur lokal (`%APPDATA%\djsync` bzw. `~/.local/share/djsync`) und gehören nie ins Repository.
