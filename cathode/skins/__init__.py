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


class Skin:
    name = "base"
    canvas = (1280, 720)
    nearest = False             # pixel-art upscale (SD skins) vs smooth
    tune_cover = "static"       # what covers a channel change: static | black

    def __init__(self, app):
        self.app = app
        self.text = Text()
        self._logo_surfaces = {}
        self.hits = []          # [(Rect, fn)] clickable this frame, in canvas pixels

    def reload(self):
        """Pick up changed settings (theme, font)."""

    def hit(self, rect, fn):
        """Register a clickable region while drawing."""
        self.hits.append((pygame.Rect(rect), fn))

    def draw(self, canvas, screen):
        fn = getattr(self, f"draw_{screen.name}", None)
        if fn:
            fn(canvas, screen)

    def logo(self, url: str, max_w: int, max_h: int) -> Optional[pygame.Surface]:
        """A channel logo fitted to the box, as a pygame surface; None while it
        loads or when there isn't one."""
        if not url or not self.app.logos:
            return None
        key = (url, max_w, max_h)
        surf = self._logo_surfaces.get(key)
        if surf is None:
            im = self.app.logos.get(url, max_w, max_h)
            if im is None:
                return None
            surf = pygame.image.frombytes(im.convert("RGBA").tobytes(), im.size, "RGBA")
            if len(self._logo_surfaces) > 512:
                self._logo_surfaces.clear()
            self._logo_surfaces[key] = surf
        return surf


def load_skin(name: str, app) -> Skin:
    from .classic import Classic
    skins = {"classic": Classic}
    return skins.get(name, Classic)(app)
