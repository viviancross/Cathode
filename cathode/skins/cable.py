"""The cable boxes: four skins after the guides the big US cable companies
leased out in the 2000s and 2010s, drawn from one parametric page. Each
names its colours, its picture's side, its menu's shape and its own words
(the dead-channel card, the boot screens); the drawing is shared.

- Calmcast i-Grid (2006): the navy grid of the Motorola-era interactive
  guide: a yellow cursor, grey-blue channel tiles, the picture top-right,
  the programme described beside it, a Main Menu list with the picture.
- Passage (2004): the charcoal guide of the Scientific Atlanta-era boxes:
  slate cells, gold cursor, the picture top-left, the description at the
  right.
- Wayfinder HD (2009): the light guide of the later Time Warner boxes: a
  white grid on a silver page, a blue cursor, a graphite title bar.
- Y1 (2014): the black guide of the current Comcast box: charcoal cells, a
  white cursor, a light face, a horizontal Main Menu over the dimmed
  picture.

Geometry is written in 1280x720 pixels (all four draw 16:9: the HD boxes
of each line did); X() and Y() scale it to the canvas."""

import time
from datetime import datetime, timedelta, timezone

import pygame

from .box import BoxSkin, mix, nice, readable, rgba, vgrad


def ampm(dt) -> str:
    """'7:00pm', the cable guides' clock."""
    return dt.astimezone().strftime("%I:%M%p").lstrip("0").lower()


def span(cur) -> str:
    return f"{ampm(cur.start)} - {ampm(cur.stop)}"


class CableSkin(BoxSkin):
    """The shared cable page. Subclasses set NATIVE, roles(), PIP, MENU,
    the words, and the mark."""
    canvas = (1280, 720)
    SD = False
    guide_hours = 1.5               # three half-hour columns, as the cable guides showed
    tune_black = 1.0
    TALL = ("guide", "screensaver", "ondemand")
    default_font = "sans"
    PIP = "right"                   # the guide's picture: right | left
    MENU = "list"                   # the Main Menu: list (beside the picture) | bar (across the top)
    MARK = "cable"                  # the wordmark
    MARK_TAG = ""                   # a small word under or beside it
    LIST_WORD = "All Channels"      # what the guide calls the full lineup
    INFO_WORD = "for details"       # the banner's hint after the INFO key's name
    # The dead-channel card: (title, line, line).
    NO_SIGNAL = ("One moment please", "This channel should be available shortly.", "Ref code: S0a00")
    # The boot: the mark, then a loading card with these words.
    boot_scenes = [("logo", 1.6), ("loading", 1.0)]
    BOOT_WORDS = ("Starting up...", "Loading guide data...")
    ATTENTION = "Attention"

    @property
    def guide_rows(self):
        return 6 + self.grow // self.Y(54)

    LEGIBLE = [("text", ["page", "page2", "cell", "cell2", "now", "chan", "panel", "row", "btn", "field"], "ground"),
               ("sel_ink", ["sel"], "ink"), ("soft", ["page", "cell", "panel"], "ink"),
               ("muted", ["page", "panel"], "ink"), ("hdr_ink", ["hdr"], "ink"), ("band_ink", ["band"], "ink"),
               ("chan_ink", ["chan"], "ink"), ("ink", ["paper"], "ink")]

    def theme_base(self, base):
        bg, acc, text = base["bg"], base["accent"], base["text"]
        # A Cathode theme's cells as a lift of its page, its header darker;
        # the cursor is its own highlight.
        return dict(base, accent=mix(bg, acc, 0.35), chnum=mix(bg, (0, 0, 0), 0.3))

    def roles(self, b):
        page, cell, sel, text, hdr = b["bg"], b["accent"], b["accent2"], b["text"], b["chnum"]
        dark = 0.299 * page[0] + 0.587 * page[1] + 0.114 * page[2] < 128
        lift = (255, 255, 255) if dark else (0, 0, 0)
        return {
            "page": page, "page2": mix(page, (0, 0, 0) if dark else (255, 255, 255), 0.3),
            "cell": cell, "cell2": mix(cell, page, 0.35), "now": mix(cell, lift, 0.14),
            "edge": mix(cell, (0, 0, 0) if dark else (160, 160, 170), 0.4),
            "chan": mix(page, lift, 0.14), "chan_ink": text,
            "hdr": hdr, "hdr_ink": readable(hdr, text),
            "sel": sel, "sel_ink": readable(sel, (12, 12, 18)),
            "text": text, "soft": mix(text, page, 0.28), "muted": mix(text, page, 0.5),
            "accent": sel, "rule": mix(page, lift, 0.25),
            "band": mix(page, (0, 0, 0), 0.5) if dark else (34, 38, 46), "band_ink": (240, 240, 244),
            "panel": mix(page, lift, 0.08), "panel_edge": mix(page, lift, 0.3),
            "row": cell, "row_ink": text, "btn": mix(cell, lift, 0.1), "btn_ink": text,
            "field": mix(page, (0, 0, 0) if dark else (255, 255, 255), 0.45),
            "paper": mix(page, lift, 0.08), "ink": text,
            "pip_edge": mix(page, lift, 0.4), "mark": text, "mark2": sel,
            "bar_track": mix(page, lift, 0.25), "bar_fill": sel,
        }

    # ── Geometry ──────────────────────────────────────────────────────────

    def X(self, v) -> int:
        return int(round(v * self.canvas[0] / 1280))

    def Y(self, v) -> int:
        return int(round(v * type(self).canvas[1] / 720))     # design rows: a grown canvas adds rows, not size

    def R(self, x, y, w, h) -> pygame.Rect:
        return pygame.Rect(self.X(x), self.Y(y), self.X(w), self.Y(h))

    def u(self, v) -> int:
        return self.Y(v)

    def tx(self, c, s, f, ink, x, y, align="left") -> int:
        return self.text.draw(c, s, f, ink[:3], x, y, align=align) if s else 0

    def mid(self, r, f) -> int:
        """The y that centres a line of f in r."""
        return r.y + (r.h - self.text.ink(f)[1]) // 2

    # ── The mark: a word in the box's face, a coloured tile beside it ─────

    def wordmark(self, c, x, y, size, ink=None, tile=None):
        b, t = self.b, self.text
        ink, tile = ink or b["mark"], tile or b["mark2"]
        f = self.fb(size)
        h = t.ink(f)[1]
        tw = int(size * 0.9)
        pygame.draw.rect(c, tile, (x, y, tw, h), border_radius=max(2, size // 8))
        ft = self.fb(max(8, int(size * 0.62)))
        t.draw(c, self.MARK[:1].upper(), ft, readable(tile, ink), x + tw // 2, y + (h - t.ink(ft)[1]) // 2,
               align="center")
        w = t.draw(c, self.MARK, f, ink, x + tw + size // 4, y)
        if self.MARK_TAG:
            fs = self.f(max(8, size // 3))
            t.draw(c, self.MARK_TAG, fs, ink, x + tw + size // 4 + w, y + h + size // 12, align="right")
        return tw + size // 4 + w

    # ── Pages ─────────────────────────────────────────────────────────────

    def _page(self, c, rect):
        """The page: its colour, a touch lighter at the top."""
        if self.hold_backdrop(rect, self._page):
            return
        b = self.b
        rect = pygame.Rect(rect)
        vgrad(c, rect, rgba(b["page"]), rgba(b["page2"]))

    def guide_video_box(self):
        r = self.R(780 if self.PIP == "right" else 20, 16, 480, 270)
        return (r.x, r.y, r.w, r.h)

    def _picture(self, c):
        vx, vy, vw, vh = self.guide_video_box()
        self.hole(c, (vx, vy, vw, vh))
        pygame.draw.rect(c, rgba(self.b["pip_edge"]), (vx - 3, vy - 3, vw + 6, vh + 6), 3)
        return pygame.Rect(vx, vy, vw, vh)

    def _topbar(self, c, title, clock=True):
        """The title bar every full page shares: the mark, the title, the
        clock at the right. Returns its rect."""
        W = self.canvas[0]
        b, t, X, Y = self.b, self.text, self.X, self.Y
        bar = self.R(0, 0, 1280, 88)
        pygame.draw.rect(c, b["hdr"], bar)
        pygame.draw.rect(c, b["accent"], (0, bar.bottom - Y(3), W, Y(3)))
        w = self.wordmark(c, X(48), Y(26), Y(30), b["hdr_ink"])
        f = self.fb(Y(32))
        self.tx(c, t.fit(f, title, X(700)), f, b["hdr_ink"], X(48) + w + X(40), Y(26))
        if clock:
            local = datetime.now()
            self.tx(c, f"{local:%a} {local.month}/{local.day}  {ampm(local)}", self.f(Y(24)), b["hdr_ink"], X(1232), Y(30),
                    align="right")
        return bar

    # ── Live: the lower-third banner, digits, volume, trick ───────────────

    def _band(self, c, r, alpha=225, radius=None):
        band = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(band, (*self.b["band"], alpha), band.get_rect(), border_radius=self.Y(6) if radius is None else radius)
        c.blit(band, r.topleft)

    def _banner(self, c, ch, cur, nxt, full=False, tag=None, bottom=True):
        """The lower third: the number and call sign in a tile at the left,
        the title over its hours and rating, the clock at the right, a
        progress line along the foot. INFO's full banner adds the synopsis
        above it; BROWSE puts its tag over it."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = self.R(40, 0, 1200, 118)
        r.bottom = H - Y(44)
        self._band(c, r)
        ink = b["band_ink"]
        # The channel tile.
        tile = pygame.Rect(r.x, r.y, X(190), r.h)
        pygame.draw.rect(c, b["sel"], tile, border_top_left_radius=Y(6), border_bottom_left_radius=Y(6))
        fn, fc = self.fb(Y(44)), self.fb(Y(20))
        self.tx(c, str(ch.number), fn, b["sel_ink"], tile.centerx, tile.y + Y(14), align="center")
        call = "".join(ch.name.upper().split())[:6]
        self.tx(c, t.fit(fc, call, tile.w - X(16)), fc, b["sel_ink"], tile.centerx, tile.y + Y(74), align="center")
        logo = self.channel_logo(ch, X(120), Y(56))
        lx = tile.right + X(20)
        if logo:
            c.blit(logo, logo.get_rect(midleft=(lx, r.y + Y(36))))
            lx += X(136)
        f_title, f_line = self.fb(Y(32)), self.f(Y(22))
        right = r.right - X(220)
        self.tx(c, t.fit(f_title, cur.title if cur else ch.name, right - lx), f_title, ink, lx, r.y + Y(16))
        if cur:
            line = "   ".join(s for s in (span(cur), cur.rating, cur.category) if s)
            self.tx(c, t.fit(f_line, line, right - lx), f_line, ink, lx, r.y + Y(62))
        else:
            self.tx(c, "No information", f_line, ink, lx, r.y + Y(62))
        local = datetime.now()
        self.tx(c, ampm(local), self.fb(Y(26)), ink, r.right - X(24), r.y + Y(16), align="right")
        hint = tag or (f"{self.k('INFO')} {self.INFO_WORD}" if not full else "")
        if hint:
            self.tx(c, hint, self.f(Y(20)), mix(ink, b["band"], 0.3) if not tag else ink, r.right - X(24), r.y + Y(66), align="right")
        # The progress line along the foot.
        line = pygame.Rect(tile.right, r.bottom - Y(6), r.w - tile.w, Y(6))
        pygame.draw.rect(c, b["bar_track"], line, border_bottom_right_radius=Y(6))
        if cur:
            now = datetime.now(timezone.utc)
            frac = max(0.0, min(1.0, (now - cur.start).total_seconds() / max(1, (cur.stop - cur.start).total_seconds())))
            pygame.draw.rect(c, b["accent"], (line.x, line.y, int(line.w * frac), line.h))
        if full and cur and (cur.description or nxt):
            f = self.f(Y(21))
            lines = t.wrap(f, cur.description or "", r.w - X(48), 3) + ([f"Next: {nxt.title}  {ampm(nxt.start)}"] if nxt else [])
            d = pygame.Rect(r.x, 0, r.w, Y(20) + len(lines) * Y(28))
            d.bottom = r.y - Y(6)
            self._band(c, d)
            y = d.y + Y(10)
            for k, ln in enumerate(lines):
                self.tx(c, ln, f, b["soft"] if nxt and k == len(lines) - 1 else ink, d.x + X(24), y)
                y += Y(28)
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def draw_browse(self, c, br):
        if br.channel:
            cur, nxt = br.program()
            tag = f"Browse: {self.k('SELECT')} to watch" + (f"  (+{br.ahead})" if br.ahead else "")
            self._banner(c, br.channel, cur, nxt, tag=tag)

    def _digits(self, c, digits):
        b, X, Y = self.b, self.X, self.Y
        r = self.R(40, 40, 220, 80)
        self._band(c, r)
        f = self.fb(Y(48))
        self.tx(c, digits + "-" * (3 - len(digits)), f, b["band_ink"], r.centerx, self.mid(r, f), align="center")

    def _volume(self, c, cx, cy):
        b, X, Y = self.b, self.X, self.Y
        v = self.app.video
        r = self.R(40, 40, 480, 56)
        self._band(c, r)
        f = self.fb(Y(22))
        self.tx(c, "Mute" if v.muted else "Volume", f, b["accent"] if v.muted else b["band_ink"], r.x + X(20), self.mid(r, f))
        bar = pygame.Rect(r.x + X(150), r.y + Y(20), X(310), Y(16))
        pygame.draw.rect(c, b["bar_track"], bar, border_radius=Y(8))
        if not v.muted:
            pygame.draw.rect(c, b["accent"], (bar.x, bar.y, max(Y(16), int(bar.w * v.volume / 100)), bar.h), border_radius=Y(8))

    def _button(self, c, r, label, on, f=None):
        """A flat button: the cursor colour when chosen."""
        b, Y = self.b, self.Y
        fill, ink = (b["sel"], b["sel_ink"]) if on else (b["btn"], b["btn_ink"])
        pygame.draw.rect(c, fill, r, border_radius=Y(5))
        if not on:
            pygame.draw.rect(c, b["panel_edge"], r, 1, border_radius=Y(5))
        f = f or self.fb(Y(22))
        if label:
            self.tx(c, self.text.fit(f, label, r.w - Y(16)), f, ink, r.centerx, self.mid(r, f), align="center")

    def _tbtn(self, c, r, kind, on, num=None):
        b = self.b
        self._button(c, r, "", on)
        self.transport_face(c, kind, r, b["sel_ink"] if on else b["btn_ink"], self.fb(self.Y(20)), num=num)

    def _trick(self, c, s):
        b, X, Y = self.b, self.X, self.Y
        r = self.R(40, 620, 1200, 56)
        self.live_buttons(c, s, r.x + X(10), r.y - Y(58), X(150), Y(42), X(20))
        self._band(c, r)
        behind = s["behind"]
        mm, ss = divmod(int(behind), 60)
        f = self.fb(Y(22))
        tag = "Paused" if s["paused"] else ("Live" if behind < 2 else "Playing")
        self.tx(c, tag, f, b["band_ink"], r.x + X(20), self.mid(r, f))
        bar = pygame.Rect(r.x + X(200), r.y + Y(22), X(800), Y(12))
        pygame.draw.rect(c, b["bar_track"], bar, border_radius=Y(6))
        total = s["buffer"] + behind
        if total >= 2:
            x = bar.x + int(bar.w * s["buffer"] / total)
            pygame.draw.rect(c, b["accent"], (bar.x, bar.y, x - bar.x, bar.h), border_radius=Y(6))
            pygame.draw.rect(c, b["band_ink"], (x - X(2), bar.y - Y(5), X(4), bar.h + Y(10)))
        self.tx(c, f"-{mm}:{ss:02d}" if behind >= 1 else "Live", f, b["band_ink"], r.right - X(20), self.mid(r, f), align="right")

    def _note(self, c, text, frac=None):
        """A short notice in a band, bottom left, above the banner's place."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        bar = frac is not None and frac >= 0
        f = self.fb(Y(24))
        r = pygame.Rect(X(40), 0, max(t.width(f, text) + X(48), X(520) if bar else 0), Y(76 if bar else 54))
        r.bottom = Y(540)
        self._band(c, r)
        self.tx(c, text, f, b["band_ink"], r.x + X(24), r.y + Y(14))
        if bar:
            self.progress(c, pygame.Rect(r.x + X(24), r.bottom - Y(22), r.w - X(48), Y(10)), frac, b["bar_track"], b["accent"])

    def draw_note(self, c, text):
        self._note(c, text)

    def draw_guide_progress(self, c, frac):
        self._note(c, "Loading guide data" + self.pct(frac), frac)

    # ── Dialogs ───────────────────────────────────────────────────────────

    def _dialog(self, c, title, lines, buttons=(), focus=0, wide=700):
        """A flat card: a header bar in the header colour, the lines, flat
        buttons along the foot. Returns the card's rect."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        f = self.f(Y(23))
        wrapped = [w for line in lines for w in t.wrap(f, line, X(wide - 80), 3)]
        r = pygame.Rect(0, 0, X(wide), Y(60) + Y(24) + len(wrapped) * Y(32) + (Y(72) if buttons else Y(12)))
        r.center = (W // 2, H // 2)
        pygame.draw.rect(c, b["panel"], r, border_radius=Y(8))
        pygame.draw.rect(c, b["panel_edge"], r, 2, border_radius=Y(8))
        head = pygame.Rect(r.x, r.y, r.w, Y(52))
        pygame.draw.rect(c, b["hdr"], head, border_top_left_radius=Y(8), border_top_right_radius=Y(8))
        pygame.draw.rect(c, b["accent"], (head.x, head.bottom - Y(3), head.w, Y(3)))
        fh = self.fb(Y(26))
        self.tx(c, t.fit(fh, title, r.w - X(40)), fh, b["hdr_ink"], head.x + X(20), self.mid(head, fh))
        y = head.bottom + Y(20)
        for line in wrapped:
            self.tx(c, line, f, b["ink"], r.x + X(24), y)
            y += Y(32)
        if buttons:
            bw = X(180)
            x0 = r.right - X(24) - len(buttons) * bw - (len(buttons) - 1) * X(16)
            for k, label in enumerate(buttons):
                self._button(c, pygame.Rect(x0 + k * (bw + X(16)), r.bottom - Y(60), bw, Y(40)), label, k == focus)
        return r

    def _signal_loss(self, c):
        """The box's dead-channel card on black."""
        c.fill((0, 0, 0, 255))
        title, l1, l2 = self.NO_SIGNAL
        self._dialog(c, title, [l1, l2])

    def _message(self, c, msg):
        c.fill((0, 0, 0, 255))
        self._dialog(c, self.ATTENTION, [msg])

    def draw_capture(self, c, cap):
        self._dialog(c, "Remote Setup", [cap.prompt, "Waiting..."])

    def draw_program_info(self, c, info):
        self._dialog(c, info.title, info.lines())

    def draw_toast(self, c, msg):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        f = self.fb(Y(23))
        lines = t.wrap(f, msg, X(1040), 3)
        lh = Y(30)
        w = max(t.width(f, ln) for ln in lines) + X(56)
        r = pygame.Rect((self.canvas[0] - w) // 2, Y(120) if self.over_picture() else Y(300), w, Y(18) + lh * len(lines))
        self._band(c, r, 240)
        pygame.draw.rect(c, b["accent"], (r.x, r.y, Y(5), r.h), border_top_left_radius=Y(6), border_bottom_left_radius=Y(6))
        for k, ln in enumerate(lines):
            self.tx(c, ln, f, b["band_ink"], r.centerx + Y(3), r.y + Y(10) + k * lh, align="center")

    def draw_options(self, c, m):
        """Live TV's Options as the card: the choices as flat rows."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        r = pygame.Rect(0, 0, X(620), Y(76) + len(m.items) * Y(50))
        r.center = (W // 2, H // 2)
        pygame.draw.rect(c, b["panel"], r, border_radius=Y(8))
        pygame.draw.rect(c, b["panel_edge"], r, 2, border_radius=Y(8))
        head = pygame.Rect(r.x, r.y, r.w, Y(52))
        pygame.draw.rect(c, b["hdr"], head, border_top_left_radius=Y(8), border_top_right_radius=Y(8))
        pygame.draw.rect(c, b["accent"], (head.x, head.bottom - Y(3), head.w, Y(3)))
        fh = self.fb(Y(26))
        self.tx(c, m.title, fh, b["hdr_ink"], head.x + X(20), self.mid(head, fh))
        f = self.f(Y(23))
        for k, it in enumerate(m.items):
            row = pygame.Rect(r.x + X(16), head.bottom + Y(12) + k * Y(50), r.w - X(32), Y(42))
            on = k == m.cursor
            if on:
                pygame.draw.rect(c, b["sel"], row, border_radius=Y(5))
            ink = b["sel_ink"] if on else b["ink"]
            lw = self.tx(c, t.fit(f, it.label, row.w - X(200)), f, ink, row.x + X(16), self.mid(row, f))
            if it.value:
                v = it.value()
                v = f"< {v} >" if on and it.adjust else v
                self.tx(c, t.fit(f, v, row.w - lw - X(48)), f, ink, row.right - X(16), self.mid(row, f), align="right")
            self.hit(row, lambda k=k: m.activate(k))

    # ── Guide ─────────────────────────────────────────────────────────────

    def _info_block(self, c, g, pic):
        """The chosen programme beside the picture: the mark, title, hours
        and rating, synopsis; the list name and clock on the last line."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        left = pic.right + X(24) if self.PIP == "left" else X(48)
        right = pic.x - X(24) if self.PIP == "right" else X(1232)
        wide = right - left
        self.wordmark(c, left, Y(22), Y(30))
        sel, cur = g.selected(), g.selected_program()
        f_title, f_line, f_desc = self.fb(Y(34)), self.f(Y(22)), self.f(Y(22))
        title = cur.title if cur else (f"{sel.number} {sel.name}" if sel else "")
        art = self.logo(cur.icon, X(100), Y(150)) if cur and cur.icon else None
        tx = left
        if art:
            c.blit(art, (left, Y(74)))
            tx = left + X(116)
        self.tx(c, t.fit(f_title, title, right - tx), f_title, b["text"], tx, Y(74))
        if cur:
            line = "   ".join(s for s in (span(cur), cur.rating, cur.category) if s)
            self.tx(c, t.fit(f_line, line, right - tx), f_line, b["soft"], tx, Y(120))
            y = Y(154)
            for ln in t.wrap(f_desc, cur.description or "", right - tx, 3):
                self.tx(c, ln, f_desc, b["text"], tx, y)
                y += Y(28)
        elif sel:
            self.tx(c, "No information available.", f_line, b["soft"], tx, Y(120))
        f_list = self.fb(Y(24))
        name = g.category if g.category != "All" else self.LIST_WORD
        if g.focus == "category":
            name = f"<  {name}  >"
        tab = pygame.Rect(left, Y(256), t.width(f_list, name) + X(24), Y(36))
        if g.focus == "category":
            pygame.draw.rect(c, b["sel"], tab, border_radius=Y(5))
        self.tx(c, name, f_list, b["sel_ink"] if g.focus == "category" else b["text"], tab.x + X(12), self.mid(tab, f_list))
        self.hit(tab, lambda: g.handle("THEMES"))
        local = datetime.now()
        self.tx(c, f"{local:%a} {local:%b} {local.day}   {ampm(local)}", f_list, b["text"], right, self.mid(tab, f_list), align="right")

    def draw_guide(self, c, g):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._page(c, (0, 0, W, H))
        pic = self._picture(c)
        self._info_block(c, g, pic)
        # The time header.
        hdr = self.R(0, 304, 1280, 32)
        pygame.draw.rect(c, b["hdr"], hdr)
        start, end = g.window()
        fh = self.fb(Y(22))
        hy = self.mid(hdr, fh)
        day = start.astimezone()
        self.tx(c, f"{day:%a} {day.month}/{day.day}", fh, b["hdr_ink"], X(24), hy)
        slots = int(g.hours * 4)
        grid_x, grid_w = X(254), X(1016)
        col = grid_w / slots
        labels = [ampm(start + timedelta(minutes=15 * i)) for i in range(slots)]
        every = self.label_every(col, max(t.width(fh, s) for s in labels))
        for i in range(slots):
            x = grid_x + col * i
            if i % every == 0:
                pygame.draw.rect(c, mix(b["hdr"], b["hdr_ink"], 0.3), (int(x), hdr.y + Y(6), 2, hdr.h - Y(12)))
                self.tx(c, labels[i], fh, b["hdr_ink"], int(x) + X(10), hy)
        rows = g.filtered()[g.top: g.top + g.rows]
        mins = g.hours * 60
        now = datetime.now(timezone.utc)
        epg = self.app.epg
        f_cell, f_num, f_call = self.f(Y(24)), self.fb(Y(24)), self.f(Y(17))
        sel = g.sel_time()
        pitch, rh = Y(54), Y(50)
        top = Y(340)
        for i, ch in enumerate(rows):
            y = top + pitch * i
            row_sel = g.focus == "grid" and g.top + i == g.cursor
            tile = pygame.Rect(0, y, X(250), rh)
            pygame.draw.rect(c, b["chan"], tile)
            logo = self.channel_logo(ch, X(90), Y(40))
            self.tx(c, str(ch.number), f_num, b["chan_ink"], X(74), y + Y(4), align="right")
            if logo:
                c.blit(logo, logo.get_rect(midleft=(X(150), tile.centery)))
                self.tx(c, t.fit(f_call, ch.name.upper(), X(64)), f_call, b["chan_ink"], X(74), y + Y(30), align="right")
            else:
                self.tx(c, t.fit(f_call, ch.name.upper(), X(150)), f_call, b["chan_ink"], X(88), y + Y(30))
            if self.app.is_favorite(ch):
                pygame.draw.circle(c, b["accent"], (tile.right - X(12), y + Y(10)), Y(4))
            cid = epg.resolve_channel_id(ch.epg_id, ch.name) if epg else None
            progs = epg.programs_in_window(cid, start, end) if cid else []
            if not progs:
                cell = pygame.Rect(grid_x, y, grid_w - X(10), rh)
                self._cell(c, cell, False, row_sel, i)
                self.tx(c, "No information", f_cell, b["sel_ink"] if row_sel else b["soft"], cell.x + X(12), self.mid(cell, f_cell))
            for p in progs:
                a = max(0.0, (p.start - start).total_seconds() / 60)
                e = min(float(mins), (p.stop - start).total_seconds() / 60)
                if e <= a:
                    continue
                cell = pygame.Rect(grid_x + int(a / mins * grid_w), y, int((e - a) / mins * grid_w) - X(4), rh)
                on = row_sel and p.start <= sel < p.stop
                self._cell(c, cell, p.start <= now < p.stop, on, i)
                ink = b["sel_ink"] if on else b["text"]
                l, r = cell.x + X(8), min(cell.right, X(1264)) - X(8)
                if p.start < start:
                    pygame.draw.polygon(c, ink, [(cell.x + X(6), cell.centery), (cell.x + X(14), cell.centery - Y(8)),
                                                 (cell.x + X(14), cell.centery + Y(8))])
                    l += X(12)
                if p.stop > end:
                    pygame.draw.polygon(c, ink, [(cell.right - X(6), cell.centery), (cell.right - X(14), cell.centery - Y(8)),
                                                 (cell.right - X(14), cell.centery + Y(8))])
                    r -= X(12)
                f, lines = self.cell_text(p.title, r - l, rh - Y(6), lambda s: self.f(Y(s)), 24)
                lh = t.ink(f)[1]
                ty = y + (rh - len(lines) * lh - (len(lines) - 1) * 2) // 2
                for line in lines:
                    self.tx(c, line, f, ink, l, ty)
                    ty += lh + 2
            self.hit((0, y, W, rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                setattr(g, "focus", "grid"), g.handle("SELECT")))
        off = (now - start).total_seconds() / 60
        if 0 <= off <= mins and rows:
            x = grid_x + int(off / mins * grid_w)
            pygame.draw.rect(c, b["accent"], (x - 1, hdr.bottom, 2, top + len(rows) * pitch - Y(4) - hdr.bottom))
        if not rows:
            cell = pygame.Rect(0, top, W, rh)
            self._cell(c, cell, False, False, 0)
            self.tx(c, t.fit(f_cell, self.empty_guide(g), cell.w - X(40)), f_cell, b["text"], cell.centerx,
                    self.mid(cell, f_cell), align="center")
        foot = top + g.rows * pitch
        fk = self.f(Y(19))
        if H - foot >= t.ink(fk)[1] + Y(6):
            self.tx(c, self.guide_keys(), fk, b["muted"], W // 2, foot + (H - foot - t.ink(fk)[1]) // 2, align="center")

    def _cell(self, c, cell, airing, on, row_i):
        b, Y = self.b, self.Y
        if on:
            pygame.draw.rect(c, b["sel"], cell)
        else:
            pygame.draw.rect(c, b["now"] if airing else (b["cell"] if row_i % 2 == 0 else b["cell2"]), cell)
            pygame.draw.rect(c, b["edge"], cell, 1)

    def guide_keys(self) -> str:
        def k(action, plain):
            name = self.k(action)
            return plain if name == action else name
        return (f"{k('CH_UP', 'CH+')}/{k('CH_DOWN', 'CH-')}: page   {k('REW', 'REW')}/{k('FF', 'FF')}: a day   "
                f"{k('THEMES', 'THEMES')}: other lists   {k('INFO', 'INFO')}: details")

    # ── Menus ─────────────────────────────────────────────────────────────

    def _is_bar(self, m) -> bool:
        return self.MENU == "bar" and m.title == "MAIN MENU" and len(getattr(m, "pages", [1])) == 1

    def menu_cols(self, menu):
        return max(1, len(menu.items)) if self._is_bar(menu) else 1

    def menu_rows(self, menu):
        return 1 if self._is_bar(menu) else super().menu_rows(menu)

    def menu_video_box(self, menu):
        if self._is_bar(menu):
            return "full"
        r = self.R(732, 128, 480, 270)
        return (r.x, r.y, r.w, r.h)

    def draw_menu(self, c, m):
        if self._is_bar(m):
            self._bar_menu(c, m)
            return
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._page(c, (0, 0, W, H))
        self._topbar(c, "Main Menu" if m.title == "MAIN MENU" else m.title.title())
        vx, vy, vw, vh = self.menu_video_box(m)
        self.hole(c, (vx, vy, vw, vh))
        pygame.draw.rect(c, b["pip_edge"], (vx - 3, vy - 3, vw + 6, vh + 6), 3)
        live = self.app.live
        if live.channel:
            fc = self.f(Y(22))
            on = live.programs()[0]
            self.tx(c, t.fit(fc, f"{live.channel.number} {live.channel.name.upper()}" + (f"   {on.title}" if on else ""), vw),
                    fc, b["text"], vx, vy + vh + Y(14))
        it = m.items[m.cursor] if 0 <= m.cursor < len(m.items) else None
        if it and it.help:
            fa = self.f(Y(22))
            for k, line in enumerate(t.wrap(fa, it.help, vw, 3)):
                self.tx(c, line, fa, b["soft"], vx, vy + vh + Y(54) + k * Y(28))
        n = len(m.items)
        rh = Y(50)
        lp = self.R(48, 120, 640, 560)
        n_vis = max(1, (lp.h - Y(40)) // rh)
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        f_row = self.f(Y(25))
        for k, i in enumerate(range(first, min(n, first + n_vis))):
            it = m.items[i]
            row = pygame.Rect(lp.x, lp.y + k * rh, lp.w, rh - Y(4))
            on = i == m.cursor
            if on:
                pygame.draw.rect(c, b["sel"], row, border_radius=Y(5))
            else:
                pygame.draw.rect(c, b["rule"], (row.x, row.bottom + Y(1), row.w, 1))
            ink = b["sel_ink"] if on else b["text"]
            if not it.enabled:
                ink = mix(ink, b["sel"] if on else b["page"], 0.5)
            ty = self.mid(row, f_row)
            lw = self.tx(c, t.fit(f_row, it.label, row.w - (X(220) if it.value else X(60))), f_row, ink, row.x + X(18), ty)
            if it.value:
                v = it.value()
                v = f"< {v} >" if on and it.adjust else v
                self.tx(c, t.fit(f_row, v, row.w - lw - X(56)), f_row, ink, row.right - X(18), ty, align="right")
            elif it.submenu:
                self.tx(c, ">", f_row, ink, row.right - X(18), ty, align="right")
            self.hit(row, lambda i=i: m.activate(i))
        ff = self.f(Y(20))
        if n > n_vis:
            self.tx(c, f"{first + 1}-{min(n, first + n_vis)} of {n}", ff, b["muted"], lp.right, Y(688), align="right")
        self.tx(c, f"{self.k('SELECT')}: choose   {self.k('BACK')}: back   {self.k('EXIT')}: close", ff, b["muted"], lp.x, Y(688))

    def _bar_menu(self, c, m):
        """The Main Menu as a row across the top of the dimmed picture: the
        chosen word lit, its help beneath."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self.dim(c, 150)
        band = self.R(0, 0, 1280, 190)
        vgrad(c, band, rgba(b["page"], 235), rgba(b["page"], 0))
        self.wordmark(c, X(48), Y(28), Y(30))
        f = self.fb(Y(26))
        n = len(m.items)
        x = X(48)
        y = Y(96)
        for i, it in enumerate(m.items):
            w = t.width(f, it.label) + X(28)
            if x + w > X(1240):
                break
            r = pygame.Rect(x, y, w, Y(44))
            on = i == m.cursor
            ink = b["text"] if on else b["soft"]
            self.tx(c, it.label, f, ink, r.centerx, self.mid(r, f), align="center")
            if on:
                pygame.draw.rect(c, b["accent"], (r.x + X(8), r.bottom, r.w - X(16), Y(4)))
            self.hit(r, lambda i=i: m.activate(i))
            x += w + X(8)
        it = m.items[m.cursor] if 0 <= m.cursor < n else None
        if it and it.help:
            fa = self.f(Y(22))
            self.tx(c, t.fit(fa, it.help, X(1180)), fa, b["text"], X(48), Y(156))

    # ── Pages: On Demand, recordings, info, keyboard, system ──────────────

    poster_wall = True
    keyboard_layer = "abc"
    WALL = (6, 2)

    def page_video_box(self, screen):
        r = self.R(800, 112, 432, 243)
        return (r.x, r.y, r.w, r.h)

    def ondemand_cols(self, screen):
        return self.WALL[0] if screen.view == "wall" else 1

    def ondemand_page(self, screen):
        Y = self.Y
        if screen.view == "wall":
            return self.WALL[0] * (self.WALL[1] + self.more(Y(46)) // Y(200))
        return 10 + self.grow // Y(46)

    def _full_page(self, c, title, picture=True):
        W, H = self.canvas
        self._page(c, (0, 0, W, H))
        self._topbar(c, title)
        if not picture:
            return None
        vx, vy, vw, vh = self.page_video_box(None)
        self.hole(c, (vx, vy, vw, vh))
        pygame.draw.rect(c, self.b["pip_edge"], (vx - 3, vy - 3, vw + 6, vh + 6), 3)
        live = self.app.live
        if live and live.channel:
            fc = self.f(self.Y(20))
            self.tx(c, self.text.fit(fc, f"{live.channel.number} {live.channel.name.upper()}", vw), fc, self.b["text"],
                    vx, vy + vh + self.Y(12))
        return pygame.Rect(vx, vy, vw, vh)

    def _side(self, c, labels, focus, x=800, y=400, w=432, h=42, pitch=54, hits=None):
        for k, label in enumerate(labels):
            r = self.R(x, y + k * pitch, w, h)
            self._button(c, r, label, k == focus)
            if hits and hits[k]:
                self.hit(r, hits[k])

    def _rows(self, c, s, panel, rows, sel, top, n_vis):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        f, fm = self.f(Y(24)), self.f(Y(20))
        rh = (panel.h - Y(16)) // n_vis
        for k, i in enumerate(range(top, min(len(rows), top + n_vis))):
            row = rows[i]
            r = pygame.Rect(panel.x + X(8), panel.y + Y(8) + k * rh, panel.w - X(16), rh - Y(3))
            on = i == sel
            if on:
                pygame.draw.rect(c, b["sel"], r, border_radius=Y(5))
            else:
                pygame.draw.rect(c, b["rule"], (r.x, r.bottom, r.w, 1))
            ink = b["sel_ink"] if on else b["text"]
            meta = row.get("meta", "")
            mw = t.width(fm, meta) + X(20) if meta else 0
            ty = self.mid(r, f)
            self.tx(c, t.fit(f, nice(row.get("title", "")), r.w - mw - X(30)), f, ink, r.x + X(14), ty)
            if meta:
                self.tx(c, meta, fm, ink if on else b["soft"], r.right - X(14), self.mid(r, fm), align="right")
            self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))
        if top + n_vis < len(rows):
            cx = panel.centerx
            pygame.draw.polygon(c, b["soft"], [(cx - X(12), panel.bottom + Y(6)), (cx + X(12), panel.bottom + Y(6)), (cx, panel.bottom + Y(18))])
        if top:
            cx = panel.centerx
            pygame.draw.polygon(c, b["soft"], [(cx - X(12), panel.y - Y(6)), (cx + X(12), panel.y - Y(6)), (cx, panel.y - Y(18))])

    def _wall(self, c, s, panel):
        b, X, Y = self.b, self.X, self.Y
        cols, tw, th, gap = self.WALL[0], X(100), Y(150), X(18)
        x0 = panel.x + (panel.w - (cols * tw + (cols - 1) * gap)) // 2
        for i, slot in self.wall_cells(s, cols, self.ondemand_page(s) // cols):
            row = s.rows[i]
            r = pygame.Rect(x0 + (slot % cols) * (tw + gap), panel.y + Y(16) + (slot // cols) * (th + Y(50)), tw, th)
            if i == s.sel:
                pygame.draw.rect(c, b["sel"], r.inflate(Y(10), Y(10)), border_radius=Y(5))
            pygame.draw.rect(c, b["field"], r)
            art = self.app.ondemand.poster(row.get("thumb", ""), r.w, r.h) if row.get("thumb") else None
            if art:
                c.blit(art, art.get_rect(center=r.center))
            fl = self.f(Y(17))
            self.tx(c, self.text.fit(fl, nice(row.get("title", "")), tw + gap - X(4)), fl,
                    b["text"] if i == s.sel else b["soft"], r.centerx, r.bottom + Y(10), align="center")
            self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))

    def draw_ondemand(self, c, s):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        rec = bool(s.level) and s.level.get("key") == "recordings"
        title = "My Recordings" if rec else "On Demand"
        self._full_page(c, title)
        fh = self.f(Y(22))
        head = "By date" if rec else (s.crumb() if len(s.stack) > 1 else "Movies, shows and more from your Plex server")
        self.tx(c, t.fit(fh, head, X(700)), fh, b["soft"], X(48), Y(108))
        panel = self.R(40, 144, 720, 540 + self.more(Y(46)))
        pygame.draw.rect(c, b["panel"], panel, border_radius=Y(6))
        if s.mode == "auth":
            y = panel.y + Y(80)
            for line, f in (("On a phone or computer, go to", self.f(Y(24))), (s.auth_link or "plex.tv/link", self.fb(Y(30))),
                            ("and enter this code:", self.f(Y(24)))):
                self.tx(c, line, f, b["text"], panel.centerx, y, align="center")
                y += t.ink(f)[1] + Y(20)
            if s.auth_code:
                self.tx(c, s.auth_code, self.fb(Y(72)), b["accent"], panel.centerx, y + Y(10), align="center")
            self._side(c, ["Cancel"], 0, hits=[s.back])
            return
        rows, n_vis = s.rows, self.ondemand_page(s)
        top = max(0, min(s.sel - n_vis // 2, len(rows) - n_vis))
        if s.view == "wall":
            self._wall(c, s, panel)
        else:
            self._rows(c, s, panel, rows, s.sel, top, n_vis)
        side = self.od_side(s)
        self._side(c, [lab for lab, _ in side], -1 if s.side is None else s.side, hits=[fn for _, fn in side])
        cur = s.current() or {}
        fa, fm = self.fb(Y(24)), self.f(Y(20))
        y = Y(590)
        for line in t.wrap(fa, nice(cur.get("title", "")), X(432), 2):
            self.tx(c, line, fa, b["text"], X(800), y)
            y += Y(30)
        if cur.get("meta"):
            self.tx(c, t.fit(fm, cur["meta"], X(432)), fm, b["soft"], X(800), y + Y(4))
        ff = self.f(Y(20))
        self.tx(c, f"{s.sel + 1} of {len(rows)}", ff, b["muted"], X(1232), Y(688), align="right")
        if s.status:
            self.tx(c, t.fit(ff, s.status, X(700)), ff, b["accent"], X(48), Y(688))

    def od_side(self, s):
        if s.mode != "browse":
            return []
        rec = bool(s.level) and s.level.get("key") == "recordings"
        return [("Options", lambda: s.handle("MENU")),
                ("Sort", lambda: s.handle("MENU")) if rec else ("My Recordings", lambda: s.handle("LIST")),
                ("Done", s.back)]

    def draw_iteminfo(self, c, info):
        from ..screens.iteminfo import hms
        b, t, X, Y = self.b, self.text, self.X, self.Y
        d = info.detail
        self._full_page(c, "Program Information", picture=False)
        art_r = self.R(48, 120, 200, 300)
        pygame.draw.rect(c, b["field"], art_r)
        pygame.draw.rect(c, b["pip_edge"], art_r, 2)
        art = self.logo(d.get("poster", ""), art_r.w, art_r.h, headers=d.get("poster_headers") or None)
        if art:
            c.blit(art, art.get_rect(center=art_r.center))
        x0 = art_r.right + X(32)
        f = self.fb(Y(34))
        y = Y(120)
        for line in t.wrap(f, d.get("title", ""), X(700), 2):
            self.tx(c, line, f, b["text"], x0, y)
            y += Y(42)
        fm = self.f(Y(22))
        meta = d.get("subtitle") or d.get("meta", "")
        facts = [s for s in (meta, f"Length: {hms(d['duration'])}" if d.get("duration") else "",
                             f"Resume at {hms(d['offset'])}" if (d.get("offset") or 0) > 5 else "") if s]
        self.tx(c, t.fit(fm, "   ".join(facts), X(700)), fm, b["soft"], x0, y + Y(4))
        y += Y(44)
        fd = self.f(Y(22))
        for line in t.wrap(fd, d.get("summary", "") or "No description available.", X(700), 8):
            self.tx(c, line, fd, b["text"], x0, y)
            y += Y(30)
        names = info.buttons()
        self._side(c, [self.button_words(info.label(n)) for n in names], info.focus, x=48, y=448, w=200, h=40, pitch=50,
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
        self._full_page(c, "Search" if kb.prompt.lower().startswith("search") else "Enter Text", picture=False)
        f = self.f(Y(24))
        self.tx(c, t.fit(f, kb.prompt, X(1000)), f, b["text"], X(140), Y(116))
        if kb.hint:
            self.tx(c, t.fit(self.f(Y(20)), kb.hint, X(1000)), self.f(Y(20)), b["soft"], X(140), Y(150))
        field = self.R(140, 186, 1000, 46)
        pygame.draw.rect(c, b["field"], field, border_radius=Y(5))
        pygame.draw.rect(c, b["accent"], (field.x, field.bottom - Y(3), field.w, Y(3)))
        ff = self.f(Y(28))
        shown = kb.value[:kb.caret]
        while shown and t.width(ff, shown) > field.w - X(40):
            shown = shown[1:]
        x = field.x + X(14) + self.tx(c, shown, ff, b["text"], field.x + X(14), self.mid(field, ff))
        pygame.draw.rect(c, b["accent"], (x + X(2), field.y + Y(8), X(3), field.h - Y(16)))
        grid = kb.grid()
        fk = self.f(Y(26))
        words = {"DEL": "Delete", "SPACE": "Space", "SHIFT": "a-z" if kb.layer == "ABC" else "A-Z",
                 "SYM": "ABC" if kb.layer == "sym" else "Symbols", "DONE": "Done", "CANCEL": "Cancel", "CLEAR": "Clear"}
        for r, row in enumerate(grid):
            last = r == len(grid) - 1
            for col, cell in enumerate(row):
                on = (r, col) == (kb.row, kb.col)
                if last:
                    rect = self.R(140 + col * 340, 614, 320, 44)
                    self._button(c, rect, words[cell], on)
                else:
                    if len(cell) == 1:
                        rect = self.R(140 + col * 102, 254 + r * 58, 94, 50)
                    else:
                        widths = {"DEL": 190, "SPACE": 480, "SHIFT": 150, "SYM": 150}
                        x0 = 140 + sum(widths[k] + 8 for k in row[:col])
                        rect = self.R(x0, 254 + r * 58, widths[cell], 50)
                    label = cell if len(cell) == 1 else words[cell]
                    self._button(c, rect, label, on, f=fk if len(cell) == 1 else self.f(Y(22)))
                self.hit(rect, lambda r=r, col=col, cell=cell: (setattr(kb, "row", r), setattr(kb, "col", col),
                                                                kb._press(cell)))
        self.tx(c, t.fit(self.f(Y(20)), kb.tip(), X(1000)), self.f(Y(20)), b["muted"], X(140), Y(676))

    def draw_diagnostics(self, c, d):
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._full_page(c, "System Information", picture=False)
        card = self.R(140, 116, 1000, 520)
        pygame.draw.rect(c, b["panel"], card, border_radius=Y(6))
        f = self.f(Y(24))
        y = card.y + Y(24)
        for label, value in [("Signal strength", f"{d.signal()}"), ("Signal quality", f"{d.quality()}")] + d.rows():
            self.tx(c, label, f, b["soft"], X(560), y, align="right")
            self.tx(c, t.fit(f, str(value), X(540)), f, b["text"], X(590), y)
            pygame.draw.rect(c, b["rule"], (card.x + X(20), y + Y(34), card.w - X(40), 1))
            y += Y(42)
        from ..menus import open_button_guide
        for k, (label, fn) in enumerate((("Help", lambda: open_button_guide(self.app)), ("Done", lambda: d.handle("BACK")))):
            r = self.R(720 + k * 220, 648, 200, 42)
            self._button(c, r, label, k == 1)
            self.hit(r, fn)

    def draw_playback(self, c, pb):
        from ..screens.iteminfo import hms
        b, t, X, Y = self.b, self.text, self.X, self.Y
        if pb.skip_label and self.on_top(pb):
            r = self.R(900, 440 if pb.bar_visible() else 600, 330, 48)
            self._button(c, r, f"{pb.skip_label.title()}  ({self.k('SELECT')})", True)
            self.hit(r, lambda: pb.handle("SELECT"))
        if not pb.bar_visible():
            return
        r = self.R(40, 520, 1200, 156)
        self._band(c, r)
        f = self.fb(Y(28))
        q = self.app.ondemand.queue
        title = pb.title + (f"  ({q.pos + 1} of {len(q.items)})" if q.items and q.pos >= 0 else "")
        tw = self.tx(c, t.fit(f, title, X(820)), f, b["band_ink"], r.x + X(24), r.y + Y(16))
        if pb.subtitle and X(820) - tw > X(120):
            fm = self.f(Y(22))
            self.tx(c, t.fit(fm, pb.subtitle, X(820) - tw - X(24)), fm, b["soft"], r.x + X(24) + tw + X(24),
                    r.y + Y(16) + (t.ink(f)[1] - t.ink(fm)[1]))
        mode = "Paused" if self.app.video.paused else "Playing"
        self.tx(c, mode, f, b["accent"], r.right - X(24), r.y + Y(16), align="right")
        line = pygame.Rect(r.x + X(130), r.y + Y(72), r.w - X(260), Y(10))
        pygame.draw.rect(c, b["bar_track"], line, border_radius=Y(5))
        frac = min(1.0, pb.pos / pb.dur) if pb.dur else 0.0
        pygame.draw.rect(c, b["accent"], (line.x, line.y, max(Y(10), int(line.w * frac)), line.h), border_radius=Y(5))
        fs = self.f(Y(22))
        self.tx(c, hms(pb.pos), fs, b["band_ink"], line.x - X(18), line.y - Y(7), align="right")
        self.tx(c, hms(pb.dur) if pb.dur else "--:--", fs, b["band_ink"], line.right + X(18), line.y - Y(7))
        self.hit(line.inflate(0, Y(24)), lambda: pb.seek_to(self._click_frac(line)))
        rects = []
        for k, (kind, _, fn) in enumerate(pb.transport()):
            br = self.R(130 + k * 170, 606, 150, 42)
            self._tbtn(c, br, kind, k == getattr(pb, "tfocus", None))
            self.hit(br, fn)
            rects.append(br)
        self.idle_row(c, pb, rects, Y(5))

    def draw_screensaver(self, c, ss):
        W, H = self.canvas
        c.fill((0, 0, 0, 255))
        size = self.Y(60)
        w = self.measure(self.wordmark, size)
        x, y = ss.position(w, int(size * 1.5), W, H)
        self.wordmark(c, x, y, size)

    # ── Boot ──────────────────────────────────────────────────────────────

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        scene, age = boot.scene(), boot.scene_age()
        self._page(c, (0, 0, W, H))
        size = Y(72)
        mw = self.measure(self.wordmark, size)
        self.wordmark(c, (W - mw) // 2, Y(250), size)
        f = self.f(Y(26))
        if scene == "logo":
            self.tx(c, self.BOOT_WORDS[0], f, b["soft"], W // 2, Y(380), align="center")
            return
        self.tx(c, self.BOOT_WORDS[1], f, b["text"], W // 2, Y(380), align="center")
        g = getattr(self.app, "guide_progress", None)
        bar = self.R(390, 430, 500, 12)
        if g is not None and g >= 0:
            self.progress(c, bar, max(g, min(1.0, age / 3.0)), b["bar_track"], b["accent"])
        else:                                   # a sweep while the size is unknown
            pygame.draw.rect(c, b["bar_track"], bar, border_radius=Y(6))
            k = (time.monotonic() * 0.6) % 1.0
            w = bar.w // 4
            x = bar.x + int((bar.w - w) * (k if int(time.monotonic() * 0.6) % 2 == 0 else 1 - k))
            pygame.draw.rect(c, b["accent"], (x, bar.y, w, bar.h), border_radius=Y(6))
            self._next_frame(0.05)
        self.tx(c, "Press any button to skip.", self.f(Y(19)), b["muted"], W // 2, Y(600), align="center")


class IGrid(CableSkin):
    """Calmcast i-Grid: the navy interactive guide of the 2006 Motorola
    boxes. Navy page, blue cells, grey-blue channel tiles, a yellow cursor
    with dark lettering, the picture top-right."""
    name = "igrid"
    label = "Calmcast i-Grid"
    MARK, MARK_TAG = "i-Grid", "CALMCAST"
    PIP = "right"
    MENU = "list"
    LIST_WORD = "All Channels"
    NO_SIGNAL = ("One Moment Please", "This channel should be available shortly.", "Ref code: S0a00")
    BOOT_WORDS = ("Please wait...", "Loading program guide...")
    NATIVE = {"bg": [14, 30, 92], "accent": [38, 66, 158], "accent2": [255, 204, 0],
              "text": [255, 255, 255], "chnum": [150, 165, 200]}

    def roles(self, b):
        r = super().roles(b)
        r.update(chan=mix(b["bg"], (255, 255, 255), 0.22), hdr_ink=(12, 16, 40), mark2=(220, 30, 40),
                 band=(8, 18, 70), bar_track=mix(b["bg"], (255, 255, 255), 0.3))
        return r


class Passage(CableSkin):
    """Passage: the charcoal guide of the 2004 Scientific Atlanta boxes.
    Charcoal page, slate cells, a gold cursor, the picture top-left and
    the description at the right."""
    name = "passage"
    label = "Passage"
    MARK, MARK_TAG = "Passage", "TIME WANDER CABLE"
    PIP = "left"
    MENU = "list"
    LIST_WORD = "All"
    NO_SIGNAL = ("Not Available", "This channel is not available at this time.", "Please try again later.")
    BOOT_WORDS = ("Please wait...", "Acquiring channel data...")
    ATTENTION = "Notice"
    NATIVE = {"bg": [20, 20, 26], "accent": [58, 66, 88], "accent2": [236, 184, 40],
              "text": [236, 236, 236], "chnum": [92, 100, 122]}

    def roles(self, b):
        r = super().roles(b)
        r.update(band=(16, 16, 20), mark2=b["accent2"])
        return r


class Wayfinder(CableSkin):
    """Wayfinder HD: the light guide of the 2009 Time Warner boxes. A silver
    page, white cells, a blue cursor, a graphite title bar."""
    name = "wayfinder"
    label = "Wayfinder HD"
    MARK, MARK_TAG = "Wayfinder", "TIME WANDER CABLE"
    PIP = "right"
    MENU = "list"
    LIST_WORD = "All Channels"
    NO_SIGNAL = ("Channel Unavailable", "This channel is temporarily unavailable.", "Please try again in a few minutes.")
    BOOT_WORDS = ("Starting...", "Loading channel listings...")
    NATIVE = {"bg": [226, 229, 234], "accent": [246, 247, 249], "accent2": [22, 92, 196],
              "text": [28, 32, 40], "chnum": [50, 56, 70]}

    def roles(self, b):
        r = super().roles(b)
        r.update(hdr_ink=(240, 242, 246), chan=mix(b["bg"], (255, 255, 255), 0.5), chan_ink=b["text"],
                 edge=(196, 200, 208), band=(34, 38, 48), band_ink=(240, 242, 246), mark2=b["accent2"],
                 panel=(246, 247, 249), panel_edge=(196, 200, 208), btn=(246, 247, 249), field=(255, 255, 255),
                 bar_track=(200, 204, 212), rule=(205, 208, 215), now=mix(b["accent"], b["accent2"], 0.12),
                 soft=(90, 96, 110), muted=(120, 126, 140))
        return r


class Y1(CableSkin):
    """Y1: the black guide of the 2014 Comcast box. A black page, charcoal
    cells, a white cursor with dark lettering, a light face, the Main Menu
    a row of words over the dimmed picture."""
    name = "y1"
    label = "Y1"
    MARK, MARK_TAG = "Y1", "CALMCAST"
    PIP = "right"
    MENU = "bar"
    default_font = "barlow"
    LIST_WORD = "All Channels"
    NO_SIGNAL = ("Something's not right", "We're having trouble playing this channel.", "Code: XRE-03007")
    BOOT_WORDS = ("Welcome", "Getting your channels ready...")
    boot_scenes = [("logo", 1.2), ("loading", 1.2)]
    ATTENTION = "Sorry"
    NATIVE = {"bg": [10, 10, 12], "accent": [36, 36, 40], "accent2": [236, 236, 240],
              "text": [240, 240, 244], "chnum": [18, 18, 22]}

    def roles(self, b):
        r = super().roles(b)
        r.update(accent=(0, 120, 215), bar_fill=(0, 120, 215), mark2=(0, 120, 215), hdr_ink=b["text"],
                 edge=(10, 10, 12), chan=(18, 18, 22), band=(14, 14, 18), rule=(44, 44, 50))
        return r

    def _cell(self, c, cell, airing, on, row_i):
        b, Y = self.b, self.Y
        pygame.draw.rect(c, b["sel"] if on else (b["now"] if airing else b["cell"]), cell, border_radius=Y(4))
