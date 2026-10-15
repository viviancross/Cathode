"""InDirecTV: a mid-2000s DirecTV-style box. InDirecTV HD follows the HR20:
a light swoosh panel over a navy grid, white on blue cells, amber selection,
the remote's colour keys explained along the bottom. InDirecTV (SD) follows
the D10/R15 era: the same screens on a dark navy ground, gold selection, 4:3.

Layout is worked out from the canvas size, so the SD variant reuses it at
640x480 and only changes colours and a few details."""

import time
from datetime import datetime, timedelta, timezone

import pygame

from .box import BoxSkin, mix, panel, rgba, vgrad


def ampm(dt) -> str:
    """'6:00a' / '7:30p', the box's own clock style."""
    return dt.astimezone().strftime("%I:%M%p").lstrip("0").lower()[:-1]


def hours(prog) -> str:
    return f"{ampm(prog.start)} - {ampm(prog.stop)}"


def stamp(dt=None) -> str:
    """'Mon 5:46a': the day and clock the banner and guide carry."""
    dt = dt or datetime.now()
    return f"{dt:%a} {ampm(dt)}"


DOTS = {"red": (214, 44, 36), "green": (58, 170, 64), "yellow": (238, 196, 34), "blue": (40, 104, 212)}


class InDirectHD(BoxSkin):
    name = "indirect_hd"
    label = "InDirecTV HD"
    canvas = (1280, 720)
    browse_style = "mini"           # BROWSE opens the mini guide
    guide_hours = 1.5               # three half-hour columns, as the box showed
    guide_rows = 6
    SD = False
    NATIVE = {"bg": [10, 36, 96], "accent": [40, 110, 200], "accent2": [244, 160, 24],
              "text": [255, 255, 255], "chnum": [240, 244, 255]}

    def roles(self, b):
        bg, acc, sel, text = b["bg"], b["accent"], b["accent2"], b["text"]
        return {
            "navy": bg, "deep": mix(bg, (0, 0, 0), 0.35), "band": acc,
            "band_hi": mix(acc, (255, 255, 255), 0.25),
            "cell": mix(bg, acc, 0.5), "cell_hi": mix(bg, acc, 0.7),
            "chan": mix(bg, acc, 0.2), "chan_ink": text,
            "sel": sel, "sel_hi": mix(sel, (255, 255, 255), 0.25), "sel_ink": text,
            "text": text, "muted": mix(text, acc, 0.45),
            "panel_top": mix((255, 255, 255), acc, 0.04), "panel_bot": mix((255, 255, 255), acc, 0.34),
            "strip": rgba(acc, 46), "rule": mix((255, 255, 255), acc, 0.5),
            "ink": mix(bg, (0, 0, 0), 0.2), "ink_soft": mix(bg, acc, 0.45),
            "watermark": mix((255, 255, 255), acc, 0.2), "mark": acc,
        }

    # Geometry, relative to the canvas.
    def u(self, v) -> int:
        """A length given in 720-line units, scaled to this canvas."""
        return int(v * self.canvas[1] / 720)

    # ── Wordmark ──────────────────────────────────────────────────────────

    def wordmark(self, c, x, y, size, ink, tile):
        """A blue tile with a white swoosh, then 'InDirecTV' in spaced caps:
        our own mark, after the era's tile-and-wordmark lockups."""
        t = self.text
        f = self.fb(size)
        h = t.ink(f)[1]
        s = int(h * 1.3)
        tr = pygame.Rect(x, y - (s - h) // 2, s, s)
        vgrad(c, tr, rgba(mix(tile, (255, 255, 255), 0.35)), rgba(tile), radius=max(3, s // 5))
        lens = tr.inflate(-s // 4, -s // 4)
        pygame.draw.ellipse(c, (255, 255, 255), lens)
        pygame.draw.ellipse(c, tile, lens.inflate(-s // 12, -s // 12).move(-s // 7, s // 9))
        tx = tr.right + size // 3
        gap = max(1, size // 9)
        for ch in "InDirecTV":
            tx += t.draw(c, ch, f, ink, tx, y) + gap
        return tx - gap - x

    # ── Live: banner ──────────────────────────────────────────────────────

    def _digits(self, c, digits):
        W = self.canvas[0]
        b, u = self.b, self.u
        f = self.fb(u(40))
        text = digits + "-" * (3 - len(digits))
        r = pygame.Rect(0, 0, self.text.width(f, text) + u(40), u(70))
        r.topright = (W - u(40), u(150))
        panel(c, r, rgba(b["band_hi"], 240), rgba(b["navy"], 240), radius=u(10), edge=rgba(b["band_hi"]))
        self.text.draw(c, text, f, b["text"], r.centerx, r.y + (r.h - self.text.ink(f)[1]) // 2, align="center")

    def _band(self, c, r):
        """The translucent blue band the box laid over the picture."""
        vgrad(c, r, rgba(self.b["band_hi"], 215), rgba(self.b["navy"], 238))
        pygame.draw.rect(c, self.b["band_hi"], (r.x, r.bottom - self.u(3), r.w, self.u(3)))

    def _banner(self, c, ch, cur, nxt, full=False, tag=None):
        """The channel banner, across the top as the box drew it: channel and
        clock, the title, when it's on; INFO again adds the synopsis under it."""
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        pad = u(40)
        r = pygame.Rect(0, 0, W, u(132))
        self._band(c, r)
        if tag:
            self.chip(c, pad, r.bottom + u(8), tag, self.fb(u(16)), rgba(b["sel"]), b["sel_ink"])
        x = pad + self.wordmark(c, pad, u(18), u(22), b["text"], b["mark"]) + u(28)
        right = W - pad
        f_num, f_call = self.fb(u(36)), self.f(u(22))
        nw = t.draw(c, str(ch.number), f_num, b["text"], x, u(12))
        t.draw(c, t.fit(f_call, ch.name.upper(), u(300)), f_call, b["muted"], x + nw + u(12), u(24))
        t.draw(c, stamp(), self.fb(u(24)), b["text"], right, u(14), align="right")

        f_title, f_line = self.fb(u(30)), self.f(u(21))
        t.draw(c, t.fit(f_title, cur.title if cur else ch.name, W - x - u(380)), f_title, b["text"], x, u(58))
        nx = x
        if cur:
            bits = [hours(cur)] + [s for s in (cur.rating, cur.episode) if s]
            t.draw(c, t.fit(f_line, "   ".join(bits), u(420)), f_line, b["muted"], right, u(64), align="right")
            bar = pygame.Rect(x, u(104), u(260), u(8))
            now = datetime.now(timezone.utc)
            self.progress(c, bar, cur.progress_at(now), rgba(b["deep"]), rgba(b["sel"]))
            left = max(0, int((cur.stop - now).total_seconds() // 60))
            nx = bar.right + u(14)
            nx += t.draw(c, f"{left} min left", self.f(u(17)), b["muted"], nx, u(100)) + u(30)
        if nxt:
            fs = self.f(u(17))
            t.draw(c, t.fit(fs, f"Next: {nxt.title}  {ampm(nxt.start)}", right - u(150) - nx), fs,
                   b["muted"], nx, u(100))
        t.draw(c, "INFO for more", self.f(u(15)), b["muted"], right, u(102), align="right")
        if full and cur and cur.description:
            f = self.f(u(20))
            lines = t.wrap(f, cur.description, W - 2 * pad, 3)
            d = pygame.Rect(0, r.bottom, W, u(20) + len(lines) * (t.ink(f)[1] + u(9)))
            vgrad(c, d, rgba(b["navy"], 232), rgba(b["deep"], 238))
            y = d.y + u(12)
            for line in lines:
                t.draw(c, line, f, b["text"], pad, y)
                y += t.ink(f)[1] + u(9)
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    # ── Signal loss ───────────────────────────────────────────────────────

    def _signal_loss(self, c):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        c.fill((0, 0, 0, 255))
        band = pygame.Rect(0, u(150), W, u(96))
        self._band(c, band)
        t.draw(c, "Searching for satellite signal. (771)", self.fb(u(28)), b["text"], u(40), band.y + u(32))
        f = self.f(u(20))
        y = band.bottom + u(26)
        for line in t.wrap(f, "The channel isn't sending a picture. Cathode keeps trying; press GUIDE or "
                              "a channel number to watch something else.", W - u(80), 3):
            t.draw(c, line, f, b["muted"], u(40), y)
            y += t.ink(f)[1] + u(10)

    # ── Guide ─────────────────────────────────────────────────────────────

    def _geo(self):
        W, H = self.canvas
        u = self.u
        top, hdr, foot = u(300), u(40), u(40)
        row_h = (H - top - hdr - foot - u(6)) // self.guide_rows
        return dict(top=top, hdr=hdr, foot=foot, row_h=row_h, ch_w=int(W * (0.19 if self.SD else 0.155)),
                    pad=u(40))

    def guide_video_box(self):
        W, H = self.canvas
        u = self.u
        h = u(192)
        w = int(h * 16 / 9)
        return (W - w - u(40), u(44), w, h)

    def _light_panel(self, c, rect):
        """The era's info panel: white into pale blue, with a soft sweep of
        light across it."""
        rect = pygame.Rect(rect)
        vgrad(c, rect, rgba(self.b["panel_top"]), rgba(self.b["panel_bot"]))
        sweep = pygame.Surface(rect.size, pygame.SRCALPHA)
        h = min(rect.h, self.u(320))          # the sweep sits across the top, whatever the panel's height
        pygame.draw.ellipse(sweep, (255, 255, 255, 90),
                            (-int(rect.w * 0.1), -int(h * 0.7), int(rect.w * 0.85), int(h * 1.5)))
        c.blit(sweep, rect.topleft)

    def _picture(self, c):
        """The live picture's window, framed in white; returns its rect."""
        vx, vy, vw, vh = self.guide_video_box()
        pygame.draw.rect(c, (0, 0, 0, 0), (vx, vy, vw, vh))
        pygame.draw.rect(c, rgba(self.b["text"]), (vx - 2, vy - 2, vw + 4, vh + 4), 2)
        return pygame.Rect(vx, vy, vw, vh)

    def draw_guide(self, c, g):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        geo = self._geo()
        top, pad = geo["top"], geo["pad"]

        # The info panel: mark and title side by side, a strip of facts, the synopsis.
        self._light_panel(c, (0, 0, W, top))
        pic = self._picture(c)
        t.draw(c, "guide", self.fb(u(44)), b["watermark"], pic.x - u(18), u(40), align="right")
        mw = self.wordmark(c, pad, u(50), u(34), b["ink"], b["mark"])
        info_w = pic.x - u(30) - pad
        sel = g.selected()
        now = datetime.now(timezone.utc)
        cur = self.app.live.programs(sel)[0] if sel else None
        f_title = self.fb(u(32))
        tx = pad + mw + u(44)
        t.draw(c, t.fit(f_title, cur.title if cur else (sel.name if sel else ""), pic.x - u(30) - tx),
               f_title, b["ink"], tx, u(96))
        strip = pygame.Rect(pad, u(142), info_w, u(38))
        vgrad(c, strip, b["strip"], b["strip"])
        fs = self.f(u(21))
        cw = strip.w // 3
        for i, s in enumerate((stamp(), hours(cur) if cur else "", (cur.rating or "") if cur else "")):
            cx = strip.x + i * cw
            if i:
                pygame.draw.line(c, b["rule"], (cx, strip.y + u(6)), (cx, strip.bottom - u(6)))
            t.draw(c, t.fit(fs, s, cw - u(24)), fs, b["ink"], cx + u(12), strip.y + (strip.h - t.ink(fs)[1]) // 2)
        if cur and cur.description:
            fd = self.f(u(21))
            yy = strip.bottom + u(14)
            for line in t.wrap(fd, cur.description + (f" {cur.category}." if cur.category else ""), info_w, 3):
                t.draw(c, line, fd, b["ink"], pad, yy)
                yy += t.ink(fd)[1] + u(8)

        # The grid: a navy frame, the day and the half hours across the top.
        c.fill(rgba(b["navy"]), (0, top, W, H - top))
        hdr = pygame.Rect(0, top, W, geo["hdr"])
        vgrad(c, hdr, rgba(b["deep"]), rgba(b["navy"]))
        start, end = g.window()
        grid_x = pad + geo["ch_w"]
        grid_w = W - pad - grid_x
        fh = self.fb(u(21))
        ty = hdr.y + (hdr.h - t.ink(fh)[1]) // 2
        day = start.astimezone()
        t.draw(c, f"{day:%a} {day.month}/{day.day}", fh, b["text"], pad + u(10), ty)
        slots = int(g.hours * 2)
        for i in range(slots):
            x = grid_x + int(i * grid_w / slots)
            t.draw(c, ampm(start + timedelta(minutes=30 * i)), fh, b["text"], x + u(8), ty)

        rows = g.filtered()[g.top: g.top + g.rows]
        y = hdr.bottom + u(6)
        rh = geo["row_h"]
        mins = g.hours * 60
        epg = self.app.epg
        f_cell = self.f(u(22))
        for i, ch in enumerate(rows):
            row_sel = g.focus == "grid" and g.top + i == g.cursor
            chr_ = pygame.Rect(pad, y, geo["ch_w"] - u(5), rh - u(5))
            vgrad(c, chr_, rgba(mix(b["chan"], (255, 255, 255), 0.08)), rgba(b["chan"]))
            cy = chr_.y + (chr_.h - t.ink(f_cell)[1]) // 2
            t.draw(c, t.fit(f_cell, f"{ch.number} " + ch.name.upper(), chr_.w - u(16)), f_cell, b["chan_ink"],
                   chr_.x + u(10), cy)
            if self.app.is_favorite(ch):
                pygame.draw.circle(c, b["sel"], (chr_.right - u(10), chr_.y + u(10)), u(4))
            cid = epg.resolve_channel_id(ch.epg_id, ch.name) if epg else None
            progs = epg.programs_in_window(cid, start, end) if cid else []
            if not progs:
                cell = pygame.Rect(grid_x, y, grid_w - u(4), rh - u(5))
                vgrad(c, cell, rgba(b["sel_hi"] if row_sel else b["cell_hi"]), rgba(b["sel"] if row_sel else b["cell"]))
                t.draw(c, "No information", f_cell, b["sel_ink"] if row_sel else b["muted"], cell.x + u(10), cy)
            for p in progs:
                a = max(0.0, (p.start - start).total_seconds() / 60)
                e = min(float(mins), (p.stop - start).total_seconds() / 60)
                if e <= a:
                    continue
                cell = pygame.Rect(grid_x + int(a / mins * grid_w), y, int((e - a) / mins * grid_w) - u(4), rh - u(5))
                on = row_sel and p.start <= max(now, start) < p.stop
                vgrad(c, cell, rgba(b["sel_hi"] if on else b["cell_hi"]), rgba(b["sel"] if on else b["cell"]))
                ink = b["sel_ink"] if on else b["text"]
                x = cell.x + u(8)
                if p.start < start:
                    x += t.draw(c, "<", f_cell, ink if on else b["band_hi"], x, cy) + u(6)
                more = p.stop > end
                avail = cell.right - u(8) - x - (u(16) if more else 0)
                if avail > u(30):
                    t.draw(c, t.fit(f_cell, p.title, avail), f_cell, ink, x, cy)
                if more:
                    t.draw(c, ">", f_cell, ink if on else b["band_hi"], cell.right - u(8), cy, align="right")
            self.hit((pad, y, W - 2 * pad, rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                            setattr(g, "focus", "grid"), g.handle("SELECT")))
            y += rh

        # The bar along the bottom: which channels, and what the colour keys do.
        foot = pygame.Rect(0, H - geo["foot"], W, geo["foot"])
        vgrad(c, foot, rgba(b["navy"]), rgba(b["deep"]))
        fl = self.f(u(19))
        fy = foot.y + (foot.h - t.ink(fl)[1]) // 2
        cat = g.category if g.category != "All" else "All Channels"
        t.draw(c, cat, fl, b["sel"] if g.focus == "category" else b["text"], pad + u(10), fy)
        self.hit((pad, foot.y, u(300), foot.h), lambda: g.handle("THEMES"))
        x = W - pad
        for dot, label in (("yellow", "Themes"), ("green", "+1 day"), ("red", "-1 day")):
            x -= t.width(fl, label)
            t.draw(c, label, fl, b["text"], x, fy)
            x -= u(22)
            pygame.draw.circle(c, DOTS[dot], (x + u(7), fy + t.ink(fl)[1] // 2), u(8))
            x -= u(30)

    # ── Menu ──────────────────────────────────────────────────────────────

    def draw_menu(self, c, m):
        """A setup page as the box had them: the list down the left, the chosen
        row explained on the right, the picture kept top-right."""
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        pad = u(40)
        self._light_panel(c, (0, 0, W, H))
        pic = self._picture(c)
        t.draw(c, "menu", self.fb(u(44)), b["watermark"], pic.x - u(18), u(40), align="right")
        mw = self.wordmark(c, pad, u(50), u(34), b["ink"], b["mark"])
        f_title = self.fb(u(30))
        tx = pad + mw + u(44)
        t.draw(c, t.fit(f_title, m.title.title(), pic.x - u(30) - tx), f_title, b["ink"], tx, u(98))
        t.draw(c, stamp(), self.f(u(20)), b["ink_soft"], pad, u(112))

        lx, ly, lw = pad, u(170), u(330)
        rh = u(42)
        n = len(m.items)
        n_vis = max(1, (H - ly - u(90)) // rh)
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        f_row = self.f(u(22))
        y = ly
        for i in range(first, min(n, first + n_vis)):
            it = m.items[i]
            row = pygame.Rect(lx, y, lw, rh - u(4))
            sel = i == m.cursor
            if sel:
                vgrad(c, row, rgba(b["band_hi"]), rgba(b["band"]), radius=u(4))
            ink = (b["text"] if sel else b["ink"]) if it.enabled else b["ink_soft"]
            t.draw(c, t.fit(f_row, it.label, lw - u(28)), f_row, ink, row.x + u(14),
                   row.y + (row.h - t.ink(f_row)[1]) // 2)
            self.hit(row, lambda i=i: m.activate(i))
            y += rh
        if n > n_vis:
            t.draw(c, f"{first + 1}-{min(n, first + n_vis)} of {n}", self.f(u(17)), b["ink_soft"], lx, y + u(6))

        it = m.items[m.cursor] if 0 <= m.cursor < n else None
        if it:
            rx = lx + lw + u(50)
            box = pygame.Rect(rx, pic.bottom + u(24), W - pad - rx, u(150))
            panel(c, box, rgba(b["navy"], 235), rgba(b["deep"], 245), radius=u(8), edge=rgba(b["band"]))
            fbg = self.fb(u(26))
            t.draw(c, t.fit(fbg, it.label, box.w - u(40)), fbg, b["text"], box.x + u(20), box.y + u(18))
            if it.value:
                v = it.value()
                fv = self.f(u(22))
                t.draw(c, t.fit(fv, f"<  {v}  >" if it.adjust else v, box.w - u(40)), fv, b["sel"],
                       box.x + u(20), box.y + u(64))
                hint = "LEFT / RIGHT to change" if it.adjust else "SELECT to change"
            elif it.submenu:
                hint = "SELECT to open"
            else:
                hint = "SELECT to choose" if it.enabled else "Not available"
            t.draw(c, hint, self.f(u(18)), b["muted"], box.x + u(20), box.bottom - u(40))
        t.draw(c, "SELECT: choose    BACK: up a level    EXIT: close", self.f(u(17)), b["ink_soft"],
               pad, H - u(56))

    # ── Mini guide ────────────────────────────────────────────────────────

    def draw_miniguide(self, c, mg):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        pad = u(40)
        rows = mg.rows()
        rh = u(44)
        r = pygame.Rect(0, 0, W, u(44) + rh * len(rows) + u(12))
        r.bottom = H
        vgrad(c, r, rgba(b["band_hi"], 215), rgba(b["navy"], 240))
        pygame.draw.rect(c, b["band_hi"], (0, r.y, W, u(3)))
        fh = self.fb(u(20))
        t.draw(c, "Mini Guide", fh, b["text"], pad, r.y + u(12))
        t.draw(c, stamp(), fh, b["text"], W - pad, r.y + u(12), align="right")
        f_row = self.f(u(21))
        y = r.y + u(44)
        for ch, cur, nxt, sel in rows:
            row = pygame.Rect(pad, y, W - 2 * pad, rh - u(5))
            vgrad(c, row, rgba(b["sel_hi"] if sel else b["cell_hi"]), rgba(b["sel"] if sel else b["cell"]))
            ink = b["sel_ink"] if sel else b["text"]
            ty = row.y + (row.h - t.ink(f_row)[1]) // 2
            t.draw(c, t.fit(f_row, f"{ch.number} {ch.name.upper()}", u(230)), f_row, ink, row.x + u(12), ty)
            mid = row.x + u(260)
            t.draw(c, t.fit(f_row, cur.title if cur else "No information", u(440)), f_row, ink, mid, ty)
            if nxt:
                t.draw(c, t.fit(f_row, f"{ampm(nxt.start)}  {nxt.title}", row.right - mid - u(470)), f_row,
                       ink if sel else b["muted"], mid + u(460), ty)
            self.hit(row, lambda ch=ch: mg.pick(ch))
            y += rh

    # ── Boot ──────────────────────────────────────────────────────────────

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        stage = boot.stage()
        vgrad(c, (0, 0, W, H), rgba(b["deep"]), rgba(b["navy"]))
        cx, cy = W // 2, int(H * 0.36)
        glow = pygame.Surface((W, H), pygame.SRCALPHA)       # the lit-up mark of a box starting
        for k in range(6, 0, -1):
            pygame.draw.circle(glow, (*b["band_hi"], 16), (cx, cy), u(60) * k)
        c.blit(glow, (0, 0))
        size = u(64)
        mw = self.measure(self.wordmark, size, b["text"], b["band_hi"])
        self.wordmark(c, (W - mw) // 2, cy - size // 2, size, b["text"], b["band_hi"])
        if stage == "starting":
            return
        caption = {"signal": "Step 1 of 2: Acquiring satellite signal...",
                   "guide": "Step 2 of 2: Downloading guide data...", "done": "Ready"}[stage]
        t.draw(c, caption, self.f(u(24)), b["text"], W // 2, int(H * 0.60), align="center")
        bar = pygame.Rect(W // 2 - u(280), int(H * 0.68), u(560), u(12))
        age = time.monotonic() - boot.start
        frac = {"signal": 0.15 + 0.25 * min(1, age / 4), "guide": 0.45 + 0.45 * min(1, age / 8),
                "done": 1.0}[stage]
        self.progress(c, bar, frac, rgba(b["deep"]), rgba(b["sel"]))
        t.draw(c, "Press any button to skip", self.f(u(17)), b["muted"], W // 2, H - u(60), align="center")


class InDirect(InDirectHD):
    """The SD era: the same screens on a dark navy ground, gold selection, 4:3."""
    name = "indirect"
    label = "InDirecTV"
    canvas = (640, 480)
    guide_rows = 5
    SD = True
    NATIVE = {"bg": [6, 22, 72], "accent": [30, 84, 190], "accent2": [250, 200, 36],
              "text": [255, 255, 255], "chnum": [255, 255, 255]}

    def roles(self, b):
        r = super().roles(b)
        bg, acc, text = b["bg"], b["accent"], b["text"]
        # No light panels in the SD era: the info area is navy fading to black.
        r.update(panel_top=mix(bg, acc, 0.35), panel_bot=mix(bg, (0, 0, 0), 0.45),
                 strip=rgba(acc, 70), rule=mix(bg, acc, 0.6),
                 ink=text, ink_soft=mix(text, acc, 0.4), watermark=mix(bg, acc, 0.55),
                 sel_ink=(20, 16, 0), sel_hi=mix(b["accent2"], (255, 255, 255), 0.3))
        return r

    def _light_panel(self, c, rect):
        vgrad(c, rect, rgba(self.b["panel_top"]), rgba(self.b["panel_bot"]))
