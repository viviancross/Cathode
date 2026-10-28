"""The FLIRC wizard: every bindable button records a HID key, the tool is
found where Flirc installs it, and a run's message is its telling line."""
import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from cathode import flirc, remote as R  # noqa: E402


class TestKeys(unittest.TestCase):
    def test_every_walk_through_button_has_a_hid_key(self):
        from cathode.menus import FLIRC_ORDER
        pygame.init()
        keys = R.Remote().keys
        for a in FLIRC_ORDER:
            self.assertIsNotNone(flirc.key_for(keys, a), a)
        self.assertEqual(flirc.key_for(keys, R.GUIDE), "g")            # a letter before anything
        self.assertEqual(flirc.key_for(keys, R.CH_UP), "]")
        self.assertEqual(flirc.key_for(keys, R.DIGITS[3]), "3")
        self.assertEqual(flirc.HID["3"], 32)
        self.assertEqual(flirc.HID["up"], 82)
        self.assertIsNone(flirc.key_for(keys, R.SKIP))                  # a media key only

    def test_steps_name_the_remote_button(self):
        from types import SimpleNamespace
        from cathode.menus import flirc_steps
        pygame.init()
        app = SimpleNamespace(remote=R.Remote(), config=SimpleNamespace(remote="sony_rm_y195"))
        steps = flirc_steps(app, [R.BACK, R.GUIDE, R.DIGITS[0], R.SKIP])
        self.assertEqual([s[0] for s in steps], ["Press RESET for Back", "Press GUIDE for Guide", "Press the button for 0"])
        self.assertEqual(steps[0][1], ["record_api", "0", "42"])        # backspace


class TestTool(unittest.TestCase):
    def test_found_by_override_flatpak_path_or_install(self):
        self.assertEqual(flirc.find("/opt/flirc_util"), ["/opt/flirc_util"])
        with mock.patch.dict(os.environ, {"FLATPAK_ID": "tv.cathode"}):
            self.assertEqual(flirc.find()[:2], ["flatpak-spawn", "--host"])
        with mock.patch.dict(os.environ, {"FLATPAK_ID": ""}), mock.patch("shutil.which", return_value=None), \
                mock.patch("os.path.exists", return_value=False):
            os.environ.pop("FLATPAK_ID")
            self.assertIsNone(flirc.find())

    def test_the_message_is_the_telling_line(self):
        self.assertEqual(flirc.last_line("Press any button on the remote to link it with 'g'\n\n  Succesfully recorded button\n", 0),
                         "Succesfully recorded button")
        self.assertEqual(flirc.last_line("Press any button on the remote to link it with 'g'\n"
                                         "Error: button already exists\n[D] lib/libflirc/fw_4.0.c (326): Error\n", 1),
                         "Error: button already exists")
        self.assertEqual(flirc.last_line("", 0), "Done")
        self.assertEqual(flirc.last_line("", 3), "flirc_util exited 3")


class FakeApp:
    def __init__(self):
        self.screens, self.toasts, self.timers = [object()], [], []
        self.config = mock.Mock(flirc_util="")

    def push(self, s):
        self.screens.append(s)

    def pop(self, s):
        self.screens.remove(s)

    def after(self, secs, fn):
        self.timers.append(fn)

    def toast(self, text, secs=2.5):
        self.toasts.append(text)

    def invalidate(self):
        pass


class TestWizard(unittest.TestCase):
    def test_without_the_tool_it_says_so_and_closes(self):
        from cathode.screens.flircwiz import FlircWizard
        app = FakeApp()
        reports = []
        with mock.patch("cathode.flirc.find", return_value=None):
            w = FlircWizard(app, [("Press the button for Guide", ["record_api", "0", "10"])] * 2, lambda n, s: reports.append(n))
            app.push(w)
            for fn in app.timers:
                fn()
        self.assertNotIn(w, app.screens)
        self.assertTrue(app.toasts[-1].startswith("flirc_util not found"))
        self.assertEqual(reports, [])

    def test_right_skips_and_esc_stops(self):
        from cathode import remote as R
        from cathode.screens.flircwiz import FlircWizard
        app = FakeApp()
        reports = []
        runs = []
        with mock.patch("cathode.flirc.Flirc.run", lambda self, args, done: runs.append(args)), \
                mock.patch("cathode.flirc.Flirc.cancel"):
            w = FlircWizard(app, [("Press the button for Guide", ["a"]), ("Press the button for Info", ["b"])],
                            lambda n, s: reports.append((n, s)))
            app.push(w)
            app.timers[0]()
            self.assertEqual(w.prompt, "Press the button for Guide")
            w.handle(R.RIGHT)
            self.assertEqual(w.prompt, "Press the button for Info")
            w._got(True, "Succesfully recorded button")
        self.assertEqual(runs, [["a"], ["b"]])
        self.assertEqual(reports, [(1, ["Press the button for Guide"])])
        self.assertNotIn(w, app.screens)


if __name__ == "__main__":
    unittest.main()
