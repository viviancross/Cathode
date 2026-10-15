"""Skins draw screens. A skin has a fixed canvas size (its own resolution,
scaled to the window by the GPU), its fonts and colours, and one draw_<name>
method per screen it knows. Screens it doesn't know fall back to Classic."""

import os
from typing import Optional

import pygame

from .. import paths


class Text:
    """Fonts by (file, size), with text placed by the top of its ink rather
    than the font's ascent: pixel fonts carry very different top bearings, and
    rows laid out by ascent drift from font to font."""

    def __init__(self):
        self._fonts = {}
        self._ink = {}

    def font(self, file: str, size: int) -> pygame.font.Font:
        key = (file, size)
        f = self._fonts.get(key)
        if f is None:
            path = paths.asset("fonts", file)
            f = pygame.font.Font(path if os.path.exists(path) else None, size)
            self._fonts[key] = f
            r = f.render("Ag", True, (255, 255, 255)).get_bounding_rect()
            self._ink[f] = (r.y, r.h)
        return f

    def ink(self, font) -> tuple:
        """(offset from the render's top to the ink's top, ink height)."""
        return self._ink[font]

    @staticmethod
    def width(font, s: str) -> int:
        return font.size(s)[0]

    def fit(self, font, s: str, max_w: int) -> str:
        """s, cut with ASCII '...' to fit max_w (pixel fonts have no ellipsis)."""
        if max_w <= 0:
            return ""
        if font.size(s)[0] <= max_w:
            return s
        while s and font.size(s + "...")[0] > max_w:
            s = s[:-1]
        return s.rstrip() + "..." if s else ""

    def wrap(self, font, s: str, max_w: int, max_lines: int) -> list:
        """Word-wrap into at most max_lines; text that doesn't fit ends the
        last line with '...'."""
        words, lines, line = (s or "").split(), [], ""
        for i, w in enumerate(words):
            trial = f"{line} {w}".strip()
            if font.size(trial)[0] <= max_w:
                line = trial
                continue
            if line:
                lines.append(line)
            if len(lines) == max_lines:
                lines[-1] = self.fit(font, lines[-1] + " " + " ".join(words[i:]), max_w)
                return lines
            line = w
        if line:
            lines.append(line)
        return lines

    def draw(self, surface, s: str, font, color, x, y, align="left", outline=None):
        """Draw with the ink's top at y. align: left | right | center (on x)."""
        if not s:
            return 0
        img = font.render(s, True, color[:3])
        if len(color) > 3 and color[3] < 255:
            img.set_alpha(color[3])
        w = img.get_width()
        x = x - w if align == "right" else x - w // 2 if align == "center" else x
        y = y - self._ink[font][0]
        if outline:
            ring = font.render(s, True, outline[:3])
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (-1, 1), (1, -1)):
                surface.blit(ring, (x + dx, y + dy))
        surface.blit(img, (x, y))
        return w


# Fonts a skin can draw with: key -> (regular file, bold file or None, label).
FONTS = {
    "sans": ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf", "Liberation Sans"),
    "vcr": ("VCR_OSD_MONO.ttf", None, "VCR OSD Mono"),
    "ibm": ("PxPlus_IBM_VGA8.ttf", None, "IBM VGA"),
    "vt220": ("Glass_TTY_VT220.ttf", None, "Glass TTY VT220"),
    "pixelop": ("PixelOperator.ttf", None, "Pixel Operator"),
    "vt323": ("VT323-Regular.ttf", None, "VT323"),
    "jersey": ("Jersey10-Regular.ttf", None, "Jersey 10"),
}


class Skin:
    name = "base"
    label = "Base"
    canvas = (1280, 720)
    nearest = False             # pixel-art upscale (SD skins) vs smooth
    tune_cover = "static"       # what covers a channel change: static | black
    right_is_browse = False     # RIGHT on live TV browses (Dish) instead of volume
    browse_style = "banner"     # BROWSE shows: banner (one channel) | mini (a mini guide)
    guide_jump_min = 24 * 60    # how far REW / FF move the guide
    default_font = "vcr"

    def __init__(self, app):
        self.app = app
        self.text = Text()
        self._logo_surfaces = {}
        self.hits = []          # [(Rect, fn)] clickable this frame, in canvas pixels

    def reload(self):
        """Pick up changed settings (theme, font)."""

    # ── Per-skin look settings (theme, font) ──────────────────────────────
    # Each skin keeps its own, so switching skins doesn't drag one skin's
    # font or colours onto another. Classic keeps 3.x's config fields.

    def font_key(self) -> str:
        return self.app.config.skin_fonts.get(self.name, self.default_font)

    def set_font_key(self, key: str):
        self.app.config.skin_fonts[self.name] = key

    def theme_key(self) -> str:
        return self.app.config.skin_themes.get(self.name, "native")

    def set_theme_key(self, key: str):
        self.app.config.skin_themes[self.name] = key

    def custom_base(self) -> dict:
        return self.app.config.skin_custom.get(self.name) or {}

    def set_custom_base(self, base: dict):
        self.app.config.skin_custom[self.name] = base

    def theme_choices(self) -> list:
        """(key, label) pairs for the Color theme setting."""
        from .. import palette
        return [(k, palette.THEME_LABELS[k]) for k in palette.THEME_ORDER] + [("custom", "Custom")]

    def native_base(self) -> dict:
        """Base colours of this skin's own look (the theme editor's start)."""
        from .. import palette
        return palette.base_colors("blue")

    def menu_video_box(self, menu):
        """Where a menu wants the video; None leaves it to the screen below."""
        return None

    def menu_cols(self, menu) -> int:
        """How many columns this skin lays a menu page out in (1 = a list).
        Grids move LEFT/RIGHT across and UP/DOWN by a row."""
        return 1

    def f(self, size: int, bold: bool = False):
        regular, heavy, _ = FONTS.get(self.font_key(), FONTS[self.default_font])
        return self.text.font(heavy if bold and heavy else regular, size)

    def fb(self, size: int):
        return self.f(size, bold=True)

    def hit(self, rect, fn):
        """Register a clickable region while drawing."""
        self.hits.append((pygame.Rect(rect), fn))

    def draw(self, canvas, screen):
        fn = getattr(self, f"draw_{screen.name}", None)
        if fn:
            fn(canvas, screen)

    def logo(self, url: str, max_w: int, max_h: int, headers=None) -> Optional[pygame.Surface]:
        """A channel logo or poster fitted to the box, as a pygame surface;
        None while it loads or when there isn't one. `headers` (a Plex token)
        go with the fetch but never into the URL or the cache name."""
        if not url or not self.app.logos:
            return None
        key = (url, max_w, max_h)
        surf = self._logo_surfaces.get(key)
        if surf is None:
            im = self.app.logos.get(url, max_w, max_h, headers=headers)
            if im is None:
                return None
            surf = pygame.image.frombytes(im.convert("RGBA").tobytes(), im.size, "RGBA")
            if len(self._logo_surfaces) > 512:
                self._logo_surfaces.clear()
            self._logo_surfaces[key] = surf
        return surf


def skin_classes() -> dict:
    """name -> skin class, in the order the Skin setting cycles them."""
    from .classic import Classic
    from .indirect import InDirect, InDirectHD
    from .plate import Plate, PlateHD
    return {c.name: c for c in (Classic, InDirect, InDirectHD, Plate, PlateHD)}


def load_skin(name: str, app) -> Skin:
    from .classic import Classic
    return skin_classes().get(name, Classic)(app)
