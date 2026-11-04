"""Skins draw screens. A skin has a canvas size (its own resolution, scaled
to the window by the GPU; a 16:9 one grows taller on a squarer window), its
fonts and colours, and one draw_<name> method per screen it knows. Screens it
doesn't know fall back to Classic."""

import os
import time
import weakref
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

    def clip(self, font, s: str, max_w: int, width=None) -> str:
        """The longest start of s that fits max_w, cut plain: no '...'
        (in a grid the cut is plain to see, and the dots would cost the
        letters that tell the shows apart). width: a measure other than
        this face's own (condensed lettering)."""
        width = width or self.width
        if max_w <= 0:
            return ""
        if width(font, s) <= max_w:
            return s
        lo, hi = 0, len(s)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if width(font, s[:mid]) <= max_w:
                lo = mid
            else:
                hi = mid - 1
        return s[:lo].rstrip()

    def lines(self, font, s: str, max_w: int, max_lines: int, width=None) -> tuple:
        """([lines], whole): s word-wrapped into at most max_lines, a word
        wider than the cell cut; whole is False when the last line had to
        be clipped to hold the rest."""
        width = width or self.width
        words, lines, line = (s or "").split(), [], ""
        for i, w in enumerate(words):
            trial = f"{line} {w}".strip()
            if width(font, trial) <= max_w:
                line = trial
                continue
            if line:
                lines.append(line)
            if len(lines) == max_lines:
                lines[-1] = self.clip(font, lines[-1] + " " + " ".join(words[i:]), max_w, width)
                return lines, False
            line = self.clip(font, w, max_w, width) if width(font, w) > max_w else w
            if line != w:                   # a word cut: the rest can't follow it
                if line:
                    lines.append(line)
                return lines, False
        if line:
            lines.append(line)
        return lines, True

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

    def wrap_even(self, font, s: str, max_w: int, max_lines: int) -> list:
        """wrap(), with the lines made as even as the words allow: the
        narrowest width that keeps the same number of lines (for centred
        text, where a long line over a short one looks ragged)."""
        lines = self.wrap(font, s, max_w, max_lines)
        if len(lines) < 2 or lines[-1].endswith("..."):
            return lines
        lo, hi = max_w // 2, max_w
        while lo < hi:
            mid = (lo + hi) // 2
            trial = self.wrap(font, s, mid, max_lines)
            if len(trial) == len(lines) and not trial[-1].endswith("..."):
                hi = mid
            else:
                lo = mid + 1
        return self.wrap(font, s, hi, max_lines)

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
    "narrow": ("ArchivoNarrow-Regular.ttf", "ArchivoNarrow-Bold.ttf", "Archivo Narrow"),
    "akzidenz": ("AkzidenzGroteskBQ-Cnd.ttf", "ArchivoNarrow-Bold.ttf", "Akzidenz Condensed"),
}


class Skin:
    name = "base"
    label = "Base"
    canvas = (1280, 720)
    nearest = False             # pixel-art upscale (SD skins) vs smooth
    tune_cover = "static"       # what covers a channel change: static | black
    tune_black = 0.0            # seconds the cover holds at least (the box's tuner-lock black)
    banner_time_setting = False # the box let you set how long the banner stays (DirecTV's Banner Time)
    # The boot's scenes, (name, min seconds): the box's own start-up screens
    # (see docs/cathode-4/box-behaviour.md). None = the shared starting /
    # signal / guide; [] = this box had no boot screen (straight to TV).
    ui_sounds = False           # the box made key sounds (only the HR20 did)
    boot_scenes = None
    boot_over_video = ()        # the scenes the box drew over live video
    right_is_browse = False     # RIGHT on live TV browses (Dish) instead of volume
    browse_style = "banner"     # BROWSE shows: banner (one channel) | mini (a mini guide)
    guide_jump_min = 24 * 60    # how far REW / FF move the guide
    poster_wall = True          # On Demand titles may show as a poster wall
    wall_episodes = True        # ...a season's episodes among them
    keyboard_layer = "abc"      # the case the on-screen keyboard opens in
    default_font = "vcr"

    # Screens laid out for any canvas height. The rest are drawn at the
    # design height and opened up along a seam on a grown canvas (paint).
    TALL = ("guide", "screensaver")

    def __init__(self, app):
        self.app = app
        self.text = Text()
        self._logo_surfaces = {}
        self._anim_due = 0.0        # when the next animated-logo frame is wanted
        self.hits = []          # [(Rect, fn)] clickable this frame, in canvas pixels
        self.canvas = type(self).canvas
        self.grow = 0               # canvas rows past the design height (16:9 on a squarer window)
        self._seams = weakref.WeakKeyDictionary()   # screen -> how paint opened it up
        self._held = None           # backdrops held back while drawing for a seam
        self._holes = []            # the picture boxes cleared while drawing for a seam

    # ── The canvas for the window ─────────────────────────────────────────

    def fit_window(self, size) -> bool:
        """A 16:9 skin grows its canvas taller on a squarer window, to 4:3 at
        most: a 16:10 or 4:3 screen gets more rows, a banner at its real
        foot, rather than bars and a smaller picture of the 16:9 screen. A
        4:3 skin keeps its own pixels. True when the canvas changed."""
        W, H = type(self).canvas
        ww, wh = size
        if W * 9 == H * 16 and ww > 0 and wh > 0:
            tall = min(round(W * wh / ww), W * 3 // 4)
            if tall >= H + 4:                   # not a window a pixel off 16:9
                H = tall
        if (W, H) == self.canvas:
            return False
        self.canvas, self.grow = (W, H), H - type(self).canvas[1]
        return True

    def tall(self, name: str) -> bool:
        return name in self.TALL

    def idle_row(self, c, pb, rects, radius=0):
        """On Demand's transport buttons while the cursor isn't in them
        (DOWN brings it): dimmed, a legend until then, so a lit button
        always means the one SELECT presses."""
        if getattr(pb, "tfocus", None) is not None:
            return
        for r in rects:
            veil = pygame.Surface(r.size, pygame.SRCALPHA)
            pygame.draw.rect(veil, (0, 0, 0, 120), veil.get_rect(), border_radius=radius)
            c.blit(veil, r.topleft)

    def over_picture(self) -> bool:
        """Whether the top screen is the picture (live TV, playback) rather
        than a full page: a toast then keeps clear of the banner instead."""
        top = getattr(self.app, "top", None)
        return bool(top) and getattr(top(), "name", "") in ("live", "playback", "browse", "miniguide")


    def paint(self, canvas, name: str, draw, owner=None):
        """draw(surface) one screen onto the canvas. On a grown canvas a
        screen that isn't tall() is drawn at its design height and opened up
        along its longest stretch of identical rows (the clear picture
        between a top banner and a foot one, the empty page under a list):
        what's above stays at the top, what's below moves to the foot, and
        that stretch's own row fills between (see seams). Page backdrops
        reaching the foot are held back and drawn at the full height under
        it, the screen's picture boxes (hole) cleared through them."""
        if not self.grow or self.tall(name):
            draw(canvas)
            return
        W, H = self.canvas
        g, dh = self.grow, H - self.grow
        design = pygame.Surface((W, dh), pygame.SRCALPHA)
        n = len(self.hits)
        self.canvas, self.grow, self._held, self._holes = (W, dh), 0, [], []
        try:
            draw(design)
        finally:
            self.canvas, self.grow, held, self._held = (W, H), g, self._held, None
        fit = seams(design, g)
        if owner is not None:
            self._seams[owner] = fit
        for fn, r in held:
            fn(canvas, pygame.Rect(r.x, r.y, r.w, r.h + g))
        for r in self._holes:                   # the picture shows through the page
            canvas.fill((0, 0, 0, 0), _moved(r, fit))
        src = dst = 0
        for y, add in fit:
            canvas.blit(design, (0, dst), (0, src, W, y - src))
            dst += y - src
            row = design.subsurface((0, min(y, dh - 1), W, 1))
            canvas.blit(pygame.transform.scale(row, (W, add)), (0, dst))
            dst, src = dst + add, y
        canvas.blit(design, (0, dst), (0, src, W, dh - src))
        self.hits[n:] = [(_moved(r, fit), f) for r, f in self.hits[n:]]

    def place_box(self, owner, box):
        """Where paint put a screen's picture box (given in design pixels)."""
        fit = self._seams.get(owner) if self.grow and not self.tall(owner.name) else None
        if not fit:
            return box
        r = _moved(pygame.Rect(box), fit)
        return (r.x, r.y, r.w, r.h)

    def hole(self, c, rect):
        """Clear a picture box down to the video. Drawing for a seam, it's
        kept too, to clear it through the backdrops paint draws later."""
        pygame.draw.rect(c, (0, 0, 0, 0), rect)
        if self._held is not None:
            self._holes.append(pygame.Rect(rect))

    def hold_backdrop(self, rect, fn) -> bool:
        """A page's backdrop reaching the foot of the canvas, while paint
        draws for a seam: kept to draw later at the full height (so its
        gradient spans the screen and the seam opens through clear rows).
        fn(surface, rect) draws it. True when held."""
        rect = pygame.Rect(rect)
        if self._held is None or rect.bottom != self.canvas[1]:
            return False
        self._held.append((fn, rect))
        return True

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

    REMOTE_WORDS = {}       # this skin's own words for remote buttons in hints

    def k(self, action: str) -> str:
        """What a hint calls a remote button: the chosen remote's name for
        it, else this skin's word, else Cathode's."""
        from ..remote import button_name
        pad = getattr(self.app, "remote", None)
        if pad is not None and getattr(pad, "last_device", "") == "pad" and pad.pad_label(action):
            return pad.pad_label(action)        # a pad in hand: its own buttons
        remote = getattr(getattr(self.app, "config", None), "remote", "")
        return button_name(remote, action, self.REMOTE_WORDS.get(action, ""))

    def on_top(self, screen) -> bool:
        """Whether `screen` is the one the remote is talking to (a menu over
        it means its own prompts would point at the wrong thing)."""
        screens = getattr(self.app, "screens", None)
        return not screens or screens[-1] is screen

    def key_also(self, action: str) -> str:
        """' (C)' after a chip that names the remote's button, for someone on
        a keyboard with no remote chosen: the key, as the notes' 'MENU (C)'."""
        from ..remote import REMOTES
        app = self.app
        pad = getattr(app, "remote", None)
        if pad is None or getattr(pad, "last_device", "keys") == "pad" or not hasattr(app, "key_name"):
            return ""
        if REMOTES.get(getattr(app.config, "remote", ""), REMOTES[""])[1]:
            return ""
        key = app.key_name(action)
        return f" ({key})" if key else ""

    def empty_guide(self, g) -> str:
        """What a guide list with no channels says (only Favorites can be)."""
        if g.category == "Favorites":
            pad = getattr(self.app, "remote", None)
            if pad is not None and getattr(pad, "last_device", "") == "pad" and not pad.pad_label("FAV"):
                return f"No favorites yet. On a channel, press {self.k('OPTIONS')} and choose Add to Favorites."
            hint = getattr(self.app, "press_hint", None)
            return f"No favorites yet. Press {hint('FAV') if hint else 'FAV'} on a channel to add it."
        return "No channels in this list."

    def guide_pct(self) -> str:
        """The app's guide load, as pct() puts it."""
        return self.pct(getattr(self.app, "guide_progress", None))

    def od_side(self, s) -> list:
        """[(label, action)] for buttons beside On Demand's list that RIGHT
        moves into; none unless the skin draws some."""
        return []

    def draw_options(self, c, m):
        """Live TV's Options pop-up; a skin whose menus already sit over the
        picture draws it as a menu."""
        self.draw_menu(c, m)

    def draw_note(self, c, text: str):
        """A key's notice (the picture format, subtitles) in this skin's style."""
        self.draw_toast(c, text)

    def draw_program_info(self, c, info):
        """INFO on a guide cell. A skin whose guide already describes the
        chosen cell in its header just notes it; the SD skins draw a box."""
        self.draw_toast(c, f"{info.title}: " + "  ".join(info.lines()))

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

    def cell_text(self, title: str, w: int, h: int, font_for, size: int, width=None, lead: int = 2) -> tuple:
        """(font, [lines]) for a guide cell w by h: the whole title on one
        line, the size stepping down to seven tenths; else whole on two
        lines (where two fit the row), stepping down the same way; else at
        `size`, two lines (one when two don't fit) with the end clipped.
        A cell too narrow for three letters carries nothing: the cursor's
        header names the programme. font_for(size) is the skin's face at
        that size; width measures it (a condensed face measures its own).
        lead: the gap between two lines."""
        t = self.text
        width = width or t.width
        f = font_for(size)
        if not title or w < width(f, "MMM"):
            return f, []
        if width(f, title) <= w:
            return f, [title]
        sizes = range(size - 1, int(size * 0.7) - 1, -1)
        for s in sizes:
            f = font_for(s)
            if width(f, title) <= w:
                return f, [title]
        for s in (size,) + tuple(sizes):
            f = font_for(s)
            if 2 * t.ink(f)[1] + lead > h:
                continue
            lines, whole = t.lines(f, title, w, 2, width)
            if whole:
                return f, lines
        f = font_for(size)
        n = 2 if 2 * t.ink(f)[1] + lead <= h else 1
        return f, t.lines(f, title, w, n, width)[0]

    def label_every(self, col_w: int, label_w: int) -> int:
        """How many columns apart the time ruler's labels sit: every column
        when a label fits one, else every other, else every fourth."""
        for n in (1, 2, 4):
            if label_w + 6 <= col_w * n:
                return n
        return 4

    def hit(self, rect, fn):
        """Register a clickable region while drawing."""
        self.hits.append((pygame.Rect(rect), fn))

    def draw(self, canvas, screen):
        fn = getattr(self, f"draw_{screen.name}", None)
        if fn:
            fn(canvas, screen)
        card = getattr(screen, "card", None)
        if card and getattr(screen, "phase", "") != "cover" and time.monotonic() < card["until"]:
            self.draw_music_card(canvas, card)

    def draw_music_card(self, c, card):
        """A music channel's lower-third as its song starts and ends: the
        artist, the song in quotes, the label, bottom left over the picture,
        the way MTV named them."""
        W, H = self.canvas
        t = self.text
        fb, fr, fs = t.font("Barlow-Bold.ttf", 40), t.font("Barlow-Medium.ttf", 34), t.font("Barlow-Medium.ttf", 24)
        lines = [(card.get("artist", ""), fb), (f"\u201c{card['song']}\u201d" if card.get("song") else "", fr),
                 (card.get("label", ""), fs)]
        lines = [(s, f) for s, f in lines if s]
        y = int(H * 0.86) - sum(t.ink(f)[1] + 8 for _s, f in lines)
        for s, f in lines:
            t.draw(c, t.fit(f, s, W - 160), f, (255, 255, 255), 80, y, outline=(0, 0, 0))
            y += t.ink(f)[1] + 8

    def logo(self, url: str, max_w: int, max_h: int, headers=None) -> Optional[pygame.Surface]:
        """A channel logo or poster fitted to the box, as a pygame surface;
        None while it loads or when there isn't one. `headers` (a Plex token)
        go with the fetch but never into the URL or the cache name."""
        if not url or not self.app.logos:
            return None
        from ..logos import Animation
        key = (url, max_w, max_h)
        surf = self._logo_surfaces.get(key)
        if surf is None:
            im = self.app.logos.get(url, max_w, max_h, headers=headers)
            if im is None:
                return None
            if isinstance(im, Animation):
                surf = (im, [self._surface(f) for f in im.frames])
            else:
                surf = self._surface(im)
            if len(self._logo_surfaces) > 512:
                self._logo_surfaces.clear()
            self._logo_surfaces[key] = surf
        if isinstance(surf, tuple):             # animated: the frame for now
            anim, frames = surf
            i, wait = anim.at(time.monotonic())
            self._next_frame(wait)
            return frames[i]
        return surf

    @staticmethod
    def _surface(im):
        return pygame.image.frombytes(im.convert("RGBA").tobytes(), im.size, "RGBA")

    def _next_frame(self, wait: float):
        """An animated logo is on screen: draw again when its next frame is
        due (one timer for all of them; none once they're off screen)."""
        now = time.monotonic()
        if self._anim_due <= now or now + wait < self._anim_due - 0.01:
            self._anim_due = now + wait
            self.app.after(wait, self.app.invalidate)


def skin_classes() -> dict:
    """name -> skin class, in the order the Skin setting cycles them."""
    from .classic import Classic
    from .indirect import InDirect, InDirectHD
    from .plate import Plate, PlateHD
    from .cable import IGrid, Passage
    return {c.name: c for c in (Classic, InDirect, InDirectHD, Plate, PlateHD, IGrid, Passage)}


def load_skin(name: str, app) -> Skin:
    from .classic import Classic
    return skin_classes().get(name, Classic)(app)


def seams(surface, grow: int):
    """Where to open a design-height surface up by `grow` rows: [(row, rows
    added there)]. Into its longest stretch of identical rows (the nearer
    the middle on a tie); split between the top and foot stretches when
    those are its two longest and alike (a notice centred on black stays
    centred); with no stretch 8 rows long, its top and foot rows extended."""
    w, h = surface.get_size()
    raw, stride = surface.get_buffer().raw, surface.get_pitch()     # bytes: slices compare at memcmp speed

    def row(y):
        return raw[y * stride:y * stride + w * 4]
    runs, start = [], 0
    for y in range(1, h + 1):
        if y == h or row(y) != row(y - 1):
            runs.append((start, y))
            start = y
    size = sorted((b - a for a, b in runs), reverse=True) + [0]
    if size[0] < 8:
        return [(0, grow // 2), (h, grow - grow // 2)]
    first, last = runs[0], runs[-1]
    if (len(runs) > 2 and min(first[1] - first[0], last[1] - last[0]) >= size[1]
            and row(0) == row(h - 1)):
        return [(sum(first) // 2, grow // 2), (sum(last) // 2, grow - grow // 2)]
    best = max(runs, key=lambda r: (r[1] - r[0], -abs(r[0] + r[1] - h)))
    return [(sum(best) // 2, grow)]


def _moved(r, fit):
    """A rect's edges after paint opened its screen up (see seams)."""
    top = r.top + sum(add for y, add in fit if r.top >= y)
    bottom = r.bottom + sum(add for y, add in fit if r.bottom > y)
    return pygame.Rect(r.x, top, r.w, bottom - top)
