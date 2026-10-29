"""The cable boxes: four skins after the guides the big US cable companies
leased out, drawn to frames of the real ones (docs/cathode-4/
skin-references.md names the sources):

- Cumcast i-Grid (2006): the Motorola-era interactive guide. A navy
  header with the mark, clock and a red tile; the picture top-right with
  the programme described in a blue panel beside it; steel channel tiles,
  blue cells, a pale yellow cursor with navy lettering; a Main Menu of
  capsule buttons in two columns.
- Passage (2004): the Scientific Atlanta-era guide. A silver page, a cream
  card top-left with the channel and the programme, the picture top-right
  over a maroon channel strip; lavender channel tiles, purple cells, the
  cursor cream; the A / B / C key bar along the foot; condensed lettering.
- Wayfinder (2010): the later Time Warner guide, blue on blue. A steel-blue
  page, the channel on a blue band over a white card with the programme,
  navy channel tiles, royal-blue cells, a gold cursor; the key bar along
  the foot.
- Y1 (2014): the Comcast box. Everything over the dimmed picture: a light
  face, charcoal cells with black gaps, the cursor a lighter cell with a
  white rule and blue lettering, the programme in a panel along the foot;
  a Main Menu of words in a row, the chosen one underlined in blue.

The three SD boxes draw 4:3 at 640x480, their frames' own pixels; Y1 draws
16:9 at 1280x720. Geometry is written in 640x480 units for all four (X()
and Y() scale it; on Y1 the units are twice as wide as tall)."""

import time
from datetime import datetime, timedelta, timezone

import pygame

from ..paths import asset

from .box import BoxSkin, mix, nice, readable, rgba, vgrad


def ampm(dt, space=False) -> str:
    """'7:03pm' (i-Guide), '8:00 pm' (Passport, Navigator)."""
    s = dt.astimezone().strftime("%I:%M%p").lstrip("0").lower()
    return s[:-2] + " " + s[-2:] if space else s


def short(dt) -> str:
    """'9:09a', the 2014 box's clock."""
    return ampm(dt)[:-1]


class CableSkin(BoxSkin):
    """What the four share: the unit system, lettering, the flat dialog,
    keyboard, system page, playback bar, boot. Each skin names its colours
    and draws its guide, banner, menu and page top."""
    canvas = (640, 480)
    SD = True
    guide_hours = 1.5
    tune_black = 1.0
    TALL = ("guide", "screensaver", "ondemand")
    default_font = "sans"
    SQUEEZE = 1.0                   # lettering squeezed to a condensed width (Passage)
    MARK = "cable"
    MARK_TAG = ""
    NO_SIGNAL = ("One Moment Please", "This channel should be available shortly.", "Ref code: S0a00")
    boot_scenes = [("logo", 1.6), ("loading", 1.0)]
    BOOT_WORDS = ("Please wait...", "Loading program guide...")
    ATTENTION = "Attention"
    ROWS, ROW_PITCH = 4, 45         # the guide's rows and their pitch, in units

    @property
    def guide_rows(self):
        return self.ROWS + self.grow // self.Y(self.ROW_PITCH)

    # ── Units: 640x480, scaled to the canvas ──────────────────────────────

    def X(self, v) -> int:
        return int(round(v * self.canvas[0] / 640))

    def Y(self, v) -> int:
        return int(round(v * type(self).canvas[1] / 480))

    def R(self, x, y, w, h) -> pygame.Rect:
        return pygame.Rect(self.X(x), self.Y(y), self.X(w), self.Y(h))

    def u(self, v) -> int:
        return self.Y(v)

    # ── Lettering ─────────────────────────────────────────────────────────

    def tx(self, c, s, f, ink, x, y, align="left", shadow=None) -> int:
        if not s:
            return 0
        t = self.text
        if self.SQUEEZE == 1.0:
            if shadow:
                t.draw(c, s, f, shadow[:3], x + 1, y + 1, align=align)
            return t.draw(c, s, f, ink[:3], x, y, align=align)
        img, extra = t.render(f, s, ink[:3])
        w, h = img.get_size()
        img = pygame.transform.smoothscale(img, (max(1, int(w * self.SQUEEZE)), h))
        w = img.get_width()
        x = x - w if align == "right" else x - w // 2 if align == "center" else x
        if shadow:
            sh, _ = t.render(f, s, shadow[:3])
            c.blit(pygame.transform.smoothscale(sh, (w, h)), (x + 1, y + 1 - t.ink(f)[0] - extra))
        c.blit(img, (x, y - t.ink(f)[0] - extra))
        return w

    def fit(self, f, s, max_w) -> str:
        return self.text.fit(f, s, int(max_w / self.SQUEEZE))

    def width(self, f, s) -> int:
        return int(self.text.width(f, s) * self.SQUEEZE)

    def wrap(self, f, s, max_w, n) -> list:
        return self.text.wrap(f, s, int(max_w / self.SQUEEZE), n)

    def mid(self, r, f) -> int:
        return r.y + (r.h - self.text.ink(f)[1]) // 2

    def cell_lines(self, title, w, h, size):
        return self.cell_text(title, w, h, lambda s: self.fb(self.Y(s)), size, width=self.width)

    # ── Pieces cut from a box's own frames ────────────────────────────────

    _sprites = {}

    def _sprite(self, name):
        """A piece of the box's frames (assets/skins/<skin>): a page or band
        with its text taken out, a row or key cut from it. Cast in the
        theme's page colour when the theme isn't the native one."""
        cast = None if self.theme_key() == "native" else tuple(self.b["page"][:3])
        key = (self.name, name, cast)
        img = CableSkin._sprites.get(key)
        if img is None:
            img = pygame.image.load(asset("skins", self.name, name))
            if cast:
                img = img.copy()
                img.fill((*cast, 255), special_flags=pygame.BLEND_RGB_MULT)   # ponytail: a colour cast, not a retinted frame
            CableSkin._sprites[key] = img
        return img

    def _nine(self, c, img, r, cut):
        """A sprite stretched to `r` as nine slices: `cut` is (left, top,
        right, bottom), the margins kept at their own size."""
        l, t, rt, bt = cut
        w, h = img.get_size()
        mw, mh = w - l - rt, h - t - bt
        dw, dh = r.w - l - rt, r.h - t - bt
        for (sx, sy, sw, sh), (dx, dy, tw, th) in (
                ((0, 0, l, t), (r.x, r.y, l, t)), ((l, 0, mw, t), (r.x + l, r.y, dw, t)), ((l + mw, 0, rt, t), (r.right - rt, r.y, rt, t)),
                ((0, t, l, mh), (r.x, r.y + t, l, dh)), ((l, t, mw, mh), (r.x + l, r.y + t, dw, dh)), ((l + mw, t, rt, mh), (r.right - rt, r.y + t, rt, dh)),
                ((0, t + mh, l, bt), (r.x, r.bottom - bt, l, bt)), ((l, t + mh, mw, bt), (r.x + l, r.bottom - bt, dw, bt)),
                ((l + mw, t + mh, rt, bt), (r.right - rt, r.bottom - bt, rt, bt))):
            if sw > 0 and sh > 0 and tw > 0 and th > 0:
                piece = img.subsurface((sx, sy, sw, sh))
                c.blit(piece if (sw, sh) == (tw, th) else pygame.transform.smoothscale(piece, (tw, th)), (dx, dy))

    # ── The picture window ────────────────────────────────────────────────

    def _picture(self, c, edge=None, w=3):
        vx, vy, vw, vh = self.guide_video_box()
        self.hole(c, (vx, vy, vw, vh))
        if edge:
            pygame.draw.rect(c, rgba(edge), (vx - w, vy - w, vw + 2 * w, vh + 2 * w), w)
        return pygame.Rect(vx, vy, vw, vh)

    def _band(self, c, r, fill, alpha=230, radius=0, **corners):
        band = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(band, (*fill[:3], alpha), band.get_rect(), border_radius=radius, **corners)
        c.blit(band, r.topleft)

    # ── Buttons, rows, panels: each skin's own ────────────────────────────

    def _button(self, c, r, label, on, f=None):
        """A flat button, the cursor colour when chosen."""
        b, Y = self.b, self.Y
        fill, ink = (b["sel"], b["sel_ink"]) if on else (b["btn"], b["btn_ink"])
        pygame.draw.rect(c, fill, r, border_radius=Y(4))
        f = f or self.fb(Y(13))
        if label:
            self.tx(c, self.fit(f, label, r.w - Y(10)), f, ink, r.centerx, self.mid(r, f), align="center")

    def _list_row(self, c, r, title, meta, on, f=None, fm=None):
        """A list row: title at the left, meta at the right."""
        b, X, Y = self.b, self.X, self.Y
        fill, ink = (b["sel"], b["sel_ink"]) if on else (b["row"], b["row_ink"])
        pygame.draw.rect(c, fill, r)
        f, fm = f or self.fb(Y(13)), fm or self.f(Y(11))
        mw = self.width(fm, meta) + X(12) if meta else 0
        self.tx(c, self.fit(f, title, r.w - mw - X(16)), f, ink, r.x + X(8), self.mid(r, f))
        if meta:
            self.tx(c, meta, fm, ink, r.right - X(8), self.mid(r, fm), align="right")

    def _panel(self, c, r):
        pygame.draw.rect(c, self.b["panel"], r)

    # ── Live: digits, volume, trick, notes ────────────────────────────────

    def _digits(self, c, digits):
        b, X, Y = self.b, self.X, self.Y
        r = self.R(24, 24, 120, 48)
        self._band(c, r, b["band"], radius=Y(4))
        f = self.fb(Y(30))
        self.tx(c, digits + "-" * (3 - len(digits)), f, b["band_ink"], r.centerx, self.mid(r, f), align="center")

    def _volume(self, c, cx, cy):
        b, X, Y = self.b, self.X, self.Y
        v = self.app.video
        r = self.R(24, 24, 280, 32)
        self._band(c, r, b["band"], radius=Y(4))
        f = self.fb(Y(13))
        self.tx(c, "Mute" if v.muted else "Volume", f, b["sel"] if v.muted else b["band_ink"], r.x + X(12), self.mid(r, f))
        bar = pygame.Rect(r.x + X(90), r.y + Y(11), X(176), Y(10))
        pygame.draw.rect(c, b["track"], bar)
        if not v.muted:
            pygame.draw.rect(c, b["sel"], (bar.x, bar.y, int(bar.w * v.volume / 100), bar.h))

    def _tbtn(self, c, r, kind, on, num=None):
        b = self.b
        self._button(c, r, "", on)
        self.transport_face(c, kind, r, b["sel_ink"] if on else b["btn_ink"], self.fb(self.Y(11)), num=num)

    def _trick(self, c, s):
        b, X, Y = self.b, self.X, self.Y
        r = self.R(24, 410, 592, 34)
        self.live_buttons(c, s, r.x + X(4), r.y - Y(38), X(86), Y(28), X(10))
        self._band(c, r, b["band"], radius=Y(4))
        behind = s["behind"]
        mm, ss = divmod(int(behind), 60)
        f = self.fb(Y(13))
        tag = "Paused" if s["paused"] else ("Live" if behind < 2 else "Playing")
        self.tx(c, tag, f, b["band_ink"], r.x + X(12), self.mid(r, f))
        bar = pygame.Rect(r.x + X(100), r.y + Y(12), X(400), Y(10))
        pygame.draw.rect(c, b["track"], bar)
        total = s["buffer"] + behind
        if total >= 2:
            x = bar.x + int(bar.w * s["buffer"] / total)
            pygame.draw.rect(c, b["sel"], (bar.x, bar.y, x - bar.x, bar.h))
            pygame.draw.rect(c, b["band_ink"], (x - 1, bar.y - Y(3), X(2), bar.h + Y(6)))
        self.tx(c, f"-{mm}:{ss:02d}" if behind >= 1 else "Live", f, b["band_ink"], r.right - X(12), self.mid(r, f), align="right")

    def _note(self, c, text, frac=None):
        b, X, Y = self.b, self.X, self.Y
        bar = frac is not None and frac >= 0
        f = self.fb(Y(14))
        r = pygame.Rect(X(24), 0, max(self.width(f, text) + X(28), X(300) if bar else 0), Y(46 if bar else 32))
        r.bottom = Y(370)
        self._band(c, r, b["band"], radius=Y(4))
        self.tx(c, text, f, b["band_ink"], r.x + X(14), r.y + Y(8))
        if bar:
            self.progress(c, pygame.Rect(r.x + X(14), r.bottom - Y(14), r.w - X(28), Y(7)), frac, b["track"], b["sel"])

    def draw_note(self, c, text):
        self._note(c, text)

    def draw_guide_progress(self, c, frac):
        self._note(c, "Loading guide data" + self.pct(frac), frac)

    # ── Dialogs ───────────────────────────────────────────────────────────

    def _dialog(self, c, title, lines, buttons=(), focus=0, wide=420):
        """The box's card: a title bar, the lines, buttons at the foot."""
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        f = self.f(Y(14))
        wrapped = [w for line in lines for w in self.wrap(f, line, X(wide - 40), 3)]
        r = pygame.Rect(0, 0, X(wide), Y(30) + Y(14) + len(wrapped) * Y(20) + (Y(44) if buttons else Y(10)))
        r.center = (W // 2, H // 2)
        pygame.draw.rect(c, b["dlg"], r, border_radius=Y(6))
        pygame.draw.rect(c, b["dlg_edge"], r, 2, border_radius=Y(6))
        head = pygame.Rect(r.x, r.y, r.w, Y(30))
        pygame.draw.rect(c, b["dlg_head"], head, border_top_left_radius=Y(6), border_top_right_radius=Y(6))
        fh = self.fb(Y(16))
        self.tx(c, self.fit(fh, title, r.w - X(20)), fh, b["dlg_head_ink"], head.centerx, self.mid(head, fh), align="center")
        y = head.bottom + Y(10)
        for line in wrapped:
            self.tx(c, line, f, b["dlg_ink"], r.x + X(14), y)
            y += Y(20)
        if buttons:
            bw = X(100)
            x0 = r.centerx - (len(buttons) * bw + (len(buttons) - 1) * X(10)) // 2
            for k, label in enumerate(buttons):
                self._button(c, pygame.Rect(x0 + k * (bw + X(10)), r.bottom - Y(36), bw, Y(24)), label, k == focus)
        return r

    def _signal_loss(self, c):
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
        b, X, Y = self.b, self.X, self.Y
        f = self.fb(Y(14))
        lines = self.wrap(f, msg, X(540), 3)
        lh = Y(18)
        w = max(self.width(f, ln) for ln in lines) + X(32)
        r = pygame.Rect((self.canvas[0] - w) // 2, Y(70) if self.over_picture() else Y(200), w, Y(12) + lh * len(lines))
        self._band(c, r, b["band"], 240, radius=Y(4))
        pygame.draw.rect(c, b["sel"], (r.x, r.y, Y(4), r.h), border_top_left_radius=Y(4), border_bottom_left_radius=Y(4))
        for k, ln in enumerate(lines):
            self.tx(c, ln, f, b["band_ink"], r.centerx + Y(2), r.y + Y(6) + k * lh, align="center")

    def draw_options(self, c, m):
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        r = pygame.Rect(0, 0, X(340), Y(40) + len(m.items) * Y(30))
        r.center = (W // 2, H // 2)
        pygame.draw.rect(c, b["dlg"], r, border_radius=Y(6))
        pygame.draw.rect(c, b["dlg_edge"], r, 2, border_radius=Y(6))
        head = pygame.Rect(r.x, r.y, r.w, Y(28))
        pygame.draw.rect(c, b["dlg_head"], head, border_top_left_radius=Y(6), border_top_right_radius=Y(6))
        fh = self.fb(Y(16))
        self.tx(c, m.title, fh, b["dlg_head_ink"], head.centerx, self.mid(head, fh), align="center")
        f = self.f(Y(14))
        for k, it in enumerate(m.items):
            row = pygame.Rect(r.x + X(8), head.bottom + Y(6) + k * Y(30), r.w - X(16), Y(26))
            on = k == m.cursor
            v = it.value() if it.value else ""
            v = f"< {v} >" if v and on and it.adjust else v
            self._list_row(c, row, it.label, v, on, f=f)
            self.hit(row, lambda k=k: m.activate(k))

    # ── The pages every box shares: On Demand, recordings, info, keyboard, system ──

    poster_wall = True
    keyboard_layer = "abc"
    WALL = (5, 2)
    OD_ROWS = 7
    LIST = (0, 232, 640, 200)       # the list area under the page top, in units
    SIDE = None                     # side buttons (x, y, w, h, pitch), or a row under the list

    def page_video_box(self, screen):
        return self.guide_video_box()

    def ondemand_cols(self, screen):
        return self.WALL[0] if screen.view == "wall" else 1

    def ondemand_page(self, screen):
        return self.WALL[0] * self.WALL[1] if screen.view == "wall" else self.OD_ROWS

    def _page_top(self, c, title, sub="", picture=True):
        """The top of a full page: the box's header, the title and help,
        the picture if the page keeps one. Subclasses draw it."""
        raise NotImplementedError

    def _foot(self, c, text):
        b, X, Y = self.b, self.X, self.Y
        f = self.f(Y(11))
        self.tx(c, self.fit(f, text, X(600)), f, b["foot_ink"], X(20), Y(458))

    def _od_buttons(self, c, labels, focus, hits):
        X, Y = self.X, self.Y
        if self.SIDE:
            x, y, w, h, pitch = self.SIDE
            for k, label in enumerate(labels):
                r = self.R(x, y + k * pitch, w, h)
                self._button(c, r, label, k == focus)
                if hits and hits[k]:
                    self.hit(r, hits[k])
            return
        lx, ly, lw, lh = self.LIST
        bw = X(130)
        x = self.X(lx + lw) - len(labels) * (bw + X(8))
        for k, label in enumerate(labels):
            r = pygame.Rect(x + k * (bw + X(8)), self.Y(ly + lh) + Y(6), bw, Y(22))
            self._button(c, r, label, k == focus)
            if hits and hits[k]:
                self.hit(r, hits[k])

    def _rows(self, c, s, area, rows, sel, top, n_vis):
        b, X, Y = self.b, self.X, self.Y
        rh = area.h // n_vis
        for k, i in enumerate(range(top, min(len(rows), top + n_vis))):
            row = rows[i]
            r = pygame.Rect(area.x, area.y + k * rh, area.w, rh - Y(2))
            self._list_row(c, r, nice(row.get("title", "")), row.get("meta", "").split("   ")[0], i == sel)
            self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))
        f = self.f(Y(11))
        if top + n_vis < len(rows):
            self.tx(c, "▼", f, b["foot_ink"], area.right - X(6), area.bottom + Y(2), align="right")
        if top:
            self.tx(c, "▲", f, b["foot_ink"], area.right - X(6), area.y - Y(14), align="right")

    def _wall(self, c, s, area):
        b, X, Y = self.b, self.X, self.Y
        cols = self.WALL[0]
        gap = X(10)
        tw = (area.w - (cols + 1) * gap) // cols
        th = (area.h - Y(30)) // self.WALL[1] - Y(8)
        for i, slot in self.wall_cells(s, cols, self.WALL[1]):
            row = s.rows[i]
            r = pygame.Rect(area.x + gap + (slot % cols) * (tw + gap), area.y + Y(6) + (slot // cols) * (th + Y(8)), tw, th)
            if i == s.sel:
                pygame.draw.rect(c, b["sel"], r.inflate(Y(8), Y(8)), border_radius=Y(3))
            pygame.draw.rect(c, b["field"], r)
            art = self.app.ondemand.poster(row.get("thumb", ""), r.w, r.h) if row.get("thumb") else None
            if art:
                c.blit(art, art.get_rect(center=r.center))
            self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))
        cur = s.current() or {}
        r = pygame.Rect(area.x, area.bottom - Y(22), area.w, Y(20))
        self._list_row(c, r, nice(cur.get("title", "")), cur.get("meta", "").split("   ")[0], True)

    def draw_ondemand(self, c, s):
        b, X, Y = self.b, self.X, self.Y
        rec = bool(s.level) and s.level.get("key") == "recordings"
        title = "My Recordings" if rec else "On Demand"
        sub = "By date" if rec else (s.crumb() if len(s.stack) > 1 else "Movies and shows from your Plex server")
        self._page_top(c, title, sub)
        area = self.R(*self.LIST)
        self._panel(c, area)
        if s.mode == "auth":
            y = area.y + Y(30)
            for line, f in (("On a phone or computer, go to", self.f(Y(13))), (s.auth_link or "plex.tv/link", self.fb(Y(16))),
                            ("and enter this code:", self.f(Y(13)))):
                self.tx(c, line, f, b["panel_ink"], area.centerx, y, align="center")
                y += self.text.ink(f)[1] + Y(10)
            if s.auth_code:
                self.tx(c, s.auth_code, self.fb(Y(40)), b["panel_ink"], area.centerx, y + Y(6), align="center")
            self._od_buttons(c, ["Cancel"], 0, [s.back])
            return
        rows, n_vis = s.rows, self.ondemand_page(s)
        top = max(0, min(s.sel - n_vis // 2, len(rows) - n_vis))
        if s.view == "wall":
            self._wall(c, s, area)
        else:
            self._rows(c, s, area.inflate(-X(8), -Y(8)), rows, s.sel, top, n_vis)
        side = self.od_side(s)
        self._od_buttons(c, [lab for lab, _ in side], -1 if s.side is None else s.side, [fn for _, fn in side])
        f = self.f(Y(11))
        self.tx(c, f"{s.sel + 1} of {len(rows)}", f, b["foot_ink"], X(620), Y(458), align="right")
        if s.status:
            self.tx(c, self.fit(f, s.status, X(360)), f, b["foot_ink"], X(20), Y(458))
        else:
            self._foot(c, f"{self.k('SELECT')}: choose   {self.k('BACK')}: back   {self.k('EXIT')}: close")

    def od_side(self, s):
        if s.mode != "browse":
            return []
        rec = bool(s.level) and s.level.get("key") == "recordings"
        return [("Options", lambda: s.handle("MENU")),
                ("Sort", lambda: s.handle("MENU")) if rec else ("Recordings", lambda: s.handle("LIST")),
                ("Done", s.back)]

    def draw_iteminfo(self, c, info):
        from ..screens.iteminfo import hms
        b, X, Y = self.b, self.X, self.Y
        d = info.detail
        meta = d.get("subtitle") or d.get("meta", "")
        facts = [s for s in (meta, f"Length {hms(d['duration'])}" if d.get("duration") else "",
                             f"Resume at {hms(d['offset'])}" if (d.get("offset") or 0) > 5 else "") if s]
        self._page_top(c, d.get("title", ""), "   ".join(facts), picture=False)
        area = self.R(*self.LIST)
        self._panel(c, area)
        art_r = pygame.Rect(area.x + X(12), area.y + Y(10), X(96), Y(144))
        pygame.draw.rect(c, b["field"], art_r)
        art = self.logo(d.get("poster", ""), art_r.w, art_r.h, headers=d.get("poster_headers") or None)
        if art:
            c.blit(art, art.get_rect(center=art_r.center))
        fd = self.f(Y(13))
        y = area.y + Y(12)
        x0 = art_r.right + X(14)
        for line in self.wrap(fd, d.get("summary", "") or "No description available.", area.right - X(12) - x0,
                              (area.h - Y(24)) // Y(17)):
            self.tx(c, line, fd, b["panel_ink"], x0, y)
            y += Y(17)
        names = info.buttons()
        self._od_buttons(c, [self.button_words(info.label(n)) for n in names], info.focus,
                         [lambda k=k, n=n: (setattr(info, "focus", k), info.press(n)) for k, n in enumerate(names)])

    def keyboard_rows(self, layer):
        if layer == "sym":
            keys = ["!@#$%^&*()", "_+=?~'\"|\\;", "[]{}<>,`:/"]
        else:
            keys = ["ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZ'-.&", "1234567890"]
            if layer == "abc":
                keys = [k.lower() for k in keys]
        return keys + [["DEL", "SPACE", "SHIFT", "SYM"], ["DONE", "CANCEL", "CLEAR"]]

    def draw_keyboard(self, c, kb):
        b, X, Y = self.b, self.X, self.Y
        self._page_top(c, "Search" if kb.prompt.lower().startswith("search") else "Enter Text", kb.prompt, picture=False)
        area = self.R(*self.LIST)
        self._panel(c, area)
        field = pygame.Rect(area.x + X(20), area.y + Y(8), area.w - X(40), Y(24))
        pygame.draw.rect(c, b["field"], field)
        pygame.draw.rect(c, b["sel"], (field.x, field.bottom - Y(2), field.w, Y(2)))
        ff = self.fb(Y(15))
        shown = kb.value[:kb.caret]
        while shown and self.width(ff, shown) > field.w - X(24):
            shown = shown[1:]
        x = field.x + X(8) + self.tx(c, shown, ff, b["field_ink"], field.x + X(8), self.mid(field, ff))
        pygame.draw.rect(c, b["sel"], (x + X(1), field.y + Y(4), X(2), field.h - Y(8)))
        grid = kb.grid()
        fk = self.fb(Y(14))
        words = {"DEL": "Delete", "SPACE": "Space", "SHIFT": "a-z" if kb.layer == "ABC" else "A-Z",
                 "SYM": "ABC" if kb.layer == "sym" else "Symbols", "DONE": "Done", "CANCEL": "Cancel", "CLEAR": "Clear"}
        kx, ky = area.x + X(20), field.bottom + Y(8)
        kw, kh, pitch = X(54), Y(22), Y(26)
        for r, row in enumerate(grid):
            last = r == len(grid) - 1
            for col, cell in enumerate(row):
                on = (r, col) == (kb.row, kb.col)
                if last:
                    rect = pygame.Rect(kx + col * X(200), ky + r * pitch + Y(4), X(190), kh)
                    self._button(c, rect, words[cell], on)
                else:
                    if len(cell) == 1:
                        rect = pygame.Rect(kx + col * (kw + X(6)), ky + r * pitch, kw, kh)
                    else:
                        widths = {"DEL": 110, "SPACE": 220, "SHIFT": 120, "SYM": 120}
                        x0 = kx + sum(X(widths[k] + 6) for k in row[:col])
                        rect = pygame.Rect(x0, ky + r * pitch, X(widths[cell]), kh)
                    label = cell if len(cell) == 1 else words[cell]
                    self._button(c, rect, label, on, f=fk if len(cell) == 1 else self.fb(Y(12)))
                self.hit(rect, lambda r=r, col=col, cell=cell: (setattr(kb, "row", r), setattr(kb, "col", col),
                                                                kb._press(cell)))
        self._foot(c, kb.tip())

    def draw_diagnostics(self, c, d):
        b, X, Y = self.b, self.X, self.Y
        self._page_top(c, "System Information", "", picture=False)
        area = self.R(*self.LIST)
        self._panel(c, area)
        f = self.f(Y(13))
        y = area.y + Y(10)
        rows = [("Signal strength", f"{d.signal()}"), ("Signal quality", f"{d.quality()}")] + d.rows()
        pitch = min(Y(20), (area.h - Y(20)) // max(1, len(rows)))
        for label, value in rows:
            self.tx(c, label, f, b["panel_dim"], area.x + X(280), y, align="right")
            self.tx(c, self.fit(f, str(value), X(300)), f, b["panel_ink"], area.x + X(292), y)
            y += pitch
        from ..menus import open_button_guide
        self._od_buttons(c, ["Help", "Done"], 1, [lambda: open_button_guide(self.app), lambda: d.handle("BACK")])

    def draw_playback(self, c, pb):
        from ..screens.iteminfo import hms
        b, X, Y = self.b, self.X, self.Y
        if pb.skip_label and self.on_top(pb):
            r = self.R(440, 300 if pb.bar_visible() else 400, 180, 26)
            self._button(c, r, f"{pb.skip_label.title()}  ({self.k('SELECT')})", True)
            self.hit(r, lambda: pb.handle("SELECT"))
        if not pb.bar_visible():
            return
        r = self.R(24, 356, 592, 86)
        self._band(c, r, b["band"], radius=Y(4))
        f = self.fb(Y(15))
        q = self.app.ondemand.queue
        title = pb.title + (f"  ({q.pos + 1} of {len(q.items)})" if q.items and q.pos >= 0 else "")
        tw = self.tx(c, self.fit(f, title, X(420)), f, b["band_ink"], r.x + X(12), r.y + Y(8))
        if pb.subtitle and X(420) - tw > X(80):
            fm = self.f(Y(12))
            self.tx(c, self.fit(fm, pb.subtitle, X(420) - tw - X(12)), fm, b["band_ink"], r.x + X(12) + tw + X(12),
                    r.y + Y(8) + (self.text.ink(f)[1] - self.text.ink(fm)[1]))
        self.tx(c, "Paused" if self.app.video.paused else "Playing", f, b["sel"], r.right - X(12), r.y + Y(8), align="right")
        line = pygame.Rect(r.x + X(70), r.y + Y(38), r.w - X(140), Y(8))
        pygame.draw.rect(c, b["track"], line)
        frac = min(1.0, pb.pos / pb.dur) if pb.dur else 0.0
        pygame.draw.rect(c, b["sel"], (line.x, line.y, max(Y(8), int(line.w * frac)), line.h))
        fs = self.f(Y(12))
        self.tx(c, hms(pb.pos), fs, b["band_ink"], line.x - X(8), line.y - Y(4), align="right")
        self.tx(c, hms(pb.dur) if pb.dur else "--:--", fs, b["band_ink"], line.right + X(8), line.y - Y(4))
        self.hit(line.inflate(0, Y(14)), lambda: pb.seek_to(self._click_frac(line)))
        rects = []
        for k, (kind, _, fn) in enumerate(pb.transport()):
            br = pygame.Rect(r.x + X(70) + k * X(78), r.bottom - Y(30), X(70), Y(22))
            self._tbtn(c, br, kind, k == getattr(pb, "tfocus", None))
            self.hit(br, fn)
            rects.append(br)
        self.idle_row(c, pb, rects, Y(4))

    def draw_screensaver(self, c, ss):
        W, H = self.canvas
        c.fill((0, 0, 0, 255))
        size = self.Y(36)
        w = self.measure(self.wordmark, size)
        x, y = ss.position(w, int(size * 1.6), W, H)
        self.wordmark(c, x, y, size)

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        scene, age = boot.scene(), boot.scene_age()
        self._boot_page(c)
        size = Y(40)
        mw = self.measure(self.wordmark, size)
        self.wordmark(c, (W - mw) // 2, Y(170), size)
        f = self.f(Y(15))
        if scene == "logo":
            self.tx(c, self.BOOT_WORDS[0], f, b["boot_ink"], W // 2, Y(250), align="center")
            return
        self.tx(c, self.BOOT_WORDS[1], f, b["boot_ink"], W // 2, Y(250), align="center")
        g = getattr(self.app, "guide_progress", None)
        bar = self.R(190, 284, 260, 8)
        if g is not None and g >= 0:
            self.progress(c, bar, max(g, min(1.0, age / 3.0)), b["track"], b["sel"])
        else:
            pygame.draw.rect(c, b["track"], bar, border_radius=Y(4))
            k = (time.monotonic() * 0.6) % 1.0
            w = bar.w // 4
            x = bar.x + int((bar.w - w) * (k if int(time.monotonic() * 0.6) % 2 == 0 else 1 - k))
            pygame.draw.rect(c, b["sel"], (x, bar.y, w, bar.h), border_radius=Y(4))
            self._next_frame(0.05)
        self.tx(c, "Press any button to skip.", self.f(Y(11)), b["boot_ink"], W // 2, Y(400), align="center")

    def _boot_page(self, c):
        c.fill((*self.b["page"], 255))

    def guide_keys(self) -> str:
        def k(action, plain):
            name = self.k(action)
            return plain if name == action else name
        return (f"{k('CH_UP', 'CH+')}/{k('CH_DOWN', 'CH-')}: page   {k('REW', 'REW')}/{k('FF', 'FF')}: a day   "
                f"{k('THEMES', 'THEMES')}: lists   {k('INFO', 'INFO')}: details")

    # ── A grid of programme cells, laid out by each skin's numbers ────────

    def _grid(self, c, g, grid_x, grid_w, top, pitch, rh, gap, size, draw_tile, draw_cell, ink_for):
        """Rows of cells from `top`: draw_tile(c, rect, ch, selected) draws
        the channel tile, draw_cell(c, rect, airing, on, row_i, prog) the
        cell's ground, ink_for(on) the lettering. Returns the rows drawn."""
        b, t, X, Y = self.b, self.text, self.X, self.Y
        start, end = g.window()
        rows = g.filtered()[g.top: g.top + g.rows]
        mins = g.hours * 60
        now = datetime.now(timezone.utc)
        epg = self.app.epg
        sel = g.sel_time()
        f_cell = self.fb(Y(size))
        for i, ch in enumerate(rows):
            y = top + pitch * i
            row_sel = g.focus == "grid" and g.top + i == g.cursor
            draw_tile(c, pygame.Rect(0, y, grid_x - gap, rh), ch, row_sel)
            cid = epg.resolve_channel_id(ch.epg_id, ch.name) if epg else None
            progs = epg.programs_in_window(cid, start, end) if cid else []
            if not progs:
                cell = pygame.Rect(grid_x, y, grid_w - gap, rh)
                draw_cell(c, cell, False, row_sel, i, None)
                self.tx(c, "No information", f_cell, ink_for(row_sel), cell.x + X(6), self.mid(cell, f_cell))
            for p in progs:
                a = max(0.0, (p.start - start).total_seconds() / 60)
                e = min(float(mins), (p.stop - start).total_seconds() / 60)
                if e <= a:
                    continue
                cell = pygame.Rect(grid_x + int(a / mins * grid_w), y, int((e - a) / mins * grid_w) - gap, rh)
                on = row_sel and p.start <= sel < p.stop
                draw_cell(c, cell, p.start <= now < p.stop, on, i, p)
                ink = ink_for(on)
                shadow = self.cell_shadow(on)
                l, r = cell.x + X(self.CELL_PAD), min(cell.right, self.canvas[0] - X(4)) - X(5)
                if p.start < start and self.CELL_ARROWS:
                    pygame.draw.polygon(c, ink, [(cell.x + X(3), cell.centery), (cell.x + X(8), cell.centery - Y(5)),
                                                 (cell.x + X(8), cell.centery + Y(5))])
                    l += X(7)
                if p.stop > end and self.CELL_ARROWS:
                    pygame.draw.polygon(c, ink, [(cell.right - X(3), cell.centery), (cell.right - X(8), cell.centery - Y(5)),
                                                 (cell.right - X(8), cell.centery + Y(5))])
                    r -= X(7)
                f, lines = self.cell_lines(p.title, r - l, rh - Y(4), size)
                lh = t.ink(f)[1]
                ty = y + (rh - len(lines) * lh - (len(lines) - 1)) // 2
                for line in lines:
                    self.tx(c, line, f, ink, l, ty, shadow=shadow)
                    ty += lh + 1
            self.hit((0, y, self.canvas[0], rh), lambda i=i: (setattr(g, "cursor", g.top + i),
                                                             setattr(g, "focus", "grid"), g.handle("SELECT")))
        off = (now - start).total_seconds() / 60
        if 0 <= off <= mins and rows and b.get("now_line"):     # a box that drew no line names none
            x = grid_x + int(off / mins * grid_w)
            pygame.draw.rect(c, b["now_line"], (x - 1, top - Y(2), X(2), len(rows) * pitch - (pitch - rh) + Y(2)))
        if not rows:
            cell = pygame.Rect(grid_x, top, grid_w - gap, rh)
            draw_cell(c, cell, False, False, 0, None)
            self.tx(c, self.fit(f_cell, self.empty_guide(g), cell.w - X(20)), f_cell, ink_for(False), cell.x + X(10),
                    self.mid(cell, f_cell))
        return rows

    def cell_shadow(self, on):
        """The drop shadow under a cell's lettering, if the box drew one."""
        return None

    CELL_PAD = 5                    # a cell's lettering inset, in units
    CELL_ARROWS = True              # arrows on cells running past the window (Passage drew none)

    def _time_header(self, c, g, hdr, grid_x, grid_w, f, ink, rule, day_x, space=False, day_fmt="{a} {m}/{d}", centre=False):
        """The day at the left, the quarter hours over the grid (centred in
        their columns when `centre`)."""
        X, Y = self.X, self.Y
        start, _ = g.window()
        day = start.astimezone()
        hy = self.mid(hdr, f)
        self.tx(c, day_fmt.format(a=f"{day:%a}", A=f"{day:%a}".upper(), m=day.month, d=day.day), f, ink, day_x, hy)
        slots = int(g.hours * 4)
        col = grid_w / slots
        labels = [ampm(start + timedelta(minutes=15 * i), space) for i in range(slots)]
        every = self.label_every(col, max(self.width(f, s) for s in labels))
        phase = (day.minute // 15) % every                  # labels on the hour and half hour when every other column
        for i in range(slots):
            x = grid_x + col * i
            if (i + phase) % every == 0:
                if i and rule:
                    pygame.draw.rect(c, rule, (int(x) - 1, hdr.y + (0 if centre else Y(4)), max(1, X(1)), hdr.h - (0 if centre else Y(8))))
                if centre:
                    cx = int(x + col * every / 2)
                    if cx + self.width(f, labels[i]) // 2 <= hdr.right:       # a label that would run off the edge isn't drawn
                        self.tx(c, labels[i], f, ink, cx, hy, align="center")
                elif int(x) + X(6) + self.width(f, labels[i]) <= hdr.right:   # nor one past the header's end
                    self.tx(c, labels[i], f, ink, int(x) + X(6), hy)


class IGrid(CableSkin):
    """Cumcast i-Grid: the 2006 interactive guide of the Motorola boxes, to
    the frames in the box's reference manual (640x480), the cumcast lockup
    and the TV GRID badge where the box's operator and listings brands sat."""
    name = "igrid"
    label = "Cumcast i-Grid"
    MARK, MARK_TAG = "i-Grid", "CUMCAST"
    NO_SIGNAL = ("One Moment Please", "This channel should be available shortly.", "Ref code: S0a00")
    BOOT_WORDS = ("Please wait...", "Loading program guide...")
    ROWS, ROW_PITCH = 4, 45
    LIST = (0, 226, 640, 212)
    OD_ROWS = 6
    guide_hours = 2                 # 156 a half hour, the fourth column off the edge, as the frame
    CELL_ARROWS = False
    # Measured off the frames: the page navy, the cell navy, the pale yellow
    # cursor, the steel channel tile.
    NATIVE = {"bg": [0, 48, 100], "accent": [0, 38, 77], "accent2": [255, 249, 164],
              "text": [255, 255, 255], "chnum": [146, 186, 221]}
    LEGIBLE = [("text", ["navy", "cell", "info_top", "info_bot", "panel", "hdr", "capsule", "band", "row"], "ground"),
               ("sel_ink", ["sel"], "ink"), ("tile_ink", ["tile"], "ink"), ("title", ["info_top", "info_bot"], "ink")]

    def theme_base(self, base):
        bg, acc = base["bg"], base["accent"]
        return dict(base, accent=mix(bg, acc, 0.4), chnum=mix(base["text"], bg, 0.3))

    def roles(self, b):
        navy, cell, sel, text, tile = b["bg"], b["accent"], b["accent2"], b["text"], b["chnum"]
        dark = mix(navy, (0, 0, 0), 0.6)
        return {
            "page": navy, "navy": navy, "hdr": mix(navy, (0, 0, 0), 0.3), "cell": cell,
            "cell_hi": mix(cell, (255, 255, 255), 0.14), "gap": mix(navy, (0, 0, 0), 0.5),
            "sel": sel, "sel_ink": readable(sel, dark), "tile": tile, "tile_ink": readable(tile, dark),
            "text": text, "title": readable(mix(cell, (255, 255, 255), 0.2), (255, 240, 120)),
            "info_top": mix(cell, (255, 255, 255), 0.22), "info_bot": mix(cell, navy, 0.3),
            "panel": mix(cell, (255, 255, 255), 0.12), "panel_ink": text, "panel_dim": mix(text, cell, 0.3),
            "capsule": mix(cell, navy, 0.2), "capsule_rim": mix(cell, (255, 255, 255), 0.45),
            "red": (220, 30, 40), "green": (1, 113, 1), "purple": (86, 12, 135), "kids": (1, 80, 147),
            "band": navy, "band_ink": text, "track": mix(navy, (255, 255, 255), 0.3), "now_line": None,
            "row": cell, "row_ink": text, "btn": mix(cell, navy, 0.2), "btn_ink": text,
            "field": mix(navy, (0, 0, 0), 0.4), "field_ink": text, "foot_ink": mix(text, cell, 0.2),
            "dlg": mix(navy, cell, 0.4), "dlg_edge": mix(cell, (255, 255, 255), 0.45), "dlg_head": mix(navy, (0, 0, 0), 0.3),
            "dlg_head_ink": readable(mix(navy, (0, 0, 0), 0.3), (255, 240, 120)), "dlg_ink": text,
            "boot_ink": text,
        }

    def wordmark(self, c, x, y, size, ink=None):
        """The cumcast lockup (assets/skins/igrid/cumcast.png: the lowercase
        word with its red crescent), its crescent `size` tall; `ink` is
        ignored, the lockup keeps its colours."""
        img = self._sprite("cumcast.png")
        k = size / img.get_height()
        w, h = max(1, round(img.get_width() * k)), max(1, round(img.get_height() * k))
        c.blit(img if (w, h) == img.get_size() else pygame.transform.smoothscale(img, (w, h)), (x, y))
        return w

    def cell_shadow(self, on):
        return None if on else self.b["gap"]

    def label_every(self, col_w, label_w):
        return max(2, super().label_every(col_w, label_w))      # the box labelled the half hours

    def _od_buttons(self, c, labels, focus, hits):
        """Capsules along the foot band, right-aligned, narrowed to fit, the
        face shrunk before a word would be cut."""
        X, Y = self.X, self.Y
        n = max(1, len(labels))
        gap = X(8 if n <= 4 else 5)
        bw = min(X(130), (X(600) - (n - 1) * gap) // n)
        x = X(620) - n * bw - (n - 1) * gap
        f = next((self.fb(Y(s)) for s in (13, 12, 11) if all(self.width(self.fb(Y(s)), l) <= bw - X(20) for l in labels)),
                 self.fb(Y(11)))
        for k, label in enumerate(labels):
            r = pygame.Rect(x + k * (bw + gap), Y(444), bw, Y(22))
            self._capsule(c, r, label, k == focus, f)
            if hits and hits[k]:
                self.hit(r, hits[k])

    def _tile(self, c, x, y, size):
        """The red tile at the header's right, in the mark's place."""
        b, t = self.b, self.text
        r = pygame.Rect(x, y, int(size * 1.3), int(size * 1.1))
        pygame.draw.rect(c, b["red"], r, border_radius=max(2, size // 8))
        f = self.fb(max(7, int(size * 0.5)))
        t.draw(c, "TV", f, (255, 255, 255), r.centerx, r.y + size // 8, align="center")
        t.draw(c, "GRID", f, (255, 255, 255), r.centerx, r.y + size // 8 + t.ink(f)[1], align="center")

    def _header(self, c, right):
        """The header is the frame's own, the cumcast lockup and the TV GRID
        badge on it where the box's operator and listings brands sat; the
        clock goes between them."""
        b, X, Y = self.b, self.X, self.Y
        c.blit(self._sprite("cumcast.png"), (X(46), Y(41)))
        c.blit(self._sprite("tvgrid.png"), (X(328), Y(30)))
        self.tx(c, ampm(datetime.now()), self.fb(Y(18)), b["text"], X(320), Y(37), align="right")

    def guide_video_box(self):
        r = self.R(400, 0, 240, 196)
        return (r.x, r.y, r.w, r.h)

    def _info_panel(self, c, rect):
        vgrad(c, rect, rgba(self.b["info_top"]), rgba(self.b["info_bot"]))

    def _foot_curve(self, c, y):
        """The lighter band at the foot of a page, its lower corners rounded
        as the box drew every page."""
        b, X, Y = self.b, self.X, self.Y
        W, H = self.canvas
        pygame.draw.rect(c, b["panel"], (0, y, W, H - y), border_bottom_left_radius=Y(18), border_bottom_right_radius=Y(18))

    def draw_guide(self, c, g):
        """The guide on the frame itself (assets/skins/igrid/guide.png): the
        header, info panel, time bar, channel tiles and the foot band are
        the frame's; the picture shows through its window; the programme,
        the hours, the rows and cells and the hints are lettered over it."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        c.blit(self._sprite("guide.png"), (0, 0))
        pic = self._picture(c)
        self._header(c, pic.x)
        sel, cur = g.selected(), g.selected_program()
        f_title, f_line, f_desc = self.fb(Y(20)), self.fb(Y(16)), self.fb(Y(16))
        title = cur.title if cur else (sel.name if sel else "")
        self.tx(c, self.fit(f_title, title, X(230)), f_title, b["title"], X(48), Y(95), shadow=b["gap"])
        if sel:
            self.tx(c, self.fit(f_line, f"{sel.number} {call(sel)}", X(110)), f_line, b["text"], X(385), Y(97), align="right", shadow=b["gap"])
        if cur:
            self.tx(c, f"{ampm(cur.start)[:-2]}-{ampm(cur.stop)}", f_line, b["text"], X(48), Y(120), shadow=b["gap"])
            if cur.rating:
                self.tx(c, cur.rating, f_line, b["text"], X(385), Y(120), align="right", shadow=b["gap"])
            y = Y(146)
            for ln in self.wrap(f_desc, cur.description or "", X(335), 2):
                self.tx(c, ln, f_desc, b["text"], X(48), y, shadow=b["gap"])
                y += Y(22)
        elif sel:
            self.tx(c, "No information available.", f_desc, b["text"], X(48), Y(146), shadow=b["gap"])
        # The time bar: the list's name where the frame says Today, the half hours centred.
        hdr = self.R(0, 196, 640, 26)
        fh = self.fb(Y(16))
        name = g.category if g.category != "All" else "Today"
        tab = pygame.Rect(X(40), hdr.y + Y(3), X(86), hdr.h - Y(6))
        if g.focus == "category":
            pygame.draw.rect(c, b["sel"], tab, border_radius=Y(3))
        self.tx(c, self.fit(fh, f"< {name} >" if g.focus == "category" else name, tab.w - X(6)), fh,
                b["sel_ink"] if g.focus == "category" else b["text"], tab.centerx, self.mid(tab, fh), align="center")
        self.hit(tab, lambda: g.handle("THEMES"))
        grid_x, grid_w = X(128), X(626)
        self._time_header(c, g, pygame.Rect(hdr.x, hdr.y, X(596), hdr.h), grid_x, grid_w, fh, b["text"], None, X(0),
                          day_fmt="", centre=True)                      # clear of the frame's arrow at the right
        top, pitch, rh = Y(226), Y(45), Y(41)

        def tile(cc, r, ch, on):
            tr = pygame.Rect(X(2), r.y, X(123), rh)
            pygame.draw.rect(cc, b["tile"], tr)
            fn, fc = self.fb(Y(17)), self.fb(Y(14))
            self.tx(cc, str(ch.number), fn, b["tile_ink"], tr.centerx, r.y + Y(2), align="center")
            self.tx(cc, self.fit(fc, call(ch), tr.w - X(6)), fc, b["tile_ink"], tr.centerx, r.y + Y(23), align="center")
            if self.app.is_favorite(ch):
                pygame.draw.circle(cc, b["red"], (tr.right - X(7), r.y + Y(7)), Y(3))

        def cell(cc, r, airing, on, i, p):
            if on:
                fill = b["sel"]
            else:
                cat = (p.category or "").lower() if p else ""
                fill = (b["green"] if "sport" in cat else b["purple"] if "movie" in cat or "film" in cat
                        else b["kids"] if "kid" in cat or "child" in cat or "family" in cat else b["cell"])
            pygame.draw.rect(cc, fill, r)
            pygame.draw.rect(cc, mix(fill, (255, 255, 255), 0.35), r, 1)
        self._grid(c, g, grid_x, grid_w, top, pitch, rh, X(3), 17, tile, cell, lambda on: b["sel_ink"] if on else b["text"])
        fk = self.fb(Y(13))
        self.tx(c, self.fit(fk, self.guide_keys(), W - X(60)), fk, b["text"], W // 2, Y(430), align="center", shadow=b["gap"])

    # ── Live: the banner along the foot ───────────────────────────────────

    def _banner(self, c, ch, cur, nxt, full=False, tag=None):
        """The banner band cut from the frame (assets/skins/igrid/banner.png,
        y 352 down): the title in yellow on the title bar with the channel
        and the clock at its right, the hours and synopsis on the body."""
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        c.blit(self._sprite("banner.png"), (0, Y(352)))
        f_title, f_line = self.fb(Y(19)), self.fb(Y(15))
        self.tx(c, self.fit(f_title, cur.title if cur else ch.name, X(340)), f_title, b["title"], X(48), Y(362), shadow=b["gap"])
        self.tx(c, self.fit(f_line, f"{ch.number} {call(ch)}", X(110)), f_line, b["text"], X(482), Y(366), align="right", shadow=b["gap"])
        pygame.draw.rect(c, mix(b["text"], b["navy"], 0.4), (X(498), Y(362), X(2), Y(22)))
        self.tx(c, ampm(datetime.now()), f_line, b["text"], X(600), Y(366), align="right", shadow=b["gap"])
        y = Y(397)
        if cur:
            line = f"{ampm(cur.start)[:-2]}-{ampm(cur.stop)}" + (f"   {cur.rating}" if cur.rating else "")
            self.tx(c, line, f_line, b["text"], X(48), y, shadow=b["gap"])
            y += Y(26)
            f_desc = self.fb(Y(15))
            for ln in self.wrap(f_desc, cur.description or "", X(550), 2 if full else 1):
                self.tx(c, ln, f_desc, b["text"], X(48), y, shadow=b["gap"])
                y += Y(20)
        else:
            self.tx(c, "No information available.", f_line, b["text"], X(48), y, shadow=b["gap"])
        hint = tag or (f"{self.k('INFO')} for more" if not full else "")
        if hint:
            self.tx(c, hint, self.fb(Y(13)), b["title"], X(600), Y(449), align="right", shadow=b["gap"])
        if full and nxt:
            self.tx(c, self.fit(f_line, f"Next: {nxt.title}", X(380)), f_line, b["text"], X(48), Y(447), shadow=b["gap"])
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def draw_browse(self, c, br):
        if br.channel:
            cur, nxt = br.program()
            self._banner(c, br.channel, cur, nxt, tag=f"Browse: {self.k('SELECT')} to watch" + (f"  (+{br.ahead})" if br.ahead else ""))

    # ── Menus: the capsule grid under the header ──────────────────────────

    def menu_cols(self, menu):
        return 2 if not any(it.value or it.adjust for it in menu.items) and len(menu.items) > 3 else 1

    def menu_rows(self, menu):
        return 5 if self.menu_cols(menu) == 2 else super().menu_rows(menu)

    def menu_video_box(self, menu):
        return self.guide_video_box()

    def _capsule(self, c, r, label, on, f=None, right="", left=False):
        """A capsule cut from the frame (yellow when chosen), stretched to r;
        the label centred, or at the left with `right` (a value) at the right."""
        b, X, Y = self.b, self.X, self.Y
        img = self._sprite("cap_sel.png" if on else "cap.png")
        self._nine(c, img, pygame.Rect(r.x - X(2), r.y - Y(4), r.w + X(4), r.h + Y(8)), (X(18), 0, X(18), 0))
        f = f or self.fb(Y(15))
        ink = b["sel_ink"] if on else b["text"]
        rw = self.width(f, right) + X(16) if right else 0
        if right or left:
            self.tx(c, self.fit(f, label, r.w - rw - X(28)), f, ink, r.x + X(14), self.mid(r, f))
            if right:
                self.tx(c, right, f, ink, r.right - X(14), self.mid(r, f), align="right")
        else:
            self.tx(c, self.fit(f, label, r.w - X(20)), f, ink, r.centerx, self.mid(r, f), align="center")

    def _button(self, c, r, label, on, f=None):
        self._capsule(c, r, label, on, f)

    def _page_top(self, c, title, sub="", picture=True, rows=False):
        """A page on the frame (assets/skins/igrid/page.png; list.png with
        the section bar and rows when `rows`): the clock on the header, the
        title in yellow and the help on the info panel, the picture in the
        window (the box kept it on every page)."""
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        c.blit(self._sprite("list.png" if rows else "page.png"), (0, 0))
        pic = self._picture(c)
        self._header(c, pic.x)
        f = self.fb(Y(18))
        self.tx(c, self.fit(f, title, X(340)), f, b["title"], X(48), Y(95), shadow=b["gap"])
        if sub:
            fs = self.fb(Y(15))
            y = Y(121)
            for ln in self.wrap(fs, sub, X(335), 3):
                self.tx(c, ln, fs, b["text"], X(48), y, shadow=b["gap"])
                y += Y(22)

    def _section(self, c, left, right=""):
        """The section bar's words (list.png): a heading at the left, a note
        at the right."""
        b, X, Y = self.b, self.X, self.Y
        f = self.fb(Y(16))
        self.tx(c, self.fit(f, left, X(300)), f, b["text"], X(48), Y(203), shadow=b["gap"])
        if right:
            self.tx(c, right, f, b["title"], X(596), Y(203), align="right", shadow=b["gap"])

    def _panel(self, c, r):
        """The page is the frame's own."""

    def draw_menu(self, c, m):
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        it = m.items[m.cursor] if 0 <= m.cursor < len(m.items) else None
        title = "Main Menu" if m.title == "MAIN MENU" else m.title.title()
        n = len(m.items)
        cols = self.menu_cols(m)
        self._page_top(c, title, (it.label + ": " + it.help) if it and it.help else (it.label if it else ""), rows=cols == 1)
        if cols == 2:
            per = self.menu_rows(m)
            first = max(0, min((m.cursor // per) * per - per, n - 2 * per)) if n > 2 * per else 0
            f = self.fb(Y(16))
            for k, i in enumerate(range(first, min(n, first + 2 * per))):
                col, row = k // per, k % per
                r = pygame.Rect(X(48 + col * 277), Y(222 + row * 42), X(262), Y(30))
                self._capsule(c, r, m.items[i].label, i == m.cursor, f)
                self.hit(r, lambda i=i: m.activate(i))
            if n > 2 * per:
                self.tx(c, "\u25bc" if first + 2 * per < n else "\u25b2", self.f(Y(11)), b["text"], W // 2, Y(436), align="center")
            fk = self.fb(Y(13))
            self.tx(c, f"{self.k('SELECT')}: choose   {self.k('BACK')}: back   {self.k('EXIT')}: close", fk, b["text"], X(48), Y(451), shadow=b["gap"])
            return
        self._section(c, title, f"{m.cursor + 1} of {n}" if n > 6 else "")
        n_vis = 6
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        f = self.fb(Y(16))
        for k, i in enumerate(range(first, min(n, first + n_vis))):
            it = m.items[i]
            r = pygame.Rect(X(153), Y(226 + k * 35), X(487), Y(32))
            v = it.value() if it.value else (">" if it.submenu else "")
            v = f"< {v} >" if i == m.cursor and it.adjust else v
            self._list_row(c, r, it.label, v, i == m.cursor, f)
            if not it.enabled and i != m.cursor:
                veil = pygame.Surface(r.size, pygame.SRCALPHA)
                veil.fill((*b["navy"], 110))
                c.blit(veil, r.topleft)
            self.hit(pygame.Rect(X(2), r.y, W - X(2), r.h), lambda i=i: m.activate(i))
        fk = self.fb(Y(13))
        self.tx(c, f"{self.k('SELECT')}: choose   {self.k('BACK')}: back   {self.k('EXIT')}: close", fk, b["text"], X(48), Y(451), shadow=b["gap"])

    def _foot(self, c, text):
        f = self.fb(self.Y(13))
        self.tx(c, self.fit(f, text, self.X(400)), f, self.b["text"], self.X(48), self.Y(451), shadow=self.b["gap"])

    # ── The info page, the search page, dialogs ───────────────────────────

    def _info_page(self, c, title, line2, line3, rating, lines, back):
        """The info frame (assets/skins/igrid/info.png): the title in yellow
        with two lines under it on the info panel, the text on the panel
        below, the frame's back key with its word."""
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        c.blit(self._sprite("info.png"), (0, 0))
        pic = self._picture(c)
        self._header(c, pic.x)
        f_title, f_line = self.fb(Y(18)), self.fb(Y(16))
        self.tx(c, self.fit(f_title, title, X(300)), f_title, b["title"], X(48), Y(95), shadow=b["gap"])
        self.tx(c, self.fit(f_line, line2, X(300)), f_line, b["text"], X(48), Y(120), shadow=b["gap"])
        self.tx(c, self.fit(f_line, line3, X(300)), f_line, b["text"], X(48), Y(143), shadow=b["gap"])
        if rating:
            self.tx(c, rating, self.fb(Y(13)), b["text"], X(385), Y(122), align="right", shadow=b["gap"])
        fd = self.fb(Y(16))
        y = Y(205)
        for line in lines:
            for ln in self.wrap(fd, line, X(545), 6):
                if y > Y(340):
                    break
                self.tx(c, ln, fd, b["text"], X(48), y, shadow=b["gap"])
                y += Y(23)
        self.hit(self.R(56, 372, 48, 48), back)
        self.tx(c, f"{self.k('BACK')}: go back to the previous screen", self.fb(Y(15)), b["text"], X(48), Y(419), shadow=b["gap"])

    def draw_program_info(self, c, info):
        ch, p = info.channel, info.program
        if p:
            when = f"{ampm(p.start)[:-2]}-{ampm(p.stop)}"
            facts = "   ".join(x for x in (p.category, p.episode) if x)
            lines = [p.description or "No further information."] + ([facts] if facts else [])
        else:
            when, lines = "", ["No information is available for this time."]
        self._info_page(c, p.title if p else ch.name, when, f"{ch.number} {call(ch)}", p.rating if p else "", lines,
                        lambda: info.handle("BACK"))

    def draw_iteminfo(self, c, info):
        from ..screens.iteminfo import hms
        b, X, Y = self.b, self.X, self.Y
        d = info.detail
        meta = d.get("subtitle") or d.get("meta", "")
        facts = [x for x in (f"Length {hms(d['duration'])}" if d.get("duration") else "",
                             f"Resume at {hms(d['offset'])}" if (d.get("offset") or 0) > 5 else "") if x]
        self._info_page(c, d.get("title", ""), meta, "   ".join(facts), "", [d.get("summary", "") or "No description available."],
                        lambda: info.handle("BACK"))
        art = self.logo(d.get("poster", ""), X(60), Y(90), headers=d.get("poster_headers") or None)
        if art:
            c.blit(art, art.get_rect(topright=(X(388), Y(98))))
        names = info.buttons()
        self._od_buttons(c, [self.button_words(info.label(n)) for n in names], info.focus,
                         [lambda k=k, n=n: (setattr(info, "focus", k), info.press(n)) for k, n in enumerate(names)])

    def draw_keyboard(self, c, kb):
        """The search frame (assets/skins/igrid/search.png): the prompt and
        the typed text on the info panel, the keys as rows of boxes on the
        frame's six rows, the chosen one yellow."""
        b, X, Y = self.b, self.X, self.Y
        c.blit(self._sprite("search.png"), (0, 0))
        pic = self._picture(c)
        self._header(c, pic.x)
        search = kb.prompt.lower().startswith("search")
        fp = self.fb(Y(15))
        y = Y(98)
        for ln in self.wrap(fp, kb.prompt, X(335), 2):
            self.tx(c, ln, fp, b["title"], X(48), y, shadow=b["gap"])
            y += Y(20)
        field = self.R(48, 142, 335, 34)
        pygame.draw.rect(c, b["cell"], field, border_radius=Y(4))
        pygame.draw.rect(c, mix(b["cell"], (255, 255, 255), 0.4), field, 1, border_radius=Y(4))
        ff = self.fb(Y(18))
        shown = kb.value[:kb.caret]
        while shown and self.width(ff, shown) > field.w - X(24):
            shown = shown[1:]
        x = field.x + X(10) + self.tx(c, shown, ff, b["text"], field.x + X(10), self.mid(field, ff))
        pygame.draw.rect(c, b["sel"], (x + X(2), field.y + Y(7), X(2), field.h - Y(14)))
        self._section(c, "Search" if search else "Enter Text", self.fit(self.fb(Y(13)), kb.tip(), X(300)))
        grid = kb.grid()
        words = {"DEL": "Delete", "SPACE": "Space", "SHIFT": "a-z" if kb.layer == "ABC" else "A-Z",
                 "SYM": "ABC" if kb.layer == "sym" else "Symbols", "DONE": "Done", "CANCEL": "Cancel", "CLEAR": "Clear"}
        fk, fw = self.fb(Y(16)), self.fb(Y(14))
        for r_, row in enumerate(grid[:6]):
            y = Y(226 + r_ * 35)
            n = len(row)
            w = (X(487) - (n - 1) * X(4)) // n
            for col, cell in enumerate(row):
                rect = pygame.Rect(X(153) + col * (w + X(4)), y, w, Y(32))
                on = (r_, col) == (kb.row, kb.col)
                pygame.draw.rect(c, b["sel"] if on else b["cell"], rect, border_radius=Y(3))
                pygame.draw.rect(c, mix(b["cell"], (255, 255, 255), 0.45), rect, 1, border_radius=Y(3))
                label = cell if len(cell) == 1 else words.get(cell, cell)
                self.tx(c, label, fk if len(cell) == 1 else fw, b["sel_ink"] if on else b["text"], rect.centerx, self.mid(rect, fk if len(cell) == 1 else fw), align="center")
                self.hit(rect, lambda r_=r_, col=col, cell=cell: (setattr(kb, "row", r_), setattr(kb, "col", col), kb._press(cell)))

    def _dialog(self, c, title, lines, buttons=(), focus=0, wide=531):
        """The frame's dialog (assets/skins/igrid/dialog.png, nine-sliced):
        the title in yellow, the lines in white, capsule buttons at the
        foot."""
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        f = self.fb(Y(15))
        wrapped = [w for line in lines for w in self.wrap(f, line, X(wide - 60), 3)]
        n = max(1, len(wrapped))
        r = pygame.Rect(0, 0, X(max(531, wide)), Y(44) + n * Y(21) + (Y(58) if buttons else Y(16)))
        r.center = (W // 2, H // 2)
        self._nine(c, self._sprite("dialog.png"), r, (X(20), Y(20), X(20), Y(20)))
        ft = self.fb(Y(16))
        self.tx(c, self.fit(ft, title, r.w - X(40)), ft, b["title"], r.centerx, r.y + Y(18), align="center", shadow=b["gap"])
        y = r.y + Y(42)
        for line in wrapped:
            self.tx(c, line, f, b["text"], r.centerx, y, align="center", shadow=b["gap"])
            y += Y(21)
        if buttons:
            bw = X(120)
            x0 = r.centerx - (len(buttons) * bw + (len(buttons) - 1) * X(14)) // 2
            for k, label in enumerate(buttons):
                self._capsule(c, pygame.Rect(x0 + k * (bw + X(14)), r.bottom - Y(46), bw, Y(28)), label, k == focus)
        return r

    def draw_options(self, c, m):
        """Options on the frame's dialog: each setting a capsule, the chosen
        one yellow."""
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        n = len(m.items)
        r = pygame.Rect(0, 0, X(531), Y(50) + n * Y(38) + Y(14))
        r.center = (W // 2, H // 2)
        self._nine(c, self._sprite("dialog.png"), r, (X(20), Y(20), X(20), Y(20)))
        ft = self.fb(Y(16))
        self.tx(c, m.title.title(), ft, b["title"], r.centerx, r.y + Y(16), align="center", shadow=b["gap"])
        f = self.fb(Y(15))
        for k, it in enumerate(m.items):
            row = pygame.Rect(r.x + X(40), r.y + Y(46) + k * Y(38), r.w - X(80), Y(30))
            on = k == m.cursor
            v = it.value() if it.value else ""
            v = f"< {v} >" if v and on and it.adjust else v
            self._capsule(c, row, it.label, on, f, right=v, left=True)
            self.hit(row, lambda k=k: m.activate(k))

    def draw_playback(self, c, pb):
        """The banner band as the playback bar: the title, the state, the
        line and the transport capsules."""
        from ..screens.iteminfo import hms
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        if pb.skip_label and self.on_top(pb):
            r = self.R(420, 300 if pb.bar_visible() else 400, 200, 30)
            self._capsule(c, r, f"{pb.skip_label.title()}  ({self.k('SELECT')})", True)
            self.hit(r, lambda: pb.handle("SELECT"))
        if not pb.bar_visible():
            return
        c.blit(self._sprite("banner.png"), (0, Y(352)))
        f = self.fb(Y(19))
        q = self.app.ondemand.queue
        title = pb.title + (f"  ({q.pos + 1} of {len(q.items)})" if q.items and q.pos >= 0 else "")
        self.tx(c, self.fit(f, title, X(400)), f, b["title"], X(48), Y(362), shadow=b["gap"])
        self.tx(c, "Paused" if self.app.video.paused else "Playing", self.fb(Y(15)), b["text"], X(600), Y(366), align="right", shadow=b["gap"])
        line = self.R(110, 400, 420, 8)
        pygame.draw.rect(c, b["track"], line)
        frac = min(1.0, pb.pos / pb.dur) if pb.dur else 0.0
        pygame.draw.rect(c, b["sel"], (line.x, line.y, max(Y(8), int(line.w * frac)), line.h))
        fs = self.fb(Y(14))
        self.tx(c, hms(pb.pos), fs, b["text"], line.x - X(10), line.y - Y(4), align="right", shadow=b["gap"])
        self.tx(c, hms(pb.dur) if pb.dur else "--:--", fs, b["text"], line.right + X(10), line.y - Y(4), shadow=b["gap"])
        self.hit(line.inflate(0, Y(14)), lambda: pb.seek_to(self._click_frac(line)))
        rects = []
        for k, (kind, _, fn) in enumerate(pb.transport()):
            br = pygame.Rect(X(110) + k * X(72), Y(420), X(64), Y(24))
            self._tbtn(c, br, kind, k == getattr(pb, "tfocus", None))
            self.hit(br, fn)
            rects.append(br)
        self.idle_row(c, pb, rects, Y(12))

    def _list_row(self, c, r, title, meta, on, f=None, fm=None):
        """A row of the list page: the meta (a number, a value) on the steel
        tile cut from the frame at the left, the title on the row, the
        chosen row the frame's yellow one."""
        b, X, Y = self.b, self.X, self.Y
        tile = self._sprite("tile.png")
        c.blit(tile, (X(2), r.y))
        if on:
            c.blit(self._sprite("row_sel.png"), (X(153), r.y))
        f, fm = f or self.fb(Y(16)), fm or self.fb(Y(15))
        ink = b["sel_ink"] if on else b["text"]
        self.tx(c, self.fit(fm, meta, X(136)), fm, b["tile_ink"], X(76), r.y + Y(8), align="center")
        self.tx(c, self.fit(f, title, X(440)), f, ink, X(160), r.y + Y(7), shadow=None if on else b["gap"])

    def _rows(self, c, s, area, rows, sel, top, n_vis):
        """On Demand's rows on the frame's six."""
        b, X, Y = self.b, self.X, self.Y
        for k, i in enumerate(range(top, min(len(rows), top + n_vis))):
            row = rows[i]
            r = pygame.Rect(X(153), Y(226 + k * 35), X(487), Y(32))
            self._list_row(c, r, nice(row.get("title", "")), row.get("meta", "").split("   ")[0], i == sel)
            self.hit(pygame.Rect(X(2), r.y, self.canvas[0] - X(2), r.h), lambda i=i: (setattr(s, "sel", i), s.select()))
        f = self.fb(Y(12))
        if top + n_vis < len(rows):
            self.tx(c, "\u25bc", f, b["text"], X(620), Y(438), align="right")
        if top:
            self.tx(c, "\u25b2", f, b["text"], X(620), Y(208), align="right")

    def draw_ondemand(self, c, s):
        b, X, Y = self.b, self.X, self.Y
        rec = bool(s.level) and s.level.get("key") == "recordings"
        title = "My Recordings" if rec else "On Demand"
        sub = "By date" if rec else (s.crumb() if len(s.stack) > 1 else "Movies and shows from your Plex server")
        self._page_top(c, title, sub, rows=s.mode != "auth" and s.view != "wall")
        area = self.R(*self.LIST)
        if s.mode == "auth":
            y = area.y + Y(30)
            for line, f in (("On a phone or computer, go to", self.fb(Y(15))), (s.auth_link or "plex.tv/link", self.fb(Y(18))),
                            ("and enter this code:", self.fb(Y(15)))):
                self.tx(c, line, f, b["text"], area.centerx, y, align="center", shadow=b["gap"])
                y += self.text.ink(f)[1] + Y(10)
            if s.auth_code:
                self.tx(c, s.auth_code, self.fb(Y(40)), b["title"], area.centerx, y + Y(6), align="center", shadow=b["gap"])
            self._od_buttons(c, ["Cancel"], 0, [s.back])
            return
        rows, n_vis = s.rows, self.ondemand_page(s)
        top = max(0, min(s.sel - n_vis // 2, len(rows) - n_vis))
        if s.view == "wall":
            self._wall(c, s, area)
        else:
            self._section(c, s.crumb() if len(s.stack) > 1 else title, f"{s.sel + 1} of {len(rows)}")
            self._rows(c, s, area, rows, s.sel, top, n_vis)
        side = self.od_side(s)
        self._od_buttons(c, [lab for lab, _ in side], -1 if s.side is None else s.side, [fn for _, fn in side])
        if s.status:
            self._foot(c, s.status)

    def _boot_page(self, c):
        W, H = self.canvas
        c.fill((*self.b["navy"], 255))
        self._info_panel(c, pygame.Rect(0, self.Y(120), W, self.Y(220)))


class Passage(CableSkin):
    """Passage: Passport Echo on the 2004 Scientific Atlanta boxes, drawn to
    the viewer's manual's frames (640x480) in Archivo Narrow, the condensed
    face the box lettered in. A silver page; the cream card top-left with
    the channel disc, call sign, title, hours and synopsis; the picture
    top-right over the maroon channel strip with the clock in its dark
    tab; a purple time header, lavender channel tiles, purple cells, the
    chosen row dark with cream lettering; the mark and the A / B / C key
    bar along the foot. The banner is the frame's purple band with the
    light channel tile, the clock tab and the green progress line."""
    name = "passage"
    label = "Passage"
    MARK, MARK_TAG = "Passage", "echo"
    default_font = "akzidenz"
    guide_hours = 2                 # 137 a half hour, as the frame: the fourth column runs off the edge
    NO_SIGNAL = ("Not Available", "This channel is not available at this time.", "Please try again later.")
    BOOT_WORDS = ("Please wait...", "Acquiring channel data...")
    ATTENTION = "Notice"
    ROWS, ROW_PITCH = 5, 29
    CELL_PAD = 12
    CELL_ARROWS = False
    LIST = (50, 216, 590, 194)
    OD_ROWS = 6
    # Measured off the frames: the silver page, the purple cell, the cream
    # card, the dark lettering, the lavender channel tile.
    NATIVE = {"bg": [206, 206, 216], "accent": [118, 103, 168], "accent2": [246, 241, 186],
              "text": [44, 40, 64], "chnum": [152, 142, 198]}
    LEGIBLE = [("white", ["cell", "lav", "hdr", "navy", "maroon", "panel", "sel", "teal"], "ground"),
               ("ink", ["page", "page_lo", "card", "tile", "list"], "ground"), ("sel_ink", ["sel"], "ink")]

    def theme_base(self, base):
        bg, acc, text = base["bg"], base["accent"], base["text"]
        return dict(base, bg=mix(text, bg, 0.2), accent=mix(acc, bg, 0.4), accent2=mix(text, base["accent2"], 0.6),
                    text=mix(bg, (0, 0, 0), 0.5), chnum=mix(acc, text, 0.4))

    def roles(self, b):
        page, cell, cream, ink, lav = b["bg"], b["accent"], b["accent2"], b["text"], b["chnum"]
        white = (255, 255, 255)
        dark = mix(cell, (0, 0, 0), 0.42)
        return {
            "page": page, "page_lo": mix(page, white, 0.55), "page_hi": mix(page, (0, 0, 0), 0.08),
            "card": cream, "card_edge": mix(cream, (0, 0, 0), 0.35), "ink": ink, "white": white, "text": ink,
            "cell": cell, "lav": lav, "hdr": (168, 157, 195), "rule": mix(cell, white, 0.3),
            "sel": mix(cell, (0, 0, 0), 0.5), "sel_ink": cream, "sel_tile": mix(lav, (0, 0, 0), 0.45), "gap": (61, 54, 85),
            "line": mix(cell, white, 0.4), "movie": (151, 20, 64), "tab_blue": (34, 48, 138),
            "maroon": (118, 24, 62), "tab": (62, 52, 88), "navy": (6, 22, 78), "teal": (62, 132, 138),
            "green": (84, 200, 60), "track": mix(cell, (0, 0, 0), 0.3), "now_line": None,
            "tile": (228, 228, 234), "tile_ink": mix(ink, (0, 0, 0), 0.3), "blue": (56, 90, 200),
            "panel": mix(cell, (0, 0, 0), 0.2), "col": mix(cell, (0, 0, 0), 0.05), "col_hdr": mix(lav, white, 0.2),
            "panel_ink": white, "panel_dim": mix(white, cell, 0.3), "list": (142, 157, 188), "list_ink": (40, 40, 110),
            "band": cell, "band_ink": white, "row": lav, "row_ink": white, "btn": lav, "btn_ink": white,
            "field": white, "field_ink": ink, "foot_ink": ink,
            "dlg": mix(page, white, 0.25), "dlg_edge": mix(page, (0, 0, 0), 0.4), "dlg_head": mix(page, white, 0.25),
            "dlg_head_ink": mix(ink, (0, 0, 0), 0.4), "dlg_ink": (30, 30, 90), "boot_ink": ink,
            "key_a": (242, 200, 30), "key_b": (44, 92, 204), "key_c": (214, 40, 40), "key_sel": (40, 90, 200),
        }

    def wb(self, size):
        """The box's wide bold (Helvetica Bold on the frames): Liberation
        Sans Bold, for headings, hours, the clock and the banner's title."""
        return self.text.font("LiberationSans-Bold.ttf", size)

    def _hint(self, c, key, word, x, y, ink=None):
        """A key and its word along a foot: the SEL disc or an A / B / C icon
        cut from the frames at (x, y), the word beside it in the condensed
        face. Returns the right edge."""
        b, X, Y = self.b, self.X, self.Y
        if key in ("SEL", "A", "B", "C"):
            icon = self._sprite("sel.png" if key == "SEL" else f"key_{key.lower()}.png")
            c.blit(icon, (x, y))
            w = icon.get_width()
        else:
            self._key(c, key, x, y + Y(15))
            w = X(24)
        f = self.f(Y(20))
        self.tx(c, word, f, ink or b["ink"], x + w + X(6), y + Y(8))
        return x + w + X(6) + self.width(f, word)

    # ── The mark: the frame's own 'PASSPORT echo' lockup ──────────────────

    def wordmark(self, c, x, y, size, ink=None):
        """The PASSAGE echo lockup (assets/skins/passage/mark.png, drawn at
        twice the frames' size: 16 is the frames' own, 34 tall), scaled to
        `size`; `ink` is ignored, the lockup keeps its colours."""
        h = int(34 * size / 16)
        return self._mark(c, x, y - h // 4, size / 32)

    def _mark(self, c, x, y, k=0.5):
        """The lockup with its top left at (x, y), the 2x sprite scaled by k."""
        img = self._sprite("mark.png")
        w, h = max(1, round(img.get_width() * k)), max(1, round(img.get_height() * k))
        c.blit(img if (w, h) == img.get_size() else pygame.transform.smoothscale(img, (w, h)), (x, y))
        return w

    # ── Pieces ────────────────────────────────────────────────────────────

    def _page(self, c, rect):
        """The silver page as the frames shade it: dark just under the top,
        brightest at mid height, darker again at the foot."""
        if self.hold_backdrop(rect, self._page):
            return
        rect = pygame.Rect(rect)
        Y = self.Y
        stops = [(0, 234), (Y(40), 189), (Y(240), 255), (Y(480), 180)]
        for (y0, g0), (y1, g1) in zip(stops, stops[1:]):
            y0, y1 = rect.y + y0, rect.y + y1
            if y1 > y0:
                vgrad(c, (rect.x, y0, rect.w, y1 - y0), rgba((g0, g0, g0)), rgba((g1, g1, g1)))

    def guide_video_box(self):
        r = self.R(320, 0, 320, 200)
        return (r.x, r.y, r.w, r.h)

    def _card(self, c, r):
        """The cream card: a tab with one big rounded top-left corner, cream
        at the top running to olive at the foot, a soft shade inward from
        its left edge, square where the header hangs off it and the picture
        meets it."""
        b, X, Y = self.b, self.X, self.Y
        card = pygame.Surface(r.size, pygame.SRCALPHA)
        vgrad(card, card.get_rect(), rgba(b["card"]), rgba(mix(b["card"], (0, 0, 0), 0.24)))
        for i in range(X(10)):                                  # the shade inward from the left edge
            k = 1 - i / X(10)
            shade = pygame.Surface((1, r.h), pygame.SRCALPHA)
            shade.fill((40, 40, 20, int(130 * k * k)))
            card.blit(shade, (i, 0))
        mask = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_top_left_radius=Y(22))
        card.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        c.blit(card, r.topleft)
        pygame.draw.rect(c, mix(b["card"], (0, 0, 0), 0.45), r, 1, border_top_left_radius=Y(22))

    def _logo_disc(self, c, ch, x, y, size):
        """The channel's logo, else its number on the frame's glossy blue
        tile: a rounded square, light blue at the top running to blue-purple
        at the foot, the number big in the wide bold."""
        logo = self.channel_logo(ch, size, size) if ch else None
        if logo:
            c.blit(logo, logo.get_rect(center=(x + size // 2, y + size // 2)))
            return
        tile = pygame.Surface((size, size), pygame.SRCALPHA)
        vgrad(tile, tile.get_rect(), rgba((122, 176, 214)), rgba((92, 92, 176)))
        mask = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=max(2, size * 3 // 10))
        tile.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        c.blit(tile, (x, y))
        num = str(ch.number) if ch else ""
        f = self.wb(max(8, size))
        if self.width(f, num) > size - size // 8:
            f = self.wb(max(8, int(size * (size - size // 8) / self.width(f, num))))
        self.tx(c, num, f, (255, 255, 255), x + size // 2, y + (size - self.text.cap(f)) // 2, align="center")

    def _strip(self, c, ch, frame=False, top=None):
        """The maroon strip under the picture: the channel in the wide bold
        at its left, the clock in its dark slanted tab. On the frames the
        strip is their own (`top` where a frame hangs it lower); elsewhere
        it's drawn."""
        b, X, Y = self.b, self.X, self.Y
        vx, vy, vw, vh = self.guide_video_box()
        strip = pygame.Rect(vx, vy + vh if top is None else top, vw, Y(22))
        tab = pygame.Rect(strip.right - X(140), strip.y, X(140), strip.h)
        if not frame:
            pygame.draw.rect(c, b["maroon"], strip)
            pygame.draw.polygon(c, b["tab"], [(tab.x + X(12), tab.y), (tab.right, tab.y), (tab.right, tab.bottom), (tab.x, tab.bottom)])
        f = self.wb(Y(17))
        if ch:
            self.tx(c, self.fit(f, f"{call(ch)} \u2022 {ch.number}", X(150)), f, b["white"], strip.x + X(12), strip.y + Y(5))
        fc = self.f(Y(20))
        self.tx(c, datetime.now().strftime("%I:%M:%S").lstrip("0"), fc, b["white"], tab.x + X(20), strip.y + Y(4))

    def _key(self, c, letter, x, cy):
        """The A / B / C key chip: a yellow triangle, a blue square, a red disc."""
        b, X, Y = self.b, self.X, self.Y
        colour = {"A": b["key_a"], "B": b["key_b"], "C": b["key_c"]}[letter]
        if letter == "A":
            pygame.draw.polygon(c, colour, [(x, cy + Y(8)), (x + X(18), cy + Y(8)), (x + X(9), cy - Y(8))])
        elif letter == "B":
            pygame.draw.rect(c, colour, (x + X(1), cy - Y(8), X(16), Y(16)), border_radius=Y(3))
        else:
            pygame.draw.circle(c, colour, (x + X(9), cy), Y(8))
        f = self.fb(Y(11))
        self.tx(c, letter, f, (20, 20, 20) if letter == "A" else b["white"], x + X(9), cy - Y(5) + (Y(2) if letter == "A" else 0), align="center")

    def _sel_chip(self, c, x, cy):
        """The SEL key: a blue disc lettered SEL."""
        b, X, Y = self.b, self.X, self.Y
        pygame.draw.circle(c, b["key_sel"], (x + X(10), cy), Y(9))
        f = self.fb(Y(8))
        self.tx(c, "SEL", f, b["white"], x + X(10), cy - Y(4), align="center")

    def _keybar(self, c, y, keys, active=None):
        """Keys along the foot, cut from the frame: the yellow A triangle,
        blue B square and red C disc, the word beside each in the condensed
        face, the active one on the frame's light box (stretched to a long
        word) with its navy edge and shadow. Up to three keys sit where the
        frame put them; more run as words alone, packed from the right, the
        face shrunk until they fit. `y` is the box's top (the guide's is 403)."""
        b, X, Y = self.b, self.X, self.Y
        ink = mix(b["ink"], (0, 0, 0), 0.4)
        n = len(keys)
        icons = n <= 3
        lead = X(45) if icons else X(14)        # the box's edge to its word: past the key icon
        pad = X(21)                              # clear past the word, the box's rim in it (the frame's Time box)
        gap = X(10)
        for size in (25, 22, 20, 18):
            f = self.f(Y(size))
            words = [self.fit(f, word, X(96) if icons else X(130)) for _, word, _ in keys]
            widths = [lead + self.width(f, w) + pad for w in words]
            if sum(widths) + gap * (n - 1) <= X(560):
                break
        if icons and all(w <= X(103) for w in widths):     # the frame's slots, 103 apart
            xs = [X(v) for v in {3: (283, 386, 506), 2: (386, 506), 1: (506,)}[n]]
            widths = [max(X(96), w) for w in widths]
        else:
            x, xs = X(620) - sum(widths) - gap * (n - 1), []
            for w in widths:
                xs.append(x + X(9))
                x += w + gap
        ty = y + Y(17) + (Y(25) - Y(size)) // 2
        for k, (letter, word, fn) in enumerate(keys):
            x = xs[k]
            box = pygame.Rect(x - X(9), y, widths[k], Y(46))
            if active == k:
                self._nine(c, self._sprite("key_box.png"), box, (X(14), 0, X(14), 0))
            if icons and letter in ("A", "B", "C"):
                c.blit(self._sprite(f"key_{letter.lower()}.png"), (x, y + Y(11 if letter == "A" else 10)))
            elif icons and letter:
                self._key(c, letter, x + X(4), y + Y(26))
            self.tx(c, words[k], f, ink, box.x + lead, ty)
            if fn:
                self.hit(box, fn)

    # ── Guide ─────────────────────────────────────────────────────────────

    def draw_guide(self, c, g):
        """The guide on the frame itself: the page, card, time header,
        channel column, grid panel, mark and foot are the Passport Echo
        frame's own pixels (assets/skins/passage/guide.png) with its text
        taken out; the picture shows through the window; the channel tile,
        call sign and number, title, hours, rating and synopsis, the day
        and half hours, the rows and cells, and the keys are lettered over
        it where the frame letters them (condensed 24 for the rows, cells
        and title, 22 for the synopsis; the wide bold 17-18 for the call
        sign, hours and header)."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        c.blit(self._sprite("guide.png"), (0, 0))
        self._mark(c, X(42), Y(416))
        self._picture(c)
        sel, cur = g.selected(), g.selected_program()
        self._strip(c, sel, frame=True)
        # The card.
        ink = mix(b["ink"], (0, 0, 0), 0.7)
        self._logo_disc(c, sel, X(62), Y(48), Y(50))
        f_wide = self.wb(Y(17))
        if sel:
            self.tx(c, call(sel), f_wide, ink, X(125), Y(52))
            self.tx(c, str(sel.number), f_wide, ink, X(125), Y(72))
        f_title, f_time, f_desc = self.f(Y(24)), self.wb(Y(18)), self.f(Y(22))
        title = cur.title if cur else (sel.name if sel else "")
        self.tx(c, self.fit(f_title, title, X(245)), f_title, ink, X(65), Y(106))
        if cur:
            self.tx(c, f"{ampm(cur.start)} \u2013 {ampm(cur.stop)}", f_time, ink, X(65), Y(130))
            x0, y = X(65), Y(150)
            if cur.rating:
                fr = self.wb(Y(15))
                chip = pygame.Rect(x0 - X(3), y, max(X(18), self.width(fr, cur.rating) + X(6)), Y(17))
                pygame.draw.rect(c, (20, 20, 20), chip, border_radius=Y(2))
                self.tx(c, cur.rating, fr, b["white"], chip.centerx, chip.y + (chip.h - t.cap(fr)) // 2, align="center")
                x0 = chip.right + X(5)
            lines = self.wrap(f_desc, cur.description or "", X(245), 4)
            if len(lines) > 3:
                lines = lines[:3]
                lines[-1] = self.fit(f_desc, lines[-1] + " ...", X(245))
            for k, ln in enumerate(lines):
                self.tx(c, ln, f_desc, ink, x0 if k == 0 else X(65), y)
                y += Y(20)
        elif sel:
            self.tx(c, "No information available.", f_desc, ink, X(65), Y(150))
        # The header: the day at the left, the half hours centred between the frame's grooves.
        hdr = self.R(53, 223, 573, 26)                   # to the panel's rounded end at 632
        grid_x, grid_w = X(185), X(548)
        self._time_header(c, g, hdr, grid_x, grid_w, self.wb(Y(18)), b["navy"], None, X(67), space=True,
                          day_fmt="{a}.{m}/{d}", centre=True)
        # The rows: 27 tall on a 29 pitch from y 255; the chosen row's dark
        # tile is the frame's, cut to the column's rounded foot.
        top, pitch, rh = Y(255), Y(29), Y(27)
        col = pygame.Rect(X(55), top, X(123), Y(148))
        sel_tile = self._sprite("col_sel.png")
        corner = pygame.Surface(col.size, pygame.SRCALPHA)
        pygame.draw.rect(corner, (255, 255, 255, 255), corner.get_rect(), border_bottom_left_radius=Y(14))
        ft = self.f(Y(24))

        def tile(cc, r, ch, on):
            if on:
                piece = sel_tile.subsurface((0, 0, col.w, min(rh, sel_tile.get_height()))).copy()
                piece.blit(corner, (0, 0), (0, r.y - col.y, col.w, rh), special_flags=pygame.BLEND_RGBA_MIN)
                cc.blit(piece, (col.x, r.y))
            ink_t = b["sel_ink"] if on else b["navy"]
            self.tx(cc, call(ch), ft, ink_t, X(68), r.y + Y(3))
            self.tx(cc, f"{ch.number:02d}" if ch.number < 100 else str(ch.number), ft, ink_t, X(168), r.y + Y(3), align="right")
            if self.app.is_favorite(ch):
                pygame.draw.polygon(cc, b["card"], [(col.x + X(3), r.y + Y(3)), (col.x + X(10), r.y + Y(3)), (col.x + X(3), r.y + Y(10))])

        def cell(cc, r, airing, on, i, p):
            cat = (p.category or "").lower() if p else ""
            if on:
                pygame.draw.rect(cc, b["sel"], (r.x + X(2), r.y, r.w - X(2), r.h))
            elif "movie" in cat or "film" in cat:
                pygame.draw.rect(cc, b["movie"], (r.x + X(2), r.y, r.w - X(2), r.h))
            pygame.draw.rect(cc, b["line"], (r.x, r.y, X(2), r.h))
        c.set_clip(pygame.Rect(0, 0, X(628), H))         # the fourth column stops at the panel's end
        self._grid(c, g, grid_x, grid_w, top, pitch, rh, 0, 24, tile, cell, lambda on: b["sel_ink"] if on else b["white"])
        c.set_clip(None)
        # The foot: the mark, then the frame's keys with Cathode's actions: A a day on, B the list, C details.
        name = g.category if g.category != "All" else "Theme"
        self._keybar(c, Y(403), [("A", "Next Day", lambda: g.handle("FF")),
                                 ("B", name if g.focus != "category" else f"< {name} >", lambda: g.handle("THEMES")),
                                 ("C", "Info", lambda: g.handle("INFO"))], 1 if g.focus == "category" else 0)

    def cell_lines(self, title, w, h, size):
        return self.cell_text(title, w, h, lambda s: self.f(self.Y(s)), size, width=self.width)

    def label_every(self, col_w, label_w):
        return max(2, super().label_every(col_w, label_w))      # the box labelled the half hours

    # ── Live: the purple band, the light channel tile, the clock tab ──────

    def _band(self, c, r, fill, alpha=235, radius=0, **corners):
        band = pygame.Surface(r.size, pygame.SRCALPHA)
        vgrad(band, band.get_rect(), rgba(mix(fill, (255, 255, 255), 0.25), alpha), rgba(fill, alpha))
        if radius:
            mask = pygame.Surface(r.size, pygame.SRCALPHA)
            pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius, **corners)
            band.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        c.blit(band, r.topleft)

    def _chan_tile(self, c, ch, r, big=False):
        """The light tile with the channel's disc, call sign and number."""
        b, X, Y = self.b, self.X, self.Y
        pygame.draw.rect(c, b["tile"], r)
        if big:
            self._logo_disc(c, ch, r.centerx - Y(22), r.y + Y(16), Y(44))
            f = self.wb(Y(14))
            self.tx(c, call(ch), f, b["tile_ink"], r.centerx, r.y + Y(66), align="center")
            self.tx(c, str(ch.number), f, b["tile_ink"], r.centerx, r.y + Y(86), align="center")
            return
        self._logo_disc(c, ch, r.x + X(50), r.y + Y(12), Y(42))
        f = self.fb(Y(16))
        self.tx(c, call(ch), f, b["tile_ink"], r.x + X(122), r.y + Y(10))
        self.tx(c, str(ch.number), f, b["tile_ink"], r.x + X(122), r.y + Y(32))

    def _banner(self, c, ch, cur, nxt, full=False, tag=None):
        """The banner on the frame itself: the band and the channel tile
        with its slant are the Passport Echo frame's own pixels
        (assets/skins/passage/banner.png, y 357-447); the clock, logo, call
        sign and number on the tile, the title and hours on the title
        strip, the start and end times, the green line with its ticks and
        the navy time tab with its pointer are lettered and drawn over it
        where the frame has them."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        if full:
            self._full_banner(c, ch, cur, nxt)
            return
        c.blit(self._sprite("banner.png"), (0, Y(357)))
        ink = (0, 0, 0)
        self.tx(c, ampm(datetime.now(), True), self.wb(Y(16)), ink, X(166), Y(363), align="right")
        logo = self.channel_logo(ch, X(48), Y(32))
        if logo:
            c.blit(logo, logo.get_rect(center=(X(84), Y(409))))
        else:
            self._logo_disc(c, ch, X(68), Y(393), Y(32))
        self.tx(c, call(ch), self.f(Y(20)), ink, X(166), Y(392), align="right")
        self.tx(c, str(ch.number), self.wb(Y(17)), ink, X(166), Y(416), align="right")
        f_title, f_hours, f_time = self.wb(Y(17)), self.f(Y(19)), self.f(Y(20))
        self.tx(c, self.fit(f_title, cur.title if cur else ch.name, X(280)), f_title, b["white"], X(203), Y(368))
        if cur:
            self.tx(c, f"{ampm(cur.start)[:-1]} - {ampm(cur.stop)[:-1]}", f_hours, b["white"], X(598), Y(368), align="right")
            now = datetime.now(timezone.utc)
            frac = max(0.0, min(1.0, (now - cur.start).total_seconds() / max(1, (cur.stop - cur.start).total_seconds())))
            line = self.R(243, 418, 270, 11)
            pygame.draw.rect(c, b["track"], line, border_radius=Y(5))
            done = pygame.Rect(line.x, line.y, max(Y(11), int(line.w * frac)), line.h)
            green = pygame.Surface(done.size, pygame.SRCALPHA)
            vgrad(green, green.get_rect(), rgba((170, 252, 106)), rgba((80, 136, 32)))
            mask = pygame.Surface(done.size, pygame.SRCALPHA)
            pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=Y(5))
            green.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            c.blit(green, done.topleft)
            for k in (1, 2, 3):
                pygame.draw.rect(c, mix(b["track"], (255, 255, 255), 0.45), (line.x + line.w * k // 4, line.y + Y(2), X(2), line.h - Y(3)))
            pygame.draw.rect(c, mix(b["track"], (0, 0, 0), 0.2), line, 1, border_radius=Y(5))
            pygame.draw.rect(c, mix(b["track"], (255, 255, 255), 0.75), (line.x + Y(4), line.bottom - 1, line.w - Y(8), 1))
            self.tx(c, ampm(cur.start)[:-2], f_time, b["white"], X(202), Y(413))
            self.tx(c, ampm(cur.stop)[:-2], f_time, b["white"], X(520), Y(413))
            px = line.x + int(line.w * frac)
            tab = pygame.Rect(0, Y(389), X(50), Y(22))
            tab.centerx = px
            pygame.draw.rect(c, b["tab_blue"], tab, border_radius=Y(5))
            pygame.draw.rect(c, mix(b["tab_blue"], (255, 255, 255), 0.7), (tab.x + X(3), tab.y + Y(2), tab.w - X(6), 1))
            pygame.draw.rect(c, mix(b["tab_blue"], (0, 0, 0), 0.6), (tab.x + X(2), tab.bottom - Y(2), tab.w - X(4), Y(2)), border_radius=Y(2))
            pygame.draw.polygon(c, b["tab_blue"], [(px - X(5), tab.bottom - Y(2)), (px + X(5), tab.bottom - Y(2)), (px, line.y)])
            fm = self.wb(Y(16))
            self.tx(c, ampm(datetime.now())[:-2], fm, b["white"], px, tab.y + Y(5), align="center")
        else:
            self.tx(c, "No information available", f_time, b["white"], X(203), Y(413))
        if tag:
            self.tx(c, tag, self.f(Y(18)), b["card"], X(598), Y(394), align="right")
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def _full_banner(self, c, ch, cur, nxt, left=0):
        """INFO's banner, the Browse frame's band (assets/skins/passage/
        browse.png, y 366 down): the title in the wide bold, the hours at the
        right, the rating chip and the synopsis in the condensed face."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        img = self._sprite("browse.png")
        c.blit(img.subsurface((0, Y(366), W, H - Y(366))), (0, Y(366)))
        f_title, f_hours, f_desc = self.wb(Y(17)), self.f(Y(19)), self.f(Y(20))
        x0 = X(62)
        self.tx(c, self.fit(f_title, cur.title if cur else ch.name, X(400)), f_title, b["white"], x0, Y(372))
        if cur:
            self.tx(c, f"{ampm(cur.start)} \u2013 {ampm(cur.stop)}", f_hours, b["white"], X(580), Y(372), align="right")
            x, y = x0, Y(398)
            if cur.rating:
                fr = self.wb(Y(14))
                chip = pygame.Rect(x, y + Y(1), self.width(fr, cur.rating) + X(10), Y(17))
                pygame.draw.rect(c, (30, 30, 50), chip, border_radius=Y(2))
                self.tx(c, cur.rating, fr, b["white"], chip.centerx, chip.y + (chip.h - t.cap(fr)) // 2, align="center")
                x = chip.right + X(8)
            lines = self.wrap(f_desc, cur.description or "", X(580) - x0, 3)
            for k, ln in enumerate(lines):
                self.tx(c, ln, f_desc, b["white"], x if k == 0 else x0, y)
                y += Y(22)
            if nxt and y < H - Y(24):
                self.tx(c, self.fit(f_desc, f"Next: {nxt.title}", X(580) - x0), f_desc, b["card"], x0, y)
        else:
            self.tx(c, "No information available", f_desc, b["white"], x0, Y(398))
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def draw_browse(self, c, br):
        """The Browse frame itself: the light column with the channel's tile,
        call sign and number, the frame's own '< Browse >' box and the
        clock; the band along the foot."""
        if not br.channel:
            return
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        ch = br.channel
        cur, nxt = br.program()
        c.blit(self._sprite("browse.png"), (0, 0))
        ink = (30, 30, 34)
        self._logo_disc(c, ch, X(80), Y(55), Y(48))
        self.tx(c, call(ch), self.f(Y(20)), ink, X(104), Y(108), align="center")
        self.tx(c, str(ch.number), self.wb(Y(17)), ink, X(104), Y(128), align="center")
        self.tx(c, ampm(datetime.now(), True), self.f(Y(20)), ink, X(65), Y(335))
        self.hit(self.R(45, 265, 44, 40), lambda: br.handle("LEFT"))
        self.hit(self.R(91, 265, 44, 40), lambda: br.handle("RIGHT"))
        self._full_banner(c, ch, cur, nxt)
        tag = f"{self.k('SELECT')} to watch" + (f"  (+{br.ahead})" if br.ahead else "")
        self.tx(c, tag, self.f(Y(18)), b["card"], X(580), H - Y(24), align="right")

    def _digits(self, c, digits):
        b, X, Y = self.b, self.X, self.Y
        r = self.R(24, 24, 120, 48)
        pygame.draw.rect(c, b["tab"], r, border_radius=Y(6))
        f = self.fb(Y(30))
        self.tx(c, digits + "-" * (3 - len(digits)), f, b["white"], r.centerx, self.mid(r, f), align="center")

    def _volume(self, c, cx, cy):
        """The frame's volume bar (assets/skins/passage/volume.png): the word
        in the wide bold, red blocks lit along the trough."""
        b, X, Y = self.b, self.X, self.Y
        v = self.app.video
        c.blit(self._sprite("volume.png"), (0, Y(400)))
        f = self.wb(Y(17))
        self.tx(c, "Mute" if v.muted else "Volume", f, b["movie"] if v.muted else b["navy"], X(52), Y(416))
        n = 33
        lit = 0 if v.muted else round(n * v.volume / 100)
        for i in range(n):
            pygame.draw.rect(c, (120, 4, 4) if i < lit else (158, 158, 160), (X(162 + 14 * i), Y(413), X(7), Y(18)))

    # ── Dialogs: the light card with the maroon band ──────────────────────

    def _dialog(self, c, title, lines, buttons=(), focus=0, wide=440, rows=None, cursor=-1, hints=None):
        """The frame's dialog (assets/skins/passage/dialog.png, stretched as
        nine slices to its rows): the title in the wide bold, the first line
        on the maroon band, the rest (or `rows`, the chosen one on the
        frame's navy row) on the lavender body, the key hints at the foot."""
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        img = self._sprite("dialog.png")
        f = self.f(Y(21))
        first, rest = (lines[0], lines[1:]) if lines else ("", [])
        body = rows if rows is not None else [w for line in rest for w in self.wrap(f, line, X(wide - 100), 3)]
        n = max(1, len(body))
        r = pygame.Rect(0, 0, X(max(429, wide)), Y(70) + n * Y(28) + Y(46))
        r.center = (W // 2, H // 2)
        self._nine(c, img, r, (X(16), Y(70), X(16), Y(46)))
        ft = self.wb(Y(17))
        self.tx(c, self.fit(ft, title, r.w - X(40)), ft, (20, 20, 20), r.centerx, r.y + Y(12), align="center")
        fb = self.f(Y(20))
        self.tx(c, self.fit(fb, first, r.w - X(40)), fb, b["white"], r.centerx, r.y + Y(44), align="center")
        sel = self._sprite("dlg_sel.png")
        for k, ln in enumerate(body):
            row = pygame.Rect(r.x + X(12), r.y + Y(70) + k * Y(28), r.w - X(24), Y(28))
            on = k == cursor
            if on:
                c.blit(sel if row.w == sel.get_width() else pygame.transform.smoothscale(sel, (row.w, sel.get_height())), (row.x, row.y + 1))
            self.tx(c, self.fit(f, ln, row.w - X(70)), f, b["white"] if on else b["dlg_ink"], row.x + X(58), row.y + Y(7))
        hints = hints or ([("SEL", "Select")] + [("C", "Cancel")] if buttons or rows is not None else [("C", "Close")])
        fy = r.bottom - Y(38)
        for k, (key, word) in enumerate(hints):
            self._hint(c, key, word, r.x + X(50) if k == 0 else r.x + r.w - X(140), fy, ink=b["dlg_ink"])
        return r

    def draw_options(self, c, m):
        """The frame's Options popup (assets/skins/passage/options.png, its
        tab lettered with the menu's own title), the chosen row on the
        frame's cream band."""
        b, X, Y = self.b, self.X, self.Y
        labels = []
        for it in m.items:
            v = it.value() if it.value else ""
            labels.append(f"{it.label}:  {v}" if v else it.label)
        img = self._sprite("options.png")
        f = self.f(Y(20))
        n = max(1, len(labels))
        w = min(X(380), max(X(140), max(self.width(f, lab) for lab in labels) + X(50)))
        r = pygame.Rect(X(228), Y(220), w, Y(30) + n * Y(26) + Y(6))
        self._nine(c, img, r, (X(24), Y(42), X(12), Y(22)))
        ft = self.wb(Y(13))
        self.tx(c, self.fit(ft, m.title.title(), X(60)), ft, b["white"], r.x + X(12), r.y + Y(5))
        sel = self._sprite("opt_sel.png")
        for k, lab in enumerate(labels):
            band = pygame.Rect(r.x - X(2), r.y + Y(30) + k * Y(26), r.w + X(2), Y(24))
            on = k == m.cursor
            if on:
                self._nine(c, sel, band, (X(30), 0, X(12), 0))
            self.tx(c, self.fit(f, lab, r.w - X(44)), f, b["navy"] if on else b["white"], r.x + X(30), band.y + Y(4))
            self.hit(band, lambda k=k: m.activate(k))

    def draw_program_info(self, c, info):
        """The More Information frame (assets/skins/passage/info.png): the
        guide's card with the channel, title, hours, rating and the first
        lines of the synopsis; the panel under the band with the rest."""
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        ch, p = info.channel, info.program
        c.blit(self._sprite("info.png"), (0, 0))
        self._picture(c)
        self._strip(c, ch, frame=True)
        ink = mix(b["ink"], (0, 0, 0), 0.7)
        self._logo_disc(c, ch, X(62), Y(48), Y(50))
        f_wide = self.wb(Y(17))
        self.tx(c, call(ch), f_wide, ink, X(125), Y(52))
        self.tx(c, str(ch.number), f_wide, ink, X(125), Y(72))
        f_title, f_time, f_desc = self.f(Y(24)), self.wb(Y(18)), self.f(Y(22))
        self.tx(c, self.fit(f_title, p.title if p else ch.name, X(245)), f_title, ink, X(65), Y(106))
        more = []
        if p:
            self.tx(c, f"{ampm(p.start)} \u2013 {ampm(p.stop)}", f_time, ink, X(65), Y(130))
            x0, y = X(65), Y(150)
            if p.rating:
                fr = self.wb(Y(15))
                chip = pygame.Rect(x0 - X(3), y, max(X(18), self.width(fr, p.rating) + X(6)), Y(17))
                pygame.draw.rect(c, (20, 20, 20), chip, border_radius=Y(2))
                self.tx(c, p.rating, fr, b["white"], chip.centerx, chip.y + (chip.h - t.cap(fr)) // 2, align="center")
                x0 = chip.right + X(5)
            lines = self.wrap(f_desc, p.description or "", X(245), 12)
            for k, ln in enumerate(lines[:3]):
                self.tx(c, ln, f_desc, ink, x0 if k == 0 else X(65), y)
                y += Y(20)
            facts = "   ".join(x for x in (p.category, p.episode) if x)
            if facts:
                more.append(facts)
            if len(lines) > 3:
                more.append(p.description or "")
            elif not facts:
                more.append("No further information.")
        else:
            self.tx(c, "No information is available for this time.", f_desc, ink, X(65), Y(150))
        self.tx(c, "More Information", self.wb(Y(16)), b["navy"], X(346), Y(230), align="center")
        fm = self.f(Y(21))
        y = Y(258)
        for line in more:
            for ln in self.wrap(fm, line, X(540), 5):
                if y > Y(380):
                    break
                self.tx(c, ln, fm, b["navy"], X(78), y)
                y += Y(24)
        self._hint(c, "C", "Close", X(506), Y(414))
        self.hit(self.R(500, 410, 120, 36), lambda: info.handle("BACK"))

    def draw_capture(self, c, cap):
        self._dialog(c, "Remote Setup", ["Waiting for a button...", cap.prompt])

    def _signal_loss(self, c):
        """The frame's blocked-programme card (assets/skins/passage/
        blocked.png) on black, with Cathode's own words."""
        self._message_card(c, self.NO_SIGNAL[0], self.NO_SIGNAL[1:])

    def _message_card(self, c, title, lines):
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        c.fill((0, 0, 0, 255))
        card = self._sprite("blocked.png")
        r = card.get_rect(center=(W // 2, H // 2))
        c.blit(card, r.topleft)
        ft = self.wb(Y(16))
        self.tx(c, self.fit(ft, title, r.w - X(40)), ft, b["white"], r.centerx, r.y + Y(10), align="center")
        f = self.f(Y(20))
        y = r.y + Y(50)
        for line in lines:
            for ln in self.wrap(f, line, r.w - X(40), 2):
                self.tx(c, ln, f, (30, 30, 34), r.centerx, y, align="center")
                y += Y(24)

    def _message(self, c, msg):
        self._message_card(c, self.ATTENTION, [msg])

    def draw_toast(self, c, msg):
        b, X, Y = self.b, self.X, self.Y
        f = self.fb(Y(15))
        lines = self.wrap(f, msg, X(500), 3)
        w = max(self.width(f, ln) for ln in lines) + X(40)
        r = pygame.Rect((self.canvas[0] - w) // 2, Y(60) if self.over_picture() else Y(200), w, Y(10) + len(lines) * Y(20))
        pygame.draw.rect(c, b["tab"], r, border_radius=Y(6))
        for k, ln in enumerate(lines):
            self.tx(c, ln, f, b["white"], r.centerx, r.y + Y(5) + k * Y(20), align="center")

    def _note(self, c, text, frac=None):
        b, X, Y = self.b, self.X, self.Y
        bar = frac is not None and frac >= 0
        f = self.fb(Y(15))
        r = pygame.Rect(X(24), 0, max(self.width(f, text) + X(28), X(300) if bar else 0), Y(46 if bar else 30))
        r.bottom = Y(360)
        pygame.draw.rect(c, b["tab"], r, border_radius=Y(6))
        self.tx(c, text, f, b["white"], r.x + X(14), r.y + Y(6))
        if bar:
            self.progress(c, pygame.Rect(r.x + X(14), r.bottom - Y(14), r.w - X(28), Y(7)), frac, b["track"], b["green"])

    # ── Pages: the General Settings frame ─────────────────────────────────

    def menu_video_box(self, menu):
        return self.page_video_box(menu)

    def page_video_box(self, screen):
        """The settings frame's window; the DVR frame's for On Demand (its
        window runs to y 216); the guide's for the rest."""
        name = getattr(screen, "name", "")
        if name in ("menu", "settings", "diagnostics", "options", "capture"):
            r = self.R(350, 0, 290, 189)
        elif name == "ondemand":
            r = self.R(320, 0, 320, 216)
        else:
            r = self.R(320, 0, 320, 200)
        return (r.x, r.y, r.w, r.h)

    def _page_top(self, c, title, sub="", picture=True, heading=""):
        """The settings page on the frame (assets/skins/passage/page.png):
        the title in the wide bold on the header strip, the heading and
        help on the cream panel, the picture in the window (page_wide.png
        runs the strip and panel across when there's none)."""
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        c.blit(self._sprite("page.png" if picture else "page_wide.png"), (0, 0))
        right = X(350) if picture else W
        ink = mix(b["ink"], (0, 0, 0), 0.7)
        f = self.wb(Y(17))
        self.tx(c, self.fit(f, title, right - X(120)), f, b["navy"], X(97), Y(46))
        y = Y(80)
        if heading:
            fh = self.wb(Y(16))
            for ln in self.wrap(fh, heading, right - X(80), 2):
                self.tx(c, ln, fh, ink, X(57), y)
                y += Y(20)
        if sub:
            fs = self.f(Y(20))
            for ln in self.wrap(fs, sub, right - X(80), max(1, (Y(186) - y) // Y(22))):
                self.tx(c, ln, fs, ink, X(57), y)
                y += Y(22)
        if picture:
            self.hole(c, self.page_video_box(None))

    def _panel(self, c, r):
        """The list panel is the frame's own."""

    def _col_header(self, c, y, word):
        b, X, Y = self.b, self.X, self.Y
        self.tx(c, self.fit(self.wb(Y(16)), word, X(180)), self.wb(Y(16)), b["navy"], X(80), y + Y(6))

    def _foot(self, c, text):
        self._hint(c, "SEL", text, self.X(58), self.Y(414))
        self._foot_clock(c)

    def _foot_clock(self, c):
        """The clock on the frame's dark tab at the foot's right."""
        b, X, Y = self.b, self.X, self.Y
        self.tx(c, datetime.now().strftime("%I:%M:%S%p").lstrip("0").lower(), self.wb(Y(16)), b["white"], X(466), Y(418))

    def _list_row(self, c, r, title, meta, on, f=None, fm=None):
        """A row of the list panel: the chosen one on the frame's navy pill
        (its arrows with it), the value in the right column."""
        b, X, Y = self.b, self.X, self.Y
        f, fm = f or self.f(Y(21)), fm or self.f(Y(19))
        if on:
            pill = self._sprite("pill.png")
            c.blit(pill, (X(60), r.y))
            if not meta:                            # nothing to step through: the arrows covered by the pill's body
                c.blit(pill, (X(266), r.y + Y(5)), pygame.Rect(X(100), Y(5), X(23), Y(16)))
        self.tx(c, self.fit(f, title, X(150)), f, b["white"], X(110), r.y + Y(6))
        if meta:
            self.tx(c, self.fit(fm, meta, X(330)), fm, b["white"] if on else b["panel_dim"], X(300), r.y + Y(7))

    def _button(self, c, r, label, on, f=None):
        b, Y = self.b, self.Y
        pygame.draw.rect(c, b["navy"] if on else b["lav"], r, border_radius=r.h // 2)
        f = f or self.fb(Y(15))
        self.tx(c, self.fit(f, label, r.w - Y(8)), f, b["white"], r.centerx, self.mid(r, f), align="center")

    def draw_menu(self, c, m):
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        cur = m.items[m.cursor] if 0 <= m.cursor < len(m.items) else None
        title = "Main Menu" if m.title == "MAIN MENU" else m.title.title()
        self._page_top(c, "General Settings" if title != "Main Menu" else "Main Menu", cur.help if cur and cur.help else "",
                       heading=f"{title}: {cur.label}" if cur else title)
        self._col_header(c, Y(192), title)
        n = len(m.items)
        n_vis = 6
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        for k, i in enumerate(range(first, min(n, first + n_vis))):
            it = m.items[i]
            r = pygame.Rect(X(60), Y(248) + k * Y(27), X(232), Y(26))
            v = it.value() if it.value else ""
            on = i == m.cursor
            self._list_row(c, r, it.label, v, on)
            if not it.enabled and not on:
                veil = pygame.Surface(r.size, pygame.SRCALPHA)
                veil.fill((*b["panel"], 120))
                c.blit(veil, r.topleft)
            self.hit(pygame.Rect(r.x, r.y, X(570), r.h), lambda i=i: m.activate(i))
        self._hint(c, "SEL", "Change" if cur and cur.adjust else "Select", X(58), Y(414))
        self._hint(c, "C", "Back" if len(getattr(m, "pages", [1])) > 1 else "Exit", X(220), Y(413))
        self._foot_clock(c)
        if n > n_vis:
            self.tx(c, f"{first + 1}-{min(n, first + n_vis)} of {n}", self.f(Y(17)), b["white"], X(624), Y(388), align="right")

    def _od_buttons(self, c, labels, focus, hits):
        letters = "ABC" if len(labels) <= 3 else [""] * len(labels)
        keys = [(letter, label, fn) for letter, label, fn in zip(letters, labels, hits or [None] * len(labels))]
        self._keybar(c, self.Y(403), keys, focus if 0 <= focus < len(keys) else None)

    def _rows(self, c, s, area, rows, sel, top, n_vis):
        """The list's rows, 37 apart between the frame's rules, the chosen
        one on the frame's teal band; the details in the teal panel."""
        b, X, Y = self.b, self.X, self.Y
        f = self.f(Y(21))
        rh = Y(37)
        for k, i in enumerate(range(top, min(len(rows), top + n_vis))):
            row = rows[i]
            r = pygame.Rect(area.x, area.y + k * rh, X(270), rh)
            on = i == sel
            if on:
                c.blit(self._sprite("od_sel.png"), (X(50), r.y))
            self.tx(c, self.fit(f, nice(row.get("title", "")), X(205)), f, b["white"] if on else b["navy"], X(95), r.y + Y(14))
            self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))
        cur = rows[sel] if 0 <= sel < len(rows) else None
        if cur:
            fd = self.f(Y(20))
            y = max(Y(283), area.y + (sel - top) * rh + rh + Y(8))    # under the band when the list's end pushes it lower
            for ln in [cur.get("meta", "")] + self.wrap(fd, cur.get("summary", "") or "", X(290), 3):
                if ln:
                    self.tx(c, self.fit(fd, ln, X(290)), fd, b["white"], X(335), y)
                    y += Y(24)
        fs = self.f(Y(17))
        if top + n_vis < len(rows):
            self.tx(c, "\u25bc", fs, b["navy"], X(300), area.bottom - Y(18))
        if top:
            self.tx(c, "\u25b2", fs, b["navy"], X(300), area.y - Y(12))

    def draw_ondemand(self, c, s):
        """On Demand on the DVR list frame (assets/skins/passage/od.png): the
        mark, the picture over the strip, the list panel, the details panel,
        the keys."""
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        rec = bool(s.level) and s.level.get("key") == "recordings"
        c.blit(self._sprite("od.png"), (0, 0))
        self._mark(c, X(59), Y(44))
        self.hole(c, self.page_video_box(s))
        live = self.app.live
        self._strip(c, live.channel if live else None, frame=True, top=Y(216))
        fh = self.wb(Y(16))
        head_word = "My Recordings" if rec else (s.crumb() if len(s.stack) > 1 else "On Demand")
        self.tx(c, self.fit(fh, head_word, X(250)), fh, b["navy"], X(60), Y(100))
        area = self.R(50, 125, 270, 275)
        if s.mode == "auth":
            fl = self.f(Y(21))
            y = area.y + Y(50)
            for line in ("On a phone or computer, go to", s.auth_link or "plex.tv/link", "and enter this code:"):
                self.tx(c, line, fl, b["navy"], area.centerx, y, align="center")
                y += Y(28)
            if s.auth_code:
                self.tx(c, s.auth_code, self.wb(Y(36)), b["navy"], area.centerx, y + Y(10), align="center")
            self._keybar(c, Y(403), [("C", "Cancel", s.back)], 0)
            return
        rows, n_vis = s.rows, self.ondemand_page(s)
        top = max(0, min(s.sel - 2, len(rows) - n_vis))     # the chosen row in the third slot, between the strip and the details, as the frame
        if s.view == "wall":
            self._wall(c, s, area.inflate(-X(10), -Y(10)))
        else:
            self._rows(c, s, pygame.Rect(X(50), Y(164), X(270), Y(222)), rows, s.sel, top, n_vis)
        side = self.od_side(s)
        self._od_buttons(c, [lab for lab, _ in side], -1 if s.side is None else s.side, [fn for _, fn in side])
        fs = self.f(Y(17))
        self.tx(c, f"{s.sel + 1} of {len(rows)}", fs, b["ink"], X(626), Y(458), align="right")
        if s.status:
            self.tx(c, self.fit(fs, s.status, X(300)), fs, b["ink"], X(50), Y(458))

    def od_side(self, s):
        if s.mode != "browse":
            return []
        rec = bool(s.level) and s.level.get("key") == "recordings"
        return [("Options", lambda: s.handle("MENU")),
                ("Sort", lambda: s.handle("MENU")) if rec else ("Saved", lambda: s.handle("LIST")),
                ("Done", s.back)]

    def draw_iteminfo(self, c, info):
        """An On Demand item on the More Information frame: the title and
        facts on the card, the poster and summary in the panel, the keys."""
        from ..screens.iteminfo import hms
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        d = info.detail
        c.blit(self._sprite("info.png"), (0, 0))
        self._picture(c)
        live = self.app.live
        self._strip(c, live.channel if live else None, frame=True)
        ink = mix(b["ink"], (0, 0, 0), 0.7)
        meta = d.get("subtitle") or d.get("meta", "")
        f_title, f_desc = self.f(Y(24)), self.f(Y(22))
        self.tx(c, self.fit(self.wb(Y(17)), "On Demand", X(240)), self.wb(Y(17)), ink, X(65), Y(52))
        for k, ln in enumerate(self.wrap(f_title, d.get("title", ""), X(245), 2)):
            self.tx(c, ln, f_title, ink, X(65), Y(80) + k * Y(26))
        facts = [x for x in (meta, f"Length {hms(d['duration'])}" if d.get("duration") else "",
                             f"Resume at {hms(d['offset'])}" if (d.get("offset") or 0) > 5 else "") if x]
        y = Y(136)
        for line in facts[:4]:
            self.tx(c, self.fit(f_desc, line, X(245)), f_desc, ink, X(65), y)
            y += Y(20)
        self.tx(c, "More Information", self.wb(Y(16)), b["navy"], X(346), Y(230), align="center")
        art_r = pygame.Rect(X(70), Y(258), X(84), Y(126))
        art = self.logo(d.get("poster", ""), art_r.w, art_r.h, headers=d.get("poster_headers") or None)
        x0 = X(78)
        if art:
            pygame.draw.rect(c, b["white"], art_r.inflate(X(4), Y(4)))
            c.blit(art, art.get_rect(center=art_r.center))
            x0 = art_r.right + X(16)
        fm = self.f(Y(21))
        y = Y(258)
        for line in self.wrap(fm, d.get("summary", "") or "No description available.", X(620) - x0, 5):
            self.tx(c, line, fm, b["navy"], x0, y)
            y += Y(24)
        names = info.buttons()
        words = [self.button_words(info.label(n)) for n in names]
        hits = [lambda k=k, n=n: (setattr(info, "focus", k), info.press(n)) for k, n in enumerate(names)]
        letters = "ABC" if len(words) <= 3 else [""] * len(words)
        self._keybar(c, Y(403), [(l, w, fn) for l, w, fn in zip(letters, words, hits)], info.focus if 0 <= info.focus < len(words) else None)

    def draw_diagnostics(self, c, d):
        b, X, Y = self.b, self.X, self.Y
        self._page_top(c, "General Settings", "Signal, picture and the software this box runs.", heading="System Information")
        self._col_header(c, Y(192), "System")
        f = self.f(Y(19))
        y = Y(226)
        rows = [("Signal strength", f"{d.signal()}"), ("Signal quality", f"{d.quality()}")] + d.rows()
        pitch = min(Y(21), (Y(180)) // max(1, len(rows)))
        for label, value in rows:
            self.tx(c, label, f, b["list_ink"], X(280), y, align="right")
            self.tx(c, self.fit(f, str(value), X(330)), f, b["white"], X(296), y)
            y += pitch
        from ..menus import open_button_guide
        self._hint(c, "A", "Help", X(58), Y(414))
        self.hit(self.R(56, 412, 90, 30), lambda: open_button_guide(self.app))
        self._hint(c, "C", "Exit", X(220), Y(413))
        self.hit(self.R(218, 412, 90, 30), lambda: d.handle("BACK"))
        self._foot_clock(c)

    def keyboard_rows(self, layer):
        """The frame's letter grid: NEW and BACK over six rows of six, space
        beneath; Done and Cancel are the keys along the foot."""
        return [["CLEAR", "DEL"], "ABCDEF", "GHIJKL", "MNOPQR", "STUVWX", "YZ1234", "567890", ["SPACE"], ["DONE", "CANCEL"]]

    def draw_keyboard(self, c, kb):
        """The Search frame (assets/skins/passage/search.png): the prompt on
        the card, the field on the bar, the letters in the wide bold on the
        lavender panel (the cursor a navy box), the tip in the results
        panel, Done and Cancel along the foot."""
        b, X, Y = self.b, self.X, self.Y
        c.blit(self._sprite("search.png"), (0, 0))
        self._picture(c)
        live = self.app.live
        self._strip(c, live.channel if live else None, frame=True)
        ink = mix(b["ink"], (0, 0, 0), 0.7)
        search = kb.prompt.lower().startswith("search")
        self.tx(c, "Search for Shows" if search else "Enter Text", self.wb(Y(17)), ink, X(65), Y(106))
        fp = self.f(Y(20))
        y = Y(130)
        for ln in self.wrap(fp, kb.prompt, X(245), 4):
            self.tx(c, ln, fp, ink, X(65), y)
            y += Y(22)
        ff = self.wb(Y(16))
        label = "Title:" if search else "Text:"
        lw = self.tx(c, label, ff, b["navy"], X(78), Y(230))
        shown = kb.value[:kb.caret]
        while shown and self.width(ff, shown) > X(300):
            shown = shown[1:]
        x = X(78) + lw + X(6)
        x += self.tx(c, shown, ff, b["movie"], x, Y(230))
        pygame.draw.rect(c, b["movie"], (x + X(2), Y(229), X(2), Y(16)))
        ft = self.f(Y(18))
        self.tx(c, self.fit(ft, kb.tip(), X(400)), ft, b["white"], X(215), Y(262))
        grid = kb.grid()
        fk = self.wb(Y(15))
        lav = (104, 104, 150)
        pitch = Y(19) if len(grid) <= 9 else Y(17)
        for r_, row in enumerate(grid):
            if r_ == len(grid) - 1:                 # Done and Cancel: the keys along the foot
                continue
            y = Y(262) + r_ * pitch
            for col, cell in enumerate(row):
                on = (r_, col) == (kb.row, kb.col)
                if cell in ("CLEAR", "DEL"):
                    word, cx = ("NEW", X(94)) if cell == "CLEAR" else ("BACK", X(162))
                    rect = pygame.Rect(cx - X(24), y - Y(2), X(48), Y(17))
                elif cell == "SPACE":
                    word, cx = "space", X(136)
                    rect = pygame.Rect(cx - X(24), y - Y(2), X(48), Y(17))
                else:
                    word, cx = cell.upper(), X(83 + 21 * col)
                    rect = pygame.Rect(cx - X(9), y - Y(2), X(18), Y(17))
                if on:
                    pygame.draw.rect(c, b["navy"], rect, border_radius=Y(2))
                self.tx(c, word, fk, b["white"] if on else lav, cx, y, align="center")
                self.hit(rect, lambda r_=r_, col=col, cell=cell: (setattr(kb, "row", r_), setattr(kb, "col", col), kb._press(cell)))
        last = kb.row == len(grid) - 1
        keys = [("A", "Done", lambda: kb._press("DONE")), ("C", "Cancel", lambda: kb._press("CANCEL"))]
        self._keybar(c, Y(403), keys, (0 if kb.col == 0 else 1) if last else None)

    def draw_playback(self, c, pb):
        """The banner's band with the title over the green line and its
        times; the transport keys as the key bar's chips."""
        from ..screens.iteminfo import hms
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        if pb.skip_label and self.on_top(pb):
            r = self.R(430, 300 if pb.bar_visible() else 400, 190, 26)
            self._button(c, r, f"{pb.skip_label.title()}  ({self.k('SELECT')})", True)
            self.hit(r, lambda: pb.handle("SELECT"))
        if not pb.bar_visible():
            return
        band = self.R(0, 367, 640, 70)
        self._band(c, band, b["cell"])
        tile = pygame.Rect(0, band.y, X(180), band.h)
        pygame.draw.rect(c, b["tile"], tile)
        f_state = self.fb(Y(16))
        self.tx(c, "Paused" if self.app.video.paused else "Playing", f_state, b["tile_ink"], tile.centerx, band.y + Y(10), align="center")
        self.tx(c, pb.subtitle or "", self.f(Y(14)), b["tile_ink"], tile.centerx, band.y + Y(36), align="center")
        f_title, f_small = self.fb(Y(18)), self.f(Y(15))
        q = self.app.ondemand.queue
        title = pb.title + (f"  ({q.pos + 1} of {len(q.items)})" if q.items and q.pos >= 0 else "")
        self.tx(c, self.fit(f_title, title, X(400)), f_title, b["white"], X(195), band.y + Y(5))
        line = pygame.Rect(X(240), band.y + Y(54), X(275), Y(7))
        pygame.draw.rect(c, b["track"], line, border_radius=Y(3))
        frac = min(1.0, pb.pos / pb.dur) if pb.dur else 0.0
        pygame.draw.rect(c, b["green"], (line.x, line.y, int(line.w * frac), line.h), border_radius=Y(3))
        self.tx(c, hms(pb.pos), f_small, b["white"], line.x - X(6), band.y + Y(46), align="right")
        self.tx(c, hms(pb.dur) if pb.dur else "--:--", f_small, b["white"], line.right + X(6), band.y + Y(46))
        pygame.draw.circle(c, b["white"], (line.x + int(line.w * frac), line.centery), Y(4))
        self.hit(line.inflate(0, Y(16)), lambda: pb.seek_to(self._click_frac(line)))
        rects = []
        for k, (kind, _, fn) in enumerate(pb.transport()):
            br = pygame.Rect(X(195) + k * X(72), band.y + Y(27), X(64), Y(18))
            self._tbtn(c, br, kind, k == getattr(pb, "tfocus", None))
            self.hit(br, fn)
            rects.append(br)
        self.idle_row(c, pb, rects, Y(9))

    def _tbtn(self, c, r, kind, on, num=None):
        b = self.b
        pygame.draw.rect(c, b["navy"] if on else b["tab"], r, border_radius=r.h // 2)
        self.transport_face(c, kind, r, b["white"], self.fb(self.Y(11)), num=num)

    def _trick(self, c, s):
        b, X, Y = self.b, self.X, self.Y
        band = self.R(0, 400, 640, 40)
        self.live_buttons(c, s, X(195), band.y - Y(30), X(72), Y(22), X(8))
        self._band(c, band, b["cell"])
        tile = pygame.Rect(0, band.y, X(180), band.h)
        pygame.draw.rect(c, b["tile"], tile)
        behind = s["behind"]
        mm, ss = divmod(int(behind), 60)
        f = self.fb(Y(16))
        self.tx(c, "Paused" if s["paused"] else ("Live" if behind < 2 else "Playing"), f, b["tile_ink"], tile.centerx, self.mid(tile, f), align="center")
        line = pygame.Rect(X(240), band.y + Y(17), X(275), Y(7))
        pygame.draw.rect(c, b["track"], line, border_radius=Y(3))
        total = s["buffer"] + behind
        if total >= 2:
            x = line.x + int(line.w * s["buffer"] / total)
            pygame.draw.rect(c, b["green"], (line.x, line.y, x - line.x, line.h), border_radius=Y(3))
            pygame.draw.circle(c, b["white"], (x, line.centery), Y(4))
        self.tx(c, f"-{mm}:{ss:02d}" if behind >= 1 else "Live", self.f(Y(15)), b["white"], line.right + X(8), band.y + Y(10))

    def draw_screensaver(self, c, ss):
        """The frame's mark on its light box, drifting on black."""
        W, H = self.canvas
        c.fill((0, 0, 0, 255))
        box = self._sprite("markbox.png")
        x, y = ss.position(box.get_width(), box.get_height(), W, H)
        c.blit(box, (x, y))
        self._mark(c, x + self.X(59), y + self.Y(2))

    def _boot_page(self, c):
        W, H = self.canvas
        self._page(c, (0, 0, W, H))

    def draw_boot(self, c, boot):
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        scene, age = boot.scene(), boot.scene_age()
        self._boot_page(c)
        size = Y(30)
        mw = self.measure(self.wordmark, size)
        self.wordmark(c, (W - mw) // 2, Y(150), size)
        if scene == "logo":
            return
        g = getattr(self.app, "guide_progress", None)
        r = self._dialog(c, "Please Wait", [self.BOOT_WORDS[1], "Press any button to skip."], hints=[("C", "Skip")])
        bar = pygame.Rect(r.x + X(40), r.bottom - Y(60), r.w - X(80), Y(10))
        if g is not None and g >= 0:
            self.progress(c, bar, max(g, min(1.0, age / 3.0)), b["track"], b["green"])
        else:
            pygame.draw.rect(c, b["track"], bar, border_radius=Y(5))
            k = (time.monotonic() * 0.6) % 1.0
            w = bar.w // 4
            x = bar.x + int((bar.w - w) * (k if int(time.monotonic() * 0.6) % 2 == 0 else 1 - k))
            pygame.draw.rect(c, b["green"], (x, bar.y, w, bar.h), border_radius=Y(5))
            self._next_frame(0.05)


def call(ch, n=5) -> str:
    """The box's call sign: the name's letters, cut at n."""
    return "".join(ch.name.upper().split())[:n]


class Wayfinder(CableSkin):
    """Wayfinder: the 2010 Time Warner guide, blue on blue, to frames of the
    real box (640x480)."""
    name = "wayfinder"
    label = "Wayfinder"
    MARK, MARK_TAG = "Wayfinder", "TIME WANDER CABLE"
    NO_SIGNAL = ("Channel Unavailable", "This channel is temporarily unavailable.", "Please try again in a few minutes.")
    BOOT_WORDS = ("Starting...", "Loading channel listings...")
    ROWS, ROW_PITCH = 5, 37
    LIST = (40, 232, 600, 190)
    OD_ROWS = 5
    # Measured: the steel page, the royal cell, the gold cursor, the navy tile.
    NATIVE = {"bg": [178, 196, 222], "accent": [35, 75, 165], "accent2": [235, 190, 60],
              "text": [255, 255, 255], "chnum": [25, 50, 130]}
    LEGIBLE = [("text", ["cell", "navy", "hdr", "band", "panel", "row"], "ground"), ("sel_ink", ["sel"], "ink"),
               ("card_ink", ["card"], "ink"), ("foot_ink", ["page", "foot"], "ink")]

    def theme_base(self, base):
        bg, acc, text = base["bg"], base["accent"], base["text"]
        return dict(base, bg=mix(text, acc, 0.35), accent=mix(acc, bg, 0.4), chnum=mix(acc, bg, 0.7))

    def roles(self, b):
        page, cell, gold, text, navy = b["bg"], b["accent"], b["accent2"], b["text"], b["chnum"]
        white = (255, 255, 255)
        return {
            "page": page, "page_lo": mix(page, white, 0.4), "cell": cell, "cell_hi": mix(cell, white, 0.12),
            "navy": navy, "hdr": mix(navy, (0, 0, 0), 0.2), "sel": gold, "sel_ink": readable(gold, (20, 30, 60)),
            "text": text, "card": white, "card_ink": mix(navy, (0, 0, 0), 0.2), "gap": mix(navy, (0, 0, 0), 0.4),
            "band": navy, "band_ink": text, "track": mix(page, (0, 0, 0), 0.2), "now_line": gold,
            "foot": mix(page, white, 0.3), "foot_ink": mix(navy, (0, 0, 0), 0.2), "red": (220, 30, 40),
            "panel": mix(cell, navy, 0.5), "panel_ink": text, "panel_dim": mix(text, cell, 0.35),
            "row": cell, "row_ink": text, "btn": navy, "btn_ink": text, "field": white, "field_ink": mix(navy, (0, 0, 0), 0.2),
            "dlg": white, "dlg_edge": navy, "dlg_head": navy, "dlg_head_ink": text, "dlg_ink": mix(navy, (0, 0, 0), 0.2),
            "boot_ink": mix(navy, (0, 0, 0), 0.2), "key_a": (240, 200, 30), "key_b": (40, 90, 200),
        }

    def wordmark(self, c, x, y, size, ink=None):
        """An eye in a ring, 'Wayfinder' bold, the tag small under it."""
        b, t = self.b, self.text
        ink = ink or b["card_ink"]
        f = self.fb(size)
        h = t.ink(f)[1]
        r = max(3, int(h * 0.42))
        pygame.draw.circle(c, ink, (x + r, y + h // 2), r, max(1, size // 10))
        pygame.draw.circle(c, ink, (x + r, y + h // 2), max(1, r // 3))
        w = t.draw(c, self.MARK, f, ink, x + 2 * r + size // 5, y)
        if self.MARK_TAG:
            fs = self.f(max(7, int(size * 0.38)))
            t.draw(c, self.MARK_TAG, fs, ink, x + 2 * r + size // 5, y + h + 1)
        return 2 * r + size // 5 + w

    def _page(self, c, rect):
        if self.hold_backdrop(rect, self._page):
            return
        vgrad(c, rect, rgba(self.b["page"]), rgba(self.b["page_lo"]))

    def guide_video_box(self):
        r = self.R(320, 0, 320, 206)
        return (r.x, r.y, r.w, r.h)

    def _chan_band(self, c, r, ch):
        """The channel's logo and name on a blue band."""
        b, X, Y = self.b, self.X, self.Y
        pygame.draw.rect(c, b["cell"], r, border_top_left_radius=Y(6), border_top_right_radius=Y(6))
        logo = self.channel_logo(ch, X(48), Y(28)) if ch else None
        x = r.x + X(10)
        if logo:
            tile = pygame.Rect(x, r.y + Y(5), X(50), Y(30))
            pygame.draw.rect(c, (255, 255, 255), tile, border_radius=Y(3))
            c.blit(logo, logo.get_rect(center=tile.center))
            x = tile.right + X(10)
        f = self.fb(Y(16))
        if ch:
            self.tx(c, self.fit(f, f"{ch.name}  {ch.number}", r.right - X(8) - x), f, b["text"], x, self.mid(r, f))

    def _strip(self, c, ch):
        b, X, Y = self.b, self.X, self.Y
        vx, vy, vw, vh = self.guide_video_box()
        strip = pygame.Rect(vx, vy + vh, vw, Y(18))
        pygame.draw.rect(c, b["navy"], strip)
        f = self.fb(Y(13))
        if ch:
            self.tx(c, self.fit(f, f"{''.join(ch.name.upper().split())[:5]} • {ch.number}", X(170)), f, b["text"], strip.x + X(10), self.mid(strip, f))
        self.tx(c, ampm(datetime.now(), True), f, b["text"], strip.right - X(10), self.mid(strip, f), align="right")

    def _foot_bar(self, c, keys, active=None):
        """The foot: the mark, the A / B keys and their words, the red tile."""
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        foot = pygame.Rect(0, Y(432), W, H - Y(432))
        pygame.draw.rect(c, b["foot"], foot)
        self.wordmark(c, X(24), Y(443), Y(13))
        f = self.fb(Y(13))
        for k, (letter, word, fn) in enumerate(keys):
            x = X(250 + k * 150)
            cy = Y(452)
            r = pygame.Rect(x - X(6), cy - Y(12), X(140), Y(24))
            if active == k:
                pygame.draw.rect(c, b["navy"], r, border_radius=Y(4))
            if letter == "A":
                pygame.draw.polygon(c, b["key_a"], [(x, cy + Y(7)), (x + X(16), cy + Y(7)), (x + X(8), cy - Y(7))])
            else:
                pygame.draw.rect(c, b["key_b"], (x, cy - Y(7), X(16), Y(14)), border_radius=Y(2))
            self.tx(c, letter, self.fb(Y(10)), (20, 20, 20) if letter == "A" else b["text"], x + X(8), cy - Y(5), align="center")
            self.tx(c, self.fit(f, word.upper(), X(110)), f, b["text"] if active == k else b["foot_ink"], x + X(24), cy - Y(7))
            if fn:
                self.hit(r, fn)
        tile = pygame.Rect(W - X(50), Y(440), X(32), Y(26))
        pygame.draw.rect(c, b["red"], tile, border_radius=Y(3))
        ft = self.fb(Y(9))
        self.tx(c, "TV", ft, (255, 255, 255), tile.centerx, tile.y + Y(3), align="center")
        self.tx(c, "GUIDE", ft, (255, 255, 255), tile.centerx, tile.y + Y(13), align="center")

    def draw_guide(self, c, g):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self._page(c, (0, 0, W, H))
        self._picture(c)
        sel, cur = g.selected(), g.selected_program()
        self._strip(c, sel)
        self._chan_band(c, self.R(40, 22, 268, 40), sel)
        card = self.R(40, 62, 268, 150)
        drop = pygame.Surface((card.w, card.h), pygame.SRCALPHA)
        pygame.draw.rect(drop, (0, 0, 0, 60), drop.get_rect(), border_bottom_left_radius=Y(6), border_bottom_right_radius=Y(6))
        c.blit(drop, (card.x + Y(3), card.y + Y(4)))
        pygame.draw.rect(c, b["card"], card, border_bottom_left_radius=Y(6), border_bottom_right_radius=Y(6))
        f_title, f_line, f_desc = self.fb(Y(16)), self.fb(Y(14)), self.f(Y(14))
        title = cur.title if cur else (sel.name if sel else "")
        self.tx(c, self.fit(f_title, title, card.w - X(20)), f_title, b["card_ink"], card.x + X(10), card.y + Y(8))
        if cur:
            line = (f"{cur.rating}  " if cur.rating else "") + f"{ampm(cur.start, True)} - {ampm(cur.stop, True)}"
            self.tx(c, line, f_line, b["card_ink"], card.x + X(10), card.y + Y(30))
            y = card.y + Y(52)
            for ln in self.wrap(f_desc, cur.description or "", card.w - X(20), 5):
                self.tx(c, ln, f_desc, b["card_ink"], card.x + X(10), y)
                y += Y(18)
        elif sel:
            self.tx(c, "No information available.", f_line, b["card_ink"], card.x + X(10), card.y + Y(30))
        hdr = self.R(40, 232, 600, 22)
        pygame.draw.rect(c, b["hdr"], hdr)
        fh = self.fb(Y(15))
        grid_x, grid_w = X(152), X(488)
        self._time_header(c, g, hdr, grid_x, grid_w, fh, b["text"], mix(b["hdr"], b["text"], 0.35), X(48),
                          space=True, day_fmt="{A} {m}/{d}")
        pygame.draw.polygon(c, b["text"], [(W - X(8), hdr.centery), (W - X(14), hdr.centery - Y(5)), (W - X(14), hdr.centery + Y(5))])
        top, pitch, rh = Y(258), Y(37), Y(34)
        pygame.draw.rect(c, b["hdr"], (X(40), hdr.bottom, W - X(40), g.rows * pitch))    # navy between the cells

        def tile(cc, r, ch, on):
            r = pygame.Rect(X(40), r.y, X(110), r.h)
            pygame.draw.rect(cc, b["navy"], r)
            self.tx(cc, self.fit(fh, "".join(ch.name.upper().split())[:6], X(70)), fh, b["text"], r.x + X(6), self.mid(r, fh))
            self.tx(cc, str(ch.number), fh, b["text"], r.right - X(6), self.mid(r, fh), align="right")
            if self.app.is_favorite(ch):
                pygame.draw.circle(cc, b["sel"], (r.x + X(6), r.y + Y(6)), Y(3))

        def cell(cc, r, airing, on, i, p):
            pygame.draw.rect(cc, b["sel"] if on else b["cell_hi"] if airing else b["cell"], r)
        self._grid(c, g, grid_x, grid_w, top, pitch, rh, X(2), 15, tile, cell, lambda on: b["sel_ink"] if on else b["text"])
        name = g.category if g.category != "All" else "All Channels"
        self._foot_bar(c, [("A", name if g.focus != "category" else f"< {name} >", lambda: g.handle("THEMES")),
                           ("B", "Find shows", None)], 0 if g.focus == "category" else None)

    # ── Live: the strip over a white card ─────────────────────────────────

    def _banner(self, c, ch, cur, nxt, full=False, tag=None):
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        strip = self.R(40, 386, 560, 22)
        card = self.R(40, 408, 560, 60)
        self._band(c, strip, b["navy"], 235, radius=Y(6), border_bottom_left_radius=0, border_bottom_right_radius=0)
        self._band(c, card, b["card"], 240, radius=Y(8), border_top_left_radius=0, border_top_right_radius=0)
        f_strip, f_title, f_line = self.fb(Y(13)), self.fb(Y(17)), self.f(Y(14))
        self.tx(c, ampm(datetime.now(), True), f_strip, b["text"], strip.x + X(10), self.mid(strip, f_strip))
        self.tx(c, self.fit(f_strip, f"{ch.number} • {ch.name}", X(300)), f_strip, b["text"], strip.x + X(100), self.mid(strip, f_strip))
        logo = self.channel_logo(ch, X(70), Y(44))
        x0 = card.x + X(12)
        if logo:
            tile = pygame.Rect(x0, card.y + Y(8), X(74), Y(44))
            pygame.draw.rect(c, mix(b["card"], b["card_ink"], 0.08), tile, border_radius=Y(3))
            c.blit(logo, logo.get_rect(center=tile.center))
            x0 = tile.right + X(12)
        self.tx(c, self.fit(f_title, cur.title if cur else ch.name, card.right - X(90) - x0), f_title, b["card_ink"], x0, card.y + Y(6))
        if cur:
            self.tx(c, f"{ampm(cur.start, True)} - {ampm(cur.stop, True)}", f_line, b["card_ink"], card.right - X(12), card.y + Y(8), align="right")
            lead = f"{cur.rating}  " if cur.rating else ""
            y = card.y + Y(28)
            for ln in self.wrap(f_line, lead + (cur.description or ""), card.right - X(12) - x0, 2):
                self.tx(c, ln, f_line, b["card_ink"], x0, y)
                y += Y(16)
        else:
            self.tx(c, "No information available", f_line, b["card_ink"], x0, card.y + Y(28))
        hint = tag or (f"{self.k('INFO')} for more" if not full else "")
        if hint:
            self.tx(c, hint, f_strip, b["sel"], strip.right - X(10), self.mid(strip, f_strip), align="right")
        if full and cur and nxt:
            d = pygame.Rect(card.x, strip.y - Y(22), card.w, Y(20))
            self._band(c, d, b["cell"], 235, radius=Y(6), border_bottom_left_radius=0, border_bottom_right_radius=0)
            self.tx(c, self.fit(f_strip, f"Next: {nxt.title}  {ampm(nxt.start, True)}", d.w - X(20)), f_strip, b["text"], d.x + X(10), self.mid(d, f_strip))
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def draw_browse(self, c, br):
        if br.channel:
            cur, nxt = br.program()
            self._banner(c, br.channel, cur, nxt, tag=f"Browse: {self.k('SELECT')} to watch" + (f"  (+{br.ahead})" if br.ahead else ""))

    # ── Pages ─────────────────────────────────────────────────────────────

    def menu_video_box(self, menu):
        return self.guide_video_box()

    def _page_top(self, c, title, sub="", picture=True):
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        self._page(c, (0, 0, W, H))
        band = self.R(40, 22, 268 if picture else 560, 40)
        pygame.draw.rect(c, b["cell"], band, border_top_left_radius=Y(6), border_top_right_radius=Y(6))
        f = self.fb(Y(17))
        self.tx(c, self.fit(f, title, band.w - X(20)), f, b["text"], band.x + X(10), self.mid(band, f))
        card = pygame.Rect(band.x, band.bottom, band.w, Y(150) if picture else Y(60))
        pygame.draw.rect(c, b["card"], card, border_bottom_left_radius=Y(6), border_bottom_right_radius=Y(6))
        if sub:
            fs = self.f(Y(14))
            y = card.y + Y(8)
            for ln in self.wrap(fs, sub, card.w - X(20), 6 if picture else 2):
                self.tx(c, ln, fs, b["card_ink"], card.x + X(10), y)
                y += Y(18)
        if picture:
            self._picture(c)
            live = self.app.live
            self._strip(c, live.channel if live else None)
        self._foot_bar(c, [])

    def _panel(self, c, r):
        pygame.draw.rect(c, self.b["panel"], r, border_radius=self.Y(4))

    def _list_row(self, c, r, title, meta, on, f=None, fm=None):
        b, X, Y = self.b, self.X, self.Y
        pygame.draw.rect(c, b["sel"] if on else b["cell"], r)
        f, fm = f or self.fb(Y(15)), fm or self.f(Y(13))
        ink = b["sel_ink"] if on else b["text"]
        mw = self.width(fm, meta) + X(12) if meta else 0
        self.tx(c, self.fit(f, title, r.w - mw - X(16)), f, ink, r.x + X(8), self.mid(r, f))
        if meta:
            self.tx(c, meta, fm, ink, r.right - X(8), self.mid(r, fm), align="right")

    def _button(self, c, r, label, on, f=None):
        b, Y = self.b, self.Y
        pygame.draw.rect(c, b["sel"] if on else b["navy"], r, border_radius=Y(4))
        f = f or self.fb(Y(14))
        self.tx(c, self.fit(f, label, r.w - Y(8)), f, b["sel_ink"] if on else b["text"], r.centerx, self.mid(r, f), align="center")

    def draw_menu(self, c, m):
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        it = m.items[m.cursor] if 0 <= m.cursor < len(m.items) else None
        self._page_top(c, "Main Menu" if m.title == "MAIN MENU" else m.title.title(), it.help if it and it.help else "")
        area = self.R(40, 232, 600, 190)
        n = len(m.items)
        rh = Y(32)
        n_vis = 6
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        f = self.fb(Y(15))
        for k, i in enumerate(range(first, min(n, first + n_vis))):
            it = m.items[i]
            r = pygame.Rect(area.x, area.y + k * rh, area.w, rh - Y(3))
            v = it.value() if it.value else (">" if it.submenu else "")
            v = f"< {v} >" if i == m.cursor and it.adjust else v
            self._list_row(c, r, it.label, v, i == m.cursor, f=f)
            if not it.enabled and i != m.cursor:
                veil = pygame.Surface(r.size, pygame.SRCALPHA)
                veil.fill((*b["page"], 120))
                c.blit(veil, r.topleft)
            self.hit(r, lambda i=i: m.activate(i))
        if n > n_vis:
            self.tx(c, f"{first + 1}-{min(n, first + n_vis)} of {n}", self.f(Y(11)), b["foot_ink"], X(560), Y(446), align="right")
        self._foot_bar(c, [("A", "Select", lambda: m.activate()), ("B", "Back", lambda: m.back())])

    def _foot(self, c, text):
        b, X, Y = self.b, self.X, self.Y
        f = self.f(Y(12))
        self.tx(c, self.fit(f, text, X(330)), f, b["foot_ink"], X(250), Y(445))


class Y1(CableSkin):
    """Y1: the 2014 Comcast box, to its own guide frames (16:9). Everything
    over the dimmed picture, a light face, blue for the chosen."""
    name = "y1"
    label = "Y1"
    canvas = (1280, 720)
    SD = False
    MARK, MARK_TAG = "y1", ""
    default_font = "barlow"
    guide_hours = 2.5
    NO_SIGNAL = ("Something's not right", "We're having trouble playing this channel.", "Code: XRE-03007")
    BOOT_WORDS = ("Welcome", "Getting your channels ready...")
    ATTENTION = "Sorry"
    ROWS, ROW_PITCH = 5, 48
    LIST = (20, 110, 600, 290)
    OD_ROWS = 7
    WALL = (6, 2)
    NATIVE = {"bg": [12, 12, 14], "accent": [38, 38, 42], "accent2": [80, 160, 230],
              "text": [240, 240, 244], "chnum": [26, 26, 30]}
    LEGIBLE = [("text", ["page", "cell", "cell_on", "tile", "panel", "row", "band"], "ground"), ("blue", ["cell_on", "page"], "ink"),
               ("soft", ["page", "cell", "panel"], "ink")]

    def theme_base(self, base):
        bg, acc, text = base["bg"], base["accent"], base["text"]
        return dict(base, accent=mix(bg, text, 0.12), chnum=mix(bg, text, 0.06))

    def roles(self, b):
        page, cell, blue, text, tile = b["bg"], b["accent"], b["accent2"], b["text"], b["chnum"]
        return {
            "page": page, "cell": cell, "cell_on": mix(cell, (255, 255, 255), 0.14), "blue": blue, "text": text,
            "soft": mix(text, page, 0.35), "muted": mix(text, page, 0.55), "tile": tile, "panel": mix(page, (255, 255, 255), 0.04),
            "panel_ink": text, "panel_dim": mix(text, page, 0.4), "orange": (235, 120, 20), "rule": mix(page, text, 0.25),
            "sel": blue, "sel_ink": readable(blue, (10, 10, 12)), "gap": (0, 0, 0), "now_line": blue,
            "band": mix(page, (0, 0, 0), 0.3), "band_ink": text, "track": mix(page, text, 0.25),
            "row": mix(page, (255, 255, 255), 0.02), "row_ink": text, "btn": cell, "btn_ink": text,
            "field": mix(page, (255, 255, 255), 0.08), "field_ink": text, "foot_ink": mix(text, page, 0.35),
            "dlg": mix(page, (255, 255, 255), 0.06), "dlg_edge": mix(page, text, 0.25), "dlg_head": mix(page, (255, 255, 255), 0.06),
            "dlg_head_ink": text, "dlg_ink": text, "boot_ink": mix(text, page, 0.3),
        }

    def wordmark(self, c, x, y, size, ink=None):
        b, t = self.b, self.text
        f = self.f(size)
        return t.draw(c, self.MARK, f, ink or b["text"], x, y)

    # The picture stays full behind every page, dimmed.
    def guide_video_box(self):
        return "full"

    def page_video_box(self, screen):
        return "full"

    def menu_video_box(self, menu):
        return "full"

    def _crumb(self, c, first, second="", clock=True):
        """'Guide / TV Listings' top-left, the clock top-right."""
        b, X, Y = self.b, self.X, self.Y
        f = self.f(Y(13))
        w = self.tx(c, first, f, b["text"], X(20), Y(14))
        if second:
            self.tx(c, " / ", f, b["soft"], X(20) + w, Y(14))
            self.tx(c, second, f, b["blue"], X(20) + w + self.width(f, " / "), Y(14))
        if clock:
            self.tx(c, short(datetime.now()), f, b["text"], X(620), Y(14), align="right")

    def _light(self, c, s, size, ink, x, y, align="left"):
        return self.tx(c, s, self.f(self.Y(size)), ink, x, y, align=align)

    def draw_guide(self, c, g):
        W, H = self.canvas
        b, t, X, Y = self.b, self.text, self.X, self.Y
        self.dim(c, 215)
        name = g.category if g.category != "All" else "All Channels"
        self._crumb(c, "Guide", name)
        f_pill = self.fb(Y(10))
        pill = pygame.Rect(X(250), Y(12), X(60), Y(18))
        pygame.draw.rect(c, b["sel"] if g.focus == "category" else b["cell_on"], pill, border_radius=Y(3))
        self.tx(c, "LISTS", f_pill, b["sel_ink"] if g.focus == "category" else b["text"], pill.centerx, self.mid(pill, f_pill), align="center")
        self.hit(pill, lambda: g.handle("THEMES"))
        self._light(c, "Change View", 11, b["soft"], pill.right + X(8), Y(15))
        hdr = self.R(0, 42, 640, 20)
        fh = self.f(Y(12))
        grid_x, grid_w = X(98), X(542)
        self._time_header(c, g, hdr, grid_x, grid_w, fh, b["soft"], None, X(20), day_fmt="Today {m}/{d}")
        top, pitch, rh = Y(66), Y(48), Y(44)
        pygame.draw.rect(c, (0, 0, 0), (0, top - Y(2), W, g.rows * pitch))               # black between the cells

        def tile(cc, r, ch, on):
            r = pygame.Rect(0, r.y, X(96), r.h)
            pygame.draw.rect(cc, b["tile"], r)
            logo = self.channel_logo(ch, X(44), Y(30))
            if logo:
                cc.blit(logo, logo.get_rect(center=(r.x + X(28), r.centery)))
            else:
                fc = self.fb(Y(10))
                self.tx(cc, self.fit(fc, "".join(ch.name.upper().split())[:6], X(48)), fc, b["soft"], r.x + X(28), self.mid(r, fc), align="center")
            fn = self.f(Y(13))
            self.tx(cc, str(ch.number), fn, b["text"], r.right - X(6), self.mid(r, fn), align="right")
            if self.app.is_favorite(ch):
                pygame.draw.circle(cc, b["blue"], (r.x + X(4), r.y + Y(5)), Y(2))

        def cell(cc, r, airing, on, i, p):
            pygame.draw.rect(cc, b["cell_on"] if on else b["cell"], r)
            if on:
                pygame.draw.rect(cc, b["text"], (r.x, r.y, r.w, Y(2)))
        self._grid(c, g, grid_x, grid_w, top, pitch, rh, X(2), 14, tile, cell, lambda on: b["blue"] if on else b["text"])
        # The programme in the panel along the foot.
        sel, cur = g.selected(), g.selected_program()
        panel = self.R(0, 316, 640, 164)
        pygame.draw.rect(c, b["panel"], panel)
        logo = self.channel_logo(sel, X(70), Y(40)) if sel else None
        tile_r = pygame.Rect(panel.x + X(20), panel.y + Y(18), X(80), Y(50))
        pygame.draw.rect(c, b["tile"], tile_r)
        if logo:
            c.blit(logo, logo.get_rect(center=tile_r.center))
        x0 = tile_r.right + X(16)
        title = cur.title if cur else (sel.name if sel else "")
        self._light(c, self.fit(self.f(Y(19)), title, X(360)), 19, b["text"], x0, panel.y + Y(16))
        if cur:
            y = panel.y + Y(44)
            for ln in self.wrap(self.f(Y(12)), cur.description or "", X(360), 3):
                self._light(c, ln, 12, b["soft"], x0, y)
                y += Y(16)
            rx = panel.right - X(20)
            self._light(c, f"{short(cur.start)} - {short(cur.stop)}", 12, b["text"], rx, panel.y + Y(18), align="right")
            if sel:
                self._light(c, f"{sel.number} {''.join(sel.name.upper().split())[:6]}", 12, b["soft"], rx, panel.y + Y(36), align="right")
            if cur.rating:
                chip = pygame.Rect(0, panel.y + Y(56), X(30), Y(14))
                chip.right = rx
                pygame.draw.rect(c, b["text"], chip, 1)
                fr = self.fb(Y(8))
                self.tx(c, cur.rating, fr, b["text"], chip.centerx, self.mid(chip, fr), align="center")
        elif sel:
            self._light(c, "No information available.", 12, b["soft"], x0, panel.y + Y(44))
        self._light(c, self.guide_keys(), 10, b["muted"], panel.centerx, panel.bottom - Y(18), align="center")

    # ── Live: the lower third ─────────────────────────────────────────────

    def _banner(self, c, ch, cur, nxt, full=False, tag=None):
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        r = self.R(0, 380, 640, 100)
        vgrad(c, r, rgba(b["band"], 0), rgba(b["band"], 235))
        pygame.draw.rect(c, rgba(b["band"], 235), (0, r.y + Y(40), W, H - r.y - Y(40)))
        tile_r = pygame.Rect(X(20), Y(420), X(70), Y(42))
        pygame.draw.rect(c, b["tile"], tile_r)
        logo = self.channel_logo(ch, X(60), Y(34))
        if logo:
            c.blit(logo, logo.get_rect(center=tile_r.center))
        x0 = tile_r.right + X(14)
        self._light(c, self.fit(self.f(Y(19)), cur.title if cur else ch.name, X(380)), 19, b["text"], x0, Y(416))
        line = (f"{short(cur.start)} - {short(cur.stop)}" + (f"   {cur.rating}" if cur.rating else "")) if cur else "No information"
        self._light(c, line, 12, b["soft"], x0, Y(442))
        self._light(c, f"{ch.number}  {''.join(ch.name.upper().split())[:8]}", 12, b["text"], X(620), Y(416), align="right")
        self._light(c, short(datetime.now()), 12, b["soft"], X(620), Y(442), align="right")
        if cur:
            now = datetime.now(timezone.utc)
            frac = max(0.0, min(1.0, (now - cur.start).total_seconds() / max(1, (cur.stop - cur.start).total_seconds())))
            bar = pygame.Rect(x0, Y(462), X(380), Y(3))
            pygame.draw.rect(c, b["track"], bar)
            pygame.draw.rect(c, b["blue"], (bar.x, bar.y, int(bar.w * frac), bar.h))
        hint = tag or (f"{self.k('INFO')} for details" if not full else "")
        if hint:
            self._light(c, hint, 10, b["muted"], X(620), Y(464), align="right")
        if full and cur and (cur.description or nxt):
            lines = self.wrap(self.f(Y(12)), cur.description or "", X(600), 3) + ([f"Next: {nxt.title}  {short(nxt.start)}"] if nxt else [])
            d = pygame.Rect(0, 0, W, Y(10) + len(lines) * Y(16))
            d.bottom = Y(410)
            pygame.draw.rect(c, rgba(b["band"], 235), d)
            y = d.y + Y(5)
            for ln in lines:
                self._light(c, ln, 12, b["soft"], X(20), y)
                y += Y(16)
        if self._tick is None or self._tick[0] <= time.monotonic():
            self._tick = self.app.after(60 - time.time() % 60, self.app.invalidate)

    def draw_browse(self, c, br):
        if br.channel:
            cur, nxt = br.program()
            self._banner(c, br.channel, cur, nxt, tag=f"Browse: {self.k('SELECT')} to watch" + (f"  (+{br.ahead})" if br.ahead else ""))

    # ── Menus: the row of words; lists for the rest ───────────────────────

    def _is_bar(self, m) -> bool:
        return m.title == "MAIN MENU" and len(getattr(m, "pages", [1])) == 1

    def menu_cols(self, menu):
        return max(1, len(menu.items)) if self._is_bar(menu) else 1

    def menu_rows(self, menu):
        return 1 if self._is_bar(menu) else super().menu_rows(menu)

    def _underline(self, c, r, on, f, label, ink):
        self.tx(c, label, f, ink, r.x, r.y)
        if on:
            w = self.width(f, label)
            pygame.draw.rect(c, self.b["blue"], (r.x, r.y + self.text.ink(f)[1] + self.Y(4), w, self.Y(2)))

    def draw_menu(self, c, m):
        W, H = self.canvas
        b, X, Y = self.b, self.X, self.Y
        self.dim(c, 170)
        if self._is_bar(m):
            self.wordmark(c, X(20), Y(252), Y(22))
            f = self.f(Y(20))
            x, y = X(20), Y(290)
            for i, it in enumerate(m.items):
                w = self.width(f, it.label)
                if x + w > X(620):
                    break
                r = pygame.Rect(x, y, w, Y(26))
                on = i == m.cursor
                self._underline(c, r, on, f, it.label, b["text"] if on else b["soft"])
                self.hit(r, lambda i=i: m.activate(i))
                x += w + X(24)
            it = m.items[m.cursor] if 0 <= m.cursor < len(m.items) else None
            if it and it.help:
                self._light(c, self.fit(self.f(Y(12)), it.help, X(600)), 12, b["soft"], X(20), Y(330))
            return
        self._crumb(c, "Menu", m.title.title())
        n = len(m.items)
        rh = Y(30)
        n_vis = 10
        first = max(0, min(m.cursor - n_vis + 1, n - n_vis)) if n > n_vis else 0
        f = self.f(Y(14))
        for k, i in enumerate(range(first, min(n, first + n_vis))):
            it = m.items[i]
            r = pygame.Rect(X(20), Y(50) + k * rh, X(600), rh - Y(2))
            on = i == m.cursor
            v = it.value() if it.value else (">" if it.submenu else "")
            v = f"< {v} >" if on and it.adjust else v
            self._list_row(c, r, it.label, v, on, f=f)
            if not it.enabled and not on:
                veil = pygame.Surface(r.size, pygame.SRCALPHA)
                veil.fill((0, 0, 0, 120))
                c.blit(veil, r.topleft)
            self.hit(r, lambda i=i: m.activate(i))
        it = m.items[m.cursor] if 0 <= m.cursor < n else None
        if it and it.help:
            self._light(c, self.fit(self.f(Y(12)), it.help, X(600)), 12, b["soft"], X(20), Y(400))
        if n > n_vis:
            self._light(c, f"{first + 1}-{min(n, first + n_vis)} of {n}", 11, b["muted"], X(620), Y(458), align="right")
        self._foot(c, f"{self.k('SELECT')}: choose   {self.k('BACK')}: back   {self.k('EXIT')}: close")

    def _list_row(self, c, r, title, meta, on, f=None, fm=None):
        b, X, Y = self.b, self.X, self.Y
        f, fm = f or self.f(Y(14)), fm or self.f(Y(12))
        ink = b["blue"] if on else b["text"]
        if on:
            pygame.draw.rect(c, b["cell_on"], r)
            pygame.draw.rect(c, b["text"], (r.x, r.y, r.w, Y(2)))
        else:
            pygame.draw.rect(c, b["rule"], (r.x, r.bottom, r.w, 1))
        mw = self.width(fm, meta) + X(12) if meta else 0
        self.tx(c, self.fit(f, title, r.w - mw - X(16)), f, ink, r.x + X(8), self.mid(r, f))
        if meta:
            self.tx(c, meta, fm, ink if on else b["soft"], r.right - X(8), self.mid(r, fm), align="right")

    def _button(self, c, r, label, on, f=None):
        b, Y = self.b, self.Y
        f = f or self.f(Y(13))
        pygame.draw.rect(c, b["cell_on"] if on else b["cell"], r, border_radius=Y(2))
        self.tx(c, self.fit(f, label, r.w - Y(8)), f, b["blue"] if on else b["text"], r.centerx, self.mid(r, f), align="center")
        if on:
            w = min(r.w - Y(8), self.width(f, label))
            pygame.draw.rect(c, b["blue"], (r.centerx - w // 2, r.bottom - Y(3), w, Y(2)))

    def _page_top(self, c, title, sub="", picture=True):
        b, X, Y = self.b, self.X, self.Y
        self.dim(c, 215)
        self._crumb(c, title.split(" / ")[0], "")
        self._light(c, self.fit(self.f(Y(24)), title, X(600)), 24, b["text"], X(20), Y(40))
        if sub:
            self._light(c, self.fit(self.f(Y(12)), sub, X(600)), 12, b["soft"], X(20), Y(78))

    def _panel(self, c, r):
        pass

    def _foot(self, c, text):
        self._light(c, self.fit(self.f(self.Y(11)), text, self.X(500)), 11, self.b["muted"], self.X(20), self.Y(458))

    def _wall(self, c, s, area):
        """Rows of posters with their titles beneath, the chosen one framed
        orange, as the box's rows."""
        b, X, Y = self.b, self.X, self.Y
        cols = self.WALL[0]
        gap = X(8)
        tw = (area.w - (cols - 1) * gap) // cols
        th = min(int(tw * 1.5), (area.h - Y(40)) // self.WALL[1] - Y(20))
        for i, slot in self.wall_cells(s, cols, self.WALL[1]):
            row = s.rows[i]
            r = pygame.Rect(area.x + (slot % cols) * (tw + gap), area.y + (slot // cols) * (th + Y(26)), tw, th)
            if i == s.sel:
                pygame.draw.rect(c, b["orange"], r.inflate(Y(6), Y(6)), Y(3))
            pygame.draw.rect(c, b["cell"], r)
            art = self.app.ondemand.poster(row.get("thumb", ""), r.w, r.h) if row.get("thumb") else None
            if art:
                c.blit(art, art.get_rect(center=r.center))
            self._light(c, self.fit(self.f(Y(10)), nice(row.get("title", "")), tw), 10, b["text"] if i == s.sel else b["soft"],
                        r.x, r.bottom + Y(4))
            self.hit(r, lambda i=i: (setattr(s, "sel", i), s.select()))

    def draw_iteminfo(self, c, info):
        from ..screens.iteminfo import hms
        b, X, Y = self.b, self.X, self.Y
        d = info.detail
        self.dim(c, 215)
        self._crumb(c, "On Demand", self.fit(self.f(Y(13)), d.get("title", ""), X(300)))
        self._light(c, self.fit(self.f(Y(24)), d.get("title", ""), X(600)), 24, b["text"], X(20), Y(40))
        art_r = self.R(20, 80, 110, 220)
        pygame.draw.rect(c, b["cell"], art_r)
        pygame.draw.rect(c, b["orange"], art_r.inflate(Y(6), Y(6)), Y(3))
        art = self.logo(d.get("poster", ""), art_r.w, art_r.h, headers=d.get("poster_headers") or None)
        if art:
            c.blit(art, art.get_rect(center=art_r.center))
        x0 = art_r.right + X(20)
        meta = d.get("subtitle") or d.get("meta", "")
        self._light(c, self.fit(self.f(Y(12)), meta, X(330)), 12, b["blue"], x0, Y(84))
        y = Y(106)
        for ln in self.wrap(self.f(Y(12)), d.get("summary", "") or "No description available.", X(330), 7):
            self._light(c, ln, 12, b["text"], x0, y)
            y += Y(16)
        pygame.draw.rect(c, b["rule"], (X(500), Y(84), 1, Y(120)))
        self._light(c, "Details", 10, b["soft"], X(512), Y(84))
        y = Y(102)
        for line in (hms(d["duration"]) if d.get("duration") else "", f"Resume at {hms(d['offset'])}" if (d.get("offset") or 0) > 5 else ""):
            if line:
                self._light(c, line, 12, b["text"], X(512), y)
                y += Y(16)
        names = info.buttons()
        f = self.f(Y(14))
        x = x0
        for k, n in enumerate(names):
            label = self.button_words(info.label(n))
            w = self.width(f, label)
            r = pygame.Rect(x, Y(270), w, Y(22))
            self._underline(c, r, k == info.focus, f, label, b["blue"] if k == info.focus else b["text"])
            self.hit(r, lambda k=k, n=n: (setattr(info, "focus", k), info.press(n)))
            x += w + X(24)

    def _boot_page(self, c):
        c.fill((*self.b["page"], 255))
