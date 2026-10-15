"""The program guide: a grid of channels by time, filtered by category.
Navigation state only; the skin decides how many rows fit and draws it."""

from datetime import datetime, timedelta, timezone

from .. import remote as R
from ..app import Screen

SLOT = 30                   # minutes per LEFT/RIGHT step


class Guide(Screen):
    name = "guide"
    opaque = True

    def __init__(self, app, category: str = "All"):
        super().__init__(app)
        self.focus = "grid"         # grid | category
        self.offset_min = 0         # window start, minutes from now (rounded)
        cats = app.categories()
        self.cat_idx = cats.index(category) if category in cats else 0
        self.top = 0                # first visible row
        self.cursor = 0             # selected row in the filtered list
        live = app.live
        if live.channel in self.filtered():
            self.cursor = self.filtered().index(live.channel)
        self._clamp()

    # ── Data ──────────────────────────────────────────────────────────────

    @property
    def rows(self) -> int:
        return self.app.skin.guide_rows

    @property
    def hours(self) -> int:
        return self.app.skin.guide_hours

    @property
    def category(self) -> str:
        cats = self.app.categories()
        return cats[self.cat_idx % len(cats)]

    def filtered(self):
        return self.app.channels_in(self.category)

    def selected(self):
        vis = self.filtered()
        return vis[self.cursor] if self.focus == "grid" and 0 <= self.cursor < len(vis) else None

    def window(self):
        """(start, end) of the visible time window, start on a half hour."""
        now = datetime.now(timezone.utc)
        base = now.replace(minute=(now.minute // SLOT) * SLOT, second=0, microsecond=0)
        start = base + timedelta(minutes=self.offset_min)
        return start, start + timedelta(hours=self.hours)

    def video_box(self):
        return self.app.skin.guide_video_box()

    # ── Navigation ────────────────────────────────────────────────────────

    def _clamp(self):
        n = len(self.filtered())
        self.cursor = max(0, min(self.cursor, n - 1)) if n else 0
        if self.cursor < self.top:
            self.top = self.cursor
        elif self.cursor >= self.top + self.rows:
            self.top = self.cursor - self.rows + 1
        self.top = max(0, min(self.top, max(0, n - self.rows)))

    def _move(self, d: int):
        n = len(self.filtered())
        if self.focus == "category":
            # Leaving the category bar: down to the top row, up to the bottom.
            self.focus = "grid"
            self.cursor = 0 if d > 0 else n - 1
        elif (d < 0 and self.cursor == 0) or (d > 0 and self.cursor >= n - 1) or not n:
            self.focus = "category"         # past either end: the category bar
            return
        else:
            self.cursor += d
        self._clamp()

    def _cycle_category(self, d: int):
        self.cat_idx = (self.cat_idx + d) % len(self.app.categories())
        self.cursor = self.top = 0
        self._clamp()

    def _time(self, minutes: int):
        # Never before now; never past what the guide data covers.
        limit = self.app.epg_horizon_min() - self.hours * 60
        self.offset_min = max(0, min(self.offset_min + minutes, max(0, limit)))

    def handle(self, a: str) -> bool:
        if a in (R.GUIDE, R.EXIT, R.BACK):
            self.app.pop(self)
        elif a == R.UP:
            self._move(-1)
        elif a == R.DOWN:
            self._move(1)
        elif a in (R.PAGE_UP, R.CH_UP):
            self.focus = "grid"
            self.cursor -= self.rows
            self.top -= self.rows
            self._clamp()
        elif a in (R.PAGE_DOWN, R.CH_DOWN):
            self.focus = "grid"
            self.cursor += self.rows
            self.top += self.rows
            self._clamp()
        elif a == R.LEFT:
            self._cycle_category(-1) if self.focus == "category" else self._time(-SLOT)
        elif a == R.RIGHT:
            self._cycle_category(1) if self.focus == "category" else self._time(SLOT)
        elif a == R.REW:
            self._time(-24 * 60)            # day back
        elif a == R.FF:
            self._time(24 * 60)             # day ahead
        elif a == R.THEMES:
            self._cycle_category(1)
        elif a == R.FAV:
            ch = self.selected()
            if ch:
                self.app.toggle_favorite(ch)
                self._clamp()
        elif a == R.SELECT:
            if self.focus == "category":
                self.focus = "grid"
                self._clamp()
            elif self.selected():
                self.app.pop(self)
                self.app.live.tune(self.app.channels.index(self.selected()))
        elif a in R.DIGITS:
            # Typed numbers tune straight away, as on live TV.
            self.app.pop(self)
            self.app.live.handle(a)
        else:
            # Volume, the menu and window keys still reach what's underneath;
            # nothing else may (UP on live TV would change the channel).
            return a not in _PASS_THROUGH
        return True


_PASS_THROUGH = {R.VOL_UP, R.VOL_DOWN, R.MUTE, R.MENU, R.FULLSCREEN, R.QUIT}
