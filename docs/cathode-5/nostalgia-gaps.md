# NostalgiaTV gaps: what the user picked (2026-11-17)

Picked from the gap list (picker widget, 2026-11-17). Built into 5.3 (5.2 built 2026-11-17 as committed at 45d96ea)
phase by phase, each committed locally with tests. Status: [ ] todo, [x] done.

## A. Channel content (libchannels, library)
- [x] Plex collections as content (source kind `collection`)
- [x] Plex playlists as content (kind `playlist`)
- [x] Single seasons or episodes (kind `season`; `title` takes episodes)
- [x] Watched filter (per channel: all / unwatched / watched)
- [x] Multi-part episodes together (Part 1 → Part 2 back to back)
- [x] Start shows from their first episode (channel action)
- [x] Max movies per day
- [x] Grown-up ratings only after a set hour
- [x] Specials on/off per channel
- [x] Random marathons
- [x] Channel redirect at set hours (simulcast another channel)
- [x] Copy content from another channel; clear content
- [x] Bulk edit channels
- [x] Channel sort and manual reorder
- [x] Hide empty / hide starter / hide all
- [x] Find a title on channels
- [x] Guide long-press (INFO, then SELECT): browse channel, add show to a channel
- [x] Logo from a web address
- [x] A single live stream URL as a channel
- [x] Preferred copy for duplicates

## B. Scheduling
- [x] Pin a show or movie to an exact start time
- [x] Per-title weights; balance by count or duration
- [x] Premieres: several times, pinned nights, back-to-back, pre-roll
- [x] Seasonal cycler (holiday episodes only in their season)
- [x] Hour timeline with ad breaks (running order view)

## C. Breaks
- [x] 5 and 10 minute alignment
- [x] N commercials between shows; commercials per break
- [x] A TV show as commercials (long items cut into break-sized pieces)
- [x] Hand-picked commercials, running order
- [x] Custom break screens
- [x] Coming up next card between shows
- [x] Announcer voice
- [x] Idents apart from bumpers
- [x] Mid-show breaks at chapter markers
- [x] Mid-show breaks at silences
- [x] Fixed-interval mid-breaks
- [x] Music clips as commercials

## D. On screen
- [x] Up-next countdown
- [x] Logo modes: on change, periodic, always
- [x] Rating box at programme start
- [x] Logo anchored to the 4:3 picture edge
- [x] Seasonal decorations
- [x] Tuning screen choices
- [x] Bezels (TV frame round the picture)

## E. Playback
- [x] Mark channel viewing watched in Plex; now-playing status
- [x] Start the programme from its beginning
- [x] Pause and skip back on library channels
- [x] Are you still watching auto sign-off
- [x] Forced / foreign-audio subtitles, default languages
- [x] Audio normalization and passthrough
- [x] Custom mpv.conf
- [x] Start on first channel or On Demand
- [x] Preferred version (of an item with several files)

## F. Special channels
- [x] Weather radar, hazards, more forecast screens
- [x] Severe weather alert crawl
- [x] Music visualizers; whole-album order
- [x] Rent mode video-store channel
- [x] Locked 18+ channel, scrambled picture
- [x] In-show pop-ups and trivia

## G. Admin web
- [x] Channel export / import (merge or replace)
- [x] Playlist auto-refresh, number offset, health
- [x] Dashboard of what's playing on the servers
- [x] Log viewer
- [x] Full channel editor in the browser
- [x] API keys and endpoints (Home Assistant)
- [x] Continuous broadcast stream with breaks for other apps (off by default: Admin > Continuous Streams)

## H. Platforms
- [x] On Demand: collections, recommended rows, trailers, theme songs
- [x] Cast to another Cathode
- [ ] Finish the Android TV and Fire TV build (branch android-tv)
