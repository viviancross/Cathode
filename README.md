<img src="assets/cathode.png" width="96" align="left" alt="Cathode">

# Cathode

A retro IPTV player for the Steam Deck, Linux, Windows, and macOS. Flip through
your M3U channels like it's 80s/90s cable TV — phosphor‑glow program guide, CRT
scanlines, channel‑change snow, and on‑screen menus that scale from the Deck's
screen to 1080p when docked.

**Version: 2.2b**

<br clear="left">

# Cathode 1.0

A retro IPTV player that turns your M3U channel list into 80s/90s cable TV.

## Features

- **M3U + XMLTV** — full program guide with a live picture-in-picture preview, channel logos (including animated GIF/APNG), favorites, and categories.
- **Retro UI** — Info Bar, Program Guide, CRT scanlines, vignette, manual channel surfing, and authentic channel-change static.
- **Themes & fonts** — 9 color themes, a custom theme editor, 5 retro fonts, the ability to add your own custom fonts, and saveable theme profiles.
- **Weather** — set your country and zip in the options menu, and the guide header shows current conditions, temperature, humidity, rain chance, and your city.
- **Full on-screen control** — context menu and on-screen keyboard, driven by mouse, keyboard, or a controller. Works in Steam Deck Game Mode.
- **Auto resolution** — renders at mpv's real window size, to any resolution.
- **Demo mode** — built-in test-pattern channels, no playlist needed.

## How it works

Cathode doesn't embed a player. It launches **mpv** as a subprocess and drives it
over mpv's **JSON IPC** (a Unix socket on Linux/macOS, a named pipe on Windows).
mpv handles video/audio; the UI is rendered in Python (Pillow + numpy) and drawn
over the video with `overlay-add`.

---

## Install

### Windows (portable, no prerequisites)

Extract **`cathode-windows-<ver>-portable.zip`** and run **`Cathode.exe`**. Python
and mpv are bundled. On first run an on‑screen keyboard asks for your playlist URL.

### Steam Deck / Linux (from source)

In Desktop Mode, open a terminal in this folder:

```bash
chmod +x install.sh cathode.sh
./install.sh      # Flatpak mpv (user scope) + venv + a Desktop/menu shortcut
./cathode.sh      # or: ./cathode.sh --demo
```

For Game Mode, set your playlist, then add the Cathode shortcut as a Non‑Steam
Game and map the controller (see [Controls](#controls)).

A prebuilt **`cathode-linux-<ver>.tar.gz`** runs without a venv (extract, then
`./Cathode/Cathode`) but still needs mpv installed (`flatpak install flathub
io.mpv.Mpv` or your distro's `mpv`).

### macOS

Run **`Cathode.app`** from `cathode-macos-<ver>.zip` (first launch: right‑click →
**Open**, since it's unsigned) and `brew install mpv`. Or from source:

```bash
chmod +x install-macos.sh cathode.sh
./install-macos.sh && ./cathode.sh
```

### Other Linux (from source)

```bash
sudo apt install mpv python3 python3-venv python3-pip   # or dnf / pacman
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py --demo
```

> **Flatpak** packaging (`io.github.viviancross.Cathode.yml` + `install-flatpak.sh`)
> exists but is **experimental/untested** — expect to iterate.
>
> **Building binaries:** PyInstaller can't cross‑compile, so build on the target
> OS. `pip install pyinstaller`, then `python tools/build_windows.py`
> (or `build_linux.py` / `build_macos.py`).

---

## Using Cathode

Cathode opens on a **main menu**: **New Playlist** (enter a name + M3U URL +
optional XMLTV URL), **Load Playlist** (pick a saved one), **Options**, and
**Exit**. Demo mode skips straight to the test channels. To boot directly into
your playlist, set `"main_menu_on_launch": false` in `config.json` — the menu
stays reachable from the context menu.

Text entry (URLs, names) uses an **on‑screen keyboard** that also accepts direct
physical typing and **Ctrl+V** paste. Press **DONE** to submit.

### Controls

| Input | Action |
|-------|--------|
| ↑ / ↓ | Channel up / down (guide: move selection) |
| ← / → | Volume down / up (guide: scroll time) — any volume change unmutes |
| `0`–`9` / numpad | Direct channel entry |
| `G` | Program guide |
| `I` / `Tab` | Info bar |
| `M` | Mute |
| `F` | Add / remove the current or highlighted channel from **Favorites** |
| `C` / **right‑click** / corner button | **Context menu** |
| `W` / double‑click | Toggle fullscreen |
| `Enter` / `Keypad Enter` | Select the highlighted item (info bar up → opens the menu) |
| `Backspace` | Delete a character (hold to repeat) / back out one menu level |
| `PgUp` / `PgDn` | Jump ±10 channels |
| `Q` | Quit |
| `Esc` | Failsafe — closes any dialog, else guide → info bar → fullscreen. Never quits. |

**Hold** a navigation key to repeat it (highlight wraps around in menus, the
keyboard, and the guide); channel/volume take a fresh press each time. While a
menu or the keyboard is open, letter/number hotkeys are disabled — press **Esc**
to close and restore them.

### Gamepad

A plugged‑in pad works on every build via a built‑in reader (**XInput** on
Windows, `/dev/input/js*` on Linux, **IOKit HID** on macOS) — no setup. On the
Deck in Game Mode, a Steam Input profile mapping buttons to the keys above also
works. Disable with `"gamepad": false`.

| Button | Action |
|--------|--------|
| **D‑pad / left stick** | Navigate (channels & volume while watching; selection in guide/menu) |
| **A** | Select / press highlighted key |
| **B** | Back (delete char / leave sub‑menu / close guide or info bar) |
| **X** / **Start** | Program guide |
| **Y** | Info bar |
| **Back / View** | Context menu |
| **LB / RB** | Channel down / up |
| **LT / RT** | Volume down / up |
| **L3 / R3** | Mute / toggle fullscreen |

### Context menu

Open with **right‑click** or the menu button next to the info bar. Picking an
item inside **Options** applies it and keeps the menu open.

```
Program Guide / Info Bar / Add Favorite / Channel [^][v] / Volume [<][>] / Mute
Playlists >  switch network, Add playlist..., Delete playlist...
Options >    Themes >   Color Theme (+ Custom Theme...), Font, Profiles
             Weather >  Zip Code..., Country, Units (°F/°C)
             Display >  Fullscreen, monitor swap
Main Menu / Quit
```

---

## Customizing

**Themes & fonts** — 9 themes (Classic Blue, Amber CRT, Green Phosphor, VHS
Magenta, Monochrome, Commodore 64, Red Alert, Synthwave, Ice) and 5 bundled fonts
(VCR OSD Mono, PxPlus IBM VGA, Glass TTY VT220, Pixel Forge, DejaVu Sans Mono).
Drop any `.ttf`/`.otf` into **`assets/fonts/`** and it appears in **Options ▸
Themes ▸ Font** automatically. **Profiles** bundle theme + font + scanline
intensity + CRT/vignette toggles; save your own with **Save current as…**.

**Custom theme editor** (**Options ▸ Themes ▸ Color Theme ▸ Custom Theme…**) —
RGB sliders for the five core colors (Background, Accent, Highlight, Text, and
**Channel #**), a Scanline Intensity slider, and CRT/Vignette toggles, all with a
live preview. Save over the current theme or as a new one; closing without saving
discards changes.

**Weather** (**Options ▸ Weather**) — set your **Zip Code**, pick your **Country**
(a bare zip is ambiguous — `90210` could resolve to Spain — so the lookup is
pinned to the chosen country), and toggle **°F / °C**. The header shows a
condition icon, temperature, city, humidity, and rain chance, refreshed every 15
minutes from [wttr.in](https://wttr.in) (no API key, fetched in the background).
Hidden until you set a zip.

**Favorites & categories** — press **`F`** to favorite the current/highlighted
channel (a toast confirms; persists in config). The guide's category selector
(◄ All ►, focus it by pressing **Up** past the top row) cycles through XMLTV
genres plus **All** and **Favorites**.

**Channel logos** come from XMLTV `<icon>` URLs (or the M3U `tvg-logo`), cached on
disk, shown in the info bar and guide; channels without one show their number.

**Monitors** (**Options ▸ Display**) — holds the Fullscreen toggle and lists
connected screens; pick one to move the window there (it rescales automatically).

**Playlists** (**Options ▸ Playlists**) — save multiple IPTV sources and switch
instantly; it reloads channels + guide and retunes.

---

## Configuration

`~/.config/cathode/config.json` (Windows: `%USERPROFILE%\.config\cathode\`).
Created automatically; edit while the app is closed.

| Key | Meaning |
|-----|---------|
| `playlist_url`, `epg_url` | Active M3U / XMLTV (URL or file path) |
| `playlists` | Saved networks: `[{name, playlist_url, epg_url}, …]` |
| `profiles` | Saved looks: `{name: {theme, font, scanline_alpha, crt, vignette, …}}` |
| `theme`, `font` | Active theme name / font key |
| `custom_themes` | User themes: `{name: {bg, accent, accent2, text, chnum, …}}` |
| `favorites` | Favorite channel numbers |
| `volume`, `muted`, `last_channel` | Playback state |
| `scanline_alpha`, `crt_enabled`, `vignette_enabled` | CRT effect strength / toggles |
| `gamepad` | Native gamepad control on/off |
| `nav_repeat_delay`, `nav_repeat_rate` | Held‑key repeat delay (ms) / rate (per sec) |
| `main_menu_on_launch` | Show the home screen on launch (`false` = boot into the playlist) |
| `guide_hours` | Hours shown across the guide |
| `weather_zip`, `weather_country`, `weather_units` | Guide weather (empty zip = off; country is ISO‑2; units `F`/`C`) |
| `reveal_duration`, `tune_timeout` | Channel‑change fade / stall timeout |
| `osd_timeout`, `osd_timeout_info` | Info‑bar durations |
| `mpv_path`, `mpv_extra_args` | Explicit mpv path / extra raw args (e.g. `["--hwdec=no"]`) |
| `user_agent` | HTTP user‑agent for playlist/EPG/streams |

**Command line:** `--playlist/-p`, `--epg/-e`, `--demo`, `--windowed/-w`,
`--fullscreen/-f`, `--width`, `--height`, `--mpv auto|flatpak|system`,
`--channel N`, `--config/-c FILE`.

---

## Autostart (always‑on PC)

```bash
chmod +x install-service.sh && ./install-service.sh
systemctl --user start cathode.service
journalctl --user -u cathode.service -f   # logs
```

## Troubleshooting

- **`ModuleNotFoundError: PIL/numpy`** — venv not active; run the installer or
  `source .venv/bin/activate`.
- **mpv not found (Windows)** — install real mpv (`mpv --version` must work) or
  set `mpv_path`. mpv.net is a different app.
- **No video in Game Mode (works in Desktop)** — Check
  `~/.cache/cathode/mpv.log` and try `mpv_extra_args` like `["--gpu-context=wayland"]`,
  `["--hwdec=no"]`, or `["--vo=gpu-next"]`.
- **Nothing in the guide** — channel `tvg-id`s must match the XMLTV ids (a fuzzy
  name match is attempted as a fallback).

## Project layout

```
main.py              entry point
cathode/
  app.py             wiring, input handling, menus/profiles/playlists
  player.py ipc.py   drives mpv over JSON IPC (socket / named pipe)
  playlist.py epg.py config.py weather.py demo.py
  ui/
    renderer.py      compositing + channel-change state machine
    osd.py guide.py menu.py osk.py effects.py theme.py mainmenu.py editor.py
assets/   fonts + icon          tools/   build + preview scripts
install*.sh  cathode.sh  make-shortcut.sh        (Linux / macOS / Flatpak)
install-windows.ps1  cathode.bat                 (Windows)
```
