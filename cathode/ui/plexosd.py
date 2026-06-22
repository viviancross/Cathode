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
    get_font, OSD_BG, OSD_BORDER, WHITE, WHITE_DIM, CYAN, YELLOW,
    CHANNEL_GREEN, GUIDE_SELECTED,
)

# focus order (left→right, timeline first). `prev`/`next` skip to the previous /
# next episode (in a show queue) or chapter (in a movie).
ITEMS = ["timeline", "prev", "back10", "playpause", "stop", "fwd10", "next",
         "volume", "menu"]
_LABELS = {"prev": "|<<", "back10": "<< 10", "playpause": "PAUSE", "stop": "STOP",
           "fwd10": "10 >>", "next": ">>|"}


def _fmt(t: float) -> str:
    t = max(0, int(t or 0))
    h, m, s = t // 3600, (t % 3600) // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class PlexOSD:
    def __init__(self, width: int, height: int):
        self.visible = False
        self.width = width
        self.height = height
        self.title = ""
        self.subtitle = ""
        self.pos = 0.0
        self.dur = 0.0
        self.paused = False
        self.volume = 80
        self.muted = False
        self.adjusting = False    # volume is selected for Left/Right adjustment
        self.scrubbing = False    # timeline is selected for Left/Right scrubbing
        self.focus = 0            # index into the current item list; default = timeline
        self.skip_label = ""      # "SKIP INTRO"/"SKIP CREDITS" while a marker is active ("" = none)
        self.skip_to = 0.0        # seconds to seek to when SKIP is pressed
        self._build_fonts()

    def _build_fonts(self):
        h = self.height
        self.f_title = get_font(max(15, int(h * 0.032)))
        self.f_sub = get_font(max(11, int(h * 0.022)))
        self.f_time = get_font(max(11, int(h * 0.022)))
        self.f_btn = get_font(max(12, int(h * 0.025)))

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

    def _panel(self) -> Tuple[int, int, int, int]:
        mx = max(12, int(self.width * 0.03))
        gap_b = max(6, int(self.height * 0.015))     # sits low, near the edge
        bh = max(86, int(self.height * 0.165))       # slim
        y1 = self.height - gap_b
        return mx, y1 - bh, self.width - mx, y1

    def _timeline_rect(self) -> Tuple[int, int, int, int]:
        x0, y0, x1, y1 = self._panel()
        pad = max(10, int(self.width * 0.012))
        el_w = 70
        du_w = 70
        by = y0 + int((y1 - y0) * 0.40)   # up high so the button row fits below
        return x0 + pad + el_w, by - 9, x1 - pad - du_w, by + 9

    def _bottom_rects(self) -> List[Tuple[str, int, int, int, int]]:
        x0, y0, x1, y1 = self._panel()
        bh = max(26, int(self.height * 0.05))
        bw = max(58, int(self.width * 0.075))
        sw = max(46, int(self.width * 0.055))    # narrower skip buttons
        vw = max(108, int(self.width * 0.13))
        mw = max(38, int(bh * 1.4))
        gap = max(6, int(self.width * 0.01))
        order = [("prev", sw), ("back10", bw), ("playpause", bw), ("stop", bw),
                 ("fwd10", bw), ("next", sw), ("volume", vw), ("menu", mw)]
        if self.skip_label:
            order.append(("skip", max(bw, int(self.width * 0.14))))
        total = sum(w for _, w in order) + gap * (len(order) - 1)
        sx = (self.width - total) // 2
        by = y1 - bh - max(6, int(self.height * 0.018))
        out = []
        x = sx
        for name, w in order:
            out.append((name, x, by, x + w, by + bh))
            x += w + gap
        return out

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

        # Title (+ subtitle inline)
        d.text((x0 + pad, y0 + pad // 2), self.title or "", font=self.f_title, fill=WHITE)
        if self.subtitle:
            tw = d.textbbox((0, 0), (self.title or "") + "  ", font=self.f_title)[2]
            d.text((x0 + pad + tw, y0 + pad // 2 + 4), self.subtitle,
                   font=self.f_sub, fill=CYAN)

        # Timeline
        tx0, ty0, tx1, ty1 = self._timeline_rect()
        midy = (ty0 + ty1) // 2
        d.text((x0 + pad, midy - self.f_time.size // 2), _fmt(self.pos),
               font=self.f_time, fill=WHITE_DIM)
        du = _fmt(self.dur)
        duw = d.textbbox((0, 0), du, font=self.f_time)[2]
        d.text((x1 - pad - duw, midy - self.f_time.size // 2), du,
               font=self.f_time, fill=WHITE_DIM)
        d.rectangle([tx0, midy - 3, tx1, midy + 3], fill=(20, 20, 30, 255),
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

        # Bottom row
        for (name, ax0, ay0, ax1, ay1) in self._bottom_rects():
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
            elif name == "skip":
                self._centered(d, self.skip_label, self.f_btn, ax0, ay0, ax1, ay1,
                               WHITE if sel else YELLOW)
            else:
                label = ("PLAY" if self.paused else "PAUSE") if name == "playpause" \
                    else _LABELS[name]
                self._centered(d, label, self.f_btn, ax0, ay0, ax1, ay1,
                               WHITE if sel else WHITE_DIM)
        return img

    def _draw_volume(self, d, ax0, ay0, ax1, ay1, sel):
        active = sel and self.adjusting
        if active:                          # brighten the box while adjusting
            d.rounded_rectangle([ax0, ay0, ax1, ay1], radius=6, outline=CYAN, width=3)
        lbl = "MUTE" if self.muted else ("<VOL>" if active else "VOL")
        d.text((ax0 + 10, ay0 + (ay1 - ay0 - self.f_btn.size) // 2), lbl,
               font=self.f_btn, fill=CYAN if active else (WHITE if sel else WHITE_DIM))
        lw = d.textbbox((0, 0), lbl, font=self.f_btn)[2]
        bx0 = ax0 + 14 + lw + 8
        bx1 = ax1 - 12
        my = (ay0 + ay1) // 2
        d.rectangle([bx0, my - 4, bx1, my + 4], fill=(20, 20, 30, 255),
                    outline=OSD_BORDER, width=1)
        if not self.muted:
            fx = bx0 + int((bx1 - bx0) * max(0, min(100, self.volume)) / 100)
            d.rectangle([bx0, my - 4, fx, my + 4], fill=CHANNEL_GREEN)

    def _draw_hamburger(self, d, ax0, ay0, ax1, ay1, sel):
        cx0 = ax0 + (ax1 - ax0) // 2 - 9
        cx1 = ax0 + (ax1 - ax0) // 2 + 9
        cy = (ay0 + ay1) // 2
        col = WHITE if sel else WHITE_DIM
        for dy in (-6, 0, 6):
            d.rectangle([cx0, cy + dy - 1, cx1, cy + dy + 1], fill=col)

    def _centered(self, d, text, font, ax0, ay0, ax1, ay1, color):
        lb = d.textbbox((0, 0), text, font=font)
        lx = ax0 + (ax1 - ax0 - (lb[2] - lb[0])) // 2 - lb[0]
        ly = ay0 + (ay1 - ay0 - (lb[3] - lb[1])) // 2 - lb[1]
        d.text((lx, ly), text, font=font, fill=color)
