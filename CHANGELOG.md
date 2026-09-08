# Changelog

## 3.1

- **The DVR:** download a Plex item to this device and watch it with the server
  unreachable. **DVR** on an item's info page starts a copy, the button tracks
  it (`DVR 42%`, then `ON DVR`), and a **DOWNLOADS** row appears in the library
  list once there's something in it. Downloads are always the original file
  rather than a transcode, because a transcode is sized for the network it was
  asked for on and a download outlives that network. One at a time, resumed with
  a Range request rather than restarted, and the index holds no Plex token.
- **Plex-Per-View works offline.** Open it with no network and whatever is
  already downloaded is on screen immediately, marked OFFLINE, instead of
  waiting out a connection timeout to show nothing. A downloaded copy is also
  preferred over the stream whenever one exists, server up or not.
- **Downloads live with your other videos:** `~/Videos/Cathode` on Windows and
  Linux (following the XDG videos directory where it's set, so a localised
  desktop gets its own name), `~/Movies/Cathode` on macOS. `download_dir` in the
  config overrides it.
- **The info screen poster no longer runs into the buttons.** At 1920x1080 it
  overlapped the button row by 21 pixels. The poster now gives up height, and
  width with it, so it keeps its 2:3 shape.
- **Button labels can't overflow their buttons.** A six-button series page at
  640 wide shrank its text as far as the floor allowed and then drew "-
  WATCHLIST" across its neighbours anyway.

## 3.0

- **Poster wall:** Plex libraries can be browsed as a grid of artwork instead of
  a list. **Options ▸ View** switches between them and the choice sticks. The
  grid sizes itself to the window, tiles carry a resume bar for anything part
  way through, and only the artwork actually on screen is ever fetched.
- **Updates follow the desktop release line only:** the Android, Tizen, PS2 and
  Miyoo ports publish to the same repository, and the update check could offer
  one of their releases — or install a build from one. It now reads only
  releases tagged as a plain version, and only accepts an asset named for this
  build.
- **The CRT is the whole app:** the home screen, the library browser and item
  detail pages were rendered flat, so walking into a menu walked out of the
  television. Every screen is now behind the same glass, including the context
  menu and on-screen keyboard. The scanlines themselves are better: a soft
  falloff rather than hard alternating rows, at a pitch that follows the screen
  instead of a fixed one-pixel line that was coarse at 480p and an invisible
  shimmer at 4K. A faint shadow-mask texture runs under them, and the vignette
  leaves the middle of the picture alone.
- **Faster interface:** the overlay pipeline was rebuilt around Pillow's own
  BGRA packer and a persistent file handle, cutting a full UI frame from 91ms to
  34ms at 1080p (43ms to 15ms at 720p). Scanlines and vignette are now one
  layer, so a frame composites once instead of twice.
- **Large libraries stay responsive:** landing near the end of a long list
  re-measured the whole list on every step, so returning from an item near the
  bottom of a 5,000-title library locked the interface for about seven seconds.
  Opening a library measured every title up front. Both are now bounded by
  what's on screen — 20,000 titles cost what 100 did.
- **A bad channel logo can't take the app down:** logo URLs come from whatever
  XMLTV or M3U you loaded, and were downloaded with no size limit and decoded
  with no dimension limit, so one oversized or crafted image could exhaust
  memory. Downloads stop at 8 MB, images are refused on their header if they
  would decode to something absurd, and nothing that fails is cached. A refused
  logo means that channel shows without art.
- **Secondary text belongs to its theme:** captions, metadata, hints and
  disabled labels used one fixed gray on all nine themes — a cool gray sitting
  inside Amber CRT's warm world, and one that measured below the readable bar on
  Commodore, Amber and Green Phosphor. It is now derived per theme and solved
  for contrast, so it holds up on custom palettes from the theme editor too.
- **Progress bars:** the channel bar, the Plex scrubber, the volume bars and the
  theme editor's sliders each drew their own unfilled track, two of them in a
  fixed near-black that ignored the theme. They share one now, and the
  update-download bar has a track at all — it used to be an empty outline that
  looked broken at 0%.
- **Clearer hierarchy:** on a Plex detail page, PLAY kept no emphasis of its own
  once the cursor moved to another button; it now holds an accent ground
  whatever the cursor is doing. In library lists, titles carry full ink against
  muted metadata instead of the two sitting a hair apart.
- **Layout fixes throughout:** the guide header no longer overprints itself at
  narrow widths. Its time ruler thins its labels instead of colliding, and its
  video preview is 16:9 in every box. The Plex bar, the theme editor's sliders,
  the on-screen keyboard, the home screen's footer and the stand-by card were
  all overflowing their boxes at some window size; each now measures its text
  and fits. The guide gained a visible **X CLOSE** button.
- **Tofu boxes in the interface:** the bundled pixel fonts have no em dash, so
  messages written with one — the update notice, the wrong-PIN warning, the
  signed-out menu row — drew a literal empty box mid-sentence in the default
  font. All the text the app draws is now checked against the fonts that ship
  with it.
- **Menus:** every menu page has a way out at the bottom, not only submenus, and
  the panel is opaque so it no longer reads as two menus stacked on the home
  screen. One dim behind dialogs, too: the context menu and the confirm dialog
  used to push the background back by different amounts.
- **Motion:** messages arrive instead of blinking — the toast that reports
  "Queued" or an available update drops in from the top edge and lifts back out,
  160ms in and 120ms out. Quitting no longer cuts to black; the picture collapses
  the way a tube does, squashing into a bright line that pinches to a dot. A new
  **Motion** toggle sits with CRT Scanlines and Vignette and resolves every
  transition straight to its end state. It saves the moment you set it, and is
  not carried into saved themes.
- **Ultrawide displays:** `ui_max_aspect` in the config keeps the interface
  TV-shaped and centred instead of stretching the menus away from the video.
  Off by default.
- **Gamepad:** button actions no longer fail when the native reader is disabled.

## 2.6

- **Play queue:** a **Play Queue** entry in the Plex context menu lists what's
  lined up and marks what's playing. Open any entry to play it now, move it up
  or down, or remove it; clear the whole queue from the bottom of the list.
- **Add to queue:** item info screens gained a **+ QUEUE** button — on a series
  it queues every episode. A queue you built by hand is no longer thrown away
  when you play something else; that item just plays first, then the queue
  follows.
- **Sort by release date:** libraries can now sort on the actual release date,
  not only the year, and each library reopens with the sort you left it on. The
  sort list also gained a **Default** entry to undo a sort, and its labels were
  shortened so options no longer truncate into each other.
- **Info screen fit:** the detail-page buttons shrink their text to fit their
  boxes, so a six-button series page stays readable down to a 640px-wide window.

## 2.5

- **First-run setup wizard:** first launch walks three skippable steps — pick
  a look (themes preview live), add a playlist, sign in to Plex. Skip
  everything and you land in the built-in demo channels instead of a blank
  screen. Rerunnable from Options ▸ Setup Wizard.
- **First run:** with no playlist configured, the home screen also says so and
  offers a **Demo Channels** button (built-in test-pattern channels — the same
  set as the `--demo` flag) so there's something to watch before setup.
- **Verified updates:** releases now ship a `.sha256` checksum file next to
  each zip; the built-in updater verifies downloads against it.

## 2.4

- **Please Stand By:** a dead channel now fades from static into an SMPTE
  test-bar card ("PLEASE STAND BY — NO SIGNAL") instead of dead air; it clears
  itself if the stream ever delivers a frame.
- **VCR transport tags:** Plex playback flashes a green "PLAY >" tag on start
  and resume; while paused, a "|| PAUSE" tag stays on screen with a slowly
  drifting tracking band, like a paused tape.
- **Screensaver:** after 5 idle minutes on the home screen or guide, a bouncing
  CATHODE wordmark takes over (corner hits change its color). Any input wakes it.
- **Degauss:** click the logo on the home screen.
- **Night sky:** the guide's weather icon shows the moon — at its real current
  phase — on clear/partly nights.
- **Off-air motif:** empty and error states (empty guide category, empty Plex
  levels) show a small test-bar strip; readability fixes: selection/on-air text
  now stays legible on every theme (light-accent themes get dark ink), all
  full-screen pages tint toward the theme's background, the Plex-Per-View
  breadcrumb moved under the level title, the on-screen keyboard shows
  controller caret hints, and the Plex control bar starts focused on
  play/pause instead of the timeline.
- **Quicker tuning:** pressing Enter (or A) tunes a typed channel number
  immediately instead of waiting out the entry timeout; an on-screen hint says
  so. Favorited channels now show a `*` badge on their guide rows.

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
