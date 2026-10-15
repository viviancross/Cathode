"""Cathode Classic: the 3.x look. Phosphor colours from the chosen theme, a
pixel font, static on a channel change."""

import time
from datetime import datetime, timedelta

import pygame

from .. import palette
from . import Skin

_FONTS = {"vcr": "VCR_OSD_MONO.ttf", "ibm": "PxPlus_IBM_VGA8.ttf",
          "vt220": "Glass_TTY_VT220.ttf", "pixelop": "PixelOperator.ttf",
          "vt323": "VT323-Regular.ttf", "jersey": "Jersey10-Regular.ttf"}

# SMPTE colour bars, top two thirds (75%).
_BARS = [(191, 191, 191), (191, 191, 0), (0, 191, 191), (0, 191, 0),
         (191, 0, 191), (191, 0, 0), (0, 0, 191)]


def clock(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def span(prog) -> str:
    """'7:00-7:30' in local time. ASCII hyphen: pixel fonts lack the en dash."""
    def hm(d):
        return d.astimezone().strftime("%I:%M").lstrip("0")
    return f"{hm(prog.start)}-{hm(prog.stop)}"


class Classic(Skin):
    name = "classic"
    canvas = (1280, 720)
    tune_cover = "static"

    def __init__(self, app):
        super().__init__(app)
        self._tick = None
        self.reload()

    def reload(self):
        """Pick up the configured theme and font."""
        cfg = self.app.config
        self.p = palette.PALETTES.get(cfg.theme, palette.PALETTES["blue"])
        self.font_file = _FONTS.get(cfg.font, _FONTS["vcr"])

    def f(self, size):
        return self.text.font(self.font_file, size)

    # ── Live TV ───────────────────────────────────────────────────────────

    def draw_live(self, c, live):
        W, H = self.canvas
        p = self.p
        if live.message:
            self._message(c, live.message)
            return
        if live.standby and live.phase != "cover":
            self._standby(c)
        if live.phase == "cover" and live.channel:
            # The channel being tuned, big and top-left, over the static.
            self.text.draw(c, str(live.channel.number), self.f(96), p["CHANNEL_GREEN"],
                           48, 40, outline=(0, 0, 0))
        if live.banner_visible() and live.channel:
            self._banner(c, live)
        if live.digits:
            self.text.draw(c, live.digits + "-" * (3 - len(live.digits)), self.f(72),
                           p["CHANNEL_GREEN"], W - 48, 40, align="right", outline=(0, 0, 0))
        if live.volume_visible():
            self._volume(c, W // 2, int(H * 0.72))

    def _banner(self, c, live):
        W, H = self.canvas
        p, t = self.p, self.text
        ch = live.channel
        cur, nxt = live.programs()
        bh = int(H * 0.155)
        bx, bw = int(W * 0.02), int(W * 0.96)
        by = H - bh - int(H * 0.025)
        f_huge, f_large, f_med, f_small = (self.f(int(bh * k)) for k in (0.55, 0.32, 0.24, 0.18))

        if live.banner_full and cur and cur.description:
            # INFO again: the description opens above the bar.
            lines = t.wrap(f_med, cur.description, bw - 40, 3)
            dh = 24 + len(lines) * (t.ink(f_med)[1] + 10)
            pygame.draw.rect(c, p["OSD_BG"], (bx, by - dh - 8, bw, dh), border_radius=8)
            pygame.draw.rect(c, p["OSD_BORDER"], (bx, by - dh - 8, bw, 3))
            y = by - dh + 6
            for line in lines:
                t.draw(c, line, f_med, p["WHITE"], bx + 20, y)
                y += t.ink(f_med)[1] + 10

        pygame.draw.rect(c, p["OSD_BG"], (bx, by, bw, bh), border_radius=8)
        pygame.draw.rect(c, p["OSD_BORDER"], (bx, by, bw, 3))

        # Logo box, or the number big in it when there's no logo.
        nb = pygame.Rect(bx + 8, by + 8, int(bh * 1.1), bh - 16)
        pygame.draw.rect(c, p["CHNUM_BG"], nb, border_radius=6)
        pygame.draw.rect(c, p["OSD_BORDER"], (nb.x, nb.y, nb.w, 3))
        epg = self.app.epg
        url = epg.icon_url(epg.resolve_channel_id(ch.epg_id, ch.name)) if epg else ""
        logo = self.logo(url or ch.logo, nb.w - 10, nb.h - 10)

        info_x = nb.right + 20
        next_x = int(W * 0.45)
        col_w = next_x - info_x - 16
        gap = max(2, int(bh * 0.05))
        y_name = by + int(bh * 0.10)
        y_prog = y_name + t.ink(f_large)[1] + gap
        pb_y = y_prog + t.ink(f_med)[1] + max(2, gap // 2)
        y_time = pb_y + 4 + max(2, gap // 2)

        name_x = info_x
        if logo is not None:
            c.blit(logo, logo.get_rect(center=nb.center))
            name_x += t.draw(c, str(ch.number), f_large, p["CHANNEL_GREEN"], info_x, y_name) + 12
        else:
            ink = t.ink(f_huge)[1]
            t.draw(c, str(ch.number), f_huge, p["CHANNEL_GREEN"], nb.centerx,
                   nb.centery - ink // 2, align="center")
        t.draw(c, t.fit(f_large, ch.name, col_w - (name_x - info_x)), f_large, p["WHITE"],
               name_x, y_name)

        if cur:
            title = cur.title + (f"  {cur.episode}" if cur.episode else "")
            t.draw(c, t.fit(f_med, title, col_w), f_med, p["CYAN"], info_x, y_prog)
            pb_w = col_w            # its own column: 3.x let it run under NEXT
            pygame.draw.rect(c, p["TRACK"], (info_x, pb_y, pb_w, 4))
            frac = cur.progress_at(datetime.now().astimezone())
            pygame.draw.rect(c, p["GREEN"], (info_x, pb_y, int(pb_w * frac), 4))
            t.draw(c, span(cur), f_small, p["WHITE_DIM"], info_x, y_time)
        else:
            t.draw(c, "No program info", f_med, p["INK_MUTED"], info_x, y_prog)

        if nxt:
            next_w = (bx + bw) - next_x - int(W * 0.10)
            t.draw(c, "NEXT", f_small, p["ORANGE"], next_x, y_name)
            t.draw(c, t.fit(f_med, nxt.title, next_w), f_med, p["WHITE_DIM"], next_x, y_prog)
            t.draw(c, span(nxt), f_small, p["INK_MUTED"], next_x, y_time)

        right = bx + bw - 12
        t.draw(c, clock(datetime.now()), f_large, p["YELLOW"], right, y_name, align="right")
        if ch.group:
            t.draw(c, ch.group.upper()[:20], f_small, p["CYAN"], right, y_prog, align="right")
        # The clock on the banner advances while it's up: one tick pending at a time.
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def _volume(self, c, cx, cy):
        p = self.p
        v = self.app.video
        f = self.f(26)
        label = "MUTE" if v.muted else f"VOL  {v.volume:3d}"
        w = self.text.width(f, label)
        box = pygame.Rect(cx - w // 2 - 12, cy - 24, w + 24, 40)
        pygame.draw.rect(c, p["OSD_BG"], box)
        pygame.draw.rect(c, p["OSD_BORDER"], (box.x, box.y, box.w, 3))
        self.text.draw(c, label, f, p["RED"] if v.muted else p["CYAN"], cx, cy - 14, align="center")
        if not v.muted:
            pygame.draw.rect(c, p["TRACK"], (cx - 60, box.bottom + 8, 120, 6))
            col = p["GREEN"] if v.volume < 80 else p["YELLOW"] if v.volume < 95 else p["RED"]
            pygame.draw.rect(c, col, (cx - 60, box.bottom + 8, int(120 * v.volume / 100), 6))

    def _standby(self, c):
        """Dead stream: colour bars and a card instead of black."""
        W, H = self.canvas
        bw = W / 7
        for i, col in enumerate(_BARS):
            pygame.draw.rect(c, (*col, 255), (round(i * bw), 0, round((i + 1) * bw) - round(i * bw),
                                              int(H * 0.67)))
        pygame.draw.rect(c, (16, 16, 16, 255), (0, int(H * 0.67), W, H - int(H * 0.67)))
        card = pygame.Rect(0, 0, int(W * 0.56), int(H * 0.18))
        card.center = (W // 2, int(H * 0.45))
        pygame.draw.rect(c, (0, 0, 0, 255), card)
        pygame.draw.rect(c, self.p["OSD_BORDER"], card, 3)
        self.text.draw(c, "PLEASE STAND BY", self.f(56), self.p["WHITE"], card.centerx,
                       card.centery - 20, align="center")

    # ── Toast ─────────────────────────────────────────────────────────────

    def draw_toast(self, c, msg):
        p, f = self.p, self.f(24)
        w = self.text.width(f, msg) + 40
        box = pygame.Rect((self.canvas[0] - w) // 2, 62, w, 44)   # under the guide's header
        pygame.draw.rect(c, p["OSD_BG"][:3] + (240,), box, border_radius=22)
        pygame.draw.rect(c, p["OSD_BORDER"], box, 2, border_radius=22)
        self.text.draw(c, msg, f, p["WHITE"], box.centerx, box.y + 12, align="center")

    # ── Guide ─────────────────────────────────────────────────────────────
    # Fixed geometry on the 1280x720 canvas (3.x's fractions at 720p).

    guide_hours = 3
    guide_rows = 6
    _G = dict(pad=25, header_h=50, panel_h=259, ruler_h=32, ch_w=179, row_h=54, cat_h=32)

    def guide_video_box(self):
        g = self._G
        top = g["header_h"] + g["pad"]
        h = g["panel_h"] - 2 * g["pad"]
        return (g["pad"], top, int(h * 16 / 9), h)

    def draw_guide(self, c, guide):
        from datetime import timezone
        W, H = self.canvas
        g, p, t = self._G, self.p, self.text
        pad, hh = g["pad"], g["header_h"]
        ruler_y = hh + g["panel_h"]
        grid_x = pad + g["ch_w"]
        grid_w = W - pad - grid_x
        grid_y = ruler_y + g["ruler_h"]
        now = datetime.now(timezone.utc)
        start, end = guide.window()
        live = self.app.live
        f_small, f_ch, f_prog = self.f(15), self.f(18), self.f(17)

        c.fill(p["GUIDE_BG"])

        # Header: title, clock.
        pygame.draw.rect(c, p["GUIDE_HEADER_BG"], (0, 0, W, hh))
        pygame.draw.rect(c, p["OSD_BORDER"], (0, hh - 2, W, 2))
        f_title = self.f(24)
        t.draw(c, "PROGRAM GUIDE", f_title, p["YELLOW"], W // 2, (hh - t.ink(f_title)[1]) // 2,
               align="center")
        local = datetime.now()
        stamp = clock(local) + local.strftime("  %a %b ") + str(local.day)
        t.draw(c, stamp, self.f(18), p["CYAN"], W - pad, (hh - t.ink(self.f(18))[1]) // 2,
               align="right")

        # Preview: a hole the compositor fills with live video.
        vx, vy, vw, vh = self.guide_video_box()
        pygame.draw.rect(c, (0, 0, 0, 0), (vx, vy, vw, vh))
        pygame.draw.rect(c, p["OSD_BORDER"], (vx - 2, vy - 2, vw + 4, vh + 4), 2)
        if live.channel:
            lbl = f"NOW: {live.channel.number} {live.channel.name}"
            lbl = t.fit(f_small, lbl, vw - 20)
            pygame.draw.rect(c, p["OSD_BG"], (vx, vy, t.width(f_small, lbl) + 16, 26))
            t.draw(c, lbl, f_small, p["ORANGE"], vx + 8, vy + 6)
        pygame.draw.rect(c, p["OSD_BORDER"], (0, ruler_y - 2, W, 2))

        # Category bar, right of the preview.
        cx0 = vx + vw + pad
        cat = pygame.Rect(cx0, vy, W - pad - cx0, g["cat_h"])
        focused = guide.focus == "category"
        pygame.draw.rect(c, p["GUIDE_SELECTED"] if focused else p["GUIDE_TIME_BG"], cat)
        pygame.draw.rect(c, p["OSD_BORDER"], cat, 1)
        ink = p["SEL_TEXT"] if focused else p["CYAN"]
        cy = cat.y + (cat.h - t.ink(f_small)[1]) // 2
        t.draw(c, "<", f_small, ink, cat.x + 8, cy)
        t.draw(c, ">", f_small, ink, cat.right - 8, cy, align="right")
        t.draw(c, t.fit(f_small, guide.category.upper(), cat.w - 50), f_small,
               p["SEL_TEXT"] if focused else p["WHITE_DIM"], cat.centerx, cy, align="center")

        # Details of the selected channel's programme, under the bar.
        self._guide_details(c, guide, pygame.Rect(cx0, cat.bottom + 12, cat.w,
                                                  vy + vh - cat.bottom - 12), now)

        # Time ruler.
        rh = g["ruler_h"]
        pygame.draw.rect(c, p["GUIDE_TIME_BG"], (pad, ruler_y, W - 2 * pad, rh))
        t.draw(c, "CHANNEL", f_small, p["CYAN"], pad + 8, ruler_y + (rh - t.ink(f_small)[1]) // 2)
        mins = guide.hours * 60
        slots = mins // 30
        for i in range(slots):
            x = grid_x + int(i * grid_w / slots)
            pygame.draw.line(c, p["GUIDE_BORDER"], (x, ruler_y), (x, ruler_y + rh))
            label = clock((start + timedelta(minutes=30 * i)).astimezone())
            t.draw(c, label, f_small, p["WHITE"], x + 6, ruler_y + (rh - t.ink(f_small)[1]) // 2)

        vis = guide.filtered()
        rows = vis[guide.top: guide.top + guide.rows]
        for i, ch in enumerate(rows):
            self._guide_row(c, guide, ch, i, grid_y + i * g["row_h"], grid_x, grid_w,
                            start, end, now, f_small, f_ch, f_prog)
        if not vis:
            t.draw(c, "No channels in this category", f_small, p["INK_MUTED"], grid_x + 12, grid_y + 16)
            t.draw(c, "Pick another one above with < >", f_small, p["WHITE_DIM"], grid_x + 12,
                   grid_y + 44)

        # Now line through the ruler and rows.
        off = (now - start).total_seconds() / 60
        if 0 <= off <= mins:
            x = grid_x + int(off / mins * grid_w)
            pygame.draw.line(c, p["RED"][:3] + (200,), (x, ruler_y),
                             (x, grid_y + g["row_h"] * guide.rows), 2)

        # Scroll hints.
        if guide.top > 0:
            self._arrow(c, W // 2, grid_y - 6, up=True)
        if guide.top + guide.rows < len(vis):
            self._arrow(c, W // 2, grid_y + g["row_h"] * guide.rows + 6, up=False)
        pygame.draw.rect(c, p["GUIDE_BORDER"], (0, 0, W, H), 2)

    def _guide_details(self, c, guide, box, now):
        p, t = self.p, self.text
        ch = guide.selected()
        if not ch:
            return
        f_small, f_title, f_text = self.f(15), self.f(30), self.f(19)
        y = box.y
        t.draw(c, t.fit(f_small, f"{ch.number}  {ch.name}" + ("  *" if self.app.is_favorite(ch) else ""),
                        box.w), f_small, p["YELLOW"], box.x, y)
        y += t.ink(f_small)[1] + 12
        cur, _ = self.app.live.programs(ch)
        if not cur:
            t.draw(c, "No program information", f_text, p["INK_MUTED"], box.x, y)
            return
        for line in t.wrap(f_title, cur.title, box.w, 2):
            t.draw(c, line, f_title, p["WHITE"], box.x, y)
            y += t.ink(f_title)[1] + 8
        meta = "   ".join(x for x in (span(cur), cur.episode, cur.category) if x)
        t.draw(c, t.fit(f_text, meta, box.w), f_text, p["CYAN"], box.x, y + 4)
        y += t.ink(f_text)[1] + 16
        lh = t.ink(f_text)[1] + 8
        for line in t.wrap(f_text, cur.description or "", box.w, max(0, (box.bottom - y) // lh)):
            t.draw(c, line, f_text, p["WHITE_DIM"], box.x, y)
            y += lh

    def _guide_row(self, c, guide, ch, i, y, grid_x, grid_w, start, end, now, f_small, f_ch, f_prog):
        g, p, t = self._G, self.p, self.text
        rh, pad, cw = g["row_h"], g["pad"], g["ch_w"]
        selected = guide.focus == "grid" and guide.top + i == guide.cursor
        current = ch is self.app.live.channel
        bg = p["GUIDE_ROW_ODD"] if i % 2 == 0 else p["GUIDE_ROW_EVEN"]
        if selected:
            bg = p["GUIDE_SELECTED"]
        elif current:
            bg = p["GUIDE_CURRENT"]

        # Channel column: logo over number + name.
        pygame.draw.rect(c, p["GUIDE_TIME_BG"], (pad, y, cw, rh))
        if self.app.is_favorite(ch):
            t.draw(c, "*", f_small, p["YELLOW"], pad + cw - 8, y + 4, align="right")
        epg = self.app.epg
        cid = epg.resolve_channel_id(ch.epg_id, ch.name)
        logo = self.logo(epg.icon_url(cid) or ch.logo, cw - 12, int(rh * 0.5))
        num = str(ch.number)
        if logo:
            c.blit(logo, logo.get_rect(center=(pad + cw // 2, y + int(rh * 0.28))))
            ty = y + int(rh * 0.58)
        else:
            ty = y + (rh - t.ink(f_ch)[1]) // 2
        nw = t.width(f_ch, num)
        name = t.fit(f_small, ch.name, cw - 20 - nw)
        total = nw + (8 + t.width(f_small, name) if name else 0)
        x0 = pad + max(4, (cw - total) // 2)
        t.draw(c, num, f_ch, p["YELLOW"] if current else p["WHITE"], x0, ty)
        if name:
            t.draw(c, name, f_small, p["CYAN"] if current else p["WHITE_DIM"], x0 + nw + 8,
                   ty + (t.ink(f_ch)[1] - t.ink(f_small)[1]) // 2)

        # Programme cells.
        pygame.draw.rect(c, bg, (grid_x, y, grid_w, rh))
        pygame.draw.line(c, p["GUIDE_BORDER"], (pad, y + rh - 1), (grid_x + grid_w, y + rh - 1))
        if not cid:
            t.draw(c, ch.name, f_prog, p["INK_MUTED"], grid_x + 8, y + (rh - t.ink(f_prog)[1]) // 2)
            return
        mins = guide.hours * 60
        for prog in epg.programs_in_window(cid, start, end):
            a = max(0.0, (prog.start - start).total_seconds() / 60)
            b = min(float(mins), (prog.stop - start).total_seconds() / 60)
            if b <= a:
                continue
            px = grid_x + int(a / mins * grid_w)
            pw = int((b - a) / mins * grid_w)
            on_air = prog.start <= now < prog.stop
            ink = p["ONAIR_TEXT"] if on_air else p["SEL_TEXT_DIM"] if selected else p["WHITE_DIM"]
            pygame.draw.rect(c, p["GUIDE_ONAIR"] if on_air else bg, (px + 1, y + 2, pw - 2, rh - 4))
            pygame.draw.line(c, p["GUIDE_BORDER"], (px, y), (px, y + rh))
            if pw >= 8 + t.width(f_prog, "MMMM"):
                t.draw(c, t.fit(f_prog, prog.title, pw - 10), f_prog, ink, px + 5,
                       y + (rh - t.ink(f_prog)[1]) // 2)

    def _arrow(self, c, cx, y, up):
        pts = [(cx - 12, y + 6), (cx + 12, y + 6), (cx, y - 6)] if up else \
              [(cx - 12, y - 6), (cx + 12, y - 6), (cx, y + 6)]
        pygame.draw.polygon(c, self.p["CYAN"], pts)

    def _message(self, c, msg):
        W, H = self.canvas
        p = self.p
        c.fill(p["SCREEN_BG"])
        f = self.f(30)
        lines = self.text.wrap(f, msg, int(W * 0.7), 4)
        y = H // 2 - len(lines) * 22
        for line in lines:
            self.text.draw(c, line, f, p["WHITE"], W // 2, y, align="center")
            y += 44
