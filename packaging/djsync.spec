# PyInstaller-Spec für die Windows-GUI: Fenster-App ohne Konsole, als Ordner (onedir).
#
# Aufruf (Windows, im Projektordner, djsync per `pip install .` installiert):
#   python -m PyInstaller --noconfirm --clean packaging\djsync.spec
# Ergebnis: dist\djsync\djsync.exe samt Laufzeitdateien – daraus baut djsync.iss den Installer.
#
# Ordner statt Einzeldatei: startet schneller (kein Entpacken bei jedem Start), und der
# Installer verteilt ohnehin mehrere Dateien.

import re

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

import djsync

# Die Oberfläche (djsync/gui/static) liegt als Paketdaten neben dem Code.
# pywebview bringt eigene PyInstaller-Hooks mit (WebView2-DLLs, JS-Dateien).
datas = collect_data_files("djsync")
hiddenimports = collect_submodules("djsync")

# Versionsinfos in der djsync.exe: SignPath prüft beim Signieren Produktname und -version.
version = djsync.__version__
numbers = tuple(int(n) for n in re.findall(r"\d+", version)[:4])
numbers += (0,) * (4 - len(numbers))
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040704B0",  # Deutsch, Unicode
                    [
                        StringStruct("CompanyName", "mhwso"),
                        StringStruct("FileDescription", "djsync"),
                        StringStruct("FileVersion", version),
                        StringStruct("InternalName", "djsync"),
                        StringStruct("LegalCopyright", "GPL-3.0-or-later"),
                        StringStruct("OriginalFilename", "djsync.exe"),
                        StringStruct("ProductName", "djsync"),
                        StringStruct("ProductVersion", version),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [0x0407, 1200])]),
    ],
)

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
    version=version_info,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="djsync",
    upx=False,
)
