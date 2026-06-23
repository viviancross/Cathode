"""Font scaling checks — every bundled font must render at the requested pixel
height (so it fits the same menu/OSD boxes) and ellipsize must fit a box.

Headless: PIL only, no display needed.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw  # noqa: E402
from cathode.ui import theme  # noqa: E402


class TestFontScaling(unittest.TestCase):
    def test_every_bundled_font_normalizes_to_requested_height(self):
        # get_font should re-pick the point size so each font's line height is
        # close to the requested pixels — otherwise some fonts overflow rows.
        for key in theme.available_fonts(include_subtitle_only=True):
            self.assertTrue(theme.set_font(key), f"could not activate {key}")
            theme._FONT_CACHE.clear()
            for target in (24, 40, 64):
                f = theme.get_font(target)
                bb = f.getbbox("Ag")            # visible glyph height
                gh = bb[3] - bb[1]
                # Within 30% of target — keeps text legible + inside its box.
                self.assertLessEqual(
                    abs(gh - target), target * 0.30,
                    f"{key} at {target}px rendered glyph height {gh}")

    def test_ellipsize_fits_box(self):
        theme.set_font("vcr")
        theme._FONT_CACHE.clear()
        img = Image.new("RGBA", (400, 100))
        d = ImageDraw.Draw(img)
        f = theme.get_font(30)
        long = "A Very Long Movie Title That Will Not Fit In A Narrow Row"
        out = theme.ellipsize(d, long, f, 200)
        self.assertLessEqual(d.textlength(out, font=f), 200)
        self.assertTrue(out.endswith("…"))
        # Short text passes through untouched.
        self.assertEqual(theme.ellipsize(d, "OK", f, 200), "OK")

    def test_wrap_lines_drops_to_next_line_and_caps(self):
        theme.set_font("vcr")
        theme._FONT_CACHE.clear()
        d = ImageDraw.Draw(Image.new("RGBA", (400, 100)))
        f = theme.get_font(30)
        long = "A Very Long Movie Title That Should Wrap Across Multiple Lines"
        lines = theme.wrap_lines(d, long, f, 200, max_lines=2)
        self.assertTrue(1 <= len(lines) <= 2)                 # capped
        for ln in lines:
            self.assertLessEqual(d.textlength(ln, font=f), 200)  # each fits
        # Short title stays one line, unchanged.
        self.assertEqual(theme.wrap_lines(d, "CNN", f, 200), ["CNN"])


if __name__ == "__main__":
    unittest.main()
