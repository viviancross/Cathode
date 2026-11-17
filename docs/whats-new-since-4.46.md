# What's new since Cathode 4.46

From 4.46 to 5.3 (November 2026), Cathode went from a box that plays other
people's channels to one that makes its own. It took on everything
NostalgiaTV does, in Cathode's boxes and with Cathode's remote, and then the
rest of NostalgiaTV's feature list. The version-by-version detail is in
`CHANGELOG.md`; this is the whole of it in one place.

| Version | In short |
|---|---|
| 4.47-4.58 | Library channels, scheduling rules, breaks, sync between Cathodes, lineup editing, the web page, profiles, Jellyfin, Emby and folders, backups |
| 5.0 | All of that as Cathode 5 |
| 5.1 | Plex-first setup, network replicas, real logos, screen bugs, episode details everywhere |
| 5.2 | Your Tunarr lineup as the starter, every title placed, the menus laid out as NostalgiaTV's |
| 5.3 | NostalgiaTV's remaining features, picked one by one; Android TV, Google TV and Fire TV |

## Channels made from your library

- **Library channels** (4.47). Cathode reads your Plex server (once, then
  only what changed) and makes channels from it, each a schedule you join
  in progress. No Tunarr needed.
- **More places than Plex** (4.57): Jellyfin and Emby servers, and folders
  on the computer. A title found in two places plays once, from Plex first
  or (5.3) from the better copy.
- **What a channel can play:** whole libraries, genres, decades, studios,
  ratings, shows, single movies and clips (5.2), seasons, single episodes,
  Plex collections and Plex playlists (5.3), and content groups: named sets
  used on any channel, so changing the group changes every channel with it
  (4.51).
- **Music libraries** (4.54) play as radio channels with the album art on a
  card, or (5.3) a visualizer, and can play a whole album at a time.
- **YouTube channels on the same schedule** (4.50): playlists and creators,
  with every rule below.
- **The starter lineup.** It began as genre and decade channels (4.47).
  In 5.1 it became network replicas, with their shows, dayparts and
  bumpers, plus HBO channels and 24/7s. Since 5.2 it is your own Tunarr
  lineup, with Tunarr's numbers, icons and screen bugs.
- **Every title has a channel** (5.2). A show or movie that no channel
  takes goes where it belongs: its network's channel, else the one it's
  most like. Never a grown-ups' title on a kids' channel. New arrivals are
  placed the same way, with a note of where they went.

## Scheduling

- **Eleven sort methods:**
  - shuffles: Random, Cyclic Shuffle;
  - blocks and marathons: Block Shuffle, Block Cyclic, Marathon Shuffle,
    Marathon Cyclic;
  - round robins: Round Robin Shuffle, Round Robin Cyclic;
  - order: Playlist Order, Whole Albums (5.3);
  - Mix (4.50): sources shared out by airtime, equally, or by weight.
  Every method keeps a show's place.
- **Written down a day at a time** (4.47), so episodes carry on in order
  across days and restarts. A file that won't play is skipped, and what
  follows moves up (4.48).
- **Rules** (4.50-4.51):
  - on-air hours, with the colour bars at sign-off;
  - time slots and dayparts, marathons;
  - seasons;
  - leave-outs, word filters, ratings, weights;
  - premieres;
  - a guide up to a month ahead.
- **More rules** (5.3):
  - **Timing:** pinned start times, premieres at chosen hours and nights
    (several back to back, with a pre-roll), grown-up ratings only after a
    set hour, a redirect to another channel's programmes in set hours.
  - **Order:** random marathons, two-part episodes back to back, holiday
    episodes only in their season, the first or a random episode to start a
    show, Start Shows Over.
  - **What plays:** a watched filter, specials on or off, a cap on movies a
    day, per-title weights, Mix balanced by count or by hours.
  - **Viewing it:** a running-order view of a channel's day.

## Commercial breaks

- **Breaks** (4.52) from your commercial and bumper libraries, lined up with
  the clock, between and during programmes. Bumper libraries are matched to
  their network. When no commercial fits the time left, a "we'll be right
  back" slate fills it.
- **5.3:**
  - lining up to 5 or 10 minutes;
  - a set number of commercials per break, or a running order;
  - hand-picked commercials;
  - idents apart from bumpers;
  - long videos (a show of old ads) cut into 30-90 second commercials;
  - music as commercials;
  - a coming-up-next card at the end of a break, and an optional announcer
    who reads it;
  - your own break screen;
  - mid-show breaks every 10, 15, 20 or 30 minutes, at Plex's chapter
    marks, or at the quiet moments where the show faded out for its own
    breaks.

## On screen

- **Episode details everywhere** (5.1): "S5E11 - Old Glory", air date,
  rating, picture and sound quality, length and score, in the banner, the
  INFO banner and the guide, in every box's own layout.
- **Logos** (5.1): your own channel logos (animated ones too), real network
  logos, and the screen bug in a corner of the picture. Each channel can set
  its own bug (5.2), shown always, on change or now and then, anchored to
  the screen or a 4:3 picture (5.3).
- **5.3:**
  - a TV rating box as a programme starts;
  - an up-next countdown;
  - tuning screens (static, black, blue, the logo);
  - seasonal decorations on the guide;
  - a TV-cabinet bezel (wood, black or silver).

## Special channels

- **Local Weather:** an almanac when there's no forecast (4.54). In 5.3,
  radar, today's outlook, and US weather alerts, with a red crawl over live
  TV for a severe one.
- **Video Store** (5.3): your movies on the shelves; browse New Releases,
  Staff Picks or a genre, and "rent" one.
- **Locked channels** (5.3): 18+ channels come through scrambled until the
  parent PIN.
- **Pop-up trivia** (5.3): who directed it, who plays whom, when it first
  aired, in bubbles during a programme.

## Playback

- **5.3:**
  - library channels mark what you watch in Plex and show in its dashboard;
  - pause, rewind and start-over on library channels;
  - "Are you still watching?" with an automatic sign-off;
  - forced subtitles and preferred subtitle and audio languages;
  - volume normalising and passthrough;
  - an `mpv.conf` for any other mpv option;
  - a choice of what to start on;
  - the preferred version of a title with several files.
- **On Demand** (5.3): Recommended rows, collections, trailers, and theme
  songs (off unless turned on).

## Your lineup, your menus

- **Lineup editing** (4.53): hide, rename and renumber channels (10.5 is
  fine), packs as guide tabs, no playlist at all, HDHomeRun tuners as
  playlists.
- **Menus laid out as NostalgiaTV's** (5.2), each box drawing them its own
  way:
  - Settings is Channels, Commercials, Schedule, Design, Preferences,
    Servers, Profiles and Admin;
  - every channel has one editor;
  - content is added by search, library, genre, decade, studio, show,
    rating or group;
  - Channel Search and a Sleep Timer sit on the Main Menu.
- **5.3:**
  - find a title on your channels;
  - bulk edit;
  - sort and reorder the list (LEFT/RIGHT on a channel moves it);
  - hide empty, starter or all channels;
  - copy or clear a channel's content;
  - a logo from a web address;
  - a stream address as a channel;
  - a playlist's number offset, auto-refresh and stream check;
  - in the guide, INFO then SELECT on a programme to browse its channel or
    put the show on another.
- **First run** (5.1): Plex first. Link, read the library, see the lineup
  it made, then watch.

## Around the house

- **Every Cathode on your network in step** (4.49): the same channels and
  the same programme at the same moment. Cast a channel, or a film from
  where it is, to another Cathode (5.3).
- **The web page** (4.55): a phone remote, what's on, the lineup and channel
  settings, with its address shown as a QR code (5.0).
  - In 5.3 it gains Plex's now playing, the log, the full channel editor,
    and export and import.
  - Sharing with other apps (M3U, XMLTV, HDHomeRun); in 5.3, continuous
    streams with the breaks, off unless turned on.
  - An API key for Home Assistant and scripts (5.3).
- **Profiles** (4.56): each with its own look and favourites, kids'
  profiles, a parent PIN, and the watch history.
- **Backups** (4.58): back up and restore settings, plus a weekly backup of
  its own. Sign-ins stay out of it.
- **Export and import** of your channels, merged or replacing (5.3).

## Android

The `android-tv` branch carries all of 5.3 in two builds:

- **The main APK** for Android TV, Google TV and Fire TV (Android 8 and
  up, 64- and 32-bit ARM), every feature on. Fire TV gets its own remote
  profile, and its Menu, Play/Pause, Rewind and Fast Forward keys work.
- **The onn APK** for the 2023 onn 4K Google TV box. It is the same
  Cathode with the heavier extras trimmed for that box: 720p drawing,
  smaller caches, a day of listings, lighter visualizers, no sound-reading
  for mid-show breaks.

## Off until you turn them on

The announcer, theme songs, continuous streams, the API, the Video Store
channel, pop-up trivia, random marathons and mid-show breaks are yours to
switch on. Breaks between programmes,
the screen bug, the rating box, the up-next countdown and the guide's
seasonal decorations start on.
