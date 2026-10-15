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
        f_title = self.fb(self.Y(32))
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
        """The translucent navy band laid over the picture, a sky line under it."""
        rect = pygame.Rect(rect)
        vgrad(c, rect, rgba(self.b["navy"], 226), rgba(self.b["navy"], 236))
        pygame.draw.rect(c, self.b["sky"], (rect.x, rect.bottom - self.Y(3), rect.w, self.Y(3)))

    def _banner(self, c, ch, cur, nxt, full=False, tag=None):
        """The channel banner across the top: mark, channel and clock on the
        first line, the title on the second; INFO again adds the synopsis."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(0, 0, 1280, 120)
        self._band(c, r)
        if tag:
            self.chip(c, X(96), r.bottom + Y(8), tag, self.fb(Y(16)), rgba(b["sel"]), b["sel_ink"])
        self.mark_inline(c, X(96), Y(26), 40, b["text"])
        f_num, f_call = self.fb(Y(36)), self.f(Y(22))
        nw = t.draw(c, str(ch.number), f_num, b["text"], X(300), Y(16))
        t.draw(c, t.fit(f_call, ch.name.upper(), X(300)), f_call, b["soft"], X(300) + nw + X(12), Y(28))
        t.draw(c, stamp(), self.fb(Y(24)), b["text"], X(1184), Y(18), align="right")
        f_title, f_line = self.fb(Y(28)), self.f(Y(22))
        t.draw(c, t.fit(f_title, cur.title if cur else ch.name, X(560)), f_title, b["text"], X(300), Y(64))
        if cur:
            bits = [hours(cur)] + [s for s in (cur.rating, cur.episode) if s]
            t.draw(c, t.fit(f_line, "   ".join(bits), X(380)), f_line, b["soft"], X(1184), Y(68), align="right")
            now = datetime.now(timezone.utc)
            left = max(0, int((cur.stop - now).total_seconds() // 60))
            t.draw(c, f"{left} min left", self.f(Y(18)), b["soft"], X(1184), Y(96), align="right")
        if nxt:
            fs = self.f(Y(18))
            t.draw(c, t.fit(fs, f"Next: {nxt.title}  {ampm(nxt.start)}", X(620)), fs, b["soft"], X(300), Y(96))
        if full and cur and cur.description:
            f = self.f(Y(22))
            lines = t.wrap(f, cur.description, X(1088), 3)
            d = pygame.Rect(0, r.bottom, W, Y(16) + len(lines) * Y(30))
            vgrad(c, d, rgba(b["navy"], 226), rgba(b["deep"], 236))
            y = d.y + Y(10)
            for line in lines:
                t.draw(c, line, f, b["text"], X(96), y)
                y += Y(30)
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def _digits(self, c, digits):
        """Typed digits take the channel's place on a short band."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(0, 0, 1280, 70)
        self._band(c, r)
        f = self.fb(Y(40))
        t.draw(c, digits + "-" * (3 - len(digits)), f, b["text"], X(300), Y(12))
        t.draw(c, stamp(), self.fb(Y(24)), b["text"], X(1184), Y(18), align="right")

    def _signal_loss(self, c):
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

    def _volume(self, c, cx, cy):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        v = self.app.video
        r = self.R(340, 630, 600, 50)
        vgrad(c, r, rgba(b["navy"], 226), rgba(b["navy"], 236), radius=Y(6))
        pygame.draw.rect(c, b["sky"], (r.x, r.bottom - Y(3), r.w, Y(3)))
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
        vgrad(c, r, rgba(b["navy"], 226), rgba(b["navy"], 236), radius=Y(6))
        pygame.draw.rect(c, b["sky"], (r.x, r.bottom - Y(3), r.w, Y(3)))
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
            fd = self.f(Y(22))
            y = Y(206)
            for line in t.wrap(fd, cur.description + (f" {cur.category}." if cur.category else ""), X(735), 3):
                t.draw(c, line, fd, b["text"], X(95), y)
                y += Y(38)

        # The frame: a navy header, navy channel cells, teal cells, the colour keys.
        pygame.draw.rect(c, b["gap"], self.R(96, 313, 1182, 359))
        hdr = self.R(96, 313, 1182, 35)
        pygame.draw.rect(c, b["navy"], hdr)
        start, end = g.window()
        fh = self.fb(Y(22))
        hy = hdr.y + (hdr.h - t.ink(fh)[1]) // 2
        day = start.astimezone()
        t.draw(c, f"{day:%a} {day.month}/{day.day}", fh, b["text"], X(105), hy)
        slots = int(g.hours * 2)
        col = 885 / slots
        for i in range(slots):
            t.draw(c, ampm(start + timedelta(minutes=30 * i)), fh, b["text"], X(299 + col * i + 8), hy)

        rows = g.filtered()[g.top: g.top + g.rows]
        mins = g.hours * 60
        epg = self.app.epg
        f_cell = self.f(Y(22))
        grid_x, grid_w = X(299), X(885)
        for i, ch in enumerate(rows):
            y = Y(352 + 48 * i)
            rh = Y(44)
            row_sel = g.focus == "grid" and g.top + i == g.cursor
            chr_ = pygame.Rect(X(96), y, X(199), rh)
            pygame.draw.rect(c, b["navy"], chr_)
            cy = y + (rh - t.ink(f_cell)[1]) // 2
            t.draw(c, t.fit(f_cell, f"{ch.number} " + ch.name.upper(), chr_.w - X(24)), f_cell, b["text"],
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
        fl = self.f(Y(22))
        ly = bar.y + (bar.h - t.ink(fl)[1]) // 2
        cat = g.category if g.category != "All" else "All Channels"
        t.draw(c, cat, fl, b["sel"] if g.focus == "category" else b["soft"], X(110), ly)
        self.hit((X(96), bar.y, X(400), bar.h), lambda: g.handle("THEMES"))
        for dot, label, dx in (("red", "-1 day", 619), ("green", "+1 day", 772), ("yellow", "Themes", 926)):
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
        n_vis = max(1, (Y(690) - Y(214)) // rh)
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
        vgrad(c, r, rgba(b["navy"], 226), rgba(b["navy"], 236))
        pygame.draw.rect(c, b["sky"], (0, r.y, W, Y(3)))
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
    """The SD era: the same screens in 4:3 on a navy ground, gold selection."""
    name = "indirect"
    label = "InDirecTV"
    canvas = (640, 480)
    SD = True
    NATIVE = {"bg": [6, 24, 70], "accent": [22, 62, 140], "accent2": [234, 190, 40],
              "text": [255, 255, 255], "chnum": [40, 120, 220]}

    def roles(self, b):
        r = super().roles(b)
        navy, cell, text, sky = b["bg"], b["accent"], b["text"], b["chnum"]
        # No white or cyan in the SD era: the top is navy fading to black.
        r.update(paper_top=mix(navy, cell, 0.3), paper_bot=mix(navy, (0, 0, 0), 0.3),
                 strip=mix(navy, cell, 0.5), strip_rule=mix(cell, text, 0.3), strip_ink=text,
                 page_top=mix(navy, (0, 0, 0), 0.3), page_mid=mix(navy, (0, 0, 0), 0.2), page_bot=mix(navy, (0, 0, 0), 0.45),
                 ink=text, watermark=mix(navy, cell, 0.6),
                 sel_ink=(20, 16, 0), sel_shadow=None,
                 teal=mix(navy, cell, 0.4), teal_dark=mix(navy, cell, 0.15), panel=mix(navy, (0, 0, 0), 0.35),
                 margin=mix(navy, cell, 0.6), bar=mix(cell, text, 0.5))
        return r
