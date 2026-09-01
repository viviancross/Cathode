"""The guide shows its own way out.

The guide closes on B / Escape / the guide key, none of which a phone has, and
the system back gesture is a step up rather than something the screen
advertises. Cathode's rule is that whatever a button does, an on-screen control
does too.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.ui.guide import Guide


class TestGuideCloseButton(unittest.TestCase):
    def setUp(self):
        self.g = Guide(1920, 1080)

    def test_the_button_sits_inside_the_header(self):
        x0, y0, x1, y1 = self.g.close_rect_px()
        self.assertGreaterEqual(y0, 0)
        self.assertLessEqual(y1, self.g.header_h)
        self.assertLessEqual(x1, self.g.width)

    def test_it_is_hit_at_its_centre(self):
        x0, y0, x1, y1 = self.g.close_rect_px()
        self.assertTrue(self.g.hit_close((x0 + x1) // 2, (y0 + y1) // 2))

    def test_it_is_not_hit_elsewhere(self):
        self.assertFalse(self.g.hit_close(10, 10))                    # far left
        self.assertFalse(self.g.hit_close(self.g.width // 2,
                                          self.g.height - 10))        # bottom

    def test_it_does_not_overlap_the_category_bar(self):
        _, _, _, cy1 = self.g.close_rect_px()
        _, by0, _, _ = self.g.category_bar_px()
        self.assertLessEqual(cy1, by0)

    def test_it_survives_a_resize(self):
        for w, h in ((1280, 720), (2640, 1080), (3840, 2160)):
            g = Guide(w, h)
            x0, y0, x1, y1 = g.close_rect_px()
            self.assertLessEqual(x1, w)
            self.assertLessEqual(y1, g.header_h)
            self.assertTrue(g.hit_close((x0 + x1) // 2, (y0 + y1) // 2))

    def test_it_is_a_usable_touch_target(self):
        # Small enough to miss is the same as not being there.
        x0, y0, x1, y1 = self.g.close_rect_px()
        self.assertGreaterEqual(x1 - x0, 88)
        self.assertGreaterEqual(y1 - y0, 26)


if __name__ == "__main__":
    unittest.main()
