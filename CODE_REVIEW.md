# Cathode Code Review — v2.2

Full-codebase review (July 2026): `app.py`, `plex.py`, `player.py`, `ipc.py`,
`gamepad.py`, `config.py`, `updater.py`, `weather.py`, `epg.py`, `playlist.py`,
`logos.py`, `clipboard.py`, all of `ui/`, and the build tools.

> **Status (July 2026): all 17 bugs fixed and the design improvements applied**
> (focus-owner input dispatch, app.py split into App + PlexMixin + MenusMixin,
> shared net.py SSL context, monitor generation counter, chmod-600 config,
> sha256 update verification, scrobble mark-watched, EPG iterparse, logo cache
> caps, fmt_hms dedup, input-routing tests, GitHub Actions CI). Line numbers
> below refer to the pre-fix tree. Skipped by design: LT/RT seek stays coupled
> to the vol_up/vol_down actions (labels updated instead — full decoupling
> needs a config migration), and the thread-per-input dispatch stays (blocking
> dialogs like the OSK depend on it).

## Bugs — high

1. **Invisible theme editor over PPV / info screen / Plex playback.** The editor
   is reachable from every Plex context menu (Options → Themes → Custom
   Theme...), but `renderer._render` only composites `editor` in the main-menu
   and live-TV branches — not in `ppv.open` (renderer.py:489-495),
   `plexinfo.open` (497-502), or `plex_playing` (533-546). The editor opens,
   captures all input (it's checked first in `_guide_up` etc.), and renders
   nothing. Feels like a freeze; only a blind Esc/B escapes.

2. **Mouse wheel escapes context → tunes live TV or crashes.** `_wheel`
   (app.py:1050-1063) handles menu/ppv/guide/plex only. Main menu, OSK, and
   editor fall through to the else branch → `_channel_up/_channel_down` →
   `_tune`. With no channels loaded, `idx % len(self.channels)` (app.py:260)
   raises ZeroDivisionError. With channels loaded, a wheel scroll on the home
   screen or while typing a URL starts tuning live TV under the UI.

3. **Keyboard digits / PgUp / PgDn during Plex playback drop to live TV.** Same
   family as the 2.2 bumper bug. `_char_typed` (app.py:778) only checks
   osk/menu/editor/main_menu — a digit typed during playback → `_digit_press` →
   `_tune` → `_plex_end`. PGUP/PGDWN (app.py:624-625) are guarded by
   `_dialog_open`, which lacks `plex_playing`, so they also `_tune`. With no
   channels loaded, same ZeroDivisionError. TAB shows the live-TV OSD over
   Plex video.

4. **Transcode quality: "Start from Beginning" still resumes.** `play_info`
   bakes `viewOffset` into the HLS transcode URL (plex.py:450-451) before the
   resume choice exists; `_ppv_play`'s start=0 does nothing because the
   transcoder already skipped ahead. Any non-Original quality ignores "Start
   from Beginning".

5. **Transcode with offset: positions all shifted.** mpv's `time-pos` is
   relative to the transcode start, but `_plex_monitor_loop` heartbeats it as
   absolute (app.py:2440-2442) → resume points corrupted;
   `_update_skip_button` compares it against absolute markers (app.py:2446) →
   Skip Intro appears at the wrong times; the progress bar is wrong too.

6. **M3U parser breaks on commas inside quoted attrs.** `_EXTINF_RE`'s attrs
   group is `[^,]*` (playlist.py:24-27). `group-title="News, Local"` → attrs
   truncated, channel name corrupted. Common in real playlists.

## Bugs — medium

7. **Plex monitor thread race.** `_plex_monitor` (bool) doubles as "should run"
   and "is running". The old loop's final `self._plex_monitor = False`
   (app.py:2444) can land after a new session's `_start_plex_monitor` set it
   True → the new monitor dies → frozen progress bar, no heartbeat, dead skip
   button. ~0.5s window on stop→play.

8. **Volume-bar click while muted: silent playback, UI says unmuted.**
   `_plex_click` "volume" (app.py:2557-2564) sets `osd.muted = False` but never
   calls `_unmute_if_muted()` — `player.muted` stays true.

9. **`sys.exit(1)` from a handler thread** (app.py:3166) only kills that
   thread. The cancel path in `_load_playlist_interactive(allow_cancel=False)`
   via `_switch_playlist` leaves the app alive on a stale screen;
   `_switch_playlist` (app.py:1771) also ignores the return value entirely.

10. **Bumpers bypass dialogs during playback.** `_lb/_rb_action` check
    `plex_playing` first — episode skip fires while the "LEAVE VIDEO?" confirm
    or the A/V menu is open. Inconsistent with the triggers (guarded).

11. **Failed volatile reload eats a browse level.** `_ppv_show_top` pops before
    `_ppv_open` (app.py:2699-2703); a loader failure means the level is gone,
    and the next Back goes up two.

## Bugs — low

12. LB on the first queued episode: `_plex_skip(-1)` no-ops with no chapter
    fallback (app.py:2506-2512). The queue only holds selected-episode-onward,
    so "prev episode" never reaches earlier episodes.
13. `ellipsize` uses Unicode `…` (theme.py:519); the pixel fonts are ASCII-only
    per the UI modules' own docstrings — possible tofu. Guide's `_truncate`
    correctly uses `"..."`.
14. Remapping `vol_up`/`vol_down` to another button moves the Plex 10s-seek
    with it (seek lives inside `_rt/_lt_action`, bound to the vol actions,
    app.py:1125-1126). Remap-menu labels are also stale ("Volume Up" is now
    also seek).
15. `_MEASURE_CACHE` is unbounded (theme.py:407) — slow leak on long-running
    sessions (EPG titles churn daily).
16. `--msg-level=all=v` is always on (player.py:216) — mpv.log grows unbounded
    over long sessions; make verbose opt-in.
17. `updater.py` uses `urllib.error.HTTPError` without importing `urllib.error`
    (works only because `urllib.request` imports it internally — fragile).

## Design / technical improvements

- **app.py is a 3204-line god class.** Split: PlexController, LiveTV/tuning,
  input routing, menu builders. Biggest single win for maintainability.
- **Centralize focus dispatch.** Bugs 1-3 — and the 2.2 bumper bug — share one
  root cause: the priority ladder (osk → editor → menu → main_menu → ppv →
  plexinfo → plex_playing → guide) is hand-copied in ~9 places
  (`_guide_up/down/left/right`, `_grid_select`, `_gamepad_back`,
  `_handle_escape`, `_menu_click`, `_wheel`, plus `renderer._render`). One
  "topmost focus owner" resolver + a per-owner handler table kills the whole
  bug class.
- **Monitor lifecycle:** replace the bool with a generation counter or a
  per-session `threading.Event`.
- **Shared SSL helper:** plex.py and updater.py use certifi; weather/EPG/
  playlist/logos don't → those break on macOS cert-less Pythons. One `net.py`
  helper.
- **Tokens on disk:** `config.json` holds Plex tokens world-readable on Linux.
  `os.chmod(0o600)` after save.
- **Updater integrity:** downloads + robocopy-overwrites the install dir with
  no hash check. Publish sha256 next to the assets and verify before apply.
- **Mark-watched reliability:** `/:/timeline` state=stopped works, but
  `/:/scrobble` is the canonical mark-watched call — use it in the
  `finished=True` path.
- **EPG memory:** `ET.fromstring` loads the whole XMLTV; big guides (100MB+)
  spike RAM on the Deck. Use `iterparse` and clear elements.
- **Logo/poster disk cache:** no eviction, grows forever in the runtime dir.
  Cap or LRU-prune.
- **Thread churn:** gamepad dispatch spawns a thread per press/repeat
  (app.py:1025), `_plex_report` a thread per heartbeat. A worker queue would
  do.
- **Tests:** input routing has zero coverage — exactly where the last two
  releases' bugs lived. A fake-renderer routing test (given state X, button Y →
  action Z) would have caught the bumper bug and bugs 1-3. Plus CI (GitHub
  Actions, `python -m unittest`, Windows + Linux).
- **Dedup:** `_fmt_time` ×3 (app.py:2354, plexosd.py:32, plexinfo.py:200);
  dead `import time` re-imports inside methods (time is already module-level);
  `_plex_finished`/`_plex_stop` near-identical bodies.

## Other

- CHANGELOG.md is not in `build_source.TOP_FILES` → releases ship without it.
  Add if intended for users.
- LICENSE-file gap already tracked (PixelForge blocker) — still open.
- On-deck "next episode" queueing overlaps the `all_episodes` per-play fetch;
  fine, but a slow server delays play start by ~1 RTT — could fetch the queue
  after playback starts instead.
