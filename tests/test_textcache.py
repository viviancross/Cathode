"""Text-raster cache (theme.draw_text / measure) — must render identically to a
direct PIL draw, and must actually cache repeats. This is what keeps heavy pixel
fonts (VT323, Jersey 10) from lagging the guide, for any font now or later."""

import os
import sys
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.ui import theme  # noqa: E402


def _draw_direct(text, font, fill, size=(200, 60), xy=(8, 10)):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(img).text(xy, text, font=font, fill=fill)
    return img


def _draw_cached(text, font, fill, size=(200, 60), xy=(8, 10)):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    theme.draw_text(img, xy, text, font, fill)
    return img


class TestTextCache(unittest.TestCase):
    def _font(self, key):
        if not theme.set_font(key):
            self.skipTest(f"font {key} not available")
        return theme.get_font(28)

    def test_cached_matches_direct_all_fonts(self):
        # Every selectable font must rasterize identically through the cache.
        for key in theme.available_fonts():
            theme.clear_text_cache()
            font = self._font(key)
            for fill in ((255, 255, 255, 255), (40, 255, 90, 185)):
                a = _draw_direct("Ch 12 News 1080p", font, fill)
                b = _draw_cached("Ch 12 News 1080p", font, fill)
                self.assertEqual(a.tobytes(), b.tobytes(),
                                 f"{key} fill={fill} mismatch")

    def test_measure_matches_textlength(self):
        font = self._font("vt323")
        d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        for s in ("", "A", "Hello world", "1080p"):
            self.assertEqual(theme.measure(d, s, font),
                             d.textlength(s, font=font))

    def test_repeat_is_cached(self):
        theme.clear_text_cache()
        font = self._font("jersey")
        img = Image.new("RGBA", (200, 60), (0, 0, 0, 0))
        theme.draw_text(img, (8, 10), "cache me", font, (255, 255, 255, 255))
        n = len(theme._TILE_CACHE)
        theme.draw_text(img, (40, 10), "cache me", font, (255, 255, 255, 255))
        self.assertEqual(len(theme._TILE_CACHE), n)  # no new tile for a repeat

    def test_edge_overflow_falls_back(self):
        # A tile that would spill past the image must still draw (no crash) and
        # match a direct draw clipped the same way.
        font = self._font("vcr")
        a = _draw_direct("edge", font, (255, 255, 255, 255), size=(40, 40), xy=(30, 8))
        b = _draw_cached("edge", font, (255, 255, 255, 255), size=(40, 40), xy=(30, 8))
        self.assertEqual(a.tobytes(), b.tobytes())


if __name__ == "__main__":
    unittest.main()
