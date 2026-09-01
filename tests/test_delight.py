"""Delight features: stand-by card, SMPTE bars, VCR tags, moon phase, attract
arming. Headless — a stub player, no mpv."""

import os
import time
import tempfile
import unittest
from datetime import datetime, timezone

from PIL import Image, ImageDraw

from cathode.ui import effects, guide
from cathode.ui.renderer import Renderer, UIState


class _Player:
    def command(self, *a, **k): pass
    def set_video_box(self, *a): pass
    def reset_video_box(self): pass


def _renderer():
    path = os.path.join(tempfile.gettempdir(), "cathode-test-overlay.bgra")
    return Renderer(_Player(), 320, 240, overlay_path=path)


class TestDelight(unittest.TestCase):
    def test_smpte_bars_paint_all_seven(self):
        img = Image.new("RGBA", (140, 20), (0, 0, 0, 255))
        effects.draw_smpte_bars(ImageDraw.Draw(img), 0, 0, 140, 20)
        seen = {img.getpixel((int((i + 0.5) * 20), 10))[:3]
                for i in range(7)}
        self.assertEqual(seen, set(effects.SMPTE_BARS))

    def test_standby_card_renders_and_clears(self):
        r = _renderer()
        r.crt_on = r.vignette_on = False   # sample raw card pixels
        r.standby = True
        frame = r._render()
        # Top-left pixel sits in the first (gray) SMPTE bar.
        self.assertEqual(frame.getpixel((5, 5))[:3], effects.SMPTE_BARS[0])
        r.begin_channel_change()
        self.assertFalse(r.standby)   # a new tune clears the card

    def test_power_off_collapses_to_a_dark_screen(self):
        # The app is called Cathode; quitting used to cut straight to black.
        r = _renderer()
        r.main_menu.open = True
        pushed = []
        r._push_to_mpv = lambda im: pushed.append(im.copy())
        r.power_off()
        self.assertGreater(len(pushed), 6)          # it actually animated
        last = pushed[-1].convert("RGB")
        self.assertEqual(last.getextrema(), ((0, 0), (0, 0), (0, 0)))

    def test_power_off_squashes_toward_the_middle(self):
        # Midway through the collapse the picture must be a band around the
        # centre line, with the top and bottom of the screen already dark.
        r = _renderer()
        r.main_menu.open = True
        pushed = []
        r._push_to_mpv = lambda im: pushed.append(im.copy())
        r.power_off()
        mid = pushed[len(pushed) // 4].convert("RGB")
        w, h = mid.size
        self.assertEqual(mid.getpixel((w // 2, 2)), (0, 0, 0))
        self.assertEqual(mid.getpixel((w // 2, h - 3)), (0, 0, 0))
        self.assertNotEqual(mid.getpixel((w // 2, h // 2)), (0, 0, 0))

    def test_power_off_is_bounded(self):
        # It runs on the way out; it must not hold the process open.
        r = _renderer()
        r._push_to_mpv = lambda im: None
        t0 = time.monotonic()
        r.power_off()
        self.assertLess(time.monotonic() - t0, r.POWER_OFF + 0.5)

    def test_power_off_honours_reduced_motion(self):
        r = _renderer()
        r.reduce_motion = True
        pushed = []
        r._push_to_mpv = lambda im: pushed.append(im)
        r.power_off()
        self.assertEqual(pushed, [])

    def test_power_off_never_blocks_the_exit(self):
        # A decorative send-off must not be able to keep the app alive, so a
        # failure anywhere inside it is swallowed.
        r = _renderer()

        def boom():
            raise RuntimeError("render failed during shutdown")
        r._render = boom
        r.power_off()          # must not raise

    def test_vcr_tags_render(self):
        r = _renderer()
        r.plex_playing = True
        r.plexosd.paused = True
        r._render()                   # "|| PAUSE" + tracking band path
        r.plexosd.paused = False
        r._vcr_tag = "PLAY >"
        r._vcr_tag_until = 1e12
        r._render()                   # flash path

    def test_moon_phase(self):
        new = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
        full = datetime(2000, 1, 21, 4, 40, tzinfo=timezone.utc)
        self.assertAlmostEqual(guide._moon_phase(new), 0.0, places=3)
        self.assertAlmostEqual(guide._moon_phase(full), 0.5, delta=0.02)
        p = guide._moon_phase()
        self.assertTrue(0.0 <= p < 1.0)

    def test_demo_button_only_without_playlist(self):
        from cathode.ui.mainmenu import MainMenu
        m = MainMenu(320, 240)
        self.assertNotIn("demo", [k for k, _ in m._buttons()])
        m.demo_hint = True
        keys = [k for k, _ in m._buttons()]
        self.assertEqual(keys.index("demo"), 2)      # after Load Playlist
        self.assertEqual(len(keys), len(set(keys)))  # no duplicates
        pressed = []
        m.show(pressed.append)
        m._sel = 2
        m.press()
        self.assertEqual(pressed, ["demo"])
        m.open = True
        m.render()                                   # hint line draws

    def test_attract_arms_only_idle_on_home_or_guide(self):
        r = _renderer()
        r._last_activity = 0.0        # long idle
        self.assertFalse(r._attract_due(1e6))       # watching → never
        r.main_menu.open = True
        self.assertTrue(r._attract_due(1e6))
        r.menu.open = True                           # dialog blocks it
        self.assertFalse(r._attract_due(1e6))
        r.menu.open = False
        r.mark_dirty()                               # activity resets the clock
        self.assertFalse(r._attract_due(r._last_activity + 1))


if __name__ == "__main__":
    unittest.main()
