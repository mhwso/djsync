# PyInstaller-Spec für die Windows-GUI: Fenster-App ohne Konsole, als Ordner (onedir).
#
# Aufruf (Windows, im Projektordner, djsync per `pip install .` installiert):
#   python -m PyInstaller --noconfirm --clean packaging\djsync.spec
# Ergebnis: dist\djsync\djsync.exe samt Laufzeitdateien – daraus baut djsync.iss den Installer.
#
# Ordner statt Einzeldatei: startet schneller (kein Entpacken bei jedem Start), und der
# Installer verteilt ohnehin mehrere Dateien.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Die Oberfläche (djsync/gui/static) liegt als Paketdaten neben dem Code.
# pywebview bringt eigene PyInstaller-Hooks mit (WebView2-DLLs, JS-Dateien).
datas = collect_data_files("djsync")
hiddenimports = collect_submodules("djsync")

a = Analysis(
    ["djsync_gui.py"],
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="djsync",
    console=False,  # Fenster-App, kein Konsolenfenster
    upx=False,  # UPX-gepackte Dateien lösen häufiger Virenscanner-Fehlalarme aus
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="djsync",
    upx=False,
)
