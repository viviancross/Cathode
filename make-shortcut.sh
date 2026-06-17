#!/usr/bin/env bash
# Create (or refresh) the Cathode desktop shortcut + app-menu entry.
# Safe to re-run any time — e.g. after moving the install folder.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ICON_FILE="$SCRIPT_DIR/assets/cathode.png"

# Regenerate the icon if it's missing.
if [ ! -f "$ICON_FILE" ]; then
    if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
        "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/tools/make_icon.py" 2>/dev/null || true
    else
        python3 "$SCRIPT_DIR/tools/make_icon.py" 2>/dev/null || true
    fi
fi

chmod +x "$SCRIPT_DIR/cathode.sh" 2>/dev/null || true

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
    chmod +x "$1"
}

APPS_DESKTOP="$HOME/.local/share/applications/cathode.desktop"
mkdir -p "$(dirname "$APPS_DESKTOP")"
write_desktop_entry "$APPS_DESKTOP"

DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
mkdir -p "$DESKTOP_DIR"
write_desktop_entry "$DESKTOP_DIR/cathode.desktop"
command -v gio &>/dev/null && \
    gio set "$DESKTOP_DIR/cathode.desktop" metadata::trusted true 2>/dev/null || true
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo "Created Cathode shortcut:"
echo "  Desktop : $DESKTOP_DIR/cathode.desktop"
echo "  App menu: $APPS_DESKTOP"
echo
echo "Add to Steam: Desktop-mode Steam > Games > Add a Non-Steam Game >"
echo "Browse > pick the Cathode shortcut (set playlist_url in"
echo "~/.config/cathode/config.json first so it launches into your channels)."
