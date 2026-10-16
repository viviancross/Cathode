"""What the satellite-box skins share: gradients and rounded panels, a sans
face, a black cut on a channel change, and a palette derived from a few base
colours so the screens a box skin doesn't redraw itself (On Demand, the
keyboard, diagnostics) still wear its colours."""

import pygame
from pygame import gfxdraw

from .. import palette
from .classic import Classic


def mix(a, b, t=0.5):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def call_sign(ch, n=5) -> str:
    """A box-style call sign from a channel's name: spaces dropped, cut at
    n letters, no ellipsis (the boxes showed TOON, NICKW, MILT)."""
    return "".join(ch.name.upper().split())[:n]


def readable(bg, ink, floor=4.5):
    """`ink` on `bg` if it reads (WCAG ratio >= floor), else near-black or
    white, whichever reads better: a theme can't make text vanish."""
    from ..palette import contrast
    if contrast(ink, bg) >= floor:
        return ink
    return max(((16, 16, 24), (255, 255, 255)), key=lambda k: contrast(k, bg))


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
    KEY_WORDS = {}                  # not Classic's OK
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
        text, bg, acc = (tuple(base[k]) for k in ("text", "bg", "accent"))

        def bright(c, floor=120):
            """A colour light enough to read on the box's dark pages."""
            c = tuple(c)
            return c if 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] >= floor else mix(c, text, 0.6)

        self.p = dict(self.p, GUIDE_SELECTED=rgba(b["sel"]), SEL_TEXT=rgba(b["sel_ink"]),
                      SEL_TEXT_DIM=rgba(b["sel_ink"], 215), YELLOW=rgba(text),
                      CYAN=rgba(bright(mix(text, acc, 0.3))), CYAN_DIM=rgba(bright(mix(text, acc, 0.5))),
                      ORANGE=rgba(bright(b["sel"])), WHITE_DIM=rgba(mix(text, bg, 0.25)),
                      INK_MUTED=rgba(mix(text, bg, 0.5)))

    def roles(self, base) -> dict:
        return {}

    # The On Demand info buttons, in the boxes' own words.
    BUTTON_WORDS = {"PLAY": "Play", "PLAY ALL": "Play All", "SEASONS": "Seasons", "SHUFFLE": "Shuffle",
                    "+ QUEUE": "Add to Queue", "+ WATCHLIST": "Add to Watchlist",
                    "- WATCHLIST": "Remove from Watchlist", "RECORD": "Record", "RECORDED": "Recorded",
                    "REC WAIT": "Recording Soon", "RESUME": "Resume Recording", "RETRY": "Retry Recording"}

    def button_words(self, label, back="Done"):
        if label == "BACK":
            return back
        if label.startswith("REC "):
            return f"Recording {label[4:]}"
        return self.BUTTON_WORDS.get(label, label.title())

    # On Demand's transport buttons wear the remote's symbols, drawn (no one
    # font has them all), with the seconds on the two seek buttons.
    ICON_W = {"play": 8, "pause": 8, "stop": 8, "back": 11, "fwd": 11, "prev": 9, "next": 9}
    SEEK_SECONDS = {"back": "10", "fwd": "30"}

    def transport_icon(self, c, kind, x, cy, h, ink):
        """The symbol for `kind`, `h` tall, its left edge at x; ICON_W gives
        its width in tenths of h."""
        u, top = h / 10, cy - h / 2

        def tri(base, tip):
            pts = [(round(x + base * u), round(top)), (round(x + base * u), round(top + h)),
                   (round(x + tip * u), round(cy))]
            gfxdraw.aapolygon(c, pts, ink)
            gfxdraw.filled_polygon(c, pts, ink)

        def bar(x0, w, y0=0.0, bh=10.0):
            pygame.draw.rect(c, ink, (round(x + x0 * u), round(top + y0 * u), max(1, round(w * u)), round(bh * u)))

        if kind == "play":
            tri(0, 8)
        elif kind == "pause":
            bar(0, 3)
            bar(5, 3)
        elif kind == "stop":
            bar(0, 8, 1, 8)
        elif kind == "back":
            tri(5.5, 0)
            tri(11, 5.5)
        elif kind == "fwd":
            tri(0, 5.5)
            tri(5.5, 11)
        elif kind == "prev":
            bar(0, 2)
            tri(9, 2)
        elif kind == "next":
            tri(0, 7)
            bar(7, 2)

    def transport_face(self, c, kind, r, ink, f, shadow=None):
        """A transport button's face centred in `r`: the symbol, and the
        seconds after the arrows going back, before them going forward."""
        t = self.text
        h = max(7, r.h * 9 // 20)
        num = self.SEEK_SECONDS.get(kind, "")
        iw = round(self.ICON_W[kind] * h / 10)
        nw = t.width(f, num) if num else 0
        gap = h // 2 if num else 0
        x = r.centerx - (iw + gap + nw) // 2
        ix, nx = (x + nw + gap, x) if kind == "fwd" else (x, x + iw + gap)
        ny = r.y + (r.h - t.ink(f)[1]) // 2
        for d, ink_ in ([(2, shadow)] if shadow else []) + [(0, ink)]:
            self.transport_icon(c, kind, ix + d, r.centery + d, h, ink_)
            if num:
                t.draw(c, num, f, ink_, nx + d, ny + d)

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

    # Classic's screens (On Demand, the keyboard, diagnostics...) lay out in
    # 1280-wide pixels. A 4:3 skin draws them at 1280 x 960 and scales down.

    def layout_canvas(self):
        W, H = self.canvas
        return (W, H) if W == 1280 else (1280, round(1280 * H / W))

    def draw(self, canvas, screen):
        fn = getattr(self, f"draw_{screen.name}", None)
        if not fn:
            return
        inherited = fn.__func__ is getattr(Classic, f"draw_{screen.name}", None)
        big = self.layout_canvas()
        if not inherited or big == self.canvas:
            fn(canvas, screen)
            return
        small = self.canvas
        surf = pygame.Surface(big, pygame.SRCALPHA)
        n = len(self.hits)
        self.canvas = big
        try:
            fn(surf, screen)
        finally:
            self.canvas = small
        sx, sy = small[0] / big[0], small[1] / big[1]
        canvas.blit(pygame.transform.smoothscale(surf, small), (0, 0))
        self.hits[n:] = [(pygame.Rect(int(r.x * sx), int(r.y * sy), int(r.w * sx), int(r.h * sy)), f)
                         for r, f in self.hits[n:]]

    def _click_frac(self, rect) -> float:
        """Where the last click landed across `rect`, which a scaled-down
        screen registered in layout pixels."""
        pt = self.app.gfx.to_canvas(self.canvas, *pygame.mouse.get_pos())
        big = self.layout_canvas()
        x = pt[0] * big[0] / self.canvas[0] if pt else rect.x
        return max(0.0, min(1.0, (x - rect.x) / max(1, rect.w)))

    def draw_live(self, c, live):
        W, H = self.canvas
        if live.message:
            self._message(c, live.message)
            return
        if live.standby and live.phase != "cover":
            self._signal_loss(c)
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
