"""Retro color themes and font configuration.

Colors are exposed as MODULE-LEVEL names (BLACK, WHITE, CYAN, OSD_BG, ...).
Other UI modules import these names by value, so `apply_theme()` rebinds them
both here and in the importing modules — this lets the color scheme be switched
live at runtime.
"""

from __future__ import annotations

from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont
import os
import sys
from typing import Optional, List

# ── Palette builder ──────────────────────────────────────────────────────────


def _a(rgb, al):
    return (rgb[0], rgb[1], rgb[2], al)


def _shift(rgb, d):
    return tuple(max(0, min(255, c + d)) for c in rgb[:3])


def _mix(a, b, t=0.5):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def _build(bg, accent, accent2, hot, text=(255, 255, 255),
           chnum=(40, 255, 90)):
    """Derive a full color set from a few base hues."""
    bg_d = _shift(bg, -18)
    bg_l = _shift(bg, 42)
    return {
        # Channel-number color (vibrant green by default; editable per theme).
        "CHANNEL_GREEN": _a(chnum, 255),
        "BLACK":       (0, 0, 0, 255),
        "TRANSPARENT": (0, 0, 0, 0),
        "WHITE":       _a(text, 255),
        "WHITE_DIM":   _a(text, 185),
        "CYAN":        _a(accent, 255),
        "CYAN_DIM":    _a(accent, 200),
        "YELLOW":      _a(accent2, 255),
        "YELLOW_DIM":  _a(accent2, 200),
        "ORANGE":      _a(hot, 255),
        "RED":         (255, 70, 70, 255),
        "GREEN":       (60, 235, 110, 255),
        "GRAY":        (130, 130, 140, 255),
        "GRAY_DARK":   (60, 60, 70, 255),
        "OSD_BG":      _a(bg, 215),
        "OSD_BORDER":  _a(accent, 205),
        "GUIDE_BG":         _a(bg_d, 240),
        "GUIDE_HEADER_BG":  _a(bg_l, 255),
        "GUIDE_ROW_ODD":    _a(bg, 232),
        "GUIDE_ROW_EVEN":   _a(bg_d, 232),
        "GUIDE_CURRENT":    _a(_mix(bg, accent, 0.45), 240),
        "GUIDE_SELECTED":   _a(_mix(bg, accent, 0.65), 255),
        "GUIDE_ONAIR":      _a(_mix(bg, accent, 0.80), 225),
        "GUIDE_TIME_BG":    _a(bg_l, 255),
        "GUIDE_BORDER":     _a(accent, 185),
        "CHNUM_BG":         _a(bg_l, 205),
        "CHNUM_TEXT":       _a(accent2, 255),
        "TV_BLUE":          _a(bg, 230),
        "TV_BLUE_DARK":     _a(bg_d, 210),
        "STATIC_COLORS": [
            (180, 180, 180), (220, 220, 220), (100, 100, 100),
            (255, 255, 255), (50, 50, 50),
        ],
    }


# name -> palette.  Tweak/add freely; THEME_ORDER controls cycle order.
PALETTES = {
    "blue":  _build((0, 0, 62),    (0, 220, 255),   (255, 220, 0),   (255, 140, 0)),
    "amber": _build((46, 24, 0),   (255, 176, 0),   (255, 224, 130), (255, 110, 0),
                    text=(255, 206, 130)),
    "green": _build((0, 34, 12),   (70, 255, 120),  (190, 255, 130), (255, 190, 0),
                    text=(170, 255, 180)),
    "vhs":   _build((40, 0, 54),   (0, 232, 255),   (255, 80, 220),  (255, 90, 170),
                    text=(240, 222, 255)),
    "mono":  _build((22, 22, 26),  (220, 220, 225), (255, 255, 255), (180, 180, 185),
                    text=(232, 232, 236)),
    "c64":   _build((48, 40, 130), (150, 140, 245), (190, 185, 255), (255, 200, 120),
                    text=(175, 168, 255)),
    "red":   _build((46, 0, 0),    (255, 80, 80),   (255, 170, 120), (255, 50, 50),
                    text=(255, 180, 170)),
    "synth": _build((28, 0, 42),   (255, 70, 180),  (110, 200, 255), (255, 120, 80),
                    text=(240, 200, 255)),
    "ice":   _build((0, 28, 46),   (130, 230, 255), (220, 250, 255), (130, 200, 255),
                    text=(220, 245, 255)),
}
THEME_ORDER = ["blue", "amber", "green", "vhs", "mono", "c64", "red", "synth", "ice"]
THEME_LABELS = {
    "blue": "Classic Blue", "amber": "Amber CRT", "green": "Green Phosphor",
    "vhs": "VHS Magenta", "mono": "Monochrome", "c64": "Commodore 64",
    "red": "Red Alert", "synth": "Synthwave", "ice": "Ice",
}

_active_theme = "blue"

# Module-level color names (populated by _install / apply_theme)
_COLOR_KEYS = list(PALETTES["blue"].keys())


def _install(pal):
    g = globals()
    for k, v in pal.items():
        g[k] = v


def apply_theme(name: str) -> str:
    """Switch the active palette and rebind colors in dependent modules."""
    global _active_theme
    if name not in PALETTES:
        name = "blue"
    _active_theme = name
    pal = PALETTES[name]
    _install(pal)
    clear_text_cache()   # palette changes the fills baked into cached text tiles
    for modname in ("cathode.ui.osd", "cathode.ui.guide", "cathode.ui.renderer",
                    "cathode.ui.menu", "cathode.ui.osk", "cathode.ui.editor",
                    "cathode.ui.mainmenu", "cathode.ui.ppv", "cathode.ui.plexosd",
                    "cathode.ui.plexinfo"):
        mod = sys.modules.get(modname)
        if mod:
            for k, v in pal.items():
                if hasattr(mod, k):
                    setattr(mod, k, v)
    return name


def set_custom_palette(bg, accent, accent2, text, chnum=(40, 255, 90)) -> str:
    """Build/refresh the 'custom' palette from the editable base colors and apply
    it.  Used by the in-app theme editor; 'custom' is intentionally not in
    THEME_ORDER so it doesn't appear in the plain theme cycle."""
    bg = tuple(int(c) for c in bg[:3])
    accent = tuple(int(c) for c in accent[:3])
    accent2 = tuple(int(c) for c in accent2[:3])
    text = tuple(int(c) for c in text[:3])
    chnum = tuple(int(c) for c in chnum[:3])
    PALETTES["custom"] = _build(bg, accent, accent2, accent2, text=text, chnum=chnum)
    if "custom" not in THEME_LABELS:
        THEME_LABELS["custom"] = "Custom"
    return apply_theme("custom")


def current_theme() -> str:
    return _active_theme


def theme_label(name: Optional[str] = None) -> str:
    return THEME_LABELS.get(name or _active_theme, name or _active_theme)


def cycle_theme() -> str:
    i = THEME_ORDER.index(_active_theme) if _active_theme in THEME_ORDER else -1
    return apply_theme(THEME_ORDER[(i + 1) % len(THEME_ORDER)])


# Install default theme at import (defines CHANNEL_GREEN + all palette globals).
# CHANNEL_GREEN defaults to vibrant green but is now part of the palette, so the
# theme editor can recolor it per custom theme.
_install(PALETTES["blue"])


# ── Fonts ────────────────────────────────────────────────────────────────────

_FONT_CACHE: dict = {}
_ACTIVE_FONT: Optional[str] = None   # explicit font file path override

# Candidate retro/monospace fonts to look for on the system (fallback search)
_FONT_CANDIDATES = [
    "VCR_OSD_MONO.ttf", "PxPlus_IBM_VGA8.ttf", "Glass_TTY_VT220.ttf",
    "PixelOperator.ttf", "VT323-Regular.ttf", "Jersey10-Regular.ttf",
    "LiberationMono-Bold.ttf", "LiberationMono-Regular.ttf",
    "UbuntuMono-Bold.ttf", "UbuntuMono-Regular.ttf",
    "FreeMono.ttf",
    "consolab.ttf", "consola.ttf", "courbd.ttf", "cour.ttf",
]

_FONT_DIRS = [
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
    "C:\\Windows\\Fonts",
    os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts"),
]

# When frozen by PyInstaller, the bundled fonts live next to the executable /
# in the unpacked bundle — search those first.
if getattr(sys, "frozen", False):
    _frozen_base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    _FONT_DIRS[:0] = [
        os.path.join(os.path.dirname(sys.executable), "assets", "fonts"),
        os.path.join(_frozen_base, "assets", "fonts"),
    ]

# Selectable fonts: key -> candidate filenames + human label
_FONT_REGISTRY = {
    "vcr":        (["VCR_OSD_MONO.ttf", "VCR OSD Mono.ttf", "VCROSDMono.ttf"],
                   "VCR OSD Mono"),
    "ibm":        (["PxPlus_IBM_VGA8.ttf", "Px437_IBM_VGA8.ttf",
                    "PxPlus IBM VGA8.ttf"], "PxPlus IBM VGA"),
    "vt220":      (["Glass_TTY_VT220.ttf"], "Glass TTY VT220"),
    "pixelop":    (["PixelOperator.ttf"], "Pixel Operator"),
    "vt323":      (["VT323-Regular.ttf"], "VT323"),
    "jersey":     (["Jersey10-Regular.ttf"], "Jersey 10"),
}
FONT_ORDER = ["vcr", "ibm", "vt220", "pixelop", "vt323", "jersey"]

# Fonts offered only for subtitles (by discovered key), never as the UI font.
_SUBTITLE_ONLY_KEYS = {"x_closedcaption"}
_active_font_key = "vcr"


def _find_font(name: str) -> Optional[str]:
    for d in _FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            if name in files:
                return os.path.join(root, name)
    return None


def _resolve_font_key(key: str) -> Optional[str]:
    entry = _FONT_REGISTRY.get(key)
    if not entry:
        return None
    for fn in entry[0]:
        p = _find_font(fn)
        if p:
            return p
    return None


def _asset_font_dirs():
    """Directories where bundled / user-dropped fonts live."""
    dirs = []
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        dirs.append(os.path.join(os.path.dirname(sys.executable), "assets", "fonts"))
        dirs.append(os.path.join(base, "assets", "fonts"))
    dirs.append(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts"))
    return dirs


# Filenames already claimed by the registry (so they aren't listed twice).
_REGISTRY_FILES = {fn.lower() for entry in _FONT_REGISTRY.values() for fn in entry[0]}


def _discovered_fonts() -> dict:
    """Any extra .ttf/.otf in assets/fonts → selectable fonts. Drop a font file
    in and it appears in the Font menu. key -> (path, label)."""
    import re
    found = {}
    for d in _asset_font_dirs():
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            low = fn.lower()
            if not low.endswith((".ttf", ".otf")) or low in _REGISTRY_FILES:
                continue
            key = "x_" + re.sub(r"[^a-z0-9]+", "", os.path.splitext(low)[0])
            label = os.path.splitext(fn)[0].replace("_", " ").replace("-", " ")
            found.setdefault(key, (os.path.join(d, fn), label))
    return found


def _font_path(key: str) -> Optional[str]:
    if key in _FONT_REGISTRY:
        return _resolve_font_key(key)
    disc = _discovered_fonts().get(key)
    return disc[0] if disc else None


def fonts_dir() -> Optional[str]:
    """The bundled fonts directory (for mpv's --sub-fonts-dir)."""
    for d in _asset_font_dirs():
        if os.path.isdir(d):
            return os.path.abspath(d)
    return None


def font_family(key: str) -> Optional[str]:
    """The internal family name of font `key` (used as mpv's sub-font)."""
    path = _font_path(key)
    if not path:
        return None
    try:
        from PIL import ImageFont
        return ImageFont.truetype(path, 20).getname()[0]
    except Exception:
        return None


def _find_any_monospace() -> Optional[str]:
    for name in _FONT_CANDIDATES:
        path = _find_font(name)
        if path:
            return path
    return None


def available_fonts(include_subtitle_only: bool = False) -> List[str]:
    """Selectable font keys: registry fonts that resolve + auto-discovered ones.
    Subtitle-only fonts (e.g. Closed Caption) are excluded unless asked for."""
    out = [k for k in FONT_ORDER if _resolve_font_key(k)]
    for k in _discovered_fonts():
        if k in _SUBTITLE_ONLY_KEYS and not include_subtitle_only:
            continue
        if k not in out:
            out.append(k)
    return out


def set_font(key: str) -> bool:
    """Make `key` the active font if its file is available."""
    global _active_font_key, _ACTIVE_FONT
    path = _font_path(key)
    if not path:
        return False
    _active_font_key = key
    _ACTIVE_FONT = path
    _FONT_CACHE.clear()
    clear_text_cache()
    return True


def current_font() -> str:
    return _active_font_key


def font_label(key: Optional[str] = None) -> str:
    key = key or _active_font_key
    entry = _FONT_REGISTRY.get(key)
    if entry:
        return entry[1]
    disc = _discovered_fonts().get(key)
    return disc[1] if disc else key


def cycle_font() -> str:
    avail = available_fonts()
    if not avail:
        return _active_font_key
    if _active_font_key in avail:
        i = avail.index(_active_font_key)
        nxt = avail[(i + 1) % len(avail)]
    else:
        nxt = avail[0]
    set_font(nxt)
    return _active_font_key


def get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    key = (size, bold, _active_font_key)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    font_path = _ACTIVE_FONT or _find_any_monospace()
    font = None
    if font_path:
        try:
            font = ImageFont.truetype(font_path, size)
            # Normalize on VISIBLE glyph height (ascender->descender ink), not the
            # nominal size or the line box. Pixel fonts pack big internal leading,
            # so sizing by line height renders them tiny; targeting the glyph box
            # makes every font fill the requested px and stay consistent in the
            # menus/OSD without overflowing.
            bb = font.getbbox("Ag")
            gh = bb[3] - bb[1]
            if gh > 0 and abs(gh - size) > 1:
                adj = max(6, int(round(size * size / gh)))
                if adj != size:
                    font = ImageFont.truetype(font_path, adj)
        except Exception:
            font = None
    if font is None:
        # No TrueType found.  PIL's bitmap default ignores `size`, so prefer
        # the size-aware default (Pillow >= 10.1) to keep text legible.
        try:
            font = ImageFont.load_default(size=size)
        except TypeError:
            font = ImageFont.load_default()

    try:
        font._cid = key   # stamp identity for the text-raster cache
    except Exception:
        pass
    _FONT_CACHE[key] = font
    return font


# ── Text rendering cache ──────────────────────────────────────────────────────
# Some pixel fonts (e.g. VT323, Jersey 10) store each glyph as dozens of square
# contours, so FreeType is ~7x slower to rasterize AND measure them — the guide
# redraws ~100 strings per repaint and would lag. These caches make re-drawing
# the SAME string/size/colour near-free, so ANY font (current or future, however
# heavy) only pays the rasterization cost once. Transparent for fast fonts.

_TILE_CACHE: "OrderedDict" = OrderedDict()   # (cid,text,fill,sw,sf) -> RGBA tile
_MEASURE_CACHE: dict = {}                     # (cid,text[,'wh']) -> width / (w,h)
_TEXT_CACHE_MAX = 4096


def clear_text_cache():
    _TILE_CACHE.clear()
    _MEASURE_CACHE.clear()


def measure(draw, text: str, font) -> float:
    """Cached draw.textlength(text, font). Pure function of (font, text)."""
    cid = getattr(font, "_cid", None)
    if cid is None or not text:
        return draw.textlength(text, font=font)
    k = (cid, text)
    v = _MEASURE_CACHE.get(k)
    if v is None:
        v = draw.textlength(text, font=font)
        _MEASURE_CACHE[k] = v
    return v


def text_wh(draw, text: str, font) -> tuple:
    """Cached ink size (w, h) from textbbox((0,0)) — same value the UI uses for
    centering. Pure function of (font, text)."""
    cid = getattr(font, "_cid", None)
    if cid is None:
        bb = draw.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0], bb[3] - bb[1]
    k = (cid, text, "wh")
    v = _MEASURE_CACHE.get(k)
    if v is None:
        bb = draw.textbbox((0, 0), text, font=font)
        v = (bb[2] - bb[0], bb[3] - bb[1])
        _MEASURE_CACHE[k] = v
    return v


def draw_text(img, xy, text: str, font, fill, stroke_width: int = 0,
              stroke_fill=None):
    """Cached equivalent of ImageDraw.Draw(img).text(xy, text, font, fill, ...).

    Rasterizes `text` into a small RGBA tile once and alpha-pastes it on repeats.
    Tiles are drawn at (0,0); pasting at (x,y) reproduces a direct draw exactly
    when the ink starts at/after the origin (true for the UI fonts). Falls back
    to a direct draw for empty text, no cache id, negative bearings, or when the
    tile would overflow the image (alpha_composite can't clip)."""
    x, y = int(xy[0]), int(xy[1])
    cid = getattr(font, "_cid", None)
    if not text or cid is None:
        ImageDraw.Draw(img).text((x, y), text, font=font, fill=fill,
                                 stroke_width=stroke_width, stroke_fill=stroke_fill)
        return
    k = (cid, text, fill, stroke_width, stroke_fill)
    tile = _TILE_CACHE.get(k)
    if tile is None:
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        l, t, r, b = probe.textbbox((0, 0), text, font=font,
                                    stroke_width=stroke_width)
        if l < 0 or t < 0 or r <= 0 or b <= 0:
            ImageDraw.Draw(img).text((x, y), text, font=font, fill=fill,
                                     stroke_width=stroke_width, stroke_fill=stroke_fill)
            return
        tile = Image.new("RGBA", (r + 1, b + 1), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((0, 0), text, font=font, fill=fill,
                                  stroke_width=stroke_width, stroke_fill=stroke_fill)
        _TILE_CACHE[k] = tile
        if len(_TILE_CACHE) > _TEXT_CACHE_MAX:
            _TILE_CACHE.popitem(last=False)
    else:
        _TILE_CACHE.move_to_end(k)
    tw, th = tile.size
    if x < 0 or y < 0 or x + tw > img.width or y + th > img.height:
        ImageDraw.Draw(img).text((x, y), text, font=font, fill=fill,
                                 stroke_width=stroke_width, stroke_fill=stroke_fill)
        return
    img.alpha_composite(tile, (x, y))


def wrap_lines(draw, text: str, font, max_w: int, max_lines: int = 2) -> list:
    """Word-wrap `text` into at most `max_lines` lines that each fit `max_w` px.
    Overflow past the last line is folded into it and ellipsized; an over-wide
    single word is ellipsized too. Use for titles that should drop to the next
    line instead of being cut off."""
    if max_w <= 0 or not text:
        return [text]
    words = text.split() or [text]
    lines, cur = [], ""
    for w in words:
        trial = w if not cur else f"{cur} {w}"
        if not cur or measure(draw, trial, font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines[max_lines - 1] += " " + " ".join(lines[max_lines:])
        lines = lines[:max_lines]
    return [ellipsize(draw, ln, font, max_w) for ln in lines]


def ellipsize(draw, text: str, font, max_w: int) -> str:
    """Trim `text` to fit `max_w` pixels, adding an ellipsis. Returns it
    unchanged if it already fits. Use for any label drawn into a fixed box so
    long titles / wide fonts never run past their boundary."""
    if not text or max_w <= 0:
        return text
    try:
        if measure(draw, text, font) <= max_w:
            return text
        ell = "…"
        t = text
        while t and measure(draw, t + ell, font) > max_w:
            t = t[:-1]
        return (t + ell) if t else ell
    except Exception:
        return text
