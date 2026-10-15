"""Cathode Classic: the 3.x look. Phosphor colours from the chosen theme, a
pixel font, static on a channel change."""

import time
from datetime import datetime

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
