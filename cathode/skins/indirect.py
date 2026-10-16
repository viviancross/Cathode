"""InDirecTV: a mid-2000s DirecTV-style box, drawn to measurements taken from
frames of the real receivers. InDirecTV HD follows the HR20 (2007): a
near-white title area over a light facts strip, white synopsis on a cyan
page, a navy-and-teal grid inside a frame, amber selection, the colour keys
along the bottom; setup-style menu pages with the picture kept top-right.
InDirecTV (SD) is the D10/R15 era: the same screens compressed to 4:3 on a
navy ground, gold selection.

Geometry is written in the HR20's own 1280x720 pixels; X() and Y() scale it
to the canvas (the SD frame scales the two axes differently)."""

import shutil
import time
from datetime import datetime, timedelta, timezone

import pygame

from .box import BoxSkin, mix, rgba, vgrad


def ampm(dt) -> str:
    """'6:00a' / '7:30p', the box's own clock style."""
    return dt.astimezone().strftime("%I:%M%p").lstrip("0").lower()[:-1]


def hours(prog) -> str:
    return f"{ampm(prog.start)} - {ampm(prog.stop)}"


def stamp(dt=None) -> str:
    """'Mon 5:46a': the day and clock the banner and guide carry."""
    dt = dt or datetime.now()
    return f"{dt:%a} {ampm(dt)}"


DOTS = {"red": (245, 28, 46), "green": (17, 164, 96), "yellow": (221, 216, 60)}


class InDirectHD(BoxSkin):
    name = "indirect_hd"
    label = "InDirecTV HD"
    canvas = (1280, 720)
    browse_style = "mini"           # BROWSE opens the mini guide
    guide_hours = 1.5               # three half-hour columns, as the box showed
    guide_rows = 6
    guide_jump_min = 12 * 60        # the red and green keys: -12hrs / +12hrs
    default_font = "barlow"         # the HR20's DIN-like screen face: Barlow matches its letterforms
    SD = False
    # Measured: the header navy, the program-cell teal, the amber, the logo blue.
    NATIVE = {"bg": [8, 36, 75], "accent": [10, 70, 112], "accent2": [240, 165, 22],
              "text": [255, 255, 255], "chnum": [15, 154, 209]}

    def roles(self, b):
        navy, cell, sel, text, sky = b["bg"], b["accent"], b["accent2"], b["text"], b["chnum"]
        return {
            "navy": navy, "cell": cell, "cell_hi": mix(cell, (255, 255, 255), 0.06),
            "gap": mix(navy, cell, 0.7), "sky": sky,
            "sel": sel, "sel_ink": text, "sel_shadow": mix(sel, (0, 0, 0), 0.75),
            "text": text, "soft": mix(sky, text, 0.45), "mark": mix(sky, text, 0.4),
            "page_top": mix(sky, navy, 0.15), "page_mid": sky, "page_bot": mix(sky, navy, 0.4),
            "paper_top": mix(text, sky, 0.06), "paper_bot": mix(text, sky, 0.02),
            "strip": mix(text, sky, 0.3), "strip_rule": mix(text, sky, 0.08),
            "ink": mix(navy, (60, 40, 110), 0.4), "strip_ink": mix(cell, (80, 120, 140), 0.5),
            "watermark": mix(text, navy, 0.3),
            "band": (33, 132, 193), "band_edge": (0, 68, 126), "paper": (244, 238, 253),
            "paper_ink": (23, 85, 129), "keybar": (55, 100, 142),
            "teal": mix(cell, sky, 0.45), "teal_dark": mix(cell, sky, 0.2), "panel": mix(cell, navy, 0.15),
            "margin": mix(cell, sky, 0.7), "bar": mix(sky, text, 0.55), "deep": mix(navy, (0, 0, 0), 0.4),
            # The pages wear the guide's colours (the user's call): navy
            # headers and channel cells, teal cells, the amber cursor with
            # white shadowed lettering, the white title area, the sky band.
            "row": cell, "row_rule": mix(navy, cell, 0.7), "row_head": navy, "pnl": mix(cell, navy, 0.15),
            "pnl_bot": mix(cell, navy, 0.5), "btn": navy, "orange": sel, "orange_ink": text,
            "label": mix(sky, text, 0.45), "tip": text, "dim": mix(sky, text, 0.45), "clock": text,
            "key": navy, "key_edge": mix(navy, cell, 0.7), "field": mix(navy, (0, 0, 0), 0.4),
            "od_col": navy, "od_panel": mix(cell, navy, 0.15), "od_row": cell, "od_row2": mix(cell, navy, 0.2),
            "od_bar": cell, "od_tile": mix(text, sky, 0.06), "od_tag": sky, "od_sel": sel,
            "od_ink": mix(navy, (60, 40, 110), 0.4),
            "tk_band": (33, 132, 193), "tk_bar": sel, "tk_state": navy, "tk_tile": mix(text, sky, 0.06),
            "pop_head": mix(text, sky, 0.06), "pop_body": navy,
        }

    # ── Geometry: the box's own pixels, scaled to the canvas ──────────────

    def X(self, v) -> int:
        return int(round(v * self.canvas[0] / 1280))

    def Y(self, v) -> int:
        return int(round(v * self.canvas[1] / 720))

    def R(self, x, y, w, h) -> pygame.Rect:
        return pygame.Rect(self.X(x), self.Y(y), self.X(w), self.Y(h))

    def u(self, v) -> int:          # kept for the shared pieces in BoxSkin
        return self.Y(v)

    # ── Wordmark ──────────────────────────────────────────────────────────

    def tile(self, c, rect, fill):
        """The blue tile with a white swoosh: our own mark."""
        rect = pygame.Rect(rect)
        s = min(rect.w, rect.h)
        vgrad(c, rect, rgba(mix(fill, (255, 255, 255), 0.3)), rgba(fill), radius=max(3, s // 6))
        lens = rect.inflate(-s // 4, -s // 4)
        pygame.draw.ellipse(c, (255, 255, 255), lens)
        pygame.draw.ellipse(c, fill, lens.inflate(-s // 12, -s // 12).move(-s // 7, s // 9))

    def mark_stacked(self, c, x, y, ink):
        """Tile over the spaced wordmark, as the box stacked its logo."""
        self.tile(c, (x + self.X(4), y, self.X(66), self.Y(55)), self.b["sky"])
        self._spaced(c, "InDirecTV", self.fb(self.Y(17)), ink, x, y + self.Y(62), self.X(2))

    def mark_inline(self, c, x, y, size, ink):
        """Tile beside the wordmark, for the banner; returns the width."""
        s = self.Y(size)
        self.tile(c, (x, y, s, s), self.b["sky"])
        return s + self.X(10) + self._spaced(c, "InDirecTV", self.fb(int(s * 0.62)), ink, x + s + self.X(10),
                                              y + (s - self.text.ink(self.fb(int(s * 0.62)))[1]) // 2, self.X(2))

    def _spaced(self, c, s, f, ink, x, y, gap) -> int:
        x0 = x
        for ch in s:
            x += self.text.draw(c, ch, f, ink, x, y) + gap
        return x - gap - x0

    # ── Pieces ────────────────────────────────────────────────────────────

    def _page(self, c, rect):
        """The cyan page: lightest a third of the way down, darker at the foot."""
        rect = pygame.Rect(rect)
        knee = rect.y + int(rect.h * 0.26)
        vgrad(c, (rect.x, rect.y, rect.w, knee - rect.y), rgba(self.b["page_top"]), rgba(self.b["page_mid"]))
        vgrad(c, (rect.x, knee, rect.w, rect.bottom - knee), rgba(self.b["page_mid"]), rgba(self.b["page_bot"]))

    def _top(self, c, title, watermark):
        """What every full page shares: the white title area, the facts strip,
        the stacked mark, the title beside it, the watermark, the picture."""
        b, t = self.b, self.text
        vgrad(c, self.R(0, 0, 1280, 146), rgba(b["paper_top"]), rgba(b["paper_bot"]))
        pygame.draw.rect(c, b["strip"], self.R(0, 146, 1280, 46))
        self.mark_stacked(c, self.X(96), self.Y(49), b["ink"])
        f_title = self.fb(self.Y(36))
        t.draw(c, t.fit(f_title, title, self.X(830) - self.X(300)), f_title, b["ink"], self.X(300), self.Y(108))
        t.draw(c, watermark, self.fb(self.Y(40)), b["watermark"], self.X(830), self.Y(57), align="right")
        return self._picture(c)

    def _picture(self, c):
        vx, vy, vw, vh = self.guide_video_box()
        pygame.draw.rect(c, (0, 0, 0, 0), (vx, vy, vw, vh))
        pygame.draw.rect(c, rgba(self.b["text"]), (vx - 3, vy - 3, vw + 6, vh + 6), 3)
        return pygame.Rect(vx, vy, vw, vh)

    def guide_video_box(self):
        r = self.R(850, 49, 323, 182)
        return (r.x, r.y, r.w, r.h)

    def _shadowed(self, c, s, f, ink, shadow, x, y, align="left"):
        if shadow:
            self.text.draw(c, s, f, shadow, x + 1, y + 1, align=align)
        return self.text.draw(c, s, f, ink, x, y, align=align)

    # ── Live: banner, digits, signal loss, volume, trick ──────────────────

    def _band(self, c, rect):
        """The translucent sky-blue band laid over the picture, a darker edge
        along its top."""
        rect = pygame.Rect(rect)
        band = pygame.Surface(rect.size, pygame.SRCALPHA)
        band.fill((*self.b["band"], 225))
        c.blit(band, rect.topleft)
        pygame.draw.rect(c, self.b["band_edge"], (rect.x, rect.y, rect.w, self.Y(8)))

    def _banner(self, c, ch, cur, nxt, full=False, tag=None):
        """The channel banner as the HR20 drew it: logo, number over call
        sign, the title; a white strip of facts; the favourites bar with the
        colour keys. INFO again adds the synopsis under it."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._band(c, self.R(0, 0, 1280, 131))
        epg = self.app.epg
        url = epg.icon_url(epg.resolve_channel_id(ch.epg_id, ch.name)) if epg else ""
        logo = self.logo(url or ch.logo, X(110), Y(62))
        if logo:
            c.blit(logo, logo.get_rect(center=(X(155), Y(92))))
        else:
            self.tile(c, (X(100), Y(60), X(66), Y(62)), b["sky"])
        f_num, f_call, f_title = self.fb(Y(36)), self.f(Y(34)), self.fb(Y(34))
        t.draw(c, str(ch.number), f_num, b["text"], X(240), Y(62))
        call, size = ch.name.upper(), 34
        while size > 20 and t.width(self.f(Y(size)), call) > X(135):    # a long name: smaller before an ellipsis
            size -= 1
        fc = self.f(Y(size))
        t.draw(c, t.fit(fc, call, X(135)), fc, b["text"], X(240), Y(99) + (t.ink(f_call)[1] - t.ink(fc)[1]))
        group = t.fit(f_call, ch.group, X(260)) if ch.group else ""
        room = min(X(560), X(1105) - (t.width(f_call, group) + X(30) if group else 0) - X(385))
        t.draw(c, t.fit(f_title, cur.title if cur else ch.name, room), f_title, b["text"], X(385), Y(97))
        if group:
            t.draw(c, group, f_call, b["text"], X(1105), Y(99), align="right")
        strip = self.R(0, 131, 1280, 55)
        paper = pygame.Surface(strip.size, pygame.SRCALPHA)
        paper.fill((*b["paper"], 240))
        c.blit(paper, strip.topleft)
        fs = self.fb(Y(23))
        sy = strip.y + (strip.h - t.ink(fs)[1]) // 2
        t.draw(c, stamp(), fs, b["paper_ink"], X(96), sy)
        if cur:
            t.draw(c, hours(cur), fs, b["paper_ink"], X(385), sy)
            if cur.rating:
                t.draw(c, cur.rating, fs, b["paper_ink"], X(808), sy)
        lock = pygame.Rect(X(1112), strip.y + Y(18), X(26), Y(18))      # the box's lock, open
        pygame.draw.rect(c, b["paper_ink"], lock, 3, border_radius=3)
        pygame.draw.arc(c, b["paper_ink"], (lock.x + X(4), lock.y - Y(12), X(16), Y(20)), 0.2, 3.0, 3)
        bar = self.R(96, 186, 1088, 22)
        kb = pygame.Surface(bar.size, pygame.SRCALPHA)
        kb.fill((*b["keybar"], 215))
        c.blit(kb, bar.topleft)
        fk = self.fb(Y(18))
        ky = bar.y + (bar.h - t.ink(fk)[1]) // 2
        t.draw(c, f"Favorites List:  {g_list(self)}", fk, b["text"], X(112), ky)
        # Where the HR20 showed its colour buttons, the keys that work here,
        # named as on Cathode's remote (it has no colour buttons).
        fc = self.fb(Y(12))
        x = bar.right - X(16)
        for key, label in ((self.k("BROWSE"), "Mini Guide"), (self.k("MENU"), "Menu")):
            x -= t.width(fk, label)
            t.draw(c, label, fk, b["text"], x, ky)
            chip = pygame.Rect(0, bar.y + Y(2), t.width(fc, key) + X(14), bar.h - Y(4))
            chip.right = x - X(8)
            pygame.draw.rect(c, b["paper"], chip, border_radius=Y(4))
            t.draw(c, key, fc, b["paper_ink"], chip.centerx, chip.y + (chip.h - t.ink(fc)[1]) // 2, align="center")
            x = chip.x - X(30)
        if tag:
            self.chip(c, X(96), bar.bottom + Y(8), tag, self.fb(Y(16)), rgba(b["sel"]), b["sel_ink"])
        if full and cur and cur.description:
            f = self.f(Y(22))
            lines = t.wrap(f, cur.description, X(1088), 3)
            d = pygame.Rect(0, bar.bottom + Y(4), W, Y(16) + len(lines) * Y(30))
            dd = pygame.Surface(d.size, pygame.SRCALPHA)
            dd.fill((*b["navy"], 226))
            c.blit(dd, d.topleft)
            y = d.y + Y(10)
            for line in lines:
                t.draw(c, line, f, b["text"], X(96), y)
                y += Y(30)
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def _digits(self, c, digits):
        """Typed digits take the channel's place on a short band."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._band(c, self.R(0, 0, 1280, 70))
        t.draw(c, digits + "-" * (3 - len(digits)), self.fb(Y(36)), b["text"], X(240), Y(16))
        t.draw(c, stamp(), self.fb(Y(24)), b["text"], X(1184), Y(22), align="right")

    def _volume(self, c, cx, cy):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        v = self.app.video
        r = self.R(340, 630, 600, 50)
        self._band(c, r)
        f = self.fb(Y(22))
        t.draw(c, "MUTE" if v.muted else "VOLUME", f, (245, 28, 46) if v.muted else b["text"], r.x + X(20),
               r.y + (r.h - t.ink(f)[1]) // 2)
        bar = pygame.Rect(r.x + X(150), r.y + Y(18), X(420), Y(14))
        pygame.draw.rect(c, b["gap"], bar)
        if not v.muted:
            n, seg = 20, X(420) // 20
            for i in range(int(round(v.volume / 5))):
                pygame.draw.rect(c, b["sky"], (bar.x + i * seg, bar.y, seg - X(2), bar.h))

    def _trick(self, c, s):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(96, 600, 1088, 70)
        self._band(c, r)
        behind = s["behind"]
        mm, ss = divmod(int(behind), 60)
        tag = ("PAUSE" if s["paused"] else "LIVE" if behind < 2 else "PLAY")
        f = self.fb(Y(26))
        t.draw(c, tag, f, b["sel"] if s["paused"] else b["text"], r.x + X(20), r.y + (r.h - t.ink(f)[1]) // 2)
        bar = pygame.Rect(r.x + X(190), r.y + Y(29), X(760), Y(12))
        pygame.draw.rect(c, b["gap"], bar)
        span = s["buffer"] + behind
        if span >= 2:
            x = bar.x + int(bar.w * s["buffer"] / span)
            pygame.draw.rect(c, b["sky"], (bar.x, bar.y, x - bar.x, bar.h))
            pygame.draw.rect(c, b["text"], (x - X(2), bar.y - Y(6), X(4), bar.h + Y(12)))
        t.draw(c, f"-{mm}:{ss:02d}" if behind >= 1 else "LIVE", self.fb(Y(22)), b["soft"], r.right - X(20),
               r.y + (r.h - t.ink(self.fb(Y(22)))[1]) // 2, align="right")

    def _note(self, c, text, frac=None):
        """A short notice on the sky band, bottom left; an amber bar under
        the text when frac is a known fraction."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        bar = frac is not None and frac >= 0
        f = self.fb(Y(24))
        r = self.R(96, 0, 0, 0)
        r.w = max(t.width(f, text) + X(48), X(520) if bar else 0)
        r.h = Y(76 if bar else 56)
        r.bottom = Y(590)                  # above the subtitle line
        self._band(c, r)
        t.draw(c, text, f, b["text"], r.x + X(24), r.y + Y(20))
        if bar:
            track = pygame.Rect(r.x + X(24), r.bottom - Y(22), r.w - X(48), Y(10))
            pygame.draw.rect(c, b["gap"], track)
            pygame.draw.rect(c, b["sel"], (track.x, track.y, int(track.w * frac), track.h))

    def draw_note(self, c, text):
        self._note(c, text)

    def draw_guide_progress(self, c, frac):
        self._note(c, "Acquiring guide data..." + self.pct(frac), frac)

    def _signal_loss(self, c):
        """The HR20's 'Searching for satellite signal (771)' card: a navy
        band on black, the explanation under it."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        c.fill((0, 0, 0, 255))
        band = self.R(0, 150, 1280, 96)
        pygame.draw.rect(c, b["navy"], band)
        pygame.draw.rect(c, b["sky"], (band.x, band.y, band.w, Y(3)))
        pygame.draw.rect(c, b["sky"], (band.x, band.bottom - Y(3), band.w, Y(3)))
        t.draw(c, "Searching for satellite signal. (771)", self.fb(Y(28)), b["text"], X(96), band.y + Y(32))
        f = self.f(Y(22))
        y = band.bottom + Y(26)
        for line in t.wrap(f, "The channel isn't sending a picture. Cathode keeps trying; press GUIDE or "
                              "a channel number to watch something else.", X(1088), 3):
            t.draw(c, line, f, b["soft"], X(96), y)
            y += Y(32)

    # ── Guide ─────────────────────────────────────────────────────────────

    def draw_guide(self, c, g):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        sel = g.selected()
        now = datetime.now(timezone.utc)
        cur = self.app.live.programs(sel)[0] if sel else None
        self._page(c, self.R(0, 192, 1280, 528))
        self._top(c, cur.title if cur else (sel.name if sel else ""), "guide")

        # The strip: when, the programme's hours, its rating, light rules between.
        fs = self.f(Y(22))
        sy = Y(146) + (Y(46) - t.ink(fs)[1]) // 2
        t.draw(c, stamp(), fs, b["strip_ink"], X(95), sy)
        for dx in (274, 740):
            pygame.draw.rect(c, b["strip_rule"], self.R(dx, 150, 4, 38))
        if cur:
            t.draw(c, hours(cur), fs, b["strip_ink"], X(300), sy)
            if cur.rating:
                t.draw(c, cur.rating, fs, b["strip_ink"], X(760), sy)
        # The synopsis, white on the page.
        if cur and cur.description:
            fd = self.f(Y(28))
            y = Y(205)
            for line in t.wrap(fd, cur.description + (f" {cur.category}." if cur.category else ""), X(735), 3):
                t.draw(c, line, fd, b["text"], X(95), y)
                y += Y(36)

        # The frame: a navy header, navy channel cells, teal cells, the colour keys.
        pygame.draw.rect(c, b["gap"], self.R(96, 313, 1182, 359))
        hdr = self.R(96, 313, 1182, 35)
        pygame.draw.rect(c, b["navy"], hdr)
        start, end = g.window()
        fh = self.fb(Y(29))
        hy = hdr.y + (hdr.h - t.ink(fh)[1]) // 2
        day = start.astimezone()
        t.draw(c, f"{day:%a} {day.month}/{day.day}", fh, b["text"], X(105), hy)
        slots = int(g.hours * 2)
        col = 885 / slots
        for i in range(slots):
            t.draw(c, ampm(start + timedelta(minutes=30 * i)), fh, b["text"], X(294 + col * i), hy)

        rows = g.filtered()[g.top: g.top + g.rows]
        mins = g.hours * 60
        epg = self.app.epg
        f_cell, f_ch = self.f(Y(30)), self.fb(Y(30))
        grid_x, grid_w = X(294), X(890)
        for i, ch in enumerate(rows):
            y = Y(352 + 48 * i)
            rh = Y(44)
            row_sel = g.focus == "grid" and g.top + i == g.cursor
            chr_ = pygame.Rect(X(96), y, X(199), rh)
            pygame.draw.rect(c, b["navy"], chr_)
            cy = y + (rh - t.ink(f_cell)[1]) // 2
            label, size = f"{ch.number} {ch.name}", 30
            while size > 21 and t.width(self.f(Y(size)), label) > chr_.w - X(24):
                size -= 1
            fl = self.f(Y(size))
            t.draw(c, t.fit(fl, label, chr_.w - X(24)), fl, b["text"], X(110), y + (rh - t.ink(fl)[1]) // 2)
            if self.app.is_favorite(ch):
                pygame.draw.circle(c, b["sel"], (chr_.right - X(12), y + Y(10)), Y(4))
            self._cell(c, pygame.Rect(grid_x + grid_w, y, X(1278) - grid_x - grid_w, rh), False)
            cid = epg.resolve_channel_id(ch.epg_id, ch.name) if epg else None
            progs = epg.programs_in_window(cid, start, end) if cid else []
            if not progs:
                cell = pygame.Rect(grid_x, y, grid_w - X(12), rh)
                self._cell(c, cell, row_sel)
                self._shadowed(c, "No information", f_cell, b["sel_ink"] if row_sel else b["soft"],
                               b["sel_shadow"] if row_sel else None, cell.x + X(8), cy)
            for p in progs:
                a = max(0.0, (p.start - start).total_seconds() / 60)
                e = min(float(mins), (p.stop - start).total_seconds() / 60)
                if e <= a:
                    continue
                cell = pygame.Rect(grid_x + int(a / mins * grid_w), y, int((e - a) / mins * grid_w) - X(4), rh)
                on = row_sel and p.start <= max(now, start) < p.stop
                self._cell(c, cell, on)
                ink, shadow = (b["sel_ink"], b["sel_shadow"]) if on else (b["text"], None)
                x = cell.x + X(8)
                if p.start < start:
                    x += self._shadowed(c, "<", f_cell, ink if on else b["mark"], shadow, x, cy) + X(6)
                more = p.stop > end
                avail = cell.right - X(8) - x - (X(18) if more else 0)
                if avail > X(30):
                    self._shadowed(c, t.fit(f_cell, p.title, avail), f_cell, ink, shadow, x, cy)
                if more:
                    self._shadowed(c, ">", f_cell, ink if on else b["mark"], shadow, cell.right - X(8), cy,
                                   align="right")
            self.hit((X(96), y, X(1182), rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                           setattr(g, "focus", "grid"), g.handle("SELECT")))

        if not rows:
            cell = self.R(96, 352, 1170, 44)
            self._cell(c, cell, False)
            t.draw(c, t.fit(f_cell, self.empty_guide(g), cell.w - X(28)), f_cell, b["text"], cell.x + X(14),
                   cell.y + (cell.h - t.ink(f_cell)[1]) // 2)

        bar = self.R(96, 639, 1182, 33)
        pygame.draw.rect(c, b["cell"], bar)
        fl = self.f(Y(30))
        ly = bar.y + (bar.h - t.ink(fl)[1]) // 2
        cat = g.category if g.category != "All" else "Channels I Get"
        t.draw(c, cat, fl, b["sel"] if g.focus == "category" else b["soft"], X(110), ly)
        self.hit((X(96), bar.y, X(400), bar.h), lambda: g.handle("THEMES"))
        for dot, label, dx in (("red", "-12hrs", 619), ("green", "+12hrs", 772), ("yellow", "Guide Options", 926)):
            pygame.draw.circle(c, DOTS[dot], (X(dx + 10), bar.centery), Y(10))
            t.draw(c, label, fl, b["text"], X(dx + 32), ly)

    def _cell(self, c, cell, on):
        b = self.b
        if on:
            self._amber(c, cell)
        else:
            vgrad(c, cell, rgba(b["cell_hi"]), rgba(b["cell"]))

    def _amber(self, c, r):
        """The HR20's amber cursor at full strength: a lit top half, the
        amber body, a darker lip along its foot."""
        b = self.b
        r = pygame.Rect(r)
        top = r.h // 2
        vgrad(c, (r.x, r.y, r.w, top), rgba(mix(b["sel"], (255, 255, 255), 0.42)), rgba(mix(b["sel"], (255, 255, 255), 0.1)))
        pygame.draw.rect(c, b["sel"], (r.x, r.y + top, r.w, r.h - top))
        lip = max(2, r.h // 12)
        pygame.draw.rect(c, mix(b["sel"], (0, 0, 0), 0.32), (r.x, r.bottom - lip, r.w, lip))

    # ── Menu: the setup page ──────────────────────────────────────────────

    def draw_menu(self, c, m):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        vgrad(c, self.R(0, 192, 1280, 528), rgba(b["teal"]), rgba(b["teal_dark"]))
        pygame.draw.rect(c, b["margin"], self.R(1180, 192, 100, 528))
        self._top(c, m.title.title(), "menu")
        fs = self.f(Y(22))
        t.draw(c, stamp(), fs, b["strip_ink"], X(96), Y(146) + (Y(46) - t.ink(fs)[1]) // 2)

        # The list down the left, a light bar on the chosen row.
        rh = Y(39)
        n = len(m.items)
        n_vis = max(1, (Y(650) - Y(214)) // rh)     # room under the list for the page counter
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        f_row = self.f(Y(24))
        for k, i in enumerate(range(first, min(n, first + n_vis))):
            it = m.items[i]
            y = Y(214) + k * rh
            sel = i == m.cursor
            row = pygame.Rect(0, y - Y(5), X(268), rh - Y(4))
            if sel:
                pygame.draw.rect(c, b["bar"], row)
            ink = (b["panel"] if sel else b["text"]) if it.enabled else b["soft"]
            size = 24
            while size > 19 and t.width(self.f(Y(size)), it.label) > X(168):     # smaller before an ellipsis
                size -= 1
            fr = self.f(Y(size))
            t.draw(c, t.fit(fr, it.label, X(168)), fr, ink, X(96), y + (t.ink(f_row)[1] - t.ink(fr)[1]))
            self.hit(row, lambda i=i: m.activate(i))
        if n > n_vis:
            t.draw(c, f"{first + 1}-{min(n, first + n_vis)} of {n}", self.f(Y(18)), b["soft"], X(96), Y(214) + n_vis * rh)

        # The panel on the right explains the chosen row; its setting sits in
        # the box at the bottom, amber when it can be changed here.
        pn = self.R(300, 240, 876, 440)
        pygame.draw.rect(c, b["panel"], pn)
        it = m.items[m.cursor] if 0 <= m.cursor < n else None
        if it:
            fbg = self.fb(Y(26))
            t.draw(c, t.fit(fbg, it.label, pn.w - X(40)), fbg, b["text"], pn.x + X(20), pn.y + Y(20))
            if it.preview:
                hint = f"Press {self.k('SELECT')} to choose this."
            elif it.value and (it.adjust or not it.action):
                hint = "Press LEFT or RIGHT to change this setting." if it.adjust else \
                    f"Press {self.k('SELECT')} to change this setting."
            elif it.submenu:
                hint = f"Press {self.k('SELECT')} to open this page."
            else:
                hint = f"Press {self.k('SELECT')} to choose." if it.enabled else "Not available right now."
            t.draw(c, hint, self.f(Y(22)), b["soft"], pn.x + X(20), pn.y + Y(64))
            box = self.R(912, 560, 256, 110)
            pygame.draw.rect(c, b["deep"], box)
            pygame.draw.rect(c, b["navy"], box, Y(2))
            if it.value:
                v = it.value()
                bar = pygame.Rect(box.x + X(8), box.y + Y(38), box.w - X(16), Y(34))
                pygame.draw.rect(c, b["sel"], bar)
                fv = self.f(Y(22))
                self._shadowed(c, t.fit(fv, f"< {v} >" if it.adjust else v, bar.w - X(16)), fv, b["sel_ink"],
                               b["sel_shadow"], bar.x + X(8), bar.y + (bar.h - t.ink(fv)[1]) // 2)
            else:
                fv = self.f(Y(22))
                t.draw(c, "Open" if it.submenu else "Choose", fv, b["text"], box.x + X(16),
                       box.y + Y(44))
        t.draw(c, f"{self.k('SELECT')}: choose    {self.k('BACK')}: up a level    {self.k('EXIT')}: close", self.f(Y(20)), b["soft"], X(96), Y(690))

    # ── Mini guide ────────────────────────────────────────────────────────

    def draw_miniguide(self, c, mg):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        rows = mg.rows()
        rh = Y(40)
        r = pygame.Rect(0, 0, W, Y(44) + rh * len(rows) + Y(10))
        r.bottom = H
        self._band(c, r)
        fh = self.fb(Y(22))
        t.draw(c, "Mini Guide", fh, b["text"], X(96), r.y + Y(12))
        t.draw(c, stamp(), fh, b["text"], X(1184), r.y + Y(12), align="right")
        f_row = self.f(Y(22))
        y = r.y + Y(44)
        for ch, cur, nxt, sel in rows:
            row = pygame.Rect(X(96), y, X(1088), rh - Y(4))
            if sel:
                self._amber(c, row)
            else:
                vgrad(c, row, rgba(b["cell_hi"]), rgba(b["cell"]))
            ink, shadow = (b["sel_ink"], b["sel_shadow"]) if sel else (b["text"], None)
            ty = row.y + (row.h - t.ink(f_row)[1]) // 2
            self._shadowed(c, t.fit(f_row, f"{ch.number} {ch.name.upper()}", X(230)), f_row, ink, shadow,
                           row.x + X(12), ty)
            self._shadowed(c, t.fit(f_row, cur.title if cur else "No information", X(420)), f_row, ink, shadow,
                           row.x + X(260), ty)
            if nxt:
                self._shadowed(c, t.fit(f_row, f"{ampm(nxt.start)}  {nxt.title}", X(380)), f_row,
                               ink if sel else b["soft"], shadow, row.x + X(700), ty)
            self.hit(row, lambda ch=ch: mg.pick(ch))
            y += rh

    # ── Pages: On Demand, the playlist, info, keyboard, system info ───────
    # The HR20's full pages share the white title area and the picture
    # top-right (_top); the box's own pixels, from frames of the real one.

    poster_wall = True              # its On Demand had the Top Picks posters
    keyboard_layer = "ABC"          # the box's grid was capitals
    OD_COLS = 6

    def page_video_box(self, screen):
        return self.guide_video_box()

    def ondemand_cols(self, screen):
        return self.OD_COLS

    def ondemand_page(self, screen):
        if screen.view == "wall":
            return self.OD_COLS * 2
        return 6 if self._is_playlist(screen) else 9      # 9 x 44 inside the 408 panel

    @staticmethod
    def _is_playlist(s):
        return bool(s.level) and s.level.get("key") == "recordings"

    def _ital(self, c, s, f, ink, x, y, align="left", shadow=None):
        """The playlist's bold italic, slanted from the bold face."""
        f.italic = True
        try:
            if shadow:
                self.text.draw(c, s, f, shadow, x + 1, y + 1, align=align)
            return self.text.draw(c, s, f, ink, x, y, align=align)
        finally:
            f.italic = False

    def _blue(self, c):
        """The blue page under the title area."""
        self._page(c, self.R(0, 192, 1280, 528))

    def _hint(self, c, x, y, key, label, ink, chip):
        """A remote button named in a footer: the button in a small chip,
        what it does beside it. Returns the x after it."""
        t, X, Y = self.text, self.X, self.Y
        fk, fl = self.fb(Y(15)), self.f(Y(21))
        w = t.width(fk, key) + X(14)
        r = pygame.Rect(x, y - Y(3), w, t.ink(fl)[1] + Y(6))
        pygame.draw.rect(c, chip, r, border_radius=Y(5))
        t.draw(c, key, fk, self.b["text"], r.centerx, r.y + (r.h - t.ink(fk)[1]) // 2, align="center")
        return r.right + X(8) + t.draw(c, label, fl, ink, r.right + X(8), y) + X(26)

    # On Demand: the DIRECTV on DEMAND page, after the 2008 frames (a 4:3
    # capture, laid out across the 16:9 page): the white logo tile, the
    # categories down the left, the chosen title's header, the titles or the
    # Top Picks posters in the teal panel, the key bar under it.

    def draw_ondemand(self, c, s):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        if s.mode != "auth" and self._is_playlist(s):
            return self._playlist(c, s)
        self._page(c, (0, 0, W, H))
        self._picture(c)
        tile = self.R(32, 35, 312, 150)
        vgrad(c, tile, rgba(b["od_tile"]), rgba(mix(b["od_tile"], b["od_bar"], 0.6)), radius=Y(14))
        fw = self.fb(Y(30))
        w = sum(t.width(fw, ch) for ch in "InDirecTV") + X(3) * 8
        self._spaced(c, "InDirecTV", fw, b["ink"], tile.centerx - w // 2, tile.y + Y(30), X(3))
        tag = pygame.Rect(tile.x + X(40), tile.y + Y(80), tile.w - X(80), Y(40))
        pygame.draw.rect(c, b["od_tag"], tag)
        ft = self.fb(Y(24))
        w = sum(t.width(ft, ch) for ch in "ON>DEMAND") + X(3) * 8
        self._spaced(c, "ON>DEMAND", ft, b["text"], tag.centerx - w // 2, tag.y + (tag.h - t.ink(ft)[1]) // 2, X(3))

        head = self.R(364, 35, 472, 183)
        pygame.draw.rect(c, b["od_panel"], head, border_radius=Y(6))
        main = self.R(356, 218, 880, 408)
        pygame.draw.rect(c, b["od_panel"], main)
        pygame.draw.rect(c, b["od_bar"], main, Y(2))
        bar = self.R(356, 634, 880, 40)
        pygame.draw.rect(c, b["od_bar"], bar, border_radius=Y(6))
        hy = bar.y + (bar.h - t.ink(self.f(Y(21)))[1]) // 2
        x = self._hint(c, bar.x + X(64), hy, self.k("MENU"), "Options", b["text"], b["navy"])
        x = self._hint(c, x, hy, self.k("LIST"), "My Recordings", b["text"], b["navy"])
        if s.status:
            t.draw(c, s.status.title(), self.fb(Y(21)), b["text"], bar.right - X(20), hy, align="right")

        fh, fd = self.fb(Y(28)), self.f(Y(22))
        if s.mode == "auth":
            t.draw(c, "Link your Plex account", fh, b["text"], head.x + X(20), head.y + Y(18))
            for k, line in enumerate(t.wrap(fd, "On Demand comes from your own Plex server. Link it once "
                                               "and it stays linked.", head.w - X(40), 4)):
                t.draw(c, line, fd, b["text"], head.x + X(20), head.y + Y(62) + k * Y(28))
            cy = main.y + Y(60)
            if s.auth_code:
                for line, f, ink in (("On a phone or computer, go to", self.f(Y(26)), b["text"]),
                                     (s.auth_link or "plex.tv/link", self.fb(Y(34)), b["od_sel"]),
                                     ("and enter this code:", self.f(Y(26)), b["text"])):
                    t.draw(c, line, f, ink, main.centerx, cy, align="center")
                    cy += t.ink(f)[1] + Y(22)
                t.draw(c, s.auth_code, self.fb(Y(84)), b["text"], main.centerx, cy + Y(10), align="center")
            return

        # The categories: the level above this one, its choice in amber; at
        # the top level the column is the list itself.
        parent = s.stack[-2] if len(s.stack) > 1 else None
        col_rows, col_sel = (parent["rows"], parent["sel"]) if parent else (s.rows, s.sel)
        fr = self.f(Y(25))
        n_col = 9
        first = max(0, min(col_sel - n_col + 1, len(col_rows) - n_col)) if len(col_rows) > n_col else 0
        for k, i in enumerate(range(first, min(len(col_rows), first + n_col))):
            r = pygame.Rect(X(32), Y(218) + k * Y(42), X(312), Y(40))
            on = i == col_sel
            pygame.draw.rect(c, b["od_sel"] if on else b["od_col"], r)
            self._shadowed(c, t.fit(fr, col_rows[i].get("title", "").title(), r.w - X(36)), fr, b["text"],
                           b["sel_shadow"] if on else None, r.x + X(20), r.y + (r.h - t.ink(fr)[1]) // 2)
            if parent:
                self.hit(r, lambda: s.back())
            else:
                self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))

        cur = s.current() or {}
        title = cur.get("title") or (s.level["title"] if s.level else "On Demand")
        t.draw(c, t.fit(fh, (title or "On Demand").title(), head.w - X(40)), fh, b["text"], head.x + X(20), head.y + Y(18))
        about = cur.get("meta") or s.crumb()
        for k, line in enumerate(t.wrap(fd, about, head.w - X(40), 4)):
            t.draw(c, line, fd, b["text"], head.x + X(20), head.y + Y(62) + k * Y(28))

        if not parent and s.view != "wall":
            # The welcome tile where the posters would be, as the home page had.
            wl = main.inflate(-X(300), -X(120))
            vgrad(c, wl, rgba(b["od_tile"]), rgba(mix(b["od_tile"], b["od_bar"], 0.6)), radius=Y(10))
            w = sum(t.width(fw, ch) for ch in "InDirecTV") + X(3) * 8
            self._spaced(c, "InDirecTV", fw, b["ink"], wl.centerx - w // 2, wl.y + Y(40), X(3))
            tg = pygame.Rect(wl.x + X(40), wl.y + Y(86), wl.w - X(80), Y(40))
            pygame.draw.rect(c, b["od_tag"], tg)
            w = sum(t.width(ft, ch) for ch in "ON>DEMAND") + X(3) * 8
            self._spaced(c, "ON>DEMAND", ft, b["text"], tg.centerx - w // 2, tg.y + (tg.h - t.ink(ft)[1]) // 2, X(3))
            t.draw(c, "WELCOME!", self.fb(Y(24)), b["od_ink"], wl.x + X(40), tg.bottom + Y(26))
            return
        if s.view == "wall":
            self._od_posters(c, s, main)
            return
        n_vis = self.ondemand_page(s)
        rows = s.rows
        top = max(0, min(s.sel - n_vis // 2, len(rows) - n_vis))
        fm = self.fb(Y(23))
        for k, i in enumerate(range(top, min(len(rows), top + n_vis))):
            row = rows[i]
            r = pygame.Rect(main.x + X(4), main.y + Y(8) + k * Y(44), main.w - X(8), Y(42))
            on = i == s.sel
            pygame.draw.rect(c, b["od_sel"] if on else (b["od_row"] if k % 2 == 0 else b["od_row2"]), r)
            sh = b["sel_shadow"] if on else None
            meta = row.get("meta", "")
            mw = t.width(fm, meta) + X(30) if meta else 0
            ty = r.y + (r.h - t.ink(fr)[1]) // 2
            self._shadowed(c, t.fit(fr, row.get("title", ""), r.w - mw - X(40)), fr, b["text"], sh, r.x + X(16), ty)
            if meta:
                self._shadowed(c, meta, fm, b["text"], sh, r.right - X(16), ty, align="right")
            off, dur = row.get("offset", 0), row.get("duration", 0)
            if off and dur:
                pygame.draw.rect(c, b["tk_bar"], (r.x + X(16), r.bottom - Y(5), int((r.w - X(32)) * min(1, off / dur)), Y(3)))
            self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))
        ax, ay = X(374), Y(654)                 # the key bar's arrow slot
        if top + n_vis < len(rows):
            pygame.draw.polygon(c, b["text"], [(ax, ay - Y(6)), (ax + X(16), ay - Y(6)), (ax + X(8), ay + Y(6))])
        if top:
            pygame.draw.polygon(c, b["text"], [(ax + X(22), ay + Y(6)), (ax + X(38), ay + Y(6)),
                                                 (ax + X(30), ay - Y(6))])

    def _od_posters(self, c, s, main):
        """Top Picks: posters in two rows, each titled on a pale strip."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        off = s.wall_offset
        tab = pygame.Rect(main.x + X(10), main.y - Y(30), X(220), Y(32))
        pygame.draw.rect(c, b["od_panel"], tab, border_top_left_radius=Y(6), border_top_right_radius=Y(6))
        ftab = self.fb(Y(22))
        t.draw(c, t.fit(ftab, (s.level["title"] if s.level else "Top Picks").title(), tab.w - X(20)), ftab, b["text"],
               tab.x + X(12), tab.y + (tab.h - t.ink(ftab)[1]) // 2)
        if off:
            sort = pygame.Rect(main.x + X(8), main.y + Y(6), main.w - X(16), Y(30))
            on = s.sel == 0
            pygame.draw.rect(c, b["od_sel"] if on else b["od_row"], sort)
            fs = self.f(Y(21))
            self._shadowed(c, s.rows[0]["title"], fs, b["text"], b["sel_shadow"] if on else None, sort.x + X(12),
                           sort.y + (sort.h - t.ink(fs)[1]) // 2)
            self.hit(sort, lambda: (setattr(s, "sel", 0), s.select()))
        rows = s.rows[off:]
        cols = self.OD_COLS
        tw, th, gap = X(112), Y(168), X(28)
        x0 = main.x + (main.w - (cols * tw + (cols - 1) * gap)) // 2
        y0 = main.y + Y(44 if off else 18)
        cur = max(0, s.sel - off)
        first = max(0, cur // cols - 1) if cur // cols >= 1 else 0
        fcap = self.fb(Y(15))
        for i in range(first * cols, min(len(rows), (first + 2) * cols)):
            row = rows[i]
            r = pygame.Rect(x0 + (i % cols) * (tw + gap), y0 + (i // cols - first) * (th + Y(16)), tw, th)
            on = i + off == s.sel
            pygame.draw.rect(c, b["od_col"], r)
            art = self.app.ondemand.poster(row.get("thumb", ""), tw, th) if row.get("thumb") else None
            if art:
                c.blit(art, art.get_rect(center=r.center))
            cap = pygame.Rect(r.x, r.bottom - Y(30), r.w, Y(30))
            strip = pygame.Surface(cap.size, pygame.SRCALPHA)
            strip.fill((*b["od_tile"], 225))
            c.blit(strip, cap.topleft)
            t.draw(c, t.fit(fcap, row.get("title", "").title(), cap.w - X(10)), fcap, b["od_ink"], cap.x + X(5),
                   cap.y + (cap.h - t.ink(fcap)[1]) // 2)
            pygame.draw.rect(c, b["od_sel"] if on else b["od_bar"], r.inflate(X(8), Y(8)) if on else r, Y(4) if on else 1)
            self.hit(r, lambda i=i + off: (setattr(s, "sel", i), s.select()))

    def _playlist(self, c, s):
        """My Recordings as the HR20's playlist: the group's title over its
        count, the instructions with their green tip, the rows in bold
        italic, orange on the chosen one, the free-space bar at the foot."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._blue(c)
        self._top(c, "My Recordings", "playlist")
        rows = s.rows
        fs = self.fb(Y(26))
        t.draw(c, f"{len(rows)} Recording" + ("" if len(rows) == 1 else "s"), fs, b["strip_ink"], X(300),
               Y(146) + (Y(46) - t.ink(fs)[1]) // 2)
        fi = self.fb(Y(25))
        lead, tip = f"Press {self.k('SELECT')} to open this recording.", f"Tip: Press {self.k('MENU')} to sort it or change the view."
        x, y = X(95), Y(200)
        for word in (lead + " " + tip).split(" "):
            w = t.width(fi, word + " ")
            if x + w > X(835):
                x, y = X(95), y + Y(39)
            t.draw(c, word, fi, b["tip"] if y > Y(200) or word.startswith("Tip") or x > X(95) + t.width(fi, lead)
                   else b["text"], x, y)
            x += w
        t.draw(c, stamp(), self.fb(Y(25)), b["clock"], X(1180), Y(244), align="right")

        head = self.R(95, 310, 1085, 37)
        pygame.draw.rect(c, b["row_head"], head)
        fh = self.fb(Y(26))
        t.draw(c, "Ordered by Date (Newest First)", fh, b["text"], head.x + X(18), head.y + (head.h - t.ink(fh)[1]) // 2)
        n_vis = self.ondemand_page(s)
        top = max(0, min(s.sel - n_vis // 2, len(rows) - n_vis))
        fr = self.fb(Y(27))
        for k, i in enumerate(range(top, min(len(rows), top + n_vis))):
            row = rows[i]
            r = pygame.Rect(head.x, head.bottom + Y(2) + k * Y(48), head.w, Y(46))
            on = i == s.sel
            self._cell(c, r, on)
            pygame.draw.rect(c, b["row_rule"], (r.x, r.y - Y(2), r.w, Y(2)))
            ink = b["text"] if on or row.get("playable") else b["dim"]
            sh = b["sel_shadow"] if on else None
            ty = r.y + (r.h - t.ink(fr)[1]) // 2
            st = row.get("state", "")
            if st and st != "done":             # still coming down: the box's ring
                pygame.draw.circle(c, ink, (r.x + X(30), r.centery), Y(12), Y(3))
            self._ital(c, t.fit(fr, row.get("title", ""), X(520)), fr, ink, r.x + X(62), ty, shadow=sh)
            meta = row.get("meta", "")
            if meta:
                self._ital(c, t.fit(fr, meta, X(440)), fr, ink, r.x + X(605), ty, shadow=sh)
            self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))
        foot = self.R(95, 645, 1085, 38)
        if top + n_vis < len(rows):
            pygame.draw.polygon(c, b["text"], [(X(110), Y(655)), (X(140), Y(655)), (X(125), Y(672))])
        free = 1.0
        try:
            du = shutil.disk_usage(self.app.ondemand.downloads.root)
            free = du.free / du.total
        except (OSError, AttributeError, ZeroDivisionError):
            pass
        fb_ = pygame.Rect(X(175), foot.y + Y(9), X(245), Y(20))
        pygame.draw.rect(c, b["row_head"], fb_)
        pygame.draw.rect(c, b["label"], (fb_.x + Y(2), fb_.y + Y(2), int((fb_.w - Y(4)) * (1 - free)), fb_.h - Y(4)))
        fl = self.f(Y(23))
        ly = foot.y + (foot.h - t.ink(fl)[1]) // 2
        t.draw(c, f"{int(free * 100)}% Free", fl, b["label"], X(432), ly)
        self._hint(c, X(860), ly, self.k("MENU"), "Options", b["text"], b["row_head"])

    # Info: the left column of things to do (orange on the chosen one), the
    # facts and the synopsis in the navy panel.

    def draw_iteminfo(self, c, info):
        from ..screens.iteminfo import hms
        b, t, X, Y = self.b, self.text, self.X, self.Y
        d = info.detail
        self._blue(c)
        self._top(c, d.get("title", ""), "info")
        fs = self.fb(Y(26))
        sy = Y(146) + (Y(46) - t.ink(fs)[1]) // 2
        t.draw(c, stamp(), fs, b["strip_ink"], X(95), sy)
        if d.get("duration"):
            t.draw(c, f"{max(1, d['duration'] // 60)}min", fs, b["strip_ink"], X(301), sy)
        meta = d.get("subtitle") or d.get("meta", "")
        if meta:
            t.draw(c, t.fit(fs, meta, X(250)), fs, b["strip_ink"], X(580), sy)
        pn = self.R(300, 222, 880, 478)
        vgrad(c, pn, rgba(b["pnl"]), rgba(b["pnl_bot"]))
        fb_ = self.f(Y(25))
        for k, name in enumerate(info.buttons()):
            r = pygame.Rect(X(62), Y(224) + k * Y(41), X(235), Y(39))
            on = k == info.focus
            self._amber(c, r) if on else pygame.draw.rect(c, b["btn"], r)
            pygame.draw.rect(c, b["row_rule"], (r.x, r.bottom, r.w, Y(2)))
            f = self.fb(Y(25)) if on else fb_
            self._shadowed(c, t.fit(f, self.button_words(info.label(name)), r.w - X(40)), f, b["text"],
                           b["sel_shadow"] if on else None, r.x + X(34), r.y + (r.h - t.ink(f)[1]) // 2)
            self.hit(r, lambda k=k, name=name: (setattr(info, "focus", k), info.press(name)))
        x, y, w = pn.x + X(40), pn.y + Y(26), pn.w - X(80)
        lh = t.ink(fb_)[1] + Y(20)
        facts = [d.get("meta", "") if d.get("subtitle") else ""]
        if d.get("duration"):
            facts.append(f"Length: {hms(d['duration'])}")
        for line in [f for f in facts if f]:
            t.draw(c, t.fit(fb_, line, w), fb_, b["text"], x, y)
            y += lh
        y += lh // 2
        for line in t.wrap(fb_, d.get("summary", "") or "No information available.", w, 6):
            t.draw(c, line, fb_, b["text"], x, y)
            y += lh
        if d.get("offset", 0) > 5:
            y += lh // 2
            t.draw(c, f"This title resumes at {hms(d['offset'])}.", fb_, b["label"], x, y)

    # The keyboard: the setup page's A-F grid, the text in the dark field,
    # the two choices bottom right.

    def keyboard_rows(self, layer):
        if layer == "sym":
            keys = ["!@#$%^", "&*()_+", "-=[]{}", ";:'\",.", "<>/?\\|", "`~    "]
        else:
            keys = ["ABCDEF", "GHIJKL", "MNOPQR", "STUVWX", "YZ1234", "567890"]
            if layer == "abc":
                keys = [k.lower() for k in keys]
        return keys + [["CLEAR", "SPACE", "DEL"], ["SHIFT", "SYM"], ["DONE"], ["CANCEL"]]

    KEY_WORDS = {"CLEAR": "CLR", "SPACE": "SPC", "DEL": "DEL", "DONE": "Done", "CANCEL": "Cancel"}

    def draw_keyboard(self, c, kb):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._blue(c)
        self._top(c, kb.prompt, "setup")
        fs = self.fb(Y(26))
        t.draw(c, stamp(), fs, b["strip_ink"], X(95), Y(146) + (Y(46) - t.ink(fs)[1]) // 2)
        pn = self.R(300, 222, 880, 498)
        vgrad(c, pn, rgba(b["pnl"]), rgba(b["pnl_bot"]))
        fi = self.f(Y(25))
        hint = kb.hint or f"Press {self.k('SELECT')} on the characters to enter the text. Select Done when finished."
        for k, line in enumerate(t.wrap(fi, hint, pn.w - X(80), 2)):
            t.draw(c, line, fi, b["text"], pn.x + X(40), Y(252) + k * Y(38))
        grid = kb.grid()
        fk = self.fb(Y(27))
        cw, ch = X(55.3), Y(37)
        for r, row in enumerate(grid):
            if row in (["DONE"], ["CANCEL"]):
                rect = self.R(907, 600 + 41 * (r - len(grid) + 2), 273, 41)
            else:
                span = 6 // len(row)
                rect = None
            for col, cell in enumerate(row):
                if rect is None:
                    cell_r = pygame.Rect(X(342) + int(col * span * cw), Y(352) + r * ch, int(span * cw), ch)
                else:
                    cell_r = rect
                on = (r, col) == (kb.row, kb.col)
                self._amber(c, cell_r) if on else pygame.draw.rect(c, b["key"], cell_r)
                pygame.draw.rect(c, b["key_edge"], cell_r, Y(2))
                if cell == "SHIFT":
                    label = "a-z" if kb.layer == "ABC" else "A-Z"
                elif cell == "SYM":
                    label = "ABC" if kb.layer == "sym" else "Symbols"
                else:
                    label = self.KEY_WORDS.get(cell, cell)
                f = fk if len(label) == 1 else self.fb(Y(24))
                sh = b["sel_shadow"] if on else None
                if rect is not None:
                    self._shadowed(c, label, self.f(Y(26)), b["text"], sh, cell_r.x + X(14),
                                   cell_r.y + (ch - t.ink(self.f(Y(26)))[1]) // 2)
                else:
                    self._shadowed(c, label, f, b["text"], sh, cell_r.centerx, cell_r.y + (ch - t.ink(f)[1]) // 2,
                                   align="center")
                self.hit(cell_r, lambda r=r, col=col, cell=cell: (setattr(kb, "row", r), setattr(kb, "col", col),
                                                                  kb._press(cell)))
        field = self.R(692, 352, 448, 42)
        pygame.draw.rect(c, b["field"], field)
        pygame.draw.rect(c, b["key_edge"], field, Y(2))
        ff = self.f(Y(26))
        before = kb.value[:kb.caret]
        shown = before
        while shown and t.width(ff, shown) > field.w - X(40):
            shown = shown[1:]
        ty = field.y + (field.h - t.ink(ff)[1]) // 2
        x = field.x + X(12) + t.draw(c, shown, ff, b["text"], field.x + X(12), ty)
        pygame.draw.rect(c, b["text"], (x + X(2), field.bottom - Y(10), X(14), Y(3)))
        t.draw(c, t.fit(ff, kb.value[kb.caret:], field.right - x - X(24)), ff, b["text"], x + X(18), ty)

    # System Info & Test: the orange rail, the labels in pale blue, the
    # values in white, OK bottom right.

    def draw_diagnostics(self, c, d):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._blue(c)
        self._top(c, "System Info & Test", "setup")
        fs = self.fb(Y(26))
        t.draw(c, stamp(), fs, b["strip_ink"], X(95), Y(146) + (Y(46) - t.ink(fs)[1]) // 2)
        pn = self.R(95, 222, 1085, 498)
        vgrad(c, pn, rgba(b["pnl"]), rgba(b["pnl_bot"]))
        pygame.draw.rect(c, b["orange"], self.R(120, 255, 20, 430))
        pygame.draw.circle(c, b["navy"], (X(130), Y(275)), Y(8))
        f = self.f(Y(25))
        y = Y(264)
        for label, value, bar in [("Signal Strength:", d.signal(), True), ("Signal Quality:", d.quality(), True)] + \
                [(f"{k}:", v, False) for k, v in d.rows()]:
            t.draw(c, label, f, b["label"], X(153), y)
            t.draw(c, t.fit(f, str(value), X(560)), f, b["text"], X(536), y)
            if bar:
                track = pygame.Rect(X(610), y + Y(2), X(320), Y(16))
                pygame.draw.rect(c, b["row_head"], track)
                pygame.draw.rect(c, b["label"], (track.x, track.y, track.w * value // 100, track.h))
            y += Y(39)
        ok = self.R(1001, 625, 179, 41)
        pygame.draw.rect(c, b["key_edge"], ok, Y(2))
        fo = self.fb(Y(26))
        t.draw(c, "OK", fo, b["text"], ok.x + X(18), ok.y + (ok.h - t.ink(fo)[1]) // 2)
        self.hit(ok, lambda: d.handle("BACK"))

    # Playback: the bar along the foot, as the box drew it for a recording
    # or an On Demand title: the logo tile, the light-blue band with the
    # time gone, the title and the length, the orange line with the time
    # tab under it, the play / pause tile at the end.

    def draw_playback(self, c, pb):
        from ..screens.iteminfo import hms
        b, t, X, Y = self.b, self.text, self.X, self.Y
        paused = self.app.video.paused
        if pb.skip_label:
            sk = self.R(880, 476 if pb.bar_visible() else 600, 320, 50)
            pygame.draw.rect(c, b["pop_body"], sk)
            pygame.draw.rect(c, b["orange"], sk, Y(3))
            f = self.fb(Y(22))
            t.draw(c, f"{pb.skip_label.title()}: {self.k('SELECT')}", f, b["text"], sk.centerx, sk.y + (sk.h - t.ink(f)[1]) // 2,
                   align="center")
            self.hit(sk, lambda: pb.handle("SELECT"))
        if not pb.bar_visible():
            return
        tile = self.R(80, 546, 292, 84)
        vgrad(c, tile, rgba(b["tk_tile"]), rgba(mix(b["tk_tile"], b["od_bar"], 0.7)))
        self.tile(c, (tile.centerx - X(26), tile.y + Y(9), X(52), Y(42)), b["sky"])
        fw = self.fb(Y(15))
        w = sum(t.width(fw, ch) for ch in "InDirecTV") + X(2) * 8
        self._spaced(c, "InDirecTV", fw, b["ink"], tile.centerx - w // 2, tile.y + Y(58), X(2))
        band = self.R(372, 546, 736, 84)
        pygame.draw.rect(c, b["tk_band"], band)
        f = self.fb(Y(22))
        q = self.app.ondemand.queue
        title = pb.title + (f"  ({q.pos + 1} of {len(q.items)})" if q.items and q.pos >= 0 else "")
        t.draw(c, hms(pb.pos), f, b["text"], band.x + X(20), band.y + Y(10))
        t.draw(c, hms(pb.dur) if pb.dur else "--:--", f, b["text"], band.right - X(20), band.y + Y(10), align="right")
        t.draw(c, t.fit(f, title, band.w - X(220)), f, b["text"], band.centerx, band.y + Y(10), align="center")
        line = pygame.Rect(band.x + X(20), band.y + Y(40), band.w - X(40), Y(10))
        pygame.draw.rect(c, b["tk_state"], line)
        frac = min(1.0, pb.pos / pb.dur) if pb.dur else 0.0
        pygame.draw.rect(c, b["tk_bar"], (line.x, line.y, int(line.w * frac), line.h))
        self.hit(line.inflate(0, Y(24)), lambda: pb.seek_to(self._click_frac(line)))
        tab = pygame.Rect(0, line.bottom + Y(6), X(84), Y(26))
        tab.centerx = max(line.x + tab.w // 2, min(line.right - tab.w // 2, line.x + int(line.w * frac)))
        pygame.draw.rect(c, b["tk_tile"], tab, border_radius=Y(10))
        ft = self.fb(Y(19))
        t.draw(c, hms(pb.pos), ft, b["ink"], tab.centerx, tab.y + (tab.h - t.ink(ft)[1]) // 2, align="center")
        st = self.R(1108, 546, 92, 84)
        pygame.draw.rect(c, b["tk_state"], st)
        cx, cy = st.center
        if paused:
            for dx in (-X(12), X(4)):
                pygame.draw.rect(c, b["text"], (cx + dx, cy - Y(16), X(9), Y(32)))
        else:
            pygame.draw.polygon(c, b["text"], [(cx - X(10), cy - Y(17)), (cx - X(10), cy + Y(17)), (cx + X(14), cy)])
        self.hit(st, pb.toggle_pause)
        # The transport buttons under the band: navy tiles like the state one.
        fb = self.fb(Y(17))
        for k, (kind, _, fn) in enumerate(pb.transport()):
            r = self.R(372 + k * 124, 636, 116, 38)
            pygame.draw.rect(c, b["tk_state"], r)
            self.transport_face(c, kind, r, b["text"], fb)
            self.hit(r, fn)

    # The pop-ups: the grey title, the blue body, the logo in the grey foot.

    def _popup(self, c, r, title, lines):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        pygame.draw.rect(c, b["pop_head"], r, border_radius=Y(12))
        body = pygame.Rect(r.x, r.y + Y(42), r.w, r.h - Y(42) - Y(72))
        pygame.draw.rect(c, b["pop_body"], body)
        fh = self.fb(Y(26))
        t.draw(c, title, fh, b["ink"], r.centerx, r.y + (Y(42) - t.ink(fh)[1]) // 2, align="center")
        f = self.fb(Y(24))
        y = body.y + Y(20)
        for line, ink in lines:
            for part in t.wrap(f, line, body.w - X(48), 3):
                t.draw(c, part, f, ink, body.x + X(24), y)
                y += Y(36)
        self.tile(c, (r.centerx - X(24), body.bottom + Y(12), X(48), Y(40)), b["sky"])

    def draw_capture(self, c, cap):
        self._popup(c, self.R(390, 200, 500, 330), "REMOTE SETUP",
                    [(cap.prompt, self.b["text"]), ("Waiting...", self.b["label"])])

    def draw_toast(self, c, msg):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        f = self.fb(Y(24))
        lines = t.wrap(f, msg, X(1040), 3)
        lh = Y(34)
        r = pygame.Rect(X(96), Y(62), max(t.width(f, ln) for ln in lines) + X(48), Y(16) + lh * len(lines))
        pygame.draw.rect(c, b["pop_body"], r)
        pygame.draw.rect(c, b["sky"], (r.x, r.y, r.w, Y(3)))
        pygame.draw.rect(c, b["sky"], (r.x, r.bottom - Y(3), r.w, Y(3)))
        for k, ln in enumerate(lines):
            t.draw(c, ln, f, b["text"], r.x + X(24), r.y + Y(12) + k * lh)

    def draw_screensaver(self, c, ss):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        c.fill((0, 0, 0, 255))
        f = self.fb(Y(30))
        w = sum(t.width(f, ch) for ch in "InDirecTV") + X(3) * 8
        bw, bh = max(w, X(120)), Y(100) + Y(12) + t.ink(f)[1]
        x, y = ss.position(bw, bh, W, H)
        self.tile(c, (x + bw // 2 - X(60), y, X(120), Y(100)), b["sky"])
        self._spaced(c, "InDirecTV", f, b["text"], x + (bw - w) // 2, y + Y(112), X(3))

    def _message(self, c, msg):
        """A message on black, in the navy band of the box's own notices."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        c.fill((0, 0, 0, 255))
        f = self.fb(Y(28))
        lines = t.wrap(f, msg, X(1088), 4)
        band = self.R(0, 0, 1280, 0)
        band.h = Y(40) + len(lines) * Y(42)
        band.centery = self.canvas[1] // 2
        pygame.draw.rect(c, b["navy"], band)
        pygame.draw.rect(c, b["sky"], (band.x, band.y, band.w, Y(3)))
        pygame.draw.rect(c, b["sky"], (band.x, band.bottom - Y(3), band.w, Y(3)))
        y = band.y + Y(22)
        for line in lines:
            t.draw(c, line, f, b["text"], X(96), y)
            y += Y(42)

    # ── Boot ──────────────────────────────────────────────────────────────

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        stage = boot.stage()
        vgrad(c, (0, 0, W, H), rgba(b["deep"]), rgba(b["cell"]))
        cx, cy = W // 2, Y(250)
        glow = pygame.Surface((W, H), pygame.SRCALPHA)       # the lit-up mark of a box starting
        for k in range(6, 0, -1):
            pygame.draw.circle(glow, (*b["sky"], 14), (cx, cy), Y(55) * k)
        c.blit(glow, (0, 0))
        self.tile(c, (cx - X(60), cy - Y(100), X(120), Y(100)), b["sky"])
        f = self.fb(Y(34))
        w = sum(t.width(f, ch) for ch in "InDirecTV") + X(4) * 8
        self._spaced(c, "InDirecTV", f, b["text"], cx - w // 2, cy + Y(16), X(4))
        if stage == "starting":
            return
        caption = {"signal": "Step 1 of 2: Acquiring satellite signal...",
                   "guide": "Step 2 of 2: Downloading guide data..." + self.guide_pct(), "done": "Ready"}[stage]
        t.draw(c, caption, self.f(Y(24)), b["text"], cx, Y(440), align="center")
        bar = self.R(360, 492, 560, 12)
        age = time.monotonic() - boot.start
        g = getattr(self.app, "guide_progress", None)
        guide = 0.45 + 0.55 * g if g is not None and g >= 0 else 0.45 + 0.45 * min(1, age / 8)
        frac = {"signal": 0.15 + 0.25 * min(1, age / 4), "guide": guide, "done": 1.0}[stage]
        self.progress(c, bar, frac, rgba(b["gap"]), rgba(b["sel"]))
        t.draw(c, "Press any button to skip", self.f(Y(18)), b["soft"], cx, Y(660), align="center")


class InDirect(InDirectHD):
    """The SD era, after a 1997 DSS receiver: a purple ground with a lavender
    page, teal bands, grey (light) selection; the channel banner across the
    top with a two-line schedule; a numbered Main Menu with the chosen item
    explained in a teal box. 640x480, geometry from the box's own frame."""
    name = "indirect"
    label = "InDirecTV"
    canvas = (640, 480)
    guide_hours = 2                 # four half-hour columns, as the DSS showed
    guide_rows = 6
    default_font = "sans"           # Liberation Sans Bold, condensed (SQUEEZE) as the DSS lettered
    SD = True
    # Measured from the frames: the purple band, the lavender page, the teal
    # bar, the light selection; the amber was the box's own highlight colour.
    NATIVE = {"bg": [56, 51, 86], "accent": [112, 106, 142], "accent2": [168, 168, 170],
              "text": [255, 255, 255], "chnum": [100, 136, 138]}

    def roles(self, b):
        purple, page, sel, text, teal = b["bg"], b["accent"], b["accent2"], b["text"], b["chnum"]
        return {
            "purple": purple, "page": page, "page_hi": mix(page, (255, 255, 255), 0.08),
            "teal": teal, "teal_dark": mix(teal, (0, 0, 0), 0.25),
            "sel": sel, "sel_ink": mix(purple, (0, 0, 0), 0.5), "shadow": mix(purple, (0, 0, 0), 0.6),
            "text": text, "soft": mix(text, page, 0.35), "rule": mix(page, (255, 255, 255), 0.3),
            "tile": mix(text, page, 0.4), "box": mix(purple, (0, 0, 0), 0.35),
            # The shared pieces (volume, mini guide...) read these.
            "navy": purple, "cell": page, "cell_hi": mix(page, (255, 255, 255), 0.06),
            "gap": mix(page, (0, 0, 0), 0.3), "sky": teal, "deep": mix(purple, (0, 0, 0), 0.4),
            "sel_shadow": None, "mark": text, "ink": text,
        }

    # The DSS frame's own 320x240 (the capture's size), scaled to the canvas.
    def X(self, v) -> int:
        return int(round(v * self.canvas[0] / 320))

    def Y(self, v) -> int:
        return int(round(v * self.canvas[1] / 240))

    SQUEEZE = 0.82                  # the DSS's condensed face, from Liberation Sans Bold

    def _shadowed(self, c, s, f, ink, shadow, x, y, align="left"):
        """The DSS lettered everything condensed, with a dark drop shadow."""
        if not s:
            return 0
        img, extra = self.text.render(f, s, ink[:3])
        w = max(1, int(img.get_width() * self.SQUEEZE))
        img = pygame.transform.smoothscale(img, (w, img.get_height()))
        x0 = x - w if align == "right" else x - w // 2 if align == "center" else x
        y0 = y - self.text.ink(f)[0] - extra
        if shadow:
            sh = pygame.transform.smoothscale(self.text.render(f, s, shadow[:3])[0], (w, img.get_height()))
            c.blit(sh, (x0 + 2, y0 + 2))
        c.blit(img, (x0, y0))
        return w

    def mark(self, c, x, y, size):
        """The squat tile alone, as the box's banner showed only its logo."""
        self.tile(c, (x, y, size, int(size * 0.64)), self.b["teal"])

    # ── Live: banner, digits, volume, trick ───────────────────────────────

    def _banner(self, c, ch, cur, nxt, full=False, tag=None):
        """The DSS banner, to the frame: a purple band y 0-56, the logo and
        the channel number in a grey tile at the left, the title at x 57,
        then Start / End lines with the rating and list, the clock and date
        right-aligned."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(0, 0, 320, 59)
        vgrad(c, r, rgba(b["purple"], 230), rgba(b["purple"], 240))
        if tag:
            self.chip(c, X(12), r.bottom + Y(4), tag, self.fb(Y(9)), rgba(b["sel"]), b["sel_ink"])
        self.mark(c, X(24), Y(19), X(22))
        num = pygame.Rect(X(22), Y(41), X(28), Y(13))
        pygame.draw.rect(c, b["tile"], num, border_radius=2)
        fn = self.fb(Y(10))
        t.draw(c, str(ch.number), fn, b["sel_ink"], num.centerx, num.y + (num.h - t.ink(fn)[1]) // 2, align="center")
        f_title = self.fb(Y(16))
        self._shadowed(c, t.fit(f_title, cur.title if cur else ch.name, X(240)), f_title, b["text"], b["shadow"],
                       X(57), Y(19))
        fs = self.fb(Y(11))
        local = datetime.now()
        cat = g_cat(self)
        rows = [("Start", ampm(cur.start) + "m" if cur else "", (cur.rating or "NR") if cur else "",
                 ampm(local) + "m"),
                ("End", ampm(cur.stop) + "m" if cur else "", "Normal List" if cat == "All" else cat,
                 f"{local:%a} {local.month}/{local.day}/{local:%y}")]
        for k, (lab, when_, mid, right) in enumerate(rows):
            y = Y(32 + 13 * k)
            self._shadowed(c, lab, fs, b["text"], b["shadow"], X(57), y)
            self._shadowed(c, when_, fs, b["text"], b["shadow"], X(82), y)
            self._shadowed(c, mid, fs, b["text"], b["shadow"], X(128), y)
            self._shadowed(c, right, fs, b["text"], b["shadow"], X(268) if k == 0 else X(288), y, align="right")
        if full and cur and cur.description:
            f = self.f(Y(12))
            lines = t.wrap(f, cur.description, X(296), 3)
            d = pygame.Rect(0, r.bottom, W, Y(8) + len(lines) * Y(15))
            vgrad(c, d, rgba(b["purple"], 230), rgba(b["deep"], 240))
            y = d.y + Y(4)
            for line in lines:
                self._shadowed(c, line, f, b["text"], b["shadow"], X(12), y)
                y += Y(15)
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def _digits(self, c, digits):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(0, 0, 320, 36)
        vgrad(c, r, rgba(b["purple"], 230), rgba(b["purple"], 240))
        self.mark(c, X(24), Y(8), X(22))
        self._shadowed(c, digits + "-" * (3 - len(digits)), self.fb(Y(18)), b["text"], b["shadow"], X(57), Y(8))

    def _notice(self, c, lines, y_bottom=None, min_w=0, centre=False):
        """The DSS's purple notice box with its light bevel, bottom left (the
        'This showing is no longer available' card), or centred; returns its
        rect."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        f = self.fb(Y(12))
        w = max(max(t.width(f, s) for s in lines) + X(24), min_w)
        r = pygame.Rect(X(52), 0, min(w, X(262)), Y(8) + len(lines) * Y(13))
        r.bottom = y_bottom if y_bottom is not None else Y(227)
        if centre:
            r.centerx = self.canvas[0] // 2
        pygame.draw.rect(c, b["purple"], r)
        pygame.draw.rect(c, b["rule"], r, 2)
        y = r.y + Y(4)
        for s in lines:
            self._shadowed(c, s, f, b["text"], b["shadow"], r.x + X(12), y)
            y += Y(13)
        return r

    def _volume(self, c, cx, cy):
        b, X, Y = self.b, self.X, self.Y
        v = self.app.video
        r = self._notice(c, ["Mute" if v.muted else f"Volume  {v.volume}"], min_w=X(190))
        bar = pygame.Rect(r.x + X(100), r.y + Y(8), X(80), Y(7))
        pygame.draw.rect(c, b["gap"], bar)
        if not v.muted:
            pygame.draw.rect(c, b["teal"], (bar.x, bar.y, int(bar.w * v.volume / 100), bar.h))

    def _trick(self, c, s):
        b, X, Y = self.b, self.X, self.Y
        behind = s["behind"]
        mm, ss = divmod(int(behind), 60)
        tag = "Paused" if s["paused"] else ("Live" if behind < 2 else "Playing")
        when_ = f"-{mm}:{ss:02d}" if behind >= 1 else "Live"
        r = self._notice(c, [f"{tag}        {when_}"], min_w=X(190))
        bar = pygame.Rect(r.x + X(12), r.bottom - Y(6), r.w - X(24), Y(3))
        pygame.draw.rect(c, b["gap"], bar)
        span = s["buffer"] + behind
        if span >= 2:
            x = bar.x + int(bar.w * s["buffer"] / span)
            pygame.draw.rect(c, b["teal"], (bar.x, bar.y, x - bar.x, bar.h))
            pygame.draw.rect(c, b["text"], (x - 1, bar.y - 2, 3, bar.h + 4))

    def _note(self, c, text, frac=None):
        b, X, Y = self.b, self.X, self.Y
        bar = frac is not None and frac >= 0
        r = self._notice(c, [text] + ([""] if bar else []), y_bottom=Y(192), min_w=X(190))   # above the subtitles
        if bar:
            track = pygame.Rect(r.x + X(12), r.bottom - Y(9), r.w - X(24), Y(4))
            pygame.draw.rect(c, b["gap"], track)
            pygame.draw.rect(c, b["teal"], (track.x, track.y, int(track.w * frac), track.h))

    def _signal_loss(self, c):
        """The DSS's card on black, as the box showed a showing it couldn't
        play (the frame at 0:09)."""
        c.fill((0, 0, 0, 255))
        self._notice(c, ["This showing is no longer available.", "Check Program Guide for other showtimes."])

    # ── Guide: the DSS Program Guide ──────────────────────────────────────

    def guide_video_box(self):
        return "hidden"                  # the DSS guide was a full page

    def draw_guide(self, c, g):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        pygame.draw.rect(c, b["purple"], (0, 0, W, Y(42)))
        pygame.draw.rect(c, b["page"], (0, Y(42), W, H - Y(42)))
        f_head, f_small, f_cell = self.f(Y(16)), self.f(Y(11)), self.fb(Y(12))
        self._shadowed(c, "Norm", f_small, b["soft"], b["shadow"], X(24), Y(14))
        self._shadowed(c, "Program Guide", f_head, b["soft"], b["shadow"], X(55), Y(14))
        local = datetime.now()
        self._shadowed(c, f"{local:%a} {local.month}/{local.day}/{local:%y}", f_small, b["text"], b["shadow"],
                       X(248), Y(14), align="right")
        self._shadowed(c, ampm(local).upper() + "M", f_small, b["text"], b["shadow"], X(290), Y(14), align="right")
        # The second line: page, and the half hours.
        start, end = g.window()
        rows_all = g.filtered()
        page, pages = g.top // g.rows + 1, max(1, (len(rows_all) + g.rows - 1) // g.rows)
        self._shadowed(c, f"{page}/{pages}", f_small, b["soft"], b["shadow"], X(24), Y(34))
        slots = int(g.hours * 2)
        col_w = 240 / slots
        for i in range(slots):
            self._shadowed(c, ampm(start + timedelta(minutes=30 * i)).upper() + "M", f_small, b["text"],
                           b["shadow"], X(55 + col_w * i), Y(30))
        # The rows: a channel tile, then bevelled page-coloured cells.
        rows = rows_all[g.top: g.top + g.rows]
        now = datetime.now(timezone.utc)
        epg = self.app.epg
        mins = g.hours * 60
        grid_x, grid_w = X(55), X(242)
        for i, ch in enumerate(rows):
            y = Y(42) + i * Y(28)
            rh = Y(26)
            row_sel = g.focus == "grid" and g.top + i == g.cursor
            tile = pygame.Rect(X(24), y, X(27), rh)
            self._bevel(c, tile, b["page"])
            name = ch.name.upper()
            while len(name) > 1 and t.width(f_cell, name) * self.SQUEEZE > X(26):   # call signs clip, no ellipsis
                name = name[:-1]
            self._shadowed(c, name, f_cell, b["text"], b["shadow"], tile.x + X(2), y + Y(2))
            self._shadowed(c, str(ch.number), f_cell, b["text"], b["shadow"], tile.x + X(2), y + Y(15))
            cid = epg.resolve_channel_id(ch.epg_id, ch.name) if epg else None
            progs = epg.programs_in_window(cid, start, end) if cid else []
            if not progs:
                cell = pygame.Rect(grid_x, y, grid_w, rh)
                self._dss_cell(c, cell, row_sel)
                self._shadowed(c, "No Information", f_cell, b["sel_ink"] if row_sel else b["text"],
                               None if row_sel else b["shadow"], cell.x + X(4), y + Y(2))
            for p in progs:
                a = max(0.0, (p.start - start).total_seconds() / 60)
                e = min(float(mins), (p.stop - start).total_seconds() / 60)
                if e <= a:
                    continue
                cell = pygame.Rect(grid_x + int(a / mins * grid_w), y, int((e - a) / mins * grid_w) - X(2), rh)
                on = row_sel and p.start <= max(now, start) < p.stop
                self._dss_cell(c, cell, on)
                ink, shadow = (b["sel_ink"], None) if on else (b["text"], b["shadow"])
                room = int((cell.w - X(8)) / self.SQUEEZE)
                lines = [t.fit(f_cell, line, room) for line in t.wrap(f_cell, p.title, room, 2)]
                for k, line in enumerate(lines):
                    self._shadowed(c, line, f_cell, ink, shadow, cell.x + X(4), y + Y(2) + k * Y(12))
            self.hit((X(24), y, X(273), rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                         setattr(g, "focus", "grid"), g.handle("SELECT")))
        if not rows:
            cell = pygame.Rect(X(24), Y(42), X(273), Y(26))
            self._bevel(c, cell, b["page"])
            for k, line in enumerate(t.wrap(f_cell, self.empty_guide(g), int((cell.w - X(8)) / self.SQUEEZE), 2)):
                self._shadowed(c, line, f_cell, b["text"], b["shadow"], cell.x + X(4), cell.y + Y(2) + k * Y(12))
        # The teal buttons along the bottom: page, the lists, Exit.
        y = Y(211)
        labels = [("v", "PAGE_DOWN"), (g.category if g.category != "All" else "Movies", "THEMES"),
                  ("Sports", "THEMES"), ("Other", "THEMES"), ("All", "THEMES"), ("Exit", "EXIT")]
        bx = X(24)
        bw = X(45)
        for k, (lab, action) in enumerate(labels):
            r = pygame.Rect(bx + k * (bw + X(1)), y, bw, Y(13))
            on = k == 1 and g.focus == "category"
            pygame.draw.rect(c, b["sel"] if on else b["teal"], r)
            pygame.draw.rect(c, b["teal_dark"], (r.x, r.bottom - 1, r.w, 1))
            if lab == "v":
                pygame.draw.polygon(c, b["purple"], [(r.centerx - X(5), r.y + Y(3)), (r.centerx + X(5), r.y + Y(3)),
                                                      (r.centerx, r.bottom - Y(3))])
            else:
                self._shadowed(c, t.fit(f_small, lab, bw - X(6)), f_small, b["sel_ink"] if on else b["text"],
                               None if on else b["shadow"], r.centerx, r.y + Y(1), align="center")
            self.hit(r, lambda a=action: g.handle(a))

    def _dss_cell(self, c, cell, on):
        """A guide cell; the chosen one is light and casts a shadow."""
        b = self.b
        self._bevel(c, cell, b["sel"] if on else b["page"])
        if on:
            pygame.draw.rect(c, b["shadow"], (cell.x + 3, cell.bottom, cell.w, 3))
            pygame.draw.rect(c, b["shadow"], (cell.right, cell.y + 3, 3, cell.h))

    def _bevel(self, c, r, fill):
        """A cell with the DSS's light top-left / dark bottom-right edges."""
        b = self.b
        pygame.draw.rect(c, fill, r)
        hi, lo = mix(fill, (255, 255, 255), 0.42), mix(fill, (0, 0, 0), 0.42)
        pygame.draw.rect(c, hi, (r.x, r.y, r.w, 2))
        pygame.draw.rect(c, hi, (r.x, r.y, 2, r.h))
        pygame.draw.rect(c, lo, (r.x, r.bottom - 2, r.w, 2))
        pygame.draw.rect(c, lo, (r.right - 2, r.y, 2, r.h))

    # ── Menu: the DSS Main Menu ───────────────────────────────────────────

    def menu_video_box(self, menu):
        return "hidden"

    def _dss_page(self, c, title, lines):
        """The DSS page: the title and two lines of instructions on the purple
        band, the teal rule, the lavender page."""
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        pygame.draw.rect(c, b["purple"], (0, 0, W, Y(57)))
        pygame.draw.rect(c, b["teal"], (0, Y(57), W, Y(12)))
        pygame.draw.rect(c, b["page"], (0, Y(69), W, H - Y(69)))
        f_small = self.fb(Y(11))
        self._shadowed(c, self.text.fit(self.f(Y(16)), title, X(250)), self.f(Y(16)), b["soft"], b["shadow"], X(55), Y(16))
        for k, line in enumerate(lines[:2]):
            self._shadowed(c, self.text.fit(f_small, line, int(X(258) / self.SQUEEZE)), f_small, b["text"], b["shadow"],
                           X(55), Y(34 + 12 * k))

    def draw_menu(self, c, m):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        f_row = self.fb(Y(12))
        self._dss_page(c, "DSS Main Menu" if m.title == "MAIN MENU" else m.title.title(),
                       [f"Use arrows to point to an item, then press {self.k('SELECT')}.",
                        "Pressing the number also selects the item."])
        n = len(m.items)
        rh = Y(14)
        n_vis = max(1, (Y(190) - Y(74)) // rh)
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        for k, i in enumerate(range(first, min(n, first + n_vis))):
            it = m.items[i]
            y = Y(71) + k * rh
            sel = i == m.cursor
            row = pygame.Rect(X(52), y - Y(2), X(218), rh)
            if sel:
                self._bevel(c, row, b["sel"])
                pygame.draw.rect(c, b["shadow"], (row.x + 3, row.bottom, row.w, 3))
                pygame.draw.rect(c, b["shadow"], (row.right, row.y + 3, 3, row.h))
            num = str((i + 1) % 10) if i < 10 else " "
            label = f"{num} {it.label}"
            if it.value:
                label += f"   {it.value()}"
            ink = (b["sel_ink"] if sel else b["text"]) if it.enabled else b["soft"]
            self._shadowed(c, t.fit(f_row, label, row.w - X(8)), f_row, ink, None if sel else b["shadow"],
                           row.x + X(3), y)
            self.hit(row, lambda i=i: m.activate(i))
        it = m.items[m.cursor] if 0 <= m.cursor < n else None
        if it:
            box = self.R(51, 196, 224, 28)
            pygame.draw.rect(c, b["teal"], box)
            pygame.draw.rect(c, b["shadow"], (box.x, box.bottom, box.w, 2))
            pygame.draw.rect(c, b["shadow"], (box.right, box.y, 2, box.h))
            self._shadowed(c, str((m.cursor + 1) % 10), self.fb(Y(14)), b["text"], b["shadow"], box.x + X(6), box.y + Y(5))
            if it.preview:
                hint = f"{self.k('SELECT')} chooses this."
            elif it.value and (it.adjust or not it.action):
                hint = "LEFT / RIGHT change this setting." if it.adjust else f"{self.k('SELECT')} changes this setting."
            elif it.submenu:
                hint = f"{self.k('SELECT')} opens this menu."
            else:
                hint = {"Program Guide": "Show the on-screen programming schedule."}.get(it.label, f"{self.k('SELECT')} chooses this.")
            room, fh = int((box.w - X(26)) / self.SQUEEZE), f_row
            for size in (12, 11, 10):
                fh = self.fb(Y(size))
                if t.width(fh, hint) <= room:
                    break
            self._shadowed(c, t.fit(fh, hint, room), fh, b["text"], b["shadow"],
                           box.x + X(20), box.y + Y(6) + (t.ink(f_row)[1] - t.ink(fh)[1]) // 2)

    # ── Mini guide: the DSS had none; a purple band of rows ───────────────

    def draw_miniguide(self, c, mg):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        rows = mg.rows()
        rh = Y(13)
        r = pygame.Rect(0, 0, W, Y(14) + rh * len(rows) + Y(4))
        r.bottom = H
        vgrad(c, r, rgba(b["purple"], 230), rgba(b["purple"], 240))
        f = self.fb(Y(11))
        self._shadowed(c, "Mini Guide", self.fb(Y(12)), b["text"], b["shadow"], X(12), r.y + Y(2))
        y = r.y + Y(14)
        for ch, cur, nxt, sel in rows:
            row = pygame.Rect(X(12), y, X(296), rh - Y(2))
            if sel:
                pygame.draw.rect(c, b["sel"], row)
            ink, shadow = (b["sel_ink"], None) if sel else (b["text"], b["shadow"])
            ty = row.y + (row.h - t.ink(f)[1]) // 2
            self._shadowed(c, t.fit(f, f"{ch.number} {ch.name.upper()}", X(70)), f, ink, shadow, row.x + X(2), ty)
            self._shadowed(c, t.fit(f, cur.title if cur else "No Information", X(108)), f, ink, shadow, row.x + X(76), ty)
            if nxt:
                self._shadowed(c, t.fit(f, f"{ampm(nxt.start)}m  {nxt.title}", X(104)), f, ink if sel else b["soft"],
                               shadow, row.x + X(190), ty)
            self.hit(row, lambda ch=ch: mg.pick(ch))
            y += rh

    # ── Pages: the DSS's own vocabulary for what it never had ─────────────
    # A 1997 box had no On Demand, no keyboard and no diagnostics page; they
    # are drawn as its Program Information and Purchase Offer pages were:
    # the purple band with two lines of instructions, the teal rule, plain
    # shadowed lines on the lavender page, the square buttons at the right.

    poster_wall = False             # nothing but lists on a DSS
    keyboard_layer = "ABC"

    def page_video_box(self, screen):
        return None                 # full pages, as the DSS drew them

    def ondemand_cols(self, screen):
        return 1

    def ondemand_page(self, screen):
        return 8

    def _dss_button(self, c, r, label, icon, on):
        """A square button with its small icon, light when chosen, its drop
        shadow down and to the right."""
        b, X, Y = self.b, self.X, self.Y
        pygame.draw.rect(c, b["shadow"], r.move(2, 2))
        pygame.draw.rect(c, b["sel"] if on else b["teal"], r)
        ink = b["sel_ink"] if on else b["text"]
        ix, iy = r.x + X(6), r.centery
        if icon == "play":
            pygame.draw.polygon(c, ink, [(ix - X(3), iy), (ix, iy - Y(3)), (ix + X(3), iy), (ix, iy + Y(3))])
        elif icon == "exit":
            pygame.draw.polygon(c, ink, [(ix - X(3), iy + Y(3)), (ix + X(3), iy - Y(3)), (ix + X(3), iy + Y(1)),
                                         (ix + X(1), iy - Y(3))])
        else:
            pygame.draw.rect(c, ink, (ix - X(3), iy - Y(3), X(6), Y(7)), 1)
            pygame.draw.line(c, ink, (ix - X(1), iy - Y(1)), (ix + X(1), iy - Y(1)))
            pygame.draw.line(c, ink, (ix - X(1), iy + Y(1)), (ix + X(1), iy + Y(1)))
        f = self.fb(Y(11))
        self._shadowed(c, self.text.fit(f, label, int((r.w - X(14)) / self.SQUEEZE)), f, ink,
                       None if on else b["shadow"], r.x + X(12), r.y + (r.h - self.text.ink(f)[1]) // 2)

    def _dss_lines(self, c, lines, x, y, width, pitch=None):
        """Plain shadowed lines down the page; returns the y after them."""
        b, Y = self.b, self.Y
        pitch = pitch or Y(14)
        for text, bold in lines:
            f = self.fb(Y(12)) if bold else self.f(Y(12))
            self._shadowed(c, self.text.fit(f, text, int(width / self.SQUEEZE)), f, b["text"], b["shadow"], x, y)
            y += pitch
        return y

    def draw_ondemand(self, c, s):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        if s.mode == "auth":
            self._dss_page(c, "Link Your Plex Account", ["On Demand comes from your own Plex server.",
                                                         f"Press {self.k('BACK')} to return to the program."])
            if s.auth_code:
                self._dss_lines(c, [("On a phone or computer, go to", False), (s.auth_link or "plex.tv/link", True),
                                    ("and enter this code:", False)], X(57), Y(80), X(230))
                self._shadowed(c, s.auth_code, self.fb(Y(30)), b["text"], b["shadow"], X(57), Y(128))
            elif s.status:
                self._dss_lines(c, [(s.status.title(), True)], X(57), Y(80), X(230))
            return
        title = (s.level["title"] if s.level else "On Demand").title()
        self._dss_page(c, title, [f"Use arrows to point to an item, then press {self.k('SELECT')}.",
                                  f"Press {self.k('MENU')} for options, {self.k('BACK')} to go back."])
        rows, n_vis = s.rows, self.ondemand_page(s)
        top = max(0, min(s.sel - n_vis + 1, len(rows) - n_vis)) if len(rows) > n_vis else 0
        f_row = self.fb(Y(12))
        for k, i in enumerate(range(top, min(len(rows), top + n_vis))):
            row = rows[i]
            y = Y(71) + k * Y(14)
            on = i == s.sel
            r = pygame.Rect(X(52), y - Y(2), X(220), Y(14))
            if on:
                pygame.draw.rect(c, b["sel"], r)
                pygame.draw.rect(c, b["shadow"], (r.x, r.bottom, r.w, 1))
                pygame.draw.rect(c, b["shadow"], (r.right, r.y, 1, r.h))
            ink, shadow = (b["sel_ink"], None) if on else (b["text"], b["shadow"])
            meta = row.get("meta", "")
            mw = int(t.width(f_row, meta) * self.SQUEEZE) + X(8) if meta else 0
            self._shadowed(c, t.fit(f_row, row.get("title", ""), int((r.w - X(8) - mw) / self.SQUEEZE)), f_row, ink, shadow,
                           r.x + X(3), y)
            if meta:
                self._shadowed(c, meta, f_row, ink, shadow, r.right - X(3), y, align="right")
            self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))
        pages = max(1, (len(rows) + n_vis - 1) // n_vis)
        fs = self.fb(Y(11))
        self._shadowed(c, f"{top // n_vis + 1}/{pages}", fs, b["soft"], b["shadow"], X(24), Y(73))
        box = self.R(51, 196, 224, 28)
        pygame.draw.rect(c, b["teal"], box)
        pygame.draw.rect(c, b["shadow"], (box.x, box.bottom, box.w, 2))
        pygame.draw.rect(c, b["shadow"], (box.right, box.y, 2, box.h))
        cur = s.current() or {}
        hint = s.status.title() if s.status else (f"{self.k('SELECT')} plays this." if cur.get("playable") else f"{self.k('SELECT')} opens this.")
        self._shadowed(c, t.fit(f_row, hint, int((box.w - X(16)) / self.SQUEEZE)), f_row, b["text"], b["shadow"],
                       box.x + X(8), box.y + Y(6))

    ICONS = {"play": "play", "playall": "play", "shuffle": "play", "back": "exit"}

    def draw_iteminfo(self, c, info):
        from ..screens.iteminfo import hms
        b, t, X, Y = self.b, self.text, self.X, self.Y
        d = info.detail
        offer = info.kind != "download"
        if offer:
            self._dss_page(c, "Purchase Offer", [f"To purchase, point to Buy and press {self.k('SELECT')}.",
                                                 "Choose Exit to return to the list."])
        else:
            self._dss_page(c, "Program Information", ["Choose Play to watch this program.",
                                                      "Choose Exit to return to the list."])
        lines = [(d.get("title", ""), True)]
        meta = d.get("subtitle") or d.get("meta", "")
        if meta:
            lines.append((meta, False))
        if d.get("duration"):
            lines.append((f"Length: {max(1, d['duration'] // 60)} min.", False))
        if d.get("offset", 0) > 5:
            lines.append((f"Resume at: {hms(d['offset'])}", False))
        y = self._dss_lines(c, lines, X(57), Y(76), X(158))
        if offer:
            fc = self.fb(Y(13))
            w = self._shadowed(c, "Cost to view:", self.fb(Y(12)), b["text"], b["shadow"], X(57), y + Y(4))
            self._shadowed(c, "$0.00", fc, b["text"], b["shadow"], X(57) + w + X(6), y + Y(3))
            y += Y(20)
        f = self.f(Y(11))
        for line in t.wrap(f, d.get("summary", ""), int(X(158) / self.SQUEEZE), max(0, (Y(232) - y - Y(6)) // Y(12))):
            self._shadowed(c, line, f, b["soft"], b["shadow"], X(57), y + Y(6))
            y += Y(12)
        for k, name in enumerate(info.buttons()):
            r = pygame.Rect(X(220), Y(83) + k * Y(19), X(92), Y(13))
            word = "Buy" if offer and name == "play" else self.button_words(info.label(name), back="Exit")
            self._dss_button(c, r, word, self.ICONS.get(name, "info"), k == info.focus)
            self.hit(r, lambda k=k, name=name: (setattr(info, "focus", k), info.press(name)))

    def draw_playback(self, c, pb):
        from ..screens.iteminfo import hms
        b, X, Y = self.b, self.X, self.Y
        if pb.skip_label:
            self._notice(c, [f"{pb.skip_label.title()}: press {self.k('SELECT')}"], y_bottom=Y(160) if pb.bar_visible() else Y(227),
                         centre=True)
        if not pb.bar_visible():
            return
        state = "Paused" if self.app.video.paused else "Playing"
        r = self._notice(c, [pb.title, f"{state}    {hms(pb.pos)} of {hms(pb.dur) if pb.dur else '--:--'}", "", ""],
                         min_w=X(262), centre=True)
        bar = pygame.Rect(r.x + X(12), r.y + Y(32), r.w - X(24), Y(4))
        pygame.draw.rect(c, b["gap"], bar)
        frac = min(1.0, pb.pos / pb.dur) if pb.dur else 0.0
        pygame.draw.rect(c, b["teal"], (bar.x, bar.y, int(bar.w * frac), bar.h))
        self.hit(bar.inflate(0, Y(8)), lambda: pb.seek_to(self._click_frac(bar)))
        # The transport buttons: the DSS's teal buttons with their shadow.
        f = self.fb(Y(8))
        bw = (bar.w - 5 * X(4)) // 6
        for k, (kind, _, fn) in enumerate(pb.transport()):
            br = pygame.Rect(bar.x + k * (bw + X(4)), r.y + Y(41), bw, Y(13))
            pygame.draw.rect(c, b["shadow"], br.move(2, 2))
            pygame.draw.rect(c, b["teal"], br)
            self.transport_face(c, kind, br, b["text"], f, shadow=b["shadow"])
            self.hit(br, fn)

    def keyboard_rows(self, layer):
        if layer == "sym":
            keys = ["!@#$%^&*()", "_+=?~'\"|\\;", "[]{}<>,`  "]
        else:
            keys = ["ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZ0123", "456789.-/:"]
            if layer == "abc":
                keys = [k.lower() for k in keys]
        return keys + [["SHIFT", "SYM", "SPACE", "DEL", "CLEAR"], ["DONE", "CANCEL"]]

    KEY_WORDS = {"SPACE": "Space", "DEL": "Delete", "CLEAR": "Clear", "DONE": "Done", "CANCEL": "Exit"}

    def draw_keyboard(self, c, kb):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._dss_page(c, kb.prompt, [kb.hint or f"Use arrows to point to a letter, then press {self.k('SELECT')}.",
                                      "Choose Done when finished."])
        field = self.R(52, 75, 220, 15)
        pygame.draw.rect(c, b["shadow"], field.move(2, 2))
        pygame.draw.rect(c, b["teal"], field)
        f = self.fb(Y(12))
        shown = kb.value[:kb.caret]
        while shown and t.width(f, shown) * self.SQUEEZE > field.w - X(12):
            shown = shown[1:]
        x = field.x + X(4) + self._shadowed(c, shown, f, b["text"], b["shadow"], field.x + X(4), field.y + Y(2))
        pygame.draw.rect(c, b["text"], (x + 1, field.y + Y(2), 2, field.h - Y(4)))
        self._shadowed(c, t.fit(f, kb.value[kb.caret:], int((field.right - x - X(6)) / self.SQUEEZE)), f, b["text"],
                       b["shadow"], x + X(3), field.y + Y(2))
        for r, row in enumerate(kb.grid()):
            for col, cell in enumerate(row):
                on = (r, col) == (kb.row, kb.col)
                if len(cell) == 1:
                    rect = pygame.Rect(X(52) + col * X(22), Y(97) + r * Y(15), X(21), Y(14))
                    self._dss_cell(c, rect, on)
                    self._shadowed(c, cell, f, b["sel_ink"] if on else b["text"], None if on else b["shadow"],
                                   rect.centerx, rect.y + Y(2), align="center")
                else:
                    w = X(43) if len(row) > 2 else X(60)
                    rect = pygame.Rect(X(52) + col * (w + X(2)), Y(97) + r * Y(15) + Y(4), w, Y(13))
                    label = ("a-z" if kb.layer == "ABC" else "A-Z") if cell == "SHIFT" else \
                        ("ABC" if kb.layer == "sym" else "Sym") if cell == "SYM" else self.KEY_WORDS.get(cell, cell)
                    self._dss_button(c, rect, label, "exit" if cell == "CANCEL" else "play" if cell == "DONE" else "info", on)
                self.hit(rect, lambda r=r, col=col, cell=cell: (setattr(kb, "row", r), setattr(kb, "col", col),
                                                                kb._press(cell)))

    def draw_diagnostics(self, c, d):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._dss_page(c, "System Test", ["Signal and picture details for this channel.",
                                          f"Press {self.k('EXIT')} to return to the program."])
        f, fb_ = self.f(Y(11)), self.fb(Y(11))
        y = Y(76)
        for label, value, bar in [("Signal strength", d.signal(), True), ("Signal quality", d.quality(), True)] + \
                [(k, v, False) for k, v in d.rows()]:
            self._shadowed(c, label, fb_, b["text"], b["shadow"], X(57), y)
            self._shadowed(c, t.fit(f, str(value), int(X(150) / self.SQUEEZE)), f, b["text"], b["shadow"], X(150), y)
            if bar:
                track = pygame.Rect(X(180), y + Y(2), X(90), Y(7))
                self._bevel(c, track, b["gap"])
                pygame.draw.rect(c, b["teal"], (track.x + 1, track.y + 1, (track.w - 2) * value // 100, track.h - 2))
            y += Y(14)
        r = pygame.Rect(X(236), Y(200), X(52), Y(13))
        self._dss_button(c, r, "Exit", "exit", True)
        self.hit(r, lambda: d.handle("BACK"))

    def draw_capture(self, c, cap):
        f = self.fb(self.Y(12))
        lines = self.text.wrap(f, cap.prompt, int(self.X(238) / self.SQUEEZE), 3) + ["Waiting..."]
        self._notice(c, lines, y_bottom=self.Y(150), min_w=self.X(262))

    def draw_toast(self, c, msg):
        self._notice(c, self.text.wrap(self.fb(self.Y(12)), msg, int(self.X(238) / self.SQUEEZE), 3))

    def draw_screensaver(self, c, ss):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        c.fill((0, 0, 0, 255))
        f = self.fb(Y(9))
        w = sum(t.width(f, ch) for ch in "InDirecTV") + X(1) * 8
        bw, bh = max(w, X(30)), Y(36) + t.ink(f)[1]
        x, y = ss.position(bw, bh, W, H)
        self.tile(c, (x + bw // 2 - X(15), y, X(30), Y(30)), b["teal"])
        self._spaced(c, "InDirecTV", f, b["text"], x + (bw - w) // 2, y + Y(36), X(1))

    def _message(self, c, msg):
        c.fill((0, 0, 0, 255))
        f = self.fb(self.Y(12))
        self._notice(c, self.text.wrap(f, msg, int(self.X(238) / self.SQUEEZE), 5), y_bottom=self.Y(150),
                     min_w=self.X(262))

    # ── Boot ──────────────────────────────────────────────────────────────

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        stage = boot.stage()
        pygame.draw.rect(c, b["purple"], (0, 0, W, H))
        self.tile(c, (W // 2 - X(15), Y(74), X(30), Y(30)), b["teal"])
        f = self.fb(Y(9))
        w = sum(t.width(f, ch) for ch in "InDirecTV") + X(1) * 8
        self._spaced(c, "InDirecTV", f, b["text"], W // 2 - w // 2, Y(110), X(1))
        if stage == "starting":
            return
        caption = {"signal": "Acquiring satellite signal...", "guide": "Receiving program guide..." + self.guide_pct(),
                   "done": "Ready"}[stage]
        self._notice(c, [caption, "Press any button to skip."], y_bottom=Y(165))


def g_cat(skin) -> str:
    """The guide's current list name, for the banner's 'Normal List' slot."""
    from ..screens.guide import Guide
    g = skin.app.find(Guide) if hasattr(skin.app, "find") else None
    return g.category if g else "All"


def g_list(skin) -> str:
    """The guide's current list name, for the banner's favourites slot."""
    from ..screens.guide import Guide
    g = skin.app.find(Guide) if hasattr(skin.app, "find") else None
    return g.category if g and g.category != "All" else "Channels I Get"
