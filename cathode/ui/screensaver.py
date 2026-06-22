"""Retro screensaver — a bouncing Cathode logo over black with faint scanlines.

Shown by the app after a few minutes idle on a non-playing screen (home menu,
browse, paused). Any input dismisses it. Full-screen and opaque, so the app just
composites it over whatever frame is underneath. ASCII only (pixel fonts).
"""

from __future__ import annotations

import os
import random
import sys
from typing import Optional

from PIL import Image, ImageDraw

from .theme import get_font, CYAN, WHITE_DIM


def _logo_path() -> Optional[str]:
    """Locate assets/cathode.png, frozen-aware (same search as the main menu)."""
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


class Screensaver:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.active = False
        self._logo_src = None
        p = _logo_path()
        if p:
            try:
                self._logo_src = Image.open(p).convert("RGBA")
            except Exception:
                self._logo_src = None
        self._build()

    def _build(self):
        size = max(64, int(self.height * 0.20))
        self.logo = (self._logo_src.resize((size, size), Image.LANCZOS)
                     if self._logo_src is not None else None)
        self.lw, self.lh = (self.logo.size if self.logo is not None else (size, size))
        self.font = get_font(max(14, int(self.height * 0.030)))
        step = max(2, int(self.width * 0.0035))
        self.vx = step
        self.vy = step
        self.x = (self.width - self.lw) // 2
        self.y = (self.height - self.lh) // 2
        # Pre-render faint scanlines once.
        self._scan = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        sd = ImageDraw.Draw(self._scan)
        for yy in range(0, self.height, 3):
            sd.line([(0, yy), (self.width, yy)], fill=(0, 0, 0, 90))

    def resize(self, width: int, height: int):
        self.width, self.height = width, height
        self._build()

    refresh_fonts = _build

    def reset(self):
        """Re-randomize position + direction when (re)activated."""
        self.x = random.randint(0, max(0, self.width - self.lw))
        self.y = random.randint(0, max(0, self.height - self.lh))
        self.vx = abs(self.vx) * random.choice((-1, 1))
        self.vy = abs(self.vy) * random.choice((-1, 1))

    def step(self):
        """Advance one frame; bounce off the edges."""
        self.x += self.vx
        self.y += self.vy
        if self.x <= 0:
            self.x = 0
            self.vx = abs(self.vx)
        elif self.x + self.lw >= self.width:
            self.x = self.width - self.lw
            self.vx = -abs(self.vx)
        if self.y <= 0:
            self.y = 0
            self.vy = abs(self.vy)
        elif self.y + self.lh >= self.height:
            self.y = self.height - self.lh
            self.vy = -abs(self.vy)

    def render(self) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 255))
        if not self.active:
            return img
        ix, iy = int(self.x), int(self.y)
        if self.logo is not None:
            img.alpha_composite(self.logo, (ix, iy))
        else:
            d = ImageDraw.Draw(img)
            d.rectangle([ix, iy, ix + self.lw, iy + self.lh], outline=CYAN, width=3)
        d = ImageDraw.Draw(img)
        label = "CATHODE"
        bb = d.textbbox((0, 0), label, font=self.font)
        lw = bb[2] - bb[0]
        d.text((ix + (self.lw - lw) // 2, iy + self.lh + 6), label,
               font=self.font, fill=WHITE_DIM)
        img.alpha_composite(self._scan)
        return img
