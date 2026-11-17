<img src="assets/cathode.png" width="96" align="left" alt="Cathode">

# Cathode

Cable TV from your own library, on a box from the 2000s.

Cathode turns your Plex library (or Jellyfin, Emby, or folders on the
computer) into a lineup of round-the-clock channels: Nickelodeon at 8 PM is
Nick at Nite, the commercials and bumpers run between the programmes, the
guide is filled two days ahead, and you join every channel in progress. It
plays your Tunarr, ErsatzTV or M3U channels too, and YouTube playlists as
channels. All of it on screen as a satellite or cable box of the period,
driven by a remote.

**Version 5.3** · Windows · Linux and the Steam Deck · Android TV, Google TV
and Fire TV

<br clear="left">

## What it does

**Channels from your library.** A starter lineup made from what you have,
every show and movie placed on the channel it belongs on, and new arrivals
placed as they come. Any channel of your own, built from shows, seasons,
single episodes, movies, whole libraries, genres, decades, studios,
ratings, Plex collections or playlists, and content groups.

**Scheduled as TV was.** Eleven sort methods (shuffles, blocks, marathons,
round robins, Mix, playlist order, whole albums). Time slots and dayparts,
on-air hours with colour bars at sign-off, premieres, pinned start times
("The Simpsons at 8:00 PM weeknights"), random marathons, holiday episodes
only in their season, two-part episodes back to back, movies capped per
day, grown-up ratings only late at night, a redirect to another channel
overnight, a watched filter, per-title weights. The day is written down a
day at a time and carried on across days and restarts.

**Breaks.** Commercials and bumpers from your clip libraries between
programmes, lined up with the clock; station idents; a set number per
break or fill-the-time; a running order or shuffled; long videos of old ads
cut into commercial-length pieces; a coming-up-next card (with an announcer
voice if you want one); mid-show breaks halfway, every so many minutes, at
chapter marks, or at the quiet moments where a show faded out for its own
breaks.

**On screen.** The channel's logo as a screen bug (always, on change, or
now and then), a TV rating box as a programme starts, an up-next countdown,
the banner and guide with each episode's details, a choice of tuning
screens, seasonal decorations on the guide, and a TV-cabinet bezel if you
like.

**Special channels.** TV Guide; Local Weather with radar, the outlook and
US weather alerts (and a red crawl over live TV for a severe one); music
libraries as radio channels with a visualizer; a Video Store channel to
browse and "rent" your movies; locked (18+) channels that come through
scrambled until the PIN; pop-up trivia during programmes.

**Live TV from playlists.** M3U and XMLTV (Tunarr, ErsatzTV, an IPTV line,
an HDHomeRun tuner), with the guide, favourites, channel packs, hidden,
renamed and renumbered channels, a number offset per playlist, and
pause, rewind and fast-forward through what's buffered. Spelunkr's channels
come with it.

**On Demand.** Your Plex libraries to browse and search, Recommended rows,
collections, trailers, theme songs, Continue Watching, the watchlist, a
play queue, Skip Intro, and My Recordings (titles downloaded to watch
offline).

**Around the house.** Every Cathode on your network keeps the same channels,
showing the same thing at the same moment. Cast a channel or a film to
another Cathode. A web page on your phone: a remote, what's on, the lineup,
every channel's settings, what Plex is playing, the log, export and import.
An API for Home Assistant. Profiles, kids' profiles and a parent PIN.

**Plex, kept in step.** Library channels mark what you watched in Plex and
show in its dashboard as playing.

## The boxes

Seven skins, switchable any time under **Settings > Design**:

| Skin | After |
|---|---|
| Cathode Classic | Cathode 3's own retro CRT look: phosphor colours, pixel fonts, static between channels |
| Cathode Direct | a DirecTV HR20 (2006): the sky-blue banner, the cyan guide, the colour keys |
| Cathode DSS | a DirecTV receiver from 1997: lavender pages, bevelled cells, 4:3 |
| Cathode Plate HD | Dish Network's 2007 guide: teal, charcoal and gold |
| Cathode Plate | Dish Network's 2005 receivers: grey pages and blue cells, 4:3 |
| Cathode Passage | a cable company's 2004 guide: a silver page, a purple grid, 4:3 |
| Cathode Cumcast | a cable company's 2006 guide: navy pages, steel channel tiles, 4:3 |

Every skin draws every screen its own way: menus, guide, banner, On Demand.
Any colour theme, the colour editor, any font, CRT scanlines and the
vignette work with all of them.

## Install

Every build carries libmpv; there's nothing else to install. Windows, the
AppImage, the Flatpak and Android update themselves (**Settings > Admin >
Check for updates**).

**Windows:** unzip `cathode-windows-5.3-portable.zip` and run **Cathode.exe**.

**Linux:** `cathode-linux-x86_64-5.3.AppImage` (make it executable and run
it), or the Flatpak:

```bash
flatpak install --user cathode-linux-x86_64-5.3.flatpak
flatpak run io.github.viviancross.Cathode
```

**Steam Deck:** install the Flatpak in Desktop Mode, then **Add a Non-Steam
Game** to run it from Game Mode with the controller.

**Android TV, Google TV, Fire TV:** sideload `cathode-android-5.3.apk` (with
Downloader, or `adb install`). For the 2023 onn 4K Google TV box, use
`cathode-android-onn-5.3.apk`: the same Cathode with its heavier extras
trimmed for that box's memory and processor.

**From source** (Python 3.10+, with libmpv installed):

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python main.py
```

On Windows, put `libmpv-2.dll` in a `_libmpv` folder next to `main.py`.

## Getting started

The first start walks you through it: pick your box and its colours, then
your channels. **From my Plex library** links Plex with a code at
plex.tv/link, asks for a ZIP code for the weather (optional), reads your
library, and shows the lineup it made. **From Tunarr, ErsatzTV or an M3U
link** takes a playlist address instead. You can have both.

## The remote

| Button | Keyboard | Controller |
|---|---|---|
| Channel up / down | Up / Down, PgUp / PgDn (by 10) | LB / RB, D-pad |
| Type a channel | 0-9 then Enter | |
| Guide | G | X |
| Info (twice: the full description) | I or Tab | Y |
| Menu | C | Start |
| Options (favourite, picture, subtitles, edit or cast this channel) | O | Back |
| Select | Enter | A |
| Back | Backspace | B |
| Previous channel | P | R3 |
| Browse / mini guide | B | |
| Favourite | F | |
| My Recordings | L | |
| Pause / rewind / fast-forward | Space / , / . | |
| Volume / mute | + - / M | LT / RT, L3 |
| Full screen | W or F11 | |
| Quit | Q | |

Media keys work as labelled, and every button can be remapped under
**Settings > Preferences > Remote control**. A FLIRC USB receiver learns any
infrared remote there. On Android the box's own remote works; Cathode asks
once to switch on its key service so the Guide and colour buttons reach it.
In the guide, INFO on a programme then SELECT offers to browse that channel
or put the show on another one.

## Settings

The Main Menu has Channel Search, the Sleep Timer and **Settings**, laid out
in tabs:

- **Channels:** add a channel (from your library, YouTube, or a stream
  address), live TV sources, packs, hidden channels, content groups, find a
  title, bulk edit, the starter lineup, and every channel's own editor.
- **Commercials:** what every channel's breaks are made of, the next-up
  card, the announcer, the break screen, which channels have breaks.
- **Schedule:** draw the schedule up afresh, read the library again, how far
  ahead the guide goes.
- **Design:** the box, its colours and lettering, screen effects.
- **Preferences:** subtitles, the channel logo, on-screen extras, sound,
  playback, the remote, the weather, YouTube.
- **Servers:** Plex, Jellyfin, Emby and folders.
- **Profiles:** who's watching, kids' profiles, the parent PIN.
- **Admin:** the phone remote, sync, sharing, continuous streams, export and
  import, the API key, backups, diagnostics, updates.

Off until you turn them on: the announcer, theme songs, continuous
streams, the API, the Video Store channel, pop-up trivia and random
marathons.

Settings live in `~/.config/cathode/config.json`. Put any extra mpv
option in `mpv.conf` beside it.

## For other apps

With **Share channels with other apps** on (Settings > Admin), your library
channels are on the phone remote's address (port 47810 on your network):
`/lineup.m3u`, `/xmltv.xml`, and as an HDHomeRun tuner for Plex's, Jellyfin's
or Channels' live TV. **Continuous Streams** makes each channel one stream
with its breaks, at `/live/<channel>.ts`. Nothing is served beyond your own
network.

Home Assistant and scripts: make a key under **Settings > Admin > API key**,
then `/api/v1/state`, `/api/v1/tune?number=`, `/api/v1/key?k=` and
`/api/v1/volume?level=`, with `Authorization: Bearer <key>`.

## Troubleshooting

- **No picture but sound:** put `hwdec=no` in `mpv.conf`.
- **A playlist's guide is empty:** its `tvg-id`s must match the XMLTV ids;
  Cathode falls back to names.
- **Logs:** Settings > Admin > Save diagnostics makes one zip of them (no
  passwords or tokens). The log is also on the phone page's Log tab.

## Building

```bash
python tools/build_all.py        # Windows zip, source zip, AppImage and Flatpak (Docker for Linux)
```

Android builds in its container on the `android-tv` branch
(`tools/build_android.py`; `CATHODE_FLAVOR=onn` for the onn box's build).

## License

Free, non-commercial software under the **GNU GPL v3** (`LICENSE`). Not
affiliated with Plex, DirecTV, Dish Network, NostalgiaTV, Tunarr or any
network or cable company; the boxes are original work in the style of the
period. Bundled fonts, libmpv and libraries keep their own licenses:
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and [`LICENSES/`](LICENSES/).
