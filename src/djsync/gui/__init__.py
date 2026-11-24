"""Windows-GUI von djsync (ADR 0001): pywebview mit statischer HTML/CSS/JS-Oberfläche.

Die Oberfläche spricht nur mit dem API-Objekt aus `djsync.gui.api`. pywebview wird erst in
`djsync.gui.app` beim Start des Fensters importiert, damit Tests ohne pywebview auskommen.
"""
