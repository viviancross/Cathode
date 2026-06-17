# Cathode setup for Windows.
# Creates a local virtualenv with the Python deps and checks for mpv.
# Run from PowerShell:  .\install-windows.ps1
$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $dir

Write-Host "=== Cathode (Windows) setup ===`n"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python 3 not found. Install it from https://python.org" -ForegroundColor Red
    Write-Host "(or: winget install Python.Python.3.12), then re-run this script."
    exit 1
}

Write-Host "[1/2] Creating virtual environment + installing Python deps..."
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -q --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -q -r requirements.txt

Write-Host "[2/2] Checking for mpv..."
if (Get-Command mpv -ErrorAction SilentlyContinue) {
    Write-Host "  mpv found: $((Get-Command mpv).Source)"
} else {
    Write-Host "  mpv NOT on PATH. Install real mpv (NOT mpv.net):" -ForegroundColor Yellow
    Write-Host "     scoop install mpv     (or)    choco install mpv"
    Write-Host "     or download from https://mpv.io/installation/ and add to PATH"
    Write-Host "  Verify with 'mpv --version'. If you keep mpv elsewhere, set"
    Write-Host '     "mpv_path": "C:/path/to/mpv.exe"  in ~/.config/cathode/config.json'
}

Write-Host "`nDone. Try it:"
Write-Host "  .\cathode.bat --demo"
Write-Host "  .\cathode.bat --playlist <M3U_URL> --epg <XMLTV_URL>"
