"""Plate Network: a mid-2000s Dish Network-style box. Plate Network HD follows
the ViP622/722: a navy info area over silver guide cells, green selection,
grey dialogs with pill buttons, list menus numbered down the right. Plate
Network (SD) follows the 301/522 era: capsule shapes, blue cells, a pale
selection, 4:3. RIGHT on live TV browses, as Dish's remote did."""

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
    NATIVE = {"bg": [16, 40, 100], "accent": [96, 150, 214], "accent2": [52, 150, 60],
              "text": [255, 255, 255], "chnum": [16, 32, 82]}

    def roles(self, b):
        bg, acc, sel, text = b["bg"], b["accent"], b["accent2"], b["text"]
        navy = mix(bg, (0, 0, 0), 0.3)
        return {
            "navy": bg, "deep": mix(bg, (0, 0, 0), 0.4), "sky": acc,
            "info_top": mix(bg, acc, 0.22), "info_bot": bg, "info_ink": text,
            "text": text, "muted": mix(text, acc, 0.4),
            "cell_top": (242, 244, 248), "cell_bot": (190, 198, 214), "cell_ink": navy,
            "chan_top": (226, 230, 238), "chan_bot": (170, 180, 200), "chan_ink": navy, "edge": navy,
            "sel": sel, "sel_hi": mix(sel, (255, 255, 255), 0.3), "sel_ink": text,
            "cursor": (242, 160, 32), "cursor_hi": (252, 200, 96), "cursor_ink": (36, 24, 0),
            "hdr_top": mix(bg, acc, 0.5), "hdr_bot": mix(bg, acc, 0.2),
            "panel_top": (240, 242, 246), "panel_bot": (198, 204, 216), "ink": navy,
            "ink_soft": mix(bg, acc, 0.35),
            "banner_top": (242, 244, 248), "banner_bot": (190, 198, 214), "banner_ink": navy,
            "banner_soft": mix(bg, acc, 0.35),
            "pill": mix(bg, acc, 0.45), "pill_hi": mix(bg, acc, 0.65), "pill_ink": text,
            "tab": sel, "tab_ink": text, "dish": (210, 30, 40),
        }

    def u(self, v) -> int:
        return int(v * self.canvas[1] / 720)

    def menu_cols(self, menu):
        return 3 if menu.title == "MAIN MENU" and len(menu.pages) == 1 else 1

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

    # ── Live: banner ──────────────────────────────────────────────────────

    def _digits(self, c, digits):
        W = self.canvas[0]
        b, u = self.b, self.u
        f = self.fb(u(40))
        text = digits + "-" * (3 - len(digits))
        r = pygame.Rect(0, 0, self.text.width(f, text) + u(40), u(70))
        r.topright = (W - u(40), u(150))
        panel(c, r, rgba(b["cell_top"]), rgba(b["cell_bot"]), radius=u(10), edge=rgba(b["edge"]))
        self.text.draw(c, text, f, b["cell_ink"], r.centerx, r.y + (r.h - self.text.ink(f)[1]) // 2,
                       align="center")

    def _banner(self, c, ch, cur, nxt, full=False, tag=None, bottom=False):
        """The channel banner, a silver capsule across the top as the box drew
        it; BROWSE puts the same thing along the bottom."""
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        m = u(24)
        r = pygame.Rect(m, u(20), W - 2 * m, u(112))
        if bottom:
            r.bottom = H - u(24)
        radius = u(28) if self.SD else u(16)
        panel(c, r, rgba(b["banner_top"], 238), rgba(b["banner_bot"], 242), radius=radius, edge=rgba(b["edge"], 220))
        if tag:
            self.chip(c, r.x + u(18), r.y - u(30) if bottom else r.bottom + u(6), tag, self.fb(u(16)),
                      rgba(b["tab"]), b["tab_ink"])
        # Channel: number over call sign, in its own box at the left.
        nb = pygame.Rect(r.x + u(12), r.y + u(12), u(150), r.h - u(24))
        vgrad(c, nb, rgba(b["hdr_top"]), rgba(b["hdr_bot"]), radius=u(18) if self.SD else u(8))
        t.draw(c, str(ch.number), self.fb(u(42)), b["text"], nb.centerx, nb.y + u(8), align="center")
        fs = self.fb(u(16))
        t.draw(c, t.fit(fs, ch.name.upper(), nb.w - u(12)), fs, b["text"], nb.centerx, nb.bottom - u(26),
               align="center")
        x = nb.right + u(20)
        right = r.right - u(230)
        f_title, f_line = self.fb(u(28)), self.f(u(20))
        ink, soft = b["banner_ink"], b["banner_soft"]
        t.draw(c, t.fit(f_title, cur.title if cur else ch.name, right - x), f_title, ink, x, r.y + u(14))
        now = datetime.now(timezone.utc)
        if cur:
            bits = [f"{ampm(cur.start)} - {ampm(cur.stop)}"] + [s for s in (cur.rating, cur.episode) if s]
            t.draw(c, t.fit(f_line, "   ".join(bits), right - x), f_line, soft, x, r.y + u(52))
        if nxt:
            fn = self.f(u(17))
            t.draw(c, t.fit(fn, f"Next: {ampm(nxt.start)}  {nxt.title}", right - x), fn, soft, x, r.y + u(82))
        rx = r.right - u(20)
        t.draw(c, when(), self.fb(u(19)), ink, rx, r.y + u(14), align="right")
        if cur:
            t.draw(c, time_left(cur, now), self.f(u(18)), soft, rx, r.y + u(46), align="right")
        t.draw(c, "INFO for details", self.f(u(15)), soft, rx, r.bottom - u(28), align="right")
        if full and cur and cur.description:
            f = self.f(u(20))
            lines = t.wrap(f, cur.description, r.w - u(40), 3)
            d = pygame.Rect(r.x, 0, r.w, u(24) + len(lines) * (t.ink(f)[1] + u(9)))
            d.y = r.y - d.h - u(8) if bottom else r.bottom + u(8)
            panel(c, d, rgba(b["banner_top"], 238), rgba(b["banner_bot"], 242), radius=radius, edge=rgba(b["edge"], 220))
            y = d.y + u(14)
            for line in lines:
                t.draw(c, line, f, ink, d.x + u(20), y)
                y += t.ink(f)[1] + u(9)
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def draw_browse(self, c, br):
        if br.channel:
            cur, nxt = br.program()
            tag = "BROWSE  -  SELECT to watch" + (f"  (+{br.ahead})" if br.ahead else "")
            self._banner(c, br.channel, cur, nxt, tag=tag, bottom=True)

    # ── Dialogs and the signal meter ──────────────────────────────────────

    def _dialog(self, c, r, title, code=None) -> int:
        """The box's grey dialog with its title in a pill; returns the y below
        the title."""
        b, t, u = self.b, self.text, self.u
        panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=u(20), edge=rgba((255, 255, 255)), edge_w=u(3))
        pill = pygame.Rect(r.x + u(30), r.y + u(16), r.w - u(60) - (u(92) if code else 0), u(44))
        vgrad(c, pill, rgba(b["pill_hi"]), rgba(b["pill"]), radius=u(10))
        f = self.fb(u(24))
        t.draw(c, t.fit(f, title, pill.w - u(20)), f, b["pill_ink"], pill.centerx,
               pill.y + (pill.h - t.ink(f)[1]) // 2, align="center")
        if code:
            cp = pygame.Rect(pill.right + u(12), pill.y, u(80), pill.h)
            pygame.draw.rect(c, b["panel_top"], cp, border_radius=u(10))
            pygame.draw.rect(c, b["ink_soft"], cp, 2, border_radius=u(10))
            fc = self.f(u(20))
            t.draw(c, code, fc, b["ink_soft"], cp.centerx, cp.y + (cp.h - t.ink(fc)[1]) // 2, align="center")
        return pill.bottom

    def _meter(self, c, rect, level, locked):
        """The signal-strength bar from the box's Point Dish screen: a scale
        to 125, red until the signal locks."""
        b, t, u = self.b, self.text, self.u
        fs = self.f(u(16))
        for k in range(6):
            t.draw(c, str(k * 25), fs, b["ink"], rect.x + int(rect.w * k / 5), rect.y, align="center")
        bar = pygame.Rect(rect.x, rect.y + u(24), rect.w, u(22))
        pygame.draw.rect(c, b["edge"], bar)
        col = (56, 170, 60) if locked else (168, 24, 24)
        pygame.draw.rect(c, col, (bar.x, bar.y, int(bar.w * min(125, level) / 125), bar.h))
        fl = self.fb(u(18))
        t.draw(c, "Locked" if locked else "Not Locked", fl, col, rect.x, bar.bottom + u(8))
        t.draw(c, f"signal strength   {level}", fl, col, rect.right, bar.bottom + u(8), align="right")

    def _signal_loss(self, c):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        c.fill((0, 0, 0, 255))
        r = pygame.Rect(0, 0, int(W * 0.66), u(290))
        r.center = (W // 2, int(H * 0.45))
        y = self._dialog(c, r, "Acquiring Satellite Signal", "002") + u(18)
        f = self.f(u(20))
        for line in t.wrap(f, "The channel isn't sending a picture. Cathode keeps trying; press GUIDE or "
                              "a channel number to watch something else.", r.w - u(80), 2):
            t.draw(c, line, f, b["ink"], r.centerx, y, align="center")
            y += t.ink(f)[1] + u(8)
        level = int(8 + 14 * (1 + math.sin(time.monotonic() * 2.2)))
        self._meter(c, pygame.Rect(r.x + u(40), r.bottom - u(104), r.w - u(80), u(80)), level, False)

    # ── Guide ─────────────────────────────────────────────────────────────

    def _geo(self):
        W, H = self.canvas
        u = self.u
        top, hdr = u(300), u(40)
        row_h = (H - top - hdr - u(12)) // self.guide_rows
        return dict(top=top, hdr=hdr, row_h=row_h, ch_w=int(W * (0.17 if self.SD else 0.2)), pad=u(24))

    def guide_video_box(self):
        W = self.canvas[0]
        u = self.u
        h = u(200) if self.SD else u(240)
        w = int(h * 16 / 9)
        return (W - w - u(40), u(28), w, h)

    def _picture(self, c):
        """The live picture's window with the channel captioned under it, as
        the box kept it top-right; returns the window's rect."""
        b, t, u = self.b, self.text, self.u
        vx, vy, vw, vh = self.guide_video_box()
        pygame.draw.rect(c, (0, 0, 0, 0), (vx, vy, vw, vh))
        pygame.draw.rect(c, rgba(b["sky"]), (vx - 2, vy - 2, vw + 4, vh + 4), 2)
        cap = pygame.Rect(vx - 2, vy + vh + 2, vw + 4, u(32))
        vgrad(c, cap, rgba(b["deep"], 235), rgba(b["deep"], 235))
        live = self.app.live
        if live.channel:
            on = live.programs()[0]
            fc = self.fb(u(17))
            cy = cap.y + (cap.h - t.ink(fc)[1]) // 2
            t.draw(c, t.fit(fc, f"{live.channel.number} {live.channel.name}", cap.w // 2 - u(12)), fc,
                   b["text"], cap.x + u(8), cy)
            if on:
                t.draw(c, t.fit(fc, on.title, cap.w // 2 - u(12)), fc, b["muted"], cap.right - u(8), cy,
                       align="right")
        return pygame.Rect(vx, vy, vw, vh)

    def draw_guide(self, c, g):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        geo = self._geo()
        top, pad = geo["top"], geo["pad"]
        vgrad(c, (0, 0, W, top), rgba(b["info_top"]), rgba(b["info_bot"]))
        mw = self.wordmark(c, pad, u(24), u(34), b["info_ink"], b["dish"])
        pic = self._picture(c)

        # The list tab and the clock beside the mark; the programme centred below.
        tab = self.chip(c, pad + mw + u(28), u(22), f"List: {g.category}", self.fb(u(19)), rgba(b["tab"]),
                        b["tab_ink"], pad=u(8), radius=u(5))
        self.hit(tab, lambda: g.handle("THEMES"))
        t.draw(c, when(), self.fb(u(19)), b["info_ink"], pad + mw + u(28), tab.bottom + u(6))
        info_w = pic.x - u(30) - pad
        cx = pad + info_w // 2
        sel = g.selected()
        cur = self.app.live.programs(sel)[0] if sel else None
        f_title = self.fb(u(26))
        t.draw(c, t.fit(f_title, cur.title if cur else (sel.name if sel else ""), info_w), f_title,
               b["info_ink"], cx, u(118), align="center")
        if cur:
            fd = self.f(u(20))
            yy = u(154)
            for line in t.wrap(fd, cur.description or "", info_w, 3):
                t.draw(c, line, fd, b["info_ink"], cx, yy, align="center")
                yy += t.ink(fd)[1] + u(7)
            meta = "   ".join(s for s in (f"{ampm(cur.start)} - {ampm(cur.stop)}", cur.rating, cur.category) if s)
            t.draw(c, t.fit(fd, meta, info_w), fd, b["info_ink"], pad, top - u(36))

        # The time header and the rows.
        c.fill(rgba(b["navy"]), (0, top, W, H - top))
        hdr = pygame.Rect(0, top, W, geo["hdr"])
        vgrad(c, hdr, rgba(b["hdr_top"]), rgba(b["hdr_bot"]))
        start, end = g.window()
        grid_x = pad + geo["ch_w"]
        grid_w = W - pad - grid_x
        fh = self.fb(u(19))
        ty = hdr.y + (hdr.h - t.ink(fh)[1]) // 2
        day = start.astimezone()
        dw = t.draw(c, f"{day:%a} {day.month}/{day.day}", fh, b["text"], pad + u(8), ty)
        ax = pad + u(8) + dw + u(12)
        pygame.draw.polygon(c, b["text"], [(ax, hdr.y + u(12)), (ax, hdr.bottom - u(12)), (ax + u(9), hdr.centery)])
        slots = int(g.hours * 2)
        for i in range(slots):
            x = grid_x + int(i * grid_w / slots)
            pygame.draw.line(c, b["muted"], (x, hdr.y + u(6)), (x, hdr.bottom - u(6)))
            t.draw(c, ampm(start + timedelta(minutes=30 * i)), fh, b["text"], x + int(grid_w / slots) // 2, ty,
                   align="center")
        rows = g.filtered()[g.top: g.top + g.rows]
        y = hdr.bottom + u(6)
        rh = geo["row_h"]
        mins = g.hours * 60
        now = datetime.now(timezone.utc)
        epg = self.app.epg
        f_cell, f_num, f_call = self.fb(u(21)), self.fb(u(22)), self.f(u(17))
        for i, ch in enumerate(rows):
            row_sel = g.focus == "grid" and g.top + i == g.cursor
            chr_ = pygame.Rect(pad, y, geo["ch_w"] - u(6), rh - u(6))
            if self.SD:
                # Capsule-ended channel cells, as the 301 drew them.
                pygame.draw.rect(c, b["chan_top"], chr_, border_top_left_radius=chr_.h // 2,
                                 border_bottom_left_radius=chr_.h // 2)
                t.draw(c, str(ch.number), f_num, b["chan_ink"], chr_.centerx + u(8), chr_.y + u(6), align="center")
                t.draw(c, t.fit(f_call, ch.name.upper(), chr_.w - u(30)), f_call, b["chan_ink"],
                       chr_.centerx + u(8), chr_.bottom - t.ink(f_call)[1] - u(6), align="center")
            else:
                vgrad(c, chr_, rgba(b["chan_top"]), rgba(b["chan_bot"]))
                t.draw(c, str(ch.number), f_num, b["chan_ink"], chr_.right - u(10), chr_.y + u(6), align="right")
                t.draw(c, t.fit(f_call, ch.name.upper(), chr_.w - u(20)), f_call, b["chan_ink"],
                       chr_.right - u(10), chr_.bottom - t.ink(f_call)[1] - u(6), align="right")
            if self.app.is_favorite(ch):
                pygame.draw.circle(c, b["sel"], (chr_.x + u(12), chr_.y + u(12)), u(4))
            cid = epg.resolve_channel_id(ch.epg_id, ch.name) if epg else None
            progs = epg.programs_in_window(cid, start, end) if cid else []
            if not progs:
                cell = pygame.Rect(grid_x, y, grid_w - u(4), rh - u(6))
                self._cell(c, cell, row_sel)
                t.draw(c, "No information", f_cell, b["sel_ink"] if row_sel else b["cell_ink"], cell.centerx,
                       cell.y + (cell.h - t.ink(f_cell)[1]) // 2, align="center")
            for p in progs:
                a = max(0.0, (p.start - start).total_seconds() / 60)
                e = min(float(mins), (p.stop - start).total_seconds() / 60)
                if e <= a:
                    continue
                cell = pygame.Rect(grid_x + int(a / mins * grid_w), y, int((e - a) / mins * grid_w) - u(4),
                                   rh - u(6))
                on = row_sel and p.start <= max(now, start) < p.stop
                self._cell(c, cell, on)
                ink = b["sel_ink"] if on else b["cell_ink"]
                if p.start < start:
                    pygame.draw.polygon(c, ink, [(cell.x + u(8), cell.centery), (cell.x + u(16), cell.centery - u(7)),
                                                 (cell.x + u(16), cell.centery + u(7))])
                if p.stop > end:
                    pygame.draw.polygon(c, ink, [(cell.right - u(8), cell.centery),
                                                 (cell.right - u(16), cell.centery - u(7)),
                                                 (cell.right - u(16), cell.centery + u(7))])
                if cell.w > u(50):
                    t.draw(c, t.fit(f_cell, p.title, cell.w - u(44)), f_cell, ink, cell.centerx,
                           cell.y + (cell.h - t.ink(f_cell)[1]) // 2, align="center")
            self.hit((pad, y, W - 2 * pad, rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                            setattr(g, "focus", "grid"), g.handle("SELECT")))
            y += rh

    def _cell(self, c, cell, on):
        b = self.b
        vgrad(c, cell, rgba(b["sel_hi"] if on else b["cell_top"]), rgba(b["sel"] if on else b["cell_bot"]))
        pygame.draw.rect(c, b["edge"], cell, 2)

    # ── Menus ─────────────────────────────────────────────────────────────

    def _icon(self, c, kind, rect, col):
        cx, cy, s = rect.centerx, rect.centery, min(rect.w, rect.h)
        w = max(2, s // 14)
        if kind == "guide":
            for k in range(3):
                pygame.draw.rect(c, col, (cx - s // 3, cy - s // 3 + k * s // 4, 2 * s // 3, s // 6), w)
        elif kind == "themes":
            pts = [(cx + s * 0.38 * math.cos(math.pi / 2 + k * math.pi / 5) * (1 if k % 2 == 0 else 0.45),
                    cy - s * 0.38 * math.sin(math.pi / 2 + k * math.pi / 5) * (1 if k % 2 == 0 else 0.45))
                   for k in range(10)]
            pygame.draw.polygon(c, col, pts, w)
        elif kind == "favorites":
            pygame.draw.circle(c, col, (cx - s // 8, cy - s // 10), s // 6)
            pygame.draw.circle(c, col, (cx + s // 8, cy - s // 10), s // 6)
            pygame.draw.polygon(c, col, [(cx - s // 3, cy - s // 20), (cx + s // 3, cy - s // 20), (cx, cy + s // 3)])
        elif kind == "demand":
            pygame.draw.rect(c, col, (cx - s // 3, cy - s // 4, 2 * s // 3, s // 2), w, border_radius=4)
            pygame.draw.polygon(c, col, [(cx - s // 10, cy - s // 8), (cx - s // 10, cy + s // 8), (cx + s // 7, cy)])
        elif kind == "recordings":
            pygame.draw.circle(c, (214, 44, 36), (cx, cy), s // 4)
            pygame.draw.circle(c, col, (cx, cy), s // 3, w)
        elif kind == "settings":
            for k in range(8):
                a = k * math.pi / 4
                pygame.draw.line(c, col, (cx + s * 0.18 * math.cos(a), cy + s * 0.18 * math.sin(a)),
                                 (cx + s * 0.34 * math.cos(a), cy + s * 0.34 * math.sin(a)), w + 2)
            pygame.draw.circle(c, col, (cx, cy), s // 5, w)
        else:
            pygame.draw.arc(c, col, (cx - s // 3, cy - s // 3, 2 * s // 3, 2 * s // 3), -0.9, 4.05, w)
            pygame.draw.line(c, col, (cx, cy - s // 2.6), (cx, cy), w)

    def _icon_for(self, label):
        lab = label.lower()
        for key, kind in (("guide", "guide"), ("theme", "themes"), ("favor", "favorites"),
                          ("demand", "demand"), ("record", "recordings"), ("setting", "settings")):
            if key in lab:
                return kind
        return "exit"

    def _menu_top(self, c, title):
        """Blue page, the mark, the title in a pill, the clock; returns the
        pill's rect."""
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        vgrad(c, (0, 0, W, H), rgba(b["info_top"]), rgba(b["deep"]))
        mw = self.wordmark(c, u(40), u(26), u(30), b["info_ink"], b["dish"])
        f = self.fb(u(26))
        pill = pygame.Rect(u(40) + mw + u(30), u(26), t.width(f, title) + u(60), u(46))
        vgrad(c, pill, rgba(b["pill_hi"]), rgba(b["pill"]), radius=u(12))
        t.draw(c, title, f, b["pill_ink"], pill.centerx, pill.y + (pill.h - t.ink(f)[1]) // 2, align="center")
        return pill

    def draw_menu(self, c, m):
        if self.menu_cols(m) > 1:
            self._menu_grid(c, m)
        else:
            self._menu_list(c, m)

    def _menu_grid(self, c, m):
        """The Main Menu: a page of numbered tiles, a digit picks one."""
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        self._menu_top(c, "Main Menu")
        t.draw(c, when(), self.f(u(19)), b["info_ink"], W - u(40), u(40), align="right")
        cols, tw, th, gap = 3, u(300), u(140), u(24)
        x0 = (W - (cols * tw + (cols - 1) * gap)) // 2
        y0 = u(110)
        f_lab, f_num = self.fb(u(22)), self.fb(u(20))
        for i, it in enumerate(m.items[:9]):
            r = pygame.Rect(x0 + (i % cols) * (tw + gap), y0 + (i // cols) * (th + gap), tw, th)
            sel = i == m.cursor
            if sel:
                panel(c, r.inflate(u(6), u(6)), rgba(b["cursor_hi"]), rgba(b["cursor"]), radius=u(18),
                      edge=rgba((255, 255, 255)), edge_w=u(3))
            else:
                panel(c, r, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=u(16), edge=rgba(b["edge"]))
            ink = (b["cursor_ink"] if sel else b["ink"]) if it.enabled else b["ink_soft"]
            self._icon(c, self._icon_for(it.label), pygame.Rect(r.x + u(16), r.y + u(24), u(90), u(90)), ink)
            num = pygame.Rect(r.right - u(52), r.y + u(12), u(40), u(32))
            vgrad(c, num, rgba(b["pill_hi"]), rgba(b["pill"]), radius=u(8))
            t.draw(c, str(i + 1), f_num, b["pill_ink"], num.centerx, num.y + (num.h - t.ink(f_num)[1]) // 2,
                   align="center")
            for k, line in enumerate(t.wrap(f_lab, it.label, tw - u(180), 2)):
                t.draw(c, line, f_lab, ink, r.x + u(118), r.y + u(52) + k * (t.ink(f_lab)[1] + u(8)))
            self.hit(r, lambda i=i: m.activate(i))
        t.draw(c, "Press a number, or use the arrows and SELECT", self.f(u(18)), b["muted"], W // 2,
               H - u(52), align="center")

    def _menu_list(self, c, m):
        """A list page as the box had them: capsule rows numbered down the
        right in a white panel, the picture kept at the right."""
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        pad = u(40)
        self._menu_top(c, m.title.title())
        pic = self._picture(c)
        t.draw(c, when(), self.f(u(19)), b["muted"], W - pad, H - u(52), align="right")
        lp = pygame.Rect(pad, u(96), pic.x - u(36) - pad, H - u(96) - u(70))
        panel(c, lp, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=u(18), edge=rgba((255, 255, 255)), edge_w=u(3))
        rh = u(48)
        n = len(m.items)
        n_vis = max(1, (lp.h - u(28)) // rh)
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        f_row, f_num = self.f(u(22)), self.fb(u(20))
        nw = u(56)
        y = lp.y + u(14)
        for i in range(first, min(n, first + n_vis)):
            it = m.items[i]
            sel = i == m.cursor
            row = pygame.Rect(lp.x + u(14), y, lp.w - u(28) - nw - u(8), rh - u(8))
            num = pygame.Rect(lp.right - u(14) - nw, y, nw, rh - u(8))
            top, bot = (b["cursor_hi"], b["cursor"]) if sel else (b["pill_hi"], b["pill"])
            vgrad(c, row, rgba(top), rgba(bot), radius=row.h // 2)
            vgrad(c, num, rgba(top), rgba(bot), radius=num.h // 2)
            ink = (b["cursor_ink"] if sel else b["pill_ink"]) if it.enabled else mix(b["pill_ink"], b["pill"], 0.5)
            ty = row.y + (row.h - t.ink(f_row)[1]) // 2
            t.draw(c, t.fit(f_row, it.label, row.w - u(240)), f_row, ink, row.x + u(18), ty)
            if it.value:
                v = it.value()
                v = f"< {v} >" if sel and it.adjust else v
                t.draw(c, t.fit(f_row, v, u(210)), f_row, ink, row.right - u(18), ty, align="right")
            elif it.submenu:
                t.draw(c, ">", f_row, ink, row.right - u(18), ty, align="right")
            if i < 9:
                t.draw(c, str(i + 1), f_num, ink, num.centerx, num.y + (num.h - t.ink(f_num)[1]) // 2, align="center")
            self.hit(row, lambda i=i: m.activate(i))
            y += rh
        if n > n_vis:
            t.draw(c, f"{first + 1}-{min(n, first + n_vis)} of {n}", self.f(u(16)), b["ink_soft"],
                   lp.x + u(18), lp.bottom - u(26))
        t.draw(c, "SELECT: choose   CANCEL: back   VIEW TV: close", self.f(u(16)), b["muted"], pad, H - u(52))

    # ── Boot ──────────────────────────────────────────────────────────────

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        stage = boot.stage()
        vgrad(c, (0, 0, W, H), rgba(b["info_top"]), rgba(b["deep"]))
        # The mark and its reflection, as the box lit up.
        size = u(72)
        mw = self.measure(self.wordmark, size, b["text"], b["dish"])
        mh = int(size * 1.7)
        mark = pygame.Surface((mw + u(20), mh), pygame.SRCALPHA)
        self.wordmark(mark, u(10), u(10), size, b["text"], b["dish"])
        mx, my = (W - mw) // 2 - u(10), int(H * 0.18)
        c.blit(mark, (mx, my))
        mirror = pygame.transform.flip(mark, False, True)
        mirror.set_alpha(56)
        c.blit(mirror, (mx, my + mh - u(16)))
        if stage == "starting":
            t.draw(c, "Starting up...", self.f(u(24)), b["muted"], W // 2, int(H * 0.56), align="center")
            return
        age = time.monotonic() - boot.start
        caption, level, locked = {
            "signal": ("Acquiring Satellite Signal", int(min(88, 10 + age * 24)), False),
            "guide": ("Downloading Program Guide", 94, True),
            "done": ("Signal Acquired", 96, True)}[stage]
        r = pygame.Rect(0, 0, int(W * 0.6), u(210))
        r.center = (W // 2, int(H * 0.70))
        y = self._dialog(c, r, caption)
        self._meter(c, pygame.Rect(r.x + u(40), y + u(22), r.w - u(80), u(80)), level, locked)
        t.draw(c, "Press any button to skip", self.f(u(17)), b["muted"], W // 2, H - u(40), align="center")


class Plate(PlateHD):
    """The SD era: capsule shapes, blue cells, a pale selection, 4:3."""
    name = "plate"
    label = "Plate Network"
    canvas = (640, 480)
    guide_rows = 5
    SD = True
    NATIVE = {"bg": [14, 28, 92], "accent": [88, 110, 200], "accent2": [230, 236, 250],
              "text": [255, 255, 255], "chnum": [255, 255, 255]}

    def roles(self, b):
        r = super().roles(b)
        bg, acc, sel, text = b["bg"], b["accent"], b["accent2"], b["text"]
        navy = mix(bg, (0, 0, 0), 0.3)
        r.update(info_top=mix(acc, (255, 255, 255), 0.55), info_bot=mix(acc, (255, 255, 255), 0.25),
                 info_ink=navy,
                 cell_top=mix(bg, acc, 0.8), cell_bot=mix(bg, acc, 0.55), cell_ink=text,
                 chan_top=mix(bg, acc, 0.6), chan_bot=mix(bg, acc, 0.4), chan_ink=text,
                 edge=mix(bg, (0, 0, 0), 0.4),
                 sel=sel, sel_hi=(255, 255, 255), sel_ink=navy,
                 cursor=(255, 255, 255), cursor_hi=(255, 255, 255), cursor_ink=navy,
                 hdr_top=mix(bg, acc, 0.3), hdr_bot=bg,
                 panel_top=(236, 236, 238), panel_bot=(176, 180, 192), ink=navy,
                 # The SD banner was a steel-blue capsule with white lettering.
                 banner_top=mix(bg, acc, 0.78), banner_bot=mix(bg, acc, 0.5), banner_ink=text,
                 banner_soft=mix(text, acc, 0.3),
                 pill=mix(bg, acc, 0.6), pill_hi=mix(bg, acc, 0.8), pill_ink=text,
                 tab=(255, 255, 255), tab_ink=navy)
        return r
