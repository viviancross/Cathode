"""InDirect: a mid-2000s DirecTV-style box. InDirect HD follows the HR20
(light gradient info panel, navy grid, amber selection); InDirect (SD)
follows the D10/R15 era: saturated blue, yellow selection, 4:3.

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


DOTS = {"red": (214, 44, 36), "green": (58, 170, 64), "yellow": (238, 196, 34), "blue": (40, 104, 212)}


class InDirectHD(BoxSkin):
    name = "indirect_hd"
    label = "InDirect HD"
    canvas = (1280, 720)
    browse_style = "mini"           # BROWSE opens the mini guide
    guide_hours = 2
    guide_rows = 6
    SD = False
    NATIVE = {"bg": [10, 32, 88], "accent": [36, 112, 206], "accent2": [248, 168, 28],
              "text": [255, 255, 255], "chnum": [240, 244, 255]}

    def roles(self, b):
        bg, acc, sel, text = b["bg"], b["accent"], b["accent2"], b["text"]
        return {
            "navy": bg, "deep": mix(bg, (0, 0, 0), 0.35), "band": acc,
            "band_hi": mix(acc, (255, 255, 255), 0.25),
            "cell": mix(bg, acc, 0.55), "cell_hi": mix(bg, acc, 0.75),
            "chan": mix(bg, (0, 0, 0), 0.15), "chan_ink": text, "sel": sel, "sel_ink": (24, 20, 10),
            "text": text, "muted": mix(text, acc, 0.45),
            "panel_top": mix((255, 255, 255), acc, 0.04), "panel_bot": mix((255, 255, 255), acc, 0.32),
            "ink": mix(bg, (0, 0, 0), 0.2), "ink_soft": mix(bg, acc, 0.45),
            "watermark": mix((255, 255, 255), acc, 0.18),
        }

    # Geometry, relative to the canvas.
    def u(self, v) -> int:
        """A length given in 720-line units, scaled to this canvas."""
        return int(v * self.canvas[1] / 720)

    # ── Wordmark ──────────────────────────────────────────────────────────

    def wordmark(self, c, x, y, size, ink, swoosh):
        """'InDirect' with an orbit arc. Our own mark, not anyone's logo."""
        f = self.fb(size)
        w = self.text.draw(c, "InDirect", f, ink, x, y)
        h = self.text.ink(f)[1]
        arc = pygame.Rect(x - size // 3, y - size // 4, w + size // 2, h + size // 2)
        pygame.draw.arc(c, swoosh, arc, 3.6, 6.0, max(2, size // 9))
        return w

    # ── Live: banner ──────────────────────────────────────────────────────

    def draw_live(self, c, live):
        W, H = self.canvas
        if live.message:
            self._message(c, live.message)
            return
        if live.standby and live.phase != "cover":
            self._signal_loss(c)
        if (live.banner_visible() or live.phase == "cover") and live.channel:
            cur, nxt = live.programs()
            self._banner(c, live.channel, cur, nxt, full=live.banner_full)
        if live.digits:
            self._digits(c, live.digits)
        if live.volume_visible():
            self._volume(c, W // 2, int(H * 0.62))
        if live.trick_visible() and live.phase != "cover":
            self._trick(c, live.trick_state())

    def _digits(self, c, digits):
        W = self.canvas[0]
        b, u = self.b, self.u
        f = self.fb(u(40))
        text = digits + "-" * (3 - len(digits))
        r = pygame.Rect(0, 0, self.text.width(f, text) + u(40), u(70))
        r.topright = (W - u(40), u(40))
        panel(c, r, rgba(b["band_hi"], 240), rgba(b["navy"], 240), radius=u(10), edge=rgba(b["band_hi"]))
        self.text.draw(c, text, f, b["text"], r.centerx, r.y + (r.h - self.text.ink(f)[1]) // 2, align="center")

    def _banner(self, c, ch, cur, nxt, full=False, tag=None):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        m = u(36)
        bh = u(150)
        r = pygame.Rect(m, H - bh - u(30), W - 2 * m, bh)
        if full and cur and cur.description:
            f = self.f(u(20))
            lines = t.wrap(f, cur.description, r.w - u(40), 3)
            dh = u(24) + len(lines) * (t.ink(f)[1] + u(10))
            d = pygame.Rect(r.x, r.y - dh - u(10), r.w, dh)
            panel(c, d, rgba(b["panel_top"], 245), rgba(b["panel_bot"], 245), radius=u(10))
            y = d.y + u(14)
            for line in lines:
                t.draw(c, line, f, b["ink"], d.x + u(20), y)
                y += t.ink(f)[1] + u(10)
        panel(c, r, rgba(b["navy"], 236), rgba(b["deep"], 246), radius=u(12),
              edge=rgba(b["band_hi"], 220))
        if tag:
            self.chip(c, r.x + u(16), r.y - u(34), tag, self.fb(u(16)), rgba(b["sel"]), b["sel_ink"])

        # Number block.
        nb = pygame.Rect(r.x + u(12), r.y + u(12), u(150), r.h - u(24))
        vgrad(c, nb, rgba(b["band_hi"]), rgba(b["band"]), radius=u(8))
        f_num = self.fb(u(46))
        t.draw(c, str(ch.number), f_num, b["text"], nb.centerx, nb.y + u(14), align="center")
        epg = self.app.epg
        url = epg.icon_url(epg.resolve_channel_id(ch.epg_id, ch.name)) if epg else ""
        logo = self.logo(url or ch.logo, nb.w - u(20), u(40))
        if logo:
            c.blit(logo, logo.get_rect(midbottom=(nb.centerx, nb.bottom - u(10))))
        else:
            fs = self.f(u(16))
            t.draw(c, t.fit(fs, ch.name.upper(), nb.w - u(12)), fs, b["text"], nb.centerx,
                   nb.bottom - u(30), align="center")

        x = nb.right + u(22)
        right = r.right - u(200)
        f_title, f_line = self.fb(u(32)), self.f(u(20))
        title = cur.title if cur else ch.name
        t.draw(c, t.fit(f_title, title, right - x), f_title, b["text"], x, r.y + u(18))
        if cur:
            bits = [hours(cur)] + [s for s in (cur.episode, cur.rating) if s]
            t.draw(c, t.fit(f_line, "   ".join(bits), right - x), f_line, b["muted"], x, r.y + u(62))
            bar = pygame.Rect(x, r.y + u(98), min(u(420), right - x - u(120)), u(10))
            now = datetime.now(timezone.utc)
            self.progress(c, bar, cur.progress_at(now), rgba(b["deep"]), rgba(b["sel"]))
            left = max(0, int((cur.stop - now).total_seconds() // 60))
            t.draw(c, f"{left} min left", self.f(u(17)), b["muted"], bar.right + u(14), bar.y - u(4))
        if nxt:
            fs = self.f(u(17))
            t.draw(c, t.fit(fs, f"Next: {nxt.title}  {ampm(nxt.start)}", right - x), fs, b["muted"],
                   x, r.y + u(120))
        now_local = datetime.now()
        t.draw(c, ampm(now_local), self.fb(u(30)), b["text"], r.right - u(20), r.y + u(18), align="right")
        t.draw(c, now_local.strftime("%a %b ") + str(now_local.day), self.f(u(18)), b["muted"],
               r.right - u(20), r.y + u(62), align="right")
        t.draw(c, "INFO for more", self.f(u(15)), b["muted"], r.right - u(20), r.bottom - u(30), align="right")
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    # ── Signal loss ───────────────────────────────────────────────────────

    def _signal_loss(self, c):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        c.fill((0, 0, 0, 255))
        r = pygame.Rect(0, 0, int(W * 0.62), u(230))
        r.center = (W // 2, int(H * 0.42))
        panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=u(12), edge=rgba(b["band"]))
        band = pygame.Rect(r.x, r.y, r.w, u(56))
        vgrad(c, band, rgba(b["band_hi"]), rgba(b["band"]), radius=u(12))
        pygame.draw.rect(c, b["band"], (band.x, band.bottom - u(12), band.w, u(12)))
        t.draw(c, "Searching for Signal", self.fb(u(26)), b["text"], band.x + u(22), band.y + u(15))
        f = self.f(u(20))
        y = band.bottom + u(22)
        for line in t.wrap(f, "Searching for the signal on this channel. The stream isn't sending a "
                              "picture; it will keep trying.", r.w - u(44), 3):
            t.draw(c, line, f, b["ink"], r.x + u(22), y)
            y += t.ink(f)[1] + u(10)
        t.draw(c, "(771)", self.fb(u(18)), b["ink_soft"], r.right - u(22), r.bottom - u(36), align="right")

    # ── Guide ─────────────────────────────────────────────────────────────

    def _geo(self):
        W, H = self.canvas
        u = self.u
        top = u(300)
        hdr = u(40)
        foot = u(40)
        rows = self.guide_rows
        row_h = (H - top - hdr - foot) // rows
        ch_w = int(W * 0.17)
        return dict(top=top, hdr=hdr, foot=foot, row_h=row_h, ch_w=ch_w, pad=u(30))

    def guide_video_box(self):
        W, H = self.canvas
        u = self.u
        h = u(230)
        w = int(h * 16 / 9)
        return (W - w - u(30), u(36), w, h)

    def draw_guide(self, c, g):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        geo = self._geo()
        top, pad = geo["top"], geo["pad"]

        # Info panel: light gradient, title, a blue band of facts, the synopsis.
        vgrad(c, (0, 0, W, top), rgba(b["panel_top"]), rgba(b["panel_bot"]))
        vx, vy, vw, vh = self.guide_video_box()
        t.draw(c, "guide", self.fb(u(46)), b["watermark"], vx - u(24), u(40), align="right")
        self.wordmark(c, pad, u(24), u(30), b["ink"], b["band"])
        pygame.draw.rect(c, (0, 0, 0, 0), (vx, vy, vw, vh))       # the live picture
        pygame.draw.rect(c, rgba(b["text"]), (vx - 2, vy - 2, vw + 4, vh + 4), 2)

        info_w = vx - pad - u(30)
        sel = g.selected()
        now = datetime.now(timezone.utc)
        cur = self.app.live.programs(sel)[0] if sel else None
        y = u(78)
        f_title = self.fb(u(30))
        t.draw(c, t.fit(f_title, cur.title if cur else (sel.name if sel else ""), info_w), f_title,
               b["ink"], pad, y)
        band = pygame.Rect(pad, y + u(44), info_w, u(34))
        vgrad(c, band, rgba(b["band_hi"]), rgba(b["band"]), radius=u(4))
        local = datetime.now()
        facts = [local.strftime("%a ") + ampm(local)]
        if cur:
            facts += [hours(cur)] + [s for s in (cur.rating,) if s]
        fb = self.f(u(19))
        t.draw(c, t.fit(fb, "     ".join(facts), band.w - u(24)), fb, b["text"], band.x + u(12),
               band.y + (band.h - t.ink(fb)[1]) // 2)
        if cur and cur.description:
            fd = self.f(u(19))
            yy = band.bottom + u(12)
            for line in t.wrap(fd, cur.description + (f" {cur.category}." if cur.category else ""),
                               info_w, 3):
                t.draw(c, line, fd, b["ink"], pad, yy)
                yy += t.ink(fd)[1] + u(8)

        # Grid.
        c.fill(rgba(b["navy"]), (0, top, W, H - top))
        hdr = pygame.Rect(0, top, W, geo["hdr"])
        vgrad(c, hdr, rgba(b["navy"]), rgba(b["deep"]))
        start, end = g.window()
        grid_x = pad + geo["ch_w"]
        grid_w = W - pad - grid_x
        fh = self.fb(u(19))
        ty = hdr.y + (hdr.h - t.ink(fh)[1]) // 2
        day = start.astimezone()
        cat = g.category if g.category != "All" else f"{day:%a} {day.month}/{day.day}"
        t.draw(c, t.fit(fh, cat, geo["ch_w"] - u(10)), fh,
               b["sel"] if g.focus == "category" else b["text"], pad + u(6), ty)
        self.hit((pad, hdr.y, geo["ch_w"], hdr.h), lambda: g.handle("THEMES"))
        slots = g.hours * 2
        for i in range(slots):
            x = grid_x + int(i * grid_w / slots)
            t.draw(c, ampm(start + timedelta(minutes=30 * i)), fh, b["text"], x + u(8), ty)

        rows = g.filtered()[g.top: g.top + g.rows]
        y = hdr.bottom + u(4)
        rh = geo["row_h"]
        mins = g.hours * 60
        epg = self.app.epg
        f_cell, f_ch = self.f(u(20)), self.fb(u(19))
        for i, ch in enumerate(rows):
            row_sel = g.focus == "grid" and g.top + i == g.cursor
            chr_ = pygame.Rect(pad, y, geo["ch_w"] - u(4), rh - u(4))
            pygame.draw.rect(c, b["chan"], chr_)
            label = f"{ch.number} " + ch.name.upper()
            t.draw(c, t.fit(f_ch, label, chr_.w - u(14)), f_ch, b["chan_ink"], chr_.x + u(8),
                   chr_.y + (chr_.h - t.ink(f_ch)[1]) // 2)
            if self.app.is_favorite(ch):
                pygame.draw.circle(c, b["sel"], (chr_.right - u(10), chr_.y + u(10)), u(4))
            cid = epg.resolve_channel_id(ch.epg_id, ch.name) if epg else None
            progs = epg.programs_in_window(cid, start, end) if cid else []
            if not progs:
                cell = pygame.Rect(grid_x, y, grid_w - u(2), rh - u(4))
                pygame.draw.rect(c, b["sel"] if row_sel else b["cell"], cell)
                t.draw(c, "No information", f_cell, b["sel_ink"] if row_sel else b["muted"], cell.x + u(10),
                       cell.y + (cell.h - t.ink(f_cell)[1]) // 2)
            for p in progs:
                a = max(0.0, (p.start - start).total_seconds() / 60)
                e = min(float(mins), (p.stop - start).total_seconds() / 60)
                if e <= a:
                    continue
                cell = pygame.Rect(grid_x + int(a / mins * grid_w), y,
                                   int((e - a) / mins * grid_w) - u(3), rh - u(4))
                on = row_sel and p.start <= max(now, start) < p.stop
                if on:
                    vgrad(c, cell, rgba(mix(b["sel"], (255, 255, 255), 0.25)), rgba(b["sel"]))
                else:
                    vgrad(c, cell, rgba(b["cell_hi"]), rgba(b["cell"]))
                ink = b["sel_ink"] if on else b["text"]
                txt = ("< " if p.start < start else "") + p.title
                more = p.stop > end
                avail = cell.w - u(16) - (u(18) if more else 0)
                if avail > u(30):
                    t.draw(c, t.fit(f_cell, txt, avail), f_cell, ink, cell.x + u(8),
                           cell.y + (cell.h - t.ink(f_cell)[1]) // 2)
                if more:
                    t.draw(c, ">", f_cell, ink, cell.right - u(8), cell.y + (cell.h - t.ink(f_cell)[1]) // 2,
                           align="right")
            self.hit((pad, y, W - 2 * pad, rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                            setattr(g, "focus", "grid"), g.handle("SELECT")))
            y += rh

        # Legend: the coloured keys, as the remote had them.
        fl = self.f(u(17))
        x = pad
        fy = H - geo["foot"] + (geo["foot"] - t.ink(fl)[1]) // 2
        for dot, label in (("red", "REW -1 day"), ("green", "FF +1 day"), ("yellow", "THEMES genres"),
                           ("blue", "PAGE up/down")):
            pygame.draw.circle(c, DOTS[dot], (x + u(8), fy + t.ink(fl)[1] // 2), u(7))
            x += u(22) + t.draw(c, label, fl, b["muted"], x + u(22), fy) + u(30)

    # ── Menu ──────────────────────────────────────────────────────────────

    def draw_menu(self, c, m):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        self.dim(c, 110)
        pw = int(W * 0.40)
        r = pygame.Rect(u(40), u(40), pw, H - u(80))
        panel(c, r, rgba(b["panel_top"], 248), rgba(b["panel_bot"], 248), radius=u(12),
              edge=rgba(b["band"]))
        head = pygame.Rect(r.x, r.y, r.w, u(70))
        vgrad(c, head, rgba(b["band_hi"]), rgba(b["band"]), radius=u(12))
        pygame.draw.rect(c, b["band"], (head.x, head.bottom - u(12), head.w, u(12)))
        t.draw(c, t.fit(self.fb(u(28)), m.title.title(), head.w - u(40)), self.fb(u(28)), b["text"],
               head.x + u(22), head.y + u(20))
        rh = u(48)
        n_vis = (r.bottom - head.bottom - u(60)) // rh
        n = len(m.items)
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        f_row = self.f(u(22))
        y = head.bottom + u(12)
        for i in range(first, min(n, first + n_vis)):
            it = m.items[i]
            row = pygame.Rect(r.x + u(12), y, r.w - u(24), rh - u(6))
            sel = i == m.cursor
            if sel:
                vgrad(c, row, rgba(mix(b["sel"], (255, 255, 255), 0.3)), rgba(b["sel"]), radius=u(6))
            ink = (b["sel_ink"] if sel else b["ink"]) if it.enabled else b["ink_soft"]
            ty = row.y + (row.h - t.ink(f_row)[1]) // 2
            label = t.fit(f_row, it.label, row.w - u(160))
            t.draw(c, label, f_row, ink, row.x + u(14), ty)
            if it.value:
                v = it.value()
                v = f"< {v} >" if sel and it.adjust else v
                t.draw(c, t.fit(f_row, v, u(200)), f_row, b["sel_ink"] if sel else b["ink_soft"],
                       row.right - u(14), ty, align="right")
            elif it.submenu:
                t.draw(c, ">", f_row, ink, row.right - u(14), ty, align="right")
            self.hit(row, lambda i=i: m.activate(i))
            y += rh
        t.draw(c, "SELECT: choose    BACK: up a level    EXIT: close", self.f(u(15)), b["ink_soft"],
               r.x + u(22), r.bottom - u(36))

    # ── Mini guide ────────────────────────────────────────────────────────

    def draw_miniguide(self, c, mg):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        rows = mg.rows()
        rh = u(46)
        r = pygame.Rect(u(36), 0, W - u(72), u(56) + rh * len(rows) + u(16))
        r.bottom = H - u(30)
        panel(c, r, rgba(b["navy"], 240), rgba(b["deep"], 246), radius=u(12), edge=rgba(b["band_hi"]))
        head = pygame.Rect(r.x, r.y, r.w, u(48))
        vgrad(c, head, rgba(b["band_hi"]), rgba(b["band"]), radius=u(12))
        pygame.draw.rect(c, b["band"], (head.x, head.bottom - u(12), head.w, u(12)))
        fh = self.fb(u(20))
        t.draw(c, "Mini Guide", fh, b["text"], head.x + u(18), head.y + u(13))
        t.draw(c, ampm(datetime.now()), fh, b["text"], head.right - u(18), head.y + u(13), align="right")
        f_row, f_ch = self.f(u(20)), self.fb(u(20))
        y = head.bottom + u(8)
        for ch, cur, nxt, sel in rows:
            row = pygame.Rect(r.x + u(12), y, r.w - u(24), rh - u(6))
            if sel:
                vgrad(c, row, rgba(mix(b["sel"], (255, 255, 255), 0.25)), rgba(b["sel"]), radius=u(5))
            else:
                vgrad(c, row, rgba(b["cell_hi"]), rgba(b["cell"]), radius=u(5))
            ink = b["sel_ink"] if sel else b["text"]
            ty = row.y + (row.h - t.ink(f_row)[1]) // 2
            t.draw(c, t.fit(f_ch, f"{ch.number} {ch.name.upper()}", u(220)), f_ch, ink, row.x + u(12), ty)
            mid = row.x + u(250)
            t.draw(c, t.fit(f_row, cur.title if cur else "No information", u(430)), f_row, ink, mid, ty)
            if nxt:
                t.draw(c, t.fit(f_row, f"{ampm(nxt.start)}  {nxt.title}", row.right - mid - u(460)), f_row,
                       ink if sel else b["muted"], mid + u(450), ty)
            self.hit(row, lambda ch=ch: mg.pick(ch))
            y += rh

    # ── Boot ──────────────────────────────────────────────────────────────

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        stage = boot.stage()
        vgrad(c, (0, 0, W, H), rgba(b["deep"]), rgba(b["band"]))
        if stage == "starting":
            return
        mark_w = self.text.width(self.fb(u(72)), "InDirect")
        self.wordmark(c, (W - mark_w) // 2, int(H * 0.30), u(72), b["text"], b["band_hi"])
        caption = {"signal": "Acquiring satellite signal...", "guide": "Downloading guide data...",
                   "done": "Ready"}[stage]
        t.draw(c, caption, self.f(u(26)), b["text"], W // 2, int(H * 0.56), align="center")
        bar = pygame.Rect(W // 2 - u(280), int(H * 0.64), u(560), u(14))
        age = time.monotonic() - boot.start
        frac = {"signal": 0.15 + 0.25 * min(1, age / 4), "guide": 0.45 + 0.45 * min(1, age / 8),
                "done": 1.0}[stage]
        self.progress(c, bar, frac, rgba(b["deep"]), rgba(b["sel"]))
        t.draw(c, "Press any button to skip", self.f(u(17)), b["muted"], W // 2, H - u(60), align="center")


class InDirect(InDirectHD):
    """The SD era: saturated blue everywhere, yellow selection, 4:3."""
    name = "indirect"
    label = "InDirect"
    canvas = (640, 480)
    guide_rows = 5
    SD = True
    NATIVE = {"bg": [0, 30, 120], "accent": [28, 96, 222], "accent2": [255, 214, 0],
              "text": [255, 255, 255], "chnum": [255, 255, 255]}

    def roles(self, b):
        r = super().roles(b)
        # No light panels in the SD era: the info area is blue like the rest.
        r.update(panel_top=mix(b["accent"], (255, 255, 255), 0.10), panel_bot=b["bg"],
                 ink=b["text"], ink_soft=mix(b["text"], b["accent"], 0.4),
                 watermark=mix(b["accent"], (255, 255, 255), 0.25),
                 chan=mix(b["accent"], (255, 255, 255), 0.55), chan_ink=mix(b["bg"], (0, 0, 0), 0.3),
                 sel_ink=(0, 0, 0))
        return r
