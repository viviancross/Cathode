#!/usr/bin/env bash
# Cathode installer for Steam Deck (SteamOS) / Linux.
#
# Designed to work on SteamOS WITHOUT disabling the read-only root filesystem:
#   • mpv is installed as a Flatpak (user scope, survives OS updates)
#   • Python deps are installed into a local virtualenv in this folder
# No `sudo`, no pacman, nothing written to the system.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Cathode IPTV Installer ==="
echo

# ── 1. mpv via Flatpak ────────────────────────────────────────────────────────
echo "[1/4] Installing mpv (Flatpak, user scope)…"

if ! command -v flatpak &>/dev/null; then
    echo "  ERROR: flatpak is not installed."
    echo "  On SteamOS flatpak is preinstalled; on other distros install it first."
    exit 1
fi

# Make sure Flathub is available (user remote)
flatpak --user remote-add --if-not-exists flathub \
    https://flathub.org/repo/flathub.flatpakrepo || true

if flatpak info io.mpv.Mpv &>/dev/null; then
    echo "  io.mpv.Mpv already installed."
else
    flatpak --user install -y flathub io.mpv.Mpv
fi

# Grant mpv access to the shared runtime dir (IPC socket + overlay buffer).
RUNTIME_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/cathode"
mkdir -p "$RUNTIME_DIR"
flatpak --user override io.mpv.Mpv --filesystem="$RUNTIME_DIR" || true

# ── 2. Python virtualenv ──────────────────────────────────────────────────────
echo "[2/4] Creating Python virtual environment…"
if ! command -v python3 &>/dev/null; then
    echo "  ERROR: python3 not found."
    exit 1
fi
python3 -m venv "$SCRIPT_DIR/.venv"
# Call the venv's Python by absolute path with `-m pip` instead of running
# `.venv/bin/pip` or `source activate`.  The pip/activate scripts hard-code the
# venv path in their #! shebang line, which the kernel truncates at 127 bytes —
# on a long install path that yields "bad interpreter: no such file or
# directory".  Invoking the python *binary* directly sidesteps that entirely.
VENV_PY="$SCRIPT_DIR/.venv/bin/python"
"$VENV_PY" -m pip install -q --upgrade pip
"$VENV_PY" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"

# ── 3. Retro fonts ────────────────────────────────────────────────────────────
echo "[3/4] Checking retro fonts…"
FONT_DIR="$SCRIPT_DIR/assets/fonts"
mkdir -p "$FONT_DIR"

fetch_font() {
    # $1 = destination filename, $2 = URL
    local dest="$FONT_DIR/$1"
    [ -f "$dest" ] && return 0
    if command -v curl &>/dev/null; then
        curl -fsSL -o "$dest" "$2" 2>/dev/null && return 0
    elif command -v wget &>/dev/null; then
        wget -q -O "$dest" "$2" 2>/dev/null && return 0
    fi
    echo "  (could not fetch $1 — a system monospace font will be used)"
    rm -f "$dest" 2>/dev/null
}

# VCR OSD Mono and PxPlus IBM VGA are bundled with the app; fetch only if
# missing (e.g. a slimmed-down copy).
fetch_font "VCR_OSD_MONO.ttf" \
    "https://raw.githubusercontent.com/3ndG4me/Font/master/VCR_OSD_MONO_1.001.ttf"
fetch_font "PxPlus_IBM_VGA8.ttf" \
    "https://github.com/olikraus/u8g2/raw/master/tools/font/ttf/PxPlus_IBM_VGA8.ttf"

# ── 4. Launcher + desktop entry ───────────────────────────────────────────────
echo "[4/4] Creating launcher…"
chmod +x "$SCRIPT_DIR/cathode.sh"

# Generate the icon if it's missing (it's normally bundled).
ICON_FILE="$SCRIPT_DIR/assets/cathode.png"
if [ ! -f "$ICON_FILE" ]; then
    "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/tools/make_icon.py" 2>/dev/null || true
fi

# Build the .desktop entry.  Note the Exec path is QUOTED so it works even when
# the install folder name contains spaces (e.g. "cathode 0.1").
write_desktop_entry() {
    cat > "$1" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Cathode
GenericName=Retro IPTV Player
Comment=Flip through IPTV channels like 80s/90s cable TV
Exec="$SCRIPT_DIR/cathode.sh"
Path=$SCRIPT_DIR
Icon=$ICON_FILE
Terminal=false
Categories=AudioVideo;Video;TV;Player;
StartupNotify=false
EOF
    chmod +x "$1"           # KDE/Plasma requires the exec bit to launch it
}

# 1) App-menu entry  2) a shortcut on the Desktop (handy for "Add to Steam")
APPS_DESKTOP="$HOME/.local/share/applications/cathode.desktop"
mkdir -p "$(dirname "$APPS_DESKTOP")"
write_desktop_entry "$APPS_DESKTOP"

DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
mkdir -p "$DESKTOP_DIR"
write_desktop_entry "$DESKTOP_DIR/cathode.desktop"
# Mark it trusted so Plasma launches it without the "untrusted" prompt.
if command -v gio &>/dev/null; then
    gio set "$DESKTOP_DIR/cathode.desktop" metadata::trusted true 2>/dev/null || true
fi
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "=== Installation complete! ==="
echo
echo "Usage:"
echo "  $SCRIPT_DIR/cathode.sh --playlist YOUR_M3U_URL_OR_FILE [--epg YOUR_XMLTV_URL]"
echo
echo "Config is saved to: ~/.config/cathode/config.json"
echo "(set playlist_url / epg_url there to skip the flags next time)"
echo
echo "A 'Cathode' shortcut was added to your Desktop and app menu."
echo
echo "To play in Game Mode:"
echo "  1. Set playlist_url / epg_url in ~/.config/cathode/config.json"
echo "     (so it launches straight into your channels with no arguments)."
echo "  2. Steam (Desktop mode) > Games > Add a Non-Steam Game > Browse, and"
echo "     pick the 'Cathode' Desktop shortcut (or cathode.sh)."
echo "  3. In its Steam properties, apply a controller layout that maps the"
echo "     D-pad/buttons to the keys below."
echo
echo "Keyboard shortcuts:"
echo "  Up / Down    Channel up / down  (move selection inside the guide)"
echo "  Left / Right Volume down / up  (timeline scroll inside the guide)"
echo "  0-9 / numpad Direct channel entry"
echo "  G            Open / close program guide"
echo "  I / Tab      Show / hide info OSD"
echo "  M            Mute"
echo "  F            Add / remove the channel from Favorites"
echo "  C            Open the context menu (themes, fonts, playlists, display)"
echo "  W            Toggle fullscreen / windowed"
echo "  Enter        Select / open the context menu from the info bar"
echo "  PgUp / PgDn  Jump +/- 10 channels"
echo "  Q            Quit        Esc  Close the current dialog / guide"
