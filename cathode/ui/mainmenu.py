"""Main menu / home screen — logo, title and the New Playlist / Load Playlist /
Options / Exit buttons.  Shown full-screen on launch (and reachable again from
the context menu).  Navigable by keyboard, controller and mouse.  ASCII only.
"""

from __future__ import annotations

import os
import sys
from typing import Callable, Optional

from PIL import Image, ImageDraw

from .theme import (
    get_font, OSD_BG, OSD_BORDER, WHITE, WHITE_DIM, CYAN, YELLOW, GRAY,
    CHANNEL_GREEN, GUIDE_SELECTED,
)

# (key, label) for each button, top to bottom.
_BUTTONS = [
    ("new",     "New Playlist"),
    ("load",    "Load Playlist"),
    ("options", "Options"),
    ("exit",    "Exit"),
]


def _logo_path() -> Optional[str]:
    """Locate assets/cathode.png, frozen-aware (PyInstaller bundle)."""
    cands = []
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        cands.append(os.path.join(os.path.dirname(sys.executable), "assets", "cathode.png"))
        cands.append(os.path.join(base, "assets", "cathode.png"))
    cands.append(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "cathode.png"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


class MainMenu:
    def __init__(self, width: int, height: int):
        self.open = False
        self.width = width
        self.height = height
        self._sel = 0
        self._on_select: Optional[Callable] = None
        self._logo_src = None
        self._load_logo()
        self._build_fonts()

    def _load_logo(self):
        p = _logo_path()
        if p:
            try:
                self._logo_src = Image.open(p).convert("RGBA")
            except Exception:
                self._logo_src = None

    def _build_fonts(self):
        h = self.height
        self.font_title = get_font(max(28, int(h * 0.085)))
        self.font_sub = get_font(max(12, int(h * 0.024)))
        self.font_btn = get_font(max(16, int(h * 0.034)))
        # Pre-scale the logo to ~26% of screen height.
        self._logo = None
        if self._logo_src is not None:
            size = max(48, int(h * 0.26))
            self._logo = self._logo_src.resize((size, size), Image.LANCZOS)

    def resize(self, w, h):
        self.width, self.height = w, h
        self._build_fonts()

    def refresh_fonts(self):
        self._build_fonts()

    # ── open / state ──────────────────────────────────────────────────────

    def show(self, on_select: Callable):
        self._on_select = on_select
        self._sel = 0
        self.open = True

    def close(self):
        self.open = False

    # ── navigation ────────────────────────────────────────────────────────

    def move_up(self):
        self._sel = (self._sel - 1) % len(_BUTTONS)

    def move_down(self):
        self._sel = (self._sel + 1) % len(_BUTTONS)

    def press(self):
        key = _BUTTONS[self._sel][0]
        if self._on_select:
            self._on_select(key)

    confirm = press

    # ── geometry / mouse ──────────────────────────────────────────────────

    def _button_rects(self):
        bw = int(self.width * 0.40)
        bh = max(40, int(self.height * 0.085))
        gap = max(10, int(self.height * 0.022))
        x0 = (self.width - bw) // 2
        total = len(_BUTTONS) * bh + (len(_BUTTONS) - 1) * gap
        # Buttons sit in the lower half, below the logo/title block.
        top = int(self.height * 0.50)
        if top + total > self.height - int(self.height * 0.05):
            top = self.height - int(self.height * 0.05) - total
        out = []
        for i in range(len(_BUTTONS)):
            y0 = top + i * (bh + gap)
            out.append((i, x0, y0, x0 + bw, y0 + bh))
        return out

    def hit_test(self, x, y):
        for (i, x0, y0, x1, y1) in self._button_rects():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return i
        return None

    def set_hover(self, x, y):
        i = self.hit_test(x, y)
        if i is not None:
            self._sel = i

    def click(self, x, y):
        i = self.hit_test(x, y)
        if i is None:
            return
        self._sel = i
        self.press()

    # ── render ────────────────────────────────────────────────────────────

    def render(self) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        if not self.open:
            return img
        d = ImageDraw.Draw(img)
        # Opaque retro backdrop with a subtle inner frame.
        bg = (OSD_BG[0] // 2, OSD_BG[1] // 2, OSD_BG[2] // 2, 255)
        d.rectangle([0, 0, self.width, self.height], fill=(6, 6, 12, 255))
        m = max(16, int(self.width * 0.03))
        d.rectangle([m, m, self.width - m, self.height - m],
                    fill=bg, outline=OSD_BORDER, width=3)

        # Logo (centered, upper area)
        cx = self.width // 2
        top_y = int(self.height * 0.08)
        if self._logo is not None:
            lw, lh = self._logo.size
            img.alpha_composite(self._logo, (cx - lw // 2, top_y))
            title_y = top_y + lh + int(self.height * 0.01)
        else:
            title_y = int(self.height * 0.18)

        # Title + subtitle
        self._centered(d, "CATHODE", self.font_title, title_y, CYAN)
        bb = d.textbbox((0, 0), "CATHODE", font=self.font_title)
        sub_y = title_y + (bb[3] - bb[1]) + int(self.height * 0.012)
        self._centered(d, "R E T R O   I P T V", self.font_sub, sub_y, YELLOW)

        # Version footer (matches the build version)
        try:
            from .. import __version__ as _ver
        except Exception:
            _ver = ""
        if _ver:
            self._centered(d, f"v{_ver}", self.font_sub,
                           self.height - int(self.height * 0.05), GRAY)

        # Buttons
        for (i, x0, y0, x1, y1) in self._button_rects():
            sel = (i == self._sel)
            fill = (GUIDE_SELECTED[0], GUIDE_SELECTED[1], GUIDE_SELECTED[2], 255) \
                if sel else (OSD_BG[0], OSD_BG[1], OSD_BG[2], 255)
            outline = CHANNEL_GREEN if sel else OSD_BORDER
            d.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=fill,
                                outline=outline, width=2 if not sel else 3)
            label = _BUTTONS[i][1]
            lbb = d.textbbox((0, 0), label, font=self.font_btn)
            lw = lbb[2] - lbb[0]
            lh = lbb[3] - lbb[1]
            tx = x0 + (x1 - x0 - lw) // 2 - lbb[0]
            ty = y0 + (y1 - y0 - lh) // 2 - lbb[1]
            d.text((tx, ty), label, font=self.font_btn,
                   fill=WHITE if sel else WHITE_DIM)
        return img

    def _centered(self, d, text, font, y, color):
        bb = d.textbbox((0, 0), text, font=font)
        w = bb[2] - bb[0]
        d.text(((self.width - w) // 2 - bb[0], y), text, font=font, fill=color)
