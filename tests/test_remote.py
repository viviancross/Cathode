"""Every device becomes the same remote buttons; rebinding replaces a
button's keys rather than adding to them."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from cathode import remote as R  # noqa: E402


def key(code, unicode=""):
    return pygame.event.Event(pygame.KEYDOWN, key=code, mod=0, unicode=unicode)


class TestRemote(unittest.TestCase):
    def test_keys_media_keys_and_digits_map_to_buttons(self):
        r = R.Remote()
        self.assertEqual(r.translate(key(pygame.K_g)), [R.GUIDE])
        self.assertEqual(r.translate(key(pygame.K_5)), ["DIGIT5"])
        self.assertEqual(r.translate(key(pygame.K_KP5)), ["DIGIT5"])
        if hasattr(pygame, "K_AUDIOPLAY"):
            self.assertEqual(r.translate(key(pygame.K_AUDIOPLAY)), [R.PAUSE])

    def test_rebinding_replaces_the_default_key(self):
        r = R.Remote(key_overrides={R.GUIDE: "h"})
        self.assertEqual(r.translate(key(pygame.K_h)), [R.GUIDE])
        self.assertEqual(r.translate(key(pygame.K_g)), [])

    def test_a_3x_binding_is_ignored(self):
        r = R.Remote(key_overrides={"guide": "h"})
        self.assertEqual(r.translate(key(pygame.K_g)), [R.GUIDE])

    def test_controller_rebinding(self):
        r = R.Remote(pad_overrides={R.GUIDE: "Y"})
        self.assertEqual(r.pad_for(R.GUIDE), "Y")
        self.assertEqual(r.pad_for(R.INFO), "-")      # Y moved off INFO

    def test_a_stick_needs_to_pass_the_threshold_and_come_back(self):
        r = R.Remote()
        ev = lambda v: pygame.event.Event(pygame.CONTROLLERAXISMOTION, instance_id=0,
                                          axis=pygame.CONTROLLER_AXIS_LEFTY, value=v)
        self.assertEqual(r.translate(ev(15000)), [])          # resting drift
        self.assertEqual(r.translate(ev(30000)), [R.DOWN])
        self.assertEqual(r.translate(ev(31000)), [])          # still held: no repeat here
        r.translate(ev(0))
        self.assertEqual(r.translate(ev(30000)), [R.DOWN])


if __name__ == "__main__":
    unittest.main()
