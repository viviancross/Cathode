"""Colour themes: a full palette derived from a few base hues, with text
colours solved for contrast against the fills they sit on.

Pure data and functions. A palette is a dict of role -> RGBA tuple; whoever
draws takes the palette it is handed, so switching theme is swapping a dict.
"""


def _a(rgb, al):
    return (rgb[0], rgb[1], rgb[2], al)


def _shift(rgb, d):
    return tuple(max(0, min(255, c + d)) for c in rgb[:3])


def _mix(a, b, t=0.5):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def _lum(rgb) -> float:
    """WCAG relative luminance of an sRGB color."""
    def f(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2])


def contrast(a, b) -> float:
    """WCAG contrast ratio between two colors (1..21)."""
    la, lb = _lum(a), _lum(b)
    hi, lo = (la, lb) if la >= lb else (lb, la)
    return (hi + 0.05) / (lo + 0.05)


def _ink(cell, light, dark, target=3.0):
    """Text color readable on the `cell` fill. Keeps the theme's light text
    when it clears `target` (guide cells are large by WCAG terms, hence 3:1);
    otherwise whichever ink contrasts more — light accents (mono, ice) turn
    selection fills near-white, where fixed white text was unreadable.

    Callers whose text is not reliably large pass a higher target: button
    labels shrink to fit their box, so a six-button row can land near 10px."""
    if contrast(cell, light) >= target:
        return light
    return dark if contrast(cell, dark) > contrast(cell, light) else light


def _muted(bg, text, target=4.5):
    """Secondary-text ink for this theme: the theme's own ink walked toward
    legibility over its own panel ground, rather than a fixed gray.

    Solved, not chosen. The flat (130,130,140) this replaces measured 3.15:1 on
    c64 and 4.4:1 on amber/green — under the 4.5:1 body bar on three of nine
    shipped themes — and being a cool gray it also read as another app's text
    inside Amber CRT's warm world. Solving per theme also covers the custom
    palettes the theme editor can build, which no fixed value could.
    """
    cand = _mix(bg, text, 0.55)
    for i in range(11, 21):                  # 0.55 .. 1.00 in twentieths
        cand = _mix(bg, text, i / 20)
        if contrast(bg, cand) >= target:
            break
    return cand


def _primary_bg(bg, accent, ink_d, text, target=4.5):
    """Ground for the primary button: the panel tinted toward the accent, at
    whatever strength still leaves the theme's own ink readable on it.

    Tries the accent tint first and darkens instead when no tint can work. On
    c64 the entire palette is one periwinkle at one lightness, so tinting
    toward the accent walks the ground *into* the text and measures 3.6:1;
    there the deliberate answer is a recessed ground rather than a brighter
    one, which still separates primary from the secondaries' flat panel.
    """
    for f in (0.30, 0.22, 0.14):
        cand = _mix(bg, accent, f)
        if contrast(cand, text) >= target:
            return cand
    for f in (0.25, 0.40, 0.55):
        cand = _mix(bg, ink_d, f)
        if contrast(cand, text) >= target:
            return cand
    return _mix(bg, ink_d, 0.55)


def _build(bg, accent, accent2, hot, text=(255, 255, 255),
           chnum=(40, 255, 90)):
    """Derive a full color set from a few base hues."""
    bg_d = _shift(bg, -18)
    bg_l = _shift(bg, 42)
    sel = _mix(bg, accent, 0.65)
    onair = _mix(bg, accent, 0.80)
    ink_d = _mix(bg_d, (0, 0, 0), 0.5)   # darkest theme tone, for light fills
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
        # Third ink step, under WHITE and WHITE_DIM: captions, hints, metadata,
        # disabled labels. Theme-derived and contrast-solved (see _muted).
        "INK_MUTED":   _a(_muted(bg, text), 255),
        # Structural dim — the UNFILLED part of a progress or volume bar. It is
        # not an ink: it must recede behind its own fill, which is the opposite
        # of what secondary text needs. GRAY used to be both at once, so it was
        # simultaneously too dim to read and too bright to sit behind a bar.
        "TRACK":       _a(_mix(bg_l, text, 0.22), 255),
        # Dim laid behind a modal panel to push back whatever it opened over.
        # One value, because it is one idea: the context menu used 90 and the
        # confirm dialog 120, so the same gesture pushed the background back by
        # two different amounts depending on which dialog you were in.
        "SCRIM":       (0, 0, 0, 110),
        # Ground for the one action a page exists for, when the cursor is NOT on
        # it. Filled primary against outline-only secondaries; the selection
        # fill stays brighter still, so focus always outranks primacy instead of
        # competing with it. A border shade alone couldn't carry this — CYAN and
        # OSD_BORDER are 50 alpha apart and read as the same button.
        "BTN_PRIMARY_BG": _a(_primary_bg(bg, accent, ink_d, text), 255),
        # Label on that ground. Flipped by the same _ink rule the selection
        # fills use: c64's accent is bright and its "white" is periwinkle, so a
        # fixed light label measured 3.6:1 there.
        "BTN_PRIMARY_TEXT": _a(_ink(_primary_bg(bg, accent, ink_d, text),
                                    text, ink_d, target=4.5), 255),
        "OSD_BG":      _a(bg, 215),
        "OSD_BORDER":  _a(accent, 205),
        "GUIDE_BG":         _a(bg_d, 240),
        "GUIDE_HEADER_BG":  _a(bg_l, 255),
        "GUIDE_ROW_ODD":    _a(bg, 232),
        "GUIDE_ROW_EVEN":   _a(bg_d, 232),
        "GUIDE_CURRENT":    _a(_mix(bg, accent, 0.45), 240),
        "GUIDE_SELECTED":   _a(sel, 255),
        "GUIDE_ONAIR":      _a(onair, 225),
        # Text that sits ON the selection / on-air fills. Fixed white text
        # fails on light-accent themes; these flip to dark ink when needed.
        "SEL_TEXT":         _a(_ink(sel, text, ink_d), 255),
        "SEL_TEXT_DIM":     _a(_ink(sel, text, ink_d), 215),
        "ONAIR_TEXT":       _a(_ink(onair, text, ink_d), 255),
        # Full-screen page backdrop (main menu, PPV, info, OSK, editor) —
        # near-black tinted toward the theme bg so every theme drenches.
        "SCREEN_BG":        _a(_mix(bg, (0, 0, 0), 0.82), 255),
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


def custom(bg, accent, accent2, text, chnum=(40, 255, 90)) -> dict:
    """A palette from the theme editor's base colours, held to the same
    contrast guarantees as the shipped ones because they are solved, not
    tabulated."""
    def rgb(c):
        return tuple(int(v) for v in c[:3])
    return _build(rgb(bg), rgb(accent), rgb(accent2), rgb(accent2),
                  text=rgb(text), chnum=rgb(chnum))


THEME_LABELS = {
    "blue": "Classic Blue", "amber": "Amber CRT", "green": "Green Phosphor",
    "vhs": "VHS Magenta", "mono": "Monochrome", "c64": "Commodore 64",
    "red": "Red Alert", "synth": "Synthwave", "ice": "Ice",
}

