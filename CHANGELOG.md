# Changelog

## 4.38

- **FLIRC wizard: skipping with the remote.** Pressing a button the FLIRC
  already knows skips the step (it refuses the button; the wizard takes the
  hint), so the walk-through needs no keyboard. The RIGHT key still skips.
- **Video Channels: no cut heads.** A video due within the last 20 seconds
  plays from its top instead of from the offset that resolving and opening
  it cost; the next is due at its stop regardless (a late start loses its
  tail, not the next one's head), so lateness doesn't pile up.

## 4.37

- **A FLIRC wizard.** Settings > Remote control > FLIRC receiver teaches a
  FLIRC USB receiver any remote: a walk-through asks for every button in
  turn (by the chosen remote's own names), RIGHT skips one; Record one
  button, Forget a button, Test the buttons (each names itself: watch the
  TV too, and forget a button it answers), built-in profiles off, erase.
  Runs Flirc's own `flirc_util` (installed with its software; in the
  Flatpak, the host's); `"flirc_util"` in config.json names it elsewhere.
  `docs/remotes/flirc.md` has the steps, the Sony page now uses it.

## 4.36

- **The guide in quarter hours.** Every skin's grid now runs in 15-minute
  columns (the ruler labels every column where its lettering fits, every
  other where it doesn't), the cursor steps by the quarter hour on a row
  without listings, and a tracking line marks the minute down every grid
  (Classic had it; the Dish and DirecTV pages get one in their own colour).
  The cell airing now sits in its own tint on every row, lit or not, so
  what's on is plain without moving the cursor.
- **Short programmes readable.** A guide cell too narrow for its title
  tries the title smaller (to seven tenths), then on two lines, before
  cutting it; cut titles are clipped plain rather than ending in "..."
  (the dots cost the letters that tell the shows apart). A cell under
  three letters wide carries nothing; the header names it on the cursor.
- **Video Channels: a source's order and shuffle.** Each source has an
  Order (as listed, reversed, by title) and a Shuffle switch; off, its
  videos run in that order from the top at 4 AM, interleaved with the
  channel's other sources as before. A big list's daily sample keeps the
  list's order.
- **Refresh schedule** on a video channel's page (where "Check sources
  now" was): fetches the sources again, draws up today's running order
  anew with your changes, and starts the channel over if it's on.

## 4.35

- **Video Channels** (the Music channels of 4.34, grown up). A channel is
  now any mix of YouTube playlists, channels and @handles. Each source's
  list of videos is fetched weekly; each broadcast day (from 4 AM) draws a
  sample of up to 500 of them by the date and interleaves the sources by
  weight: Auto (each source's share of the running time, no source under
  5%), Equal, or Manual per source. Videos under a minute, Shorts and
  live streams (and what they leave behind) stay out, each adjustable. Long-form channels get a programme per video in
  the guide; music channels keep the half-hour blocks (Auto picks, or
  choose). The lower-third names the uploader and the video, or the artist
  and the song. Settings > Channels > Video Channels is the maker: name,
  channel number, sources (add, edit, weight, reorder, remove), weighting,
  minimum length, Shorts, guide style, lower-third, "Check sources now",
  Remove channel. A fresh install has the three decade playlists and
  "bideogaymin" (fourteen gaming channels mixed); 4.34's music playlists
  carry over as one-source channels.

## 4.34

- **Restart Cathode** in the main menu, next to Exit: closes and starts
  again as it was launched (the exe, the AppImage, or main.py).
- **The mouse pointer goes away.** It hides three seconds after the mouse
  sits still, and at once on a key or a pad button; it's back as soon as
  the mouse moves.
- **Music channels.** YouTube playlists as channels of music videos, after
  Cathode's own channels. Three official decade playlists are there from
  the start ('80s, '90s, 2000s); Settings > Channels > Music channels
  adds any playlist link or takes one away. Each channel is a timeline: the
  day's running order is the playlist shuffled by the date, laid out from
  midnight, so tuning in lands mid-song, tuning away and back finds the
  same song further on, and the guide's half-hour blocks say which songs
  start in them. A lower-third names the artist and the song as each
  starts and again before it ends. A video that can't play is dropped
  from the day's order. Resolved through yt-dlp running inside Cathode
  (no JavaScript runtime needed today); Settings > Channels > Music
  channels > YouTube support fetches the newest yt-dlp when YouTube
  changes break it (checked weekly on its own), which takes over at the
  next start.

## 4.33

- **Cathode's own channels.** Two channels of Cathode's own sit in the
  lineup and the guide like any other, after the lineup's last number
  (or at a number you choose, or off, under Settings > Channels >
  Cathode's channels). They draw their picture instead of playing a
  stream, so they take the channel-change static, the CRT pass and the
  guide's picture box like a broadcast.
  - **The TV Guide channel:** the look of the TV Guide Channel at the end
    of the nineties. A promo for what's on now, one channel after another,
    over the top half (its poster where the guide has one, the title,
    its rating, its time, its channel number); every channel's next
    ninety minutes rolling up through the bottom half in bevelled navy
    cells, the clock in the corner cell, arrows on a programme that runs
    past the edge, bold condensed type with a shadow.
  - **The Weather channel:** the current conditions, the three-hourly
    outlook, the extended forecast and the almanac, each held for eight
    seconds under a running clock, with the conditions crawling along the
    foot. It uses the zip code from Settings > System > Weather.
  - **Their music.** Each plays its own background music while it's
    tuned (smooth jazz under the weather, a light synth tune under the
    guide), following the box's volume and mute. Settings > Channels >
    Cathode's channels > Background music turns it off; a `tvguide.ogg`
    or `weather.ogg` (mp3, wav, flac) dropped in `~/.config/cathode/music`
    plays instead of Cathode's.

## 4.32

- **Guide posters.** A programme's poster, where the guide carries one
  (Tunarr's does), shows in the InDirecTV HD and Plate Network HD guide
  headers and in Classic's programme panel.
- **Channel numbers with a decimal part** (ErsatzTV's 10.1, 10.2) are
  kept as they are instead of breaking the playlist.
- **The lineup refreshes itself** on the guide's six-hour schedule: a
  channel added on the server appears without a restart, and the channel
  playing stays playing.

## 4.31

- **A provider line's guide fills in from the API.** The panel's XMLTV
  (when it serves one) rarely lists every channel of a big line; the
  channels it leaves out now get their programmes through the panel's
  per-channel API, as IPTV Smarters shows them. The log says how many
  channels the XMLTV covered and how many the API added.
- The log also says, for any playlist, how many channels the guide
  covers and names a few it doesn't, with their guide ids, so a
  diagnostics zip shows why a guide comes up empty.

## 4.30

- **The guide's highlight walks the programmes.** LEFT/RIGHT move from
  one show to the next along the row, as a box's cursor does; the time
  window slides only when the chosen show would leave it, and never
  before now. UP/DOWN keep the time, so the lit cell follows the clock
  down the grid. REW/FF jump a day and put the cursor on the first column.
- **A list of categories** on THEMES (keyboard T) or OPTIONS (pad: left
  stick), as a pop-up in the skin's style: one pick, no cycling.
- **INFO on a guide cell** pops up that programme (channel, when, rating,
  synopsis) on the InDirecTV SD and Plate SD guides, whose pages have no
  header for it; the HD guides' headers already follow the chosen cell.

## 4.29

- **The guide for provider lines that lock their XMLTV** (xmltv.php
  answering 513 while the channels load) comes through the provider's
  API instead, channel by channel, the way IPTV Smarters shows it. A
  line that does serve its XMLTV still uses that. Lines added with 4.28
  switch over on their own.
- A provider line's password no longer shows in Settings > Channels.
- **The Flatpak updates itself** from Settings > System > Check for
  updates: it installs the new bundle through the host's flatpak, so a
  Steam Deck updates from Game Mode without a password. (The 4.28
  Flatpak lacks the permission for this, so 4.28 to 4.29 is one last
  manual install; from 4.29 on it updates itself.)

## 4.28

- **Provider lines that refuse the playlist link** (the ones that answer
  "884" however they're asked) load through the provider's own API, the
  way IPTV Smarters and TiviMate do: paste the same M3U Plus link and
  Cathode finds the channels, their groups and the guide that way.
- A provider's refusal now says what to check (the username and password
  in the link, that the line is active, other apps signed in with it).

## 4.27

- **Provider links that answer "refused it (884)"** are tried in every
  shape a panel serves (get.php as m3u_plus and m3u, and the /playlist/
  path) and as the players panels expect; what the panel said to each
  try goes in the log, so a diagnostics zip shows why.
- **A saved audio output that isn't on this computer** no longer mutes
  Cathode: sound goes to the default output, with a note.

## 4.26

- **IPTV providers that refuse unknown players** (a link that answered
  "refused it (884)") are fetched as a player: Cathode tries the
  User-Agents real players send and keeps the one the provider answers
  to, for its guide and its streams.
- **InDirecTV HD makes the HR20's sounds:** a key tick and an error bonk,
  with Settings > System > Sound effects (Off / Low / Medium / High). The
  other boxes were silent and stay so.
- **Banners after the manuals:** the InDirecTV HD strip's audio, messages
  and lock icons; the Plate Network HD banner laid out as its manual
  shows it.

## 4.25

- **One address to set up.** Setup asks for your Tunarr or ErsatzTV
  address (like 10.0.0.215:8000), finds it, and takes the playlist and
  guide from it. An IPTV provider's **M3U Plus link** works the same way:
  paste the get.php link and the guide comes from the same provider.
  Channel icons a server wrote as "localhost" now point at the server.
- **Boot sequences after the real boxes:** InDirecTV HD's blue "hello"
  screens and Step 1 / Step 2; Plate Network HD's "Starting up..." and
  Acquiring Signal dialog; Plate Network SD's ATTENTION 015; InDirecTV SD
  starts straight on the picture, as a DSS box did.
- **Channel changes feel like the box:** a moment of black on every
  change (each box's own); Banner time (2-8 s) under Picture & Style on
  the InDirecTV skins.
- **Save diagnostics** under Settings > System: one zip for a bug report,
  with the Plex tokens removed.

## 4.24

- **Easier to read from the couch.** The InDirecTV HD pause bar's tag and
  time, the InDirecTV SD synopsis and Plate Network HD's buttons and small
  lines all read better, and no colour theme can push text on the boxes'
  fixed colours below the legibility floor.
- **First run** opens on a welcome line, counts its steps as 3/3, and every
  keyboard says how to type or paste. MENU pastes, so a remote or a pad can.
- **Hints:** the InDirecTV HD guide names REW/FF (the remote has no colour
  keys); no "Press DOWN" tip or Skip Intro over an open menu; BACK is "back"
  everywhere; the comma key shows in hints.
- **TV safe area:** text and controls sit inside the area an overscanning TV
  shows, on every skin.
- **For bug reports:** mpv's own warnings and errors (a damaged audio frame,
  an audio dropout) now go to cathode.log.

## 4.23

- **Subtitles can't crash Cathode.** Switching Auto-sync (or adding a
  subtitle the server wouldn't hand over) could close the app. Now a file
  that won't load is noted in the log, the subtitle you had on stays on,
  and one Plex won't sync comes back as it was.
- **Auto-sync says when Plex can't.** Plex lines subtitles up with the
  speech only after it has analysed a title ("Generate voice activity
  data" in its Library settings, off by default). Switching Auto-sync on
  where none can be synced now says so.

## 4.22

- **Live TV keeps going when a stream drops.** When the server ends a
  stream (Tunarr closes a session after a bad source file), Cathode now
  opens the channel again behind the seconds still buffered and goes
  straight on to it: no banner, no black screen, usually no gap. It used
  to sit paused until you changed channel. A stream stuck buffering is
  picked back up the same way, and only one that keeps failing shows the
  stand-by card.
- **On Demand plays the next episode** when one ends, and the playback
  bar goes away after a few seconds (BACK hides it; BACK again leaves).
  The bar now shows the title's year and rating, or the episode.
- **The Main Menu from a playing title:** press MENU, then Main Menu.
  Settings open over the title; the guide stops it (keeping your place)
  and goes back to TV.
- **Channel logos:** the InDirecTV banner shows the channel's logo, and
  very large logos (over 40 megapixels) load instead of being skipped.
- **Clearer for first-timers and from the couch:** setup says what the
  playlist and guide links are; Classic's guide lights only the cursor
  row; key chips name the keyboard key; Plate Network's menus fit on one
  page, its On Demand page is called On Demand, and its ATTENTION bar
  moves smoothly; playback says DOWN reaches its buttons; Diagnostics
  name the codec.

## 4.21

- **Plex posters load on Linux.** The Flatpak couldn't check the
  certificate of a Plex server reached over https, so the poster wall
  stayed empty. Posters and logos now use the same certificates as the
  rest of Cathode, and one that fails says why in the log.
- **Closed Caption is back** in Subtitles > Font, by that name (it was
  listed as "Space Mono"), and each font appears there once.

## 4.20

The 4.0 alpha, updating itself.

- **Updates reach the alpha.** The 4.x updater follows releases marked
  pre-release on GitHub (tagged with a version, like `v4.20`), so alpha
  installs update from one to the next, while 3.x installs, which skip
  pre-releases, stay on 3.x. Windows, the AppImage and source installs
  update themselves; the Flatpak and the Mac app say when one is out.
- Versions compare number by number, so after 4.20 comes 4.21 (or 5.0):
  a "4.3" would read as older than 4.20.

## 4.0

A rebuild, from the window up, to feel like using a satellite box rather than
a retro-themed player.

- **Three skins.** Cathode Classic is 3.x's look. **InDirecTV** and
  **InDirecTV HD** are DirecTV-style boxes (D10/R15 era and HR20), **Plate Network**
  and **Plate Network HD** Dish-style ones (301/522 era and ViP622/722). The SD
  variants draw in 4:3. Their screens are drawn to measurements from video
  of the real boxes: the 1997 DSS receiver's purple pages, the HR20's blue
  banner and cyan guide, the 2005 Dish guide's blue tab and pills, the 2007
  teal guide. Every screen is the box's own, On Demand, My Recordings,
  info pages, the keyboard and system info included. Each has a mark of
  its own; no real logos ship. Each skin
  keeps its own colour theme and font, and any skin can use any theme, the
  colour editor, any font and the CRT effect.
- **Box behaviour.** A start-up screen that follows the real loading, a
  banner on every tune (INFO again for the description), browse without
  tuning (Plate Network: RIGHT, as on Dish), a mini guide (InDirecTV), a signal-loss screen for dead channels, PREV, a THEMES button for genres, guide paging
  and day jumps, numbered menus. On Demand playback bars carry on-screen
  transport buttons in every skin, each box's in its own style.
- **On Demand subtitles.** Subtitle files Plex keeps beside a title (.srt)
  now load with it. During playback, MENU > Subtitles > **Find subtitles**
  searches through the Plex server's own OpenSubtitles link in the chosen
  **Search language**; picking a result has the server fetch it and keep it
  with the title, and Cathode switches it on. **Auto-sync** (on by default)
  asks the Plex server to align subtitles to the dialogue wherever it can
  (Plex Pass and the server's voice analysis).
- **Any screen shape.** The 16:9 skins (Classic, InDirecTV HD, Plate Network
  HD) fill 16:10 (Steam Deck) and 4:3 screens instead of sitting between
  bars. Their canvas grows taller, so guides, On Demand lists and poster
  walls show more rows, banners and bars sit at the screen's real edges,
  and box pages stretch their panels. Text stays the same size. The 4:3 skins are pillarboxed on
  wider screens as before, or stretched to fill with Settings > Picture &
  Style > **Wide screen**. Picture boxes now keep the video's shape at
  every window shape; they used to squash it.
- **Readable in every theme, and says what things do.** Cathode 3's colour
  themes are translated into each box's own colours and kept at 4.5:1 or
  better; the box's own look (Original) is marked Recommended. Every menu
  row says what it does, in each box's own place for it; the Button Guide
  is on the Main Menu; the Plate guides show their keys in a strip at the foot.
  A channel with no listings says why (no guide, guide failed or empty,
  channel not in the guide), and each playlist's page shows and edits its
  playlist and guide addresses. Setup checks the playlist address as it's
  entered ("Found N channels"); a playlist file on the computer works too.
  Dead-channel cards say what to do next, toasts are no longer cut short,
  small type is up to 17 px, and focus is only ever lit where the cursor is.
- **Kind to servers that transcode (Tunarr).** Surfing with CH+/CH- moves the
  banner at once but loads the stream only once the presses stop, and a
  dropped stream is retried after 2, 5, 10, then every 20 seconds instead of
  restarting the server's transcode every 2.
- **Linux displays.** On a Wayland session (a Steam Deck's desktop) Cathode
  falls back to X11 when Wayland isn't reachable, and tells PyOpenGL to use
  the same path SDL does; the Flatpak sets both itself.
- **Posters.** Every skin's title info shows the poster, and every skin
  offers the **poster wall** (On Demand > MENU > View), each in its box's
  style. Classic's info buttons are centred.
- **Live TV playback buttons and Options.** SELECT shows the banner; SELECT
  again (or PAUSE, REW, FF) brings the playback buttons onto the pause bar:
  Rewind 10 s, Play/Pause, Forward 10 s, Jump to Live, in each box's style.
  LEFT/RIGHT move between them, SELECT presses, BACK puts them away. The
  **Options** pop-up (O, or the pad's left-stick click) holds Add to
  Favorites, Picture format, Subtitles and On Demand, so a pad reaches
  them all.
- **Remote reach.** Every button on screen can be reached by the remote: the
  guide's list shows its focus in every skin, DOWN moves into On Demand's
  playback buttons, RIGHT into Plate's side buttons, and the mini guide
  moves with the arrows. **Settings > Remote control > Button guide** lists
  what each button does, named for the remote, pad or keyboard in use.
- **Easier channel setup by remote.** Address keyboards start lowercase with
  http:// already typed, and : and / are on the first layer in every skin.
  BACK on an empty field leaves it. First run numbers its channel steps
  3a, 3b and 3c.
- **Channel logos in the guide.** InDirecTV HD shows the chosen channel's
  logo over its title, Plate Network HD under the plate network mark, Plate
  Network on the channel pill (from the guide data or the playlist).
- **Animated logos.** Animated GIF, PNG and WebP channel logos play at their
  own frame rate wherever they show, and only cost redraws while on screen.
- **Clearer words.** On Demand titles read **Watch** and **Cost: Free** on
  every skin's info page (recordings keep Play); titles keep the server's
  own casing ("TV Shows"); errors read as sentences. Plate's hints name
  Cathode's buttons (BACK, EXIT). Marks: no TV GUIDE tag, and the DSS menu
  is "Main Menu".
- **Safer by remote.** Exit Cathode, Unlink Plex account, Delete playlist
  and Reset buttons each ask first, with the safe choice on top. A channel
  number that doesn't exist says "No channel 99"; channel keys during a film
  say how to stop it. Diagnostics read a live stream's buffer fairly and
  name a software decoder.
- **Gamepads.** Hints name the pad's own buttons once one is used (Xbox,
  PlayStation symbols, Nintendo), and go back to the remote's or keyboard's
  when those are pressed. The pad's View / Share / - button now opens
  Browse (the mini guide on InDirecTV) instead of repeating Start.
- **Remotes.** Every remote button now has a plain keyboard key (CH+/CH- are
  `]`/`[`, STOP is X), so an IR receiver like a FLIRC can send them all.
  Settings > Remote control > Remote picks a remote whose own button names
  the hints then use. The first is the **Sony RM-Y195**; setup is in
  docs/remotes/sony-rm-y195.md.
- **FORMAT key** (A, or Settings > Picture & Style): Original, Zoom, Stretch
  or 4:3, over any screen, remembered. **Guide refreshes show their real
  progress** in each box's own notice, and the start-up screen's bar follows
  the actual download. InDirecTV's DSS offers On Demand titles as its 1997
  **Purchase Offer** page (Cost to view: $0.00).
- **First run** is a short wizard: choose your box, then its colours (each page
  redraws in what you point at), then set up channels: the playlist's address,
  its guide and its name. Playlists can be renamed under Settings > Channels.
  MENU sets up channels until there are some, a
  playlist that won't load says why in plain words and where to fix it, an
  empty Favorites list says how to add one, and the keys are shown once.
- **Subtitles** on live TV and On Demand: S (bindable) cycles the stream's tracks
  and broadcast closed captions; Settings > Subtitles turns them on for
  everything you watch and sets their size, colour, background and font.
- **Built for real-world data.** Channel names and guide text in any script
  (Arabic and Hebrew shaped right-to-left, Chinese, Japanese, Korean, Thai,
  Hindi, Greek, Cyrillic, emoji) fall back to a system font when a skin's own
  font lacks them. Playlists with a byte-order mark, Windows-1252 text, HTML
  entities or control characters load cleanly. A damaged settings file is kept
  as config.json.damaged instead of overwritten, and a bad value costs only
  that setting. A guide or Plex failure says why in plain words.
- **Pause live TV**, rewind and fast-forward through the buffer, back to live.
- **On Demand and My Recordings** are Plex-Per-View and the DVR, rebuilt on
  the new core: the same sign-in, browsing, poster wall, queue, resume and
  offline recordings.
- **Faster.** Cathode draws its own window and plays video with libmpv in
  process; the interface is composited on the GPU, including the CRT
  effect and the channel-change static, and only redrawn when it changes. An
  idle Cathode uses next to no CPU.
- **Desktop.** Any game controller (SDL), media keys for IR remotes, full
  screen on a chosen monitor, start with the computer, the screen kept awake
  while playing.
- **Ready-made builds everywhere**, each with libmpv inside: Windows zip,
  Linux AppImage and Flatpak (the Steam Deck's way in), and a macOS app for
  Apple Silicon and Intel. The AppImage updates itself like the Windows
  build; the Flatpak and the Mac app tell you when an update is out.
- **Dropped:** demo mode (`tools/devtv.py` writes a test lineup for
  development instead). Cathode 3's key and controller remaps don't carry
  over, because every button was renamed; set them again under Settings >
  Remote control.

## 3.4

- **Updates install properly.** The installer was meant to wait two seconds
  for Cathode to close, but run detached that wait didn't happen at all, so it
  copied over a Cathode that was still running and then deleted the download
  whether the copy had worked or not. It now waits for Cathode to actually
  exit, and won't let it be relaunched until the copy is finished. If anything
  fails, the download is kept, the reason is written to
  `updates/apply_update.log`, and the next launch tells you. Files a new
  version no longer ships are removed instead of piling up, and a Windows
  username with an apostrophe in it no longer breaks the install. Updating
  from 3.3 still uses 3.3's installer; if that update looks incomplete, extract
  the 3.4 zip over the install by hand.
- **Channel changes stay in order.** Two quick presses could both start from
  the same channel and reach mpv in the wrong order, leaving the info bar on
  one channel and the picture on another. A late signal from the stream being
  replaced could also lift the static early, onto a black screen, or spend a
  Plex resume point on the wrong file. Presses now queue, and Cathode only
  listens to the stream it actually asked for.
- **The guide keeps itself current.** It loaded once at startup, so a Cathode
  left on overnight ran off the end of its listings. It now reloads every six
  hours and keeps what it has if a reload fails. Big guides load with a fraction
  of the memory: the download is read as it arrives instead of all at once, and
  only listings from three hours back to a day and a half ahead are kept.
- **One Cathode at a time.** A second launch shared the first one's overlay,
  config and controller and the two drew over each other. It now says Cathode
  is already running and exits.
- **No console window on Windows.** Closing it used to quit the app. What it
  showed now goes to `cathode.log` (the run before is kept as `cathode.log.1`),
  and startup errors appear in a message box.
- **Built on Python 3.13 and Pillow 12.** 3.3 shipped Python 3.10 and Pillow
  9.0, whose WebP decoder predates the libwebp security fix. The Windows build
  now refuses to run on an out-of-date toolchain.
- **DVR poster art is size-capped**, like channel logos.

## 3.3

- **The screensaver can be switched off**, under **Options ▸ Display ▸
  Screensaver**. It also no longer paints over a channel change: it ran on its
  own clock outside the render path, only checked whether it should still be
  running once per frame, and could land one last opaque black frame with the
  wordmark on top of the static after you'd already pressed a channel key.
  It now re-checks under the render lock immediately before every write.

## 3.2

- **The controller only drives Cathode while its window is in front.** XInput
  hands the pad's state to any process that asks, focused or not, so with
  Cathode open in a second window every press in the game you were actually
  playing changed the channel behind it. Input is now gated on mpv's own
  `focused` property; a press made while another window had focus is never
  delivered, and refocusing with a button or the stick still held doesn't fire
  a phantom press or a burst of repeats.

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
