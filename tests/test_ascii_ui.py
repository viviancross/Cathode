"""Every character the UI draws must exist in the bundled pixel fonts.

The faces are retro and sparse. An em dash is a tofu box in VCR — the DEFAULT
font — and in vt220; an ellipsis is a box in vt220. A degree sign, checked the
same way, is present everywhere, so the weather header keeps it. The rule is
therefore not "ASCII only" but "verified against the fonts we actually ship",
which is what this test does.
"""

import glob
import io
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402

from cathode.ui import theme  # noqa: E402

_STR = re.compile(r'"([^"\n]*)"|\'([^\'\n]*)\'')
# Codepoint no font defines, used as the "this is what missing looks like"
# reference to compare candidate glyphs against.
_MISSING = ""


def _renders(ch: str, font) -> bool:
    """Whether `font` has a real glyph for `ch` (not the .notdef box)."""
    def bits(s):
        im = Image.new("L", (90, 90), 0)
        ImageDraw.Draw(im).text((6, 6), s, font=font, fill=255)
        return im.tobytes()
    return bits(ch) != bits(_MISSING)


def _drawable_strings():
    """String literals that can reach the screen. Console `print` lines are
    skipped: a terminal renders anything, and the log deliberately uses arrows
    and dashes."""
    out = []
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in sorted(glob.glob(os.path.join(root, "cathode", "**", "*.py"),
                                 recursive=True)):
        with io.open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith(("#", '"""', "'''")) or "print(" in line:
                continue
            for m in _STR.finditer(line):
                s = m.group(1) or m.group(2) or ""
                if any(ord(c) > 126 for c in s):
                    out.append((os.path.relpath(path, root), lineno, s))
    return out


class TestDrawableGlyphs(unittest.TestCase):
    def tearDown(self):
        theme.set_font("vcr")

    def test_every_drawn_character_exists_in_every_bundled_font(self):
        strings = _drawable_strings()
        missing = []
        for key in theme.FONT_ORDER:
            if not theme.set_font(key):
                continue                      # font not present in this build
            font = theme.get_font(32)
            for path, lineno, s in strings:
                for ch in set(c for c in s if ord(c) > 126):
                    if not _renders(ch, font):
                        missing.append(f"{path}:{lineno} {ch!r} missing in {key}")
        self.assertEqual(missing, [], "\n" + "\n".join(missing))

    def test_the_probe_itself_works(self):
        # Guards the test: if _renders ever returned True for everything, the
        # check above would pass vacuously.
        theme.set_font("vcr")
        font = theme.get_font(32)
        self.assertTrue(_renders("A", font))
        self.assertFalse(_renders("—", font))   # em dash: tofu in VCR
        self.assertTrue(_renders("°", font))    # degree: present

    def test_ellipsize_stays_ascii(self):
        # theme.ellipsize appends "..." rather than U+2026 for this reason.
        d = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        theme.set_font("vcr")
        out = theme.ellipsize(d, "A very long title that will not fit at all",
                              theme.get_font(28), 60)
        self.assertNotIn("…", out)


if __name__ == "__main__":
    unittest.main()
