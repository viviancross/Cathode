"""The mini guide: a few channels around the one you're on, now and next,
over the picture. UP/DOWN scroll it, OK tunes."""

from .. import remote as R
from ..app import Screen

ROWS = 5


class MiniGuide(Screen):
    name = "miniguide"
    IDLE = 10.0

    def __init__(self, app):
        super().__init__(app)
        self.idx = app.live.idx
        self._timer = None
        self._arm()

    def _arm(self):
        self.app.cancel(self._timer)
        self._timer = self.app.after(self.IDLE, lambda: self in self.app.screens and self.app.pop(self))

    def rows(self):
        """[(channel, now, next, selected)] centred on the selection."""
        chans = self.app.channels
        n = len(chans)
        if not n:
            return []
        out = []
        for k in range(-(ROWS // 2), ROWS - ROWS // 2):
            if n < ROWS and not 0 <= self.idx + k < n:
                continue
            ch = chans[(self.idx + k) % n]
            cur, nxt = self.app.live.programs(ch)
            out.append((ch, cur, nxt, k == 0))
        return out

    def pick(self, ch):
        self.app.pop(self)
        self.app.live.tune(self.app.channels.index(ch))

    def handle(self, a: str) -> bool:
        n = len(self.app.channels)
        if not n:
            self.app.pop(self)
            return True
        self._arm()
        if a in (R.DOWN, R.CH_UP):          # down the list, as in the guide; CH+ is the next channel
            self.idx = (self.idx + 1) % n
        elif a in (R.UP, R.CH_DOWN):
            self.idx = (self.idx - 1) % n
        elif a == R.SELECT:
            self.pick(self.app.channels[self.idx])
        elif a in (R.BROWSE, R.BACK, R.EXIT):
            self.app.pop(self)
        elif a in (R.GUIDE, R.PREV) or a in R.DIGITS:
            self.app.pop(self)
            return False                    # live TV takes it from here
        else:
            return a not in (R.VOL_UP, R.VOL_DOWN, R.MUTE, R.MENU, R.FULLSCREEN, R.QUIT)
        return True
