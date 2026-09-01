"""The gamepad action map must exist whatever is emitting the actions.

`_gamepad_buttons` maps normalized action names ("a", "start", ...) to handlers.
It used to be built only when the native /dev/input reader was enabled, which
made it look like a property of that reader. It isn't: Android delivers the same
action names from KeyEvents with the reader switched off, and every button press
then crashed the dispatch thread on a missing attribute.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.app import App
from cathode.config import Config


class _FakeTransport:
    def try_connect(self):
        return True

    def send(self, data):
        pass

    def serve(self, on_line):
        pass

    def close(self):
        pass


class _FakeConnection:
    """Stands in for a platform that drives mpv itself, as Android does."""

    def connect(self, args):
        return _FakeTransport()

    def alive(self):
        return True

    def shutdown(self):
        pass


def _app(gamepad):
    cfg = Config("")
    cfg.gamepad = gamepad
    return App(config=cfg, width=320, height=240, fullscreen=False,
               connection=_FakeConnection())


class TestGamepadButtonMap(unittest.TestCase):
    def test_the_map_is_built_even_with_the_native_reader_off(self):
        app = _app(gamepad=False)
        app._build_gamepad_buttons()
        self.assertTrue(app._gamepad_buttons)

    def test_the_map_covers_the_select_button(self):
        # "a" is the action every screen uses to activate; without it the UI is
        # navigable but nothing can be chosen.
        app = _app(gamepad=False)
        app._build_gamepad_buttons()
        self.assertIn("a", app._gamepad_buttons)

    def test_dispatch_does_not_raise_when_the_reader_is_off(self):
        app = _app(gamepad=False)
        app._build_gamepad_buttons()
        app._gamepad_dispatch("a", False)   # must not raise AttributeError


if __name__ == "__main__":
    unittest.main()
