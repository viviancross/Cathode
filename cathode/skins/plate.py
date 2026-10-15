"""Plate Network: a mid-2000s Dish Network-style box, drawn to measurements
taken from frames of the real receivers. Plate Network HD follows the ViP622
/722: a navy page with a green list tab, the programme centred above a grid
of light-blue channel cells and grey program cells, green selection, white
list panels with numbered capsule rows, grey dialogs with the Point Dish
signal meter. Plate Network (SD) follows the 2005 guide of the 322/522 era:
a grey page with a big blue tab of pills, blue cells with a pale selection,
and the deep-blue channel banner with its periwinkle date pill.

HD geometry is the ViP's own 1280x720 pixels; the SD screens are laid out in
the 4:3 frame's 640x480."""

import math
import time
from datetime import datetime, timedelta, timezone

import pygame

from .box import BoxSkin, mix, panel, rgba, vgrad


def ampm(dt) -> str:
    """'7:30am', the box's clock style."""
    return dt.astimezone().strftime("%I:%M%p").lstrip("0").lower()


def when(dt=None) -> str:
    """'7:52am Sun 3/29', the box's clock line."""
    dt = dt or datetime.now()
    return f"{ampm(dt)} {dt:%a} {dt.month}/{dt.day}"


def time_left(prog, now) -> str:
    h, m = divmod(max(0, int((prog.stop - now).total_seconds())) // 60, 60)
    return f"Time Left: {h}:{m:02d}"


class PlateHD(BoxSkin):
    name = "plate_hd"
    label = "Plate Network HD"
    canvas = (1280, 720)
    right_is_browse = True
    guide_hours = 1.5               # three half-hour columns, as the box showed
    guide_rows = 5
    SD = False
    # Measured: the page navy, the channel-cell blue, the selection green, the cell grey.
    NATIVE = {"bg": [25, 47, 78], "accent": [184, 209, 231], "accent2": [74, 131, 75],
              "text": [255, 255, 255], "chnum": [199, 200, 199]}

    def roles(self, b):
        navy, chan, sel, text, grey = b["bg"], b["accent"], b["accent2"], b["text"], b["chnum"]
        ink = mix(navy, (0, 0, 0), 0.1)
        return {
            "navy": navy, "navy_hi": mix(navy, (90, 120, 160), 0.4), "deep": mix(navy, (0, 0, 0), 0.25),
            "margin": mix(navy, (80, 120, 160), 0.3), "hdr": mix(navy, (120, 160, 220), 0.5),
            "chan_top": mix(chan, (255, 255, 255), 0.4), "chan_bot": chan, "cell_ink": ink,
            "cell_top": mix(grey, (255, 255, 255), 0.3), "cell_bot": mix(grey, (0, 0, 0), 0.08),
            "cell_edge": mix(grey, (0, 0, 0), 0.3), "marker": mix(grey, (0, 0, 0), 0.6),
            "sel": sel, "sel_hi": mix(sel, (255, 255, 255), 0.2), "sel_ink": text,
            "text": text, "muted": mix(text, navy, 0.4), "tab": sel, "tab_ink": text,
            "cursor": (246, 213, 85), "cursor_ink": ink,
            "list_panel": mix(chan, (255, 255, 255), 0.75), "row": mix(text, chan, 0.3), "row_edge": mix(chan, navy, 0.6),
            "pip": mix(navy, (0, 0, 0), 0.75), "pip_edge": mix(navy, (60, 110, 200), 0.5),
            "panel_top": (240, 242, 246), "panel_bot": (198, 204, 216), "ink": ink,
            "pill": (44, 62, 150), "pill_hi": (90, 110, 200), "pill_ink": text, "dish": (210, 30, 40),
            "banner_top": mix(chan, (255, 255, 255), 0.5), "banner_bot": chan, "banner_ink": ink,
            "banner_soft": mix(ink, chan, 0.4),
        }

    def X(self, v) -> int:
        return int(round(v * self.canvas[0] / 1280))

    def Y(self, v) -> int:
        return int(round(v * self.canvas[1] / 720))

    def R(self, x, y, w, h) -> pygame.Rect:
        return pygame.Rect(self.X(x), self.Y(y), self.X(w), self.Y(h))

    def u(self, v) -> int:
        return self.Y(v)

    # ── Wordmark ──────────────────────────────────────────────────────────

    def wordmark(self, c, x, y, size, ink, dish):
        """'plate' slanted and bold with a red dish beside it, NETWORK small
        beneath: our own mark, after the era's lockup."""
        t = self.text
        f = self.fb(size)
        h = t.ink(f)[1]
        tx = x + int(size * 0.9)
        f.italic = True                 # the face has no bold italic: slant it
        try:
            w = t.draw(c, "plate", f, ink, tx, y)
        finally:
            f.italic = False
        d = pygame.Rect(x, y + h // 4, int(size * 0.78), int(h * 0.62))
        pygame.draw.ellipse(c, dish, d)
        pygame.draw.ellipse(c, mix(dish, (255, 255, 255), 0.4), d.inflate(-d.w // 3, -d.h // 3))
        pygame.draw.line(c, dish, d.center, (d.right, y - h // 10), max(2, size // 10))
        fs = self.f(max(8, size // 3))
        t.draw(c, "N E T W O R K", fs, ink, tx + w, y + h + size // 12, align="right")
        return tx + w - x

    # ── Shared pieces ─────────────────────────────────────────────────────

    def _navy_page(self, c, rect):
        """The ViP's page: navy with a lighter wash across the upper half."""
        rect = pygame.Rect(rect)
        vgrad(c, rect, rgba(self.b["navy_hi"]), rgba(self.b["navy"]))
        wash = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.polygon(wash, (255, 255, 255, 22), [(rect.w * 0.3, 0), (rect.w, 0), (rect.w, rect.h * 0.35),
                                                        (rect.w * 0.45, rect.h * 0.5)])
        c.blit(wash, rect.topleft)

    def _dialog(self, c, r, title, code=None) -> int:
        """The box's grey dialog with its title in a pill; returns the y
        below the title."""
        b, t, Y, X = self.b, self.text, self.Y, self.X
        panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=Y(20), edge=rgba((255, 255, 255)), edge_w=Y(3))
        pill = pygame.Rect(r.x + X(30), r.y + Y(16), r.w - X(60) - (X(92) if code else 0), Y(44))
        vgrad(c, pill, rgba(b["pill_hi"]), rgba(b["pill"]), radius=Y(10))
        f = self.fb(Y(24))
        t.draw(c, t.fit(f, title, pill.w - X(20)), f, b["pill_ink"], pill.centerx,
               pill.y + (pill.h - t.ink(f)[1]) // 2, align="center")
        if code:
            cp = pygame.Rect(pill.right + X(12), pill.y, X(80), pill.h)
            pygame.draw.rect(c, b["panel_top"], cp, border_radius=Y(10))
            pygame.draw.rect(c, b["banner_soft"], cp, 2, border_radius=Y(10))
            fc = self.f(Y(20))
            t.draw(c, code, fc, b["banner_soft"], cp.centerx, cp.y + (cp.h - t.ink(fc)[1]) // 2, align="center")
        return pill.bottom

    def _meter(self, c, rect, level, locked):
        """The signal-strength bar from the box's Point Dish screen: a scale
        to 125, red until the signal locks."""
        b, t, Y = self.b, self.text, self.Y
        fs = self.f(Y(16))
        for k in range(6):
            t.draw(c, str(k * 25), fs, b["ink"], rect.x + int(rect.w * k / 5), rect.y, align="center")
        bar = pygame.Rect(rect.x, rect.y + Y(24), rect.w, Y(22))
        pygame.draw.rect(c, b["deep"], bar)
        col = (56, 170, 60) if locked else (168, 24, 24)
        pygame.draw.rect(c, col, (bar.x, bar.y, int(bar.w * min(125, level) / 125), bar.h))
        fl = self.fb(Y(18))
        t.draw(c, "Locked" if locked else "Not Locked", fl, col, rect.x, bar.bottom + Y(8))
        t.draw(c, f"signal strength   {level}", fl, col, rect.right, bar.bottom + Y(8), align="right")

    def _signal_loss(self, c):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        c.fill((0, 0, 0, 255))
        r = self.R(215, 180, 850, 290)
        y = self._dialog(c, r, "Acquiring Satellite Signal", "002") + Y(18)
        f = self.f(Y(20))
        for line in t.wrap(f, "The channel isn't sending a picture. Cathode keeps trying; press GUIDE or "
                              "a channel number to watch something else.", r.w - X(80), 2):
            t.draw(c, line, f, b["ink"], r.centerx, y, align="center")
            y += Y(28)
        level = int(8 + 14 * (1 + math.sin(time.monotonic() * 2.2)))
        self._meter(c, pygame.Rect(r.x + X(40), r.bottom - Y(104), r.w - X(80), Y(80)), level, False)

    def _grey_box(self, c, r):
        panel(c, r, rgba(self.b["panel_top"], 240), rgba(self.b["panel_bot"], 244), radius=self.Y(10),
              edge=rgba((255, 255, 255), 230), edge_w=self.Y(2))

    def _volume(self, c, cx, cy):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        v = self.app.video
        r = self.R(40, 24, 420, 56)
        self._grey_box(c, r)
        f = self.fb(Y(22))
        t.draw(c, "Mute" if v.muted else "Volume", f, (168, 24, 24) if v.muted else b["ink"], r.x + X(18),
               r.y + (r.h - t.ink(f)[1]) // 2)
        bar = pygame.Rect(r.x + X(130), r.y + Y(18), X(270), Y(20))
        pygame.draw.rect(c, b["deep"], bar)
        if not v.muted:
            pygame.draw.rect(c, (56, 170, 60), (bar.x, bar.y, int(bar.w * v.volume / 100), bar.h))

    def _trick(self, c, s):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(40, 640, 1200, 56)
        self._grey_box(c, r)
        behind = s["behind"]
        mm, ss = divmod(int(behind), 60)
        f = self.fb(Y(22))
        tag = "Paused" if s["paused"] else ("Live TV" if behind < 2 else "Playing")
        t.draw(c, tag, f, b["ink"], r.x + X(18), r.y + (r.h - t.ink(f)[1]) // 2)
        bar = pygame.Rect(r.x + X(190), r.y + Y(20), X(800), Y(16))
        pygame.draw.rect(c, b["deep"], bar)
        span = s["buffer"] + behind
        if span >= 2:
            x = bar.x + int(bar.w * s["buffer"] / span)
            pygame.draw.rect(c, b["pill_hi"], (bar.x, bar.y, x - bar.x, bar.h))
            pygame.draw.rect(c, b["ink"], (x - X(2), bar.y - Y(5), X(4), bar.h + Y(10)))
        t.draw(c, f"-{mm}:{ss:02d}" if behind >= 1 else "Live", f, b["ink"], r.right - X(18),
               r.y + (r.h - t.ink(f)[1]) // 2, align="right")

    # ── Live: banner, digits ──────────────────────────────────────────────

    def _digits(self, c, digits):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(40, 24, 300, 70)
        self._grey_box(c, r)
        f = self.fb(Y(40))
        t.draw(c, digits + "-" * (3 - len(digits)), f, b["ink"], r.centerx, r.y + (r.h - t.ink(f)[1]) // 2,
               align="center")

    def _banner(self, c, ch, cur, nxt, full=False, tag=None, bottom=False):
        """The channel banner in the ViP's light blue, number in a navy box
        at the left; BROWSE puts the same thing along the bottom."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(24, 20, 1232, 112)
        if bottom:
            r.bottom = H - Y(24)
        panel(c, r, rgba(b["banner_top"], 240), rgba(b["banner_bot"], 244), radius=Y(12), edge=rgba(b["navy"], 220))
        if tag:
            self.chip(c, r.x + X(18), r.y - Y(30) if bottom else r.bottom + Y(6), tag, self.fb(Y(16)),
                      rgba(b["tab"]), b["tab_ink"])
        nb = pygame.Rect(r.x + X(12), r.y + Y(12), X(150), r.h - Y(24))
        vgrad(c, nb, rgba(b["navy_hi"]), rgba(b["navy"]), radius=Y(8))
        t.draw(c, str(ch.number), self.fb(Y(42)), b["text"], nb.centerx, nb.y + Y(8), align="center")
        fs = self.fb(Y(16))
        t.draw(c, t.fit(fs, ch.name.upper(), nb.w - X(12)), fs, b["text"], nb.centerx, nb.bottom - Y(26),
               align="center")
        self._banner_text(c, r, nb.right + X(20), r.right - X(230), ch, cur, nxt, b["banner_ink"], b["banner_soft"])
        if full and cur and cur.description:
            f = self.f(Y(20))
            lines = t.wrap(f, cur.description, r.w - X(40), 3)
            d = pygame.Rect(r.x, 0, r.w, Y(24) + len(lines) * Y(28))
            d.y = r.y - d.h - Y(8) if bottom else r.bottom + Y(8)
            panel(c, d, rgba(b["banner_top"], 240), rgba(b["banner_bot"], 244), radius=Y(12), edge=rgba(b["navy"], 220))
            y = d.y + Y(14)
            for line in lines:
                t.draw(c, line, f, b["banner_ink"], d.x + X(20), y)
                y += Y(28)
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def _banner_text(self, c, r, x, right, ch, cur, nxt, ink, soft):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        f_title, f_line = self.fb(Y(28)), self.f(Y(20))
        t.draw(c, t.fit(f_title, cur.title if cur else ch.name, right - x), f_title, ink, x, r.y + Y(14))
        now = datetime.now(timezone.utc)
        if cur:
            bits = [f"{ampm(cur.start)} - {ampm(cur.stop)}"] + [s for s in (cur.rating, cur.episode) if s]
            t.draw(c, t.fit(f_line, "   ".join(bits), right - x), f_line, soft, x, r.y + Y(52))
        if nxt:
            fn = self.f(Y(17))
            t.draw(c, t.fit(fn, f"Next: {ampm(nxt.start)}  {nxt.title}", right - x), fn, soft, x, r.y + Y(82))
        rx = r.right - X(20)
        t.draw(c, when(), self.fb(Y(19)), ink, rx, r.y + Y(14), align="right")
        if cur:
            t.draw(c, time_left(cur, now), self.f(Y(18)), soft, rx, r.y + Y(46), align="right")
        t.draw(c, "INFO for details", self.f(Y(15)), soft, rx, r.bottom - Y(28), align="right")

    def draw_browse(self, c, br):
        if br.channel:
            cur, nxt = br.program()
            tag = "BROWSE  -  SELECT to watch" + (f"  (+{br.ahead})" if br.ahead else "")
            self._banner(c, br.channel, cur, nxt, tag=tag, bottom=True)

    # ── Guide: the ViP's ──────────────────────────────────────────────────

    def guide_video_box(self):
        r = self.R(728, 36, 450, 253)
        return (r.x, r.y, r.w, r.h)

    def _picture(self, c, caption=True):
        """The picture top-right in a light frame, the channel captioned in
        a dark strip under it; returns the frame's rect."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        vx, vy, vw, vh = self.guide_video_box()
        frame = pygame.Rect(vx - X(4), vy - Y(4), vw + X(8), vh + Y(8) + (Y(30) if caption else 0))
        pygame.draw.rect(c, b["pip_edge"], frame, border_radius=Y(3))
        pygame.draw.rect(c, (0, 0, 0, 0), (vx, vy, vw, vh))
        if caption:
            cap = pygame.Rect(vx, vy + vh, vw, Y(30))
            pygame.draw.rect(c, b["pip"], cap)
            live = self.app.live
            if live.channel:
                fc = self.fb(Y(21))
                t.draw(c, t.fit(fc, f"{live.channel.number} {live.channel.name.upper()}", vw - X(70)), fc,
                       b["muted"], cap.x + X(8), cap.y + (cap.h - t.ink(fc)[1]) // 2)
        return frame

    def draw_guide(self, c, g):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._navy_page(c, (0, 0, W, Y(334)))
        self.wordmark(c, X(100), Y(44), Y(40), b["text"], b["dish"])
        self._picture(c)
        tab = self.chip(c, X(250), Y(36), f"List: {g.category}", self.fb(Y(24)), rgba(b["tab"]), b["tab_ink"],
                        pad=Y(5), radius=Y(3))
        self.hit(tab, lambda: g.handle("THEMES"))
        t.draw(c, when(), self.fb(Y(24)), b["text"], X(250), Y(76))
        sel = g.selected()
        cur = self.app.live.programs(sel)[0] if sel else None
        cx = X(420)
        f_title = self.fb(Y(24))
        t.draw(c, t.fit(f_title, cur.title if cur else (sel.name if sel else ""), X(630)), f_title, b["text"],
               cx, Y(138), align="center")
        if cur:
            fd = self.f(Y(24))
            y = Y(164)
            for line in t.wrap(fd, cur.description or "", X(630), 4):
                t.draw(c, line, fd, b["text"], cx, y, align="center")
                y += Y(27)
            fm = self.f(Y(22))
            meta = "   ".join(s for s in (f"{ampm(cur.start)} - {ampm(cur.stop)}", cur.rating, cur.category) if s)
            t.draw(c, t.fit(fm, meta, X(580)), fm, b["text"], X(145), Y(300))

        # The header, the rows, the margins.
        pygame.draw.rect(c, b["navy"], (0, Y(334), W, H - Y(334)))
        pygame.draw.rect(c, b["margin"], self.R(1184, 334, 96, 346))
        hdr = self.R(0, 334, 1184, 30)
        pygame.draw.rect(c, b["hdr"], hdr)
        start, end = g.window()
        fh = self.fb(Y(22))
        hy = hdr.y + (hdr.h - t.ink(fh)[1]) // 2
        day = start.astimezone()
        t.draw(c, f"{day:%a} {day.month}/{day.day}", fh, b["text"], X(95), hy)
        ax = X(278)
        pygame.draw.polygon(c, b["text"], [(ax, hdr.y + Y(8)), (ax, hdr.bottom - Y(8)), (ax + X(9), hdr.centery)])
        slots = int(g.hours * 2)
        for i in range(slots):
            t.draw(c, ampm(start + timedelta(minutes=30 * i)), fh, b["text"], X(420 + 305 * i), hy, align="center")
        rows = g.filtered()[g.top: g.top + g.rows]
        mins = g.hours * 60
        now = datetime.now(timezone.utc)
        epg = self.app.epg
        f_cell, f_num, f_call = self.fb(Y(22)), self.fb(Y(24)), self.f(Y(20))
        grid_x, grid_w = X(271), X(908)
        for i, ch in enumerate(rows):
            y = Y(368 + 62.5 * i)
            rh = Y(57)
            row_sel = g.focus == "grid" and g.top + i == g.cursor
            chr_ = pygame.Rect(0, y, X(265), rh)
            vgrad(c, chr_, rgba(b["chan_top"]), rgba(b["chan_bot"]))
            t.draw(c, str(ch.number), f_num, b["cell_ink"], X(262), y + Y(4), align="right")
            t.draw(c, t.fit(f_call, ch.name.upper(), X(170)), f_call, b["cell_ink"], X(262), y + Y(30), align="right")
            if "HD" in ch.name.upper().split():
                t.draw(c, "HD", self.fb(Y(22)), b["pill_hi"], X(80), y + Y(6))
            if self.app.is_favorite(ch):
                pygame.draw.circle(c, b["sel"], (X(16), y + Y(14)), Y(5))
            cid = epg.resolve_channel_id(ch.epg_id, ch.name) if epg else None
            progs = epg.programs_in_window(cid, start, end) if cid else []
            if not progs:
                cell = pygame.Rect(grid_x, y, grid_w, rh)
                self._cell(c, cell, row_sel)
                t.draw(c, "No information", f_cell, b["sel_ink"] if row_sel else b["cell_ink"], cell.centerx,
                       y + (rh - t.ink(f_cell)[1]) // 2, align="center")
            for p in progs:
                a = max(0.0, (p.start - start).total_seconds() / 60)
                e = min(float(mins), (p.stop - start).total_seconds() / 60)
                if e <= a:
                    continue
                cell = pygame.Rect(grid_x + int(a / mins * grid_w), y, int((e - a) / mins * grid_w) - X(6), rh)
                on = row_sel and p.start <= max(now, start) < p.stop
                self._cell(c, cell, on)
                ink = b["sel_ink"] if on else b["cell_ink"]
                mk = b["sel_ink"] if on else b["marker"]
                if p.start < start:
                    pygame.draw.polygon(c, mk, [(cell.x + X(8), cell.centery), (cell.x + X(16), cell.centery - Y(8)),
                                                (cell.x + X(16), cell.centery + Y(8))])
                if p.stop > end:
                    pygame.draw.polygon(c, mk, [(cell.right - X(8), cell.centery), (cell.right - X(16), cell.centery - Y(8)),
                                                (cell.right - X(16), cell.centery + Y(8))])
                if cell.w > X(50):
                    t.draw(c, t.fit(f_cell, p.title, cell.w - X(44)), f_cell, ink, cell.centerx,
                           y + (rh - t.ink(f_cell)[1]) // 2, align="center")
            self.hit((0, y, X(1184), rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                      setattr(g, "focus", "grid"), g.handle("SELECT")))

    def _cell(self, c, cell, on):
        b = self.b
        if on:
            vgrad(c, cell, rgba(b["sel_hi"]), rgba(b["sel"]))
        else:
            vgrad(c, cell, rgba(b["cell_top"]), rgba(b["cell_bot"]))
            pygame.draw.rect(c, b["cell_edge"], cell, 1)

    # ── Menus: the ViP's list pages ───────────────────────────────────────

    def menu_cols(self, menu):
        return 1

    def _menu_top(self, c, title):
        """Navy page, the mark, the title in bold slanted caps, the date."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._navy_page(c, (0, 0, W, H))
        pygame.draw.rect(c, b["deep"], (0, Y(685), W, H - Y(685)))
        self.wordmark(c, X(46), Y(20), Y(34), b["text"], b["dish"])
        f = self.fb(Y(40))
        f.italic = True
        try:
            t.draw(c, t.fit(f, title, X(700)), f, b["text"], X(220), Y(28))
        finally:
            f.italic = False
        local = datetime.now()
        t.draw(c, f"{local:%a}, {local:%B} {local.day}", self.fb(Y(24)), b["text"], X(1157), Y(46), align="right")

    def draw_menu(self, c, m):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._menu_top(c, m.title.title())
        # The picture, framed in near-black, the channel captioned above it
        # and what's on beneath, as the box did.
        frame = self.R(555, 120, 667, 556)
        pygame.draw.rect(c, b["pip"], frame, border_radius=Y(8))
        pygame.draw.rect(c, b["pip_edge"], frame, Y(3), border_radius=Y(8))
        vx, vy, vw, vh = self.menu_video_box(m)
        pygame.draw.rect(c, (0, 0, 0, 0), (vx, vy, vw, vh))
        live = self.app.live
        if live.channel:
            fc = self.fb(Y(22))
            t.draw(c, t.fit(fc, f"{live.channel.number} {live.channel.name.upper()}", X(400)), fc, b["text"],
                   X(597), Y(139))
            t.draw(c, ampm(datetime.now()), fc, b["text"], X(1178), Y(139), align="right")
            on = live.programs()[0]
            if on:
                t.draw(c, "Today", fc, b["text"], X(597), Y(560))
                t.draw(c, t.fit(fc, f"{ampm(on.start)} - {ampm(on.stop)}  {on.title}", X(580)), fc, b["text"],
                       X(597), Y(588))

        lp = self.R(51, 127, 493, 567)
        pygame.draw.rect(c, b["list_panel"], lp, border_radius=Y(14))
        pygame.draw.rect(c, (255, 255, 255), lp, Y(3), border_radius=Y(14))
        n = len(m.items)
        rh = Y(53)
        n_vis = max(1, (lp.h - Y(32)) // rh)
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        f_row = self.fb(Y(24))
        for k, i in enumerate(range(first, min(n, first + n_vis))):
            it = m.items[i]
            y = lp.y + Y(16) + k * rh
            sel = i == m.cursor
            row = pygame.Rect(X(83), y, X(380), Y(42))
            num = pygame.Rect(X(470), y, X(44), Y(42))
            fill = b["cursor"] if sel else b["row"]
            for rr in (row, num):
                pygame.draw.rect(c, fill, rr, border_radius=Y(8))
                pygame.draw.rect(c, b["row_edge"], rr, Y(2), border_radius=Y(8))
            ink = b["cursor_ink"] if it.enabled else mix(b["cursor_ink"], b["row"], 0.5)
            ty = row.y + (row.h - t.ink(f_row)[1]) // 2
            t.draw(c, t.fit(f_row, it.label, row.w - X(170)), f_row, ink, row.x + X(16), ty)
            if it.value:
                v = it.value()
                v = f"< {v} >" if sel and it.adjust else v
                t.draw(c, t.fit(f_row, v, X(150)), f_row, ink, row.right - X(14), ty, align="right")
            elif it.submenu:
                t.draw(c, ">", f_row, ink, row.right - X(14), ty, align="right")
            if i < 9:
                t.draw(c, str(i + 1), f_row, ink, num.centerx, ty, align="center")
            self.hit(row, lambda i=i: m.activate(i))
        if n > n_vis:
            t.draw(c, f"{first + 1}-{min(n, first + n_vis)} of {n}", self.f(Y(18)), b["ink"], lp.x + X(32),
                   lp.bottom - Y(28))
        t.draw(c, "SELECT: choose   CANCEL: back   VIEW TV: close", self.f(Y(18)), b["muted"], X(51), Y(694))

    def menu_video_box(self, menu):
        r = self.R(609, 181, 569, 354)
        return (r.x, r.y, r.w, r.h)

    # ── Boot ──────────────────────────────────────────────────────────────

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        stage = boot.stage()
        self._navy_page(c, (0, 0, W, H))
        size = Y(72)
        mw = self.measure(self.wordmark, size, b["text"], b["dish"])
        mh = int(size * 1.7)
        mark = pygame.Surface((mw + X(20), mh), pygame.SRCALPHA)
        self.wordmark(mark, X(10), Y(10), size, b["text"], b["dish"])
        mx, my = (W - mw) // 2 - X(10), Y(130)
        c.blit(mark, (mx, my))
        mirror = pygame.transform.flip(mark, False, True)
        mirror.set_alpha(56)
        c.blit(mirror, (mx, my + mh - Y(16)))
        if stage == "starting":
            t.draw(c, "Starting up...", self.f(Y(24)), b["muted"], W // 2, Y(400), align="center")
            return
        age = time.monotonic() - boot.start
        caption, level, locked = {
            "signal": ("Acquiring Satellite Signal", int(min(88, 10 + age * 24)), False),
            "guide": ("Downloading Program Guide", 94, True),
            "done": ("Signal Acquired", 96, True)}[stage]
        r = self.R(256, 400, 768, 210)
        y = self._dialog(c, r, caption)
        self._meter(c, pygame.Rect(r.x + X(40), y + Y(22), r.w - X(80), Y(80)), level, locked)
        t.draw(c, "Press any button to skip", self.f(Y(17)), b["muted"], W // 2, Y(680), align="center")


class Plate(PlateHD):
    """The SD era, after the 2005 guide: a grey page, a big blue tab of pills,
    blue cells and a pale selection; the deep-blue banner. 640x480."""
    name = "plate"
    label = "Plate Network"
    canvas = (640, 480)
    guide_rows = 4
    SD = True
    # Measured from the 2005 guide and banner: the tab blue, the page grey,
    # the pale selection, the banner's deep blue.
    NATIVE = {"bg": [59, 88, 150], "accent": [232, 232, 233], "accent2": [209, 246, 255],
              "text": [255, 255, 255], "chnum": [3, 22, 126]}

    def roles(self, b):
        r = super().roles(b)
        blue, grey, sel, text, deep = b["bg"], b["accent"], b["accent2"], b["text"], b["chnum"]
        ink = mix(deep, (0, 0, 0), 0.3)
        r.update(
            blue=blue, blue_hi=mix(blue, (255, 255, 255), 0.35), grey=grey, grey_bot=mix(grey, (0, 0, 0), 0.4),
            stripe=mix(grey, (0, 0, 0), 0.08), pillfill=mix(grey, (255, 255, 255), 0.6),
            hdr=(94, 95, 90), cell_ink=text, sel=sel, sel_ink=ink, ink=ink, text=text,
            chan_ink=ink, chan_fill=mix(grey, (255, 255, 255), 0.5),
            banner=deep, banner_ink=text, banner_soft=mix(text, deep, 0.3), date_pill=(145, 152, 241),
            cursor=sel, cursor_ink=ink, row=blue, row_ink=text, row_edge=mix(blue, (255, 255, 255), 0.4),
            list_panel=mix(grey, (255, 255, 255), 0.7), muted=mix(ink, grey, 0.4),
            pill=mix(blue, (0, 0, 0), 0.2), pill_hi=mix(blue, (255, 255, 255), 0.25), pill_ink=text,
            panel_top=(236, 236, 238), panel_bot=(176, 180, 192), dish=(210, 30, 40))
        return r

    # SD coordinates are the 4:3 frame's own 640x480.
    def X(self, v) -> int:
        return int(round(v * self.canvas[0] / 640))

    def Y(self, v) -> int:
        return int(round(v * self.canvas[1] / 480))

    # ── Shared: the grey striped page and the blue tab ────────────────────

    def _grey_page(self, c, rect, bottom_dark=True):
        """The 2005 page: light grey with fine horizontal stripes, darker
        toward the foot."""
        rect = pygame.Rect(rect)
        b = self.b
        vgrad(c, rect, rgba(b["grey"]), rgba(b["grey_bot"] if bottom_dark else b["grey"]))
        stripes = pygame.Surface(rect.size, pygame.SRCALPHA)
        for y in range(0, rect.h, 5):
            pygame.draw.line(stripes, (0, 0, 0, 18), (0, y), (rect.w, y))
        c.blit(stripes, rect.topleft)

    def _tab(self, c, right):
        """The big blue tab: an ellipse clipped at the picture's edge, the
        mark and the TV-guide tag inside; returns its rect."""
        b = self.b
        tab = pygame.Surface((right, self.Y(243)), pygame.SRCALPHA)
        pygame.draw.ellipse(tab, b["blue"], (self.X(40), -self.Y(14), self.X(560), self.Y(258)))
        c.blit(tab, (0, 0))
        self.wordmark(c, self.X(76), self.Y(60), self.Y(30), b["text"], b["dish"])
        tag = self.R(88, 130, 50, 40)
        pygame.draw.rect(c, b["dish"], tag, border_radius=self.Y(4))
        f = self.fb(self.Y(13))
        self.text.draw(c, "TV", f, b["text"], tag.centerx, tag.y + self.Y(5), align="center")
        self.text.draw(c, "GUIDE", self.fb(self.Y(10)), b["text"], tag.centerx, tag.y + self.Y(23), align="center")
        return tab

    def _pill(self, c, y, lines, right):
        """A white capsule-left pill from x=167 to the picture's edge."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = pygame.Rect(X(167), Y(y), right - X(167), Y(40))
        pygame.draw.rect(c, b["pillfill"], r, border_top_left_radius=r.h // 2, border_bottom_left_radius=r.h // 2)
        f = self.fb(Y(15))
        ty = r.y + (r.h - len(lines) * Y(17)) // 2
        for line in lines:
            t.draw(c, t.fit(f, line, r.w - X(40)), f, b["ink"], r.x + X(28), ty)
            ty += Y(17)
        return r

    def guide_video_box(self):
        r = self.R(320, 0, 320, 243)
        return (r.x, r.y, r.w, r.h)

    # ── Guide: the 2005 page ──────────────────────────────────────────────

    def draw_guide(self, c, g):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._grey_page(c, (0, 0, W, Y(245)))
        vx, vy, vw, vh = self.guide_video_box()
        self._tab(c, vx)
        pygame.draw.rect(c, (0, 0, 0, 0), (vx, vy, vw, vh))
        local = datetime.now()
        self._pill(c, 33, [f"{local:%a} {local.month}/{local.day}", ampm(local)], vx)
        tab = self._pill(c, 100, [f"List: {g.category}"], vx)
        self.hit(tab, lambda: g.handle("THEMES"))
        sel = g.selected()
        self._pill(c, 166, [f"<  {sel.number if sel else '---'}  >"], vx)

        # The header, the rows: capsule channel cells, bevelled blue cells.
        hdr = self.R(0, 245, 640, 18)
        pygame.draw.rect(c, b["hdr"], hdr)
        pygame.draw.rect(c, b["hdr"], self.R(607, 245, 33, 235))
        start, end = g.window()
        fh = self.fb(Y(14))
        hy = hdr.y + (hdr.h - t.ink(fh)[1]) // 2
        day = start.astimezone()
        t.draw(c, f"{day:%a} {day.month}/{day.day}", fh, b["text"], X(60), hy)
        ax = X(146)
        pygame.draw.polygon(c, b["text"], [(ax, hdr.y + Y(4)), (ax, hdr.bottom - Y(4)), (ax + X(6), hdr.centery)])
        slots = int(g.hours * 2)
        for i in range(slots):
            t.draw(c, ampm(start + timedelta(minutes=30 * i)), fh, b["text"], X(208 + 158.5 * i), hy, align="center")
        pygame.draw.rect(c, (0, 0, 0), self.R(0, 263, 640, 205))
        rows = g.filtered()[g.top: g.top + g.rows]
        mins = g.hours * 60
        now = datetime.now(timezone.utc)
        epg = self.app.epg
        f_cell, f_num, f_call = self.fb(Y(15)), self.fb(Y(15)), self.fb(Y(12))
        grid_x, grid_w = X(131), X(472)
        for i, ch in enumerate(rows):
            y = Y(267 + 50 * i)
            rh = Y(46)
            row_sel = g.focus == "grid" and g.top + i == g.cursor
            chr_ = pygame.Rect(X(1), y, X(125), rh)
            pygame.draw.rect(c, b["chan_fill"], chr_)
            arc = pygame.Rect(X(20), y - Y(2), X(60), rh + Y(4))     # the blue crescent at the left
            pygame.draw.ellipse(c, b["blue"], arc)
            pygame.draw.ellipse(c, b["chan_fill"], arc.move(X(12), 0))
            t.draw(c, str(ch.number), f_num, b["chan_ink"], X(95), y + Y(6), align="center")
            t.draw(c, t.fit(f_call, ch.name.upper(), X(70)), f_call, b["chan_ink"], X(95), y + Y(26), align="center")
            cid = epg.resolve_channel_id(ch.epg_id, ch.name) if epg else None
            progs = epg.programs_in_window(cid, start, end) if cid else []
            if not progs:
                cell = pygame.Rect(grid_x, y, grid_w, rh)
                self._cell(c, cell, row_sel)
                t.draw(c, "No information", f_cell, b["sel_ink"] if row_sel else b["cell_ink"], cell.centerx,
                       y + (rh - t.ink(f_cell)[1]) // 2, align="center")
            for p in progs:
                a = max(0.0, (p.start - start).total_seconds() / 60)
                e = min(float(mins), (p.stop - start).total_seconds() / 60)
                if e <= a:
                    continue
                cell = pygame.Rect(grid_x + int(a / mins * grid_w), y, int((e - a) / mins * grid_w) - X(4), rh)
                on = row_sel and p.start <= max(now, start) < p.stop
                self._cell(c, cell, on)
                ink = b["sel_ink"] if on else b["cell_ink"]
                if p.start < start:
                    pygame.draw.polygon(c, ink, [(cell.x + X(5), cell.centery), (cell.x + X(11), cell.centery - Y(6)),
                                                 (cell.x + X(11), cell.centery + Y(6))])
                if p.stop > end:
                    pygame.draw.polygon(c, ink, [(cell.right - X(5), cell.centery), (cell.right - X(11), cell.centery - Y(6)),
                                                 (cell.right - X(11), cell.centery + Y(6))])
                if cell.w > X(30):
                    t.draw(c, t.fit(f_cell, p.title, cell.w - X(28)), f_cell, ink, cell.centerx,
                           y + (rh - t.ink(f_cell)[1]) // 2, align="center")
            self.hit((0, y, X(607), rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                     setattr(g, "focus", "grid"), g.handle("SELECT")))
        pygame.draw.rect(c, (251, 251, 251), self.R(0, 467, 640, 3))
        pygame.draw.rect(c, (206, 206, 206), self.R(0, 470, 640, 10))

    def _cell(self, c, cell, on):
        b = self.b
        if on:
            pygame.draw.rect(c, b["sel"], cell)
        else:
            pygame.draw.rect(c, b["blue"], cell)
            pygame.draw.rect(c, b["blue_hi"], (cell.x, cell.y, cell.w, self.Y(2)))

    # ── Live: the 2005 banner ─────────────────────────────────────────────

    def _banner(self, c, ch, cur, nxt, full=False, tag=None, bottom=False):
        """The deep-blue banner across the top, the date in a periwinkle pill
        at the left, the programme in white; BROWSE puts it at the bottom."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(0, 28, 640, 62)
        if bottom:
            r.bottom = H - Y(28)
        vgrad(c, r, rgba(b["banner"], 232), rgba(b["banner"], 240), radius=Y(10))
        if tag:
            self.chip(c, r.x + X(12), r.y - Y(22) if bottom else r.bottom + Y(4), tag, self.fb(Y(11)),
                      rgba(b["date_pill"]), b["ink"])
        local = datetime.now()
        pill = pygame.Rect(r.x + X(12), r.y + Y(7), X(120), Y(34))
        pygame.draw.rect(c, b["date_pill"], pill, border_radius=pill.h // 2)
        fp = self.fb(Y(12))
        t.draw(c, f"{local:%a} {local.month}/{local.day}", fp, b["ink"], pill.centerx, pill.y + Y(4), align="center")
        t.draw(c, ampm(local), fp, b["ink"], pill.centerx, pill.y + Y(18), align="center")
        fn = self.fb(Y(18))
        nw = t.draw(c, str(ch.number), fn, b["banner_ink"], pill.x + X(4), pill.bottom + Y(2))
        t.draw(c, t.fit(self.fb(Y(11)), ch.name.upper(), X(90)), self.fb(Y(11)), b["banner_ink"],
               pill.x + X(10) + nw, pill.bottom + Y(7))
        x = X(150)
        f_title, f_line = self.fb(Y(16)), self.f(Y(13))
        t.draw(c, t.fit(f_title, cur.title if cur else ch.name, X(300)), f_title, b["banner_ink"], x, r.y + Y(8))
        now = datetime.now(timezone.utc)
        if cur:
            t.draw(c, f"{ampm(cur.start)} - {ampm(cur.stop)}", f_line, b["banner_ink"], x, r.y + Y(29))
        if nxt:
            t.draw(c, t.fit(f_line, f"Next: {ampm(nxt.start)}  {nxt.title}", X(300)), f_line, b["banner_soft"],
                   x, r.y + Y(46))
        rx = r.right - X(14)
        if cur:
            t.draw(c, cur.rating or "", f_line, b["banner_ink"], rx, r.y + Y(8), align="right")
            t.draw(c, time_left(cur, now), f_line, b["banner_ink"], rx, r.y + Y(29), align="right")
        t.draw(c, "INFO for details", self.f(Y(11)), b["banner_soft"], rx, r.y + Y(47), align="right")
        if full and cur and cur.description:
            f = self.f(Y(13))
            lines = t.wrap(f, cur.description, r.w - X(28), 3)
            d = pygame.Rect(r.x, 0, r.w, Y(12) + len(lines) * Y(17))
            d.y = r.y - d.h - Y(4) if bottom else r.bottom + Y(4)
            vgrad(c, d, rgba(b["banner"], 232), rgba(b["banner"], 240), radius=Y(10))
            y = d.y + Y(7)
            for line in lines:
                t.draw(c, line, f, b["banner_ink"], d.x + X(14), y)
                y += Y(17)
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def _digits(self, c, digits):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(0, 28, 220, 50)
        vgrad(c, r, rgba(b["banner"], 232), rgba(b["banner"], 240), radius=Y(10))
        f = self.fb(Y(30))
        t.draw(c, digits + "-" * (3 - len(digits)), f, b["banner_ink"], r.centerx, r.y + (r.h - t.ink(f)[1]) // 2,
               align="center")

    def _volume(self, c, cx, cy):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        v = self.app.video
        r = self.R(12, 28, 260, 36)
        vgrad(c, r, rgba(b["banner"], 232), rgba(b["banner"], 240), radius=Y(10))
        f = self.fb(Y(14))
        t.draw(c, "Mute" if v.muted else "Volume", f, (255, 120, 120) if v.muted else b["banner_ink"], r.x + X(14),
               r.y + (r.h - t.ink(f)[1]) // 2)
        bar = pygame.Rect(r.x + X(90), r.y + Y(12), X(155), Y(12))
        pygame.draw.rect(c, b["pill"], bar)
        if not v.muted:
            pygame.draw.rect(c, (56, 190, 70), (bar.x, bar.y, int(bar.w * v.volume / 100), bar.h))

    def _trick(self, c, s):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(12, 420, 616, 36)
        vgrad(c, r, rgba(b["banner"], 232), rgba(b["banner"], 240), radius=Y(10))
        behind = s["behind"]
        mm, ss = divmod(int(behind), 60)
        f = self.fb(Y(14))
        tag = "Paused" if s["paused"] else ("Live TV" if behind < 2 else "Playing")
        t.draw(c, tag, f, b["banner_ink"], r.x + X(14), r.y + (r.h - t.ink(f)[1]) // 2)
        bar = pygame.Rect(r.x + X(110), r.y + Y(12), X(400), Y(12))
        pygame.draw.rect(c, b["pill"], bar)
        span = s["buffer"] + behind
        if span >= 2:
            x = bar.x + int(bar.w * s["buffer"] / span)
            pygame.draw.rect(c, b["date_pill"], (bar.x, bar.y, x - bar.x, bar.h))
            pygame.draw.rect(c, b["text"], (x - X(1), bar.y - Y(4), X(3), bar.h + Y(8)))
        t.draw(c, f"-{mm}:{ss:02d}" if behind >= 1 else "Live", f, b["banner_ink"], r.right - X(14),
               r.y + (r.h - t.ink(f)[1]) // 2, align="right")

    # ── Menus: the 2005 page with a white list panel ──────────────────────

    def menu_cols(self, menu):
        return 1

    def menu_video_box(self, menu):
        return self.guide_video_box()

    def draw_menu(self, c, m):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._grey_page(c, (0, 0, W, H))
        vx, vy, vw, vh = self.guide_video_box()
        self._tab(c, vx)
        pygame.draw.rect(c, (0, 0, 0, 0), (vx, vy, vw, vh))
        self._pill(c, 33, [m.title.title()], vx)
        local = datetime.now()
        self._pill(c, 100, [f"{local:%a} {local.month}/{local.day}", ampm(local)], vx)
        live = self.app.live
        if live.channel:
            self._pill(c, 166, [f"{live.channel.number} {live.channel.name.upper()}"], vx)

        lp = self.R(12, 252, 616, 212)
        pygame.draw.rect(c, b["list_panel"], lp, border_radius=Y(10))
        pygame.draw.rect(c, b["blue"], lp, Y(2), border_radius=Y(10))
        n = len(m.items)
        rh = Y(26)
        n_vis = max(1, (lp.h - Y(14)) // rh)
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        f_row = self.fb(Y(14))
        for k, i in enumerate(range(first, min(n, first + n_vis))):
            it = m.items[i]
            y = lp.y + Y(8) + k * rh
            sel = i == m.cursor
            row = pygame.Rect(lp.x + X(10), y, lp.w - X(60), rh - Y(4))
            num = pygame.Rect(lp.right - X(44), y, X(34), rh - Y(4))
            fill, ink = (b["cursor"], b["cursor_ink"]) if sel else (b["row"], b["row_ink"])
            if not it.enabled:
                ink = mix(ink, fill, 0.5)
            for rr in (row, num):
                pygame.draw.rect(c, fill, rr, border_radius=rr.h // 2)
                pygame.draw.rect(c, b["row_edge"], (rr.x + rr.h // 2, rr.y, rr.w - rr.h, Y(2)))
            ty = row.y + (row.h - t.ink(f_row)[1]) // 2
            t.draw(c, t.fit(f_row, it.label, row.w - X(170)), f_row, ink, row.x + X(14), ty)
            if it.value:
                v = it.value()
                v = f"< {v} >" if sel and it.adjust else v
                t.draw(c, t.fit(f_row, v, X(150)), f_row, ink, row.right - X(12), ty, align="right")
            elif it.submenu:
                t.draw(c, ">", f_row, ink, row.right - X(12), ty, align="right")
            if i < 9:
                t.draw(c, str(i + 1), f_row, ink, num.centerx, ty, align="center")
            self.hit(row, lambda i=i: m.activate(i))
        if n > n_vis:
            t.draw(c, f"{first + 1}-{min(n, first + n_vis)} of {n}", self.f(Y(11)), b["ink"], lp.x + X(14),
                   lp.bottom - Y(14))
        t.draw(c, "SELECT: choose   CANCEL: back   VIEW TV: close", self.f(Y(11)), b["ink"], X(12), Y(468))

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        stage = boot.stage()
        self._grey_page(c, (0, 0, W, H))
        tab = pygame.Surface((W, Y(243)), pygame.SRCALPHA)
        pygame.draw.ellipse(tab, b["blue"], (X(40), -Y(14), X(560), Y(258)))
        c.blit(tab, (0, 0))
        size = Y(44)
        mw = self.measure(self.wordmark, size, b["text"], b["dish"])
        self.wordmark(c, (W - mw) // 2, Y(70), size, b["text"], b["dish"])
        if stage == "starting":
            t.draw(c, "Starting up...", self.fb(Y(14)), b["text"], W // 2, Y(180), align="center")
            return
        age = time.monotonic() - boot.start
        caption, level, locked = {
            "signal": ("Acquiring Satellite Signal", int(min(88, 10 + age * 24)), False),
            "guide": ("Downloading Program Guide", 94, True),
            "done": ("Signal Acquired", 96, True)}[stage]
        r = self.R(80, 270, 480, 150)
        y = self._dialog(c, r, caption)
        self._meter(c, pygame.Rect(r.x + X(30), y + Y(16), r.w - X(60), Y(60)), level, locked)
        t.draw(c, "Press any button to skip", self.f(Y(12)), b["ink"], W // 2, Y(448), align="center")

    def _signal_loss(self, c):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        c.fill((0, 0, 0, 255))
        r = self.R(80, 120, 480, 200)
        y = self._dialog(c, r, "Acquiring Satellite Signal", "002") + Y(12)
        f = self.f(Y(13))
        for line in t.wrap(f, "The channel isn't sending a picture. Cathode keeps trying; press GUIDE or "
                              "a channel number to watch something else.", r.w - X(60), 2):
            t.draw(c, line, f, b["ink"], r.centerx, y, align="center")
            y += Y(18)
        level = int(8 + 14 * (1 + math.sin(time.monotonic() * 2.2)))
        self._meter(c, pygame.Rect(r.x + X(30), r.bottom - Y(72), r.w - X(60), Y(60)), level, False)
