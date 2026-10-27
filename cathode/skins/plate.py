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

from .box import BoxSkin, call_sign, mix, nice, panel, readable, rgba, vgrad


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
    tune_black = 1.0                # the ViP's black on a change, about a second
    label = "Plate Network HD"
    canvas = (1280, 720)
    right_is_browse = True
    guide_hours = 1.5               # three half-hour columns, as the box showed
    SD = False
    TALL = ("guide", "screensaver", "ondemand")

    @property
    def guide_rows(self):
        return 7 + self.grow // self.Y(53)          # a taller screen lists more channels
    # Measured: the page teal, the on-now cell teal, the later-cell navy, the
    # gold of the selection frame.
    NATIVE = {"bg": [0, 51, 66], "accent": [0, 62, 61], "accent2": [0, 17, 55],
              "text": [255, 255, 255], "chnum": [230, 235, 134]}
    LEGIBLE = [("text", ["page", "page_lo", "page_hi", "vp_top", "vp_mid", "vp_bot", "now", "later", "row",
                         "vp_row", "vp_green", "vp_green2", "vp_info", "pill", "vp_btn", "chan", "list_panel"],
                "ground"),
               ("soft", ["page", "page_lo"], "ink"), ("muted", ["page", "page_lo"], "ink"),
               ("vp_dim", ["page", "vp_bot"], "ink"), ("cursor_ink", ["cursor"], "ink")]

    def theme_base(self, base):
        bg, acc = base["bg"], base["accent"]
        # On-now and later cells as darks of the accent; the gold cursor is
        # the theme's own highlight.
        return dict(base, accent=mix(acc, bg, 0.7), accent2=mix(acc, bg, 0.85), chnum=base["accent2"])

    def roles(self, b):
        page, now_, later, text, gold = b["bg"], b["accent"], b["accent2"], b["text"], b["chnum"]

        return {
            "page": page, "page_hi": mix(page, (40, 120, 130), 0.35), "page_lo": mix(page, (0, 0, 0), 0.3),
            "now": now_, "later": later, "edge": mix(later, (120, 160, 200), 0.3),
            "chan": (58, 54, 66), "hdr": (10, 18, 30), "gold": gold, "text": text,
            "soft": mix(text, page, 0.3), "muted": mix(text, page, 0.5),
            "banner": (34, 35, 33), "banner_ink": text, "pill": (84, 84, 86), "pill_ink": text,
            "tag": (200, 30, 40), "dish": (210, 30, 40),
            "row": mix(page, (40, 120, 130), 0.5), "row_ink": text, "row_edge": mix(page, (0, 0, 0), 0.3),
            "cursor": gold, "cursor_ink": readable(gold, mix(later, (0, 0, 0), 0.3)), "pip": (0, 0, 0),
            "pip_edge": mix(page, (120, 170, 180), 0.5),
            "sel": gold, "sel_ink": readable(gold, mix(later, (0, 0, 0), 0.3)), "deep": mix(page, (0, 0, 0), 0.4),
            # Panels, dialogs and the pages' parts, in the guide's colours.
            "list_panel": (58, 54, 66), "panel_top": (58, 54, 66), "panel_bot": (10, 18, 30), "ink": text,
            "pb_track": (84, 84, 86), "pb_edge": (10, 18, 30), "pb_fill": gold,
            "vp_top": mix(page, (40, 120, 130), 0.35), "vp_mid": page, "vp_bot": mix(page, (0, 0, 0), 0.3),
            "vp_hdr": mix(mix(page, (40, 120, 130), 0.35), text, 0.15),
            "vp_panel": (58, 54, 66), "vp_panel_edge": mix(page, (120, 170, 180), 0.5),
            "vp_row": later, "vp_row_edge": mix(later, (120, 160, 200), 0.3), "vp_ink": text,
            "vp_amber": gold, "vp_amber_edge": mix(gold, (0, 0, 0), 0.3), "vp_btn": (84, 84, 86),
            "vp_btn_edge": (40, 40, 42), "vp_info": later, "vp_green": now_, "vp_green2": mix(now_, later, 0.35),
            "vp_orange": (200, 30, 40), "vp_dim": mix(text, page, 0.5), "vp_field": (10, 18, 30),
        }

    def X(self, v) -> int:
        return int(round(v * self.canvas[0] / 1280))

    def Y(self, v) -> int:
        return int(round(v * type(self).canvas[1] / 720))     # design rows: a grown canvas adds rows, not size

    def R(self, x, y, w, h) -> pygame.Rect:
        return pygame.Rect(self.X(x), self.Y(y), self.X(w), self.Y(h))

    def u(self, v) -> int:
        return self.Y(v)

    # ── Lettering: the box used a condensed bold sans ─────────────────────

    def cb(self, c, s, f, ink, x, y, align="left", squeeze=0.86) -> int:
        """Bold text squeezed to the box's condensed width; returns its width."""
        if not s:
            return 0
        img, extra = self.text.render(f, s, ink[:3])
        w, h = img.get_size()
        img = pygame.transform.smoothscale(img, (max(1, int(w * squeeze)), h))
        w = img.get_width()
        x = x - w if align == "right" else x - w // 2 if align == "center" else x
        c.blit(img, (x, y - self.text.ink(f)[0] - extra))
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

    # ── Pages ─────────────────────────────────────────────────────────────

    def _page(self, c, rect):
        """The teal page, lighter at the top, with the box's faint swirls."""
        if self.hold_backdrop(rect, self._page):
            return
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
        r = self.R(774, 16, 480, 270)       # inside the area a TV shows
        return (r.x, r.y, r.w, r.h)

    def _picture(self, c):
        vx, vy, vw, vh = self.guide_video_box()
        self.hole(c, (vx, vy, vw, vh))
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
        # The ViP622 manual's banner (p.37): the day and clock in the left
        # cell; the title, its hours and the channel in the middle; the
        # rating, time left and the list at the right.
        f_big, f_mid, f_small = self.fb(Y(34)), self.fb(Y(28)), self.fb(Y(24))
        local, now = datetime.now(), datetime.now(timezone.utc)
        cx = r.x + X(123)
        self.cb(c, f"{local:%a} {local.month}/{local.day}".upper(), f_mid, ink, cx, r.y + Y(22), align="center")
        self.cb(c, ampm(local).replace("am", " am").replace("pm", " pm"), f_mid, ink, cx, r.y + Y(56), align="center")
        mid = r.x + X(607)
        self.cb(c, self.fit_cb(f_big, cur.title if cur else ch.name, X(560)), f_big, ink, mid, r.y + Y(8), align="center")
        if cur:
            self.cb(c, f"{ampm(cur.start)} - {ampm(cur.stop)}", f_small, ink, mid, r.y + Y(44), align="center")
        self.cb(c, self.fit_cb(f_small, f"{ch.number} {ch.name.upper()}", X(400)), f_small, ink, mid, r.y + Y(72),
                align="center")
        rx = r.right - X(20)
        self.cb(c, (cur.rating if cur and cur.rating else "NR"), f_small, ink, rx, r.y + Y(10), align="right")
        if cur:
            self.cb(c, time_left(cur, now).replace("Time left", "Time Left:"), f_small, ink, rx, r.y + Y(40), align="right")
        self.cb(c, self.fit_cb(f_small, f"List: {g_list(self)}", X(220)), f_small, ink, rx, r.y + Y(70), align="right")
        if nxt and full:                # the Browse Banner had "Next:"; the full banner carries it too
            fn = self.fb(Y(20))
            self.cb(c, self.fit_cb(fn, f"Next: {nxt.title}", X(420)), fn, b["soft"], mid, r.y + Y(100), align="center")
        label = tag or (f"{self.k('INFO')} FOR DETAILS" if not full else "")
        if label:
            pr = pygame.Rect(r.x + X(17), r.y - Y(34) if bottom else r.bottom + Y(10), 0, Y(34))
            fp = self.fb(Y(28))
            pr.w = int(t.width(fp, label) * 0.86) + X(40)
            pygame.draw.rect(c, b["pill"], pr, border_radius=Y(6))
            self.cb(c, label, fp, b["pill_ink"], pr.x + X(18), pr.y + Y(5))
        if full and cur and cur.description:
            f = self.fb(Y(18))
            lines = t.wrap(f, cur.description, int((r.w - X(40)) / 0.86), 3)
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
            tag = f"BROWSE  -  {self.k('SELECT')} TO WATCH" + (f"  (+{br.ahead})" if br.ahead else "")
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

    def _tbtn(self, c, r, kind, on, num=None):
        """A playback button: the dialogs' white capsule, amber when chosen."""
        b = self.b
        self._vip_button(c, r, "", on)
        self.transport_face(c, kind, r, b["sel_ink"] if on else b["vp_ink"], self.fb(self.Y(20)), num=num)

    def _trick(self, c, s):
        b, X, Y = self.b, self.X, self.Y
        r = self.R(40, 620, 1200, 56)
        self.live_buttons(c, s, r.x + X(10), r.y - Y(58), X(150), Y(42), X(20))
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

    def _note(self, c, text, frac=None):
        """A short notice in the banner's grey box, bottom left; a gold bar
        under the text when frac is a known fraction."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        bar = frac is not None and frac >= 0
        f = self.fb(Y(26))
        r = self.R(40, 0, 0, 0)
        r.w = max(int(t.width(f, text) * 0.86) + X(48), X(560) if bar else 0)
        r.h = Y(80 if bar else 56)
        r.bottom = Y(590)                  # above the subtitle line
        self._box(c, r)
        self.cb(c, text, f, b["banner_ink"], r.x + X(24), r.y + Y(16))
        if bar:
            track = pygame.Rect(r.x + X(24), r.bottom - Y(26), r.w - X(48), Y(12))
            pygame.draw.rect(c, b["pill"], track, border_radius=Y(6))
            pygame.draw.rect(c, b["gold"], (track.x, track.y, max(track.h, int(track.w * frac)), track.h),
                             border_radius=Y(6))

    def draw_note(self, c, text):
        self._note(c, text)

    def draw_guide_progress(self, c, frac):
        self._note(c, "Retrieving program information" + self.pct(frac), frac)

    def _signal_loss(self, c):
        """Dish's ATTENTION dialog on black, with its progress bar (the
        frame at 0:16), while the channel sends nothing."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        c.fill((0, 0, 0, 255))
        r = self.R(290, 250, 700, 220)
        panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=Y(12), edge=rgba(b["pip_edge"]), edge_w=Y(3))
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
        pygame.draw.rect(c, b["pb_track"], bar)
        pygame.draw.rect(c, b["pb_edge"], bar, 1)
        seg = max(4, X(12))
        n = (bar.w - X(8)) // (seg + X(3))
        lit = int(time.monotonic() * 4) % (n + 1)
        self._next_frame(0.25 - time.monotonic() % 0.25 + 0.005)     # it walks: draw it again
        for i in range(lit):
            pygame.draw.rect(c, b["pb_fill"], (bar.x + X(4) + i * (seg + X(3)), bar.y + 3, seg, bar.h - 6))

    # ── Guide ─────────────────────────────────────────────────────────────

    def draw_guide(self, c, g):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._page(c, (0, 0, W, Y(300)))
        self.wordmark(c, X(42), Y(52), Y(44), b["text"], b["dish"])
        pic = self._picture(c)
        sel = g.selected()
        cur = g.selected_program()
        f_title, f_info, f_small = self.fb(Y(37)), self.fb(Y(22)), self.fb(Y(24))
        title = cur.title if cur else (sel.name if sel else "")
        # The title, a line of when / rating / genre under it, then the
        # synopsis in even lines: one block, clear of the logo at the left.
        # With a poster (Tunarr's guide carries one) the block narrows and
        # sits to its right.
        art = self.logo(cur.icon, X(110), Y(165)) if cur and cur.icon else None
        cx, wide = X(470), X(600)
        if art:
            c.blit(art, (X(205), Y(40)))
            cx, wide = X(500), X(440)
        self.cb(c, self.fit_cb(f_title, title, wide), f_title, b["text"], cx, Y(44), align="center")
        logo = self.channel_logo(sel, X(150), Y(74))
        if logo:                            # where the box carried its guide tag
            c.blit(logo, logo.get_rect(midleft=(X(46), Y(182))))
        if cur:
            info = "   ".join(s for s in (f"{ampm(cur.start)} - {ampm(cur.stop)}", cur.rating, cur.category) if s)
            self.cb(c, self.fit_cb(f_info, info, wide - X(40)), f_info, b["soft"], cx, Y(92), align="center")
            y = Y(132)
            for line in t.wrap_even(f_small, cur.description or "", int((wide - X(80)) / 0.86), 3):
                self.cb(c, line, f_small, b["text"], cx, y, align="center")
                y += Y(30)
        f_list = self.fb(Y(30))
        name = g.category if g.category != "All" else "All Sub"
        if g.focus == "category":           # the guide's gold frame, as on a chosen cell
            name = f"<  {name}  >"
        tab = pygame.Rect(X(96), Y(262), int(t.width(f_list, name) * 0.86) + X(16), Y(30))
        if g.focus == "category":
            pygame.draw.rect(c, b["gold"], tab.inflate(X(14), Y(10)).move(-X(4), Y(2)), Y(3), border_radius=Y(4))
        self.cb(c, name, f_list, b["gold"] if g.focus == "category" else b["text"], X(96), Y(268))
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
        self.cb(c, f"{day:%a} {day:%b} {day.day}", fh, b["text"], X(64), hy)
        slots = int(g.hours * 2)
        cols = [X(251), X(605), X(961), X(1280)]
        for i in range(slots):
            self.cb(c, ampm(start + timedelta(minutes=30 * i)), fh, b["text"], (cols[i] + cols[i + 1]) // 2, hy, align="center")
        rows = g.filtered()[g.top: g.top + g.rows]
        mins = g.hours * 60
        now = datetime.now(timezone.utc)
        epg = self.app.epg
        f_cell, f_chan = self.fb(Y(27)), self.f(Y(24))
        grid_x, grid_w = X(255), X(1025)
        sel = g.sel_time()
        for i, ch in enumerate(rows):
            y = Y(328 + 53 * i)
            rh = Y(50)
            row_sel = g.focus == "grid" and g.top + i == g.cursor
            chr_ = pygame.Rect(0, y, X(247), rh)
            pygame.draw.rect(c, b["chan"], chr_)
            cy = y + (rh - t.ink(f_cell)[1]) // 2
            self.cb(c, self.fit_cb(f_chan, f"{ch.number} {ch.name.upper()}", X(176)), f_chan, b["text"], X(64), cy)
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
                on = row_sel and p.start <= sel < p.stop
                self._cell(c, cell, airing, on)
                x0 = cell.x + X(6)
                if p.start < start:
                    pygame.draw.polygon(c, b["text"], [(x0, cell.centery), (x0 + X(9), cell.centery - Y(9)),
                                                       (x0 + X(9), cell.centery + Y(9))])
                if p.stop > end:
                    pygame.draw.polygon(c, b["text"], [(cell.right - X(6), cell.centery), (cell.right - X(15), cell.centery - Y(9)),
                                                       (cell.right - X(15), cell.centery + Y(9))])
                right = min(cell.right, X(1216))         # the lettering stays inside the title-safe area
                if right - cell.x > X(40):
                    self.cb(c, self.fit_cb(f_cell, p.title, right - cell.x - X(36)), f_cell, b["text"],
                            (cell.x + right) // 2, cy, align="center")
            self.hit((0, y, W, rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                setattr(g, "focus", "grid"), g.handle("SELECT")))
        foot = Y(328) + g.rows * Y(53)            # the band under the last row: the keys
        fk = self.fb(Y(18))                        # the band the box's seven rows leave: as big as fits
        if H - foot >= t.ink(fk)[1] + Y(4):
            self.cb(c, self.guide_keys(), fk, b["soft"], W // 2, foot + (H - foot - t.ink(fk)[1]) // 2, align="center")
        if not rows:
            cell = self.R(0, 328, 1272, 50)
            self._cell(c, cell, False, False)
            self.cb(c, self.fit_cb(f_cell, self.empty_guide(g), cell.w - X(40)), f_cell, b["text"], cell.centerx,
                    cell.y + (cell.h - t.ink(f_cell)[1]) // 2, align="center")

    def _cell(self, c, cell, airing, on):
        b, Y = self.b, self.Y
        pygame.draw.rect(c, b["now"] if airing else b["later"], cell)
        if on:
            pygame.draw.rect(c, b["gold"], cell, Y(5))
            pygame.draw.rect(c, mix(b["gold"], (255, 255, 255), 0.55), cell.inflate(-Y(10), -Y(10)), 1)
        else:
            pygame.draw.rect(c, b["edge"], cell, 1)

    # ── Menus: the list page, in this world's colours ─────────────────────

    def menu_cols(self, menu):
        return 1

    def guide_keys(self) -> str:
        """The guide's keys, for the strip at its foot."""
        def k(action, plain):           # the remote's name for it, else the button's own
            name = self.k(action)
            return plain if name == action else name
        return (f"{k('CH_UP', 'CH+')}/{k('CH_DOWN', 'CH-')}: page   {k('REW', 'REW')}/{k('FF', 'FF')}: a day   "
                f"{k('THEMES', 'THEMES')}: other lists")

    def _menu_top(self, c, title):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._page(c, (0, 0, W, H))
        self.wordmark(c, X(64), Y(36), Y(36), b["text"], b["dish"])
        f = self.fb(Y(36))
        f.italic = True
        try:
            self.cb(c, self.fit_cb(f, title, X(600)), f, b["text"], X(250), Y(38))
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
        self.hole(c, (vx, vy, vw, vh))
        if not getattr(self.app, "channels", None):     # nothing playing yet: the mark, not black
            size = Y(64)
            mw = self.measure(self.wordmark, size, b["text"], b["dish"])
            self.wordmark(c, vx + (vw - mw) // 2, vy + vh // 2 - size, size, b["text"], b["dish"])
        live = self.app.live
        if live.channel:
            fc = self.fb(Y(22))
            self.cb(c, self.fit_cb(fc, f"{live.channel.number} {live.channel.name.upper()}", X(400)), fc, b["text"], X(597), Y(139))
            self.cb(c, ampm(datetime.now()), fc, b["text"], X(1178), Y(139), align="right")
            on = live.programs()[0]
            if on:
                self.cb(c, "Today", fc, b["text"], X(597), Y(560))
                self.cb(c, self.fit_cb(fc, f"{ampm(on.start)} - {ampm(on.stop)}  {on.title}", X(580)), fc, b["text"], X(597), Y(588))
        it = m.items[m.cursor] if 0 <= m.cursor < len(m.items) else None
        if it and it.help:
            fa = self.fb(Y(20))
            for k, line in enumerate(t.wrap(fa, it.help, int(X(570) / 0.86), 2)):
                self.cb(c, line, fa, b["soft"], X(597), Y(622) + k * Y(26))
        lp = self.R(64, 127, 480, 515)
        pygame.draw.rect(c, b["list_panel"], lp, border_radius=Y(14))
        pygame.draw.rect(c, b["pip_edge"], lp, Y(3), border_radius=Y(14))
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
            lw = self.cb(c, self.fit_cb(f_row, it.label, row.w - (X(180) if it.value else X(50))), f_row, ink,
                         row.x + X(16), ty)
            if it.value:
                v = it.value()
                v = f"< {v} >" if sel and it.adjust else v
                self.cb(c, self.fit_cb(f_row, v, row.w - lw - X(48)), f_row, ink, row.right - X(14), ty, align="right")
            elif it.submenu:
                self.cb(c, ">", f_row, ink, row.right - X(14), ty, align="right")
            if i < 9:
                self.cb(c, str(i + 1), f_row, ink, num.centerx, ty, align="center")
            self.hit(row, lambda i=i: m.activate(i))
        if n > n_vis:
            self.cb(c, f"{first + 1}-{min(n, first + n_vis)} of {n}", self.fb(Y(18)), b["ink"], lp.x + X(32), lp.bottom - Y(28))
        self.cb(c, f"{self.k('SELECT')}: choose   {self.k('BACK')}: back   {self.k('EXIT')}: close", self.fb(Y(21)), mix(b["muted"], b["text"], 0.4), X(64), Y(654))

    def menu_video_box(self, menu):
        r = self.R(609, 181, 569, 354)
        return (r.x, r.y, r.w, r.h)

    # ── Pages: the ViP's On Demand, My Recordings, info, keyboard ─────────
    # From frames of the real ViP622/722 (2009-11): a blue page, the mark
    # and an italic title top-left, the date top-right, the picture in a
    # pale frame with its channel above it; lists in a pale rounded panel,
    # white capsule buttons in a column at the right, amber on the chosen.

    poster_wall = True              # posters in the list panel, framed as the picture
    keyboard_layer = "ABC"
    WALL = (5, 2)                   # posters across, down

    def page_video_box(self, screen):
        r = self.R(800, 100, 440, 248)
        return (r.x, r.y, r.w, r.h)

    def ondemand_cols(self, screen):
        return self.WALL[0] if screen.view == "wall" else 1

    def ondemand_page(self, screen):
        Y = self.Y
        if screen.view == "wall":
            return self.WALL[0] * (self.WALL[1] + self.more(Y(48)) // Y(186))
        return 8 + self.grow // Y(48)       # and a taller screen's rows

    def _vip_page(self, c, title, sub="", picture=True):
        """The page every ViP screen shares; returns the picture's rect."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        knee = Y(150)
        vgrad(c, (0, 0, W, knee), rgba(b["vp_top"]), rgba(b["vp_mid"]))
        self._grad(c, (0, knee, W, H - knee), rgba(b["vp_mid"]), rgba(b["vp_bot"]))
        hdr = pygame.Surface((W, Y(90)), pygame.SRCALPHA)
        pygame.draw.ellipse(hdr, (*b["vp_hdr"], 70), (-X(200), -Y(160), W + X(400), Y(240)))
        c.blit(hdr, (0, 0))
        self.wordmark(c, X(64), Y(36), Y(34), b["text"], b["dish"])
        f = self.fb(Y(36))
        f.italic = True
        try:
            self.cb(c, self.fit_cb(f, title, X(600)), f, b["text"], X(240), Y(38))
        finally:
            f.italic = False
        if sub:
            fs = self.fb(Y(26))
            fs.italic = True
            try:
                self.cb(c, self.fit_cb(fs, sub, X(420)), fs, b["text"], X(240), Y(78))
            finally:
                fs.italic = False
        local = datetime.now()
        self.cb(c, f"{local:%a}, {local:%B} {local.day}", self.fb(Y(26)), b["text"], X(1216), Y(40), align="right")
        if not picture:
            return None
        vx, vy, vw, vh = self.page_video_box(None)
        frame = pygame.Rect(vx - X(8), vy - Y(8), vw + X(16), vh + Y(48))
        pygame.draw.rect(c, b["vp_panel_edge"], frame.inflate(X(6), Y(6)), border_radius=Y(12))
        pygame.draw.rect(c, b["vp_row"], frame, border_radius=Y(10))
        self.hole(c, (vx, vy, vw, vh))
        live = self.app.live
        fc = self.fb(Y(22))
        if live and live.channel:
            self.cb(c, self.fit_cb(fc, f"{live.channel.number} {live.channel.name.upper()}", vw - X(20)), fc,
                    b["vp_ink"], vx + X(6), vy + vh + Y(12))
        return pygame.Rect(vx, vy, vw, vh)

    def _vip_panel(self, c, r):
        """The pale rounded list panel with its blue edge."""
        b, Y = self.b, self.Y
        pygame.draw.rect(c, b["vp_panel_edge"], r.inflate(Y(6), Y(6)), border_radius=Y(18))
        vgrad(c, r, rgba(b["vp_panel"]), rgba(mix(b["vp_panel"], b["vp_hdr"], 0.35)), radius=Y(16))

    def _vip_button(self, c, r, label, on, hot=False):
        """A white capsule button; amber with a gold ring when chosen."""
        b, Y = self.b, self.Y
        if on:
            pygame.draw.rect(c, (250, 230, 60), r.inflate(Y(8), Y(8)), border_radius=r.h)
        fill, edge = (b["vp_amber"], b["vp_amber_edge"]) if on else (b["vp_btn"], b["vp_btn_edge"])
        if hot and not on:
            fill = b["vp_orange"]
        pygame.draw.rect(c, edge, r.inflate(Y(4), Y(4)), border_radius=r.h)
        vgrad(c, r, rgba(mix(fill, (255, 255, 255), 0.4 if on else 0.22)), rgba(fill), radius=r.h // 2)
        f = self.fb(Y(24))
        label = self.fit_cb(f, label, r.w - Y(20))
        ty = r.y + (r.h - self.text.ink(f)[1]) // 2
        if not on:                          # white on grey: a dark shadow under it, as the box's lettering had
            self.cb(c, label, f, mix(fill, (0, 0, 0), 0.7), r.centerx + 1, ty + 1, align="center")
        self.cb(c, label, f, b["sel_ink"] if on else b["vp_ink"], r.centerx, ty, align="center")

    def _vip_buttons(self, c, labels, focus, x=870, y=412, w=300, h=44, pitch=58, hits=None):
        for k, label in enumerate(labels):
            r = self.R(x, y + k * pitch, w, h)
            self._vip_button(c, r, label, k == focus)
            if hits:
                self.hit(r, hits[k])

    def _vip_rows(self, c, s, panel, rows, sel, top, n_vis, green=False):
        """Rows in the panel: the box's list stripes, amber on the chosen."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        f, fm = self.fb(Y(25)), self.fb(Y(23))
        rh = (panel.h - Y(70)) // n_vis
        for k, i in enumerate(range(top, min(len(rows), top + n_vis))):
            row = rows[i]
            r = pygame.Rect(panel.x + X(12), panel.y + Y(36) + k * rh, panel.w - X(24), rh - Y(4))
            on = i == sel
            fill = b["vp_amber"] if on else (b["vp_green"] if k % 2 == 0 else b["vp_green2"]) if green else b["vp_row"]
            pygame.draw.rect(c, fill, r)
            pygame.draw.rect(c, b["vp_row_edge"], r, 1)
            ink = b["sel_ink"] if on else b["text"]
            meta = row.get("meta", "")
            mw = self.measure(lambda cc, x, y: self.cb(cc, meta, fm, ink, x, y)) + X(20) if meta else 0
            ty = r.y + (r.h - t.ink(f)[1]) // 2
            self.cb(c, self.fit_cb(f, row.get("title", ""), r.w - mw - X(30)), f, ink, r.x + X(12), ty)
            if meta:
                self.cb(c, meta, fm, ink, r.right - X(12), ty, align="right")
            self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))
        if top + n_vis < len(rows):
            cx = panel.centerx
            pygame.draw.polygon(c, b["vp_ink"], [(cx - X(14), panel.bottom - Y(28)), (cx + X(14), panel.bottom - Y(28)),
                                                 (cx, panel.bottom - Y(14))])
        if top:
            cx = panel.centerx
            pygame.draw.polygon(c, b["vp_ink"], [(cx - X(14), panel.y + Y(28)), (cx + X(14), panel.y + Y(28)),
                                                 (cx, panel.y + Y(14))])

    def draw_ondemand(self, c, s):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        rec = bool(s.level) and s.level.get("key") == "recordings"
        title = "My Recordings" if rec else "On Demand"
        sub = "" if rec or not s.level or len(s.stack) < 2 else nice(s.level["title"])
        self._vip_page(c, title, sub)
        panel = self.R(40, 236, 740, 460 + self.more(Y(48)))      # a taller screen's rows
        self._vip_panel(c, panel)
        fh = self.fb(Y(22))
        fh.italic = True
        try:
            head = "Ordered by Date" if rec else (s.crumb() if len(s.stack) > 1 else "Pay-Per-View & On Demand")
            self.cb(c, self.fit_cb(fh, head, panel.w - X(40)), fh, b["vp_ink"], panel.x + X(20), panel.y + Y(10))
        finally:
            fh.italic = False
        if s.mode == "auth":
            y = panel.y + Y(60)
            for line, f in (("On a phone or computer, go to", self.fb(Y(24))), (s.auth_link or "plex.tv/link", self.fb(Y(30))),
                            ("and enter this code:", self.fb(Y(24)))):
                self.cb(c, line, f, b["vp_ink"], panel.centerx, y, align="center")
                y += t.ink(f)[1] + Y(20)
            if s.auth_code:
                self.cb(c, s.auth_code, self.fb(Y(72)), b["vp_ink"], panel.centerx, y + Y(10), align="center")
            self._vip_about(c, {"title": "Link your Plex account",
                                "meta": "On Demand comes from your own Plex server."})
            self._vip_buttons(c, ["Cancel"], 0, hits=[s.back])
            return
        rows, n_vis = s.rows, self.ondemand_page(s)
        top = max(0, min(s.sel - n_vis // 2, len(rows) - n_vis))
        if s.view == "wall":
            self._vip_wall(c, s, panel)
        else:
            self._vip_rows(c, s, panel, rows, s.sel, top, n_vis, green=rec)
        fc = self.fb(Y(20))
        fc.italic = True
        try:
            self.cb(c, f"{'Event' if rec else 'Item'} ({s.sel + 1} of {len(rows)})", fc, b["vp_ink"], panel.right - X(20),
                    panel.bottom - Y(30), align="right")
        finally:
            fc.italic = False
        side = self.od_side(s)
        self._vip_buttons(c, [lab for lab, _ in side], -1 if s.side is None else s.side, hits=[fn for _, fn in side])
        if s.status:
            fs = self.fb(Y(22))
            self.cb(c, s.status, fs, b["text"], X(1240), Y(668) + self.grow, align="right")
        self._vip_about(c, s.current() or {})

    def od_side(self, s):
        if s.mode != "browse":
            return []
        if s.level and s.level.get("key") == "recordings":
            return [("Sort", lambda: s.handle("MENU")), ("Options", lambda: s.handle("MENU")), ("Done", s.back)]
        return [("Options", lambda: s.handle("MENU")), ("My Recordings", lambda: s.handle("LIST")), ("Done", s.back)]

    def _vip_wall(self, c, s, panel):
        """Posters in the list panel, each in the picture's pale frame; the
        chosen one ringed amber and gold like a chosen button. Its title is
        in the lines above the panel."""
        b, X, Y = self.b, self.X, self.Y
        cols, tw, th, gap = self.WALL[0], X(112), Y(168), X(24)
        x0 = panel.x + (panel.w - (cols * tw + (cols - 1) * gap)) // 2
        cells = self.wall_cells(s, cols, self.ondemand_page(s) // cols)
        cx = panel.centerx
        if cells and cells[-1][0] < len(s.rows) - 1:
            pygame.draw.polygon(c, b["vp_ink"], [(cx - X(14), panel.bottom - Y(28)), (cx + X(14), panel.bottom - Y(28)),
                                                 (cx, panel.bottom - Y(14))])
        if cells and cells[0][1] == 0 and cells[0][0] > s.wall_offset:
            pygame.draw.polygon(c, b["vp_ink"], [(cx - X(14), panel.y + Y(40)), (cx + X(14), panel.y + Y(40)),
                                                 (cx, panel.y + Y(28))])
        for i, slot in cells:
            row = s.rows[i]
            r = pygame.Rect(x0 + (slot % cols) * (tw + gap), panel.y + Y(48) + (slot // cols) * (th + Y(18)), tw, th)
            if i == s.sel:
                pygame.draw.rect(c, (250, 230, 60), r.inflate(Y(16), Y(16)), border_radius=Y(8))
                pygame.draw.rect(c, b["vp_amber"], r.inflate(Y(10), Y(10)), border_radius=Y(6))
            pygame.draw.rect(c, b["pip_edge"], r.inflate(Y(4), Y(4)))
            pygame.draw.rect(c, b["vp_row"], r)
            art = self.app.ondemand.poster(row.get("thumb", ""), r.w, r.h) if row.get("thumb") else None
            if art:
                c.blit(art, art.get_rect(center=r.center))
            self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))

    def _vip_about(self, c, row):
        """The chosen row's title and details, top-left above the list."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        f, fd = self.fb(Y(26)), self.fb(Y(22))
        y = Y(130)
        for line in t.wrap(f, row.get("title", ""), int(X(720) / 0.86), 2):
            self.cb(c, line, f, b["text"], X(48), y)
            y += Y(34)
        meta = row.get("meta", "")
        if meta:
            self.cb(c, self.fit_cb(fd, meta, X(720)), fd, b["text"], X(48), y + Y(6))

    def draw_iteminfo(self, c, info):
        """The ViP's DVR Event page: the title centred over the facts, the
        description in the panel with its Time Left heading, the capsule
        buttons down the right."""
        from ..screens.iteminfo import hms
        b, t, X, Y = self.b, self.text, self.X, self.Y
        d = info.detail
        self._vip_page(c, "Event Info")
        # The poster top left in the picture's pale frame; the title block
        # centred in the room beside it.
        art_r = self.R(48, 98, 128, 192)
        pygame.draw.rect(c, b["pip_edge"], art_r.inflate(Y(6), Y(6)))
        pygame.draw.rect(c, b["vp_row"], art_r)
        art = self.logo(d.get("poster", ""), art_r.w, art_r.h, headers=d.get("poster_headers") or None)
        if art:
            c.blit(art, art.get_rect(center=art_r.center))
        cx, room = X(490), X(560)
        f = self.fb(Y(28))
        self.cb(c, self.fit_cb(f, d.get("title", ""), room), f, b["text"], cx, Y(118), align="center")
        fm = self.fb(Y(23))
        meta = d.get("subtitle") or d.get("meta", "")
        if meta:
            self.cb(c, self.fit_cb(fm, meta, room), fm, b["text"], cx, Y(162), align="center")
        if d.get("duration"):
            self.cb(c, f"Length: {hms(d['duration'])}", fm, b["text"], cx, Y(200), align="center")
        if info.kind != "download":
            self.cb(c, "Cost: Free", fm, b["text"], cx, Y(238), align="center")
        panel = self.R(40, 300, 740, 360)
        self._vip_panel(c, panel)
        pygame.draw.rect(c, b["vp_info"], panel.inflate(-X(16), -Y(16)), border_radius=Y(10))
        if (d.get("offset") or 0) > 5:      # a title part-watched: what's left of it
            fh = self.fb(Y(22))
            fh.italic = True
            try:
                left = f"Time Left: {hms(max(0, (d.get('duration') or 0) - d['offset']))}"
                self.cb(c, left, fh, b["vp_ink"], panel.right - X(24), panel.y + Y(18), align="right")
            finally:
                fh.italic = False
        fd = self.fb(Y(22))
        y = panel.y + Y(54)
        for line in t.wrap(fd, d.get("summary", "") or "No description available.", int((panel.w - X(60)) / 0.86), 8):
            self.cb(c, line, fd, b["vp_ink"], panel.centerx, y, align="center")
            y += Y(30)
        names = info.buttons()
        self._vip_buttons(c, [self.button_words(info.label(n)) for n in names], info.focus,
                          hits=[lambda k=k, n=n: (setattr(info, "focus", k), info.press(n)) for k, n in enumerate(names)])

    # The keyboard: the Themes & Search pop-up: a grey-blue card over the
    # page, the keyword field, the pale rounded keys, Done / Cancel / Clear.

    def keyboard_rows(self, layer):
        if layer == "sym":
            keys = ["!@#$%^&*()", "_+=?~'\"|\\;", "[]{}<>,`:/"]
        else:
            keys = ["ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZ'-.&", "1234567890"]
            if layer == "abc":
                keys = [k.lower() for k in keys]
        return keys + [["DEL", "SPACE", "SHIFT", "SYM"], ["DONE", "CANCEL", "CLEAR"]]

    def draw_keyboard(self, c, kb):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._vip_page(c, "Search" if kb.prompt.lower().startswith("search") else "Text Entry", picture=False)
        card = self.R(150, 104, 980, 590)
        pygame.draw.rect(c, b["vp_panel_edge"], card.inflate(X(8), Y(8)), border_radius=Y(30))
        vgrad(c, card, rgba(mix(b["vp_hdr"], (255, 255, 255), 0.25)), rgba(b["vp_mid"]), radius=Y(28))
        f = self.fb(Y(24))
        self.cb(c, self.fit_cb(f, kb.prompt, X(800)), f, b["vp_ink"], card.centerx, card.y + Y(24), align="center")
        if kb.hint:
            self.cb(c, self.fit_cb(self.fb(Y(20)), kb.hint, X(800)), self.fb(Y(20)), b["vp_ink"], card.centerx,
                    card.y + Y(58), align="center")
        field = self.R(250, 196, 780, 42)
        pygame.draw.rect(c, b["vp_field"], field)
        pygame.draw.rect(c, b["vp_panel_edge"], field, Y(2))
        ff = self.fb(Y(26))
        shown = kb.value[:kb.caret]
        while shown and t.width(ff, shown) * 0.86 > field.w - X(40):
            shown = shown[1:]
        x = field.x + X(12) + self.cb(c, shown, ff, b["vp_ink"], field.x + X(12), field.y + (field.h - t.ink(ff)[1]) // 2)
        pygame.draw.rect(c, b["vp_ink"], (x + X(2), field.bottom - Y(10), X(14), Y(3)))
        well = self.R(250, 258, 780, 300)
        pygame.draw.rect(c, b["vp_mid"], well, border_radius=Y(16))
        pygame.draw.rect(c, b["vp_panel_edge"], well, Y(2), border_radius=Y(16))
        grid = kb.grid()
        fk = self.fb(Y(26))
        words = {"DEL": "Del", "SPACE": "Space", "SHIFT": "a-z" if kb.layer == "ABC" else "A-Z",
                 "SYM": "ABC" if kb.layer == "sym" else "Symbols", "DONE": "Done", "CANCEL": "Cancel",
                 "CLEAR": "Clear Entry"}
        for r, row in enumerate(grid):
            last = r == len(grid) - 1
            for col, cell in enumerate(row):
                on = (r, col) == (kb.row, kb.col)
                if last:
                    rect = self.R(250 + col * 270, 590, 240, 46)
                    self._vip_button(c, rect, words[cell], on, hot=cell == "CANCEL")
                else:
                    if len(cell) == 1:
                        rect = self.R(270 + col * 74, 272 + r * 54, 66, 46)
                    else:
                        widths = {"DEL": 120, "SPACE": 360, "SHIFT": 120, "SYM": 120}
                        x0 = 270 + sum(widths[k] + 8 for k in row[:col])
                        rect = self.R(x0, 272 + r * 54, widths[cell], 46)
                    fill = b["vp_amber"] if on else b["vp_row"]
                    pygame.draw.rect(c, b["vp_btn_edge"], rect.inflate(Y(4), Y(4)), border_radius=Y(12))
                    vgrad(c, rect, rgba(mix(fill, (255, 255, 255), 0.5)), rgba(fill), radius=Y(10))
                    label = cell if len(cell) == 1 else words[cell]
                    fl = fk if len(cell) == 1 else self.fb(Y(22))
                    self.cb(c, label, fl, b["sel_ink"] if on else b["vp_ink"], rect.centerx,
                            rect.y + (rect.h - t.ink(fl)[1]) // 2, align="center")
                self.hit(rect, lambda r=r, col=col, cell=cell: (setattr(kb, "row", r), setattr(kb, "col", col),
                                                                kb._press(cell)))
        self.cb(c, self.fit_cb(self.fb(Y(20)), kb.tip(), X(800)), self.fb(Y(20)), b["vp_ink"], card.centerx, Y(652),
                align="center")

    # Diagnostics: the System Info card, labels right-aligned to a centre
    # line, values beside them, Help / Done / Cancel along the foot.

    def draw_diagnostics(self, c, d):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._vip_page(c, "System Info", picture=False)
        card = self.R(120, 104, 1040, 590)
        pygame.draw.rect(c, b["vp_panel"], card.inflate(X(8), Y(8)), border_radius=Y(30))
        vgrad(c, card, rgba(mix(b["vp_info"], (255, 255, 255), 0.2)), rgba(b["vp_info"]), radius=Y(28))
        f = self.fb(Y(27))
        y = card.y + Y(34)
        for label, value in [("Signal Strength", f"{d.signal()}"), ("Signal Quality", f"{d.quality()}")] + d.rows():
            self.cb(c, label, f, b["vp_ink"], X(620), y, align="right")
            self.cb(c, self.fit_cb(f, str(value), X(500)), f, b["vp_ink"], X(650), y)
            y += Y(42)
        from ..menus import open_button_guide
        for k, (label, fn) in enumerate((("Help", lambda: open_button_guide(self.app)), ("Done", lambda: d.handle("BACK")),
                                         ("Cancel", lambda: d.handle("BACK")))):
            r = self.R(250 + k * 280, 618, 230, 46)
            self._vip_button(c, r, label, k == 1)
            if fn:
                self.hit(r, fn)

    # Playback: the ViP's trick bar over the picture: a dark band with the
    # title, the progress line and its times, the mode at the right.

    def draw_playback(self, c, pb):
        from ..screens.iteminfo import hms
        b, t, X, Y = self.b, self.text, self.X, self.Y
        if pb.skip_label and self.on_top(pb):
            r = self.R(880, 424 if pb.bar_visible() else 600, 350, 52)
            self._vip_button(c, r, f"{pb.skip_label.title()}  ({self.k('SELECT')})", True)
            self.hit(r, lambda: pb.handle("SELECT"))
        if not pb.bar_visible():
            return
        r = self.R(40, 500, 1200, 180)
        self._box(c, r)
        f = self.fb(Y(28))
        q = self.app.ondemand.queue
        title = pb.title + (f"  ({q.pos + 1} of {len(q.items)})" if q.items and q.pos >= 0 else "")
        title = self.fit_cb(f, title, X(860))
        tw = self.cb(c, title, f, b["banner_ink"], r.x + X(24), r.y + Y(16))
        if pb.subtitle and X(860) - tw > X(120):        # the title's facts beside it
            fm = self.f(Y(24))
            self.cb(c, self.fit_cb(fm, pb.subtitle, X(860) - tw - X(24)), fm, b["banner_ink"],
                    r.x + X(24) + tw + X(24), r.y + Y(16) + (t.ink(f)[1] - t.ink(fm)[1]))
        mode = "Paused" if self.app.video.paused else "Play"
        self.cb(c, mode, f, b["gold"], r.right - X(24), r.y + Y(16), align="right")
        line = pygame.Rect(r.x + X(140), r.y + Y(74), r.w - X(280), Y(14))
        pygame.draw.rect(c, b["pill"], line, border_radius=Y(7))
        frac = min(1.0, pb.pos / pb.dur) if pb.dur else 0.0
        pygame.draw.rect(c, b["gold"], (line.x, line.y, max(Y(14), int(line.w * frac)), line.h), border_radius=Y(7))
        fs = self.fb(Y(24))
        self.cb(c, hms(pb.pos), fs, b["banner_ink"], line.x - X(18), line.y - Y(4), align="right")
        self.cb(c, hms(pb.dur) if pb.dur else "--:--", fs, b["banner_ink"], line.right + X(18), line.y - Y(4))
        self.hit(line.inflate(0, Y(24)), lambda: pb.seek_to(self._click_frac(line)))
        # The transport buttons: the white capsules of the box's dialogs.
        rects = []
        for k, (kind, _, fn) in enumerate(pb.transport()):
            br = self.R(140 + k * 170, 618, 150, 42)
            self._tbtn(c, br, kind, k == getattr(pb, "tfocus", None))
            self.hit(br, fn)
            rects.append(br)
        self.idle_row(c, pb, rects, Y(21))

    def draw_options(self, c, m):
        """Options as the ViP's pale dialog: the title in the blue capsule,
        the choices as its white capsule buttons, amber on the chosen one."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = pygame.Rect(0, 0, X(600), Y(96) + len(m.items) * Y(58))
        r.center = (W // 2, H // 2)
        pygame.draw.rect(c, b["vp_panel_edge"], r.inflate(X(8), Y(8)), border_radius=Y(24))
        vgrad(c, r, rgba(b["vp_panel"]), rgba(mix(b["vp_panel"], b["vp_hdr"], 0.4)), radius=Y(22))
        cap = pygame.Rect(r.x + X(30), r.y + Y(18), r.w - X(60), Y(44))
        vgrad(c, cap, rgba(b["vp_hdr"]), rgba(b["vp_mid"]), radius=Y(22))
        fh = self.fb(Y(26))
        self.cb(c, "Options", fh, b["text"], cap.centerx, cap.y + (cap.h - t.ink(fh)[1]) // 2, align="center")
        for k, it in enumerate(m.items):
            br = pygame.Rect(r.x + X(60), cap.bottom + Y(18) + k * Y(58), r.w - X(120), Y(44))
            on = k == m.cursor
            label = it.label
            if it.value:
                v = it.value()
                label += f":  < {v} >" if on and it.adjust else f":  {v}"
            self._vip_button(c, br, label, on)
            self.hit(br, lambda k=k: m.activate(k))

    def _vip_dialog(self, c, title, lines, buttons=()):
        """The ViP's pale dialog: the title in a blue capsule, the lines
        centred, capsule buttons under them."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        f = self.fb(Y(24))
        wrapped = [w for line in lines for w in t.wrap(f, line, int(X(560) / 0.86), 3)]
        r = pygame.Rect(0, 0, X(680), Y(110) + len(wrapped) * Y(34) + (Y(70) if buttons else 0))
        r.center = (W // 2, H // 2)
        pygame.draw.rect(c, b["vp_panel_edge"], r.inflate(X(8), Y(8)), border_radius=Y(24))
        vgrad(c, r, rgba(b["vp_panel"]), rgba(mix(b["vp_panel"], b["vp_hdr"], 0.4)), radius=Y(22))
        cap = pygame.Rect(r.x + X(30), r.y + Y(18), r.w - X(60), Y(44))
        vgrad(c, cap, rgba(b["vp_hdr"]), rgba(b["vp_mid"]), radius=Y(22))
        fh = self.fb(Y(26))
        self.cb(c, title, fh, b["text"], cap.centerx, cap.y + (cap.h - t.ink(fh)[1]) // 2, align="center")
        y = cap.bottom + Y(20)
        for line in wrapped:
            self.cb(c, line, f, b["vp_ink"], r.centerx, y, align="center")
            y += Y(34)
        for k, label in enumerate(buttons):
            bw = X(200)
            x0 = r.centerx - (len(buttons) * bw + (len(buttons) - 1) * X(30)) // 2
            self._vip_button(c, pygame.Rect(x0 + k * (bw + X(30)), r.bottom - Y(62), bw, Y(42)), label, k == 0)

    def draw_capture(self, c, cap):
        self._vip_dialog(c, "Remote Setup", [cap.prompt, "Waiting..."])

    def draw_toast(self, c, msg):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        f = self.fb(Y(24))
        lines = t.wrap(f, msg, int(X(1040) / 0.86), 3)
        lh = Y(32)
        w = max(int(t.width(f, ln) * 0.86) for ln in lines) + X(64)
        r = pygame.Rect((self.canvas[0] - w) // 2, Y(150) if self.over_picture() else Y(70), w,
                        Y(18) + lh * len(lines))       # under the banner; on a page, between title and panels
        radius = r.h // 2 if len(lines) == 1 else Y(18)
        pygame.draw.rect(c, b["vp_panel_edge"], r.inflate(X(6), Y(6)), border_radius=radius)
        vgrad(c, r, rgba(b["vp_panel"]), rgba(mix(b["vp_panel"], b["vp_hdr"], 0.4)), radius=radius)
        for k, ln in enumerate(lines):
            self.cb(c, ln, f, b["vp_ink"], r.centerx, r.y + Y(14) + k * lh, align="center")

    def _message(self, c, msg):
        c.fill((0, 0, 0, 255))
        self._vip_dialog(c, "ATTENTION", [msg])

    def draw_screensaver(self, c, ss):
        W, H = self.canvas
        b, Y = self.b, self.Y
        c.fill((0, 0, 0, 255))
        size = Y(60)
        w = self.measure(self.wordmark, size, b["text"], b["dish"])
        x, y = ss.position(w, int(size * 1.5), W, H)
        self.wordmark(c, x, y, size, b["text"], b["dish"])

    # ── Boot ──────────────────────────────────────────────────────────────

    # The ViP's boot, from video frames (docs/cathode-4/box-behaviour.md):
    # the logo on black with "Starting up...", black, then the Acquiring
    # Signal dialog with its code in a tab and a five-block bar that fills
    # green and holds, then a hard cut to the picture.
    boot_scenes = [("logo", 2.4), ("black", 0.6), ("attention", 1.2)]

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        scene, age = boot.scene(), boot.scene_age()
        c.fill((0, 0, 0, 255))
        if scene == "black":
            return
        if scene == "logo":
            size = Y(72)
            mw = self.measure(self.wordmark, size, b["text"], b["dish"])
            self.wordmark(c, (W - mw) // 2, Y(260), size, b["text"], b["dish"])
            self.cb(c, "Starting up...", self.fb(Y(26)), b["text"], W // 2, Y(380), align="center")
            return
        # The dialog, its code in a tab at the top right.
        r = self.R(290, 250, 700, 220)
        panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=Y(12), edge=rgba(b["pip_edge"]), edge_w=Y(3))
        tab = pygame.Rect(r.right - X(96), r.y - Y(18), X(72), Y(30))
        vgrad(c, tab, rgba(mix(b["later"], (255, 255, 255), 0.35)), rgba(b["later"]), radius=Y(8))
        self.cb(c, "535", self.fb(Y(18)), b["text"], tab.centerx, tab.y + (tab.h - t.ink(self.fb(Y(18)))[1]) // 2,
                align="center")
        pill = pygame.Rect(r.x + X(30), r.y + Y(14), r.w - X(60), Y(36))
        vgrad(c, pill, rgba(mix(b["later"], (255, 255, 255), 0.35)), rgba(b["later"]), radius=Y(10))
        f = self.fb(Y(22))
        self.cb(c, "Acquiring Signal", f, b["text"], pill.centerx, pill.y + (pill.h - t.ink(f)[1]) // 2, align="center")
        fl = self.fb(Y(19))
        self.cb(c, "This should take no more than 5 minutes to complete...", fl, b["ink"], r.centerx,
                pill.bottom + Y(16), align="center")
        # Five blocks that fill green left to right, then hold.
        g = getattr(self.app, "guide_progress", None)
        frac = max(min(1.0, age / 1.0), g if g is not None and g >= 0 else 0.0)
        bar = pygame.Rect(r.x + X(60), r.bottom - Y(58), r.w - X(120), Y(24))
        pygame.draw.rect(c, b["pb_track"], bar)
        pygame.draw.rect(c, b["pb_edge"], bar, 1)
        seg = (bar.w - X(24)) // 5
        for i in range(int(round(frac * 5))):
            pygame.draw.rect(c, (60, 170, 70), (bar.x + X(4) + i * (seg + X(4)), bar.y + 3, seg, bar.h - 6))
        self.cb(c, "Press any button to skip.", self.fb(Y(17)), b["soft"], W // 2, Y(600), align="center")


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
    tune_black = 1.2                # the 301's black on a change, a second or two
    guide_rows = 4
    SD = True
    # Measured: the tab blue, the page grey, the pale selection, the pill
    # blue of the menus.
    NATIVE = {"bg": [43, 72, 157], "accent": [183, 183, 184], "accent2": [173, 200, 208],
              "text": [255, 255, 255], "chnum": [34, 46, 113]}
    LEGIBLE = [("text", ["pill", "row", "blue", "blue_lo"], "ground"),
               ("ink", ["pillfill", "list_panel", "chan_fill", "grey_hi", "sel"], "ink"),
               ("m_ink", ["m_page_top", "m_page_bot"], "ground")]

    def theme_base(self, base):
        bg, acc, text = base["bg"], base["accent"], base["text"]
        # The blue tab from the accent, the light grey ground and the pale
        # cursor from the text colour, the pills a deep accent.
        return dict(base, bg=mix(acc, bg, 0.6), accent=mix(text, bg, 0.3), accent2=mix(text, acc, 0.4),
                    chnum=mix(acc, bg, 0.8))

    def roles(self, b):
        r = super().roles(b)
        blue, grey, sel, text, pillb = b["bg"], b["accent"], b["accent2"], b["text"], b["chnum"]
        sel_hi = (250, 250, 252)
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
            panel_top=(236, 236, 238), panel_bot=(176, 180, 192), dish=(210, 30, 40),
            pb_track=(255, 255, 255), pb_edge=ink, pb_fill=ink,
            # The 2005 menu page (Theme Categories frame): darker ground, a
            # dark band behind the rows, navy-to-blue lens pills.
            m_page_top=mix(grey, (0, 0, 0), 0.33), m_page_bot=mix(grey, (0, 0, 0), 0.45),
            m_band_top=mix(grey, (0, 0, 0), 0.70), m_band_bot=mix(grey, (0, 0, 0), 0.14),
            m_below_top=mix(grey, (0, 0, 0), 0.70), m_below_bot=mix(grey, (0, 0, 0), 0.55),
            m_rule=mix(grey, (0, 0, 0), 0.26),
            m_p0=mix(pillb, (0, 0, 0), 0.28), m_p1=mix(pillb, (50, 60, 190), 0.6),
            m_p2=mix(pillb, (130, 150, 240), 0.62), m_p3=mix(pillb, (80, 100, 170), 0.5),
            m_rim=mix(grey, (90, 90, 140), 0.55), m_lip=mix(pillb, (0, 0, 0), 0.5),
            m_sel_top=mix(sel_hi, (200, 200, 255), 0.3), m_sel=mix(sel_hi, (0, 0, 0), 0.16),
            m_sel_bot=mix(sel_hi, (0, 0, 0), 0.24), m_sel_ink=(18, 18, 24),
            m_ink=mix(text, (200, 200, 255), 0.12), m_shadow=(16, 18, 40),
            m_title_top=mix(grey, (0, 0, 0), 0.45), m_title_bot=mix(grey, (0, 0, 0), 0.62),
            m_title_rim=mix(grey, (0, 0, 0), 0.18))
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

    def _pill(self, c, y, lines, right, cx, icon=None, on=False):
        """A white capsule-ended pill from x=166, running on behind the
        picture; its lines centred on `cx` as the box set them. On: the
        tab's blue with white lettering, so the chosen pill reads at once."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = pygame.Rect(X(166), Y(y), right - X(166), Y(42))
        pygame.draw.rect(c, b["blue"] if on else b["pillfill"], r, border_top_left_radius=r.h // 2,
                         border_bottom_left_radius=r.h // 2)
        if on:                              # its white rim keeps the pill's shape on the blue tab
            pygame.draw.rect(c, b["pillfill"], r, Y(3), border_top_left_radius=r.h // 2,
                             border_bottom_left_radius=r.h // 2)
        ink = b["text"] if on else b["ink"]
        f = self.fb(Y(17))
        pitch = Y(20)
        ty = r.y + (r.h - (len(lines) - 1) * pitch - t.ink(f)[1]) // 2
        for line in lines:
            t.draw(c, t.fit(f, line, (right - X(cx)) * 2 - X(8)), f, ink, X(cx), ty, align="center")
            ty += pitch
        if icon == "lock":
            # The favourite list's padlock in a ring.
            ix, iy = X(188), r.centery
            pygame.draw.circle(c, ink, (ix, iy), Y(13), max(2, Y(3)))
            body = pygame.Rect(0, 0, X(10), Y(8))
            body.midtop = (ix, iy - Y(1))
            pygame.draw.rect(c, ink, body, border_radius=1)
            pygame.draw.arc(c, ink, (ix - X(4), iy - Y(7), X(8), Y(10)), 0, 3.15, max(2, Y(2)))
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
        self.hole(c, (vx, vy, vw, vh))
        local = datetime.now()
        self._pill(c, 37, [f"{local:%a} {local.month}/{local.day}", ampm(local).replace("am", " am").replace("pm", " pm")],
                   vx, 268)
        name = g.category if g.category != "All" else "All Sub"
        tab = self._pill(c, 100, ["Favorite List:", f"<  {name}  >" if g.focus == "category" else name], vx, 258,
                         icon="lock", on=g.focus == "category")
        self.hit(tab, lambda: g.handle("THEMES"))
        sel = g.selected()
        self._pill(c, 160, [f"<  {sel.number if sel else '---'}  >"], vx, 205)
        logo = self.channel_logo(sel, X(56), Y(30))
        if logo:
            c.blit(logo, logo.get_rect(center=(X(282), Y(181))))

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
        sel = g.sel_time()
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
                on = row_sel and p.start <= sel < p.stop
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
                    lines = [t.fit(f_cell, ln, cell.w - inset_l - inset_r)
                             for ln in t.wrap(f_cell, p.title, cell.w - inset_l - inset_r, 2)]
                    pitch = Y(17)
                    ty = y + (rh - (len(lines) - 1) * pitch - t.ink(f_cell)[1]) // 2
                    cx = cell.x + inset_l + (cell.w - inset_l - inset_r) // 2
                    for line in lines:
                        t.draw(c, line, f_cell, ink, cx, ty, align="center")
                        ty += pitch
            self.hit((0, y, X(597), rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                     setattr(g, "focus", "grid"), g.handle("SELECT")))
        if not rows:
            cell = pygame.Rect(0, Y(261), X(594), Y(42))
            self._cell(c, cell, False)
            t.draw(c, t.fit(f_cell, self.empty_guide(g), cell.w - X(20)), f_cell, b["cell_ink"], cell.centerx,
                   cell.y + (cell.h - t.ink(f_cell)[1]) // 2, align="center")
        strip = self.R(0, 452, 640, 28)
        pygame.draw.rect(c, b["grey_hi"], strip)
        fk = self.f(Y(12))
        t.draw(c, t.fit(fk, self.guide_keys(), strip.w - X(40)), fk, b["ink"], strip.centerx,
               strip.y + (strip.h - t.ink(fk)[1]) // 2, align="center")

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
        # The call sign a size under the number, inside the tile with a margin
        # (one size for every tile; past that it clips, still no ellipsis).
        call, room, fc = dish_call(ch), 2 * (tile.right - X(3) - cx), self.fb(Y(14))
        while len(call) > 1 and t.width(fc, call) > room:
            call = call[:-1]
        t.draw(c, call, fc, b["chan_ink"], cx, tile.y + Y(21), align="center")

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
            f_tag = self.fb(Y(12))
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

    def _tbtn(self, c, r, kind, on, num=None):
        """A playback button: a small capsule like the banner's, the pills'
        light lens when chosen."""
        b = self.b
        if on:
            self._lens(c, r, on=True)
        else:
            self._band(c, r)
        self.transport_face(c, kind, r, b["m_sel_ink"] if on else b["band_ink"], self.fb(self.Y(15)), num=num)

    def _trick(self, c, s):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(40, 404, 560, 36)
        self.live_buttons(c, s, r.x, r.y - Y(42), X(110), Y(34), X(10))
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
        """Two columns, as the Main Menu, when the rows carry no values
        (LEFT/RIGHT is free to cross) and one would page."""
        if menu.title == "MAIN MENU":
            return 2 if len(menu.pages) == 1 else 1
        return 2 if 6 < len(menu.items) <= 10 and not any(it.value or it.adjust for it in menu.items) else 1

    def menu_rows(self, menu):
        return 5 if self.menu_cols(menu) == 2 else super().menu_rows(menu)

    def menu_video_box(self, menu):
        return "hidden"

    # ── The 2005 menu page, measured off the Theme Categories frame ───────

    def _lens_mask(self, w, h, lp, rp):
        """A white pill on clear, pointed at the ends asked for (the box's
        bullet ends) and square at the others; drawn at 3x and scaled down
        for smooth edges, cached."""
        key = (w, h, lp, rp)
        cache = self.__dict__.setdefault("_lens_cache", {})
        m = cache.get(key)
        if m is None:
            k = 3
            W, H = w * k, h * k
            e = min(int(H * 0.7), W // 3)          # how far a point runs past the body
            mid = H * 0.58                          # the point sits a little below centre

            def bez(p0, p1, p2, n=14):
                return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                         (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
                        for t in (i / n for i in range(n + 1))]
            pts = []
            if lp:
                pts += bez((e, H - 1), (e * 0.36, H - 1), (0, mid)) + bez((0, mid), (e * 0.4, 0), (e, 0))
            else:
                pts += [(0, H - 1), (0, 0)]
            if rp:
                pts += bez((W - 1 - e, 0), (W - 1 - e * 0.4, 0), (W - 1, mid)) + \
                    bez((W - 1, mid), (W - 1 - e * 0.36, H - 1), (W - 1 - e, H - 1))
            else:
                pts += [(W - 1, 0), (W - 1, H - 1)]
            big = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.polygon(big, (255, 255, 255, 255), pts)
            m = cache[key] = pygame.transform.smoothscale(big, (w, h))
        return m

    def _lens_fill(self, w, h, lp, rp, stops):
        """The pill shape filled with a vertical gradient: stops are
        (fraction, colour) pairs from top to bottom."""
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for (f0, c0), (f1, c1) in zip(stops, stops[1:]):
            y0, y1 = int(h * f0), int(h * f1)
            if y1 > y0:
                vgrad(surf, (0, y0, w, y1 - y0), rgba(c0), rgba(c1))
        surf.blit(self._lens_mask(w, h, lp, rp), (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        return surf

    def _lens(self, c, r, lp=True, rp=True, on=False):
        """A 2005 menu pill: the pale rim above, the dark lip below, the
        body navy at the top running to bright blue (pale grey when chosen)."""
        b, Y = self.b, self.Y
        w, h = r.size
        lip = self._lens_fill(w, h, lp, rp, [(0, b["m_lip"]), (1, b["m_lip"])])
        rim = self._lens_fill(w, h, lp, rp, [(0, b["m_rim"]), (1, b["m_rim"])])
        c.blit(lip, (r.x, r.y + Y(2)))
        c.blit(rim, (r.x, r.y - Y(3)))
        if on:
            stops = [(0, b["m_sel_top"]), (0.18, b["m_sel"]), (0.85, b["m_sel"]), (1, b["m_sel_bot"])]
        else:
            stops = [(0, b["m_p0"]), (0.24, b["m_p1"]), (0.82, b["m_p2"]), (1, b["m_p3"])]
        c.blit(self._lens_fill(w, h, lp, rp, stops), r.topleft)

    def _lens_text(self, c, s, f, x, y, on, align="left"):
        """Pill lettering: pale with a dark drop shadow, dark on the chosen."""
        b, t, Y = self.b, self.text, self.Y
        if on:
            return t.draw(c, s, f, b["m_sel_ink"], x, y, align=align)
        t.draw(c, s, f, b["m_shadow"], x + Y(2), y + Y(2), align=align)
        return t.draw(c, s, f, b["m_ink"], x, y, align=align)

    def _menu_page(self, c, title):
        """The page every SD menu shares: the darker grey ground, the light
        mark with its shadow, the dark grey title pill with light lettering."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        vgrad(c, (0, 0, W, H), rgba(b["m_page_top"]), rgba(b["m_page_bot"]))
        swirl = pygame.Surface((W, H), pygame.SRCALPHA)
        for k in range(3):
            pygame.draw.ellipse(swirl, (255, 255, 255, 22), (-W // 2 + k * W // 5, -H // 6 + k * H // 9, W, H),
                                max(2, H // 50))
        c.blit(swirl, (0, 0))
        ew = X(60)                                      # the frame's darker sides
        for i in range(ew):
            a = int(90 * (1 - i / ew) ** 2)
            shade = pygame.Surface((1, H), pygame.SRCALPHA)
            shade.fill((0, 0, 0, a))
            c.blit(shade, (i, 0))
            c.blit(shade, (W - 1 - i, 0))
        self.wordmark(c, X(62), Y(38), Y(44), b["m_shadow"], b["m_shadow"])
        self.wordmark(c, X(60), Y(36), Y(44), b["m_ink"], b["dish"])
        tp = pygame.Rect(X(318), Y(60), X(340), Y(40))
        rad = tp.h // 2
        pygame.draw.rect(c, b["m_lip"], tp.move(0, Y(3)), border_top_left_radius=rad, border_bottom_left_radius=rad)
        pygame.draw.rect(c, b["m_title_rim"], tp.move(0, -Y(2)), border_top_left_radius=rad, border_bottom_left_radius=rad)
        vgrad(c, tp, rgba(b["m_title_top"]), rgba(b["m_title_bot"]), radius=rad)   # its right end runs off screen
        f_title = self.fb(Y(27))
        ty = tp.y + (tp.h - t.cap(f_title)) // 2
        t.draw(c, t.fit(f_title, title, tp.w - X(40)), f_title, b["m_shadow"], tp.x + X(17), ty + Y(2))
        t.draw(c, t.fit(f_title, title, tp.w - X(40)), f_title, b["m_ink"], tp.x + X(15), ty)

    def _menu_band(self, c, y, h):
        """The band the rows sit on, as the frame shows it: a pale rule
        above, dark at the top running light to the foot, dark below it."""
        b, Y = self.b, self.Y
        W, H = self.canvas
        band = pygame.Rect(0, y, W, h)
        pygame.draw.rect(c, b["m_rule"], (0, y - Y(2), W, Y(2)))
        vgrad(c, band, rgba(b["m_band_top"]), rgba(b["m_band_bot"]))
        if band.bottom < H:
            vgrad(c, (0, band.bottom, W, H - band.bottom), rgba(b["m_below_top"]), rgba(b["m_below_bot"]))
        return band

    def draw_menu(self, c, m):
        """A grey page, the mark top-left, the title in a pill at the right,
        two columns of numbered blue pills (one for a long list), the chosen
        one white."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._menu_page(c, "Main Menu" if m.title == "MAIN MENU" else m.title.title())
        n = len(m.items)
        cols = self.menu_cols(m)
        about = m.items[m.cursor].help if 0 <= m.cursor < n else ""
        if about:                       # what the chosen row does, under the title
            fa = self.fb(Y(13))
            for k, line in enumerate(t.wrap(fa, about, X(300), 2)):
                t.draw(c, line, fa, b["m_shadow"], X(331), Y(108) + k * Y(16) + 1)
                t.draw(c, line, fa, b["m_ink"], X(330), Y(108) + k * Y(16))
        # The 2005 page's rhythm: rows 36 tall on a 45 pitch from y 163, the
        # band 6 above the first and 6 below the last; five rows a column in
        # the two-column grid, six in a list (the footer needs the rest).
        top, rh, ph = Y(163), Y(45), Y(36)
        per_col = self.menu_rows(m) if cols == 2 else 6
        n_vis = per_col * cols
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        rows_used = min(per_col, max(1, n - first if cols == 1 else min(per_col, n)))
        self._menu_band(c, top - Y(8), rows_used * rh - (rh - ph) + Y(16))
        f_row = self.fb(Y(20))
        left, mid, right = X(50), X(321), X(592)
        for k, i in enumerate(range(first, min(n, first + n_vis))):
            it = m.items[i]
            col, row_i = (k // per_col, k % per_col) if cols == 2 else (0, k)
            y = top + row_i * rh
            if cols == 2:
                # One capsule a row, split at the centre: the left half
                # rounded on the left, the right half on the right (a left
                # half with nothing beside it closes its own end).
                partner = (k + per_col if col == 0 else k - per_col) + first
                alone = col == 0 and partner >= min(n, first + n_vis)
                row = pygame.Rect(left, y, mid - left, ph) if col == 0 else pygame.Rect(mid, y, right - mid, ph)
                round_l, round_r = col == 0, col == 1 or alone
            else:
                row = pygame.Rect(left, y, right - left, ph)
                round_l = round_r = True
            sel = i == m.cursor
            self._lens(c, row, lp=round_l, rp=round_r, on=sel)
            if cols == 2 and col == 1:
                pygame.draw.rect(c, b["m_lip"], (mid - X(1), y, X(2), ph))
            ty = row.y + (row.h - t.cap(f_row)) // 2
            num = str((i + 1) % 10) if i < 10 else ""
            label = f"{num} {it.label}".strip()
            pad = X(28) if round_l else X(8)
            lw = self._lens_text(c, t.fit(f_row, label, row.w - pad - (X(140) if it.value else X(36))), f_row,
                                 row.x + pad, ty, sel)
            if not it.enabled and not sel:
                veil = pygame.Surface((lw + X(4), row.h), pygame.SRCALPHA)
                veil.fill(b["m_p2"][:3] + (110,))
                c.blit(veil, (row.x + pad - X(2), row.y))
            end = row.right - (X(30) if round_r else X(14))
            if it.value:
                v = it.value()
                v = f"< {v} >" if sel and it.adjust else v
                self._lens_text(c, t.fit(f_row, v, row.w - pad - lw - X(48)), f_row, end, ty, sel, align="right")
            elif it.submenu:
                self._lens_text(c, ">", f_row, end, ty, sel, align="right")
            self.hit(row, lambda i=i: m.activate(i))
        f_foot = self.f(Y(12))
        t.draw(c, f"{self.k('SELECT')}: choose   {self.k('BACK')}: back   {self.k('EXIT')}: close", f_foot, b["m_ink"], X(40), Y(444))
        if n > n_vis:
            count = f"{first + 1}-{min(n, first + n_vis)} of {n}"
            t.draw(c, count, f_foot, b["m_ink"], X(600), Y(444), align="right")
            ax, ay = X(600) - t.width(f_foot, count) - X(16), Y(444) + t.ink(f_foot)[1] // 2
            if first + n_vis < n:           # more below
                pygame.draw.polygon(c, b["m_ink"], [(ax - X(6), ay - Y(3)), (ax + X(6), ay - Y(3)), (ax, ay + Y(4))])
            if first:                       # more above
                ax -= X(18)
                pygame.draw.polygon(c, b["m_ink"], [(ax - X(6), ay + Y(3)), (ax + X(6), ay + Y(3)), (ax, ay - Y(4))])

    # ── Pages: the 2005 box's grey pages ──────────────────────────────────
    # The 322/522 drew everything on the grey swirl page: the mark top-left,
    # the title in a pale pill at the right, blue capsule pills (white on
    # the chosen one), grey dialogs with a blue title pill. On Demand, My
    # Recordings, info and the keyboard are drawn in that vocabulary.

    poster_wall = True              # posters on the band, the chosen one's pill under them
    keyboard_layer = "ABC"
    WALL = (4, 2)                   # posters across, down

    def page_video_box(self, screen):
        return None

    def ondemand_cols(self, screen):
        return self.WALL[0] if screen.view == "wall" else 1

    def ondemand_page(self, screen):
        return self.WALL[0] * self.WALL[1] if screen.view == "wall" else 6

    def _sd_page(self, c, title):
        """The grey page with the mark and the title pill (the Theme
        Categories page's top)."""
        self._menu_page(c, title)

    def _gloss(self, c, r, radius=None):
        """The 2005 pill's sheen across its top half: a lighter capsule on a
        pill, a lighter rounded band on a key (radius: the key's corners)."""
        Y, b = self.Y, self.b
        inset = r.h // 3 if radius is None else Y(4)
        g = pygame.Rect(r.x + inset, r.y + Y(2), r.w - 2 * inset, max(2, int(r.h * 0.42)))
        pygame.draw.rect(c, mix(b["row"], b["row_hi"], 0.75), g,
                         border_radius=g.h // 2 if radius is None else max(1, radius - Y(2)))

    def _sd_pill(self, c, r, label, on, right="", centre=False):
        """A blue capsule pill with its light top line, white when chosen."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._lens(c, r, on=on)
        f = self.fb(Y(19))
        ty = r.y + (r.h - t.cap(f)) // 2
        rw = t.width(f, right) + X(16) if right else 0
        if label and centre:
            self._lens_text(c, t.fit(f, label, r.w - X(32)), f, r.centerx, ty, on, align="center")
        elif label:
            self._lens_text(c, t.fit(f, label, r.w - X(48) - rw), f, r.x + X(24), ty, on)
        if right:
            self._lens_text(c, right, f, r.right - X(24), ty, on, align="right")

    def _sd_band(self, c, y, h):
        b, X, Y = self.b, self.X, self.Y
        return self._menu_band(c, y, h)

    def _sd_side(self, c, labels, focus, y0=170, hits=None):
        """Blue pill buttons in a column at the right, the chosen one white."""
        X, Y = self.X, self.Y
        for k, label in enumerate(labels):
            r = pygame.Rect(X(424), Y(y0) + k * Y(40), X(200), Y(32))
            self._sd_pill(c, r, label, k == focus)
            if hits and hits[k]:
                self.hit(r, hits[k])

    def draw_ondemand(self, c, s):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        rec = bool(s.level) and s.level.get("key") == "recordings"
        self._sd_page(c, "My Recordings" if rec else (nice(s.level["title"]) if s.level and len(s.stack) > 1
                                                      else "On Demand"))
        band = self._sd_band(c, Y(160), Y(270))
        if s.mode == "auth":
            fl = self.fb(Y(17))
            y = band.y + Y(24)
            for line in ("On a phone or computer, go to", s.auth_link or "plex.tv/link", "and enter this code:"):
                t.draw(c, line, fl, b["m_ink"], X(240), y, align="center")
                y += Y(30)
            if s.auth_code:
                t.draw(c, s.auth_code, self.fb(Y(44)), b["m_ink"], X(240), y + Y(4), align="center")
            self._sd_side(c, ["Cancel"], 0, hits=[s.back])
            return
        rows, n_vis = s.rows, self.ondemand_page(s)
        top = max(0, min(s.sel - n_vis // 2, len(rows) - n_vis))
        if s.view == "wall":
            self._sd_wall(c, s, band)
        for k, i in enumerate(range(top, min(len(rows), top + n_vis)) if s.view != "wall" else ()):
            row = rows[i]
            r = pygame.Rect(X(20), band.y + Y(10) + k * Y(42), X(390), Y(34))
            self._sd_pill(c, r, nice(row.get("title", "")), i == s.sel, right=row.get("meta", "").split("   ")[0])
            self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))
        fs = self.f(Y(12))
        t.draw(c, f"{s.sel + 1} of {len(rows)}", fs, b["m_ink"], X(40), band.bottom + Y(6))
        if s.status:
            t.draw(c, s.status, self.fb(Y(13)), b["m_ink"], X(600), band.bottom + Y(6), align="right")
        side = self.od_side(s)
        self._sd_side(c, [lab for lab, _ in side], -1 if s.side is None else s.side, hits=[fn for _, fn in side])
        t.draw(c, f"{self.k('SELECT')}: choose   {self.k('BACK')}: back   {self.k('EXIT')}: close", self.f(Y(12)), b["m_ink"], X(40), Y(444))

    def od_side(self, s):
        if s.mode != "browse":
            return []
        rec = bool(s.level) and s.level.get("key") == "recordings"
        return [("Options", lambda: s.handle("MENU")),
                ("Sort", lambda: s.handle("MENU")) if rec else ("My Recordings", lambda: s.handle("LIST")),
                ("Done", s.back)]

    def _sd_wall(self, c, s, band):
        """Posters on the band, four across and two down, the chosen one
        ringed in the pills' white; its title on a pill beneath them."""
        b, X, Y = self.b, self.X, self.Y
        cols, tw, th, gap = self.WALL[0], X(66), Y(99), X(20)
        x0 = X(20) + (X(390) - (cols * tw + (cols - 1) * gap)) // 2
        for i, slot in self.wall_cells(s, cols):
            row = s.rows[i]
            r = pygame.Rect(x0 + (slot % cols) * (tw + gap), band.y + Y(10) + (slot // cols) * (th + Y(10)), tw, th)
            if i == s.sel:
                pygame.draw.rect(c, b["m_sel"], r.inflate(X(10), Y(10)), border_radius=Y(6))
            pygame.draw.rect(c, b["m_lip"], r.inflate(X(2), Y(2)))
            art = self.app.ondemand.poster(row.get("thumb", ""), r.w, r.h) if row.get("thumb") else None
            if art:
                c.blit(art, art.get_rect(center=r.center))
            self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))
        cur = s.current() or {}
        pill = pygame.Rect(X(20), band.y + Y(10) + 2 * (th + Y(10)) + Y(2), X(390), Y(34))
        self._sd_pill(c, pill, nice(cur.get("title", "")), True, right=cur.get("meta", "").split("   ")[0])

    def draw_iteminfo(self, c, info):
        from ..screens.iteminfo import hms
        b, t, X, Y = self.b, self.text, self.X, self.Y
        d = info.detail
        self._sd_page(c, "Event Info")
        r = self.R(20, 150, 390, 290)
        panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=Y(12), edge=rgba((255, 255, 255)), edge_w=Y(2))
        pill = pygame.Rect(r.x + X(14), r.y + Y(10), r.w - X(28), Y(30))
        vgrad(c, pill, rgba(b["pill_hi"]), rgba(b["pill"]), radius=Y(10))
        f = self.fb(Y(17))
        t.draw(c, t.fit(f, d.get("title", ""), pill.w - X(20)), f, b["pill_ink"], pill.centerx,
               pill.y + (pill.h - t.ink(f)[1]) // 2, align="center")
        # The poster at the left under the pill, white-edged like the panel;
        # the facts beside it, the summary under both.
        art_r = pygame.Rect(r.x + X(18), pill.bottom + Y(10), X(76), Y(114))
        pygame.draw.rect(c, (255, 255, 255), art_r.inflate(X(4), Y(4)), border_radius=Y(3))
        pygame.draw.rect(c, b["panel_bot"], art_r)
        art = self.logo(d.get("poster", ""), art_r.w, art_r.h, headers=d.get("poster_headers") or None)
        if art:
            c.blit(art, art.get_rect(center=art_r.center))
        fl = self.fb(Y(14))
        y = pill.bottom + Y(14)
        lx = art_r.right + X(66)
        for label, value in (("info:", d.get("subtitle") or d.get("meta", "")),
                             ("length:", hms(d["duration"]) if d.get("duration") else ""),
                             ("resume:", hms(d["offset"]) if d.get("offset", 0) > 5 else ""),
                             ("cost:", "Free" if info.kind != "download" else "")):
            if value:
                t.draw(c, label, fl, b["ink"], lx, y, align="right")
                t.draw(c, t.fit(fl, value, r.right - X(12) - (lx + X(8))), fl, b["ink"], lx + X(8), y)
                y += Y(20)
        fd = self.f(Y(14))
        y = art_r.bottom + Y(6)
        for line in t.wrap(fd, d.get("summary", ""), r.w - X(36), max(1, (r.bottom - Y(12) - y) // Y(18))):
            t.draw(c, line, fd, b["ink"], r.centerx, y, align="center")
            y += Y(18)
        names = info.buttons()
        self._sd_side(c, [self.button_words(info.label(n), back="Done") for n in names], info.focus, y0=150,
                      hits=[lambda k=k, n=n: (setattr(info, "focus", k), info.press(n)) for k, n in enumerate(names)])

    def keyboard_rows(self, layer):
        if layer == "sym":
            keys = ["!@#$%^&*()", "_+=?~'\"|\\;", "[]{}<>,`:/"]
        else:
            keys = ["ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZ'-.&", "1234567890"]
            if layer == "abc":
                keys = [k.lower() for k in keys]
        return keys + [["DEL", "SPACE", "SHIFT", "SYM"], ["DONE", "CANCEL", "CLEAR"]]

    def draw_keyboard(self, c, kb):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._sd_page(c, "Search" if kb.prompt.lower().startswith("search") else "Text Entry")
        band = self._sd_band(c, Y(150), Y(296))
        f = self.fb(Y(15))
        pw = t.draw(c, t.fit(f, kb.prompt, X(560)), f, b["m_ink"], X(40), band.y + Y(8))
        if kb.hint:
            fh = self.f(Y(12))
            t.draw(c, t.fit(fh, kb.hint, X(540) - pw), fh, b["m_ink"], X(600), band.y + Y(10), align="right")
        field = self.R(40, 178, 560, 26)
        pygame.draw.rect(c, b["pillfill"], field, border_radius=Y(6))
        pygame.draw.rect(c, b["ink"], field, 1, border_radius=Y(6))
        ff = self.fb(Y(16))
        shown = kb.value[:kb.caret]
        while shown and t.width(ff, shown) > field.w - X(30):
            shown = shown[1:]
        x = field.x + X(8) + t.draw(c, shown, ff, b["ink"], field.x + X(8), field.y + (field.h - t.ink(ff)[1]) // 2)
        pygame.draw.rect(c, b["ink"], (x + 1, field.bottom - Y(6), X(8), Y(2)))
        fk = self.fb(Y(17))
        words = {"DEL": "Del", "SPACE": "Space", "SHIFT": "a-z" if kb.layer == "ABC" else "A-Z",
                 "SYM": "ABC" if kb.layer == "sym" else "Symbols", "DONE": "Done", "CANCEL": "Cancel", "CLEAR": "Clear"}
        grid = kb.grid()
        for r, row in enumerate(grid):
            for col, cell in enumerate(row):
                on = (r, col) == (kb.row, kb.col)
                if r == len(grid) - 1:
                    rect = self.R(40 + col * 190, 396, 176, 30)
                    self._sd_pill(c, rect, words[cell], on)
                else:
                    if len(cell) == 1:
                        rect = self.R(40 + col * 56, 214 + r * 36, 52, 32)
                    else:
                        widths = {"DEL": 100, "SPACE": 220, "SHIFT": 100, "SYM": 100}
                        x0 = 40 + sum(widths[k] + 6 for k in row[:col])
                        rect = self.R(x0, 214 + r * 36, widths[cell], 32)
                    fill, ink = (b["cursor"], b["cursor_ink"]) if on else (b["row"], b["row_ink"])
                    pygame.draw.rect(c, fill, rect, border_radius=Y(8))
                    if not on:
                        self._gloss(c, rect, radius=Y(8))
                    label = cell if len(cell) == 1 else words[cell]
                    fl = fk if len(cell) == 1 else self.fb(Y(15))
                    t.draw(c, label, fl, ink, rect.centerx, rect.y + (rect.h - t.ink(fl)[1]) // 2, align="center")
                self.hit(rect, lambda r=r, col=col, cell=cell: (setattr(kb, "row", r), setattr(kb, "col", col),
                                                                kb._press(cell)))
        t.draw(c, t.fit(self.f(Y(12)), kb.tip(), X(560)), self.f(Y(12)), b["ink"], X(40), Y(431))

    def draw_diagnostics(self, c, d):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._sd_page(c, "System Info")
        r = self.R(28, 150, 584, 296)
        panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=Y(12), edge=rgba((255, 255, 255)), edge_w=Y(2))
        f = self.fb(Y(15))
        y = r.y + Y(16)
        for label, value in [("Signal Strength", f"{d.signal()}"), ("Signal Quality", f"{d.quality()}")] + d.rows():
            t.draw(c, label, f, b["ink"], X(300), y, align="right")
            t.draw(c, t.fit(f, str(value), X(280)), f, b["ink"], X(316), y)
            y += Y(24)
        ok = pygame.Rect(X(230), r.bottom - Y(42), X(180), Y(30))
        self._sd_pill(c, ok, "Done", True, centre=True)
        self.hit(ok, lambda: d.handle("BACK"))

    def draw_playback(self, c, pb):
        """The 2005 box's DVR bar: the capsules of its banner along the
        bottom, the title over the progress line, the times in the outer
        two."""
        from ..screens.iteminfo import hms
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        if pb.skip_label and self.on_top(pb):
            r = self.R(370, 262 if pb.bar_visible() else 400, 230, 32)
            self._sd_pill(c, r, f"{pb.skip_label.title()}: {self.k('SELECT')}", True)
            self.hit(r, lambda: pb.handle("SELECT"))
        if not pb.bar_visible():
            return
        top, h = H - Y(46) - Y(42) - Y(87), Y(87)
        left = pygame.Rect(X(55), top, X(88), h)
        mid = pygame.Rect(X(147), top, X(333), h)
        right = pygame.Rect(X(484), top, X(96), h)
        for r in (left, mid, right):
            self._band(c, r)
        ink = b["band_ink"]
        f, fs = self.fb(Y(19)), self.fb(Y(17))
        t.draw(c, "Elapsed", fs, ink, left.centerx, top + Y(24), align="center")
        t.draw(c, hms(pb.pos), f, ink, left.centerx, top + Y(51), align="center")
        t.draw(c, "Length", fs, ink, right.centerx, top + Y(24), align="center")
        t.draw(c, hms(pb.dur) if pb.dur else "--:--", f, ink, right.centerx, top + Y(51), align="center")
        t.draw(c, t.fit(self.fb(Y(22)), pb.title, mid.w - X(20)), self.fb(Y(22)), ink, mid.centerx, top + Y(12),
               align="center")
        line = pygame.Rect(mid.x + X(18), top + Y(50), mid.w - X(36), Y(10))
        pygame.draw.rect(c, b["band_soft"], line, border_radius=Y(5))
        frac = min(1.0, pb.pos / pb.dur) if pb.dur else 0.0
        pygame.draw.rect(c, b["warn"], (line.x, line.y, max(Y(10), int(line.w * frac)), line.h), border_radius=Y(5))
        state = "Paused" if self.app.video.paused else "Play"
        t.draw(c, t.fit(fs, f"{state}   {pb.subtitle}".strip(), mid.w - X(20)), fs, ink, mid.centerx, top + Y(67),
               align="center")
        self.hit(line.inflate(0, Y(20)), lambda: pb.seek_to(self._click_frac(line)))
        # The transport buttons: small capsules like the banner's.
        rects = []
        for k, (kind, _, fn) in enumerate(pb.transport()):
            br = pygame.Rect(X(55) + k * X(89), top + h + Y(8), X(80), Y(34))
            self._tbtn(c, br, kind, k == getattr(pb, "tfocus", None))
            self.hit(br, fn)
            rects.append(br)
        self.idle_row(c, pb, rects, Y(17))

    def _note(self, c, text, frac=None):
        """A dark capsule like the banner's, bottom left."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        bar = frac is not None and frac >= 0
        f = self.fb(Y(16))
        r = pygame.Rect(X(55), 0, max(t.width(f, text) + X(36), X(330) if bar else 0), Y(58 if bar else 38))
        r.bottom = Y(385)                  # above the subtitle line
        self._band(c, r)
        t.draw(c, text, f, b["band_ink"], r.x + X(18), r.y + Y(11))
        if bar:
            track = pygame.Rect(r.x + X(18), r.bottom - Y(17), r.w - X(36), Y(7))
            pygame.draw.rect(c, b["band_soft"], track, border_radius=Y(3))
            pygame.draw.rect(c, b["warn"], (track.x, track.y, max(track.h, int(track.w * frac)), track.h),
                             border_radius=Y(3))

    def draw_options(self, c, m):
        """Options as the grey ATTENTION-style dialog: the blue title pill,
        the choices as the menu's lens pills, light on the chosen one."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = pygame.Rect(X(110), 0, X(420), Y(56) + len(m.items) * Y(40))
        r.centery = H // 2
        panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=Y(10), edge=rgba((255, 255, 255)), edge_w=Y(2))
        pill = pygame.Rect(r.x + X(20), r.y + Y(10), r.w - X(40), Y(28))
        vgrad(c, pill, rgba(b["pill_hi"]), rgba(b["pill"]), radius=Y(8))
        fh = self.fb(Y(15))
        t.draw(c, "OPTIONS", fh, b["pill_ink"], pill.centerx, pill.y + (pill.h - t.ink(fh)[1]) // 2, align="center")
        for k, it in enumerate(m.items):
            br = pygame.Rect(r.x + X(20), pill.bottom + Y(10) + k * Y(40), r.w - X(40), Y(32))
            on = k == m.cursor
            v = it.value() if it.value else ""
            self._sd_pill(c, br, it.label, on, right=f"< {v} >" if v and on and it.adjust else v)
            self.hit(br, lambda k=k: m.activate(k))

    def _sd_dialog(self, c, title, lines):
        """The grey ATTENTION-style dialog."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        f = self.f(Y(14))
        wrapped = [w for line in lines for w in t.wrap(f, line, X(380), 3)]
        r = pygame.Rect(X(100), 0, X(440), Y(60) + len(wrapped) * Y(20))
        r.centery = H // 2
        panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=Y(10), edge=rgba((255, 255, 255)), edge_w=Y(2))
        pill = pygame.Rect(r.x + X(20), r.y + Y(10), r.w - X(40), Y(28))
        vgrad(c, pill, rgba(b["pill_hi"]), rgba(b["pill"]), radius=Y(8))
        fh = self.fb(Y(15))
        t.draw(c, title, fh, b["pill_ink"], pill.centerx, pill.y + (pill.h - t.ink(fh)[1]) // 2, align="center")
        y = pill.bottom + Y(10)
        for line in wrapped:
            t.draw(c, line, f, b["ink"], r.centerx, y, align="center")
            y += Y(20)

    def draw_program_info(self, c, info):
        """A guide cell's programme as the grey dialog: the title in the pill,
        the channel, when, and the synopsis under it."""
        self._sd_dialog(c, self.fit_cb(self.fb(self.Y(15)), info.title.upper(), self.X(360)), info.lines())

    def draw_capture(self, c, cap):
        self._sd_dialog(c, "REMOTE SETUP", [cap.prompt, "Waiting..."])

    def draw_toast(self, c, msg):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        f = self.fb(Y(15))
        lines = t.wrap(f, msg, X(560), 3)
        lh = Y(20)
        w = max(t.width(f, ln) for ln in lines) + X(40)
        r = pygame.Rect((self.canvas[0] - w) // 2, Y(110), w, Y(14) + lh * len(lines))
        if len(lines) == 1:
            self._sd_pill(c, r, "", True)
        else:
            pygame.draw.rect(c, b["cursor"], r, border_radius=Y(10))
        for k, ln in enumerate(lines):
            t.draw(c, ln, f, b["cursor_ink"], r.centerx, r.y + Y(9) + k * lh, align="center")

    def _message(self, c, msg):
        c.fill((0, 0, 0, 255))
        self._sd_dialog(c, "ATTENTION", [msg])

    # The 2005 box (docs/cathode-4/box-behaviour.md): no splash, a black
    # moment, then the grey ATTENTION 015 dialog "Acquiring satellite
    # signal. Please wait." with its bar, then straight to the picture.
    boot_scenes = [("black", 0.8), ("attention", 1.0)]

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        c.fill((0, 0, 0, 255))
        if boot.scene() == "black":
            return
        r = self.R(100, 150, 440, 150)
        panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=Y(10), edge=rgba((255, 255, 255)), edge_w=Y(2))
        pill = pygame.Rect(r.x + X(20), r.y + Y(10), r.w - X(40), Y(28))
        vgrad(c, pill, rgba(b["pill_hi"]), rgba(b["pill"]), radius=Y(8))
        f = self.fb(Y(15))
        t.draw(c, "ATTENTION  015", f, b["pill_ink"], pill.centerx, pill.y + (pill.h - t.ink(f)[1]) // 2, align="center")
        fl = self.f(Y(13))
        t.draw(c, "Acquiring satellite signal. Please wait.", fl, b["ink"], r.centerx, pill.bottom + Y(12), align="center")
        t.draw(c, "Press any button to skip.", fl, b["ink"], r.centerx, pill.bottom + Y(34), align="center")
        self._progress_bar(c, pygame.Rect(r.x + X(30), r.bottom - Y(34), r.w - X(60), Y(16)))


def dish_call(ch) -> str:
    """The 2005 box's call sign: spaces dropped, cut at five letters, as it
    showed HISTI and BIOGR."""
    return call_sign(ch, 5)


def g_list(skin) -> str:
    """The guide's current list name, for the banner's 'List:' slot."""
    from ..screens.guide import Guide
    g = skin.app.find(Guide) if hasattr(skin.app, "find") else None
    return (g.category if g and g.category != "All" else "All Sub")
