<#
Baut djsync lokal unter Windows: dist\djsync\djsync.exe und, falls Inno Setup 6 installiert
ist, den Installer dist\djsync-setup-<version>.exe.

Aufruf in PowerShell im Projektordner:
  .\packaging\build.ps1            # EXE (und Installer) bauen
  .\packaging\build.ps1 -Run       # danach djsync.exe starten
  .\packaging\build.ps1 -Source    # nichts bauen, GUI direkt aus dem Quellcode starten (schnell)

Aus WSL (Projekt im WSL-Dateisystem):
  powershell.exe -ExecutionPolicy Bypass -File "$(wslpath -w packaging/build.ps1)" -Run

Die Python-Umgebung liegt unter %LOCALAPPDATA%\djsync-build, nicht im Projekt. Die gebaute App
nutzt dieselben Daten wie die installierte (%APPDATA%\djsync).
#>
param(
    [switch]$Run,          # nach dem Bauen djsync.exe starten
    [switch]$Source,       # statt zu bauen die GUI aus dem Quellcode starten
    [switch]$NoInstaller   # nur die EXE bauen, auch wenn Inno Setup installiert ist
)
$ErrorActionPreference = "Stop"

function Invoke-Checked {
    & $args[0] @($args | Select-Object -Skip 1)
    if ($LASTEXITCODE -ne 0) { throw "Fehlgeschlagen ($LASTEXITCODE): $($args -join ' ')" }
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$work = Join-Path $env:LOCALAPPDATA "djsync-build"
$python = Join-Path $work "venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Python-Umgebung anlegen: $work\venv"
    $base = Get-Command py -ErrorAction SilentlyContinue
    if ($base) { Invoke-Checked py -3 -m venv "$work\venv" } else { Invoke-Checked python -m venv "$work\venv" }
}

Write-Host "Abhängigkeiten installieren …"
Invoke-Checked $python -m pip install --quiet --disable-pip-version-check . "pyinstaller>=6"
# Gleiche Versionsnummer, neuer Code: djsync selbst immer neu installieren
Invoke-Checked $python -m pip install --quiet --disable-pip-version-check --no-deps --force-reinstall .

if ($Source) {
    Write-Host "GUI aus dem Quellcode starten …"
    Invoke-Checked $python -m djsync.gui
    return
}

$version = (& $python -c "import djsync; print(djsync.__version__)").Trim()
Write-Host "djsync $version bündeln (PyInstaller) …"
Invoke-Checked $python -m PyInstaller --noconfirm --clean --log-level WARN `
    --workpath "$work\pyinstaller" --distpath dist packaging\djsync.spec
Write-Host "→ dist\djsync\djsync.exe"

$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if ($NoInstaller) {
    # nur die EXE
} elseif (Test-Path $iscc) {
    Write-Host "Installer bauen (Inno Setup) …"
    Invoke-Checked $iscc /Q "/DAppVersion=$version" packaging\djsync.iss
    Write-Host "→ dist\djsync-setup-$version.exe"
} else {
    Write-Host "Inno Setup 6 nicht gefunden – kein Installer. Installieren mit: winget install JRSoftware.InnoSetup"
}

if ($Run) { Start-Process "dist\djsync\djsync.exe" }
