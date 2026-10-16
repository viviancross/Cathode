"""Skins draw screens. A skin has a fixed canvas size (its own resolution,
scaled to the window by the GPU), its fonts and colours, and one draw_<name>
method per screen it knows. Screens it doesn't know fall back to Classic."""

import os
from typing import Optional

import pygame

from .. import paths

# System faces for characters a skin's own font lacks (Arabic, CJK, Thai,
# Indic, emoji...), first match wins. Windows, macOS and Linux families.
FALLBACK_FAMILIES = [
    "arial", "dejavusans", "notosans", "liberationsans", "helvetica",
    "microsoftyahei", "msgothic", "malgungothic", "pingfangsc", "hiraginosans", "applesdgothicneo",
    "notosanscjksc", "notosanscjk", "wenquanyimicrohei", "droidsansfallback",
    "nirmalaui", "leelawadeeui", "tahoma", "notosansthai", "notosansdevanagari", "kohinoordevanagari",
    "segoeuiemoji", "segoeuisymbol", "applecoloremoji", "notocoloremoji", "symbola",
]


def _rtl_script(ch: str) -> str:
    """'Arab' or 'Hebr' for a right-to-left letter, '' otherwise."""
    o = ord(ch)
    if 0x0590 <= o <= 0x05FF or 0xFB1D <= o <= 0xFB4F:
        return "Hebr"
    if 0x0600 <= o <= 0x08FF or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF:
        return "Arab"
    return ""


class Text:
    """Fonts by (file, size), with text placed by the top of its ink rather
    than the font's ascent: pixel fonts carry very different top bearings, and
    rows laid out by ascent drift from font to font."""

    def __init__(self):
        self._fonts = {}
        self._ink = {}
        self._cap = {}
        self._path = {}         # font -> the file it came from
        self._has = {}          # (font, char) -> the font draws it
        self._notdef = {}       # font -> its missing-glyph box, rendered
        self._alt = {}          # (path, size, script) -> a fallback or RTL font
        self._fallbacks = None  # the system faces found, in order

    def font(self, file: str, size: int) -> pygame.font.Font:
        key = (file, size)
        f = self._fonts.get(key)
        if f is None:
            path = paths.asset("fonts", file)
            f = pygame.font.Font(path if os.path.exists(path) else None, size)
            self._fonts[key] = f
            self._path[f] = path if os.path.exists(path) else None
            r = f.render("Ag", True, (255, 255, 255)).get_bounding_rect()
            self._ink[f] = (r.y, r.h)
        return f

    # ── Characters the font lacks: drawn in a system face that has them ──

    def _draws(self, font, ch: str) -> bool:
        key = (font, ch)
        got = self._has.get(key)
        if got is None:
            if font not in self._notdef:
                self._notdef[font] = pygame.image.tobytes(font.render("\U0010FFFD", True, (255, 255, 255),
                                                                       (0, 0, 0)), "RGB")
            got = self._has[key] = pygame.image.tobytes(font.render(ch, True, (255, 255, 255), (0, 0, 0)),
                                                        "RGB") != self._notdef[font]
        return got

    def _variant(self, path, size, script, bold):
        """A font for `path` at `size`, set up for a right-to-left script."""
        key = (path, size, script, bold)
        f = self._alt.get(key)
        if f is None:
            f = self._alt[key] = pygame.font.Font(path, size)
            self._path[f] = path
            f.bold = bold and "bold" not in str(path).lower()
            if script:
                f.set_direction(pygame.DIRECTION_RTL)
                f.set_script(script)
            r = f.render("Ag", True, (255, 255, 255)).get_bounding_rect()
            self._ink[f] = (r.y, r.h)
        return f

    def _font_for(self, font, ch: str):
        """The font that draws ch: the skin's own, else the first system
        face that has it, else the skin's own (a box beats nothing)."""
        if ch.isspace() or self._draws(font, ch):
            return font
        if self._fallbacks is None:
            seen, self._fallbacks = set(), []
            for fam in FALLBACK_FAMILIES:
                p = pygame.font.match_font(fam)
                if p and p not in seen:
                    seen.add(p)
                    self._fallbacks.append(p)
        for p in self._fallbacks:
            f = self._variant(p, font.point_size, "", self._bold(font))
            if self._draws(f, ch):
                return f
        return font

    def _bold(self, font) -> bool:
        return font.bold or "bold" in str(self._path.get(font, "")).lower()

    def runs(self, font, s: str) -> list:
        """[(font, text)] in display order: s split where the drawing font
        changes. Right-to-left letters get a shaping font; spaces and
        punctuation between them stay in their run, numbers stay left-to-
        right, and a line that starts right-to-left lays its runs out from
        the right. (A light bidi: enough for names and titles, not the full
        Unicode algorithm.)"""
        if s.isascii():
            return [(font, s)]
        out, rtl = [], []           # runs, and which of them read right-to-left
        for ch in s:
            script = _rtl_script(ch)
            neutral = not script and not ch.isalnum()
            if neutral and rtl and rtl[-1] and self._draws(out[-1][0], ch):
                out[-1] = (out[-1][0], out[-1][1] + ch)     # a space inside right-to-left text
                continue
            f = self._font_for(font, ch)
            if script:
                f = self._variant(self._path.get(f), f.point_size, script, self._bold(font))
            if out and out[-1][0] is f:
                out[-1] = (f, out[-1][1] + ch)
            else:
                out.append((f, ch))
                rtl.append(bool(script))
        first = next((_rtl_script(ch) != "" for ch in s if ch.isalpha()), False)
        if not first:
            # Left-to-right line: spaces trailing a right-to-left run belong after it.
            fixed = []
            for (f, t), r in zip(out, rtl):
                tail = t[len(t.rstrip()):] if r else ""
                fixed.append((f, t[:len(t) - len(tail)] if tail else t))
                if tail:
                    fixed.append((font, tail))
            return [(f, t) for f, t in fixed if t]
        return out[::-1]

    def render(self, font, s: str, color):
        """(surface, extra) for s in font; extra is how far the surface's
        top sits above where font's own render would start (a taller
        fallback face), 0 for most text."""
        runs = self.runs(font, s)
        if len(runs) == 1 and runs[0][0] is font:
            return font.render(s, True, color), 0
        imgs = [(f, f.render(t, True, color)) for f, t in runs]
        base = max(f.get_ascent() for f, _ in imgs)
        h = base + max(img.get_height() - f.get_ascent() for f, img in imgs)
        surf = pygame.Surface((sum(img.get_width() for _, img in imgs), h), pygame.SRCALPHA)
        x = 0
        for f, img in imgs:
            surf.blit(img, (x, base - f.get_ascent()))
            x += img.get_width()
        return surf, base - font.get_ascent()

    def ink(self, font) -> tuple:
        """(offset from the render's top to the ink's top, ink height)."""
        return self._ink[font]

    def cap(self, font) -> int:
        """Cap height: centring capitals on this, not on ink() (which runs
        down to the descenders), sits them optically in the middle."""
        h = self._cap.get(font)
        if h is None:
            h = self._cap[font] = font.render("H", True, (255, 255, 255)).get_bounding_rect().h
        return h

    def width(self, font, s: str) -> int:
        return sum(f.size(t)[0] for f, t in self.runs(font, s))

    def fit(self, font, s: str, max_w: int) -> str:
        """s, cut with ASCII '...' to fit max_w (pixel fonts have no ellipsis).
        A binary search, so a runaway title can't stall a frame."""
        if max_w <= 0:
            return ""
        if self.width(font, s) <= max_w:
            return s
        lo, hi = 0, len(s)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.width(font, s[:mid] + "...") <= max_w:
                lo = mid
            else:
                hi = mid - 1
        s = s[:lo]
        return s.rstrip() + "..." if s else ""

    def wrap(self, font, s: str, max_w: int, max_lines: int) -> list:
        """Word-wrap into at most max_lines; text that doesn't fit ends the
        last line with '...'."""
        words, lines, line = (s or "").split(), [], ""
        for i, w in enumerate(words):
            trial = f"{line} {w}".strip()
            if self.width(font, trial) <= max_w:
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
        img, extra = self.render(font, s, color[:3])
        if len(color) > 3 and color[3] < 255:
            img.set_alpha(color[3])
        w = img.get_width()
        x = x - w if align == "right" else x - w // 2 if align == "center" else x
        y = y - self._ink[font][0] - extra
        if outline:
            ring, _ = self.render(font, s, outline[:3])
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
    "barlow": ("Barlow-Medium.ttf", "Barlow-Bold.ttf", "Barlow"),
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
    poster_wall = True          # On Demand titles may show as a poster wall
    keyboard_layer = "abc"      # the case the on-screen keyboard opens in
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

    def page_video_box(self, screen):
        """Where a full page (On Demand, item info, keyboard, diagnostics)
        keeps the picture; None hides it."""
        return None

    def keyboard_rows(self, layer):
        """The on-screen keyboard's rows for a layer, action rows included
        (SHIFT, SYM, SPACE, DEL, CLEAR, CANCEL, DONE); None for the standard
        layout."""
        return None

    @staticmethod
    def pct(frac) -> str:
        """' 40%' for a known fraction, '' otherwise."""
        return f" {int(frac * 100)}%" if frac is not None and frac >= 0 else ""

    KEY_WORDS = {}          # this skin's own words for remote buttons in hints

    def k(self, action: str) -> str:
        """What a hint calls a remote button: the chosen remote's name for
        it, else this skin's word, else Cathode's."""
        from ..remote import button_name
        remote = getattr(getattr(self.app, "config", None), "remote", "")
        return button_name(remote, action, self.KEY_WORDS.get(action, ""))

    def empty_guide(self, g) -> str:
        """What a guide list with no channels says (only Favorites can be)."""
        if g.category == "Favorites":
            hint = getattr(self.app, "press_hint", None)
            return f"No favorites yet. Press {hint('FAV') if hint else 'FAV'} on a channel to add it."
        return "No channels in this list."

    def guide_pct(self) -> str:
        """The app's guide load, as pct() puts it."""
        return self.pct(getattr(self.app, "guide_progress", None))

    def draw_note(self, c, text: str):
        """A key's notice (the picture format, subtitles) in this skin's style."""
        self.draw_toast(c, text)

    def draw_guide_progress(self, c, frac):
        """A guide load's truthful progress (frac -1 when the size is
        unknown), while live TV or the guide is up."""
        self.draw_toast(c, "Updating guide data..." + self.pct(frac))

    def menu_cols(self, menu) -> int:
        """How many columns this skin lays a menu page out in (1 = a list).
        Grids fill a column before the next (1-5 down the left, 6-0 down the
        right, as the boxes numbered them); UP/DOWN move in a column and
        LEFT/RIGHT across."""
        return 1

    def menu_rows(self, menu) -> int:
        """Rows in each column of a grid menu."""
        cols = max(1, self.menu_cols(menu))
        return max(1, -(-len(menu.items) // cols))

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
