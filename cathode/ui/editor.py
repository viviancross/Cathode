"""Custom OSD theme editor — RGB color sliders for the main UI colors, plus
CRT-scanline and vignette toggles, with live preview and save options.

Navigable like the rest of the UI: up/down moves between rows, left/right adjusts
the value (or toggles), Enter/Select presses action rows; mouse hover + click
also work (clicking a slider sets it by x-position).  A close button sits in the
top-right of the title bar.  All glyphs ASCII.
"""

from __future__ import annotations

from typing import Callable, Optional

from PIL import Image, ImageDraw

from .theme import (
    get_font, OSD_BG, OSD_BORDER, WHITE, WHITE_DIM, CYAN, YELLOW, GRAY,
    BLACK, CHANNEL_GREEN, GUIDE_SELECTED,
)

_COLORS = [("bg", "Background"), ("accent", "Accent"),
           ("accent2", "Highlight"), ("text", "Text"),
           ("chnum", "Channel #")]
_CHANS = ("R", "G", "B")
_DEFAULT = {"bg": [0, 0, 62], "accent": [0, 220, 255],
            "accent2": [255, 220, 0], "text": [255, 255, 255],
            "chnum": [40, 255, 90]}


class ThemeEditor:
    def __init__(self, width: int, height: int):
        self.open = False
        self.width = width
        self.height = height
        self.colors = {k: list(v) for k, v in _DEFAULT.items()}
        self.scanline = 40
        self.crt = True
        self.vignette = True
        self._sel = 0
        self._scroll = 0
        self._rows = []
        self._on_change = None
        self._on_action = None
        self._on_close = None
        self._build_fonts()
        self._build_rows()

    def _build_fonts(self):
        h = self.height
        self.font = get_font(max(13, int(h * 0.024)))
        self.font_title = get_font(max(15, int(h * 0.030)))

    def resize(self, w, h):
        self.width, self.height = w, h
        self._build_fonts()

    def refresh_fonts(self):
        self._build_fonts()

    def _build_rows(self):
        rows = []
        for ck, cname in _COLORS:
            for ci, ch in enumerate(_CHANS):
                rows.append(("color", ck, ci, f"{cname} {ch}"))
        rows.append(("slider", "scanline", None, "Scanline Intensity"))
        rows.append(("toggle", "crt", None, "CRT Scanlines"))
        rows.append(("toggle", "vignette", None, "Vignette"))
        rows.append(("action", "save_current", None, "Save Current Theme"))
        rows.append(("action", "save_new", None, "Save As New Theme"))
        rows.append(("action", "reset", None, "Reset to Default"))
        rows.append(("action", "close", None, "Close"))
        self._rows = rows

    # ── open / state ──────────────────────────────────────────────────────

    def show(self, state, on_change, on_action, on_close):
        self.colors = {k: list(state["colors"].get(k, _DEFAULT[k])) for k in _DEFAULT}
        self.scanline = int(state.get("scanline", 40))
        self.crt = bool(state.get("crt", True))
        self.vignette = bool(state.get("vignette", True))
        self._on_change, self._on_action, self._on_close = on_change, on_action, on_close
        self._sel = self._scroll = 0
        self.open = True

    def close(self):
        self.open = False

    def state(self):
        return {"colors": {k: list(v) for k, v in self.colors.items()},
                "scanline": self.scanline, "crt": self.crt,
                "vignette": self.vignette}

    def _changed(self):
        if self._on_change:
            self._on_change(self.state())

    # ── navigation / adjust ───────────────────────────────────────────────

    def _vis_count(self):
        return self._geom()[3][1]

    def move(self, d):
        self._sel = max(0, min(len(self._rows) - 1, self._sel + d))
        vis = self._vis_count()
        if self._sel < self._scroll:
            self._scroll = self._sel
        elif self._sel >= self._scroll + vis:
            self._scroll = self._sel - vis + 1

    def move_up(self):    self.move(-1)
    def move_down(self):  self.move(1)

    def adjust(self, delta):
        kind, key, ci, _ = self._rows[self._sel]
        if kind == "color":
            self.colors[key][ci] = max(0, min(255, self.colors[key][ci] + delta * 8))
        elif kind == "slider":
            self.scanline = max(0, min(255, self.scanline + delta * 8))
        elif kind == "toggle":
            setattr(self, key, not getattr(self, key))
        else:
            return
        self._changed()

    def left(self):  self.adjust(-1)
    def right(self): self.adjust(1)

    def _reset(self):
        self.colors = {k: list(v) for k, v in _DEFAULT.items()}
        self.scanline, self.crt, self.vignette = 40, True, True
        self._changed()

    def press(self):
        kind, key, _ci, _ = self._rows[self._sel]
        if kind == "action":
            if key == "reset":
                self._reset()
            elif key == "close":
                self.open = False
                if self._on_close:
                    self._on_close()
            elif self._on_action:
                self._on_action(key)
        elif kind == "toggle":
            self.adjust(1)

    confirm = press

    # ── geometry / mouse ──────────────────────────────────────────────────

    def _geom(self):
        w, h = self.width, self.height
        pw = max(460, min(int(w * 0.54), 860))
        px = (w - pw) // 2
        title_h = max(36, int(h * 0.062))
        avail = int(h * 0.88) - title_h
        nrows = max(1, len(self._rows))
        # Shrink rows so every row (incl. the action buttons) fits without
        # scrolling at normal resolutions; only tiny windows will scroll.
        row_h = max(24, min(int(h * 0.05), avail // nrows))
        vis = max(1, min(nrows, avail // row_h))
        ph = title_h + vis * row_h + 16
        py = (h - ph) // 2
        return px, py, pw, (row_h, vis), title_h

    def _close_btn_rect(self):
        px, py, pw, _, title_h = self._geom()
        s = title_h - 14
        x1 = px + pw - 12
        y0 = py + (title_h - s) // 2
        return (x1 - s, y0, x1, y0 + s)

    def _row_rects(self):
        px, py, pw, (row_h, vis), title_h = self._geom()
        top = py + title_h
        out = []
        for vi in range(vis):
            ri = self._scroll + vi
            if ri >= len(self._rows):
                break
            ry = top + vi * row_h
            out.append((ri, px, ry, px + pw, ry + row_h))
        return out

    def hit_test(self, x, y):
        for (ri, x0, y0, x1, y1) in self._row_rects():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return ri
        return None

    def set_hover(self, x, y):
        ri = self.hit_test(x, y)
        if ri is not None:
            self._sel = ri

    def _slider_span(self):
        px, py, pw, _, _ = self._geom()
        pad = 14
        val_w = 46
        sx0 = px + int(pw * 0.46)
        sx1 = px + pw - pad - val_w
        return sx0, sx1

    def click(self, x, y):
        cx0, cy0, cx1, cy1 = self._close_btn_rect()
        if cx0 <= x <= cx1 and cy0 <= y <= cy1:
            self.open = False
            if self._on_close:
                self._on_close()
            return
        ri = self.hit_test(x, y)
        if ri is None:
            return
        self._sel = ri
        kind, key, ci, _ = self._rows[ri]
        if kind in ("color", "slider"):
            sx0, sx1 = self._slider_span()
            frac = (x - sx0) / max(1, (sx1 - sx0))
            val = int(max(0.0, min(1.0, frac)) * 255)
            if kind == "color":
                self.colors[key][ci] = val
            else:
                self.scanline = val
            self._changed()
        else:
            self.press()

    # ── render ────────────────────────────────────────────────────────────

    @staticmethod
    def _draw_text(d, text, font, fill, x, y0, row_h, right_edge=None):
        """Draw vertically-centered text; right-align to right_edge if given."""
        bb = d.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        tx = (right_edge - tw - bb[0]) if right_edge is not None else (x - bb[0])
        ty = y0 + (row_h - th) // 2 - bb[1]
        d.text((tx, ty), text, font=font, fill=fill)

    def render(self) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        if not self.open:
            return img
        d = ImageDraw.Draw(img)
        px, py, pw, (row_h, vis), title_h = self._geom()
        ph = title_h + vis * row_h + 16
        pad = 14
        panel = (OSD_BG[0], OSD_BG[1], OSD_BG[2], 255)
        d.rectangle([0, 0, self.width, self.height], fill=(8, 8, 14, 255))
        d.rectangle([px, py, px + pw, py + ph], fill=panel)
        d.rectangle([px, py, px + pw, py + ph], outline=OSD_BORDER, width=2)

        # Title bar + divider
        self._draw_text(d, "CUSTOM THEME", self.font_title, YELLOW,
                        px + pad, py, title_h)
        d.line([px + pad, py + title_h - 2, px + pw - pad, py + title_h - 2],
               fill=OSD_BORDER, width=1)

        # Close [X] button (top-right of the title bar)
        cx0, cy0, cx1, cy1 = self._close_btn_rect()
        d.rectangle([cx0, cy0, cx1, cy1], outline=OSD_BORDER, width=2)
        d.line([cx0 + 6, cy0 + 6, cx1 - 6, cy1 - 6], fill=WHITE, width=2)
        d.line([cx0 + 6, cy1 - 6, cx1 - 6, cy0 + 6], fill=WHITE, width=2)

        sx0, sx1 = self._slider_span()
        val_right = px + pw - pad
        for (ri, x0, y0, x1, y1) in self._row_rects():
            kind, key, ci, label = self._rows[ri]
            if ri == self._sel:
                d.rectangle([x0 + 3, y0, x1 - 3, y1],
                            fill=(GUIDE_SELECTED[0], GUIDE_SELECTED[1],
                                  GUIDE_SELECTED[2], 255))
            is_action = kind == "action"
            lab_color = CYAN if (is_action and key in ("save_current", "save_new")) \
                else (CHANNEL_GREEN if (is_action and key == "close") else WHITE)
            self._draw_text(d, label, self.font, lab_color, x0 + pad, y0, row_h)
            cy = y0 + row_h // 2
            if kind in ("color", "slider"):
                val = self.colors[key][ci] if kind == "color" else self.scanline
                d.rectangle([sx0, cy - 5, sx1, cy + 5], fill=(0, 0, 0, 255),
                            outline=OSD_BORDER, width=1)
                fillx = sx0 + int((sx1 - sx0) * val / 255)
                bar = CHANNEL_GREEN
                if kind == "color":
                    c = [(255, 90, 90), (90, 255, 120), (110, 160, 255)][ci]
                    bar = (c[0], c[1], c[2], 255)
                d.rectangle([sx0, cy - 5, fillx, cy + 5], fill=bar)
                self._draw_text(d, str(val), self.font, WHITE_DIM,
                                0, y0, row_h, right_edge=val_right)
            elif kind == "toggle":
                on = getattr(self, key)
                self._draw_text(d, "ON" if on else "OFF", self.font,
                                CHANNEL_GREEN if on else GRAY,
                                0, y0, row_h, right_edge=val_right)

        # Scroll hints (only when the window is too short to show every row),
        # centered in the panel margins so they never overlap a row's value.
        cxh = px + pw // 2
        if self._scroll > 0:
            self._draw_text(d, "^", self.font, CYAN, cxh, py + title_h - row_h, row_h)
        if self._scroll + vis < len(self._rows):
            self._draw_text(d, "v", self.font, CYAN, cxh, py + ph - 14, 12)
        return img
