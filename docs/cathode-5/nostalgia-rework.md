# The NostalgiaTV rework

Started 2026-11-15. The aim: everything NostalgiaTV does, inside Cathode, without
losing what makes Cathode its own. This file is the plan and the running status;
update the Status column as phases land.

## Ground rules

- **Clone what it does, not what it is.** Features and behaviour are fair game. Its
  name, artwork, theme designs and its made-up network names are not copied. The
  starter lineup's channels carry placeholder names of our own.
- **Windows and the Steam Deck first.** The other builds follow later; nothing is
  held back or trimmed for them now.
- **No dates.** The phases are an order, not a calendar.
- **What stays Cathode.** The seven real-box skins, the tube and CRT, the TV Guide
  and Weather channels, YouTube video channels, Spelunkr, IPTV playlists and Tunarr,
  the remote profiles and FLIRC, the ports. New features are drawn by the skins,
  never as a generic overlay.
- **Remote first.** Everything works from the couch with a D-pad. The browser page
  (phase 7) is the comfortable way to do the fiddly parts, not the only way.
- **No Tunarr required.** A box with only a Plex sign-in must end up with a full
  lineup. Tunarr and playlists keep working beside it.
- Lands in slices on `main`, each one finished, tested and versioned (4.47 on).

## Where NostalgiaTV's features map

Source for its feature list: the store listing, the server's README, one review
and the developer's post (links at the foot). Nobody here has run the app.

| NostalgiaTV | Cathode today | Plan |
|---|---|---|
| Channels built from Plex libraries, in the app | Needs Tunarr | Phase 1 |
| Ready-made themed channels (85+) | Spelunkr, YouTube prefill | Phase 1: a starter lineup made from your own library |
| Custom channels: library, collection, playlist, genre, decade, studio, label, picked titles | YouTube sources only | Phase 1 (library, genre, decade, studio, show), phase 2 (the rest) |
| Nine sort methods | Shuffle by weight | Phase 1 |
| Join in progress, 24/7 schedule, 7/14/30 days | Yes for video channels (1 day) | Phase 1 |
| Time slots, restricted hours, exclusions, weights | Weights only | Phase 2 |
| Marathons, premieres for new arrivals, seasonal lineups | No | Phase 2 |
| Kid / mature filtering | No | Phase 2 (by content rating) |
| Content Groups (named reusable sets) | No | Phase 2 |
| Commercial groups, break sequences, padding | Spelunkr's own breaks | Phase 3 |
| Mid-show breaks: halfway, chapters, silence | Spelunkr's cut points | Phase 3 (halfway, chapters), silence later (needs ffmpeg) |
| "Be right back" screens | No | Phase 3, drawn per skin |
| Weather channel | Yes (local on the 8s) | Keep; phase 4 adds the offline almanac fallback |
| Music radio channels with a visualizer | YouTube music videos | Phase 4 (Plex music by genre, now-playing card) |
| Trailers "What's On" channel, trailer pre-rolls | No | Phase 4 |
| Live stream channels, M3U / XMLTV import | Yes | Keep |
| HDHomeRun import, Plex / Jellyfin Live TV | No | Phase 6 |
| Channel packs (guide tabs), favourites | Favourites, categories | Phase 5 |
| Hide, reorder, renumber | No | Phase 5 (also decimal numbers) |
| Jellyfin, Emby, local folders, duplicate hiding | Plex only | Phase 6 |
| Web Configure, Watch and TV Remote pages | No | Phase 7 |
| Tuner output: HDHR, M3U, XMLTV, stream | No | Phase 7 (feeds Cathode's thin ports too) |
| Profiles, kid profiles, parent PIN, tether | Plex Home users | Phase 8 |
| Watch history dashboard | No | Phase 8 |
| Ten guide themes, theme designer, fonts | Seven box skins, themes, fonts per skin | Keep ours; phase 9 adds bezels |
| CRT effects, tuning animation, retro sounds | Yes | Keep |
| On Demand, search, Continue Watching, skip intro, subtitles | Yes | Keep |
| Config export / import, weekly backup | No | Phase 9 |
| Five languages | English | Last, if wanted |
| Docker companion server, device sync | No | Phase 7's server, run by any Cathode on the LAN |

## How it's built

```
plex.py ──► library.py ──► libchannels.py ──► videochannels.Player ──► mpv
            (the index)    (channels, the      (already plays YouTube
                            day's running       and Spelunkr timelines)
                            order, guide)
```

- **`library.py`: the index.** One compact file per Plex library in the cache
  folder: movies and clips (key, title, seconds, year, genres, studio, rating),
  shows and their episodes (season, number, air date). Fetched 2000 at a time off
  the UI thread, again when Plex says the library changed. 40,000 episodes take
  about 25 seconds the first time.
- **`libchannels.py`: channels.** `config.library_channels` holds each channel:
  name, number, sources, sort method, later its slots and breaks. A source is
  `{kind, section, value}`: a whole library, a genre, a decade, a studio, a show.
- **The running order is written down, a broadcast day at a time** (4 AM to 4 AM),
  seven days ahead, in the cache folder with the rotation state it ended on. The
  next day continues from that state, so episodes carry on in order across days
  and restarts. Editing a channel rewrites today onward; a changed library
  rewrites tomorrow onward.
- **Playing.** Each entry is `{id, plex, title, duration, kind, in}`. The existing
  `Player` tunes in at the right offset; a library entry's stream is asked of Plex
  at that moment (direct play, or the Plex quality setting's transcode from the
  offset). A file that won't play is skipped: the next title starts at once and
  the days drawn up close over it (4.48). The stand-by card is for the server
  being away.
- **Guide.** One listing per programme with its summary, episode number and
  poster; breaks belong to the programme before them, as Spelunkr's do.

### The nine sort methods, as built

NostalgiaTV names them without defining them. These are our definitions.

| Method | What airs |
|---|---|
| Random | Any title, any time; nothing repeats within its last 20% |
| Cyclic Shuffle | Every title once, shuffled, then a fresh shuffle |
| Block Shuffle | A block of N episodes of one show in order, then a random other show |
| Block Cyclic | The same, shows taking turns in a fixed order |
| Marathon Shuffle | One show for hours (N episodes, default 12), then a random other show |
| Marathon Cyclic | The same, shows in a fixed order |
| Round Robin Shuffle | One episode of each show in turn, the order of shows reshuffled each round |
| Round Robin Cyclic | One episode of each show in turn, fixed order |
| Playlist Order | Exactly as listed: shows by title, episodes in order, movies by year |

Every method keeps each show's place: its next episode is the one after the last
it aired, on any channel using that method.

## Phases

| # | Phase | Done when | Status |
|---|---|---|---|
| 1 | Library channels | Sign in to Plex, get a starter lineup; tune lands mid-programme; guide lists the days ahead; make and edit a channel with the remote; all nine sort methods | Built in 4.47, not yet watched on a TV (see below) |
| 2 | Rules | Time slots, restricted hours with sign-off, exclusions, weights, marathons, premieres, seasonal lineups, kid filter, content groups, schedule length 7/14/30 | |
| 3 | Breaks | Commercial groups from any library; bumper-commercial-bumper sequences; padding to :00/:15/:30; halfway and chapter breaks; be-right-back card on every skin | |
| 4 | More channels | Trailers channel and pre-rolls; Plex music radio with a card; weather almanac fallback | |
| 5 | Lineup editing | Hide, reorder, renumber, decimal numbers, channel packs as guide tabs | |
| 6 | More sources | Jellyfin and Emby behind the same index; local folders; duplicate hiding; HDHR import; Plex Live TV | |
| 7 | Server and pages | Built-in web server: Configure, Watch, TV Remote; M3U, XMLTV, HDHR and stream output | |
| 8 | Profiles | Profiles with their own lineup and look, kid profiles, parent PIN, tether, watch history | |
| 9 | Housekeeping | Export / import, weekly backup, bezels, languages if wanted | |

### Phase 1 as it stands (4.47)

Built and tested: `cathode/library.py`, `cathode/libchannels.py`, the hooks in
`videochannels.py` (`Player._hold`, the Plex branch of `start`), `plex.py`
(`library_sections`, `section_page`, `stream_at`), Settings > Channels > Library
Channels, `tests/test_library.py`. Checked against the real server without the
window: 56,448 titles in 31 libraries read in about 14 seconds the first time
and 3 after; 67 starter channels; a stream answered for the title on the air.

Still open in phase 1:

- Nobody has watched it. Tune to a library channel, let a programme end, check
  the guide and a poster on each skin.
- A box with no playlist at all gets no lineup, so no library channels. Spelunkr
  ships as the default playlist, which hides this; phase 5 fixes it properly.
- The guide lists 48 hours, as video channels do. Schedule length (7/14/30 days)
  is phase 2.
- Collections, playlists, labels and hand-picked titles as sources: phase 2.

## Decisions taken without asking (say if any are wrong)

- Library channels sit after the lineup in a block of their own, from the next
  hundred up (a lineup ending at 69 puts them from 101).
- The starter lineup is generated from what the library holds: a channel per genre
  with enough hours, per decade, per studio or network with enough shows, a
  marathon channel for each long-running show, and movie channels. It never
  touches a channel you've edited.
- Libraries that look like bumpers or commercials (Plex "Other Videos" whose
  median clip is under 150 seconds) are kept out of programme channels and offered
  as break material in phase 3. Libraries hidden from On Demand are indexed but no
  channel takes them unless it names one.
- The starter lineup is added once, automatically, the first time the library is
  read. One menu row removes it.
- Jellyfin and Emby were turned down in October; they're in the plan now because
  the request is everything, but they come after the Plex path is complete.

## Sources

- https://appgoblin.info/apps/com.nostalgiatv
- https://hub.docker.com/r/purestream711/nostalgiatv-server
- https://blog.lon.tv/2026/02/21/the-nostalgia-tv-for-plex-app-turns-your-plex-meida-into-a-retro-cable-tv-experience-sponsored-post/
