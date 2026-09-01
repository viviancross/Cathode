"""Toast transition: envelope shape, its frame driver, and reduced motion.

The toast is the app's only general feedback channel, and it used to blink on
and off. These pin the arrival/departure envelope, the fact that the render
thread keeps painting while it moves (outside a channel change the loop only
paints on input or once a second), and that motion can be switched off.
"""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.ui import renderer as R  # noqa: E402
from cathode.ui.renderer import Renderer  # noqa: E402


class _Player:
    def command(self, *a, **k): pass
    def set_video_box(self, *a): pass
    def reset_video_box(self): pass


def _renderer(w=320, h=240):
    path = os.path.join(tempfile.gettempdir(), "cathode-test-motion.bgra")
    return Renderer(_Player(), w, h, overlay_path=path)


def _toast(r, age=0.0, life=2.5):
    """Put a toast on `r` that appeared `age` seconds ago."""
    now = time.monotonic()
    r.notification = "Queued: Aliens"
    r._notif_shown_at = now - age
    r.notification_until = now - age + life
    return r


class TestEasing(unittest.TestCase):
    def test_curves_are_anchored(self):
        for fn in (R._ease_out_quart, R._ease_in_quad):
            self.assertAlmostEqual(fn(0.0), 0.0, places=6)
            self.assertAlmostEqual(fn(1.0), 1.0, places=6)

    def test_curves_clamp_outside_the_unit_range(self):
        for fn in (R._ease_out_quart, R._ease_in_quad):
            self.assertEqual(fn(-5.0), 0.0)
            self.assertEqual(fn(5.0), 1.0)

    def test_out_quart_is_front_loaded_and_in_quad_is_back_loaded(self):
        # An arrival should be most of the way there early; a departure should
        # start slowly and accelerate away. Swapping them reads as sluggish
        # arrivals and abrupt exits.
        self.assertGreater(R._ease_out_quart(0.25), 0.5)
        self.assertLess(R._ease_in_quad(0.25), 0.25)

    def test_both_curves_are_monotonic(self):
        for fn in (R._ease_out_quart, R._ease_in_quad):
            vals = [fn(i / 40) for i in range(41)]
            self.assertEqual(vals, sorted(vals), fn.__name__)


class TestToastEnvelope(unittest.TestCase):
    def test_it_arrives_from_above_and_settles(self):
        r = _renderer()
        _toast(r, age=0.0)
        op, dy = r._notif_envelope()
        self.assertAlmostEqual(op, 0.0, places=2)
        self.assertLess(dy, 0)                     # starts above its resting place

        _toast(r, age=r.NOTIF_IN + 0.01)
        op, dy = r._notif_envelope()
        self.assertEqual((round(op, 3), dy), (1.0, 0))

    def test_it_leaves_by_lifting_back_out(self):
        r = _renderer()
        _toast(r, age=2.5 - r.NOTIF_OUT / 2, life=2.5)
        op, dy = r._notif_envelope()
        self.assertLess(op, 1.0)
        self.assertGreater(op, 0.0)
        self.assertLess(dy, 0)

    def test_opacity_never_leaves_the_unit_range(self):
        r = _renderer()
        for age in [i / 100 for i in range(0, 260, 3)]:
            _toast(r, age=age, life=2.5)
            op, _ = r._notif_envelope()
            self.assertGreaterEqual(op, 0.0, age)
            self.assertLessEqual(op, 1.0, age)

    def test_the_exit_is_quicker_than_the_entrance(self):
        # A departure that takes as long as an arrival reads as hesitation.
        r = _renderer()
        self.assertLess(r.NOTIF_OUT, r.NOTIF_IN)

    def test_the_whole_transition_stays_in_the_feedback_range(self):
        # Product register: state feedback belongs in 150-250ms, not half a
        # second of choreography the user has to wait through.
        r = _renderer()
        self.assertLessEqual(r.NOTIF_IN, 0.25)
        self.assertLessEqual(r.NOTIF_OUT, 0.25)


class TestFrameDriver(unittest.TestCase):
    """Outside a channel change the render loop paints on input or once a
    second, so a transition needs its own reason to keep drawing."""

    def test_animating_during_arrival_and_departure(self):
        r = _renderer()
        _toast(r, age=0.02)
        self.assertTrue(r._notif_animating())
        _toast(r, age=2.5 - r.NOTIF_OUT / 2, life=2.5)
        self.assertTrue(r._notif_animating())

    def test_idle_while_the_toast_just_sits_there(self):
        # The hold period must NOT keep the render thread busy.
        r = _renderer()
        _toast(r, age=1.0, life=2.5)
        self.assertFalse(r._notif_animating())

    def test_idle_with_no_toast(self):
        r = _renderer()
        r.notification = ""
        self.assertFalse(r._notif_animating())


class TestReducedMotion(unittest.TestCase):
    def test_it_resolves_instantly_to_the_end_state(self):
        r = _renderer()
        r.reduce_motion = True
        _toast(r, age=0.0)
        self.assertEqual(r._notif_envelope(), (1.0, 0))

    def test_it_stops_the_render_thread_animating(self):
        r = _renderer()
        r.reduce_motion = True
        _toast(r, age=0.02)
        self.assertFalse(r._notif_animating())

    def test_the_toast_is_still_drawn(self):
        # Reduced motion removes the movement, never the message.
        r = _renderer()
        r.reduce_motion = True
        _toast(r, age=0.0)
        r.main_menu.open = True
        before = r._render().copy()
        r.notification = ""
        after = r._render()
        self.assertNotEqual(before.tobytes(), after.tobytes())


class TestBoundedRepaint(unittest.TestCase):
    def test_the_patch_is_the_pill_not_the_screen(self):
        # This runs every frame of the transition; a full-surface patch to move
        # a small pill spends the frame budget on empty pixels.
        r = _renderer(1280, 800)
        _toast(r, age=0.05)
        bx, by, bw, bh = r._notif_box()
        self.assertLess(bw, r.width // 2)
        self.assertLess(bh, r.height // 8)
        self.assertGreaterEqual(bx, 0)
        self.assertGreaterEqual(by, 0)

    def test_the_pill_stays_on_screen_horizontally(self):
        r = _renderer(1280, 800)
        _toast(r, age=0.05)
        bx, _by, bw, _bh = r._notif_box()
        self.assertGreaterEqual(bx, 0)
        self.assertLessEqual(bx + bw, r.width)

    def test_no_box_without_a_toast(self):
        r = _renderer()
        r.notification = ""
        self.assertIsNone(r._notif_box())


class TestWiring(unittest.TestCase):
    def test_config_default_has_motion_on(self):
        from cathode.config import Config
        self.assertTrue(Config("").motion_enabled)

    def test_the_editor_toggle_reaches_the_renderer(self):
        from cathode.app import App
        from cathode.config import Config
        cfg = Config("")
        cfg.gamepad = False
        app = App(config=cfg, width=320, height=240, fullscreen=False, demo=True)
        app.config.save = lambda: None
        self.assertFalse(app.renderer.reduce_motion)

        state = app.renderer.editor.state()
        state["motion"] = False
        app._editor_changed(state)
        self.assertTrue(app.renderer.reduce_motion)
        self.assertFalse(app.config.motion_enabled)

    def test_motion_is_not_saved_into_a_theme(self):
        # It is an accessibility preference, not part of the look, so it must
        # not ride the editor's save/revert cycle.
        from cathode.app import App
        from cathode.config import Config
        cfg = Config("")
        cfg.gamepad = False
        app = App(config=cfg, width=320, height=240, fullscreen=False, demo=True)
        snap = app._visual_snapshot()
        self.assertNotIn("motion", snap)


if __name__ == "__main__":
    unittest.main()
