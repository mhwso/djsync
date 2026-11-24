# GUI mit pywebview und HTML ohne Build-Schritt

Die Windows-GUI entsteht in Python mit pywebview im systemeigenen Edge WebView2. Die Oberfläche ist reines HTML/CSS/JavaScript ohne Node-Build. Wir bleiben damit im bestehenden Python-Kern, der Installer bleibt klein (WebView2 ist auf Windows 10/11 vorhanden), und der eingebettete Spotify-Player braucht ohnehin eine Web-Ansicht.

## Considered Options

- **PySide6/Qt mit Qt WebEngine**: native Widgets, aber ein eigenes Chromium bläht den Installer auf über 150 MB auf.
- **Frontend-Framework (Svelte, React, Vue)**: abgelehnt, weil dafür eine Node-Toolchain im Build nötig wäre.
