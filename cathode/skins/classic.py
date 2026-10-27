"""Cathode Classic: the 3.x look. Phosphor colours from the chosen theme, a
pixel font, static on a channel change."""

import time
from datetime import datetime, timedelta

import pygame

from .. import palette
from . import Skin

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
    label = "Cathode Classic"
    canvas = (1280, 720)
    tune_cover = "static"
    # Type roles in canvas pixels: one size per job, so a job reads the same
    # on every screen. 17 is the floor for reading from the couch. Display
    # numerals (the tuned number, digits, the pause tag, link codes) stay
    # literal where they're drawn.
    TYPE = dict(hint=19, meta=19, body=22, heading=26, title=30, display=40)

    def __init__(self, app):
        super().__init__(app)
        self._tick = None
        self.reload()

    def reload(self):
        """Pick up the configured theme and font."""
        self.p = palette.resolve(self.theme_key(), self.custom_base())

    def role(self, name):
        return self.f(self.TYPE[name])

    # Classic's look lives in 3.x's config fields, so old configs carry over.
    def font_key(self):
        return self.app.config.font

    def set_font_key(self, key):
        self.app.config.font = key

    def theme_key(self):
        return self.app.config.theme

    def set_theme_key(self, key):
        self.app.config.theme = key

    def custom_base(self):
        return self.app.config.custom_palette

    def set_custom_base(self, base):
        self.app.config.custom_palette = base

    def native_base(self):
        return palette.base_colors(self.theme_key())

    # ── Live TV ───────────────────────────────────────────────────────────

    def draw_live(self, c, live):
        W, H = self.canvas
        p = self.p
        if live.message:
            # Under a menu (the first-run wizard) it would peek out around it.
            if getattr(self.app, "top", lambda: live)() is live:
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
        t.draw(c, tag, self.f(48), p["WHITE"], 64, 40, outline=(0, 0, 0))
        span = s["buffer"] + behind
        if span >= 2:
            self._blocks(c, (64, 104, 360, 14), s["buffer"] / span, p["CYAN"], p["TRACK"])
        f_btn = self.role("meta")
        for i, (_, _, label) in enumerate(s.get("buttons", ())):
            r = pygame.Rect(48 + i * 124, 136, 114, 36)
            on = i == s.get("focus")
            pygame.draw.rect(c, (p["GUIDE_SELECTED"] if on else p["OSD_BG"])[:3] + (255,), r, border_radius=6)
            pygame.draw.rect(c, p["CYAN"] if on else p["OSD_BORDER"], r, 2 if on else 1, border_radius=6)
            t.draw(c, label, f_btn, p["SEL_TEXT"] if on else p["WHITE"], r.centerx,
                   r.y + (r.h - t.ink(f_btn)[1]) // 2, align="center")
            self.hit(r, lambda i=i: s["press"](i))

    @staticmethod
    def _blocks(c, rect, frac, fill, track, block=12, gap=3):
        """A bar of square-ended blocks, lit up to frac: the TV's own OSD bar."""
        rect = pygame.Rect(rect)
        n = max(1, (rect.w + gap) // (block + gap))
        w = (rect.w - (n - 1) * gap) / n
        lit = round(n * max(0.0, min(1.0, frac)))
        for i in range(n):
            x = rect.x + round(i * (w + gap))
            pygame.draw.rect(c, fill if i < lit else track, (x, rect.y, round(w), rect.h))

    def _banner(self, c, ch, cur, nxt, full=False, tag=None):
        W, H = self.canvas
        D = type(self).canvas[1]            # sized to the design: a taller screen moves it, not grows it
        p, t = self.p, self.text
        bh = int(D * 0.155)
        bx, bw = int(W * 0.05), int(W * 0.90)
        by = H - bh - int(D * 0.05)
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
        pygame.draw.rect(c, p["OSD_BG"], (bx, by, bw, bh))
        pygame.draw.rect(c, edge, (bx, by, bw, 8))
        pygame.draw.rect(c, edge, (bx, by + bh - 4, bw, 4))
        if tag:
            tw = t.width(f_small, tag) + 20
            pygame.draw.rect(c, p["ORANGE"], (bx + 16, by - 26, tw, 26))
            t.draw(c, tag, f_small, (0, 0, 0), bx + 26, by - 20)

        # Logo box, or the number big in it when there's no logo.
        nb = pygame.Rect(bx + 8, by + 8, int(bh * 1.1), bh - 16)
        pygame.draw.rect(c, p["CHNUM_BG"], nb)
        pygame.draw.rect(c, p["OSD_BORDER"], (nb.x, nb.y, nb.w, 5))
        epg = self.app.epg
        url = epg.icon_url(epg.resolve_channel_id(ch.epg_id, ch.name)) if epg else ""
        logo = self.logo(url or ch.logo, nb.w - 10, nb.h - 10)

        info_x = nb.right + 20
        next_x = int(W * 0.45)
        col_w = next_x - info_x - 16
        tight, apart = max(2, int(bh * 0.05)), max(4, int(bh * 0.09))
        pb_h = 9
        stack = t.ink(f_large)[1] + tight + t.ink(f_med)[1] + apart + pb_h + tight + t.ink(f_small)[1]
        y_name = by + (bh - stack) // 2
        y_prog = y_name + t.ink(f_large)[1] + tight
        pb_y = y_prog + t.ink(f_med)[1] + apart
        y_time = pb_y + pb_h + tight

        name_x = info_x
        if logo is not None:
            c.blit(logo, logo.get_rect(center=nb.center))
            name_x += t.draw(c, str(ch.number), f_large, p["CHANNEL_GREEN"], info_x, y_name) + 12
        else:
            size = int(bh * 0.74)
            fn = self.f(size)
            while size > 12 and t.width(fn, str(ch.number)) > nb.w - 16:
                size -= 2
                fn = self.f(size)
            ink = t.ink(fn)[1]
            t.draw(c, str(ch.number), fn, p["CHANNEL_GREEN"], nb.centerx,
                   nb.centery - ink // 2, align="center", outline=(0, 0, 0))
        t.draw(c, t.fit(f_large, ch.name, col_w - (name_x - info_x)), f_large, p["WHITE"],
               name_x, y_name)

        if cur:
            title = cur.title + (f"  {cur.episode}" if cur.episode else "")
            t.draw(c, t.fit(f_med, title, col_w), f_med, p["CYAN"], info_x, y_prog)
            pb_w = col_w            # its own column: 3.x let it run under NEXT
            self._blocks(c, (info_x, pb_y, pb_w, pb_h), cur.progress_at(datetime.now().astimezone()),
                         p["GREEN"], p["TRACK"], block=10, gap=2)
            t.draw(c, span(cur), f_small, p["WHITE_DIM"], info_x, y_time)
        else:
            t.draw(c, "No program info", f_med, p["INK_MUTED"], info_x, y_prog)

        right = bx + bw - 12
        group = t.fit(f_small, ch.group.upper(), int(W * 0.16)) if ch.group else ""
        if nxt:
            gw = t.width(f_small, group) if group else 0
            next_w = right - gw - 24 - next_x
            t.draw(c, "NEXT", f_small, p["ORANGE"], next_x, y_name)
            t.draw(c, t.fit(f_med, nxt.title, next_w), f_med, p["WHITE_DIM"], next_x, y_prog)
            t.draw(c, span(nxt), f_small, p["INK_MUTED"], next_x, y_time)

        f_clock = self.f(int(bh * 0.40))
        t.draw(c, clock(datetime.now()), f_clock, p["YELLOW"], right, y_name, align="right", outline=(0, 0, 0))
        if group:               # under the clock, clear of it
            t.draw(c, group, f_small, p["CYAN"], right, max(y_prog, y_name + t.ink(f_clock)[1] + 6), align="right")
        # The clock on the banner advances while it's up: one tick pending at a time.
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def _volume(self, c, cx, cy):
        p = self.p
        v = self.app.video
        f = self.role("title")
        label = "MUTE" if v.muted else f"VOL  {v.volume:3d}"
        w = self.text.width(f, label)
        box = pygame.Rect(cx - w // 2 - 16, cy - 26, w + 32, 46)
        pygame.draw.rect(c, p["OSD_BG"], box)
        pygame.draw.rect(c, p["OSD_BORDER"], (box.x, box.y, box.w, 6))
        self.text.draw(c, label, f, p["RED"] if v.muted else p["CYAN"], cx, cy - 10, align="center",
                       outline=(0, 0, 0))
        if not v.muted:
            col = p["GREEN"] if v.volume < 80 else p["YELLOW"] if v.volume < 95 else p["RED"]
            self._blocks(c, (cx - 100, box.bottom + 8, 200, 14), v.volume / 100, col, p["TRACK"])

    def _osd_note(self, c, text, frac=None):
        """A small OSD box top-right; a bar under the text when frac is a
        known fraction."""
        W, H = self.canvas
        p, t = self.p, self.text
        f = self.role("meta")
        bar = frac is not None and frac >= 0
        w = max(t.width(f, text) + 32, 300 if bar else 0)
        box = pygame.Rect(W - 48 - w, 40, w, 44 + (16 if bar else 0))
        pygame.draw.rect(c, p["OSD_BG"], box)
        pygame.draw.rect(c, p["OSD_BORDER"], (box.x, box.y, box.w, 6))
        t.draw(c, text, f, p["CYAN"], box.x + 16, box.y + 16)
        if bar:
            self._blocks(c, (box.x + 16, box.bottom - 18, box.w - 32, 9), frac, p["GREEN"], p["TRACK"],
                         block=10, gap=2)

    def draw_note(self, c, text):
        self._osd_note(c, text.upper())

    def draw_guide_progress(self, c, frac):
        self._osd_note(c, "UPDATING GUIDE" + self.pct(frac), frac)

    def _standby(self, c):
        """Dead stream: colour bars and a card instead of black."""
        W, H = self.canvas
        bw = W / 7
        for i, col in enumerate(_BARS):
            pygame.draw.rect(c, (*col, 255), (round(i * bw), 0, round((i + 1) * bw) - round(i * bw),
                                              int(H * 0.67)))
        pygame.draw.rect(c, (16, 16, 16, 255), (0, int(H * 0.67), W, H - int(H * 0.67)))
        card = pygame.Rect(0, 0, int(W * 0.62), int(type(self).canvas[1] * 0.18) + 34)    # the title, a line under it
        card.center = (W // 2, int(H * 0.45))
        pygame.draw.rect(c, (0, 0, 0, 255), card)
        pygame.draw.rect(c, self.p["OSD_BORDER"], card, 3)
        self.text.draw(c, "PLEASE STAND BY", self.f(56), self.p["WHITE"], card.centerx,
                       card.centery - 38, align="center")
        self.text.draw(c, f"Still trying. {self.k('GUIDE')} or a channel number to change.", self.role("body"),
                       self.p["WHITE_DIM"], card.centerx, card.centery + 30, align="center")

    # ── Browse ────────────────────────────────────────────────────────────

    def draw_browse(self, c, b):
        if not b.channel:
            return
        cur, nxt = b.program()
        ok = self.k("SELECT")
        tag = f"BROWSE  -  {ok}: WATCH" if not b.ahead else f"BROWSE  +{b.ahead}  -  {ok}: WATCH"
        self._banner(c, b.channel, cur, nxt, tag=tag)

    # ── Boot ──────────────────────────────────────────────────────────────

    REMOTE_WORDS = {"SELECT": "OK"}

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
        f_word, f_stage = self.f(64), self.role("heading")
        t.draw(c, "CATHODE", f_word, p["CYAN"], W // 2, y, align="center")
        caption = {"signal": "Acquiring signal...", "guide": "Downloading program guide..." + self.guide_pct(),
                   "done": "Ready"}[stage]
        t.draw(c, caption, f_stage, p["WHITE"], W // 2, y + 110, align="center")
        bar = pygame.Rect(W // 2 - 260, y + 160, 520, 12)
        pygame.draw.rect(c, p["TRACK"], bar)
        g = getattr(self.app, "guide_progress", None)
        if stage == "done":
            pygame.draw.rect(c, p["GREEN"], bar)
        elif stage == "guide" and g is not None and g >= 0:       # the real download, not a sweep
            pygame.draw.rect(c, p["CYAN"], (bar.x, bar.y, int(bar.w * g), bar.h))
        else:
            x = bar.x + int((age * 260) % (bar.w + 120)) - 120     # sweeping block
            seg = pygame.Rect(x, bar.y, 120, bar.h).clip(bar)
            pygame.draw.rect(c, p["CYAN"], seg)
        t.draw(c, "Press any button to skip", self.role("hint"), p["INK_MUTED"], W // 2, H - 52,
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
        f_title, f_row, f_hint = self.role("heading"), self.role("body"), self.role("hint")
        scrim = pygame.Surface((W, H), pygame.SRCALPHA)
        scrim.fill(p["SCRIM"])
        c.blit(scrim, (0, 0))
        n = len(m.items)
        about = m.items[m.cursor].help if 0 <= m.cursor < n else ""
        rh, pw, foot = 46, 620, 46 + (30 if about else 0)
        top = max(0, min(m.cursor - self.MENU_ROWS + 1, n - self.MENU_ROWS)) if n > self.MENU_ROWS else 0
        shown = m.items[top: top + self.MENU_ROWS]
        ph = 64 + len(shown) * rh + 10 + foot
        panel = pygame.Rect((W - pw) // 2, (H - ph) // 2, pw, ph)
        pygame.draw.rect(c, p["OSD_BG"][:3] + (245,), panel, border_radius=10)
        pygame.draw.rect(c, p["OSD_BORDER"], panel, 2, border_radius=10)
        t.draw(c, m.title.upper(), f_title, p["YELLOW"], panel.x + 24, panel.y + 18)
        pygame.draw.rect(c, p["OSD_BORDER"], (panel.x + 12, panel.y + 54, pw - 24, 6))
        y = panel.y + 64
        for i, it in enumerate(shown, start=top):
            row = pygame.Rect(panel.x + 12, y, pw - 24, rh - 4)
            sel = i == m.cursor
            if sel:
                pygame.draw.rect(c, p["GUIDE_SELECTED"], row)
            ink = (p["SEL_TEXT"] if sel else p["WHITE"]) if it.enabled else p["INK_MUTED"]
            ty = row.y + (row.h - t.ink(f_row)[1]) // 2
            label = it.label + (" >" if it.submenu else "")
            v = it.value() if it.value else ""
            if v and sel and it.adjust:
                v = f"< {v} >"
            room = row.w - 28 - (t.width(f_row, v) + 16 if v else 0)
            t.draw(c, t.fit(f_row, label, room), f_row, ink, row.x + 14, ty)
            if v:
                t.draw(c, v, f_row, p["SEL_TEXT"] if sel else p["CYAN"], row.right - 14, ty, align="right")
            self.hit(row, lambda i=i: m.activate(i))
            y += rh
        if n > self.MENU_ROWS:
            if top > 0:
                self._arrow(c, panel.centerx, panel.y + 60, up=True)
            if top + self.MENU_ROWS < n:
                self._arrow(c, panel.centerx, y + 2, up=False)
        pygame.draw.rect(c, p["OSD_BORDER"], (panel.x + 12, panel.bottom - foot, pw - 24, 1))
        if about:
            t.draw(c, t.fit(f_hint, about, pw - 40), f_hint, p["WHITE_DIM"], panel.centerx,
                   panel.bottom - foot + 12, align="center")
        change = "   </>: change" if any(it.adjust for it in m.items) else ""
        hint = f"{self.k('SELECT')}: select{change}   {self.k('BACK')}: back   {self.k('EXIT')}: close"
        if t.width(f_hint, hint) > pw - 40:        # a remote's longer names: tighter, not cut
            hint = f"{self.k('SELECT')}: select{change.replace('   ', '  ')}  {self.k('BACK')}: back  {self.k('EXIT')}: close"
        t.draw(c, t.fit(f_hint, hint, pw - 40), f_hint, p["INK_MUTED"], panel.centerx,
               panel.bottom - 46 + (46 - t.ink(f_hint)[1]) // 2, align="center")

    # ── On-screen keyboard ────────────────────────────────────────────────

    def draw_keyboard(self, c, kb):
        W, H = self.canvas
        p, t = self.p, self.text
        c.fill(p["SCREEN_BG"])
        f_prompt, f_field, f_key, f_hint = self.role("heading"), self.role("body"), self.role("heading"), self.role("hint")
        f_act = self.role("meta")
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
                f = f_act
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
        t.draw(c, kb.tip(), f_hint, p["INK_MUTED"], W // 2, H - 60, align="center")

    # ── On Demand: browse ─────────────────────────────────────────────────

    OD_ROW_H = 56
    OD_TOP = 108
    OD_TILE = (150, 225)        # poster, 2:3: two whole rows fit under the header
    OD_GAP = 26

    def layout_canvas(self):
        """The size these screens are laid out at (a 4:3 box skin draws them
        larger and scales down)."""
        return self.canvas

    def tall(self, name: str) -> bool:
        return True         # Classic lays every screen out against the canvas height

    def ondemand_cols(self, screen) -> int:
        W = self.layout_canvas()[0]
        return max(1, (W - 128 + self.OD_GAP) // (self.OD_TILE[0] + self.OD_GAP))

    def ondemand_page(self, screen) -> int:
        H = self.layout_canvas()[1]
        if screen.view == "wall":
            return self.ondemand_cols(screen) * 2
        return (H - self.OD_TOP - 40) // self.OD_ROW_H

    def draw_ondemand(self, c, s):
        W, H = self.canvas
        p, t = self.p, self.text
        c.fill(p["SCREEN_BG"])
        f_title, f_crumb, f_btn = self.role("title"), self.role("hint"), self.role("meta")
        pygame.draw.rect(c, p["GUIDE_HEADER_BG"], (0, 0, W, 92))
        pygame.draw.rect(c, p["OSD_BORDER"], (0, 90, W, 2))
        # Cathode 3 called this PLEX-PER-VIEW, and Classic still does: the
        # top level wears the name, deeper levels their own title under it.
        deep = s.level and s.mode == "browse" and len(s.stack) > 1
        title = s.level["title"] if deep else "PLEX-PER-VIEW"
        t.draw(c, t.fit(f_title, title, W - 460), f_title, p["YELLOW"], 64, 36)
        crumb = s.crumb() if deep else ("Movies and shows from your Plex server" if s.mode == "browse" else "")
        if crumb:
            t.draw(c, t.fit(f_crumb, crumb, W - 460), f_crumb, p["INK_MUTED"], 64, 64)
        x, f_key = W - 64, self.role("hint")
        for key, word, fn in ((self.k("BACK"), "back", s.back), (self.k("MENU"), "options", lambda: s.handle("MENU"))):
            seg = f"{key}: {word}"
            w = t.width(f_key, seg)
            t.draw(c, seg, f_key, p["INK_MUTED"], x - w, 46 - t.ink(f_key)[1] // 2)
            self.hit((x - w, 36, w, 24), fn)
            x -= w + 28
        if s.status:
            t.draw(c, s.status, f_btn, p["ORANGE"], x - 10, 38, align="right")

        if s.mode == "auth":
            self._od_auth(c, s)
        elif s.view == "wall":
            self._od_wall(c, s)
        else:
            self._od_list(c, s)

    def _od_auth(self, c, s):
        W, H = self.canvas
        p, t = self.p, self.text
        t.draw(c, "Link your Plex account", self.role("title"), p["WHITE"], W // 2, 180, align="center")
        if s.auth_code:
            t.draw(c, "On a phone or computer, go to", self.role("body"), p["WHITE_DIM"], W // 2, 250,
                   align="center")
            t.draw(c, s.auth_link or "plex.tv/link", self.role("title"), p["CYAN"], W // 2, 290, align="center")
            t.draw(c, "and enter this code:", self.role("body"), p["WHITE_DIM"], W // 2, 350, align="center")
            t.draw(c, s.auth_code, self.f(84), p["CHANNEL_GREEN"], W // 2, 400, align="center")
        t.draw(c, f"{self.k('BACK')}: back to TV", self.role("hint"), p["INK_MUTED"], W // 2, H - 60, align="center")

    def _od_list(self, c, s):
        W, H = self.canvas
        p, t = self.p, self.text
        rows, rh = s.rows, self.OD_ROW_H
        n_vis = self.ondemand_page(s)
        top = max(0, min(s.sel - n_vis // 2, len(rows) - n_vis))
        f_row, f_meta = self.role("body"), self.role("meta")
        y = self.OD_TOP
        for i in range(top, min(len(rows), top + n_vis)):
            row = rows[i]
            r = pygame.Rect(64, y, W - 128, rh - 6)
            sel = i == s.sel
            pygame.draw.rect(c, p["GUIDE_SELECTED"] if sel else p["OSD_BG"][:3] + (255,), r,
                             border_radius=6)
            ink = p["SEL_TEXT"] if sel else p["WHITE"]
            meta = row.get("meta", "")      # recordings: their state ("42%", "PAUSED")
            # The order marker, as the PPV menu had it: ORDER on something that
            # plays, OPEN on a show or season, nothing on the sort row.
            mark = "ORDER" if row.get("playable") else "OPEN" if row.get("type") in ("show", "season") else ""
            right = r.right - 16
            if mark:
                t.draw(c, mark, f_meta, p["SEL_TEXT"] if sel else p["CHANNEL_GREEN"], right,
                       r.y + (r.h - t.ink(f_meta)[1]) // 2, align="right")
                right -= t.width(f_meta, "ORDER") + 24
            mw = (r.right - right) + (t.width(f_meta, meta) + 20 if meta else 0)
            ty = r.y + (r.h - t.ink(f_row)[1]) // 2
            t.draw(c, t.fit(f_row, row.get("title", ""), r.w - mw - 40), f_row, ink, r.x + 16, ty)
            if meta:
                t.draw(c, meta, f_meta, p["SEL_TEXT_DIM"] if sel else p["INK_MUTED"], right,
                       r.y + (r.h - t.ink(f_meta)[1]) // 2, align="right")
            off, dur = row.get("offset", 0), row.get("duration", 0)
            if off and dur:             # part way through: a resume bar along the row
                pygame.draw.rect(c, p["TRACK"], (r.x + 16, r.bottom - 7, r.w - 32, 3))
                pygame.draw.rect(c, p["ORANGE"], (r.x + 16, r.bottom - 7, int((r.w - 32) * min(1, off / dur)), 3))
            self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))
            y += rh
        if top > 0:
            self._arrow(c, W // 2, self.OD_TOP - 8, up=True)
        if top + n_vis < len(rows):
            self._arrow(c, W // 2, y + 2, up=False)

    def _od_wall(self, c, s):
        W, H = self.canvas
        p, t = self.p, self.text
        off = s.wall_offset
        rows = s.rows[off:]
        cols = self.ondemand_cols(s)
        tw, th = self.OD_TILE
        gap = self.OD_GAP
        f = self.role("hint")
        label_h = 2 * (t.ink(f)[1] + 4) + 8
        row_h = th + label_h + gap
        x0 = (W - (cols * tw + (cols - 1) * gap)) // 2
        y = self.OD_TOP + 8
        # A taller screen than two rows need: the wall sits mid-way down it.
        y += max(0, H - y - 2 * row_h - (40 if off else 0) - 40) // 2
        if off:     # the Sort row: a bar above the posters, not a poster
            bar = pygame.Rect(x0, y - 4, W - 2 * x0, 32)
            on = s.sel == 0
            pygame.draw.rect(c, p["GUIDE_SELECTED"] if on else p["OSD_BG"][:3] + (255,), bar,
                             border_radius=6)
            t.draw(c, s.rows[0]["title"], f, p["SEL_TEXT"] if on else p["WHITE_DIM"], bar.x + 12,
                   bar.y + (bar.h - t.ink(f)[1]) // 2)
            self.hit(bar, lambda: (setattr(s, "sel", 0), s.select()))
            y += 40
        cur = max(0, s.sel - off)
        first_row = max(0, cur // cols - 1)
        for i in range(first_row * cols, min(len(rows), (first_row + 2) * cols)):
            row = rows[i]
            col = i % cols
            r = pygame.Rect(x0 + col * (tw + gap), y + (i // cols - first_row) * row_h, tw, th)
            sel = i + off == s.sel
            pygame.draw.rect(c, p["OSD_BG"][:3] + (255,), r)
            art = self.app.ondemand.poster(row.get("thumb", ""), tw, th) if row.get("thumb") else None
            if art:
                c.blit(art, art.get_rect(center=r.center))
            else:
                lines = t.wrap(f, row.get("title", ""), tw - 16, 4)
                ly = r.y + 20
                for line in lines:
                    t.draw(c, line, f, p["WHITE_DIM"], r.centerx, ly, align="center")
                    ly += t.ink(f)[1] + 6
            seen, dur = row.get("offset", 0), row.get("duration", 0)
            if seen and dur:
                pygame.draw.rect(c, p["TRACK"], (r.x, r.bottom - 5, r.w, 5))
                pygame.draw.rect(c, p["ORANGE"], (r.x, r.bottom - 5, int(r.w * min(1, seen / dur)), 5))
            pygame.draw.rect(c, p["YELLOW"] if sel else p["OSD_BORDER"], r.inflate(6, 6) if sel else r,
                             3 if sel else 1)
            if art:     # with no art the title is already on the plate
                for k, line in enumerate(t.wrap(f, row.get("title", ""), tw, 2)):
                    t.draw(c, line, f, p["WHITE"] if sel else p["WHITE_DIM"], r.centerx,
                           r.bottom + 8 + k * (t.ink(f)[1] + 4), align="center")
            self.hit(r, lambda i=i + off: (setattr(s, "sel", i), s.select()))

    # ── On Demand: item info ──────────────────────────────────────────────

    def draw_iteminfo(self, c, info):
        from ..screens.iteminfo import PRIMARY, hms
        W, H = self.canvas
        p, t = self.p, self.text
        d = info.detail
        c.fill(p["SCREEN_BG"])
        # The order screen's own header band, as the list page has: this is
        # PLEX-PER-VIEW, and a recording is MY RECORDINGS.
        f_band = self.role("title")
        pygame.draw.rect(c, p["GUIDE_HEADER_BG"], (0, 0, W, 60))
        pygame.draw.rect(c, p["OSD_BORDER"], (0, 58, W, 2))
        t.draw(c, "MY RECORDINGS" if info.kind == "download" else "PLEX-PER-VIEW", f_band, p["YELLOW"], 64,
               30 - t.ink(f_band)[1] // 2)
        t.draw(c, "ORDER SCREEN" if info.kind != "download" else "RECORDED", self.role("hint"), p["INK_MUTED"],
               W - 64, 30 - t.ink(self.role("hint"))[1] // 2, align="right")
        poster = pygame.Rect(60, 88, 300, 450)
        pygame.draw.rect(c, p["OSD_BG"][:3] + (255,), poster)
        # A server URL (token in the headers) or, for a recording, a file on disk.
        art = self.logo(d.get("poster", ""), poster.w, poster.h, headers=d.get("poster_headers") or None)
        if art:
            c.blit(art, art.get_rect(center=poster.center))
        pygame.draw.rect(c, p["OSD_BORDER"], poster, 2)

        x, w = poster.right + 50, W - poster.right - 110
        f_title, f_meta, f_text = self.role("display"), self.role("meta"), self.role("body")
        y = 94
        for line in t.wrap(f_title, d.get("title", ""), w, 2):
            t.draw(c, line, f_title, p["WHITE"], x, y)
            y += t.ink(f_title)[1] + 10
        meta = d.get("subtitle") or d.get("meta", "")
        if meta:
            t.draw(c, t.fit(f_meta, meta, w), f_meta, p["CYAN"], x, y + 6)
            y += t.ink(f_meta)[1] + 22
        if info.kind != "download":
            t.draw(c, "Cost: Free", f_meta, p["CYAN"], x, y)
            y += t.ink(f_meta)[1] + 18
        if d.get("offset", 0) > 5:
            t.draw(c, f"Resume at {hms(d['offset'])}", f_meta, p["ORANGE"], x, y)
            y += t.ink(f_meta)[1] + 18
        lh = t.ink(f_text)[1] + 10
        for line in t.wrap(f_text, d.get("summary", ""), w, max(1, (520 - y) // lh)):
            t.draw(c, line, f_text, p["WHITE_DIM"], x, y)
            y += lh

        bs = info.buttons()
        f_btn = self.role("body")
        bw = min(200, (W - 120 - (len(bs) - 1) * 16) // len(bs))
        bx = (W - (len(bs) * bw + (len(bs) - 1) * 16)) // 2
        for i, b in enumerate(bs):
            r = pygame.Rect(bx, H - 140, bw, 56)
            sel = i == info.focus
            fill = p["GUIDE_SELECTED"] if sel else p["BTN_PRIMARY_BG"] if b in PRIMARY else p["OSD_BG"]
            pygame.draw.rect(c, fill[:3] + (255,), r, border_radius=8)
            pygame.draw.rect(c, p["CYAN"] if b in PRIMARY else p["OSD_BORDER"], r, 2, border_radius=8)
            ink = p["SEL_TEXT"] if sel else p["BTN_PRIMARY_TEXT"] if b in PRIMARY else p["WHITE"]
            # An offer is ORDERed, as the PPV menu said; a recording plays.
            label = {"play": "ORDER", "playall": "ORDER ALL"}.get(b, info.label(b)) if info.kind != "download" \
                else info.label(b)
            t.draw(c, t.fit(f_btn, label, bw - 16), f_btn, ink, r.centerx,
                   r.y + (r.h - t.ink(f_btn)[1]) // 2, align="center")
            self.hit(r, lambda i=i, b=b: (setattr(info, "focus", i), info.press(b)))
            bx += bw + 16

    # ── On Demand: playback ───────────────────────────────────────────────

    def draw_playback(self, c, pb):
        from ..screens.iteminfo import hms
        W, H = self.canvas
        p, t = self.p, self.text
        paused = self.app.video.paused
        tag = "|| PAUSE" if paused else pb.flash[0] if time.monotonic() < pb.flash[1] else ""
        if tag:
            t.draw(c, tag, self.f(48), p["WHITE"], 64, 40, outline=(0, 0, 0))
        if pb.skip_label and self.on_top(pb):
            r = pygame.Rect(W - 314, H - 246 if pb.bar_visible() else H - 126, 250, 56)
            pygame.draw.rect(c, p["OSD_BG"][:3] + (240,), r, border_radius=8)
            pygame.draw.rect(c, p["YELLOW"], r, 2, border_radius=8)
            f_skip = self.role("body")
            t.draw(c, f"{pb.skip_label}  ({self.k('SELECT')})", f_skip, p["YELLOW"], r.centerx,
                   r.y + (r.h - t.ink(f_skip)[1]) // 2, align="center")
            self.hit(r, lambda: pb.handle("SELECT"))
        if not pb.bar_visible():
            return
        bar = pygame.Rect(64, H - 186, W - 128, 150)
        pygame.draw.rect(c, p["OSD_BG"], bar, border_radius=8)
        pygame.draw.rect(c, p["OSD_BORDER"], (bar.x, bar.y, bar.w, 3))
        f_title, f_sub, f_btn = self.role("heading"), self.role("meta"), self.role("meta")
        t.draw(c, t.fit(f_title, pb.title, bar.w - 300), f_title, p["WHITE"], bar.x + 20, bar.y + 16)
        t.draw(c, t.fit(f_sub, pb.subtitle, bar.w - 300), f_sub, p["CYAN"], bar.x + 20, bar.y + 50)
        q = self.app.ondemand.queue
        if q.items and q.pos >= 0:
            t.draw(c, f"{q.pos + 1} of {len(q.items)}", f_sub, p["INK_MUTED"], bar.right - 20,
                   bar.y + 20, align="right")
        # Timeline: elapsed, track, duration. Click to jump.
        tl = pygame.Rect(bar.x + 110, bar.y + 80, bar.w - 220, 12)
        frac = min(1.0, pb.pos / pb.dur) if pb.dur else 0.0
        self._blocks(c, tl, frac, p["GREEN"], p["TRACK"])       # the set's own OSD bar, as the volume has
        t.draw(c, hms(pb.pos), f_sub, p["WHITE"], tl.x - 14, tl.y - 4, align="right")
        t.draw(c, hms(pb.dur) if pb.dur else "--:--", f_sub, p["WHITE"], tl.right + 14, tl.y - 4)
        self.hit(tl.inflate(0, 24), lambda: pb.seek_to(self._click_frac(tl)))
        # Transport buttons, for the mouse (the remote acts on its own keys).
        buttons = pb.transport()
        bw = 104
        x = bar.centerx - (len(buttons) * bw + (len(buttons) - 1) * 10) // 2
        rects = []
        for k, (_, label, fn) in enumerate(buttons):
            r = pygame.Rect(x, bar.y + 104, bw, 34)
            rects.append(r)
            on = k == getattr(pb, "tfocus", None)
            pygame.draw.rect(c, (p["GUIDE_SELECTED"] if on else p["OSD_BG"])[:3] + (255,), r, border_radius=6)
            pygame.draw.rect(c, p["CYAN"] if on else p["OSD_BORDER"], r, 2 if on else 1, border_radius=6)
            t.draw(c, label, f_btn, p["SEL_TEXT"] if on else p["WHITE"], r.centerx, r.y + (r.h - t.ink(f_btn)[1]) // 2,
                   align="center")
            self.hit(r, fn)
            x += bw + 10
        self.idle_row(c, pb, rects, 6)

    def _click_frac(self, rect) -> float:
        """Where the last click landed across `rect`, 0..1."""
        pt = self.app.gfx.to_canvas(self.canvas, *pygame.mouse.get_pos())
        return max(0.0, min(1.0, ((pt[0] if pt else rect.x) - rect.x) / max(1, rect.w)))

    # ── Remap capture ─────────────────────────────────────────────────────

    def draw_capture(self, c, cap):
        W, H = self.canvas
        p, t = self.p, self.text
        f = self.role("heading")
        box = pygame.Rect(0, 0, 900, 140)
        box.center = (W // 2, H // 2)
        pygame.draw.rect(c, p["OSD_BG"][:3] + (250,), box, border_radius=10)
        pygame.draw.rect(c, p["YELLOW"], box, 2, border_radius=10)
        t.draw(c, t.fit(f, cap.prompt, box.w - 40), f, p["WHITE"], box.centerx, box.y + 40,
               align="center")
        t.draw(c, "Waiting...", self.role("meta"), p["INK_MUTED"], box.centerx, box.y + 90, align="center")

    # ── Diagnostics ───────────────────────────────────────────────────────

    def draw_diagnostics(self, c, d):
        W, H = self.canvas
        p, t = self.p, self.text
        c.fill(p["SCREEN_BG"])
        f_title, f_row, f_hint = self.role("title"), self.role("body"), self.role("hint")
        t.draw(c, "DIAGNOSTICS", f_title, p["YELLOW"], W // 2, 48, align="center")
        y = 120
        for label, value, pct in (("Signal strength", d.signal(), None), ("Signal quality", d.quality(), None)):
            t.draw(c, label, f_row, p["CYAN"], 160, y)
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
        t.draw(c, f"{self.k('BACK')}: back", f_hint, p["INK_MUTED"], W // 2, H - 60, align="center")

    # ── Toast ─────────────────────────────────────────────────────────────

    def draw_toast(self, c, msg):
        p, t, f = self.p, self.text, self.role("heading")
        room = self.canvas[0] - 160
        lines = t.wrap(f, msg, room, 3)
        lh = t.ink(f)[1] + 12
        w = max(t.width(f, line) for line in lines) + 40
        h = 20 + lh * len(lines)
        screens = getattr(self.app, "screens", None) or []
        top = screens[-1] if screens else None
        # Under the guide's header, or over live TV; on the other pages it
        # sits at the foot, clear of their titles.
        y = 62 if self.over_picture() or getattr(top, "name", "") == "guide" else self.canvas[1] - 20 - h
        box = pygame.Rect((self.canvas[0] - w) // 2, y, w, h)
        radius = 22 if len(lines) == 1 else 12
        pygame.draw.rect(c, p["OSD_BG"][:3] + (240,), box, border_radius=radius)
        pygame.draw.rect(c, p["OSD_BORDER"], box, 2, border_radius=radius)
        for k, line in enumerate(lines):
            t.draw(c, line, f, p["WHITE"], box.centerx, box.y + 16 + k * lh, align="center")

    # ── Guide ─────────────────────────────────────────────────────────────
    # Fixed geometry on the 1280x720 canvas (3.x's fractions at 720p).

    guide_hours = 3
    _G = dict(pad=64, gap=25, header_h=64, panel_h=245, ruler_h=32, ch_w=179, row_h=50, cat_h=32)

    @property
    def guide_rows(self):
        return 6 + self.grow // self._G["row_h"]       # a taller screen lists more channels

    def guide_video_box(self):
        g = self._G
        top = g["header_h"] + g["gap"]
        h = g["panel_h"] - 2 * g["gap"]
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
        f_small, f_ch, f_prog = self.role("hint"), self.role("meta"), self.role("meta")

        c.fill(p["GUIDE_BG"])

        # Header: title, clock.
        pygame.draw.rect(c, p["GUIDE_HEADER_BG"], (0, 0, W, hh))
        pygame.draw.rect(c, p["OSD_BORDER"], (0, hh - 2, W, 2))
        f_title, f_stamp = self.role("heading"), self.role("meta")
        t.draw(c, "PROGRAM GUIDE", f_title, p["YELLOW"], W // 2, hh - t.ink(f_title)[1] - 10,
               align="center")
        local = datetime.now()
        stamp = clock(local) + local.strftime("  %a %b ") + str(local.day)
        t.draw(c, stamp, f_stamp, p["CYAN"], W - pad, hh - t.ink(f_stamp)[1] - 10,
               align="right")
        wx = self.app.weather.current() if self.app.weather else None
        if wx:
            self._weather(c, wx, pad, hh, W // 2 - t.width(f_title, "PROGRAM GUIDE") // 2 - pad)

        # Preview: a hole the compositor fills with live video.
        vx, vy, vw, vh = self.guide_video_box()
        self.hole(c, (vx, vy, vw, vh))
        pygame.draw.rect(c, p["OSD_BORDER"], (vx - 2, vy - 2, vw + 4, vh + 4), 2)
        if live.channel:
            lbl = f"NOW: {live.channel.number} {live.channel.name}"
            lbl = t.fit(f_small, lbl, vw - 20)
            pygame.draw.rect(c, p["OSD_BG"], (vx, vy, t.width(f_small, lbl) + 16, 26))
            t.draw(c, lbl, f_small, p["ORANGE"], vx + 8, vy + 6)
        pygame.draw.rect(c, p["OSD_BORDER"], (0, ruler_y - 2, W, 2))

        # Category bar, right of the preview.
        cx0 = vx + vw + g["gap"]
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
            t.draw(c, self.empty_guide(guide), f_ch, p["WHITE"], grid_x + 12, grid_y + 16)
            t.draw(c, "Or pick another list above with < >", f_small, p["WHITE_DIM"], grid_x + 12,
                   grid_y + 48)

        # Now line through the ruler and rows.
        off = (now - start).total_seconds() / 60
        if 0 <= off <= mins:
            x = grid_x + int(off / mins * grid_w)
            pygame.draw.line(c, p["RED"][:3] + (200,), (x, ruler_y + g["ruler_h"] - 6),      # a tick in the ruler, clear of its labels
                             (x, grid_y + g["row_h"] * guide.rows), 2)
        k = guide.cursor - guide.top
        if guide.focus == "grid" and 0 <= k < len(rows):
            pygame.draw.rect(c, p["YELLOW"], (pad - 2, grid_y + k * g["row_h"] - 2, W - 2 * pad + 4,
                                              g["row_h"] + 3), 5)

        # The key hints, in the band under the grid.
        band = grid_y + g["row_h"] * guide.rows
        hint = f"{self.k('SELECT')}: watch   </>: show by show   CH+/-: page   REW/FF: a day   {self.k('EXIT')}: close"
        t.draw(c, t.fit(f_small, hint, W - 2 * pad), f_small, p["INK_MUTED"], W // 2, band + 18, align="center")

        # Scroll hints.
        if guide.top > 0:
            self._arrow(c, grid_x - 20, ruler_y + g["ruler_h"] // 2, up=True)
        if guide.top + guide.rows < len(vis):
            self._arrow(c, W // 2, grid_y + g["row_h"] * guide.rows + 6, up=False)
        pygame.draw.rect(c, p["GUIDE_BORDER"], (0, 0, W, H), 2)

    def _weather(self, c, w, x, hh, right):
        """Icon and two lines of conditions, left of the guide's title."""
        p, t = self.p, self.text
        f = self.role("hint")
        s = min(hh - 12, 40)
        line1 = f"{w.get('temp', '')}{w.get('units', 'F')}  {w.get('conditions', '')}"    # the pixel font has no degree sign
        line2 = "   ".join(x for x in (w.get("city"), f"{w['humidity']}% RH" if w.get("humidity") else "",
                                      f"{w['rain']}% rain" if w.get("rain") else "") if x)
        avail = right - x - s - 8
        if avail < 60:
            return
        self._weather_icon(c, x, hh - s - 6, s, w.get("category", "cloudy"))
        lh = t.ink(f)[1] + 4
        y = hh - 2 * lh - 4
        t.draw(c, t.fit(f, line1, avail), f, p["WHITE"], x + s + 8, y)
        t.draw(c, t.fit(f, line2, avail), f, p["WHITE_DIM"], x + s + 8, y + lh)

    def _weather_icon(self, c, x, y, s, cat):
        p = self.p
        night = not 6 <= datetime.now().hour < 19

        def disc(cx, cy, r):
            col = (228, 228, 214, 255) if night else p["YELLOW"]
            pygame.draw.circle(c, col, (int(cx), int(cy)), int(r))

        def cloud(bx, by, bw, bh, col):
            r = bh / 2
            pygame.draw.circle(c, col, (int(bx + r), int(by + bh - r)), int(r))
            pygame.draw.circle(c, col, (int(bx + bw - r), int(by + bh - r)), int(r))
            pygame.draw.ellipse(c, col, (bx + bw * 0.28, by, bw * 0.44, bh * 0.95))
            pygame.draw.rect(c, col, (bx + r, by + bh - r, bw - 2 * r, r))
        if cat == "clear":
            disc(x + s / 2, y + s / 2, s * 0.28)
            return
        if cat == "partly":
            disc(x + s * 0.32, y + s * 0.34, s * 0.2)
            cloud(x + s * 0.28, y + s * 0.42, s * 0.66, s * 0.4, p["WHITE_DIM"])
            return
        cloud(x + s * 0.08, y + s * 0.18, s * 0.84, s * 0.5,
              p["INK_MUTED"] if cat == "fog" else p["WHITE_DIM"])
        base = y + s * 0.72
        for i in range(3):
            dx = x + s * (0.3 + i * 0.2)
            if cat == "rain":
                pygame.draw.line(c, p["CYAN"], (dx, base), (dx - s * 0.08, base + s * 0.2), 2)
            elif cat == "snow":
                pygame.draw.circle(c, p["WHITE"], (int(dx), int(base + s * 0.12)), 2)
        if cat == "storm":
            cx = x + s / 2
            pygame.draw.polygon(c, p["YELLOW"], [(cx, base), (cx - s * 0.12, base + s * 0.16),
                                                 (cx, base + s * 0.16), (cx - s * 0.06, base + s * 0.3)])

    # ── Screensaver ───────────────────────────────────────────────────────

    def draw_screensaver(self, c, ss):
        W, H = self.canvas
        c.fill((0, 0, 0, 255))
        logo = self._boot_logo()
        f = self.role("display")
        lw = logo.get_width() if logo else 0
        bw = max(lw, self.text.width(f, "CATHODE"))
        bh = (logo.get_height() + 12 if logo else 0) + self.text.ink(f)[1]
        x, y = ss.position(bw, bh, W, H)
        if logo:
            c.blit(logo, (x + (bw - lw) // 2, y))
            y += logo.get_height() + 12
        self.text.draw(c, "CATHODE", f, self.p["CYAN"], x + bw // 2, y, align="center")

    def _guide_details(self, c, guide, box, now):
        p, t = self.p, self.text
        ch = guide.selected()
        if not ch:
            return
        f_small, f_title, f_text = self.role("hint"), self.role("title"), self.role("meta")
        y = box.y
        t.draw(c, t.fit(f_small, f"{ch.number}  {ch.name}" + ("  *" if self.app.is_favorite(ch) else ""),
                        box.w), f_small, p["YELLOW"], box.x, y)
        y += t.ink(f_small)[1] + 12
        cur = guide.selected_program()
        if not cur:
            t.draw(c, "No program information", f_text, p["INK_MUTED"], box.x, y)
            return
        art = self.logo(cur.icon, 72, box.h - 4) if cur.icon else None
        w = box.w
        if art:                             # the poster at the panel's right, text clear of it
            c.blit(art, (box.right - art.get_width(), box.y))
            w = box.w - art.get_width() - 12
        for line in t.wrap(f_title, cur.title, w, 2):
            t.draw(c, line, f_title, p["WHITE"], box.x, y)
            y += t.ink(f_title)[1] + 8
        meta = "   ".join(x for x in (span(cur), cur.episode, cur.category) if x)
        t.draw(c, t.fit(f_text, meta, w), f_text, p["CYAN"], box.x, y + 4)
        y += t.ink(f_text)[1] + 16
        lh = t.ink(f_text)[1] + 8
        for line in t.wrap(f_text, cur.description or "", w, max(0, (box.bottom - y) // lh)):
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

        # Channel column: logo over number + name; lit on the cursor row.
        pygame.draw.rect(c, p["GUIDE_SELECTED"] if selected else p["GUIDE_TIME_BG"], (pad, y, cw, rh))
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
        t.draw(c, num, f_ch, p["SEL_TEXT"] if selected else p["YELLOW"] if current else p["WHITE"], x0, ty)
        if name:
            t.draw(c, name, f_small, p["SEL_TEXT"] if selected else p["CYAN"] if current else p["WHITE_DIM"], x0 + nw + 8,
                   ty + (t.ink(f_ch)[1] - t.ink(f_small)[1]) // 2)

        # Programme cells.
        pygame.draw.rect(c, bg, (grid_x, y, grid_w, rh))
        pygame.draw.line(c, p["GUIDE_BORDER"], (pad, y + rh - 1), (grid_x + grid_w, y + rh - 1))
        progs = epg.programs_in_window(cid, start, end) if cid else []
        if not progs:           # no listings: the channel's own name, readable on the cursor too
            t.draw(c, t.fit(f_prog, ch.name, grid_w - 16), f_prog, p["SEL_TEXT_DIM"] if selected else p["INK_MUTED"],
                   grid_x + 8, y + (rh - t.ink(f_prog)[1]) // 2)
            return
        mins = guide.hours * 60
        sel = guide.sel_time()
        for prog in progs:
            a = max(0.0, (prog.start - start).total_seconds() / 60)
            b = min(float(mins), (prog.stop - start).total_seconds() / 60)
            if b <= a:
                continue
            px = grid_x + int(a / mins * grid_w)
            pw = int((b - a) / mins * grid_w)
            on_air = prog.start <= now < prog.stop
            ink = (p["SEL_TEXT"] if on_air else p["SEL_TEXT_DIM"]) if selected else \
                p["WHITE"] if on_air else p["WHITE_DIM"]
            pygame.draw.rect(c, bg, (px + 1, y + 2, pw - 2, rh - 4))
            pygame.draw.line(c, p["GUIDE_BORDER"], (px, y), (px, y + rh))
            if selected and prog.start <= sel < prog.stop:        # the chosen cell on the chosen row
                pygame.draw.rect(c, p["YELLOW"], (px + 2, y + 3, pw - 4, rh - 6), 2)
            if on_air:
                pygame.draw.rect(c, p["SEL_TEXT"] if selected else p["CYAN"], (px + 1, y + 2, 4, rh - 4))
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
        f = self.role("title")
        lines = self.text.wrap(f, msg, int(W * 0.7), 4)
        y = H // 2 - len(lines) * 22
        for line in lines:
            self.text.draw(c, line, f, p["WHITE"], W // 2, y, align="center")
            y += 44
