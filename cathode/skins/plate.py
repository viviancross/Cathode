"""Plate Network: a mid-2000s Dish Network-style box, drawn to measurements
taken from frames of the real receivers. Plate Network HD follows the 2007
teal guide: a dark teal page with the mark and TV-guide tag top-left, the
programme's title, rating and synopsis in white beside the picture, the list
name and clock, a charcoal time header and 7 rows of charcoal channel cells
with teal (on now) and navy (later) program cells, a gold frame on the
selection; the playback banner is a grey translucent box lettered in white.
Plate Network (SD) follows the 2005 guide of the 322/522 era: a grey page
with a big blue tab of pills, blue cells with a pale selection, and a bare
black band of a banner.

HD geometry: the capture's 4:3 picture, mapped onto the 1280x720 canvas; SD
geometry: the 4:3 frame's own 640x480."""

import time
from datetime import datetime, timedelta, timezone

import pygame

from .box import BoxSkin, mix, panel, rgba, vgrad


def ampm(dt) -> str:
    """'7:30am', the box's clock style."""
    return dt.astimezone().strftime("%I:%M%p").lstrip("0").lower()


def when(dt=None) -> str:
    """'Sep 2  2:58PM', the HD box's clock line."""
    dt = dt or datetime.now()
    return f"{dt:%b} {dt.day}  {ampm(dt).upper()}"


def time_left(prog, now) -> str:
    h, m = divmod(max(0, int((prog.stop - now).total_seconds())) // 60, 60)
    return f"Time left {h}:{m:02d}"


class PlateHD(BoxSkin):
    name = "plate_hd"
    label = "Plate Network HD"
    canvas = (1280, 720)
    right_is_browse = True
    guide_hours = 1.5               # three half-hour columns, as the box showed
    guide_rows = 7
    SD = False
    # Measured: the page teal, the on-now cell teal, the later-cell navy, the
    # gold of the selection frame.
    NATIVE = {"bg": [0, 51, 66], "accent": [0, 62, 61], "accent2": [0, 17, 55],
              "text": [255, 255, 255], "chnum": [230, 235, 134]}

    def roles(self, b):
        page, now_, later, text, gold = b["bg"], b["accent"], b["accent2"], b["text"], b["chnum"]
        return {
            "page": page, "page_hi": mix(page, (40, 120, 130), 0.35), "page_lo": mix(page, (0, 0, 0), 0.3),
            "now": now_, "later": later, "edge": mix(later, (120, 160, 200), 0.3),
            "chan": (58, 54, 66), "hdr": (10, 18, 30), "gold": gold, "text": text,
            "soft": mix(text, page, 0.3), "muted": mix(text, page, 0.5),
            "banner": (34, 35, 33), "banner_ink": text, "pill": (84, 84, 86), "pill_ink": text,
            "tag": (200, 30, 40), "dish": (210, 30, 40),
            "list_panel": (232, 238, 240), "row": mix(page, (40, 120, 130), 0.5), "row_ink": text,
            "row_edge": mix(page, (0, 0, 0), 0.3), "cursor": gold, "cursor_ink": mix(later, (0, 0, 0), 0.3),
            "ink": mix(later, (0, 0, 0), 0.3), "pip": (0, 0, 0), "pip_edge": mix(page, (120, 170, 180), 0.5),
            "panel_top": (236, 238, 240), "panel_bot": (190, 196, 204),
            "sel": gold, "sel_ink": mix(later, (0, 0, 0), 0.3), "deep": mix(page, (0, 0, 0), 0.4),
        }

    def X(self, v) -> int:
        return int(round(v * self.canvas[0] / 1280))

    def Y(self, v) -> int:
        return int(round(v * self.canvas[1] / 720))

    def R(self, x, y, w, h) -> pygame.Rect:
        return pygame.Rect(self.X(x), self.Y(y), self.X(w), self.Y(h))

    def u(self, v) -> int:
        return self.Y(v)

    # ── Lettering: the box used a condensed bold sans ─────────────────────

    def cb(self, c, s, f, ink, x, y, align="left", squeeze=0.86) -> int:
        """Bold text squeezed to the box's condensed width; returns its width."""
        if not s:
            return 0
        img = f.render(s, True, ink[:3])
        w, h = img.get_size()
        img = pygame.transform.smoothscale(img, (max(1, int(w * squeeze)), h))
        w = img.get_width()
        x = x - w if align == "right" else x - w // 2 if align == "center" else x
        c.blit(img, (x, y - self.text.ink(f)[0]))
        return w

    def fit_cb(self, f, s, max_w, squeeze=0.86) -> str:
        return self.text.fit(f, s, int(max_w / squeeze))

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

    def _tvguide(self, c, x, y, w, h):
        """The red TV-guide tag the box carried under its mark."""
        b, t = self.b, self.text
        r = pygame.Rect(x, y, w, h)
        pygame.draw.rect(c, b["tag"], r, border_radius=h // 8)
        pygame.draw.rect(c, mix(b["tag"], (255, 255, 255), 0.5), r, 2, border_radius=h // 8)
        f1, f2 = self.fb(int(h * 0.42)), self.fb(int(h * 0.26))
        t.draw(c, "TV", f1, b["text"], r.centerx, r.y + int(h * 0.08), align="center")
        t.draw(c, "GUIDE", f2, b["text"], r.centerx, r.y + int(h * 0.56), align="center")

    # ── Pages ─────────────────────────────────────────────────────────────

    def _page(self, c, rect):
        """The teal page, lighter at the top, with the box's faint swirls."""
        rect = pygame.Rect(rect)
        b = self.b
        vgrad(c, rect, rgba(b["page_hi"]), rgba(b["page_lo"]))
        swirl = pygame.Surface(rect.size, pygame.SRCALPHA)
        for k in range(3):
            pygame.draw.ellipse(swirl, (255, 255, 255, 14),
                                (-rect.w // 3 + k * rect.w // 4, -rect.h // 3 + k * rect.h // 6, rect.w, rect.h),
                                max(3, rect.h // 24))
        c.blit(swirl, rect.topleft)

    def guide_video_box(self):
        r = self.R(786, 8, 494, 276)
        return (r.x, r.y, r.w, r.h)

    def _picture(self, c):
        vx, vy, vw, vh = self.guide_video_box()
        pygame.draw.rect(c, (0, 0, 0, 0), (vx, vy, vw, vh))
        pygame.draw.rect(c, rgba(self.b["pip_edge"]), (vx - 3, vy - 3, vw + 6, vh + 6), 3)
        return pygame.Rect(vx, vy, vw, vh)

    # ── Live: the grey banner, digits, volume, trick ──────────────────────

    def _box(self, c, r, alpha=232):
        box = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(box, (*self.b["banner"], alpha), box.get_rect(), border_radius=self.Y(8))
        c.blit(box, r.topleft)

    def _banner(self, c, ch, cur, nxt, full=False, tag=None, bottom=False):
        """Number, call sign and list stacked at the left; title and rating
        centred; date, clock and time left at the right. BROWSE puts the same
        box along the bottom."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(40, 43, 1200, 103)
        if bottom:
            r.bottom = H - Y(43)
        self._box(c, r)
        ink = b["banner_ink"]
        f_big, f_mid = self.fb(Y(38)), self.fb(Y(30))
        cx = r.x + X(123)
        # Both outer stacks sit centred in the box's height.
        self.cb(c, str(ch.number), f_big, ink, cx, r.y + Y(10), align="center")
        self.cb(c, self.fit_cb(f_mid, ch.name.upper(), X(200)), f_mid, ink, cx, r.y + Y(45), align="center")
        self.cb(c, self.fit_cb(f_mid, g_list(self), X(200)), f_mid, ink, cx, r.y + Y(73), align="center")
        mid = r.x + X(607)
        self.cb(c, self.fit_cb(f_mid, cur.title if cur else ch.name, X(560)), f_mid, ink, mid, r.y + Y(24), align="center")
        now = datetime.now(timezone.utc)
        if cur:
            bits = [s for s in (cur.rating, f"{ampm(cur.start)} - {ampm(cur.stop)}") if s]
            self.cb(c, "   ".join(bits), f_mid, ink, mid, r.y + Y(59), align="center")
        local = datetime.now()
        rx = r.right - X(20)
        self.cb(c, f"{local:%a} {local.month}/{local.day:02d}", f_mid, ink, rx, r.y + Y(12), align="right")
        self.cb(c, ampm(local), f_mid, ink, rx, r.y + Y(42), align="right")
        if cur:
            self.cb(c, time_left(cur, now), f_mid, ink, rx, r.y + Y(72), align="right")
        if nxt:
            fn = self.fb(Y(17))
            self.cb(c, self.fit_cb(fn, f"Next: {nxt.title}", X(420)), fn, b["soft"], mid, r.y + Y(84), align="center")
        label = tag or ("INFO FOR DETAILS" if not full else "")
        if label:
            pr = pygame.Rect(r.x + X(17), r.y - Y(34) if bottom else r.bottom + Y(10), 0, Y(34))
            fp = self.fb(Y(28))
            pr.w = int(t.width(fp, label) * 0.86) + X(40)
            pygame.draw.rect(c, b["pill"], pr, border_radius=Y(6))
            self.cb(c, label, fp, b["pill_ink"], pr.x + X(18), pr.y + Y(5))
        if full and cur and cur.description:
            f = self.fb(Y(18))
            lines = t.wrap(f, cur.description, int(r.w * 0.86) - X(40), 3)
            d = pygame.Rect(r.x, 0, r.w, Y(16) + len(lines) * Y(26))
            d.y = r.y - d.h - Y(8) if bottom else r.bottom + Y(8)
            self._box(c, d)
            y = d.y + Y(8)
            for line in lines:
                self.cb(c, line, f, ink, d.x + X(20), y)
                y += Y(26)
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def draw_browse(self, c, br):
        if br.channel:
            cur, nxt = br.program()
            tag = "BROWSE  -  SELECT TO WATCH" + (f"  (+{br.ahead})" if br.ahead else "")
            self._banner(c, br.channel, cur, nxt, tag=tag, bottom=True)

    def _digits(self, c, digits):
        b, X, Y = self.b, self.X, self.Y
        r = self.R(40, 43, 300, 70)
        self._box(c, r)
        self.cb(c, digits + "-" * (3 - len(digits)), self.fb(Y(36)), b["banner_ink"], r.centerx, r.y + Y(14), align="center")

    def _volume(self, c, cx, cy):
        b, X, Y = self.b, self.X, self.Y
        v = self.app.video
        r = self.R(40, 43, 480, 56)
        self._box(c, r)
        f = self.fb(Y(22))
        self.cb(c, "MUTE" if v.muted else "VOLUME", f, b["gold"] if v.muted else b["banner_ink"], r.x + X(20), r.y + Y(14))
        bar = pygame.Rect(r.x + X(170), r.y + Y(18), X(290), Y(20))
        pygame.draw.rect(c, b["pill"], bar)
        if not v.muted:
            pygame.draw.rect(c, b["gold"], (bar.x, bar.y, int(bar.w * v.volume / 100), bar.h))

    def _trick(self, c, s):
        b, X, Y = self.b, self.X, self.Y
        r = self.R(40, 620, 1200, 56)
        self._box(c, r)
        behind = s["behind"]
        mm, ss = divmod(int(behind), 60)
        f = self.fb(Y(22))
        tag = "PAUSED" if s["paused"] else ("LIVE TV" if behind < 2 else "PLAYING")
        self.cb(c, tag, f, b["banner_ink"], r.x + X(20), r.y + Y(14))
        bar = pygame.Rect(r.x + X(200), r.y + Y(20), X(800), Y(16))
        pygame.draw.rect(c, b["pill"], bar)
        span = s["buffer"] + behind
        if span >= 2:
            x = bar.x + int(bar.w * s["buffer"] / span)
            pygame.draw.rect(c, b["gold"], (bar.x, bar.y, x - bar.x, bar.h))
            pygame.draw.rect(c, b["text"], (x - X(2), bar.y - Y(5), X(4), bar.h + Y(10)))
        self.cb(c, f"-{mm}:{ss:02d}" if behind >= 1 else "LIVE", f, b["banner_ink"], r.right - X(20), r.y + Y(14), align="right")

    def _signal_loss(self, c):
        """Dish's ATTENTION dialog on black, with its progress bar (the
        frame at 0:16), while the channel sends nothing."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        c.fill((0, 0, 0, 255))
        r = self.R(290, 250, 700, 220)
        panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=Y(12), edge=rgba((255, 255, 255)), edge_w=Y(3))
        pill = pygame.Rect(r.x + X(30), r.y + Y(14), r.w - X(60), Y(36))
        vgrad(c, pill, rgba(mix(b["later"], (255, 255, 255), 0.35)), rgba(b["later"]), radius=Y(10))
        f = self.fb(Y(22))
        self.cb(c, "ATTENTION", f, b["text"], pill.centerx, pill.y + (pill.h - t.ink(f)[1]) // 2, align="center")
        fl = self.fb(Y(19))
        self.cb(c, "Acquiring satellite signal.", fl, b["ink"], r.centerx, pill.bottom + Y(16), align="center")
        self.cb(c, "Please wait, or pick another channel.", fl, b["ink"], r.centerx, pill.bottom + Y(50), align="center")
        self._progress_bar(c, pygame.Rect(r.x + X(40), r.bottom - Y(50), r.w - X(80), Y(22)))

    def _progress_bar(self, c, bar):
        """The dialog's inset bar, its dark segments walking along."""
        b, X = self.b, self.X
        pygame.draw.rect(c, (255, 255, 255), bar)
        pygame.draw.rect(c, b["ink"], bar, 1)
        seg = max(4, X(12))
        n = (bar.w - X(8)) // (seg + X(3))
        lit = int(time.monotonic() * 4) % (n + 1)
        for i in range(lit):
            pygame.draw.rect(c, b["ink"], (bar.x + X(4) + i * (seg + X(3)), bar.y + 3, seg, bar.h - 6))

    # ── Guide ─────────────────────────────────────────────────────────────

    def draw_guide(self, c, g):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._page(c, (0, 0, W, Y(300)))
        self.wordmark(c, X(42), Y(52), Y(44), b["text"], b["dish"])
        self._tvguide(c, X(46), Y(150), X(109), Y(65))
        pic = self._picture(c)
        sel = g.selected()
        cur = self.app.live.programs(sel)[0] if sel else None
        f_title, f_small = self.fb(Y(37)), self.fb(Y(24))
        title = cur.title if cur else (sel.name if sel else "")
        cx = X(470)
        self.cb(c, self.fit_cb(f_title, title, X(600)), f_title, b["text"], cx, Y(62), align="center")
        if cur:
            blurb = (f"{cur.category}. " if cur.category else "") + (cur.description or "")
            y = Y(168)
            for line in t.wrap(f_small, blurb, int(X(600) / 0.86), 3):
                self.cb(c, line, f_small, b["text"], cx, y, align="center")
                y += Y(30)
        f_list = self.fb(Y(30))
        tab = pygame.Rect(X(96), Y(262), int(t.width(f_list, g.category) * 0.86) + X(16), Y(30))
        self.cb(c, g.category if g.category != "All" else "All Sub", f_list, b["gold"] if g.focus == "category" else b["text"],
                X(96), Y(268))
        self.hit(tab, lambda: g.handle("THEMES"))
        self.cb(c, when(), f_list, b["text"], X(453), Y(268))

        # The charcoal header and the rows.
        pygame.draw.rect(c, b["page_lo"], (0, Y(300), W, H - Y(300)))
        hdr = self.R(0, 300, 1280, 32)
        pygame.draw.rect(c, b["hdr"], hdr)
        start, end = g.window()
        fh = self.fb(Y(28))
        hy = hdr.y + (hdr.h - t.ink(fh)[1]) // 2
        day = start.astimezone()
        self.cb(c, f"{day:%a} {day:%b} {day.day}", fh, b["text"], X(34), hy)
        slots = int(g.hours * 2)
        cols = [X(251), X(605), X(961), X(1280)]
        for i in range(slots):
            self.cb(c, ampm(start + timedelta(minutes=30 * i)), fh, b["text"], (cols[i] + cols[i + 1]) // 2, hy, align="center")
        rows = g.filtered()[g.top: g.top + g.rows]
        mins = g.hours * 60
        now = datetime.now(timezone.utc)
        epg = self.app.epg
        f_cell, f_chan = self.fb(Y(27)), self.f(Y(27))
        grid_x, grid_w = X(255), X(1025)
        for i, ch in enumerate(rows):
            y = Y(328 + 53 * i)
            rh = Y(50)
            row_sel = g.focus == "grid" and g.top + i == g.cursor
            chr_ = pygame.Rect(0, y, X(247), rh)
            pygame.draw.rect(c, b["chan"], chr_)
            cy = y + (rh - t.ink(f_cell)[1]) // 2
            self.cb(c, self.fit_cb(f_chan, f"{ch.number} {ch.name.upper()}", X(220)), f_chan, b["text"], X(26), cy)
            if self.app.is_favorite(ch):
                pygame.draw.circle(c, b["gold"], (chr_.right - X(14), y + Y(12)), Y(5))
            cid = epg.resolve_channel_id(ch.epg_id, ch.name) if epg else None
            progs = epg.programs_in_window(cid, start, end) if cid else []
            if not progs:
                cell = pygame.Rect(grid_x, y, grid_w - X(8), rh)
                self._cell(c, cell, False, row_sel)
                self.cb(c, "No Information", f_cell, b["text"], cell.centerx, cy, align="center")
            for p in progs:
                a = max(0.0, (p.start - start).total_seconds() / 60)
                e = min(float(mins), (p.stop - start).total_seconds() / 60)
                if e <= a:
                    continue
                cell = pygame.Rect(grid_x + int(a / mins * grid_w), y, int((e - a) / mins * grid_w) - X(8), rh)
                airing = p.start <= now < p.stop
                on = row_sel and p.start <= max(now, start) < p.stop
                self._cell(c, cell, airing, on)
                x0 = cell.x + X(6)
                if p.start < start:
                    pygame.draw.polygon(c, b["text"], [(x0, cell.centery), (x0 + X(9), cell.centery - Y(9)),
                                                       (x0 + X(9), cell.centery + Y(9))])
                if p.stop > end:
                    pygame.draw.polygon(c, b["text"], [(cell.right - X(6), cell.centery), (cell.right - X(15), cell.centery - Y(9)),
                                                       (cell.right - X(15), cell.centery + Y(9))])
                if cell.w > X(40):
                    self.cb(c, self.fit_cb(f_cell, p.title, cell.w - X(36)), f_cell, b["text"], cell.centerx, cy, align="center")
            self.hit((0, y, W, rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                setattr(g, "focus", "grid"), g.handle("SELECT")))

    def _cell(self, c, cell, airing, on):
        b, Y = self.b, self.Y
        pygame.draw.rect(c, b["now"] if airing else b["later"], cell)
        pygame.draw.rect(c, b["gold"] if on else b["edge"], cell, Y(3) if on else 1)

    # ── Menus: the list page, in this world's colours ─────────────────────

    def menu_cols(self, menu):
        return 1

    def _menu_top(self, c, title):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._page(c, (0, 0, W, H))
        self.wordmark(c, X(42), Y(30), Y(36), b["text"], b["dish"])
        f = self.fb(Y(36))
        f.italic = True
        try:
            self.cb(c, self.fit_cb(f, title, X(600)), f, b["text"], X(230), Y(36))
        finally:
            f.italic = False
        local = datetime.now()
        self.cb(c, f"{local:%a}, {local:%B} {local.day}", self.fb(Y(22)), b["text"], X(1157), Y(46), align="right")

    def draw_menu(self, c, m):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._menu_top(c, m.title.title())
        frame = self.R(555, 120, 667, 556)
        pygame.draw.rect(c, b["pip"], frame, border_radius=Y(8))
        pygame.draw.rect(c, b["pip_edge"], frame, Y(3), border_radius=Y(8))
        vx, vy, vw, vh = self.menu_video_box(m)
        pygame.draw.rect(c, (0, 0, 0, 0), (vx, vy, vw, vh))
        live = self.app.live
        if live.channel:
            fc = self.fb(Y(22))
            self.cb(c, self.fit_cb(fc, f"{live.channel.number} {live.channel.name.upper()}", X(400)), fc, b["text"], X(597), Y(139))
            self.cb(c, ampm(datetime.now()), fc, b["text"], X(1178), Y(139), align="right")
            on = live.programs()[0]
            if on:
                self.cb(c, "Today", fc, b["text"], X(597), Y(560))
                self.cb(c, self.fit_cb(fc, f"{ampm(on.start)} - {ampm(on.stop)}  {on.title}", X(580)), fc, b["text"], X(597), Y(588))
        lp = self.R(51, 127, 493, 567)
        pygame.draw.rect(c, b["list_panel"], lp, border_radius=Y(14))
        pygame.draw.rect(c, (255, 255, 255), lp, Y(3), border_radius=Y(14))
        n = len(m.items)
        rh = Y(53)
        n_vis = max(1, (lp.h - Y(32)) // rh)
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        f_row = self.fb(Y(23))
        for k, i in enumerate(range(first, min(n, first + n_vis))):
            it = m.items[i]
            y = lp.y + Y(16) + k * rh
            sel = i == m.cursor
            row = pygame.Rect(X(83), y, X(380), Y(42))
            num = pygame.Rect(X(470), y, X(44), Y(42))
            fill, ink = (b["cursor"], b["cursor_ink"]) if sel else (b["row"], b["row_ink"])
            if not it.enabled:
                ink = mix(ink, fill, 0.5)
            for rr in (row, num):
                pygame.draw.rect(c, fill, rr, border_radius=Y(8))
                pygame.draw.rect(c, b["row_edge"], rr, Y(2), border_radius=Y(8))
            ty = row.y + (row.h - t.ink(f_row)[1]) // 2
            self.cb(c, self.fit_cb(f_row, it.label, row.w - (X(180) if it.value else X(50))), f_row, ink,
                    row.x + X(16), ty)
            if it.value:
                v = it.value()
                v = f"< {v} >" if sel and it.adjust else v
                self.cb(c, self.fit_cb(f_row, v, X(140)), f_row, ink, row.right - X(14), ty, align="right")
            elif it.submenu:
                self.cb(c, ">", f_row, ink, row.right - X(14), ty, align="right")
            if i < 9:
                self.cb(c, str(i + 1), f_row, ink, num.centerx, ty, align="center")
            self.hit(row, lambda i=i: m.activate(i))
        if n > n_vis:
            self.cb(c, f"{first + 1}-{min(n, first + n_vis)} of {n}", self.fb(Y(18)), b["ink"], lp.x + X(32), lp.bottom - Y(28))
        self.cb(c, "SELECT: choose   CANCEL: back   VIEW TV: close", self.fb(Y(18)), b["muted"], X(51), Y(694))

    def menu_video_box(self, menu):
        r = self.R(609, 181, 569, 354)
        return (r.x, r.y, r.w, r.h)

    # ── Boot ──────────────────────────────────────────────────────────────

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        stage = boot.stage()
        self._page(c, (0, 0, W, H))
        size = Y(72)
        mw = self.measure(self.wordmark, size, b["text"], b["dish"])
        self.wordmark(c, (W - mw) // 2, Y(150), size, b["text"], b["dish"])
        self._tvguide(c, W // 2 - X(40), Y(290), X(80), Y(66))
        caption = {"starting": "Starting up...", "signal": "Acquiring satellite signal.",
                   "guide": "Retrieving program information from satellite.", "done": "Ready"}[stage]
        r = self.R(290, 440, 700, 110)
        panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=Y(12), edge=rgba((255, 255, 255)), edge_w=Y(3))
        pill = pygame.Rect(r.x + X(30), r.y + Y(14), r.w - X(60), Y(36))
        vgrad(c, pill, rgba(mix(b["later"], (255, 255, 255), 0.35)), rgba(b["later"]), radius=Y(10))
        f = self.fb(Y(22))
        self.cb(c, "ATTENTION", f, b["text"], pill.centerx, pill.y + (pill.h - t.ink(f)[1]) // 2, align="center")
        self.cb(c, self.fit_cb(self.fb(Y(19)), caption, r.w - X(40)), self.fb(Y(19)), b["ink"], r.centerx, pill.bottom + Y(14),
                align="center")
        if stage != "starting":
            self.cb(c, "Please wait, or press any button to skip.", self.fb(Y(16)), b["soft"], W // 2, Y(600), align="center")


class Plate(PlateHD):
    """The SD era, after the 2005 guide and banner of the 322/522: a grey
    page with a big blue ellipse tab of pills, crescent channel cells, blue
    program cells with a pale selection; a banner of three dark capsules
    over the picture (date and clock, then the title over Time Left and
    List, then number and call sign); grey menus of blue pill rows. 640x480,
    geometry from the video's 4:3 frame (its 160..1120 x 0..720 mapped to
    640x480)."""
    name = "plate"
    label = "Plate Network"
    canvas = (640, 480)
    guide_rows = 4
    SD = True
    # Measured: the tab blue, the page grey, the pale selection, the pill
    # blue of the menus.
    NATIVE = {"bg": [43, 72, 157], "accent": [183, 183, 184], "accent2": [173, 200, 208],
              "text": [255, 255, 255], "chnum": [34, 46, 113]}

    def roles(self, b):
        r = super().roles(b)
        blue, grey, sel, text, pillb = b["bg"], b["accent"], b["accent2"], b["text"], b["chnum"]
        ink = mix(pillb, (0, 0, 0), 0.4)
        r.update(
            blue=blue, blue_hi=mix(blue, (255, 255, 255), 0.3), blue_lo=mix(blue, (0, 0, 0), 0.25),
            grey=grey, grey_hi=mix(grey, (255, 255, 255), 0.45), grey_lo=mix(grey, (0, 0, 0), 0.3),
            pillfill=mix(grey, (255, 255, 255), 0.75), hdr=(76, 78, 74),
            cell_ink=text, sel=sel, sel_ink=ink, ink=ink, text=text,
            chan_ink=ink, chan_fill=mix(grey, (255, 255, 255), 0.4),
            # The 2005 banner was lettered straight onto a dark translucent band.
            band=(0, 0, 0), band_ink=text, band_soft=mix(text, (120, 120, 120), 0.35), warn=(236, 196, 48),
            cursor=(250, 250, 252), cursor_ink=ink, row=pillb, row_hi=mix(pillb, (255, 255, 255), 0.35),
            row_ink=text, muted=mix(ink, grey, 0.4), list_panel=mix(grey, (255, 255, 255), 0.55),
            pill=pillb, pill_hi=mix(pillb, (255, 255, 255), 0.35), pill_ink=text,
            panel_top=(236, 236, 238), panel_bot=(176, 180, 192), dish=(210, 30, 40))
        return r

    # SD coordinates are the 4:3 frame's own 640x480.
    def X(self, v) -> int:
        return int(round(v * self.canvas[0] / 640))

    def Y(self, v) -> int:
        return int(round(v * self.canvas[1] / 480))

    # ── Shared: the grey page, the blue tab, the pills ────────────────────

    def _grey_page(self, c, rect):
        """The 2005 page: light grey with a faint swirl, darker to the foot."""
        rect = pygame.Rect(rect)
        b = self.b
        vgrad(c, rect, rgba(b["grey_hi"]), rgba(b["grey_lo"]))
        swirl = pygame.Surface(rect.size, pygame.SRCALPHA)
        for k in range(3):
            pygame.draw.ellipse(swirl, (255, 255, 255, 28), (-rect.w // 2 + k * rect.w // 5, rect.h // 4 + k * rect.h // 8,
                                                             rect.w, rect.h), max(2, rect.h // 40))
        c.blit(swirl, rect.topleft)

    def _tab(self, c, right):
        """The big blue tab: a wide ellipse running on behind the picture,
        the mark in its left end."""
        b, X, Y = self.b, self.X, self.Y
        tab = pygame.Surface((right, Y(236)), pygame.SRCALPHA)
        pygame.draw.ellipse(tab, b["blue"], (X(50), Y(8), X(600), Y(222)))
        c.blit(tab, (0, 0))
        # The mark fills the tab's end (x 62-156) without reaching the pills.
        size = Y(34)
        while size > 8 and self.measure(self.wordmark, size, b["text"], b["dish"]) > X(94):
            size -= 1
        w = self.measure(self.wordmark, size, b["text"], b["dish"])
        h = self.text.ink(self.fb(size))[1] + size // 12 + self.text.ink(self.f(max(8, size // 3)))[1]
        self.wordmark(c, X(62) + (X(94) - w) // 2, Y(111) - h // 2, size, b["text"], b["dish"])
        return X(166)

    def _pill(self, c, y, lines, right, cx, icon=None):
        """A white capsule-ended pill from x=166, running on behind the
        picture; its lines centred on `cx` as the box set them."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = pygame.Rect(X(166), Y(y), right - X(166), Y(42))
        pygame.draw.rect(c, b["pillfill"], r, border_top_left_radius=r.h // 2, border_bottom_left_radius=r.h // 2)
        f = self.fb(Y(17))
        pitch = Y(20)
        ty = r.y + (r.h - (len(lines) - 1) * pitch - t.ink(f)[1]) // 2
        for line in lines:
            t.draw(c, t.fit(f, line, (right - X(cx)) * 2 - X(8)), f, b["ink"], X(cx), ty, align="center")
            ty += pitch
        if icon == "lock":
            # The favourite list's padlock in a ring.
            ix, iy = X(188), r.centery
            pygame.draw.circle(c, b["ink"], (ix, iy), Y(13), max(2, Y(3)))
            body = pygame.Rect(0, 0, X(10), Y(8))
            body.midtop = (ix, iy - Y(1))
            pygame.draw.rect(c, b["ink"], body, border_radius=1)
            pygame.draw.arc(c, b["ink"], (ix - X(4), iy - Y(7), X(8), Y(10)), 0, 3.15, max(2, Y(2)))
        return r

    def guide_video_box(self):
        r = self.R(320, 0, 320, 236)
        return (r.x, r.y, r.w, r.h)

    def _signal_loss(self, c):
        """The ATTENTION dialog on black, as on the HD box, at the 4:3 size."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        c.fill((0, 0, 0, 255))
        r = self.R(100, 150, 440, 150)
        panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=Y(10), edge=rgba((255, 255, 255)), edge_w=Y(2))
        pill = pygame.Rect(r.x + X(20), r.y + Y(10), r.w - X(40), Y(28))
        vgrad(c, pill, rgba(b["pill_hi"]), rgba(b["pill"]), radius=Y(8))
        f = self.fb(Y(15))
        t.draw(c, "ATTENTION", f, b["pill_ink"], pill.centerx, pill.y + (pill.h - t.ink(f)[1]) // 2, align="center")
        fl = self.f(Y(13))
        t.draw(c, "Acquiring satellite signal.", fl, b["ink"], r.centerx, pill.bottom + Y(12), align="center")
        t.draw(c, "Please wait, or pick another channel.", fl, b["ink"], r.centerx, pill.bottom + Y(34), align="center")
        self._progress_bar(c, pygame.Rect(r.x + X(30), r.bottom - Y(34), r.w - X(60), Y(16)))

    # ── Guide: the 2005 page ──────────────────────────────────────────────

    def draw_guide(self, c, g):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._grey_page(c, (0, 0, W, Y(236)))
        vx, vy, vw, vh = self.guide_video_box()
        self._tab(c, vx)
        pygame.draw.rect(c, (0, 0, 0, 0), (vx, vy, vw, vh))
        local = datetime.now()
        self._pill(c, 37, [f"{local:%a} {local.month}/{local.day}", ampm(local).replace("am", " am").replace("pm", " pm")],
                   vx, 268)
        tab = self._pill(c, 100, ["Favorite List:", g.category if g.category != "All" else "All Sub"], vx, 258,
                         icon="lock")
        self.hit(tab, lambda: g.handle("THEMES"))
        sel = g.selected()
        self._pill(c, 160, [f"<  {sel.number if sel else '---'}  >"], vx, 205)

        # The header: day, a play arrow, the half hours between dividers.
        hdr = self.R(0, 233, 640, 26)
        pygame.draw.rect(c, b["hdr"], hdr)
        pygame.draw.rect(c, b["hdr"], self.R(597, 259, 43, 200))
        start, end = g.window()
        grid_x, grid_w = X(135), X(462)
        slots = int(g.hours * 2)
        col = grid_w / slots
        fh = self.fb(Y(18))
        hy = hdr.y + (hdr.h - t.ink(fh)[1]) // 2
        day = start.astimezone()
        t.draw(c, f"{day:%a} {day.month}/{day.day}", fh, b["text"], X(90), hy, align="center")
        ax = X(145)
        pygame.draw.polygon(c, b["text"], [(ax, hdr.y + Y(6)), (ax, hdr.bottom - Y(6)), (ax + X(7), hdr.centery)])
        rule = mix(b["hdr"], (0, 0, 0), 0.55)
        for i in range(slots):
            x = grid_x + int(col * i)
            if i:
                pygame.draw.rect(c, rule, (x - X(2), hdr.y + Y(2), X(2), hdr.h - Y(4)))
            t.draw(c, ampm(start + timedelta(minutes=30 * i)).replace("am", " am").replace("pm", " pm"), fh, b["text"],
                   x + int(col / 2), hy, align="center")
        pygame.draw.rect(c, (0, 0, 0), self.R(0, 259, 597, 200))

        rows = g.filtered()[g.top: g.top + g.rows]
        mins = g.hours * 60
        now = datetime.now(timezone.utc)
        epg = self.app.epg
        f_cell, f_tile = self.fb(Y(17)), self.fb(Y(17))
        for i, ch in enumerate(rows):
            y = Y(261 + 46.7 * i)
            rh = Y(42)
            row_sel = g.focus == "grid" and g.top + i == g.cursor
            self._chan_tile(c, pygame.Rect(0, y, X(131), rh), ch, f_tile)
            cid = epg.resolve_channel_id(ch.epg_id, ch.name) if epg else None
            progs = epg.programs_in_window(cid, start, end) if cid else []
            if not progs:
                cell = pygame.Rect(grid_x, y, grid_w - X(3), rh)
                self._cell(c, cell, row_sel)
                t.draw(c, "Info Not Available", f_cell, b["sel_ink"] if row_sel else b["cell_ink"], cell.centerx,
                       y + (rh - t.ink(f_cell)[1]) // 2, align="center")
            for p in progs:
                a = max(0.0, (p.start - start).total_seconds() / 60)
                e = min(float(mins), (p.stop - start).total_seconds() / 60)
                if e <= a:
                    continue
                cell = pygame.Rect(grid_x + int(a / mins * grid_w), y, int((e - a) / mins * grid_w) - X(3), rh)
                on = row_sel and p.start <= max(now, start) < p.stop
                self._cell(c, cell, on)
                ink = b["sel_ink"] if on else b["cell_ink"]
                mark = b["sel_ink"] if on else mix(b["text"], b["blue"], 0.12)
                inset_l = inset_r = X(10)
                if p.start < start:
                    self._crescent(c, cell, mark, left=True)
                    inset_l = X(18)
                if p.stop > end:
                    self._crescent(c, cell, mark, left=False)
                    inset_r = X(18)
                if cell.w > X(30):
                    lines = t.wrap(f_cell, p.title, cell.w - inset_l - inset_r, 2)
                    pitch = Y(17)
                    ty = y + (rh - (len(lines) - 1) * pitch - t.ink(f_cell)[1]) // 2
                    cx = cell.x + inset_l + (cell.w - inset_l - inset_r) // 2
                    for line in lines:
                        t.draw(c, line, f_cell, ink, cx, ty, align="center")
                        ty += pitch
            self.hit((0, y, X(597), rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                     setattr(g, "focus", "grid"), g.handle("SELECT")))
        pygame.draw.rect(c, b["grey_hi"], self.R(0, 452, 640, 28))

    def _chan_tile(self, c, tile, ch, f):
        """A channel tile: light grey, the blue crescent inside its left half
        (never past its edges), the number over the call sign."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        surf = pygame.Surface(tile.size, pygame.SRCALPHA)
        vgrad(surf, surf.get_rect(), rgba(mix(b["chan_fill"], (255, 255, 255), 0.35)), rgba(b["chan_fill"]))
        outer = pygame.Rect(X(37), -Y(3), X(86), tile.h + Y(6))
        pygame.draw.ellipse(surf, b["blue"], outer)
        inner = outer.move(X(10), 0)
        clip = pygame.Surface(tile.size, pygame.SRCALPHA)
        vgrad(clip, clip.get_rect(), rgba(mix(b["chan_fill"], (255, 255, 255), 0.35)), rgba(b["chan_fill"]))
        mask = pygame.Surface(tile.size, pygame.SRCALPHA)
        pygame.draw.ellipse(mask, (255, 255, 255, 255), inner)
        clip.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        surf.blit(clip, (0, 0))
        pygame.draw.rect(surf, mix(b["chan_fill"], (0, 0, 0), 0.25), (0, tile.h - Y(2), tile.w, Y(2)))
        c.blit(surf, tile.topleft)
        cx = X(102)
        t.draw(c, str(ch.number), f, b["chan_ink"], cx, tile.y + Y(6), align="center")
        call = dish_call(ch)
        while len(call) > 1 and t.width(f, call) > X(58):      # call signs clip, no ellipsis
            call = call[:-1]
        t.draw(c, call, f, b["chan_ink"], cx, tile.y + Y(21), align="center")

    def _crescent(self, c, cell, ink, left=True):
        """The tall thin '(' or ')' the box drew where a programme runs on
        past the grid's edge."""
        X, Y = self.X, self.Y
        w = X(16)
        surf = pygame.Surface((w, cell.h), pygame.SRCALPHA)
        outer = pygame.Rect(X(2), -Y(2), w * 2, cell.h + Y(4))
        pygame.draw.ellipse(surf, ink, outer)
        pygame.draw.ellipse(surf, (0, 0, 0, 0), outer.move(X(6), 0))
        if not left:
            surf = pygame.transform.flip(surf, True, False)
        c.blit(surf, (cell.x if left else cell.right - w, cell.y))

    def _cell(self, c, cell, on):
        b, Y = self.b, self.Y
        if on:
            pygame.draw.rect(c, b["sel"], cell)
        else:
            pygame.draw.rect(c, b["blue"], cell)
            pygame.draw.rect(c, b["blue_hi"], (cell.x, cell.y, cell.w, Y(2)))
            pygame.draw.rect(c, b["blue_lo"], (cell.x, cell.bottom - Y(2), cell.w, Y(2)))

    # ── Live: the 2005 banner ─────────────────────────────────────────────

    def _band(self, c, r, alpha=140):
        """A dark translucent capsule, as the box laid its banner and bars
        over the picture."""
        band = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(band, (0, 0, 0, alpha), band.get_rect(), border_radius=self.Y(10))
        c.blit(band, r.topleft)

    def _banner(self, c, ch, cur, nxt, full=False, tag=None, bottom=False):
        """Three capsules, as the 2005 box drew its banner (2:32 in the
        reference): date and clock in the short left one; the title over Time
        Left and List in the long middle one; number over call sign in the
        short right one. BROWSE puts the same three along the bottom."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        top, h = Y(46), Y(87)
        if bottom:
            top = H - Y(46) - h
        left = pygame.Rect(X(55), top, X(88), h)
        mid = pygame.Rect(X(147), top, X(333), h)
        right = pygame.Rect(X(484), top, X(96), h)
        for r in (left, mid, right):
            self._band(c, r)
        if tag:
            f_tag = self.fb(Y(11))
            th = t.ink(f_tag)[1] + 16                   # chip() pads 8 all round
            self.chip(c, mid.x, mid.y - th - Y(4) if bottom else mid.bottom + Y(4), tag, f_tag,
                      rgba(b["sel"]), b["ink"])
        ink = b["band_ink"]
        local = datetime.now()
        f_date, f_title, f_chan, f_line = self.fb(Y(18)), self.fb(Y(22)), self.fb(Y(21)), self.fb(Y(17))
        t.draw(c, f"{local:%a} {local.month}/{local.day}", f_date, ink, left.centerx, top + Y(24), align="center")
        t.draw(c, ampm(local).replace("am", " am").replace("pm", " pm"), f_date, ink, left.centerx, top + Y(51),
               align="center")
        t.draw(c, t.fit(f_title, cur.title if cur else ch.name, mid.w - X(20)), f_title, ink, X(318), top + Y(3),
               align="center")
        if cur:
            t.draw(c, time_left(cur, datetime.now(timezone.utc)), f_line, ink, X(160), top + Y(71))
        t.draw(c, f"List: {g_list(self)}", f_line, ink, X(376), top + Y(71))
        t.draw(c, str(ch.number), f_chan, ink, right.centerx, top + Y(21), align="center")
        call = dish_call(ch)
        while len(call) > 1 and t.width(f_chan, call) > right.w - X(10):     # call signs clip, no ellipsis
            call = call[:-1]
        t.draw(c, call, f_chan, ink, right.centerx, top + Y(49), align="center")
        if full and cur and cur.description:
            f = self.f(Y(13))
            lines = t.wrap(f, cur.description, right.right - left.x - X(40), 3)
            d = pygame.Rect(left.x, 0, right.right - left.x, Y(12) + len(lines) * Y(17))
            d.y = top - d.h - Y(4) if bottom else top + h + Y(4)
            self._band(c, d)
            y = d.y + Y(6)
            for line in lines:
                t.draw(c, line, f, ink, d.x + X(20), y)
                y += Y(17)
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def _digits(self, c, digits):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(40, 40, 200, 50)
        self._band(c, r)
        f = self.fb(Y(26))
        t.draw(c, digits + "-" * (3 - len(digits)), f, b["band_ink"], r.centerx, r.y + (r.h - t.ink(f)[1]) // 2,
               align="center")

    def _volume(self, c, cx, cy):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        v = self.app.video
        r = self.R(40, 40, 260, 36)
        self._band(c, r)
        f = self.fb(Y(14))
        t.draw(c, "Mute" if v.muted else "Volume", f, b["warn"] if v.muted else b["band_ink"], r.x + X(14),
               r.y + (r.h - t.ink(f)[1]) // 2)
        bar = pygame.Rect(r.x + X(90), r.y + Y(12), X(155), Y(12))
        pygame.draw.rect(c, (60, 60, 60), bar)
        if not v.muted:
            pygame.draw.rect(c, b["sel"], (bar.x, bar.y, int(bar.w * v.volume / 100), bar.h))

    def _trick(self, c, s):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(40, 404, 560, 36)
        self._band(c, r)
        behind = s["behind"]
        mm, ss = divmod(int(behind), 60)
        f = self.fb(Y(14))
        tag = "Paused" if s["paused"] else ("Live TV" if behind < 2 else "Playing")
        t.draw(c, tag, f, b["band_ink"], r.x + X(14), r.y + (r.h - t.ink(f)[1]) // 2)
        bar = pygame.Rect(r.x + X(110), r.y + Y(12), X(340), Y(12))
        pygame.draw.rect(c, (60, 60, 60), bar)
        span = s["buffer"] + behind
        if span >= 2:
            x = bar.x + int(bar.w * s["buffer"] / span)
            pygame.draw.rect(c, b["sel"], (bar.x, bar.y, x - bar.x, bar.h))
            pygame.draw.rect(c, b["text"], (x - X(1), bar.y - Y(4), X(3), bar.h + Y(8)))
        t.draw(c, f"-{mm}:{ss:02d}" if behind >= 1 else "Live", f, b["band_ink"], r.right - X(14),
               r.y + (r.h - t.ink(f)[1]) // 2, align="right")

    # ── Menus: the 2005 Theme Categories page ─────────────────────────────

    def menu_cols(self, menu):
        return 2 if menu.title == "MAIN MENU" and len(menu.pages) == 1 else 1

    def menu_video_box(self, menu):
        return "hidden"

    def draw_menu(self, c, m):
        """A grey page, the mark top-left, the title in a pill at the right,
        two columns of numbered blue pills (one for a long list), the chosen
        one white."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._grey_page(c, (0, 0, W, H))
        self.wordmark(c, X(60), Y(36), Y(44), b["ink"], b["dish"])
        f_title = self.fb(Y(27))
        title = "Main Menu" if m.title == "MAIN MENU" else m.title.title()
        tp = pygame.Rect(X(300), Y(58), X(340), Y(44))
        pygame.draw.rect(c, mix(b["grey_lo"], (0, 0, 0), 0.3), tp.move(0, Y(3)), border_top_left_radius=tp.h // 2,
                         border_bottom_left_radius=tp.h // 2)
        pygame.draw.rect(c, b["grey_hi"], tp, border_top_left_radius=tp.h // 2, border_bottom_left_radius=tp.h // 2)
        t.draw(c, t.fit(f_title, title, tp.w - X(40)), f_title, b["ink"], tp.x + X(15), tp.y + (tp.h - t.ink(f_title)[1]) // 2)
        n = len(m.items)
        cols = self.menu_cols(m)
        rh = Y(40)
        per_col = 5 if cols == 2 else max(1, (Y(430) - Y(165)) // rh)
        n_vis = per_col * cols
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        f_row = self.fb(Y(20))
        band = self.R(0, 160, 640, 270 if cols == 2 else per_col * rh + Y(20))
        pygame.draw.rect(c, b["grey_lo"], band)
        if cols == 2:
            pygame.draw.rect(c, mix(b["grey_lo"], (0, 0, 0), 0.5), (X(319), band.y, X(2), band.h))
        col_w = X(280) if cols == 2 else X(540)
        for k, i in enumerate(range(first, min(n, first + n_vis))):
            it = m.items[i]
            col, row_i = (k // per_col, k % per_col) if cols == 2 else (0, k)
            x = X(50) + col * X(280)
            y = band.y + Y(8) + row_i * rh
            sel = i == m.cursor
            row = pygame.Rect(x, y, col_w - X(10), Y(32))
            fill, ink = (b["cursor"], b["cursor_ink"]) if sel else (b["row"], b["row_ink"])
            if not it.enabled:
                ink = mix(ink, fill, 0.5)
            pygame.draw.rect(c, fill, row, border_radius=row.h // 2)
            if not sel:
                pygame.draw.rect(c, b["row_hi"], (row.x + row.h // 2, row.y + Y(2), row.w - row.h, Y(3)), border_radius=2)
            ty = row.y + (row.h - t.ink(f_row)[1]) // 2
            num = str((i + 1) % 10) if i < 10 else ""
            label = f"{num} {it.label}".strip()
            t.draw(c, t.fit(f_row, label, row.w - (X(165) if it.value else X(50))), f_row, ink, row.x + X(28), ty)
            if it.value:
                v = it.value()
                v = f"< {v} >" if sel and it.adjust else v
                t.draw(c, t.fit(f_row, v, X(120)), f_row, ink, row.right - X(22), ty, align="right")
            elif it.submenu:
                t.draw(c, ">", f_row, ink, row.right - X(22), ty, align="right")
            self.hit(row, lambda i=i: m.activate(i))
        if n > n_vis:
            t.draw(c, f"{first + 1}-{min(n, first + n_vis)} of {n}", self.f(Y(11)), b["ink"], X(40), band.bottom + Y(6))
        t.draw(c, "SELECT: choose   CANCEL: back   VIEW TV: close", self.f(Y(11)), b["ink"], X(40), Y(456))

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        stage = boot.stage()
        self._grey_page(c, (0, 0, W, H))
        tab = pygame.Surface((W, Y(236)), pygame.SRCALPHA)
        pygame.draw.ellipse(tab, b["blue"], (X(58), Y(17), X(420), Y(197)))
        c.blit(tab, (0, 0))
        size = Y(44)
        mw = self.measure(self.wordmark, size, b["text"], b["dish"])
        self.wordmark(c, (W - mw) // 2, Y(80), size, b["text"], b["dish"])
        caption = {"starting": "Starting up...", "signal": "Acquiring Satellite Signal",
                   "guide": "Retrieving program information from satellite.", "done": "Ready"}[stage]
        r = self.R(100, 280, 440, 90)
        panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=Y(10), edge=rgba((255, 255, 255)), edge_w=Y(2))
        pill = pygame.Rect(r.x + X(20), r.y + Y(10), r.w - X(40), Y(28))
        vgrad(c, pill, rgba(b["pill_hi"]), rgba(b["pill"]), radius=Y(8))
        f = self.fb(Y(15))
        t.draw(c, "ATTENTION", f, b["pill_ink"], pill.centerx, pill.y + (pill.h - t.ink(f)[1]) // 2, align="center")
        t.draw(c, t.fit(self.f(Y(13)), caption, r.w - X(30)), self.f(Y(13)), b["ink"], r.centerx, pill.bottom + Y(10),
               align="center")
        if stage != "starting":
            t.draw(c, "Please wait, or press any button to skip.", self.f(Y(11)), b["ink"], r.centerx, r.bottom - Y(22),
                   align="center")


def dish_call(ch) -> str:
    """The 2005 box's call sign: spaces dropped, cut at five letters, as it
    showed HISTI and BIOGR."""
    return "".join(ch.name.upper().split())[:5]


def g_list(skin) -> str:
    """The guide's current list name, for the banner's 'List:' slot."""
    from ..screens.guide import Guide
    g = skin.app.find(Guide) if hasattr(skin.app, "find") else None
    return (g.category if g and g.category != "All" else "All Sub")
