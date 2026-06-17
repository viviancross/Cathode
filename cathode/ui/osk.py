"""On-screen keyboard overlay — in-app text entry (replaces tkinter dialogs).

Driven by the same inputs as the rest of the UI: arrow keys / Enter / Esc, the
Steam Deck controller (mapped to those), and mouse hover + click.  Used for the
M3U / XMLTV URLs and for naming profiles.  All glyphs are ASCII (pixel fonts).
"""

from __future__ import annotations

from typing import Callable, Optional

from PIL import Image, ImageDraw

from .theme import (
    get_font, OSD_BG, OSD_BORDER, WHITE, WHITE_DIM, CYAN, YELLOW, GRAY,
    BLACK, CHANNEL_GREEN, GUIDE_SELECTED,
)

_SPECIAL = {"SHIFT", "SPACE", "DEL", "CLR", "CANCEL", "DONE"}

_ROWS = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl"),
    list("zxcvbnm"),
    list("./:-_?=&%@~#+,"),
    ["SHIFT", "SPACE", "DEL", "CLR", "CANCEL", "DONE"],
]


class OnScreenKeyboard:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.open = False
        self.text = ""
        self.prompt = ""
        self._shift = False
        self._sel = [0, 0]
        self._on_done: Optional[Callable] = None
        self._on_cancel: Optional[Callable] = None
        self._build_fonts()

    def _build_fonts(self):
        self.font = get_font(max(16, int(self.height * 0.034)))
        self.font_small = get_font(max(13, int(self.height * 0.026)))

    def resize(self, width, height):
        self.width, self.height = width, height
        self._build_fonts()

    def refresh_fonts(self):
        self._build_fonts()

    # ── open / finish ─────────────────────────────────────────────────────

    def show(self, prompt: str, initial: str = "",
             on_done: Optional[Callable] = None,
             on_cancel: Optional[Callable] = None):
        self.prompt = prompt
        self.text = initial or ""
        self._shift = False
        self._sel = [0, 0]
        self._on_done = on_done
        self._on_cancel = on_cancel
        self.open = True

    def _finish(self, result: Optional[str]):
        self.open = False
        done, cancel = self._on_done, self._on_cancel
        self._on_done = self._on_cancel = None
        if result is not None and done:
            done(result)
        elif result is None and cancel:
            cancel()

    # ── navigation / input ────────────────────────────────────────────────

    def move(self, dr: int, dc: int):
        r, c = self._sel
        if dr:
            r = (r + dr) % len(_ROWS)          # wrap top/bottom
            c = min(c, len(_ROWS[r]) - 1)
        if dc:
            c = (c + dc) % len(_ROWS[r])        # wrap left/right
        self._sel = [r, c]

    def move_up(self):    self.move(-1, 0)
    def move_down(self):  self.move(1, 0)
    def move_left(self):  self.move(0, -1)
    def move_right(self): self.move(0, 1)

    def press(self):
        """Activate the highlighted on-screen key (the 'Select' action)."""
        cell = _ROWS[self._sel[0]][self._sel[1]]
        self._activate(cell)

    def confirm(self):
        """Submit the entered text (what Enter does)."""
        self._finish(self.text)

    def _activate(self, cell: str):
        if cell == "SHIFT":
            self._shift = not self._shift
        elif cell == "SPACE":
            self.text += " "
        elif cell == "DEL":
            self.text = self.text[:-1]
        elif cell == "CLR":
            self.text = ""
        elif cell == "CANCEL":
            self._finish(None)
        elif cell == "DONE":
            self._finish(self.text)
        else:
            self.text += cell.upper() if (self._shift and cell.isalpha()) else cell

    def cancel(self):
        self._finish(None)

    def backspace(self):
        self.text = self.text[:-1]

    def insert(self, text: str):
        """Append typed or pasted text (newlines stripped)."""
        if not text:
            return
        self.text += text.replace("\r", "").replace("\n", "")

    # ── geometry / hit-test / render ──────────────────────────────────────

    def _geom(self):
        pw = int(self.width * 0.82)
        px = (self.width - pw) // 2
        key_h = max(30, int(self.height * 0.072))
        gap = max(4, int(self.width * 0.006))
        field_h = key_h + 10
        ph = int(self.height * 0.06) + field_h + len(_ROWS) * (key_h + gap) + 24
        py = (self.height - ph) // 2
        return px, py, pw, ph, key_h, gap, field_h

    def _key_rects(self):
        px, py, pw, ph, key_h, gap, field_h = self._geom()
        top = py + int(self.height * 0.06) + field_h + 8
        rects = []
        for r, row in enumerate(_ROWS):
            n = len(row)
            kw = (pw - gap * (n + 1)) / n
            ry = top + r * (key_h + gap)
            for c in range(n):
                kx = px + gap + c * (kw + gap)
                rects.append((r, c, int(kx), int(ry), int(kx + kw), int(ry + key_h)))
        return rects

    def hit_test(self, x, y):
        for (r, c, x0, y0, x1, y1) in self._key_rects():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return r, c
        return None

    def set_hover(self, x, y):
        hit = self.hit_test(x, y)
        if hit:
            self._sel = [hit[0], hit[1]]

    def click(self, x, y):
        hit = self.hit_test(x, y)
        if hit:
            self._sel = [hit[0], hit[1]]
            self.press()
            return True
        return False

    def render(self) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        if not self.open:
            return img
        d = ImageDraw.Draw(img)
        px, py, pw, ph, key_h, gap, field_h = self._geom()
        # Fully opaque dialog — no video shows through anywhere while typing.
        # (ImageDraw fills REPLACE pixels incl. alpha, so every fill is alpha 255.)
        panel_bg = (OSD_BG[0], OSD_BG[1], OSD_BG[2], 255)
        key_bg = (min(255, OSD_BG[0] + 26), min(255, OSD_BG[1] + 26),
                  min(255, OSD_BG[2] + 30), 255)
        sel_bg = (GUIDE_SELECTED[0], GUIDE_SELECTED[1], GUIDE_SELECTED[2], 255)
        d.rectangle([0, 0, self.width, self.height], fill=(8, 8, 14, 255))
        d.rectangle([px, py, px + pw, py + ph], fill=panel_bg)
        d.rectangle([px, py, px + pw, py + ph], outline=OSD_BORDER, width=2)

        pad = 16
        # Prompt + a hint that real-keyboard typing / paste also work
        d.text((px + pad, py + 10), self.prompt, font=self.font_small, fill=YELLOW)
        hint = "type or Ctrl+V to paste"
        hb = d.textbbox((0, 0), hint, font=self.font_small)
        d.text((px + pw - pad - (hb[2] - hb[0]), py + 10),
               hint, font=self.font_small, fill=GRAY)
        # Text field
        fy = py + int(self.height * 0.06)
        d.rectangle([px + pad, fy, px + pw - pad, fy + field_h - 6], fill=BLACK)
        d.rectangle([px + pad, fy, px + pw - pad, fy + field_h - 6],
                    outline=OSD_BORDER, width=1)
        shown = self.text + "_"
        # keep the end visible for long URLs
        while shown and d.textlength(shown, font=self.font) > (pw - 2 * pad - 16):
            shown = shown[1:]
        d.text((px + pad + 8, fy + 6), shown, font=self.font, fill=CHANNEL_GREEN)

        # Keys
        for (r, c, x0, y0, x1, y1) in self._key_rects():
            cell = _ROWS[r][c]
            selected = [r, c] == self._sel
            d.rectangle([x0, y0, x1, y1], fill=(sel_bg if selected else key_bg))
            d.rectangle([x0, y0, x1, y1], outline=OSD_BORDER, width=1)
            label = cell
            if cell == "SPACE":
                label = "SPACE"
            elif cell == "SHIFT":
                label = "SHIFT*" if self._shift else "SHIFT"
            elif len(cell) == 1 and self._shift and cell.isalpha():
                label = cell.upper()
            color = WHITE
            if cell == "DONE":
                color = CHANNEL_GREEN
            elif cell == "CANCEL":
                color = WHITE_DIM
            bb = d.textbbox((0, 0), label, font=self.font_small)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            d.text((x0 + ((x1 - x0) - tw) // 2, y0 + ((y1 - y0) - th) // 2 - bb[1]),
                   label, font=self.font_small, fill=color)
        return img
