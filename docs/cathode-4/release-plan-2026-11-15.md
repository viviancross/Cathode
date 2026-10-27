# Cathode 5 by November 15

Agreed 2026-10-27. Nineteen days. After November 15 there is no more agent
time, so the rule is: nothing lands half-finished, and the last five days
belong to release mechanics, not features. Feature freeze is November 10;
anything not done by then goes to 5.1.

## Where things stand

| Line | State |
|---|---|
| Desktop / Deck (`main`, 4.31) | The October plan's feature work is done: one-address setup, diagnostics zip, boot sequences, channel-change feel, HR20 sounds, banner polish, provider (Xtream) lines, guide cursor and pop-ups, one-command builds. |
| Open bugs | Strong8K guide still empty on 4.31 (needs a diagnostics zip: the log now says what the XMLTV and the API covered). On Demand audio glitch unconfirmed since 4.27's audio fixes. |
| QA | Cold installs on Tunarr and ErsatzTV, keyboard and pad, not done. |
| Android TV (`android-tv`) | Runs on the emulator end to end; not yet on a box. Debug-signed; release signing wired but untested. |
| Release plumbing | 5.0 bump, `FOLLOW_PRERELEASES = False`, release notes, README refresh: not started. |

## What 5.0 adds

Chosen for a Tunarr / ErsatzTV household, in the order they get built.

### Fixes
- **ErsatzTV channel numbers like 10.5.** Channel numbers are whole numbers today and the playlist's `tvg-chno` goes through `int()`, so a decimal lineup breaks. Decimals through the keypad, guide and banner.
- **The lineup refreshes itself.** The guide reloads every six hours; the channel list only at start. Reload the playlist on the same schedule, so a channel added in the server's web UI appears without a restart.
- **Strong8K guide**, from the user's next diagnostics zip.

### The guide knows what the server knows
- **Guide posters.** Tunarr and ErsatzTV schedule Plex items and their APIs say which; each programme gets its poster, summary and rating in the INFO pop-up and banner. Research first: which of the two servers' guide or API carries the item id. "Start over" (play the item from its beginning) and "Watch later" (the Plex watchlist) ride on the same mapping if the research holds.
- **Rating bug.** "TV-PG" in the corner for the first seconds of a programme, from Plex's rating.
- **Up next bug.** Near the end of a programme, a brief corner mark naming what's next on this channel. (Chosen over a commercial-break countdown.)

### Cathode's own channels
One framework: a screen that takes a channel number, sits in the lineup and the guide like any channel, and draws itself instead of playing a stream.
- **The TV Guide channel.** Prevue-style: the current picture in the top half, the grid scrolling through every channel's now and next in the bottom half, in that blue-and-yellow look.
- **The Weather channel.** Local-on-the-8s pages from the weather feed Cathode already has: current conditions, the outlook, the hourly rain chance, the clock.
- **Music channels.** A Plex music library as Music Choice-style channels: shuffled playback with the static card of artist, album art, title and a line of trivia; one channel per genre or playlist.

### Setup and control
- **Phone companion.** A page Cathode serves on the LAN, address and QR code in Settings: a channel keypad, every remote button, a real keyboard for playlist links and Plex logins. Its HTTP endpoints are a documented control API (Home Assistant, curl).
- **Find the server on the LAN.** Setup scans for Tunarr and ErsatzTV and offers what it finds, so a Deck or TV box needs no typing.
- **Editable channel lists.** Hide, renumber, custom lists, which list the guide shows ("Channels I Get"). What makes a 21,000-channel provider line usable.

### Android TV
Ships beside 5.0 as `android-v5.0`, labelled a beta: one APK, arm64, Android 8+, leanback launcher. Needs the box test (mediacodec video, audio, frame pacing, remote keys), release signing with the existing keystore, and a README note. No self-update; Settings says when a release is out.

## Calendar

| Days | Work |
|---|---|
| Oct 27 to 28 | Strong8K from the zip (4.32). Decimal numbers, lineup refresh. Server API research, then guide posters with the rating and up-next bugs. |
| Oct 29 to 31 | Channel framework, TV Guide channel, Weather channel. Alpha 4.33. |
| Nov 1 to 3 | Music channels. Phone companion and API. Android box pass as reports arrive. |
| Nov 4 to 6 | Editable channel lists. LAN discovery. Start over / watch later if the research allowed. Alpha 4.34. |
| Nov 7 to 10 | Cold-install QA: Tunarr, ErsatzTV (Docker), keyboard, pad, Deck Game Mode. On Demand audio check. Fix round. Android signing and box pass two. Freeze at the end of Nov 10. |
| Nov 11 | Release notes ("Cathode 5", the story from 4.0 for people who never saw an alpha), README with screenshots, LICENSE and notices check. |
| Nov 12 to 13 | 5.0 release-candidate builds: four desktop artifacts and the signed APK, audited. Final pass on the RC. |
| Nov 14 | The user publishes `v5.0` and `android-v5.0`. |
| Nov 15 | Buffer: a hotfix build if the day needs one. |

## Release checklist (Nov 11 onward)
- `__version__ = "5.0"`, README version line, `FOLLOW_PRERELEASES = False`.
- CHANGELOG: a 5.0 section telling the story from 4.0, the 4.x sections kept below.
- README: what it is, the three skins with screenshots, the one-address setup, Tunarr and ErsatzTV named, install per platform, Android TV, the phone companion.
- LICENSE, THIRD_PARTY_NOTICES.md, LICENSES/fonts: present and current.
- `tools/build_all.py --android`: five artifacts, audited, sha256 sidecars.
- Tags: `v5.0` on the desktop commit, `android-v5.0` on the Android commit. The user publishes both.

## 5.1 list (considered, not in 5.0)
Demo channels on first run; sleep timer; picture adjustments; "what's new" in the mail; Continue Watching on On Demand; autotune reminders; the spin-up poster card on channel change; On Now wall; channel bug; Previews channel; Jellyfin On Demand; DVR (background recording); multiview; signal meter; two servers in one lineup; standby on POWER; box-style notices; T9 channel search; cast / voice typing / QR sign-in on the companion page; per-channel audio and subtitle memory; live preview in the guide; jump to a time; ambient screensaver; recently watched; Trakt; a folder as a source; parental locks; favourites lists 1 to 4; commercial-break countdown.

## Needed from the user
- A diagnostics zip from 4.31 after opening the guide on the Strong8K line.
- The Android APK on the box, and `adb logcat -s python` from the first run.
