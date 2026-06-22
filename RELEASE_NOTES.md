# Cathode 2.0

A retro IPTV player that plays your M3U channels like old cable TV: a phosphor-glow
program guide, CRT scanlines, channel-change static, and on-screen menus driven by
keyboard, mouse, or game controller. Runs on the Steam Deck, Linux, Windows, and macOS.

## Features

**Live TV**
- M3U playlists with an XMLTV program guide and a live picture-in-picture preview
- Channel logos, favorites, and categories
- Info bar, CRT scanlines, vignette, and channel-change static

**Plex-Per-View** — browse and watch your own Plex library on demand
- Sign in with a plex.tv/link code; Plex Home users with PIN support
- Multiple/shared servers, picked under Options > Plex > Server
- Search, Continue Watching, and your watchlist
- Movie / TV / Other Videos libraries, browsable by genre or folder, sortable
- Resume where you left off (synced back to the server), Play All, and Shuffle
- Skip Intro / Skip Credits, audio & subtitle track selection, subtitle
  font/size/color, audio device, and streaming-quality (direct play or transcode)

**Interface**
- 9 color themes, 5 retro fonts, a custom theme editor, and saved profiles
- Weather strip in the guide header (no API key)
- Full mouse control with on-screen Back/Menu buttons; controller support that
  survives unplug/reconnect; Steam Deck Game Mode
- Sleep timer and an idle screensaver
- Built-in update check (Options > Check for Updates)
- Demo mode with test-pattern channels

On first launch, an on-screen keyboard asks for your M3U playlist URL. To try it
first with built-in test channels, use `--demo` where shown.

### Windows

1. Download `cathode-windows-2.0-portable.zip`.
2. Right-click it → **Extract All** into any folder.
3. Open the folder and run **`Cathode.exe`**.

Python and mpv are bundled — nothing else to install. (If SmartScreen warns,
choose **More info → Run anyway**.)

### Steam Deck

1. In **Desktop Mode**, download `cathode-linux-macos-2.0.zip` and extract it.
2. Open the extracted folder, right-click → **Open Terminal Here**, and run:

   ```bash
   chmod +x install.sh cathode.sh
   ./install.sh
   ./cathode.sh          # add --demo to try without a playlist
   ```

`install.sh` (run once) installs mpv via Flatpak, sets up a private Python
environment, and adds a menu shortcut. For Game Mode, finish setup in Desktop
Mode, then add Cathode as a non-Steam game.

### Linux / macOS

Extract `cathode-linux-macos-2.0.zip`, open a terminal in that folder, then:

```bash
chmod +x install.sh cathode.sh      # macOS: install-macos.sh
./install.sh                        # macOS: ./install-macos.sh
./cathode.sh                        # add --demo to try without a playlist
```

The installer sets up mpv (Flatpak on Linux, Homebrew on macOS) and a private
Python environment. On Linux you can instead install mpv from your distro
(`sudo apt install mpv`, or `dnf`/`pacman`) and Cathode will find it.

## Notes

- Free, non-commercial software under the GNU GPL v3.0.
- Not affiliated with or endorsed by Plex Inc.
