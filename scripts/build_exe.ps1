# Baut dist\djsync.exe – eine einzelne Datei, kein Python beim Nutzer nötig.
# Aufruf (PowerShell, im Projektordner):  .\scripts\build_exe.ps1
Set-Location (Join-Path $PSScriptRoot "..")

# Native Programme schreiben Statusmeldungen auf stderr – Fehler daher über den Exit-Code prüfen.
function Invoke-Step([string]$Name, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { Write-Error "$Name fehlgeschlagen (Exit-Code $LASTEXITCODE)"; exit 1 }
}

$python = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
Invoke-Step "venv" { & $python -m venv .build-venv }
$venvPython = ".build-venv\Scripts\python.exe"
Invoke-Step "pip" { & $venvPython -m pip install --quiet --upgrade pip }
Invoke-Step "Abhängigkeiten" { & $venvPython -m pip install --quiet . "pyinstaller>=6" }

Invoke-Step "PyInstaller" {
    & $venvPython -m PyInstaller --noconfirm --clean --log-level WARN --onefile --console `
        --name djsync `
        --paths src `
        --collect-submodules djsync `
        src\djsync\__main__.py
}

$help = & dist\djsync.exe --help
if ($LASTEXITCODE -ne 0) { Write-Error "Smoke-Test fehlgeschlagen (Exit-Code $LASTEXITCODE)"; exit 1 }
$help | Select-Object -First 1
Write-Host "`nFertig: dist\djsync.exe"
