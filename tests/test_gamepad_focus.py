"""The controller only drives Cathode while Cathode's window is in front.

XInput, /dev/input/js* and IOKit all hand controller state to any process that
asks, focused or not, so with Cathode open in a second window every press in
the game you were actually playing changed the channel behind it. The reader
now asks the app whether mpv's window has focus before emitting anything.
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.gamepad import GamepadReader, _REPEAT_DELAY


def _reader(focused_flag):
    out = []
    r = GamepadReader(lambda name, rep: out.append((name, rep)),
                      is_focused=lambda: focused_flag[0])
    return r, out


def _state():
    return {"buttons": set(), "held": {}}


class TestFocusGate(unittest.TestCase):
    def test_presses_pass_while_focused(self):
        r, out = _reader([True])
        st = _state()
        r._process({"up"}, {"a"}, st)
        self.assertEqual(out, [("a", False), ("up", False)])

    def test_nothing_is_emitted_while_unfocused(self):
        # The report: playing a game in front, Cathode behind, every press
        # reached Cathode anyway.
        r, out = _reader([False])
        st = _state()
        r._process({"up", "down"}, {"a", "b", "start"}, st)
        self.assertEqual(out, [])

    def test_a_button_held_across_refocus_is_not_a_fresh_press(self):
        # Pressed while a game had focus, still down when Cathode is refocused:
        # that must not read as a new press on the next poll. The button set is
        # kept current while gated precisely so this edge can't fire.
        flag = [False]
        r, out = _reader(flag)
        st = _state()
        r._process(set(), {"a"}, st)          # pressed while unfocused
        flag[0] = True                        # alt-tab back, still holding A
        r._process(set(), {"a"}, st)
        self.assertEqual(out, [])
        r._process(set(), set(), st)          # release
        r._process(set(), {"a"}, st)          # a genuine new press
        self.assertEqual(out, [("a", False)])

    def test_a_direction_held_across_refocus_does_not_arrive_mid_repeat(self):
        # Hold timers are dropped while gated, so refocusing with the stick
        # still pushed starts a clean press, not a burst of repeats.
        flag = [False]
        r, out = _reader(flag)
        st = _state()
        r._process({"down"}, set(), st)
        st["held"]["down"] = 0.0              # pretend a repeat is long overdue
        r._process({"down"}, set(), st)       # still unfocused: timers cleared
        self.assertEqual(st["held"], {})
        flag[0] = True
        r._process({"down"}, set(), st)
        self.assertEqual(out, [("down", False)])   # one press, no repeat
        self.assertGreater(st["held"]["down"], time.monotonic())

    def test_no_focus_callback_means_always_on(self):
        # Callers with no window to speak of (the tests, a headless run) keep
        # the old behaviour.
        out = []
        r = GamepadReader(lambda n, rep: out.append(n))
        r._process(set(), {"b"}, _state())
        self.assertEqual(out, ["b"])

    def test_refocus_restores_input_immediately(self):
        flag = [False]
        r, out = _reader(flag)
        st = _state()
        r._process(set(), {"x"}, st)
        self.assertEqual(out, [])
        flag[0] = True
        r._process(set(), set(), st)
        r._process(set(), {"y"}, st)
        self.assertEqual(out, [("y", False)])


class TestPlayerReportsFocus(unittest.TestCase):
    """The app learns focus from mpv's `focused` property, not from the OS."""

    def _player(self):
        from cathode.player import Player
        seen = []
        p = Player.__new__(Player)
        p._on_focus = seen.append
        p._on_eof = p._on_resize = p._on_playback_started = p._on_mouse_pos = None
        p._osd_w = p._osd_h = 0
        p._key_handlers = {}
        p.on_after_key = None
        p._resume_to = None
        return p, seen

    def test_focus_changes_reach_the_callback(self):
        p, seen = self._player()
        p._handle_event({"event": "property-change", "name": "focused", "data": False})
        p._handle_event({"event": "property-change", "name": "focused", "data": True})
        self.assertEqual(seen, [False, True])

    def test_an_unavailable_property_does_not_lock_the_controller_out(self):
        # A backend that can't report focus sends no bool. That must read as
        # "still focused", never as "unfocused" — otherwise a Mac would boot
        # with a dead controller.
        p, seen = self._player()
        p._handle_event({"event": "property-change", "name": "focused"})
        p._handle_event({"event": "property-change", "name": "focused", "data": None})
        self.assertEqual(seen, [])

    def test_the_app_starts_focused(self):
        from cathode.app import App
        from cathode.config import Config
        cfg = Config("")
        cfg.gamepad = False
        app = App(config=cfg, width=320, height=240, fullscreen=False, demo=True)
        self.assertTrue(app._focused)
        app._on_focus(False)
        self.assertFalse(app._focused)


if __name__ == "__main__":
    unittest.main()
