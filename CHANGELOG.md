# Changelog

## 2.3

Bug-fix and hardening release (full sweep — see CODE_REVIEW.md).

- **Subtitle background:** new Audio & Subtitles ▸ Subtitle Background option
  (None / Shaded / Black) draws a box behind subtitles for readability.

- **Input routing rework:** every button, key, click, and scroll now goes
  through a single focus-owner dispatcher. Fixes a family of "dropped back to
  live TV" bugs: mouse wheel on the home screen / keyboard, digits and
  PgUp/PgDn during Plex playback, and the theme editor opening invisibly over
  Plex screens (which looked like a freeze). Bumpers no longer skip episodes
  while a dialog is open; Tab/Info during Plex playback shows the Plex bar.
- **Transcode fixes:** "Start from Beginning" now works at non-Original
  quality; resume points, Skip Intro timing, and timeline seeks are correct
  when a transcode starts mid-file.
- **Plex playback:** finished items are scrobbled (reliably marked watched);
  prev/next at the edge of an episode queue falls back to chapter skip;
  clicking the volume bar while muted unmutes; the progress-bar updater can no
  longer die when stopping and starting playback quickly.
- **Playlists:** M3U attributes containing commas (e.g.
  `group-title="News, Local"`) parse correctly; cancelling a playlist load
  returns to the home screen instead of a stale state.
- **Watchlist:** a failed refresh no longer loses your place when backing out.
- **Security / robustness:** Plex tokens are never placed in URLs; the config
  file is made owner-only on Linux; updates are verified against a published
  sha256 checksum when the release provides one; HTTPS certificate
  verification now works on macOS for weather/EPG/playlist/logo fetches too.
- **Housekeeping:** big EPG files use far less memory; logo/poster caches are
  capped; mpv's log file no longer grows unbounded (verbose logging is now the
  `mpv_verbose_log` config option); the changelog ships with the app.

## 2.2

- **Sequential episode play:** starting a single TV episode — from the show
  page or Continue Watching — now queues the rest of the show and keeps playing
  in order after it finishes (previously it stopped and returned to the info
  screen). Movies and the last episode of a show still play on their own.
- **Plex playback controls:** the gamepad bumpers and triggers now control the
  video instead of switching live‑TV channels.
  - Bumpers (LB / RB): skip to the previous / next episode (or chapter).
  - Triggers (LT / RT): jump 10 seconds back / forward.
