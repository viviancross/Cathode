"""Plate: a mid-2000s Dish Network-style box. Plate HD follows the ViP622/722
(light sky-blue info panel, silver guide cells, green selection, a numbered
3x3 Main Menu); Plate (SD) follows the 301/522 era: dark navy, yellow
selection, 4:3. RIGHT on live TV browses, as Dish's remote did."""

import math
import time
from datetime import datetime, timedelta, timezone

import pygame

from .box import BoxSkin, mix, panel, rgba, vgrad


def ampm(dt) -> str:
    """'7:30am', the box's clock style."""
    return dt.astimezone().strftime("%I:%M%p").lstrip("0").lower()


class PlateHD(BoxSkin):
    name = "plate_hd"
    label = "Plate HD"
    canvas = (1280, 720)
    right_is_browse = True
    guide_hours = 2
    guide_rows = 6
    NATIVE = {"bg": [18, 42, 104], "accent": [110, 168, 226], "accent2": [58, 168, 66],
              "text": [255, 255, 255], "chnum": [16, 32, 82]}

    def roles(self, b):
        bg, acc, sel, text = b["bg"], b["accent"], b["accent2"], b["text"]
        return {
            "navy": bg, "deep": mix(bg, (0, 0, 0), 0.4), "sky": acc,
            "panel_top": mix((255, 255, 255), acc, 0.10), "panel_bot": mix((255, 255, 255), acc, 0.55),
            "ink": mix(bg, (0, 0, 0), 0.25), "ink_soft": mix(bg, acc, 0.4),
            "cell_top": (240, 242, 247), "cell_bot": (186, 194, 210), "cell_ink": mix(bg, (0, 0, 0), 0.25),
            "chan_top": (214, 220, 232), "chan_bot": (160, 170, 192),
            "sel": sel, "sel_hi": mix(sel, (255, 255, 255), 0.35), "sel_ink": (255, 255, 255),
            "text": text, "muted": mix(text, acc, 0.4), "tab": sel,
            "hdr_top": mix(bg, acc, 0.25), "hdr_bot": bg,
            "tile_top": mix(bg, acc, 0.35), "tile_bot": mix(bg, (0, 0, 0), 0.2),
        }

    def u(self, v) -> int:
        return int(v * self.canvas[1] / 720)

    def menu_cols(self, menu):
        return 3 if menu.title == "MAIN MENU" and len(menu.pages) == 1 else 1

    # ── Wordmark ──────────────────────────────────────────────────────────

    def wordmark(self, c, x, y, size, ink, dot):
        """'plate' with a dish beside it. Our own mark."""
        f = self.fb(size)
        w = self.text.draw(c, "plate", f, ink, x + size, y)
        h = self.text.ink(f)[1]
        pygame.draw.ellipse(c, dot, (x, y + h // 4, int(size * 0.8), int(h * 0.7)), max(2, size // 10))
        pygame.draw.line(c, dot, (x + int(size * 0.4), y + h // 2), (x + int(size * 0.7), y), max(2, size // 12))
        return w + size

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
        panel(c, r, rgba(b["cell_top"]), rgba(b["cell_bot"]), radius=u(10), edge=rgba(b["navy"]))
        self.text.draw(c, text, f, b["cell_ink"], r.centerx, r.y + (r.h - self.text.ink(f)[1]) // 2,
                       align="center")

    def _banner(self, c, ch, cur, nxt, full=False, tag=None):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        m = u(40)
        r = pygame.Rect(m, H - u(150) - u(30), W - 2 * m, u(150))
        if full and cur and cur.description:
            f = self.f(u(20))
            lines = t.wrap(f, cur.description, r.w - u(40), 3)
            dh = u(24) + len(lines) * (t.ink(f)[1] + u(10))
            d = pygame.Rect(r.x, r.y - dh - u(10), r.w, dh)
            panel(c, d, rgba(b["panel_top"], 245), rgba(b["panel_bot"], 245), radius=u(14))
            y = d.y + u(14)
            for line in lines:
                t.draw(c, line, f, b["ink"], d.x + u(20), y)
                y += t.ink(f)[1] + u(10)
        panel(c, r, rgba(b["cell_top"], 242), rgba(b["cell_bot"], 242), radius=u(14),
              edge=rgba(b["navy"], 220))
        if tag:
            self.chip(c, r.x + u(18), r.y - u(34), tag, self.fb(u(16)), rgba(b["tab"]), b["sel_ink"])
        # Channel: number over call sign, at the left.
        nb = pygame.Rect(r.x + u(14), r.y + u(14), u(160), r.h - u(28))
        vgrad(c, nb, rgba(b["hdr_top"]), rgba(b["hdr_bot"]), radius=u(10))
        f_num = self.fb(u(48))
        t.draw(c, str(ch.number), f_num, b["text"], nb.centerx, nb.y + u(12), align="center")
        epg = self.app.epg
        url = epg.icon_url(epg.resolve_channel_id(ch.epg_id, ch.name)) if epg else ""
        logo = self.logo(url or ch.logo, nb.w - u(20), u(40))
        if logo:
            c.blit(logo, logo.get_rect(midbottom=(nb.centerx, nb.bottom - u(10))))
        else:
            fs = self.fb(u(17))
            t.draw(c, t.fit(fs, ch.name.upper(), nb.w - u(12)), fs, b["muted"], nb.centerx,
                   nb.bottom - u(30), align="center")
        x = nb.right + u(22)
        right = r.right - u(210)
        f_title, f_line = self.fb(u(32)), self.f(u(20))
        t.draw(c, t.fit(f_title, cur.title if cur else ch.name, right - x), f_title, b["ink"], x, r.y + u(18))
        if cur:
            bits = [f"{ampm(cur.start)} - {ampm(cur.stop)}"] + [s for s in (cur.rating, cur.episode) if s]
            t.draw(c, t.fit(f_line, "   ".join(bits), right - x), f_line, b["ink_soft"], x, r.y + u(62))
            bar = pygame.Rect(x, r.y + u(100), min(u(440), right - x), u(10))
            self.progress(c, bar, cur.progress_at(datetime.now(timezone.utc)), rgba(b["chan_bot"]),
                          rgba(b["sel"]))
        if nxt:
            fs = self.f(u(17))
            t.draw(c, t.fit(fs, f"Next: {ampm(nxt.start)}  {nxt.title}", right - x), fs, b["ink_soft"],
                   x, r.y + u(120))
        local = datetime.now()
        t.draw(c, ampm(local), self.fb(u(28)), b["ink"], r.right - u(22), r.y + u(20), align="right")
        t.draw(c, local.strftime("%a %m/%d").replace(" 0", " "), self.f(u(18)), b["ink_soft"],
               r.right - u(22), r.y + u(60), align="right")
        t.draw(c, "INFO for details", self.f(u(15)), b["ink_soft"], r.right - u(22), r.bottom - u(30),
               align="right")
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def draw_browse(self, c, br):
        if br.channel:
            cur, nxt = br.program()
            tag = "BROWSE  -  SELECT to watch" + (f"  (+{br.ahead})" if br.ahead else "")
            self._banner(c, br.channel, cur, nxt, tag=tag)

    # ── Signal loss ───────────────────────────────────────────────────────

    def _meter(self, c, rect, level, b):
        """A signal-strength meter: a row of bars, lit up to `level` (0-100)."""
        n = 20
        gap = max(2, rect.w // 120)
        bw = (rect.w - (n - 1) * gap) // n
        for i in range(n):
            lit = (i + 1) * 100 / n <= level
            h = int(rect.h * (0.35 + 0.65 * (i + 1) / n))
            bar = pygame.Rect(rect.x + i * (bw + gap), rect.bottom - h, bw, h)
            col = (b["sel"] if i < n * 0.7 else (238, 196, 34)) if lit else b["chan_bot"]
            pygame.draw.rect(c, col, bar, border_radius=2)

    def _signal_loss(self, c):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        c.fill((0, 0, 0, 255))
        r = pygame.Rect(0, 0, int(W * 0.6), u(260))
        r.center = (W // 2, int(H * 0.42))
        panel(c, r, rgba(b["tile_top"]), rgba(b["tile_bot"]), radius=u(16), edge=rgba(b["sky"]))
        bar = pygame.Rect(r.x, r.y, r.w, u(52))
        vgrad(c, bar, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=u(16))
        pygame.draw.rect(c, b["panel_bot"], (bar.x, bar.bottom - u(14), bar.w, u(14)))
        t.draw(c, "Acquiring Signal", self.fb(u(26)), b["ink"], bar.centerx, bar.y + u(13), align="center")
        f = self.f(u(20))
        t.draw(c, "This channel isn't sending a picture.", f, b["text"], r.centerx, bar.bottom + u(22),
               align="center")
        t.draw(c, "Still trying...", f, b["muted"], r.centerx, bar.bottom + u(52), align="center")
        level = int(12 + 10 * (1 + math.sin(time.monotonic() * 2.2)))
        self._meter(c, pygame.Rect(r.x + u(40), r.bottom - u(80), r.w - u(80), u(50)), level, b)

    # ── Guide ─────────────────────────────────────────────────────────────

    def _geo(self):
        W, H = self.canvas
        u = self.u
        top, hdr = u(300), u(40)
        rows = self.guide_rows
        row_h = (H - top - hdr - u(10)) // rows
        return dict(top=top, hdr=hdr, row_h=row_h, ch_w=int(W * 0.15), pad=u(26))

    def guide_video_box(self):
        W = self.canvas[0]
        u = self.u
        h = u(220)
        w = int(h * 16 / 9)
        return (W - w - u(30), u(30), w, h)

    def draw_guide(self, c, g):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        geo = self._geo()
        top, pad = geo["top"], geo["pad"]
        vgrad(c, (0, 0, W, top), rgba(b["panel_top"]), rgba(b["panel_bot"]))
        self.wordmark(c, pad, u(20), u(34), b["ink"], (204, 32, 40))
        vx, vy, vw, vh = self.guide_video_box()
        pygame.draw.rect(c, (0, 0, 0, 0), (vx, vy, vw, vh))
        pygame.draw.rect(c, rgba(b["navy"]), (vx - 3, vy - 3, vw + 6, vh + 6), 3)
        live = self.app.live
        if live.channel:
            cap = pygame.Rect(vx, vy + vh + u(6), vw, u(30))
            pygame.draw.rect(c, rgba(b["navy"], 230), cap)
            fc = self.fb(u(17))
            t.draw(c, t.fit(fc, f"{live.channel.number}  {live.channel.name}", cap.w - u(16)), fc,
                   b["text"], cap.x + u(8), cap.y + (cap.h - t.ink(fc)[1]) // 2)

        # The list tab, the clock, the selected programme.
        ft = self.fb(u(19))
        tab = self.chip(c, pad + u(150), u(24), f"List: {g.category}", ft, rgba(b["tab"]), b["sel_ink"],
                        pad=u(10), radius=u(12))
        self.hit(tab, lambda: g.handle("THEMES"))
        local = datetime.now()
        t.draw(c, f"{ampm(local)} {local:%a} {local.month}/{local.day}", self.fb(u(19)), b["ink"],
               pad + u(150), tab.bottom + u(8))
        sel = g.selected()
        cur = live.programs(sel)[0] if sel else None
        info_w = vx - pad - u(30)
        y = u(118)
        f_title = self.fb(u(28))
        t.draw(c, t.fit(f_title, cur.title if cur else (sel.name if sel else ""), info_w), f_title,
               b["ink"], pad, y)
        if cur:
            fd = self.f(u(19))
            yy = y + u(42)
            for line in t.wrap(fd, cur.description or "", info_w, 3):
                t.draw(c, line, fd, b["ink"], pad, yy)
                yy += t.ink(fd)[1] + u(8)
            meta = "   ".join(s for s in (f"{ampm(cur.start)} - {ampm(cur.stop)}", cur.category, cur.rating) if s)
            t.draw(c, t.fit(fd, meta, info_w), fd, b["ink_soft"], pad, top - u(34))

        # Time header and rows.
        c.fill(rgba(b["navy"]), (0, top, W, H - top))
        hdr = pygame.Rect(0, top, W, geo["hdr"])
        vgrad(c, hdr, rgba(b["hdr_top"]), rgba(b["hdr_bot"]))
        start, end = g.window()
        grid_x = pad + geo["ch_w"]
        grid_w = W - pad - grid_x
        fh = self.fb(u(19))
        ty = hdr.y + (hdr.h - t.ink(fh)[1]) // 2
        day = start.astimezone()
        t.draw(c, f"{day:%a} {day.month}/{day.day}", fh, b["text"], pad + u(8), ty)
        slots = g.hours * 2
        for i in range(slots):
            x = grid_x + int(i * grid_w / slots)
            pygame.draw.line(c, b["muted"], (x, hdr.y + u(6)), (x, hdr.bottom - u(6)))
            t.draw(c, ampm(start + timedelta(minutes=30 * i)), fh, b["text"],
                   x + int(grid_w / slots) // 2, ty, align="center")
        rows = g.filtered()[g.top: g.top + g.rows]
        y = hdr.bottom + u(4)
        rh = geo["row_h"]
        mins = g.hours * 60
        now = datetime.now(timezone.utc)
        epg = self.app.epg
        f_cell, f_num, f_call = self.fb(u(19)), self.fb(u(20)), self.f(u(15))
        for i, ch in enumerate(rows):
            row_sel = g.focus == "grid" and g.top + i == g.cursor
            chr_ = pygame.Rect(pad, y, geo["ch_w"] - u(4), rh - u(4))
            vgrad(c, chr_, rgba(b["chan_top"]), rgba(b["chan_bot"]))
            t.draw(c, str(ch.number), f_num, b["cell_ink"], chr_.centerx, chr_.y + u(6), align="center")
            t.draw(c, t.fit(f_call, ch.name.upper(), chr_.w - u(10)), f_call, b["cell_ink"], chr_.centerx,
                   chr_.bottom - t.ink(f_call)[1] - u(6), align="center")
            cid = epg.resolve_channel_id(ch.epg_id, ch.name) if epg else None
            progs = epg.programs_in_window(cid, start, end) if cid else []
            if not progs:
                cell = pygame.Rect(grid_x, y, grid_w - u(2), rh - u(4))
                vgrad(c, cell, rgba(b["sel_hi"] if row_sel else b["cell_top"]),
                      rgba(b["sel"] if row_sel else b["cell_bot"]))
                t.draw(c, ch.name, f_cell, b["sel_ink"] if row_sel else b["cell_ink"], cell.centerx,
                       cell.y + (cell.h - t.ink(f_cell)[1]) // 2, align="center")
            for p in progs:
                a = max(0.0, (p.start - start).total_seconds() / 60)
                e = min(float(mins), (p.stop - start).total_seconds() / 60)
                if e <= a:
                    continue
                cell = pygame.Rect(grid_x + int(a / mins * grid_w), y, int((e - a) / mins * grid_w) - u(3),
                                   rh - u(4))
                on = row_sel and p.start <= max(now, start) < p.stop
                vgrad(c, cell, rgba(b["sel_hi"] if on else b["cell_top"]),
                      rgba(b["sel"] if on else b["cell_bot"]))
                ink = b["sel_ink"] if on else b["cell_ink"]
                if p.start < start:
                    pygame.draw.polygon(c, ink, [(cell.x + u(8), cell.centery), (cell.x + u(16), cell.centery - u(7)),
                                                 (cell.x + u(16), cell.centery + u(7))])
                if cell.w > u(50):
                    t.draw(c, t.fit(f_cell, p.title, cell.w - u(40)), f_cell, ink, cell.centerx,
                           cell.y + (cell.h - t.ink(f_cell)[1]) // 2, align="center")
            self.hit((pad, y, W - 2 * pad, rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                            setattr(g, "focus", "grid"), g.handle("SELECT")))
            y += rh

    # ── Menus ─────────────────────────────────────────────────────────────

    ICONS = ("guide", "themes", "favorites", "demand", "recordings", "settings", "exit")

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

    def draw_menu(self, c, m):
        if self.menu_cols(m) > 1:
            self._menu_grid(c, m)
        else:
            self._menu_list(c, m)

    def _menu_grid(self, c, m):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        vgrad(c, (0, 0, W, H), rgba(b["hdr_top"]), rgba(b["deep"]))
        self.wordmark(c, u(50), u(34), u(32), b["text"], (204, 32, 40))
        t.draw(c, "Main Menu", self.fb(u(36)), b["text"], W // 2, u(36), align="center")
        local = datetime.now()
        t.draw(c, f"{ampm(local)}  {local:%a} {local.month}/{local.day}", self.f(u(20)), b["muted"],
               W - u(50), u(44), align="right")
        cols, tw, th, gap = 3, u(300), u(150), u(28)
        x0 = (W - (cols * tw + (cols - 1) * gap)) // 2
        y0 = u(130)
        f_lab, f_num = self.fb(u(22)), self.fb(u(26))
        for i, it in enumerate(m.items[:9]):
            r = pygame.Rect(x0 + (i % cols) * (tw + gap), y0 + (i // cols) * (th + gap), tw, th)
            sel = i == m.cursor
            if sel:
                panel(c, r.inflate(u(8), u(8)), rgba(b["sel_hi"]), rgba(b["sel"]), radius=u(18),
                      edge=rgba((255, 255, 255)), edge_w=u(3))
            else:
                panel(c, r, rgba(b["tile_top"]), rgba(b["tile_bot"]), radius=u(16), edge=rgba(b["sky"], 200))
            ink = b["text"] if it.enabled else b["muted"]
            self._icon(c, self._icon_for(it.label), pygame.Rect(r.x + u(14), r.y + u(20), u(90), u(90)), ink)
            t.draw(c, str(i + 1), f_num, ink, r.right - u(18), r.y + u(14), align="right")
            for k, line in enumerate(t.wrap(f_lab, it.label, tw - u(130), 2)):
                t.draw(c, line, f_lab, ink, r.x + u(116), r.y + u(52) + k * (t.ink(f_lab)[1] + u(8)))
            self.hit(r, lambda i=i: m.activate(i))
        t.draw(c, "Press a number, or use the arrows and SELECT", self.f(u(18)), b["muted"], W // 2,
               H - u(56), align="center")

    def _menu_list(self, c, m):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        self.dim(c, 140)
        pw = int(W * 0.52)
        n_vis = 9
        n = len(m.items)
        rh = u(48)
        shown = min(n, n_vis)
        r = pygame.Rect((W - pw) // 2, 0, pw, u(80) + shown * rh + u(64))
        r.centery = H // 2
        panel(c, r, rgba(b["tile_top"], 248), rgba(b["tile_bot"], 248), radius=u(18), edge=rgba(b["sky"]))
        head = pygame.Rect(r.x, r.y, r.w, u(62))
        vgrad(c, head, rgba(b["panel_top"]), rgba(b["panel_bot"]), radius=u(18))
        pygame.draw.rect(c, b["panel_bot"], (head.x, head.bottom - u(16), head.w, u(16)))
        t.draw(c, t.fit(self.fb(u(26)), m.title.title(), head.w - u(40)), self.fb(u(26)), b["ink"],
               head.centerx, head.y + u(18), align="center")
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        f_row = self.f(u(22))
        y = head.bottom + u(12)
        for i in range(first, min(n, first + n_vis)):
            it = m.items[i]
            row = pygame.Rect(r.x + u(14), y, r.w - u(28), rh - u(6))
            sel = i == m.cursor
            if sel:
                vgrad(c, row, rgba(b["sel_hi"]), rgba(b["sel"]), radius=u(8))
            ink = (b["sel_ink"] if sel else b["text"]) if it.enabled else b["muted"]
            ty = row.y + (row.h - t.ink(f_row)[1]) // 2
            t.draw(c, f"{i + 1}" if i < 9 else " ", self.fb(u(20)), ink, row.x + u(14), ty)
            t.draw(c, t.fit(f_row, it.label, row.w - u(230)), f_row, ink, row.x + u(52), ty)
            if it.value:
                v = it.value()
                v = f"< {v} >" if sel and it.adjust else v
                t.draw(c, t.fit(f_row, v, u(200)), f_row, ink, row.right - u(14), ty, align="right")
            elif it.submenu:
                t.draw(c, ">", f_row, ink, row.right - u(14), ty, align="right")
            self.hit(row, lambda i=i: m.activate(i))
            y += rh
        t.draw(c, "SELECT: choose   CANCEL: back   VIEW TV: close", self.f(u(15)), b["muted"],
               r.centerx, r.bottom - u(36), align="center")

    # ── Boot ──────────────────────────────────────────────────────────────

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, t, u = self.b, self.text, self.u
        stage = boot.stage()
        vgrad(c, (0, 0, W, H), rgba(b["hdr_top"]), rgba(b["deep"]))
        if stage == "starting":
            return
        mw = self.text.width(self.fb(u(70)), "plate") + u(70)
        self.wordmark(c, (W - mw) // 2, int(H * 0.18), u(70), b["text"], (204, 32, 40))
        r = pygame.Rect(0, 0, int(W * 0.56), u(220))
        r.center = (W // 2, int(H * 0.62))
        panel(c, r, rgba(b["tile_top"]), rgba(b["tile_bot"]), radius=u(16), edge=rgba(b["sky"]))
        age = time.monotonic() - boot.start
        if stage == "signal":
            caption, level = "Acquiring Satellite Signal", int(min(85, 20 + age * 22))
        elif stage == "guide":
            caption, level = "Downloading Program Guide", 92
        else:
            caption, level = "Signal Acquired", 96
        t.draw(c, caption, self.fb(u(26)), b["text"], r.centerx, r.y + u(22), align="center")
        self._meter(c, pygame.Rect(r.x + u(40), r.y + u(80), r.w - u(80), u(70)), level, b)
        t.draw(c, f"Signal strength: {level}", self.f(u(18)), b["muted"], r.centerx, r.bottom - u(40),
               align="center")
        t.draw(c, "Press any button to skip", self.f(u(17)), b["muted"], W // 2, H - u(50), align="center")


class Plate(PlateHD):
    """The SD era: dark navy, yellow selection, 4:3."""
    name = "plate"
    label = "Plate"
    canvas = (640, 480)
    guide_rows = 5
    NATIVE = {"bg": [10, 20, 60], "accent": [64, 92, 170], "accent2": [250, 214, 0],
              "text": [255, 255, 255], "chnum": [250, 214, 0]}

    def roles(self, b):
        r = super().roles(b)
        bg, acc = b["bg"], b["accent"]
        r.update(panel_top=mix(bg, acc, 0.55), panel_bot=mix(bg, acc, 0.25), ink=b["text"],
                 ink_soft=mix(b["text"], acc, 0.45),
                 cell_top=mix(bg, acc, 0.65), cell_bot=mix(bg, acc, 0.40), cell_ink=b["text"],
                 chan_top=mix(bg, acc, 0.45), chan_bot=mix(bg, acc, 0.25),
                 sel_ink=(0, 0, 0))
        return r
