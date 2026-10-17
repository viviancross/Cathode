"""Live TV: the bottom of the stack. Tuning, the channel banner, typed channel
numbers, volume, previous channel, and the cover over a channel change."""

import time
from datetime import datetime, timezone

from .. import remote as R
from ..app import Screen


def _smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class LiveTV(Screen):
    name = "live"
    DIGIT_WAIT = 2.0        # seconds after the last digit before tuning

    def __init__(self, app):
        super().__init__(app)
        self.idx = 0
        self.prev = None            # channel index PREV goes back to
        self.phase = "idle"         # idle | cover | reveal | watch
        self.standby = False        # dead stream: the skin's stand-by card
        self.message = "Loading channels..." if app.config.playlist_url else \
            "No channels yet. Press MENU to set up your channels."
        self.banner_until = 0.0
        self.banner_full = False    # INFO pressed again: the expanded banner
        self.volume_until = 0.0
        self.digits = ""
        self.trick_until = 0.0
        self.trick_focus = None     # the playback button LEFT/RIGHT point at, while they're up
        self.select_armed = False   # SELECT showed the banner: SELECT again brings the buttons
        self.suspended = False                      # On Demand has the picture
        self.behind, self._paused_at = 0.0, 0.0     # pause-live bookkeeping
        self._reveal_start = 0.0
        self._timeout = self._digit_timer = self._banner_timer = None
        self._settle = None         # surfing: the stream loads once the presses stop
        self._fails = 0             # a dropped stream's retries in a row
        self.dropped = False        # the stream ended: reconnecting under its last picture
        self._handover = False      # its replacement is queued behind the buffered picture
        self._stall = None          # buffering with nothing to show: the watchdog

    # Surfing (CH+/CH-, paging) moves the banner at once but loads the stream
    # only once the presses stop: a server that starts a transcode per tune
    # (Tunarr's HLS) isn't asked for every channel skipped past.
    SURF_SETTLE = 0.5
    # A dropped stream is picked up again quietly, under its last picture (no
    # banner, no cover): at once, then less often each time it fails in a
    # row, so a slow server isn't restarted from scratch in a loop. Only one
    # that keeps failing gets the stand-by card.
    RETRY = (0.5, 2.0, 5.0, 10.0, 20.0)
    STANDBY_AFTER = 3
    # Stuck buffering this long (two of Tunarr's 4 s segments) is a server
    # that stopped sending without ending the stream: reconnect as for a drop.
    STALL_LIMIT = 8.0

    # ── Channels ──────────────────────────────────────────────────────────

    @property
    def channels(self):
        return self.app.channels

    @property
    def channel(self):
        return self.channels[self.idx] if self.channels else None

    def channels_loaded(self):
        self.message = ""
        want = self.app.start_channel or self.app.config.last_channel
        self.tune(self.number_to_idx(want) if want else 0)

    def number_to_idx(self, number: int) -> int:
        for i, ch in enumerate(self.channels):
            if ch.number == number:
                return i
        return 0

    def tune(self, idx: int, settle: bool = False, retry: bool = False):
        """Change channel: cover the picture until the new stream's first frame
        is up (or the timeout gives up on it), with the banner showing.
        settle: surfing, load the stream once the presses stop. retry: a
        dropped stream picked up again (keeps counting the failures)."""
        if not self.channels:
            return
        idx %= len(self.channels)
        if self.phase != "idle" and idx != self.idx:
            self.prev = self.idx
        self.idx = idx
        if not retry:
            self._fails = 0
        self.dropped = self._handover = False
        self.app.cancel(self._stall)
        self._stall = None
        ch = self.channels[idx]
        self.phase, self.standby = "cover", False
        self.behind = 0.0                   # a fresh tune is live
        self.app.cancel(self._timeout)
        self.app.cancel(self._settle)
        self._settle = None
        self.app.config.last_channel = ch.number
        self.show_banner()
        if settle:
            self._settle = self.app.after(self.SURF_SETTLE, lambda: self._play(idx))
        else:
            self._play(idx)

    def _play(self, idx: int):
        """Load the stream on the banner, with the timeout that gives up on it."""
        self._settle = None
        if idx != self.idx:
            return
        ch = self.channels[idx]
        self._timeout = self.app.after(self.app.config.tune_timeout, self._timed_out)
        self.app.video.play(ch.url)
        print(f"[cathode] Tuning to {ch}")

    def _timed_out(self):
        """No frame in time: reveal anyway, onto the stand-by card."""
        if self.phase == "cover":
            self.standby = True
            self._reveal()

    def _reveal(self):
        self.app.cancel(self._timeout)
        self.phase = "reveal"
        self._reveal_start = time.monotonic()
        self.app.invalidate()

    def video_box(self):
        return "full"

    def suspend(self):
        """Something else (On Demand) is using the picture: let go of it."""
        self.app.cancel(self._timeout)
        self.suspended, self.standby = True, False
        self.phase = "watch"

    def resume(self):
        """Back to live TV after On Demand."""
        if self.suspended:
            self.suspended = False
            if self.channels:
                self.tune(self.idx)

    def on_video(self, kind, **data):
        if self.suspended:
            return                      # about On Demand's video, not ours
        if self._settle is not None:
            return                      # the channel being surfed past, not the one coming
        if kind == "video_started":
            self.standby, self._fails = False, 0
            if self.dropped:                # back: the new picture replaces the held one
                self.dropped = False
                self.app.cancel(self._timeout)
            if self._handover:              # the replacement took over: it's live
                self._handover, self.behind = False, 0.0
            if self.phase == "cover":
                self._reveal()
        elif kind == "video_buffering":
            self.app.cancel(self._stall)
            self._stall = None
            if data.get("on") and self.channels and self.phase in ("watch", "reveal") and not self.dropped:
                self._stall = self.app.after(self.STALL_LIMIT, self._stalled)
        elif kind == "video_draining" and self.channels and self.phase in ("watch", "reveal")                 and not (self.dropped or self._handover):
            # The server ended the stream (Tunarr closed its session) but
            # seconds of it are still buffered: queue the channel again now.
            # mpv opens it at once and goes straight on to it as the buffer
            # runs out, with no banner, cover or gap if the server is quick.
            self._handover = True
            print("[cathode] stream source ended, handing over to a fresh one")
            self.app.video.follow(self.channel.url)
        elif kind == "video_ended" and self.channels and self.phase in ("watch", "reveal"):
            # Ended outright (or the handover failed): reload it under the
            # last picture.
            self._handover = False
            # A live stream that ends has dropped (Tunarr closed its session,
            # say): load it again underneath.
            wait = self.RETRY[min(self._fails, len(self.RETRY) - 1)]
            self._fails += 1
            self.dropped = True
            if self._fails >= self.STANDBY_AFTER:
                self.standby = True
            print(f"[cathode] stream ended ({data.get('reason')}), reconnecting in {wait:g} s")
            self.app.after(wait, lambda i=self.idx: self.idx == i and self.dropped and self._reconnect(i))

    def _stalled(self):
        self._stall = None
        if self.channels and self.phase in ("watch", "reveal") and not self.dropped:
            self.on_video("video_ended", reason="stalled")

    def _reconnect(self, idx: int):
        """The dropped stream again, without the tune's banner and cover; a
        load that never answers counts as another drop."""
        if self.suspended or self.phase not in ("watch", "reveal"):
            return
        self.app.cancel(self._timeout)
        self._timeout = self.app.after(self.app.config.tune_timeout,
                                       lambda: self.dropped and self.on_video("video_ended", reason="timeout"))
        self.app.video.play(self.channels[idx].url)

    # ── What the compositor and skin read ─────────────────────────────────

    def cover(self):
        """(kind, alpha) over the video, or None."""
        kind = self.app.skin.tune_cover
        if self.phase == "cover":
            return (kind, 1.0)
        if self.phase == "reveal":
            dur = self.app.config.reveal_duration if self.app.config.motion_enabled else 0
            t = (time.monotonic() - self._reveal_start) / dur if dur > 0 else 1.0
            if t >= 1.0:
                self.phase = "watch"
                return None
            return (kind, 1.0 - _smoothstep(t))
        return None

    def animating(self) -> bool:
        return self.phase == "reveal" or (self.phase == "cover"
                                          and self.app.skin.tune_cover == "static")

    def banner_visible(self) -> bool:
        return time.monotonic() < self.banner_until

    def volume_visible(self) -> bool:
        return time.monotonic() < self.volume_until

    def _why_no_listing(self, cur) -> str:
        """Why INFO has nothing more to show, and where to fix it."""
        if cur:
            return "No description for this program."
        app = self.app
        if not app.config.epg_url:
            return "This playlist has no guide. Add its address in Settings > Channels."
        if not app.epg.channel_ids:
            return ("The guide didn't load. Check its address in Settings > Channels." if app.epg_failed
                    else "The guide has nothing in it. Check its address in Settings > Channels.")
        ch = self.channel
        if ch and not app.epg.resolve_channel_id(ch.epg_id, ch.name):
            return "The guide doesn't list this channel."
        return "No listings for this channel right now."

    def programs(self, ch=None):
        """(current, next) programme for a channel, either may be None."""
        ch = ch or self.channel
        epg = self.app.epg
        if not ch or not epg:
            return None, None
        cid = epg.resolve_channel_id(ch.epg_id, ch.name)
        if not cid:
            return None, None
        now = datetime.now(timezone.utc)
        return epg.current_program(cid, now), epg.next_program(cid, now)

    # ── Timed overlays ────────────────────────────────────────────────────

    def _expire_at(self, until):
        self.app.after(max(0.0, until - time.monotonic()) + 0.01, self.app.invalidate)

    def show_banner(self, seconds=None, full=False):
        self.select_armed = False
        seconds = seconds or self.app.config.osd_timeout
        self.banner_until = time.monotonic() + seconds
        self.banner_full = full
        self._expire_at(self.banner_until)
        self.app.invalidate()

    def hide_banner(self) -> bool:
        if not self.banner_visible():
            return False
        self.banner_until = 0.0
        return True

    def show_volume(self):
        self.volume_until = time.monotonic() + 2.5
        self._expire_at(self.volume_until)

    # ── Remote ────────────────────────────────────────────────────────────

    def handle(self, a: str) -> bool:
        if a in R.DIGITS:
            return self._digit(a[-1])
        if a == R.SELECT and self.digits:
            self._commit_digits()
            return True
        if a == R.LIST:                 # works with no channels too: recordings are local
            from .ondemand import OnDemandScreen, RECORDINGS
            self.hide_banner()
            self.app.push(OnDemandScreen(self.app, RECORDINGS))
            return True
        if not self.channels and a not in (R.VOL_UP, R.VOL_DOWN, R.MUTE):
            return False
        if self._trick_keys(a):
            return True
        if a in (R.UP, R.CH_UP):
            self.tune(self.idx + 1, settle=True)
        elif a in (R.DOWN, R.CH_DOWN):
            self.tune(self.idx - 1, settle=True)
        elif a == R.PAGE_UP:
            self.tune(self.idx + 10, settle=True)
        elif a == R.PAGE_DOWN:
            self.tune(self.idx - 10, settle=True)
        elif a == R.PREV:
            if self.prev is not None:
                self.tune(self.prev)
        elif a == R.GUIDE:
            from .guide import Guide
            self.hide_banner()
            self.app.push(Guide(self.app))
        elif a == R.THEMES:
            from .guide import Guide        # THEMES opens the guide on a genre
            self.hide_banner()
            g = Guide(self.app)
            g._cycle_category(2 if len(self.app.categories()) > 2 else 1)
            self.app.push(g)
        elif a == R.FAV:
            self.app.toggle_favorite(self.channel)
        elif a == R.BROWSE or (a == R.RIGHT and self.app.skin.right_is_browse):
            self.hide_banner()
            if self.app.skin.browse_style == "mini":
                from .miniguide import MiniGuide
                self.app.push(MiniGuide(self.app))
            else:
                from .browse import Browse
                self.app.push(Browse(self.app))
        elif a == R.SELECT:
            if self.banner_visible() and self.select_armed:     # twice: the playback buttons
                self.hide_banner()
                self.trick_focus = 1
                self.trick_until = time.monotonic() + self.TRICK_IDLE
                self._trick_tick()
            else:
                self.show_banner(self.app.config.osd_timeout_info)
                self.select_armed = True
        elif a == R.OPTIONS:
            from ..menus import open_options
            self.hide_banner()
            open_options(self.app)
        elif a == R.INFO:
            # INFO once shows the banner; again expands it to the description.
            full = self.banner_visible() and not self.banner_full
            cur = self.programs()[0] if full else None
            if full and not (cur and cur.description):      # nothing more to show: say why
                self.app.toast(self._why_no_listing(cur), 5.0)
            self.show_banner(self.app.config.osd_timeout_info * (2 if full else 1), full=full)
        elif a in (R.EXIT, R.BACK):
            return self.hide_banner()
        elif a in (R.VOL_UP, R.RIGHT):
            self.app.video.volume = self.app.video.volume + 5
            self.app.video.muted = False
            self.show_volume()
        elif a in (R.VOL_DOWN, R.LEFT):
            self.app.video.volume = self.app.video.volume - 5
            self.show_volume()
        elif a == R.MUTE:
            self.app.video.muted = not self.app.video.muted
            self.show_volume()
        elif a in (R.PAUSE, R.PLAY, R.REW, R.FF, R.REPLAY, R.SKIP, R.STOP):
            self.trick_focus = {R.REW: 0, R.REPLAY: 0, R.FF: 2, R.SKIP: 3, R.STOP: 3}.get(a, 1)
            self._trick(a)
        else:
            return False
        return True

    # ── Pause live TV ─────────────────────────────────────────────────────

    TRICK_IDLE = 6.0                # seconds the buttons stay up untouched (always, while paused)

    def trick_buttons(self) -> list:
        """The playback buttons on the pause bar: (kind, number, label)."""
        paused = self.app.video.paused
        return [("back", "10", "<< 10"), ("play" if paused else "pause", None, "PLAY" if paused else "PAUSE"),
                ("fwd", "10", "10 >>"), ("next", "LIVE", "LIVE >>|")]

    def press_trick(self, i: int):
        """A playback button, pressed by SELECT on it or a click."""
        self.trick_focus = i
        self._trick([R.REW, R.PLAY if self.app.video.paused else R.PAUSE, R.FF, R.SKIP][i])

    def _trick_keys(self, a) -> bool:
        """While the playback buttons are up: LEFT/RIGHT move between them,
        SELECT presses one, BACK puts them away."""
        if self.trick_focus is not None and not self.trick_visible():
            self.trick_focus = None
        if self.trick_focus is None:
            return False
        if a in (R.LEFT, R.RIGHT):
            self.trick_focus = (self.trick_focus + (1 if a == R.RIGHT else -1)) % 4
            self.trick_until = time.monotonic() + self.TRICK_IDLE
            self.app.invalidate()
        elif a == R.SELECT:
            self.press_trick(self.trick_focus)
        elif a in (R.BACK, R.EXIT):
            self.trick_focus, self.trick_until = None, 0.0
            self.app.invalidate()
        else:
            return False
        return True

    def _trick(self, a):
        """Pause, rewind and fast-forward within the buffered past of a live
        channel, as a DVR box does. How far behind live we are is kept here:
        mpv's cache can't say (on a live stream it always runs a few seconds
        ahead of the picture)."""
        v = self.app.video
        now = time.monotonic()
        if a in (R.PAUSE, R.PLAY):
            if v.paused:
                self.behind += now - self._paused_at
                v.paused = False
            elif a == R.PAUSE:
                self._paused_at = now
                v.paused = True
        elif a in (R.REW, R.REPLAY):
            step = min(10.0 if a == R.REW else 7.0, v.buffered_behind() or 10.0)
            v.seek(-step)
            self.behind += step
        elif a == R.FF:
            step = min(10.0, self.behind_now())          # never past live
            if step > 0:
                v.seek(step)
                self.behind = max(0.0, self.behind - step)
        elif a in (R.SKIP, R.STOP):
            if self.behind_now() > 1:
                self.trick_focus = None
                self.tune(self.idx)            # back to live
                self.app.toast("LIVE")
                return
        self.trick_until = now + self.TRICK_IDLE
        self._trick_tick()

    def behind_now(self) -> float:
        paused = self.app.video.paused
        return self.behind + (time.monotonic() - self._paused_at if paused else 0.0)

    def _trick_tick(self):
        """Keep the trick bar's numbers moving while it's up."""
        self.app.invalidate()
        if self.trick_visible() and not self._trick_timer_live():
            self._trick_timer = self.app.after(1.0, self._trick_tick)

    def _trick_timer_live(self) -> bool:
        t = getattr(self, "_trick_timer", None)
        return bool(t) and not t[3] and t[0] > time.monotonic()

    def trick_visible(self) -> bool:
        """The bar stays while paused or behind live, and briefly after a press."""
        v = self.app.video
        if self.dropped:                    # mpv holds an ended stream paused: not a pause
            return False
        return bool(v and self.channel) and (v.paused or time.monotonic() < self.trick_until)

    def trick_state(self) -> dict:
        v = self.app.video
        return {"paused": v.paused, "behind": self.behind_now(), "buffer": v.buffered_behind(),
                "buttons": self.trick_buttons(), "focus": self.trick_focus, "press": self.press_trick}

    def _digit(self, d: str) -> bool:
        if not self.channels:
            return False
        self.digits = (self.digits + d)[-4:]
        self.app.cancel(self._digit_timer)
        self._digit_timer = self.app.after(self.DIGIT_WAIT, self._commit_digits)
        return True

    def _commit_digits(self):
        self.app.cancel(self._digit_timer)
        number, self.digits = int(self.digits or 0), ""
        for i, ch in enumerate(self.channels):
            if ch.number == number:
                self.tune(i)
                return
        self.app.note(f"No channel {number}")
