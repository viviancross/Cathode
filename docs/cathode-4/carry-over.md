# Carry-over: behaviours 3.4's tests guarded

The rebuild deleted the modules these tests drove (`app*.py`, `player.py`,
`ui/*`, ...). The behaviours still apply and each needs a test against the new
code before 4.0. Read the originals with `git show 432d6de:tests/<file>.py`.
Tick a line when the new code has a test for it.

## Live TV and tuning (`test_tune_races`)
- [ ] A late playback-restart from the replaced file never reveals the new channel
- [ ] Rapid presses each move exactly one channel; mpv ends on the channel the banner shows
- [ ] A stale tune timeout doesn't reveal the next channel
- [ ] Per-stream HTTP headers and the load they belong to go out together
- [ ] Tuning with no channels loaded is safe

## Input routing (`test_input_routing`, `test_gamepad_*`)
- [ ] Topmost screen owns input: keyboard over dialog over playback over live
- [ ] Wheel, digits and channel keys never tune from the home screen, keyboard, or Plex playback
- [ ] Guide opens only from live TV
- [ ] Plex playback: bumpers = prev/next item, triggers = seek; dead while a dialog is over playback
- [ ] Skip at the queue edge falls back to a chapter skip
- [ ] Controller input only while the window is focused; a button held across refocus is not a new press
- [ ] Controller works with no controller-specific config

## Plex (`test_plex_queue`, `test_episode_queue`, `test_ppv*`, `test_downloads` UI parts)
- [ ] Play queue: add, move up/down (identity, edges, playing marker), remove (shifts current), clear
- [ ] One-off play keeps a hand-built queue, replaces an automatic one
- [ ] Episode queue runs from the selected episode to the end; none for last/unknown episode
- [ ] Sort: release-date offered, remembered per library, labels survive truncation
- [ ] Poster wall: two whole rows fit, steps by row, only visible tiles fetch art, no token in URLs
- [ ] Info page buttons per item kind incl. DVR; downloaded items offer only what works offline
- [ ] Offline: DVR list shows before the server is asked; a late server answer doesn't yank the screen

## Menus, keyboard, guide (`test_menu*`, `test_osk`, `test_guide_close`)
- [ ] Long menus scroll a window that follows the selection; back row pops a submenu
- [ ] Every menu page offers an exit; at the root it closes, in a submenu it goes up
- [ ] On-screen keyboard: caret at end on open, insert/backspace at caret, caret clamps
- [ ] Guide close control is hittable and doesn't overlap the category bar

## Look (`test_delight`, `test_crt`, `test_motion`, `test_fonts`, `test_ascii_ui`, `test_ui_aspect`)
- [ ] Stand-by card renders on a dead stream and clears when a frame arrives
- [ ] Power-off collapse: bounded, honours reduced motion, never blocks exit
- [ ] Screensaver arms only when idle on home/guide, never when disabled, never paints after state changes
- [ ] CRT: pitch follows screen height, soft profile, vignette leaves the middle alone, text stays readable
- [ ] Reduced motion resolves every transition instantly
- [ ] Every drawn character exists in every bundled font; truncation stays ASCII
- [ ] UI box: centred, pillarboxed on wide displays, pointer coordinates mapped into it

## Process (`test_single_instance`, `test_updater`, `test_epg`)
- [x] Second instance refused while the first holds the lock (`test_updater` covers `hold_instance_lock`)
- [ ] Log goes to cathode.log, previous run kept as cathode.log.1
- [ ] A failed update install is reported on the next launch
- [ ] EPG reloads on a timer, stops when the playlist changes, keeps the old guide if a reload fails
