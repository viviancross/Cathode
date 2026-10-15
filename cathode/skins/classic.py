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
            cur, nxt = live.programs()
            self._banner(c, live.channel, cur, nxt, full=live.banner_full)
        if live.digits:
            self.text.draw(c, live.digits + "-" * (3 - len(live.digits)), self.f(72),
                           p["CHANNEL_GREEN"], W - 48, 40, align="right", outline=(0, 0, 0))
        if live.volume_visible():
            self._volume(c, W // 2, int(H * 0.72))
        if live.trick_visible() and live.phase != "cover":
            self._trick(c, live.trick_state())

    def _trick(self, c, s):
        """VCR-style transport tag top-left, and where you are in the buffer."""
        p, t = self.p, self.text
        behind = s["behind"]
        mm, ss = divmod(int(behind), 60)
        if s["paused"]:
            tag = f"|| PAUSE  -{mm}:{ss:02d}" if behind >= 1 else "|| PAUSE"
        else:
            tag = f">  -{mm}:{ss:02d}" if behind >= 2 else ">  LIVE"
        t.draw(c, tag, self.f(48), p["WHITE"], 48, 40, outline=(0, 0, 0))
        span = s["buffer"] + behind
        if span >= 2:
            bar = pygame.Rect(48, 104, 360, 8)
            pygame.draw.rect(c, p["TRACK"], bar)
            x = bar.x + int(bar.w * s["buffer"] / span)
            pygame.draw.rect(c, p["CYAN"], (bar.x, bar.y, x - bar.x, bar.h))
            pygame.draw.rect(c, p["WHITE"], (x - 2, bar.y - 6, 4, bar.h + 12))

    def _banner(self, c, ch, cur, nxt, full=False, tag=None):
        W, H = self.canvas
        p, t = self.p, self.text
        bh = int(H * 0.155)
        bx, bw = int(W * 0.02), int(W * 0.96)
        by = H - bh - int(H * 0.025)
        f_huge, f_large, f_med, f_small = (self.f(int(bh * k)) for k in (0.55, 0.32, 0.24, 0.18))

        if full and cur and cur.description:
            # INFO again: the description opens above the bar.
            lines = t.wrap(f_med, cur.description, bw - 40, 3)
            dh = 24 + len(lines) * (t.ink(f_med)[1] + 10)
            pygame.draw.rect(c, p["OSD_BG"], (bx, by - dh - 8, bw, dh), border_radius=8)
            pygame.draw.rect(c, p["OSD_BORDER"], (bx, by - dh - 8, bw, 3))
            y = by - dh + 6
            for line in lines:
                t.draw(c, line, f_med, p["WHITE"], bx + 20, y)
                y += t.ink(f_med)[1] + 10

        edge = p["ORANGE"] if tag else p["OSD_BORDER"]
        pygame.draw.rect(c, p["OSD_BG"], (bx, by, bw, bh), border_radius=8)
        pygame.draw.rect(c, edge, (bx, by, bw, 3))
        if tag:
            tw = t.width(f_small, tag) + 20
            pygame.draw.rect(c, p["ORANGE"], (bx + 16, by - 26, tw, 26))
            t.draw(c, tag, f_small, (0, 0, 0), bx + 26, by - 20)

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

    # ── Browse ────────────────────────────────────────────────────────────

    def draw_browse(self, c, b):
        if not b.channel:
            return
        cur, nxt = b.program()
        tag = "BROWSE  -  OK: WATCH" if not b.ahead else f"BROWSE  +{b.ahead}  -  OK: WATCH"
        self._banner(c, b.channel, cur, nxt, tag=tag)

    # ── Boot ──────────────────────────────────────────────────────────────

    def draw_boot(self, c, boot):
        W, H = self.canvas
        p, t = self.p, self.text
        c.fill((0, 0, 0, 255))
        stage = boot.stage()
        age = time.monotonic() - boot.start
        if stage == "starting":
            # The tube warming up: a line that opens into the picture.
            k = min(1.0, age / 0.6)
            h = max(2, int(H * k * k))
            pygame.draw.rect(c, p["WHITE"][:3] + (int(255 * (1 - k * 0.7)),),
                             (int(W * (0.5 - 0.5 * min(1, k * 3))), (H - h) // 2,
                              int(W * min(1, k * 3)), h))
            return
        c.fill(p["SCREEN_BG"])
        logo = self._boot_logo()
        y = int(H * 0.22)
        if logo:
            c.blit(logo, logo.get_rect(midtop=(W // 2, y)))
            y += logo.get_height() + 24
        f_word, f_stage = self.f(64), self.f(26)
        t.draw(c, "CATHODE", f_word, p["CYAN"], W // 2, y, align="center")
        caption = {"signal": "Acquiring signal...", "guide": "Downloading program guide...",
                   "done": "Ready"}[stage]
        t.draw(c, caption, f_stage, p["WHITE"], W // 2, y + 110, align="center")
        bar = pygame.Rect(W // 2 - 260, y + 160, 520, 12)
        pygame.draw.rect(c, p["TRACK"], bar)
        if stage == "done":
            pygame.draw.rect(c, p["GREEN"], bar)
        else:
            x = bar.x + int((age * 260) % (bar.w + 120)) - 120     # sweeping block
            seg = pygame.Rect(x, bar.y, 120, bar.h).clip(bar)
            pygame.draw.rect(c, p["CYAN"], seg)
        t.draw(c, "Press any button to skip", self.f(16), p["INK_MUTED"], W // 2, H - 52,
               align="center")

    def _boot_logo(self):
        if not hasattr(self, "_logo_img"):
            from .. import paths
            try:
                img = pygame.image.load(paths.asset("cathode.png"))
                self._logo_img = pygame.transform.smoothscale(img, (160, 160))
            except (pygame.error, FileNotFoundError):
                self._logo_img = None
        return self._logo_img

    # ── Menus ─────────────────────────────────────────────────────────────

    MENU_ROWS = 10

    def draw_menu(self, c, m):
        W, H = self.canvas
        p, t = self.p, self.text
        f_title, f_row, f_hint = self.f(26), self.f(22), self.f(15)
        scrim = pygame.Surface((W, H), pygame.SRCALPHA)
        scrim.fill(p["SCRIM"])
        c.blit(scrim, (0, 0))
        rh, pw = 46, 620
        n = len(m.items)
        top = max(0, min(m.cursor - self.MENU_ROWS + 1, n - self.MENU_ROWS)) if n > self.MENU_ROWS else 0
        shown = m.items[top: top + self.MENU_ROWS]
        ph = 64 + len(shown) * rh + 44
        panel = pygame.Rect((W - pw) // 2, (H - ph) // 2, pw, ph)
        pygame.draw.rect(c, p["OSD_BG"][:3] + (245,), panel, border_radius=10)
        pygame.draw.rect(c, p["OSD_BORDER"], panel, 2, border_radius=10)
        t.draw(c, m.title.upper(), f_title, p["YELLOW"], panel.x + 24, panel.y + 18)
        pygame.draw.rect(c, p["OSD_BORDER"], (panel.x + 12, panel.y + 56, pw - 24, 2))
        y = panel.y + 64
        for i, it in enumerate(shown, start=top):
            row = pygame.Rect(panel.x + 12, y, pw - 24, rh - 4)
            sel = i == m.cursor
            if sel:
                pygame.draw.rect(c, p["GUIDE_SELECTED"], row, border_radius=6)
            ink = (p["SEL_TEXT"] if sel else p["WHITE"]) if it.enabled else p["INK_MUTED"]
            ty = row.y + (row.h - t.ink(f_row)[1]) // 2
            label = it.label + (" >" if it.submenu else "")
            t.draw(c, label, f_row, ink, row.x + 14, ty)
            if it.value:
                v = it.value()
                if sel and it.adjust:
                    v = f"< {v} >"
                t.draw(c, v, f_row, p["SEL_TEXT"] if sel else p["CYAN"], row.right - 14, ty, align="right")
            self.hit(row, lambda i=i: m.activate(i))
            y += rh
        if n > self.MENU_ROWS:
            if top > 0:
                self._arrow(c, panel.centerx, panel.y + 60, up=True)
            if top + self.MENU_ROWS < n:
                self._arrow(c, panel.centerx, y + 2, up=False)
        hint = "OK: select   </>: change   BACK: return   EXIT: close"
        t.draw(c, t.fit(f_hint, hint, pw - 40), f_hint, p["INK_MUTED"], panel.centerx,
               panel.bottom - 30, align="center")

    # ── On-screen keyboard ────────────────────────────────────────────────

    def draw_keyboard(self, c, kb):
        W, H = self.canvas
        p, t = self.p, self.text
        c.fill(p["SCREEN_BG"])
        f_prompt, f_field, f_key, f_hint = self.f(28), self.f(24), self.f(26), self.f(16)
        t.draw(c, kb.prompt, f_prompt, p["YELLOW"], W // 2, 60, align="center")
        field = pygame.Rect(80, 110, W - 160, 56)
        pygame.draw.rect(c, p["OSD_BG"][:3] + (255,), field)     # opaque: no video through it
        pygame.draw.rect(c, p["OSD_BORDER"], field, 2)
        # Show the end of a long value, where the caret usually is.
        before = kb.value[:kb.caret]
        shown = before
        while shown and t.width(f_field, shown) > field.w - 40:
            shown = shown[1:]
        rest = t.fit(f_field, kb.value[kb.caret:], field.w - 40 - t.width(f_field, shown))
        ty = field.y + (field.h - t.ink(f_field)[1]) // 2
        x = field.x + 16 + t.draw(c, shown, f_field, p["WHITE"], field.x + 16, ty)
        pygame.draw.rect(c, p["CYAN"], (x + 1, field.y + 10, 3, field.h - 20))
        t.draw(c, rest, f_field, p["WHITE"], x + 6, ty)
        if kb.hint:
            t.draw(c, kb.hint, f_hint, p["INK_MUTED"], W // 2, field.bottom + 14, align="center")

        grid = kb.grid()
        kw, kh, gap = 96, 64, 8
        gx = (W - (10 * kw + 9 * gap)) // 2
        y = 230
        for r, row in enumerate(grid):
            if r == len(grid) - 1:                      # the action row: wider keys
                aw = (10 * kw + 9 * gap - (len(row) - 1) * gap) // len(row)
                widths = [aw] * len(row)
                f = f_hint
            else:
                widths = [kw] * len(row)
                f = f_key
            x = gx
            for col, cell in enumerate(row):
                rect = pygame.Rect(x, y, widths[col], kh)
                sel = (r, col) == (kb.row, kb.col)
                fill = p["GUIDE_SELECTED"] if sel else p["BTN_PRIMARY_BG"] if cell == "DONE" else p["OSD_BG"]
                pygame.draw.rect(c, fill[:3] + (255,), rect, border_radius=6)
                pygame.draw.rect(c, p["OSD_BORDER"], rect, 1, border_radius=6)
                ink = p["SEL_TEXT"] if sel else p["BTN_PRIMARY_TEXT"] if cell == "DONE" else p["WHITE"]
                t.draw(c, cell, f, ink, rect.centerx, rect.y + (kh - t.ink(f)[1]) // 2, align="center")
                self.hit(rect, lambda r=r, col=col, cell=cell: (setattr(kb, "row", r), setattr(kb, "col", col),
                                                                kb._press(cell)))
                x += widths[col] + gap
            y += kh + gap
        t.draw(c, "Type on a keyboard or pick keys.  Ctrl+V pastes.  LB/RB move the cursor.",
               f_hint, p["INK_MUTED"], W // 2, H - 44, align="center")

    # ── Diagnostics ───────────────────────────────────────────────────────

    def draw_diagnostics(self, c, d):
        W, H = self.canvas
        p, t = self.p, self.text
        c.fill(p["SCREEN_BG"])
        f_title, f_row, f_hint = self.f(30), self.f(22), self.f(16)
        t.draw(c, "DIAGNOSTICS", f_title, p["YELLOW"], W // 2, 48, align="center")
        y = 120
        for label, value, pct in (("Signal strength", d.signal(), None), ("Signal quality", d.quality(), None)):
            t.draw(c, label, f_row, p["WHITE"], 160, y)
            bar = pygame.Rect(480, y - 2, 520, 26)
            pygame.draw.rect(c, p["TRACK"], bar)
            col = p["GREEN"] if value >= 70 else p["YELLOW"] if value >= 40 else p["RED"]
            pygame.draw.rect(c, col, (bar.x, bar.y, bar.w * value // 100, bar.h))
            t.draw(c, f"{value:3d}", f_row, p["WHITE"], bar.right + 20, y)
            y += 56
        y += 20
        for label, value in d.rows():
            t.draw(c, label, f_row, p["CYAN"], 160, y)
            t.draw(c, t.fit(f_row, str(value), W - 640), f_row, p["WHITE"], 480, y)
            y += 42
        t.draw(c, "BACK: return", f_hint, p["INK_MUTED"], W // 2, H - 44, align="center")

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
