#!/usr/bin/env bash
# Install Cathode as a systemd *user* service so it launches with your desktop
# session and restarts itself if it crashes.  For an always-on Linux PC.
#
# This is a USER service (systemctl --user), not a system one: it needs your
# graphical session (a display) to show video, so it starts on login.  For a
# machine that boots straight into Cathode, enable auto-login in your desktop
# settings (see the note printed at the end).
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/cathode.service"

if ! command -v systemctl &>/dev/null; then
    echo "ERROR: systemd (systemctl) not found on this system." >&2
    exit 1
fi

mkdir -p "$UNIT_DIR"

# Note: the ExecStart path is double-quoted so it survives spaces in the install
# folder name (e.g. "cathode 0.1").  Restart=on-failure means a crash relaunches
# it, but quitting cleanly with Q/Esc leaves it stopped.  Change to
# Restart=always for a true kiosk that always comes back.
cat > "$UNIT" <<EOF
[Unit]
Description=Cathode retro IPTV player
After=graphical-session.target
PartOf=graphical-session.target
# Back off instead of hammering if it fails to start repeatedly
StartLimitIntervalSec=120
StartLimitBurst=5

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart="$SCRIPT_DIR/cathode.sh"
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
EOF

systemctl --user daemon-reload
systemctl --user enable cathode.service

echo "Installed: $UNIT"
echo
echo "Before starting, make sure your channels are set so it launches with no"
echo "arguments:  ~/.config/cathode/config.json  ->  playlist_url / epg_url"
echo
echo "Start it now:        systemctl --user start cathode.service"
echo "Check it:            systemctl --user status cathode.service"
echo "Live logs:           journalctl --user -u cathode.service -f"
echo "Stop it:             systemctl --user stop cathode.service"
echo "Disable autostart:   systemctl --user disable cathode.service"
echo
echo "It will now start automatically every time you log into the desktop."
echo "For a machine that boots straight in with no one touching it, also turn on"
echo "auto-login in your desktop/display-manager settings."
