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
        self.standby = False        # dead stream: the "please stand by" card
        self.message = "Loading channels..." if app.config.playlist_url else \
            "No playlist set up yet. Start Cathode with --playlist <M3U URL or file>."
        self.banner_until = 0.0
        self.banner_full = False    # INFO pressed again: the expanded banner
        self.volume_until = 0.0
        self.digits = ""
        self._reveal_start = 0.0
        self._timeout = self._digit_timer = self._banner_timer = None

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

    def tune(self, idx: int):
        """Change channel: cover the picture until the new stream's first frame
        is up (or the timeout gives up on it), with the banner showing."""
        if not self.channels:
            return
        idx %= len(self.channels)
        if self.phase != "idle" and idx != self.idx:
            self.prev = self.idx
        self.idx = idx
        ch = self.channels[idx]
        self.phase, self.standby = "cover", False
        self.app.cancel(self._timeout)
        self._timeout = self.app.after(self.app.config.tune_timeout, self._timed_out)
        self.app.video.play(ch.url)
        self.app.config.last_channel = ch.number
        self.show_banner()
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

    def on_video(self, kind, **data):
        if kind == "video_started":
            self.standby = False
            if self.phase == "cover":
                self._reveal()
        elif kind == "video_ended" and self.channels and self.phase in ("watch", "reveal"):
            # A live stream that ends has dropped; pick it back up.
            print(f"[cathode] stream ended ({data.get('reason')}), retuning")
            self.app.after(2.0, lambda i=self.idx: self.idx == i and self.tune(i))

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
        if not self.channels and a not in (R.VOL_UP, R.VOL_DOWN, R.MUTE):
            return False
        if a in (R.UP, R.CH_UP):
            self.tune(self.idx + 1)
        elif a in (R.DOWN, R.CH_DOWN):
            self.tune(self.idx - 1)
        elif a == R.PAGE_UP:
            self.tune(self.idx + 10)
        elif a == R.PAGE_DOWN:
            self.tune(self.idx - 10)
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
        elif a in (R.INFO, R.SELECT):
            # INFO once shows the banner; again expands it to the description.
            full = self.banner_visible() and not self.banner_full
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
        else:
            return False
        return True

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
        self.app.invalidate()       # no such channel: the digits just clear
