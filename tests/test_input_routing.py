"""Input routing: the focus-owner dispatch must keep buttons inside the active
screen. Regression net for the "dropped to live TV" bug family (2.2 bumpers,
wheel-on-home-screen, digits-during-Plex).

Headless: App is constructed but never run, so no mpv is launched.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.app import App  # noqa: E402
from cathode.config import Config  # noqa: E402


def make_app():
    return App(config=Config(""), width=320, height=240,
               fullscreen=False, demo=True)


class TestFocusOwner(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.r = self.app.renderer

    def test_live_is_default(self):
        self.assertEqual(self.app._focus_owner(), "live")

    def test_plex_playback_owns_focus(self):
        self.r.plex_playing = True
        self.assertEqual(self.app._focus_owner(), "plex")
        self.assertFalse(self.app._dialog_open())

    def test_dialog_beats_playback(self):
        self.r.plex_playing = True
        self.r.menu.open = True
        self.assertEqual(self.app._focus_owner(), "menu")
        self.assertTrue(self.app._dialog_open())

    def test_osk_beats_everything(self):
        self.r.plex_playing = True
        self.r.menu.open = True
        self.r.osk.open = True
        self.assertEqual(self.app._focus_owner(), "osk")


class TestRouting(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.r = self.app.renderer
        self.tuned = []
        self.app._tune = lambda idx, initial=False: self.tuned.append(idx)

    def test_wheel_on_home_screen_never_tunes(self):
        self.r.main_menu.open = True
        self.app._wheel_up()
        self.app._wheel_down()
        self.assertEqual(self.tuned, [])

    def test_wheel_in_osk_never_tunes(self):
        self.r.osk.open = True
        self.app._wheel_up()
        self.assertEqual(self.tuned, [])

    def test_wheel_during_plex_never_tunes(self):
        self.r.plex_playing = True
        self.app._wheel_down()
        self.assertEqual(self.tuned, [])

    def test_digits_ignored_during_plex_playback(self):
        self.r.plex_playing = True
        self.app._hotkey_actions = {}
        self.app._char_typed("5")
        self.assertEqual(self.app._digit_buf, "")

    def test_digits_ignored_in_ppv_browse(self):
        self.r.ppv.open = True
        self.app._hotkey_actions = {}
        self.app._char_typed("5")
        self.assertEqual(self.app._digit_buf, "")

    def test_bumpers_skip_during_plex_playback(self):
        self.r.plex_playing = True
        skips = []
        self.app._plex_skip = lambda d: skips.append(d)
        self.app._lb_action()
        self.app._rb_action()
        self.assertEqual(skips, [-1, 1])

    def test_bumpers_dead_while_dialog_over_playback(self):
        self.r.plex_playing = True
        self.r.menu.open = True
        skips = []
        self.app._plex_skip = lambda d: skips.append(d)
        self.app._lb_action()
        self.app._rb_action()
        self.assertEqual(skips, [])

    def test_triggers_seek_during_plex_playback(self):
        self.r.plex_playing = True
        seeks = []
        self.app._plex_seek = lambda d: seeks.append(d)
        self.app._lt_action()
        self.app._rt_action()
        self.assertEqual(seeks, [-10, 10])

    def test_guide_blocked_outside_live(self):
        self.r.ppv.open = True
        self.app._toggle_guide()
        from cathode.ui.renderer import UIState
        self.assertNotEqual(self.r.state, UIState.GUIDE_OPEN)


class TestTuneGuards(unittest.TestCase):
    def test_tune_with_no_channels_is_safe(self):
        app = make_app()
        app.channels = []
        app._tune(3)   # must not raise (no ZeroDivisionError)

    def test_plex_skip_falls_back_to_chapter_at_queue_edge(self):
        app = make_app()
        app._plex_queue = ["10", "11"]
        app._plex_queue_pos = 0
        chapters = []
        app.player.chapter_skip = lambda d: chapters.append(d)
        app._plex_show_osd = lambda: None
        app._plex_skip(-1)   # prev on the first item -> chapter skip
        self.assertEqual(chapters, [-1])


if __name__ == "__main__":
    unittest.main()
