"""Plex-Per-View item info screen.

A Plex-style detail page shown when a title is selected: poster, summary and
metadata, and Play / Watchlist / Back buttons. Full-screen and opaque; the app
drives data + actions, this renders and tracks the button cursor. The poster is
fetched through the shared logo/image store. ASCII only (pixel fonts).
"""

from __future__ import annotations

from typing import Optional

from PIL import Image, ImageDraw

from .theme import (
    get_font, ellipsize, fmt_hms, wrap_lines, OSD_BG, OSD_BORDER, WHITE,
    WHITE_DIM, CYAN, YELLOW, INK_MUTED, BTN_PRIMARY_BG, BTN_PRIMARY_TEXT,
    CHANNEL_GREEN, GUIDE_SELECTED, SEL_TEXT, SCREEN_BG,
)

# Button sets per item kind. "show" = a TV series; "episode" = a single
# episode (no watchlist — Plex only watchlists at the series level); movies and
# other videos use the default play/watchlist/back.
BUTTON_SETS = {
    "show": ["playall", "seasons", "shuffle", "queue", "watchlist", "back"],
    "episode": ["play", "queue", "back"],
    "default": ["play", "queue", "watchlist", "back"],
}

LABELS = {
    "play": "PLAY", "playall": "PLAY ALL", "seasons": "SEASONS",
    "shuffle": "SHUFFLE", "queue": "+ QUEUE", "back": "BACK",
}

# The one action this page exists for. It keeps an accent border and full-
# strength label even while the cursor is elsewhere, so "what does this page
# want me to do" survives moving the focus off it. Focus is still the fill —
# primacy and focus are different questions and need different answers.
PRIMARY = {"play", "playall"}


def _fmt(t: float) -> str:
    t = max(0, int(t or 0))
    h, m = t // 3600, (t % 3600) // 60
    return f"{h}h {m:02d}m" if h else f"{m}m"


class PlexInfoScreen:
    def __init__(self, width: int, height: int):
        self.open = False
        self.width = width
        self.height = height
        self.data = {}
        self.watchlisted = False
        self.buttons = list(BUTTON_SETS["default"])
        self.focus = 0
        self.logos = None          # LogoStore (set by App) for the poster
        self._build_fonts()

    def _build_fonts(self):
        h = self.height
        self.f_title = get_font(max(22, int(h * 0.050)))
        self.f_sub = get_font(max(13, int(h * 0.028)))
        self.f_body = get_font(max(12, int(h * 0.026)))
        # Buttons have no fixed font: the row shrinks it to fit (_fitted_btn_font).
        self.btn_size = max(14, int(h * 0.030))

    def resize(self, w, h):
        self.width, self.height = w, h
        self._build_fonts()

    refresh_fonts = _build_fonts

    def show(self, data, watchlisted=False, kind="default"):
        self.data = data or {}
        self.watchlisted = watchlisted
        self.buttons = list(BUTTON_SETS.get(kind, BUTTON_SETS["default"]))
        self.focus = 0
        self.open = True

    def close(self):
        self.open = False

    # ── nav ───────────────────────────────────────────────────────────────

    def move(self, delta):
        self.focus = (self.focus + delta) % len(self.buttons)

    def focused_id(self) -> str:
        return self.buttons[self.focus]

    def _button_rects(self):
        n = len(self.buttons)
        gap = max(10, int(self.width * 0.015))
        bh = max(40, int(self.height * 0.075))
        # Shrink button width so the whole row fits when there are many buttons.
        avail = int(self.width * 0.94)
        # Floor is 80px, not a comfortable 120 — a six-button show page still has
        # to fit on a 640-wide window.
        bw = max(80, min(int(self.width * 0.17),
                         (avail - gap * (n - 1)) // max(1, n)))
        total = bw * n + gap * (n - 1)
        x0 = (self.width - total) // 2
        y = self.height - bh - int(self.height * 0.08)
        out = []
        for i in range(n):
            x = x0 + i * (bw + gap)
            out.append((i, x, y, x + bw, y + bh))
        return out

    def hit_test(self, x, y) -> Optional[int]:
        for (i, ax0, ay0, ax1, ay1) in self._button_rects():
            if ax0 <= x <= ax1 and ay0 <= y <= ay1:
                return i
        return None

    def set_hover(self, x, y):
        i = self.hit_test(x, y)
        if i is not None:
            self.focus = i

    # ── render ────────────────────────────────────────────────────────────

    def render(self) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        if not self.open:
            return img
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, self.width, self.height], fill=SCREEN_BG)
        m = max(20, int(self.width * 0.04))

        # Poster (left)
        pw = int(self.width * 0.28)
        ph = int(pw * 1.5)
        px, py = m, int(self.height * 0.12)
        poster = None
        url = self.data.get("poster")
        if url and self.logos is not None:
            poster = self.logos.get(url, pw, ph,
                                    headers=self.data.get("poster_headers"))
        if poster is not None:
            img.alpha_composite(poster, (px, py))
        else:
            d.rectangle([px, py, px + pw, py + ph],
                        fill=(OSD_BG[0], OSD_BG[1], OSD_BG[2], 255),
                        outline=OSD_BORDER, width=2)
            self._center_in(d, "NO ART", self.f_sub, px, py, px + pw, py + ph, INK_MUTED)

        # Text column (right)
        tx = px + pw + m
        ty = py
        col_w = self.width - tx - m            # right column width; wrap to it
        title_lh = self._th(d, "Ag", self.f_title) + 6
        for ln in wrap_lines(d, self.data.get("title", ""), self.f_title, col_w, 3):
            d.text((tx, ty), ln, font=self.f_title, fill=WHITE)
            ty += title_lh
        ty += 4
        meta = self.data.get("subtitle", "")
        dur = self.data.get("duration", 0)
        if dur:
            meta = (meta + "    " if meta else "") + _fmt(dur)
        if meta:
            d.text((tx, ty), ellipsize(d, meta, self.f_sub, col_w), font=self.f_sub, fill=CYAN)
            ty += self._th(d, "Ag", self.f_sub) + 14
        off = self.data.get("offset", 0)
        if off and off > 5:
            d.text((tx, ty), f"Resume at {fmt_hms(off)}", font=self.f_body, fill=YELLOW)
            ty += self._th(d, "Ag", self.f_body) + 12
        self._wrap(d, self.data.get("summary", ""), self.f_body,
                   tx, ty, self.width - tx - m, WHITE_DIM)

        # Buttons
        wl_label = "- WATCHLIST" if self.watchlisted else "+ WATCHLIST"
        labels = [wl_label if b == "watchlist" else LABELS.get(b, b.upper())
                  for b in self.buttons]
        rects = self._button_rects()
        f_btn = self._fitted_btn_font(d, labels,
                                      rects[0][3] - rects[0][1] if rects else 0)
        for (i, ax0, ay0, ax1, ay1) in rects:
            label = labels[i]
            sel = (i == self.focus)
            primary = self.buttons[i] in PRIMARY
            fill = (GUIDE_SELECTED[0], GUIDE_SELECTED[1], GUIDE_SELECTED[2], 255) \
                if sel else (OSD_BG[0], OSD_BG[1], OSD_BG[2], 255)
            if sel:
                outline, width, ink = CHANNEL_GREEN, 3, SEL_TEXT
            elif primary:
                fill = (BTN_PRIMARY_BG[0], BTN_PRIMARY_BG[1],
                        BTN_PRIMARY_BG[2], 255)
                outline, width, ink = CYAN, 2, BTN_PRIMARY_TEXT
            else:
                outline, width, ink = OSD_BORDER, 2, WHITE_DIM
            d.rounded_rectangle([ax0, ay0, ax1, ay1], radius=8, fill=fill,
                                outline=outline, width=width)
            self._center_in(d, label, f_btn, ax0, ay0, ax1, ay1, ink)
        return img

    # ── helpers ───────────────────────────────────────────────────────────

    def _fitted_btn_font(self, d, labels, bw):
        """Largest button font whose widest label still fits inside a button.
        Labels are centered, so an overflowing one spills over its neighbours —
        a six-button series page in a wide pixel font does exactly that."""
        size = self.btn_size
        while size > 9:
            f = get_font(size)
            if max(d.textlength(t, font=f) for t in labels) <= bw - 12:
                return f
            size -= 1
        return get_font(10)

    def _wrap(self, d, text, font, x, y, maxw, color):
        if not text:
            return
        line_h = self._th(d, "Ag", font) + 6
        words = text.split()
        line = ""
        for w in words:
            test = (line + " " + w).strip()
            if d.textbbox((0, 0), test, font=font)[2] > maxw and line:
                d.text((x, y), line, font=font, fill=color)
                y += line_h
                line = w
                if y > self.height - int(self.height * 0.22):
                    d.text((x, y), line + " ...", font=font, fill=color)
                    return
            else:
                line = test
        if line:
            d.text((x, y), line, font=font, fill=color)

    def _center_in(self, d, text, font, x0, y0, x1, y1, color):
        bb = d.textbbox((0, 0), text, font=font)
        d.text((x0 + (x1 - x0 - (bb[2] - bb[0])) // 2 - bb[0],
                y0 + (y1 - y0 - (bb[3] - bb[1])) // 2 - bb[1]), text, font=font, fill=color)

    @staticmethod
    def _th(d, text, font):
        bb = d.textbbox((0, 0), text, font=font)
        return bb[3] - bb[1]
