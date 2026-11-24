#!/usr/bin/env bash
# Aus WSL: ruft packaging/build.ps1 unter Windows auf und reicht alle Optionen durch.
#
#   packaging/build.sh            # djsync.exe (+ Installer, falls Inno Setup installiert) bauen
#   packaging/build.sh -Run       # bauen und djsync.exe starten
#   packaging/build.sh -Source    # nichts bauen, GUI direkt aus dem Quellcode starten
set -euo pipefail

if ! command -v powershell.exe >/dev/null; then
    echo "powershell.exe nicht gefunden – das Skript ist für WSL gedacht." >&2
    exit 1
fi

script="$(wslpath -w "$(dirname "$(readlink -f "$0")")/build.ps1")"
exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$script" "$@"
