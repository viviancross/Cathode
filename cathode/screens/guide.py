"""The program guide: a grid of channels by time, filtered by category.
Navigation state only; the skin decides how many rows fit and draws it."""

import math
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
        self.sel_min = 0            # the chosen cell's time, minutes from now; always inside the window
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

    @staticmethod
    def _base():
        """Now, on the half hour: what offset_min and sel_min count from."""
        now = datetime.now(timezone.utc)
        return now.replace(minute=(now.minute // SLOT) * SLOT, second=0, microsecond=0)

    def window(self):
        """(start, end) of the visible time window, start on a half hour."""
        start = self._base() + timedelta(minutes=self.offset_min)
        return start, start + timedelta(hours=self.hours)

    def sel_time(self):
        """When the chosen cell is: on the cursor row, the programme airing
        then is the one lit."""
        return self._base() + timedelta(minutes=self.sel_min)

    def selected_program(self):
        """The programme in the chosen cell, for the skin's header."""
        ch = self.selected()
        if not ch:
            return None
        epg = self.app.epg
        cid = epg.resolve_channel_id(ch.epg_id, ch.name)
        return epg.current_program(cid, self.sel_time()) if cid else None

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

    def set_category(self, name: str):
        """Straight to a list by name (a skin's labelled button)."""
        cats = self.app.categories()
        if name in cats:
            self.cat_idx, self.focus = cats.index(name), "grid"
            self.cursor = self.top = 0
            self._clamp()

    def _pick_category(self):
        """The lists as a pop-up (THEMES, or OPTIONS for a pad): one press to
        any category instead of cycling through them all."""
        from functools import partial
        from .menu import Item, Options

        def pick(i):
            self.cat_idx, self.focus = i, "grid"
            self.cursor = self.top = 0
            self._clamp()
        cats = self.app.categories()
        title = getattr(self.app.skin, "lists_title", "CATEGORIES")      # what this box called them
        menu = Options(self.app, title, [Item(c, action=partial(pick, i), close=True) for i, c in enumerate(cats)])
        menu.cursor = self.cat_idx
        self.app.push(menu)

    def _time(self, minutes: int):
        # Never before now; never past what the guide data covers.
        limit = self.app.epg_horizon_min() - self.hours * 60
        self.offset_min = max(0, min(self.offset_min + minutes, max(0, limit)))
        if minutes:                     # a jump: the cursor to the window's first column
            self.sel_min = self.offset_min
        self.sel_min = max(self.offset_min, min(self.sel_min, self.offset_min + self.hours * 60 - 1))

    def _cell_starts(self, ch):
        """Minutes from now of each cell's start on a row, the one airing now
        at 0 (a programme that began earlier counts from now)."""
        epg = self.app.epg
        cid = epg.resolve_channel_id(ch.epg_id, ch.name)
        base = self._base()
        progs = epg.programs_in_window(cid, base, base + timedelta(minutes=max(1, self.app.epg_horizon_min()))) \
            if cid else []
        return sorted({max(0, math.ceil((p.start - base).total_seconds() / 60)) for p in progs})

    def _step(self, d: int):
        """LEFT/RIGHT on the grid: the previous or next cell on the cursor row,
        the way a box's highlight walks the row; the window slides only when
        the chosen cell would leave it, and never before now."""
        ch = self.selected()
        starts = self._cell_starts(ch) if ch else []
        if starts:
            beyond = [m for m in starts if (m > self.sel_min if d > 0 else m < self.sel_min)]
            if not beyond:
                return
            target = min(beyond) if d > 0 else max(beyond)
        else:
            target = self.sel_min + d * SLOT        # no listings: half-hour cells
        mins = self.hours * 60
        target = max(0, target)
        if target < self.offset_min:
            self.offset_min = target // SLOT * SLOT
        elif target >= self.offset_min + mins:
            self.offset_min = target // SLOT * SLOT - mins + SLOT
        self.sel_min = target
        self._time(0)

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
            self._cycle_category(-1) if self.focus == "category" else self._step(-1)
        elif a == R.RIGHT:
            self._cycle_category(1) if self.focus == "category" else self._step(1)
        elif a == R.REW:
            self._time(-self.app.skin.guide_jump_min)     # a day back (12 hours on the HR20)
        elif a == R.FF:
            self._time(self.app.skin.guide_jump_min)
        elif a in (R.THEMES, R.OPTIONS):
            self._pick_category()
        elif a == R.INFO:
            if self.selected():
                self.app.push(ProgramInfo(self.app, self.selected(), self.selected_program()))
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


class ProgramInfo(Screen):
    """INFO on a guide cell: the programme in that cell, as a pop-up over the
    grid (the SD skins have no header to describe it in). INFO again, BACK
    or EXIT close it."""
    name = "program_info"

    def __init__(self, app, channel, program):
        super().__init__(app)
        self.channel, self.program = channel, program

    @property
    def title(self) -> str:
        return self.program.title if self.program else "No information"

    def lines(self):
        """The channel, when it's on (with its rating and genre), and the
        synopsis, each a line for the skin to wrap."""
        ch, p = self.channel, self.program
        out = [f"{ch.number} {ch.name}"]
        if p:
            a, b = p.start.astimezone(), p.stop.astimezone()
            when = f"{a:%I:%M}-{b:%I:%M %p}".lstrip("0").replace("-0", "-")
            out.append("   ".join(x for x in (when, p.rating, p.category, p.episode) if x))
            out.append(p.description or "No further information.")
        else:
            out.append("No information is available for this time.")
        return out

    def handle(self, a: str) -> bool:
        if a in (R.INFO, R.BACK, R.EXIT, R.SELECT):
            self.app.pop(self)
        return a not in _PASS_THROUGH
