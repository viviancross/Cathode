"""Browse: look at what's on other channels, now and later, without leaving
the one you're watching. SELECT tunes to what you're looking at."""

from datetime import datetime, timedelta, timezone

from .. import remote as R
from ..app import Screen


class Browse(Screen):
    name = "browse"
    IDLE = 8.0                  # seconds without a press before it closes

    def __init__(self, app, step: int = 1):
        super().__init__(app)
        live = app.live
        self.idx = (live.idx + step) % len(app.channels) if app.channels else 0
        self.ahead = 0          # programmes after the one on now
        self._timer = None
        self._arm()

    def _arm(self):
        self.app.cancel(self._timer)
        self._timer = self.app.after(self.IDLE, lambda: self in self.app.screens and self.app.pop(self))

    @property
    def channel(self):
        return self.app.channels[self.idx] if self.app.channels else None

    def program(self):
        """The programme being looked at: on now, or `ahead` after it."""
        ch, epg = self.channel, self.app.epg
        cid = epg.resolve_channel_id(ch.epg_id, ch.name) if ch else None
        if not cid:
            return None, None
        now = datetime.now(timezone.utc)
        progs = epg.programs_in_window(cid, now, now + timedelta(days=30))
        if not progs:
            return None, None
        i = min(self.ahead, len(progs) - 1)
        return progs[i], (progs[i + 1] if i + 1 < len(progs) else None)

    def handle(self, a: str) -> bool:
        n = len(self.app.channels)
        if not n:
            self.app.pop(self)
            return True
        self._arm()
        if a in (R.UP, R.CH_UP):
            self.idx, self.ahead = (self.idx + 1) % n, 0
        elif a in (R.DOWN, R.CH_DOWN):
            self.idx, self.ahead = (self.idx - 1) % n, 0
        elif a == R.RIGHT:
            self.ahead += 1
            if self.program()[0] is None or self.ahead > 48:
                self.ahead -= 1
        elif a == R.LEFT:
            if self.ahead:
                self.ahead -= 1
            else:
                self.app.pop(self)
        elif a == R.SELECT:
            self.app.pop(self)
            self.app.live.tune(self.idx)
        elif a in (R.BROWSE, R.BACK, R.EXIT, R.INFO):
            self.app.pop(self)
        elif a in R.DIGITS or a in (R.GUIDE, R.PREV):
            self.app.pop(self)
            return False                  # let live TV act on it
        else:
            return a not in (R.VOL_UP, R.VOL_DOWN, R.MUTE, R.MENU, R.FULLSCREEN, R.QUIT)
        return True
