"""What the satellite-box skins share: gradients and rounded panels, a sans
face, a black cut on a channel change, and a palette derived from a few base
colours so the screens a box skin doesn't redraw itself (On Demand, the
keyboard, diagnostics) still wear its colours."""

import pygame

from .. import palette
from .classic import Classic


def mix(a, b, t=0.5):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rgba(c, a=255):
    return (c[0], c[1], c[2], a)


def vgrad(c, rect, top, bottom, radius=0):
    """A vertical gradient (RGB or RGBA ends) filling `rect`, corners
    optionally rounded."""
    rect = pygame.Rect(rect)
    if rect.w <= 0 or rect.h <= 0:
        return
    top, bottom = rgba(top, top[3] if len(top) > 3 else 255), rgba(bottom, bottom[3] if len(bottom) > 3 else 255)
    strip = pygame.Surface((1, 2), pygame.SRCALPHA)
    strip.set_at((0, 0), top)
    strip.set_at((0, 1), bottom)
    g = pygame.transform.smoothscale(strip, (rect.w, rect.h))
    if radius:
        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
        g.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    c.blit(g, rect.topleft)


def panel(c, rect, top, bottom, radius=10, edge=None, edge_w=2):
    vgrad(c, rect, top, bottom, radius)
    if edge:
        pygame.draw.rect(c, edge, rect, edge_w, border_radius=radius)


class BoxSkin(Classic):
    """Base for InDirecTV and Plate Network. Subclasses give `NATIVE` base colours and
    `roles(base)`, their extra colours, and redraw the screens that make a
    box recognisable: banner, guide, menu, browse, boot, signal loss."""
    tune_cover = "black"            # digital boxes cut to black, not snow
    default_font = "sans"
    NATIVE = palette.base_colors("blue")

    def reload(self):
        key = self.theme_key()
        if key == "native":
            base = dict(self.NATIVE)
        elif key == "custom" and self.custom_base():
            base = self.custom_base()
        else:
            base = palette.base_colors(key)
        try:
            self.p = palette.custom(**base)
        except (TypeError, KeyError, IndexError):
            base = dict(self.NATIVE)
            self.p = palette.custom(**base)
        self.b = self.roles({k: tuple(v) for k, v in base.items()})
        # Screens drawn by the shared code select with the box's own colour
        # and title in its text colour, not Classic's derived ones.
        b = self.b
        self.p = dict(self.p, GUIDE_SELECTED=rgba(b["sel"]), SEL_TEXT=rgba(b["sel_ink"]),
                      SEL_TEXT_DIM=rgba(b["sel_ink"], 215), YELLOW=rgba(b["text"]))

    def roles(self, base) -> dict:
        return {}

    # Box skins keep their look in skin_fonts / skin_themes (the base class).
    def font_key(self):
        return self.app.config.skin_fonts.get(self.name, self.default_font)

    def set_font_key(self, key):
        self.app.config.skin_fonts[self.name] = key

    def theme_key(self):
        return self.app.config.skin_themes.get(self.name, "native")

    def set_theme_key(self, key):
        self.app.config.skin_themes[self.name] = key

    def custom_base(self):
        return self.app.config.skin_custom.get(self.name) or {}

    def set_custom_base(self, base):
        self.app.config.skin_custom[self.name] = base

    def native_base(self):
        return {k: list(v) for k, v in self.NATIVE.items()}

    def theme_choices(self):
        return [("native", "Original")] + super().theme_choices()

    # ── Shared pieces ─────────────────────────────────────────────────────

    def menu_video_box(self, menu):
        """Box menus keep a picture window top-right, as the real ones did; a
        full-page grid (the Dish-style Main Menu) covers it."""
        return "hidden" if self.menu_cols(menu) > 1 else self.guide_video_box()

    def draw_live(self, c, live):
        W, H = self.canvas
        if live.message:
            self._message(c, live.message)
            return
        if (live.banner_visible() or live.phase == "cover") and live.channel:
            cur, nxt = live.programs()
            self._banner(c, live.channel, cur, nxt, full=live.banner_full)
        if live.digits:
            self._digits(c, live.digits)
        if live.volume_visible():
            self._volume(c, W // 2, int(H * 0.62))
        if live.trick_visible() and live.phase != "cover":
            self._trick(c, live.trick_state())

    def measure(self, fn, *args) -> int:
        """Width of something drawn by `fn(surface, x, y, *args)`, found by
        drawing it off-screen."""
        return fn(pygame.Surface((1, 1), pygame.SRCALPHA), 0, 0, *args)

    def dim(self, c, alpha=150):
        veil = pygame.Surface(self.canvas, pygame.SRCALPHA)
        veil.fill((0, 0, 0, alpha))
        c.blit(veil, (0, 0))

    def chip(self, c, x, y, text, font, fill, ink, pad=8, radius=6):
        """A small rounded label; returns its rect."""
        w = self.text.width(font, text) + 2 * pad
        h = self.text.ink(font)[1] + 2 * pad
        r = pygame.Rect(x, y, w, h)
        pygame.draw.rect(c, fill, r, border_radius=radius)
        self.text.draw(c, text, font, ink, r.x + pad, r.y + pad)
        return r

    def progress(self, c, rect, frac, track, fill):
        pygame.draw.rect(c, track, rect, border_radius=rect.h // 2)
        if frac > 0:
            done = pygame.Rect(rect.x, rect.y, max(rect.h, int(rect.w * min(1.0, frac))), rect.h)
            pygame.draw.rect(c, fill, done, border_radius=rect.h // 2)
