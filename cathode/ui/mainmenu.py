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
    get_font, OSD_BG, OSD_BORDER, WHITE, WHITE_DIM, CYAN, YELLOW, INK_MUTED,
    CHANNEL_GREEN, GUIDE_SELECTED, SEL_TEXT, SCREEN_BG,
)

# (key, label) for each button, top to bottom.
_BUTTONS = [
    ("new",     "New Playlist"),
    ("load",    "Load Playlist"),
    ("plex",    "Plex-Per-View"),
    ("options", "Options"),
    ("exit",    "Exit"),
]
_DEMO_BUTTON = ("demo", "Demo Channels")


def footer_crowded(width, m, pad, vw, cw, hw) -> bool:
    """Would the centred first-run nudge run into the version or the credit?

    The nudge is centred, so what matters is where its ends land — not whether
    the three widths happen to add up to less than the line, which they can do
    while still overlapping.
    """
    hx = (width - hw) // 2
    return hx < m + pad + vw + pad or hx + hw > width - m - pad - cw - pad


def _logo_path() -> Optional[str]:
    """Locate assets/cathode.png, frozen-aware (PyInstaller bundle)."""
    cands = []
    # Read per call, not at import: a host that can't be found by walking up
    # from __file__ points here instead. Under Chaquopy the .py files are served
    # from inside the APK while the data files are extracted elsewhere, so the
    # two are not siblings on disk and the logo silently doesn't appear.
    override = os.environ.get("CATHODE_ASSETS_DIR", "")
    if override:
        cands.append(os.path.join(override, "cathode.png"))
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
        self.min_btn_h = 0        # physical floor for touch hosts (px)
        self.width = width
        self.height = height
        # First-run nudge: no playlist configured yet — offer the built-in
        # demo channels and say where to add a real source.
        self.demo_hint = False
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
        self.font_foot = get_font(max(11, int(h * 0.020)))   # corner credits
        # Pre-scale the logo. A touch host gets a smaller one: the buttons
        # need the height more than the decoration does, and held upright
        # there is little of it to go round.
        self._logo = None
        if self._logo_src is not None:
            frac = 0.14 if getattr(self, "min_btn_h", 0) else 0.26
            size = max(48, int(h * frac))
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

    def _buttons(self):
        if self.demo_hint:
            return _BUTTONS[:2] + [_DEMO_BUTTON] + _BUTTONS[2:]
        return _BUTTONS

    def move_up(self):
        self._sel = (self._sel - 1) % len(self._buttons())

    def move_down(self):
        self._sel = (self._sel + 1) % len(self._buttons())

    def press(self):
        key = self._buttons()[self._sel][0]
        if self._on_select:
            self._on_select(key)

    confirm = press

    # ── geometry / mouse ──────────────────────────────────────────────────

    def _button_rects(self):
        n = len(self._buttons())
        # 40% of the width is a comfortable button on a television. In a portrait
        # box that same fraction is narrower than the labels, so widen it: the
        # box's own shape decides, not the platform.
        bw = int(self.width * (0.40 if self.width >= self.height else 0.76))
        x0 = (self.width - bw) // 2
        gap = max(8, int(self.height * 0.018))
        # Fit the buttons in the band between the title block and the inner
        # border, shrinking them so every option stays inside the box.
        m = max(16, int(self.width * 0.03))          # matches the border inset
        region_top = int(self.height * 0.50)
        # 0.055h keeps the last button clear of the footer line (version /
        # credit / first-run hint) even with the tallest bundled pixel fonts.
        region_bottom = self.height - m - int(self.height * 0.055)
        # A touch host wants buttons a thumb can hit. Held upright the UI box is
        # short, and the lower half alone cannot give six of them that much
        # height, so take back space from the title block first. It is still a
        # target rather than a guarantee: when even the taller band is too
        # small, buttons that fit beat buttons that overlap the footer.
        floor = getattr(self, "min_btn_h", 0)
        if floor:
            need = n * floor + (n - 1) * gap
            region_top = min(region_top,
                             max(int(self.height * 0.38), region_bottom - need))
        avail = max(1, region_bottom - region_top)
        fit = max(24, (avail - (n - 1) * gap) // n)
        bh = min(int(self.height * 0.085), fit)
        if floor:
            bh = min(max(bh, floor), fit)
        bh = max(24, bh)
        total = n * bh + (n - 1) * gap
        top = region_top + max(0, (avail - total) // 2)   # center in the band
        return [(i, x0, top + i * (bh + gap), x0 + bw, top + i * (bh + gap) + bh)
                for i in range(n)]

    def hit_test(self, x, y):
        for (i, x0, y0, x1, y1) in self._button_rects():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return i
        return None

    def hit_logo(self, x, y) -> bool:
        """The logo is a hidden button (degauss easter egg)."""
        if self._logo is None or not self.open:
            return False
        lw, lh = self._logo.size
        x0 = (self.width - lw) // 2
        y0 = int(self.height * 0.08)
        return x0 <= x <= x0 + lw and y0 <= y <= y0 + lh

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
        d.rectangle([0, 0, self.width, self.height], fill=SCREEN_BG)
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

        # Corner footer: version bottom-left, credit bottom-right (small, inside
        # the inner frame).
        try:
            from .. import __version__ as _ver
        except Exception:
            _ver = ""
        pad = max(8, int(self.width * 0.012))
        fh = d.textbbox((0, 0), "Ag", font=self.font_foot)[3]
        fy = self.height - m - pad - fh
        credit = "made by vivian cross"
        hint = "NO PLAYLIST YET - ADD ONE, OR TRY THE DEMO"
        vw = d.textlength(f"v{_ver}", font=self.font_foot) if _ver else 0
        cw = d.textlength(credit, font=self.font_foot)
        hw = d.textlength(hint, font=self.font_foot) if self.demo_hint else 0
        # Version left, credit right, first-run nudge between them. When all
        # three won't share the line the decoration goes and the instruction
        # stays — it is the only one of the three that tells you what to do.
        hx = (self.width - hw) // 2
        crowded = self.demo_hint and footer_crowded(
            self.width, m, pad, vw, cw, hw)
        if crowded:
            d.text((hx, fy), hint, font=self.font_foot, fill=YELLOW)
        else:
            if _ver:
                d.text((m + pad, fy), f"v{_ver}", font=self.font_foot, fill=INK_MUTED)
            d.text((self.width - m - pad - cw, fy), credit,
                   font=self.font_foot, fill=INK_MUTED)
            if self.demo_hint:
                d.text((hx, fy), hint, font=self.font_foot, fill=YELLOW)

        # Buttons. The font is fitted to the widest label rather than trusted:
        # labels are centred, so one that overflows spills over its neighbours
        # instead of being clipped, and no font is safe at every box shape.
        rects = self._button_rects()
        f_btn = self._fitted_btn_font(
            d, [b[1] for b in self._buttons()],
            (rects[0][3] - rects[0][1]) if rects else self.width)
        for (i, x0, y0, x1, y1) in rects:
            sel = (i == self._sel)
            fill = (GUIDE_SELECTED[0], GUIDE_SELECTED[1], GUIDE_SELECTED[2], 255) \
                if sel else (OSD_BG[0], OSD_BG[1], OSD_BG[2], 255)
            outline = CHANNEL_GREEN if sel else OSD_BORDER
            d.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=fill,
                                outline=outline, width=2 if not sel else 3)
            label = self._buttons()[i][1]
            lbb = d.textbbox((0, 0), label, font=f_btn)
            lw = lbb[2] - lbb[0]
            lh = lbb[3] - lbb[1]
            tx = x0 + (x1 - x0 - lw) // 2 - lbb[0]
            ty = y0 + (y1 - y0 - lh) // 2 - lbb[1]
            d.text((tx, ty), label, font=f_btn,
                   fill=SEL_TEXT if sel else WHITE_DIM)
        return img

    def _fitted_btn_font(self, d, labels, bw):
        """Largest button font whose widest label still fits inside a button."""
        size = max(16, int(self.height * 0.034))
        while size > 10:
            f = get_font(size)
            if max(d.textlength(t, font=f) for t in labels) <= bw - 16:
                return f
            size -= 1
        return get_font(11)

    def _centered(self, d, text, font, y, color):
        # Place the VISIBLE ink at (centered, y): subtract the glyph bbox left/top
        # so the title sits at the same spot under the logo for every font. Pixel
        # fonts (VT323, Jersey 10, Pixel Operator) carry big top bearing, so
        # without this they'd drop well below the logo.
        bb = d.textbbox((0, 0), text, font=font)
        w = bb[2] - bb[0]
        d.text(((self.width - w) // 2 - bb[0], y - bb[1]), text, font=font, fill=color)
