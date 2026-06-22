<img src="assets/cathode.png" width="96" align="left" alt="Cathode">

# Cathode

A retro IPTV player. It plays your M3U channels like old cable TV: a phosphor‑glow
program guide, CRT scanlines, channel‑change static, and on‑screen menus you can
drive with a keyboard, a mouse, or a game controller. It runs on the Steam Deck,
Linux, Windows, and macOS, and renders at the window's real size, so it looks
right on the Deck's screen and on a docked 1080p TV.

**Version 2.0**

<br clear="left">

## How it works

Cathode doesn't decode video itself. It runs **mpv** as a separate process and
talks to it over mpv's JSON IPC (a socket on Linux/macOS, a named pipe on
Windows). mpv handles video and audio. Cathode draws the interface in Python
with Pillow and paints it over the video with mpv's `overlay-add`. Running mpv
as its own process is also why the Flatpak mpv works on the Deck with no special
build.

## Features

- M3U playlists with an XMLTV program guide, a live picture‑in‑picture preview,
  channel logos (including animated GIF and APNG), favorites, and categories.
- A retro interface: info bar, program guide, scanlines, vignette, and
  channel‑change static that holds until the new stream's first frame is ready.
- 9 color themes, 5 bundled fonts, a custom theme editor, and saved profiles
  that bundle a theme, font, and CRT settings together. Drop your own font into
  `assets/fonts/` and it shows up in the menu.
- A weather strip in the guide header (current conditions, temperature, city,
  humidity, rain chance) from wttr.in. No API key.
- **Plex‑Per‑View**: sign in to your Plex server and browse and watch your
  library on demand, laid out like a cable pay‑per‑view menu. See below.
- Full on‑screen control. Every action has a button on screen, so it works in
  Steam Deck Game Mode with no desktop dialogs.
- Renders at mpv's real window size, so it fits any resolution automatically.
- A demo mode with built‑in test‑pattern channels, so you can try it with no
  playlist.

## Install

### Windows

Extract the Windows zip and run `Cathode.exe`. Python and mpv are included, so
there's nothing else to install. On first run, an on‑screen keyboard asks for
your playlist URL.

### Steam Deck and Linux

In Desktop Mode, open a terminal in the source folder:

```bash
chmod +x install.sh cathode.sh
./install.sh
./cathode.sh          # add --demo to try it without a playlist
```

`install.sh` installs the Flatpak mpv (user scope), creates a virtualenv, and
adds a menu shortcut. For Game Mode, set up your playlist in Desktop Mode first,
then add `cathode.sh` to Steam as a non‑Steam game and apply a controller layout.

### macOS

```bash
chmod +x install-macos.sh cathode.sh
./install-macos.sh    # installs mpv with Homebrew and sets up a virtualenv
./cathode.sh          # add --demo to try it without a playlist
```

### Any other Linux

```bash
sudo apt install mpv python3 python3-venv python3-pip   # or dnf / pacman
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py --demo
```

## Using it

Cathode opens on a home screen with **New Playlist**, **Load Playlist**,
**Plex‑Per‑View**, **Options**, and **Exit**. New Playlist asks for a name, an
M3U URL, and an optional XMLTV URL. Demo mode skips straight to the test
channels.

Text fields use an on‑screen keyboard that also takes real typing and Ctrl+V
paste. Press DONE to submit.

To boot straight into your last playlist, set `"main_menu_on_launch": false` in
the config file. The home screen is still reachable from the context menu.

### Controls

| Key | Action |
|-----|--------|
| ↑ / ↓ | Channel up / down (in the guide, move the selection) |
| ← / → | Volume down / up (in the guide, scroll through time) |
| 0–9 | Type a channel number |
| G | Program guide |
| I or Tab | Info bar |
| M | Mute |
| F | Favorite the current or highlighted channel |
| C, right‑click, or the corner button | Context menu |
| W or double‑click | Fullscreen |
| Enter | Select the highlighted item |
| Backspace | Delete a character, or go back one menu level |
| PgUp / PgDn | Jump 10 channels |
| Q | Quit |
| Esc | Close whatever's open; never quits |

Hold a navigation key to repeat it. While a menu or the keyboard is open, letter
and number shortcuts are off until you close it.

### Game controller

A controller works on every build with no setup (XInput on Windows,
`/dev/input/js*` on Linux, IOKit HID on macOS). Turn it off with
`"gamepad": false`.

| Button | Action |
|--------|--------|
| D‑pad / left stick | Navigate |
| A | Select |
| B | Back |
| X or Start | Program guide |
| Y | Info bar |
| Back / View | Context menu |
| LB / RB | Channel down / up |
| LT / RT | Volume down / up |
| L3 / R3 | Mute / fullscreen |

## Plex‑Per‑View

Pick **Plex‑Per‑View** from the home screen. The first time, it shows a code to
enter at plex.tv/link; after that it stays signed in. If your account has Plex
Home users, it asks who's watching.

From there you can:

- Browse Movie, TV, and Other Videos libraries, including by folder.
- Filter by genre and sort by title, date added, year, or rating.
- Open your Plex watchlist.
- See a detail page per title with poster, summary, and resume point.
- Play a movie or episode, play a whole show, or shuffle it.
- Resume where you left off. Cathode reports your position back to the server, so
  progress and watched state stay in sync with your other devices.

While something is playing, press the context‑menu button for audio and subtitle
tracks, subtitle font/size/color, and the audio output device. Set streaming
quality (direct play or a transcode cap) under Options.

Your Plex token is sent to the server in a request header, not in the video URL,
so it doesn't end up in mpv's log file.

## Options and config

Most settings live under **Options** in the context menu: themes, fonts,
profiles, the custom theme editor, weather (zip and country), and display. The
config file is at `~/.config/cathode/config.json` and is written automatically.

Settings you'll only find in the file:

- `main_menu_on_launch` — show the home screen on launch, or boot into the last
  playlist.
- `mpv_path` — full path to mpv if it isn't on PATH.
- `mpv_extra_args` — extra mpv flags, e.g. `["--hwdec=no"]`.
- `gamepad` — turn the controller reader on or off.

## Building from source

PyInstaller can't cross‑compile, so build on the OS you're targeting. Install
PyInstaller (`pip install pyinstaller`), then run the matching script:

```bash
python tools/build_windows.py   # cathode-windows-<ver>-portable.zip (bundles mpv)
python tools/build_linux.py     # cathode-linux-<ver>.tar.gz
python tools/build_macos.py     # cathode-macos-<ver>.zip (mpv via Homebrew)
python tools/build_source.py    # cross-platform source zip
```

Only the Windows build bundles mpv. The Linux and macOS builds expect mpv to be
installed on the machine.

## Troubleshooting

- **mpv not found (Windows)** — install real mpv so `mpv --version` works, or set
  `mpv_path`. mpv.net is a different program and won't work.
- **No video in Game Mode but it works on the desktop** — check
  `~/.cache/cathode/mpv.log`, then try `mpv_extra_args` like
  `["--gpu-context=wayland"]`, `["--hwdec=no"]`, or `["--vo=gpu-next"]`.
- **Guide is empty** — the channel `tvg-id`s have to match the XMLTV ids. Cathode
  also tries a fuzzy name match as a fallback.
- **ModuleNotFoundError for PIL or numpy** — the virtualenv isn't active. Run the
  installer, or `source .venv/bin/activate`.

## Project layout

```
main.py              entry point
cathode/
  app.py             input handling, menus, profiles, playlists
  player.py ipc.py   drives mpv over JSON IPC
  plex.py            Plex client (sign-in, browse, playback)
  playlist.py epg.py config.py weather.py demo.py logos.py gamepad.py
  ui/
    renderer.py      compositing and the channel-change state machine
    mainmenu.py guide.py osd.py menu.py osk.py editor.py theme.py effects.py
    ppv.py plexinfo.py plexosd.py    (Plex-Per-View screens)
assets/   fonts and icons
tools/    build and preview scripts
```

## License and credits

Cathode is free, non‑commercial software under the **GNU General Public License
v3.0**. See [`LICENSE`](LICENSE).

Cathode is not affiliated with, endorsed by, or sponsored by Plex Inc. "Plex" is
a trademark of Plex Inc.; Cathode is an independent client for a Plex server you
already own.

The bundled fonts and the bundled mpv (Windows only) keep their own licenses.
Cathode runs mpv as its own process and never links it as a library. Details
and attributions are in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and
[`LICENSES/`](LICENSES/).
