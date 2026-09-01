"""The CRT is the whole app, not a layer over video.

Guards two things that were separately broken: the tube reaching every screen
(the opaque full-screen pages returned before it was ever composited), and the
scanline geometry staying tube-shaped instead of window-shaped.
"""

import os
import tempfile
import unittest

import numpy as np
from PIL import Image

from cathode.ui import effects
from cathode.ui.renderer import Renderer, UIState


class _Player:
    def command(self, *a, **k): pass
    def set_video_box(self, *a): pass
    def reset_video_box(self): pass


def _renderer(w=320, h=240):
    path = os.path.join(tempfile.gettempdir(), "cathode-test-crt.bgra")
    return Renderer(_Player(), w, h, overlay_path=path)


def _differs(a, b) -> bool:
    """Whether two frames differ at all. Comparing the same screen rendered
    with the tube on and off is the only honest test that it was applied —
    looking for row-to-row variation in one frame just finds the UI's own
    content."""
    return np.abs(np.asarray(a, dtype=np.int16)
                  - np.asarray(b, dtype=np.int16)).max() > 0


class TestScanlineGeometry(unittest.TestCase):
    def test_pitch_scales_with_the_screen(self):
        # The tube has a fixed line count; the window does not change it. A
        # fixed 1px pitch made 4K hairlines and 480p coarse stripes.
        self.assertAlmostEqual(effects.scanline_pitch(480), 2.0, places=2)
        self.assertAlmostEqual(effects.scanline_pitch(1080), 4.5, places=2)
        self.assertAlmostEqual(effects.scanline_pitch(2160), 9.0, places=2)

    def test_pitch_never_collapses_below_two_pixels(self):
        for h in (1, 100, 240, 479):
            self.assertGreaterEqual(effects.scanline_pitch(h), 2.0, h)

    def test_profile_is_soft_not_a_hard_on_off_row(self):
        # A raised cosine, not alternating rows: at least three distinct alpha
        # levels down a column. The old overlay had exactly two.
        ov = effects.make_crt_overlay(64, 800, alpha=40)
        col = np.asarray(ov)[:, 0, 3]
        self.assertGreaterEqual(len(set(col.tolist())), 3)

    def test_slot_mask_gives_the_overlay_vertical_structure(self):
        ov = effects.make_crt_overlay(64, 800, alpha=40)
        row = np.asarray(ov)[0, :, 3]
        self.assertGreater(len(set(row.tolist())), 1)

    def test_zero_alpha_is_a_clear_overlay(self):
        ov = effects.make_crt_overlay(32, 32, alpha=0)
        self.assertEqual(np.asarray(ov)[:, :, 3].max(), 0)

    def test_it_does_not_darken_more_than_the_overlay_it_replaced(self):
        # Legibility guard: the old cache put `alpha` on every other row, so
        # mean alpha was alpha/2. The new one must not exceed that by much or
        # it eats the smallest metadata text.
        new = np.asarray(effects.make_crt_overlay(256, 800, alpha=40))[:, :, 3]
        old = np.asarray(effects.make_scanline_cache(256, 800, 40))[:, :, 3]
        self.assertLess(new.mean(), old.mean() * 1.5)


class TestCombine(unittest.TestCase):
    def test_merged_layer_matches_stacking_them(self):
        a = effects.make_crt_overlay(64, 64, alpha=40)
        b = effects.make_vignette(64, 64, strength=0.35)
        base = Image.new("RGBA", (64, 64), (200, 120, 60, 255))
        stacked = Image.alpha_composite(Image.alpha_composite(base, a), b)
        merged = Image.alpha_composite(base, effects.combine_dark_overlays(a, b))
        diff = np.abs(np.asarray(stacked, dtype=np.int16)
                      - np.asarray(merged, dtype=np.int16))
        self.assertLessEqual(int(diff.max()), 2)   # rounding only

    def test_no_layers_is_none(self):
        self.assertIsNone(effects.combine_dark_overlays())
        self.assertIsNone(effects.combine_dark_overlays(None))


class TestCrtReachesEveryScreen(unittest.TestCase):
    """The bug this file exists for: the home, browse and detail pages each
    returned early from _render, so the tube was never composited over them."""

    SCREENS = {
        "home": lambda r: setattr(r.main_menu, "open", True),
        "ppv browse": lambda r: setattr(r.ppv, "open", True),
        "plex info": lambda r: setattr(r.plexinfo, "open", True),
        "guide": lambda r: setattr(r, "state", UIState.GUIDE_OPEN),
        "watching tv": lambda r: None,
        "plex playback": lambda r: setattr(r, "plex_playing", True),
    }

    def test_every_screen_is_inside_the_tube(self):
        for name, setup in self.SCREENS.items():
            on = _renderer()
            setup(on)
            lit = on._render()

            off = _renderer()
            setup(off)
            off.crt_on = False
            off.vignette_on = False
            plain = off._render()

            self.assertTrue(_differs(lit, plain),
                            f"{name}: renders identically with the CRT off, "
                            f"so the tube is never applied to it")

    def test_turning_the_crt_off_leaves_the_screen_untouched(self):
        for name, setup in self.SCREENS.items():
            r = _renderer()
            setup(r)
            r.crt_on = False
            r.vignette_on = False
            self.assertIsNone(r.crt_layer, name)
            # With no layer, _apply_crt must be a genuine no-op.
            frame = Image.new("RGBA", (r.width, r.height), (7, 11, 13, 255))
            self.assertFalse(_differs(frame, r._apply_crt(frame)), name)

    def test_a_plain_attribute_assignment_still_rebuilds_the_layer(self):
        # app.py assigns these straight from config; with the layer cached, a
        # plain assignment used to change the flag and keep compositing the
        # old overlay.
        r = _renderer()
        self.assertIsNotNone(r.crt_layer)
        r.crt_on = False
        r.vignette_on = False
        self.assertIsNone(r.crt_layer)
        r.crt_on = True
        self.assertIsNotNone(r.crt_layer)

    def test_scanline_alpha_change_rebuilds_the_layer(self):
        r = _renderer()
        before = np.asarray(r.crt_layer)[:, :, 3].mean()
        r.set_scanline_alpha(120)
        after = np.asarray(r.crt_layer)[:, :, 3].mean()
        self.assertGreater(after, before)


class TestLegibilityUnderTheTube(unittest.TestCase):
    """The palette is solved for contrast, but the CRT is composited on top of
    it, so what the viewer actually sees is dimmer than the palette says. This
    pins the shipped number rather than the theoretical one.
    """

    W, H = 1280, 800

    def _centre_darkening(self, alpha):
        """Mean darkening over the band where body text and list rows sit.
        Not the whole frame: the vignette is a corner effect and averaging it
        across the picture would overstate what centre text suffers."""
        from cathode.ui import effects as fx
        scan = np.asarray(fx.make_crt_overlay(self.W, self.H, alpha))[:, :, 3]
        vig = np.asarray(fx.make_vignette(self.W, self.H, 0.35))[:, :, 3]
        x0, x1 = int(self.W * 0.05), int(self.W * 0.95)
        y0, y1 = int(self.H * 0.25), int(self.H * 0.90)
        keep = ((1 - scan[y0:y1, x0:x1] / 255.0)
                * (1 - vig[y0:y1, x0:x1] / 255.0))
        return float((1.0 - keep).mean())

    @staticmethod
    def _dimmed(rgb, k):
        return tuple(int(c * (1.0 - k)) for c in rgb[:3])

    def test_body_text_stays_readable_through_the_crt(self):
        from cathode.ui import theme
        k = self._centre_darkening(40)          # shipped default
        for name, pal in theme.PALETTES.items():
            bg = self._dimmed(pal["SCREEN_BG"], k)
            fg = self._dimmed(pal["WHITE_DIM"], k)
            ratio = theme.contrast(fg, bg)
            self.assertGreaterEqual(
                ratio, 4.5, f"{name}: body text is {ratio:.2f}:1 under the CRT")

    def test_muted_text_holds_the_large_text_bar_through_the_crt(self):
        # 4.5:1 in the palette lands near 3.6:1 once the tube darkens both ink
        # and ground. PRODUCT.md sets no WCAG target and this tier is metadata
        # and hints viewed at ten feet, so 3:1 is the floor being defended —
        # but it IS a floor, and raising the scanline default would eat it.
        from cathode.ui import theme
        k = self._centre_darkening(40)
        for name, pal in theme.PALETTES.items():
            bg = self._dimmed(pal["SCREEN_BG"], k)
            fg = self._dimmed(pal["INK_MUTED"], k)
            ratio = theme.contrast(fg, bg)
            self.assertGreaterEqual(
                ratio, 3.0, f"{name}: muted text is {ratio:.2f}:1 under the CRT")

    def test_the_vignette_leaves_the_middle_of_the_picture_alone(self):
        # A linear falloff darkened from the centre outward, which read as a
        # grey wash over the picture instead of edges rolling off.
        from cathode.ui import effects as fx
        vig = np.asarray(fx.make_vignette(self.W, self.H, 0.35))[:, :, 3]
        centre = vig[self.H // 2, self.W // 2]
        corner = vig[0, 0]
        self.assertLessEqual(int(centre), 4)
        self.assertGreater(int(corner), 80)


if __name__ == "__main__":
    unittest.main()
