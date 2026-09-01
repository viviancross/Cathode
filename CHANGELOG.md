# Changelog

## 3.0

- **Poster wall:** Plex libraries can be browsed as a grid of artwork instead of
  a list — **Options ▸ View** switches between them, and the choice sticks. The
  grid sizes itself to the window, tiles carry a resume bar for anything part
  way through, and only the artwork actually on screen is ever fetched.
- **Faster interface:** the overlay pipeline was rebuilt around Pillow's own
  BGRA packer and a persistent file handle, cutting a full UI frame from 91ms to
  34ms at 1080p (43ms to 15ms at 720p).
- **Layout fixes throughout:** the guide header no longer overprints itself at
  narrow widths, its time ruler thins its labels instead of colliding, and its
  video preview is 16:9 in every box. The Plex bar, the theme editor's sliders,
  the on-screen keyboard, the home screen's footer and the stand-by card were
  all overflowing their boxes at some window size; each now measures its text
  and fits. The guide gained a visible **X CLOSE** button.
- **Menus:** every menu page now has a way out at the bottom, not only submenus,
  and the panel is opaque so it no longer reads as two menus stacked on the home
  screen.
- **Updates only follow the desktop release line.** The Android, Tizen, PS2 and
  Miyoo ports publish to the same repository, and the update check could offer
  one of their releases — or, worse, install a build from one. It now reads only
  releases tagged as a plain version, and only accepts an asset named for this
  build.
- **Ultrawide displays:** `ui_max_aspect` in the config keeps the interface
  TV-shaped and centred instead of stretching the menus away from the video.
  Off by default.
- **Gamepad:** button actions no longer fail when the native reader is disabled.
- **Secondary text belongs to its theme.** Captions, metadata, hints and
  disabled labels used one fixed gray on all nine themes — a cool gray sitting
  inside Amber CRT's warm world, and one that measured below the readable bar on
  Commodore, Amber and Green Phosphor. It is now derived per theme and solved
  for contrast, so it holds up on custom palettes from the theme editor too.
- **Progress bars read as bars again.** The unfilled part of a progress or
  volume bar shared that same gray, so one value had to be both readable text
  and a recessive track. They are now separate.
- **The primary action stays primary.** On a Plex detail page, PLAY kept no
  emphasis of its own once the cursor moved to another button; it now holds an
  accent ground whatever the cursor is doing.
- **Library lists read faster at ten feet.** Titles carry full ink against muted
  metadata, instead of the two sitting a hair apart.
- **The CRT is the whole app now.** The home screen, the library browser and
  item detail pages were rendered flat — the scanlines and vignette only ever
  reached live TV, the guide and Plex playback, so walking into a menu walked
  out of the television. Every screen is now behind the same glass, including
  the context menu and on-screen keyboard, which used to stay crisp on top of a
  scanlined page.
- **A better tube.** Scanlines have a soft falloff instead of switching hard
  between black and clear rows, and their pitch follows the screen: the old
  fixed one-pixel line was a coarse stripe at 480p and an invisible, shimmering
  hairline at 4K. A faint shadow-mask texture runs under them, and the vignette
  now leaves the middle of the picture alone and rolls off at the edges the way
  a real tube does, rather than greying the whole screen evenly.
- **Faster with the effects on.** Scanlines and vignette are flattened into one
  layer, so a frame composites once instead of twice — about 40% less work per
  frame on every screen that already had them.
- **Tofu boxes in the interface.** The bundled pixel fonts have no em dash, so
  messages written with one — the update notice, the wrong-PIN warning, the
  signed-out menu row — drew a literal empty box in the middle of the sentence
  on the default font. All the text the app draws is now checked against the
  fonts that ship with it.
- **Progress bars match each other.** The channel bar, the Plex scrubber, the
  volume bars and the theme editor's sliders each drew their own unfilled track,
  two of them in a fixed near-black that ignored the theme. They share one now,
  and the update-download bar has a track at all — it used to be an empty
  outline that looked broken at 0%.
- **One dim behind dialogs.** The context menu and the confirm dialog pushed the
  background back by different amounts.
- **Messages arrive instead of blinking.** The toast that reports "Queued",
  "Added to Favorites" or an available update used to appear and vanish between
  one frame and the next, so a message replacing another one was easy to miss.
  It now drops in from the top edge and lifts back out — 160ms in, 120ms out.
- **Motion can be turned off.** A new **Motion** toggle sits with CRT Scanlines
  and Vignette in the theme editor; with it off every transition resolves
  straight to its end state. It is a comfort setting rather than part of a
  theme, so it saves the moment you set it and is not carried into saved themes.
- **Large libraries no longer freeze the browser.** Landing near the end of a
  long list re-measured the whole list on every step, so returning from an item
  near the bottom of a 5,000-title library locked the interface for about seven
  seconds. Opening one also measured every title up front. Both are now bounded
  by what's on screen: opening a library and jumping to its end are as quick at
  20,000 titles as at 100.
- **A bad channel logo can't take the app down.** Logo URLs come from whatever
  XMLTV or M3U you loaded, and were downloaded with no size limit and decoded
  with no dimension limit — so a single oversized or deliberately-crafted image
  could exhaust memory. Downloads now stop at 8 MB, images are refused on their
  header if they'd decode to something absurd, and nothing that fails is left in
  the cache. A refused logo just means that channel shows without art.
- **The set turns off.** Quitting cut straight to black. The picture now
  collapses the way a tube does — squashing into a bright horizontal line, the
  line pinching to a dot, the dot fading. It takes under half a second, happens
  on the way out where nothing is waiting on it, and respects the Motion
  toggle.

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
