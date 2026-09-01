"""Playback control bar for Plex-Per-View.

A slim bottom info bar shown while a Plex item is playing: title, a scrubbable
timeline, transport buttons (back 10s, play/pause, stop, forward 10s), a volume
control, and a context-menu (hamburger) button. Styled like the live-TV info bar.

Every part is a focusable item. The arrow keys move the highlight; Left/Right
also scrub when the timeline is highlighted and change volume when the volume
item is highlighted. The app reads focused_id() / the item rects to act.
ASCII only (pixel fonts).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from .theme import (
    get_font, ellipsize, fmt_hms, OSD_BG, OSD_BORDER, WHITE, WHITE_DIM, CYAN,
    YELLOW, TRACK, CHANNEL_GREEN, GUIDE_SELECTED, SEL_TEXT,
)

# focus order (left→right, timeline first). `prev`/`next` skip to the previous /
# next episode (in a show queue) or chapter (in a movie).
ITEMS = ["timeline", "prev", "back10", "playpause", "stop", "fwd10", "next",
         "volume", "menu"]
_LABELS = {"prev": "|<<", "back10": "<< 10", "playpause": "PAUSE", "stop": "STOP",
           "fwd10": "10 >>", "next": ">>|"}


class PlexOSD:
    def __init__(self, width: int, height: int):
        self.visible = False
        self.width = width
        self.height = height
        self.min_row_h = 0        # physical floor for touch hosts (px); also the
        # signal that there IS one, which changes what the bar needs to carry
        self.title = ""
        self.subtitle = ""
        self.pos = 0.0
        self.dur = 0.0
        self.paused = False
        self.volume = 80
        self.muted = False
        self.adjusting = False    # volume is selected for Left/Right adjustment
        self.scrubbing = False    # timeline is selected for Left/Right scrubbing
        # Default focus = play/pause: the first A-press should pause, not start
        # a timeline scrub.
        self.focus = ITEMS.index("playpause")
        self.skip_label = ""      # "SKIP INTRO"/"SKIP CREDITS" while a marker is active ("" = none)
        self.skip_to = 0.0        # seconds to seek to when SKIP is pressed
        self._build_fonts()

    def _build_fonts(self):
        # Sizes harmonized with the context menu (title 0.034h, body 0.030h,
        # small 0.024h) so text looks even across the menus and the OSD.
        h = self.height
        self.f_title = get_font(max(16, int(h * 0.034)))
        self.f_sub = get_font(max(12, int(h * 0.024)))
        self.f_time = get_font(max(12, int(h * 0.024)))
        self.f_btn = get_font(max(14, int(h * 0.030)))

    def resize(self, w, h):
        self.width, self.height = w, h
        self._build_fonts()

    refresh_fonts = _build_fonts

    # ── state ─────────────────────────────────────────────────────────────

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def set_info(self, title: str, subtitle: str = ""):
        self.title = title
        self.subtitle = subtitle

    def set_progress(self, pos: float, dur: float, paused: bool):
        self.pos = pos or 0.0
        self.dur = dur or 0.0
        self.paused = bool(paused)

    # ── focus ─────────────────────────────────────────────────────────────

    def _items(self) -> List[str]:
        # SKIP is appended only while a marker is active, so it's never the
        # default focus (which stays on the timeline at index 0).
        return ITEMS + (["skip"] if self.skip_label else [])

    def focus_next(self):
        self.focus = (self.focus + 1) % len(self._items())

    def focus_prev(self):
        self.focus = (self.focus - 1) % len(self._items())

    def focused_id(self) -> str:
        items = self._items()
        return items[self.focus % len(items)]

    def focus_to(self, name: str):
        items = self._items()
        if name in items:
            self.focus = items.index(name)

    # ── geometry ──────────────────────────────────────────────────────────

    def _pad(self) -> int:
        return max(10, int(self.width * 0.012))

    def _btn_h(self) -> int:
        return max(26, self.min_row_h, int(self.height * 0.05))

    def _btn_gap(self) -> int:
        return max(6, int(self.height * 0.018))

    def _text_h(self, d=None) -> int:
        """Height of the title block — two lines when the subtitle stacks."""
        d = d or ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        h = d.textbbox((0, 0), "Ag", font=self.f_title)[3]
        if self.width < self.height and self.subtitle:
            h += d.textbbox((0, 0), "Ag", font=self.f_sub)[3] + 4
        return h

    def _panel(self) -> Tuple[int, int, int, int]:
        mx = max(12, int(self.width * 0.03))
        gap_b = max(6, int(self.height * 0.015))     # sits low, near the edge
        # Slim on a television. Upright the bar carries an extra line -- the
        # subtitle drops under the title rather than sharing it -- so it needs
        # the height to stay slim-looking rather than crushed.
        frac = 0.22 if self.width < self.height else 0.165
        bh = max(86, int(self.height * frac))
        # A fraction of the height is not a promise about the contents. The
        # button row has a physical floor on a touch host, and on a short
        # display -- a cover screen, a small window -- the fraction doesn't
        # cover it, so the buttons end up drawn over the timeline.
        if self.min_row_h:
            need = (self._pad() // 2 + self._text_h() + 10 + 18 + 10
                    + self._btn_h() + self._btn_gap() + 8)
            bh = max(bh, need)
        y1 = self.height - gap_b
        return mx, y1 - bh, self.width - mx, y1

    def _timeline_rect(self) -> Tuple[int, int, int, int]:
        x0, y0, x1, y1 = self._panel()
        pad = max(10, int(self.width * 0.012))
        # Reserve what the labels actually measure. A fraction of the width is
        # only enough while the box is landscape: the time font is sized off the
        # height, so in a tall box "41:20" is wider than the fraction set aside
        # for it and the bar is drawn straight through the text.
        d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        el_w = max(int(self.width * 0.06),
                   int(d.textlength(fmt_hms(self.pos), font=self.f_time)) + 14)
        du_w = max(int(self.width * 0.06),
                   int(d.textlength(fmt_hms(self.dur), font=self.f_time)) + 14)
        # Centred in what's left between the title block and the button row,
        # rather than at a fixed fraction of the panel: the two things it has to
        # clear both grow on a touch host, and the fraction doesn't.
        top = y0 + pad // 2 + self._text_h(d)
        bot = y1 - self._btn_h() - self._btn_gap()
        by = (top + bot) // 2
        return x0 + pad + el_w, by - 9, x1 - pad - du_w, by + 9

    def _bottom_rects(self) -> List[Tuple[str, int, int, int, int]]:
        x0, y0, x1, y1 = self._panel()
        bh = self._btn_h()
        bw = max(58, int(self.width * 0.075))
        sw = max(46, int(self.width * 0.055))    # narrower skip buttons
        vw = max(108, int(self.width * 0.13))
        mw = max(38, int(bh * 1.4))
        gap = max(6, int(self.width * 0.01))
        order = [("prev", sw), ("back10", bw), ("playpause", bw), ("stop", bw),
                 ("fwd10", bw), ("next", sw)]
        if not self.min_row_h:
            # A phone's volume rocker already does this, and does it better than
            # a slider a thumb has to find inside a control bar.
            order.append(("volume", vw))
        if self.skip_label:
            order.append(("skip", max(bw, int(self.width * 0.14))))
        order.append(("menu", mw))

        pad = self._pad()
        room = (x1 - x0) - 2 * pad - gap * (len(order) - 1)
        # The boxes are fractions of the width and the labels in them are sized
        # off the height, so in a tall box the labels overflow their boxes and
        # print through each other. Fit the row to the width it actually has:
        # shrink it when it doesn't fit, and on a touch host spread it out when
        # it does, so the room goes to the labels instead of the margins. The
        # menu button is square and sits out of the scaling.
        flex = [(n, w) for n, w in order if n != "menu"]
        k = (room - mw) / max(1, sum(w for _, w in flex))
        if k < 1 or self.min_row_h:
            order = [(n, mw if n == "menu" else max(24, int(w * k)))
                     for n, w in order]
        by = y1 - bh - self._btn_gap()
        total = sum(w for _, w in order) + gap * (len(order) - 1)
        x = x0 + pad + max(0, ((x1 - x0) - 2 * pad - total) // 2)
        out = []
        for name, w in order:
            out.append((name, x, by, x + w, by + bh))
            x += w + gap
        return out

    def _fitted_btn_font(self, d, labels, bw):
        """Largest button font whose widest label still fits inside a button."""
        size = max(14, int(self.height * 0.030))
        while size > 9:
            f = get_font(size)
            if not labels or max(d.textlength(t, font=f) for t in labels) <= bw - 12:
                return f
            size -= 1
        return get_font(9)

    def _rects(self) -> Dict[str, Tuple[int, int, int, int]]:
        r = {"timeline": self._timeline_rect()}
        for (name, a, b, c, d) in self._bottom_rects():
            r[name] = (a, b, c, d)
        return r

    def hit_test(self, x, y) -> Optional[str]:
        for name, (ax0, ay0, ax1, ay1) in self._rects().items():
            if ax0 <= x <= ax1 and ay0 <= y <= ay1:
                return name
        return None

    def set_hover(self, x, y):
        name = self.hit_test(x, y)
        if name in ITEMS:
            self.focus = ITEMS.index(name)

    def seek_fraction(self, x) -> Optional[float]:
        """For a click on the timeline: 0..1 position, else None."""
        tx0, _, tx1, _ = self._timeline_rect()
        if tx1 <= tx0:
            return None
        return max(0.0, min(1.0, (x - tx0) / (tx1 - tx0)))

    def volume_fraction(self, x) -> Optional[float]:
        for (name, a, _, c, _) in self._bottom_rects():
            if name == "volume" and c > a:
                return max(0.0, min(1.0, (x - a - 10) / max(1, (c - a - 20))))
        return None

    # ── render ────────────────────────────────────────────────────────────

    def render(self) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        if not self.visible:
            return img
        d = ImageDraw.Draw(img)
        x0, y0, x1, y1 = self._panel()
        d.rectangle([x0, y0, x1, y1], fill=(OSD_BG[0], OSD_BG[1], OSD_BG[2], 235),
                    outline=OSD_BORDER, width=3)
        pad = max(10, int(self.width * 0.012))
        fid = self.focused_id()

        # Title (+ subtitle). Side by side on a television; upright there isn't
        # the width for both, and sharing the line costs the title most of its
        # characters, so the subtitle takes its own.
        inner = (x1 - x0) - 2 * pad
        stacked = self.width < self.height
        title_max = inner if (stacked or not self.subtitle) else int(inner * 0.62)
        title_t = ellipsize(d, self.title or "", self.f_title, title_max)
        d.text((x0 + pad, y0 + pad // 2), title_t, font=self.f_title, fill=WHITE)
        if self.subtitle:
            if stacked:
                sy = y0 + pad // 2 + d.textbbox((0, 0), "Ag", font=self.f_title)[3] + 4
                d.text((x0 + pad, sy),
                       ellipsize(d, self.subtitle, self.f_sub, inner),
                       font=self.f_sub, fill=CYAN)
            else:
                tw = d.textbbox((0, 0), title_t + "  ", font=self.f_title)[2]
                sub_t = ellipsize(d, self.subtitle, self.f_sub, inner - tw)
                d.text((x0 + pad + tw, y0 + pad // 2 + 4), sub_t,
                       font=self.f_sub, fill=CYAN)

        # Timeline
        tx0, ty0, tx1, ty1 = self._timeline_rect()
        midy = (ty0 + ty1) // 2
        # Centred on the bar by measured ink, not by the font's nominal size —
        # the pixel fonts carry enough top bearing that the nominal size puts
        # the digits low enough to sit on the bar.
        def _time_at(x, text):
            bb = d.textbbox((0, 0), text, font=self.f_time)
            d.text((x, midy - (bb[3] - bb[1]) // 2 - bb[1]), text,
                   font=self.f_time, fill=WHITE_DIM)

        _time_at(x0 + pad, fmt_hms(self.pos))
        du = fmt_hms(self.dur)
        duw = d.textbbox((0, 0), du, font=self.f_time)[2]
        _time_at(x1 - pad - duw, du)
        d.rectangle([tx0, midy - 3, tx1, midy + 3], fill=TRACK,
                    outline=OSD_BORDER, width=1)
        if self.dur > 0:
            frac = max(0.0, min(1.0, self.pos / self.dur))
            fx = tx0 + int((tx1 - tx0) * frac)
            d.rectangle([tx0, midy - 3, fx, midy + 3], fill=CHANNEL_GREEN)
            d.ellipse([fx - 6, midy - 6, fx + 6, midy + 6], fill=CHANNEL_GREEN)
        if fid == "timeline":
            col = CYAN if self.scrubbing else CHANNEL_GREEN   # brighten while scrubbing
            d.rectangle([tx0 - 6, ty0, tx1 + 6, ty1], outline=col,
                        width=3 if self.scrubbing else 2)

        # Bottom row. The font is fitted to the narrowest button rather than
        # trusted: labels are centred, so one that overflows spills across its
        # neighbours instead of being clipped.
        rects = self._bottom_rects()
        labelled = [r for r in rects if r[0] not in ("menu", "volume")]
        f_btn = self._fitted_btn_font(
            d, [self._label_for(n) for n, _, _, _, _ in labelled],
            min((r[3] - r[1]) for r in labelled) if labelled else 0)
        for (name, ax0, ay0, ax1, ay1) in rects:
            sel = (name == fid)
            fill = (GUIDE_SELECTED[0], GUIDE_SELECTED[1], GUIDE_SELECTED[2], 255) \
                if sel else (OSD_BG[0], OSD_BG[1], OSD_BG[2], 255)
            d.rounded_rectangle([ax0, ay0, ax1, ay1], radius=6, fill=fill,
                                outline=CHANNEL_GREEN if sel else OSD_BORDER,
                                width=3 if sel else 2)
            if name == "menu":
                self._draw_hamburger(d, ax0, ay0, ax1, ay1, sel)
            elif name == "volume":
                self._draw_volume(d, ax0, ay0, ax1, ay1, sel)
            else:
                self._centered(d, self._label_for(name), f_btn,
                               ax0, ay0, ax1, ay1,
                               SEL_TEXT if sel else
                               (YELLOW if name == "skip" else WHITE_DIM))
        return img

    def _label_for(self, name: str) -> str:
        if name == "skip":
            return self.skip_label
        if name == "playpause":
            return "PLAY" if self.paused else "PAUSE"
        return _LABELS.get(name, "")

    def _draw_volume(self, d, ax0, ay0, ax1, ay1, sel):
        active = sel and self.adjusting
        if active:                          # brighten the box while adjusting
            d.rounded_rectangle([ax0, ay0, ax1, ay1], radius=6, outline=CYAN, width=3)
        lbl = "MUTE" if self.muted else ("<VOL>" if active else "VOL")
        d.text((ax0 + 10, ay0 + (ay1 - ay0 - self.f_btn.size) // 2), lbl,
               font=self.f_btn, fill=SEL_TEXT if sel else WHITE_DIM)
        lw = d.textbbox((0, 0), lbl, font=self.f_btn)[2]
        bx0 = ax0 + 14 + lw + 8
        bx1 = ax1 - 12
        my = (ay0 + ay1) // 2
        d.rectangle([bx0, my - 4, bx1, my + 4], fill=TRACK,
                    outline=OSD_BORDER, width=1)
        if not self.muted:
            fx = bx0 + int((bx1 - bx0) * max(0, min(100, self.volume)) / 100)
            d.rectangle([bx0, my - 4, fx, my + 4], fill=CHANNEL_GREEN)

    def _draw_hamburger(self, d, ax0, ay0, ax1, ay1, sel):
        cx0 = ax0 + (ax1 - ax0) // 2 - 9
        cx1 = ax0 + (ax1 - ax0) // 2 + 9
        cy = (ay0 + ay1) // 2
        col = SEL_TEXT if sel else WHITE_DIM
        for dy in (-6, 0, 6):
            d.rectangle([cx0, cy + dy - 1, cx1, cy + dy + 1], fill=col)

    def _centered(self, d, text, font, ax0, ay0, ax1, ay1, color):
        lb = d.textbbox((0, 0), text, font=font)
        lx = ax0 + (ax1 - ax0 - (lb[2] - lb[0])) // 2 - lb[0]
        ly = ay0 + (ay1 - ay0 - (lb[3] - lb[1])) // 2 - lb[1]
        d.text((lx, ly), text, font=font, fill=color)
