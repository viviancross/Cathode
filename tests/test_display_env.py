"""Linux display set-up: SDL falls back to X11 when the session asks for a
Wayland it can't reach, and PyOpenGL is told to use what SDL really uses."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from cathode import gfx  # noqa: E402


class TestLinuxDisplay(unittest.TestCase):
    def run_with(self, env, results, driver):
        calls = iter(results)

        def init():
            r = next(calls)
            if r:
                raise pygame.error(r)
        with mock.patch.object(gfx.sys, "platform", "linux"), mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(gfx.pygame.display, "init", init), \
                mock.patch.object(gfx.pygame.display, "get_driver", lambda: driver):
            gfx.settle_linux_display()
            return dict(os.environ)

    def test_an_unreachable_wayland_falls_back_to_x11_and_glx(self):
        env = self.run_with({"SDL_VIDEODRIVER": "wayland"}, ["wayland not available", None], "x11")
        self.assertEqual(env["SDL_VIDEODRIVER"], "x11")
        self.assertEqual(env["PYOPENGL_PLATFORM"], "glx")

    def test_a_real_wayland_uses_egl(self):
        env = self.run_with({"SDL_VIDEODRIVER": "wayland"}, [None], "wayland")
        self.assertEqual(env["PYOPENGL_PLATFORM"], "egl")

    def test_x11_in_a_wayland_session_uses_glx(self):
        env = self.run_with({"XDG_SESSION_TYPE": "wayland"}, [None], "x11")
        self.assertEqual(env["PYOPENGL_PLATFORM"], "glx")

    def test_the_users_own_choice_wins(self):
        env = self.run_with({"PYOPENGL_PLATFORM": "egl"}, [None], "x11")
        self.assertEqual(env["PYOPENGL_PLATFORM"], "egl")


if __name__ == "__main__":
    unittest.main()
