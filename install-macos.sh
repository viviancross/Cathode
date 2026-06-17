#!/usr/bin/env bash
# Cathode installer for macOS (from source).
#
# Creates a local virtualenv with the Python deps and ensures mpv is present
# (via Homebrew). No app bundle is built — launch with ./cathode.sh. To build a
# double-clickable Cathode.app instead, see tools/build_macos.py.
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Cathode macOS Installer ==="

# ── 1. mpv (Homebrew) ─────────────────────────────────────────────────────────
echo "[1/3] Checking mpv…"
if ! command -v mpv >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
        echo "  Installing mpv via Homebrew…"
        brew install mpv
    else
        echo "  ERROR: mpv not found and Homebrew isn't installed."
        echo "  Install Homebrew (https://brew.sh), then: brew install mpv"
        exit 1
    fi
fi

# ── 2. Python virtualenv ──────────────────────────────────────────────────────
echo "[2/3] Creating Python virtual environment…"
if ! command -v python3 >/dev/null 2>&1; then
    echo "  ERROR: python3 not found (install from python.org or 'brew install python')."
    exit 1
fi
python3 -m venv "$DIR/.venv"
VENV_PY="$DIR/.venv/bin/python"
"$VENV_PY" -m pip install -q --upgrade pip
"$VENV_PY" -m pip install -q -r "$DIR/requirements.txt"

# ── 3. Launcher ───────────────────────────────────────────────────────────────
echo "[3/3] Making the launcher executable…"
chmod +x "$DIR/cathode.sh"

echo
echo "=== Installation complete! ==="
echo
echo "Launch it with:"
echo "  $DIR/cathode.sh --playlist YOUR_M3U_URL_OR_FILE [--epg YOUR_XMLTV_URL]"
echo
echo "Config is saved to: ~/.config/cathode/config.json"
echo "(set playlist_url / epg_url there to skip the flags next time)."
