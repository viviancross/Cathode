"""Capping the UI's shape on displays wider than a television.

Cathode's layout is designed for 16:9. On a phone in landscape (22:9 here) or an
ultrawide monitor, filling the display drags the menus out to the bezels and away
from the video, which mpv is already pillarboxing to 16:9. `fit_aspect` finds the
centred box to draw into; the overlay is offset to match, and pointer input has
to be shifted by the same amount or every hit test misses.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.ui.renderer import fit_aspect

WIDE = 16 / 9


class TestFitAspect(unittest.TestCase):
    def test_zero_aspect_fills_the_display(self):
        self.assertEqual(fit_aspect(2640, 1080, 0), (2640, 1080, 0, 0))

    def test_a_matching_display_is_untouched(self):
        self.assertEqual(fit_aspect(1920, 1080, WIDE), (1920, 1080, 0, 0))

    def test_a_wider_display_is_pillarboxed(self):
        w, h, x, y = fit_aspect(2640, 1080, WIDE)
        self.assertEqual((w, h), (1920, 1080))
        self.assertEqual(y, 0)
        self.assertEqual(x, (2640 - 1920) // 2)

    def test_a_taller_display_fills_when_no_minimum_is_set(self):
        # Without a lower bound the box keeps the display's own shape rather
        # than being squeezed to the maximum.
        self.assertEqual(fit_aspect(1080, 2640, WIDE), (1080, 2640, 0, 0))

    def test_a_minimum_letterboxes_a_very_tall_display(self):
        # A phone upright is ~1:2.4. Held to 3:4 the interface gets room; a
        # 16:9 band there would use a quarter of the screen and show two menu
        # rows.
        w, h, x, y = fit_aspect(1080, 2640, WIDE, 3 / 4)
        self.assertEqual(w, 1080)
        self.assertEqual(h, 1440)          # 1080 / (3/4)
        self.assertEqual(x, 0)
        self.assertEqual(y, (2640 - 1440) // 2)

    def test_a_display_already_in_range_is_untouched(self):
        self.assertEqual(fit_aspect(1080, 1080, WIDE, 3 / 4), (1080, 1080, 0, 0))

    def test_the_maximum_still_wins_on_a_wide_display(self):
        w, h, _, _ = fit_aspect(2640, 1080, WIDE, 3 / 4)
        self.assertEqual((w, h), (1920, 1080))

    def test_the_box_never_exceeds_the_display(self):
        for dw, dh in ((2640, 1080), (1080, 2640), (1000, 1000), (3440, 1440)):
            w, h, x, y = fit_aspect(dw, dh, WIDE)
            self.assertLessEqual(w, dw)
            self.assertLessEqual(h, dh)
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)

    def test_the_box_is_centred(self):
        for dw, dh in ((2640, 1080), (1080, 2640), (3440, 1440)):
            w, h, x, y = fit_aspect(dw, dh, WIDE)
            # equal margins either side, give or take an odd pixel
            self.assertLessEqual(abs((dw - w - x) - x), 1)
            self.assertLessEqual(abs((dh - h - y) - y), 1)

    def test_degenerate_sizes_do_not_divide_by_zero(self):
        self.assertEqual(fit_aspect(0, 0, WIDE), (0, 0, 0, 0))
        self.assertEqual(fit_aspect(1920, 0, WIDE), (1920, 0, 0, 0))


class TestAppUsesTheCap(unittest.TestCase):
    """The size the UI renders at, and the offset it is drawn and clicked at."""

    def _app(self, width, height, platform_aspect=0.0, config_aspect=0.0):
        from cathode.app import App
        from cathode.config import Config

        class _T:
            def try_connect(self): return True
            def send(self, data): pass
            def serve(self, on_line): pass
            def close(self): pass

        class _C:
            def connect(self, args): return _T()
            def alive(self): return True
            def shutdown(self): pass

        cfg = Config("")
        cfg.gamepad = False
        cfg.ui_max_aspect = config_aspect
        return App(config=cfg, width=width, height=height, fullscreen=False,
                   connection=_C(), ui_max_aspect=platform_aspect)

    def test_the_renderer_is_sized_to_the_box(self):
        app = self._app(2640, 1080, platform_aspect=WIDE)
        self.assertEqual((app.renderer.width, app.renderer.height), (1920, 1080))

    def test_the_overlay_is_offset_to_centre_it(self):
        app = self._app(2640, 1080, platform_aspect=WIDE)
        self.assertEqual(app.renderer.overlay_pos, (360, 0))

    def test_without_a_cap_the_display_is_filled(self):
        app = self._app(2640, 1080)
        self.assertEqual((app.renderer.width, app.renderer.height), (2640, 1080))
        self.assertEqual(app.renderer.overlay_pos, (0, 0))

    def test_config_overrides_the_platform_default(self):
        # A user who wants it edge to edge on a phone sets a very wide aspect.
        app = self._app(2640, 1080, platform_aspect=WIDE, config_aspect=2640 / 1080)
        self.assertEqual((app.renderer.width, app.renderer.height), (2640, 1080))

    def test_the_guide_preview_box_is_converted_into_surface_space(self):
        # mpv's video margins are ratios of the whole surface, but the guide's
        # preview box is in UI coordinates. When the UI is inset those differ,
        # and skipping the conversion puts the video preview in the wrong place.
        from cathode.ui.renderer import UIState
        app = self._app(2640, 1080, platform_aspect=WIDE)
        r = app.renderer
        boxes = []
        r.player.set_video_box = lambda *a: boxes.append(a)
        r.state = UIState.GUIDE_OPEN
        r.guide.preview_box_px = lambda: (0, 0, 1920, 1080)   # the whole UI box
        r._apply_video_box()
        left, right, top, bottom = boxes[-1]
        # The UI box starts 360px into a 2640px surface and fills its height.
        self.assertAlmostEqual(left, 360 / 2640, places=4)
        self.assertAlmostEqual(right, 360 / 2640, places=4)
        self.assertAlmostEqual(top, 0.0, places=4)
        self.assertAlmostEqual(bottom, 0.0, places=4)

    def test_the_preview_box_is_unconverted_when_the_ui_fills_the_display(self):
        from cathode.ui.renderer import UIState
        app = self._app(1920, 1080)
        r = app.renderer
        boxes = []
        r.player.set_video_box = lambda *a: boxes.append(a)
        r.state = UIState.GUIDE_OPEN
        r.guide.preview_box_px = lambda: (480, 270, 1440, 810)
        r._apply_video_box()
        self.assertEqual(
            tuple(round(v, 4) for v in boxes[-1]), (0.25, 0.25, 0.25, 0.25))

    def test_pointer_coordinates_are_shifted_into_the_ui_box(self):
        app = self._app(2640, 1080, platform_aspect=WIDE)
        app._on_mouse_pos(360, 10)        # left edge of the UI box
        self.assertEqual(app._last_mouse, (0, 10))
        app._on_mouse_pos(1320, 540)      # centre of the display
        self.assertEqual(app._last_mouse, (960, 540))


if __name__ == "__main__":
    unittest.main()
