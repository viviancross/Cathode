"""InDirecTV: a mid-2000s DirecTV-style box, drawn to measurements taken from
frames of the real receivers. InDirecTV HD follows the HR20 (2007): a
near-white title area over a light facts strip, white synopsis on a cyan
page, a navy-and-teal grid inside a frame, amber selection, the colour keys
along the bottom; setup-style menu pages with the picture kept top-right.
InDirecTV (SD) is the D10/R15 era: the same screens compressed to 4:3 on a
navy ground, gold selection.

Geometry is written in the HR20's own 1280x720 pixels; X() and Y() scale it
to the canvas (the SD frame scales the two axes differently)."""

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
            "paper_ink": (23, 85, 129), "keybar": (55, 100, 142), "key_yellow": (224, 208, 49),
            "key_blue": (1, 78, 167),
            "teal": mix(cell, sky, 0.45), "teal_dark": mix(cell, sky, 0.2), "panel": mix(cell, navy, 0.15),
            "margin": mix(cell, sky, 0.7), "bar": mix(sky, text, 0.55), "deep": mix(navy, (0, 0, 0), 0.4),
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
        call, fc = ch.name.upper(), f_call
        if t.width(fc, call) > X(170):            # a long name: a smaller face before an ellipsis
            fc = self.f(Y(24))
        t.draw(c, t.fit(fc, call, X(170)), fc, b["text"], X(240), Y(99 if fc is f_call else 104))
        t.draw(c, t.fit(f_title, cur.title if cur else ch.name, X(560)), f_title, b["text"], X(385), Y(97))
        if ch.group:
            t.draw(c, t.fit(f_call, ch.group, X(260)), f_call, b["text"], X(1105), Y(99), align="right")
        strip = self.R(0, 134, 1280, 52)
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
        for dot, label, dx in ((b["key_yellow"], "TV Options", 820), (b["key_blue"], "Mini Guide", 1005)):
            pygame.draw.circle(c, dot, (X(dx), bar.centery), Y(11))
            t.draw(c, label, fk, b["text"], X(dx + 20), ky)
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
            t.draw(c, t.fit(f_ch, f"{ch.number} " + ch.name.upper(), chr_.w - X(24)), f_ch, b["text"],
                   X(110), cy)
            if self.app.is_favorite(ch):
                pygame.draw.circle(c, b["sel"], (chr_.right - X(12), y + Y(10)), Y(4))
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
            pygame.draw.rect(c, b["sel"], cell)
        else:
            vgrad(c, cell, rgba(b["cell_hi"]), rgba(b["cell"]))

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
            t.draw(c, t.fit(f_row, it.label, X(160)), f_row, ink, X(96), y)
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
            if it.value:
                hint = "Press LEFT or RIGHT to change this setting." if it.adjust else \
                    "Press SELECT to change this setting."
            elif it.submenu:
                hint = "Press SELECT to open this page."
            else:
                hint = "Press SELECT to choose." if it.enabled else "Not available right now."
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
        t.draw(c, "SELECT: choose    BACK: up a level    EXIT: close", self.f(Y(20)), b["soft"], X(96), Y(690))

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
                pygame.draw.rect(c, b["sel"], row)
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
                   "guide": "Step 2 of 2: Downloading guide data...", "done": "Ready"}[stage]
        t.draw(c, caption, self.f(Y(24)), b["text"], cx, Y(440), align="center")
        bar = self.R(360, 492, 560, 12)
        age = time.monotonic() - boot.start
        frac = {"signal": 0.15 + 0.25 * min(1, age / 4), "guide": 0.45 + 0.45 * min(1, age / 8),
                "done": 1.0}[stage]
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
            "sel_hi": mix(sel, (255, 255, 255), 0.25), "sel_shadow": None, "mark": text, "ink": text,
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
        img = f.render(s, True, ink[:3])
        w = max(1, int(img.get_width() * self.SQUEEZE))
        img = pygame.transform.smoothscale(img, (w, img.get_height()))
        x0 = x - w if align == "right" else x - w // 2 if align == "center" else x
        y0 = y - self.text.ink(f)[0]
        if shadow:
            sh = pygame.transform.smoothscale(f.render(s, True, shadow[:3]), (w, img.get_height()))
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

    def _notice(self, c, lines, y_bottom=None, min_w=0):
        """The DSS's purple notice box with its light bevel, bottom left (the
        'This showing is no longer available' card); returns its rect."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        f = self.fb(Y(12))
        w = max(max(t.width(f, s) for s in lines) + X(24), min_w)
        r = pygame.Rect(X(52), 0, min(w, X(262)), Y(8) + len(lines) * Y(13))
        r.bottom = y_bottom if y_bottom is not None else Y(227)
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
            y = Y(42) + i * Y(28.5)
            rh = Y(27)
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
                lines = t.wrap(f_cell, p.title, int((cell.w - X(8)) / self.SQUEEZE), 2)
                for k, line in enumerate(lines):
                    self._shadowed(c, line, f_cell, ink, shadow, cell.x + X(4), y + Y(2) + k * Y(12))
            self.hit((X(24), y, X(273), rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                         setattr(g, "focus", "grid"), g.handle("SELECT")))
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
            pygame.draw.rect(c, b["shadow"], (cell.x + 2, cell.bottom, cell.w, 2))
            pygame.draw.rect(c, b["shadow"], (cell.right, cell.y + 2, 2, cell.h))

    def _bevel(self, c, r, fill):
        """A cell with the DSS's light top-left / dark bottom-right edges."""
        b = self.b
        pygame.draw.rect(c, fill, r)
        hi, lo = mix(fill, (255, 255, 255), 0.35), mix(fill, (0, 0, 0), 0.35)
        pygame.draw.line(c, hi, r.topleft, r.topright)
        pygame.draw.line(c, hi, r.topleft, r.bottomleft)
        pygame.draw.line(c, lo, r.bottomleft, r.bottomright)
        pygame.draw.line(c, lo, r.topright, r.bottomright)

    # ── Menu: the DSS Main Menu ───────────────────────────────────────────

    def menu_video_box(self, menu):
        return "hidden"

    def draw_menu(self, c, m):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        pygame.draw.rect(c, b["purple"], (0, 0, W, Y(57)))
        pygame.draw.rect(c, b["teal"], (0, Y(57), W, Y(12)))
        pygame.draw.rect(c, b["page"], (0, Y(69), W, H - Y(69)))
        f_head, f_small, f_row = self.f(Y(16)), self.fb(Y(11)), self.fb(Y(12))
        title = "DSS Main Menu" if m.title == "MAIN MENU" else m.title.title()
        self._shadowed(c, title, f_head, b["soft"], b["shadow"], X(55), Y(16))
        self._shadowed(c, "Use arrows to point to an item, then press SELECT.", f_small, b["text"], b["shadow"],
                       X(55), Y(34))
        self._shadowed(c, "Pressing the number also selects the item.", f_small, b["text"], b["shadow"], X(55), Y(46))
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
                pygame.draw.rect(c, b["sel"], row)
                pygame.draw.rect(c, b["shadow"], (row.x, row.bottom, row.w, 1))
                pygame.draw.rect(c, b["shadow"], (row.right, row.y, 1, row.h))
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
            if it.value:
                hint = "LEFT / RIGHT change this setting." if it.adjust else "SELECT changes this setting."
            elif it.submenu:
                hint = "SELECT opens this menu."
            else:
                hint = {"Program Guide": "Show the on-screen programming schedule."}.get(it.label, "SELECT chooses this.")
            self._shadowed(c, t.fit(f_row, hint, int((box.w - X(26)) / self.SQUEEZE)), f_row, b["text"], b["shadow"],
                           box.x + X(20), box.y + Y(6))

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
        caption = {"signal": "Acquiring satellite signal...", "guide": "Receiving program guide...",
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
