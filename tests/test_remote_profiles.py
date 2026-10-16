"""Remote profiles: every remote button has a keyboard key an IR receiver
can send, and hints use the chosen remote's names."""
import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from cathode import remote as R  # noqa: E402


class TestRemoteProfiles(unittest.TestCase):
    def test_channel_and_stop_have_plain_keys(self):
        pygame.init()
        keys = R.Remote().keys
        for name, action in (("]", R.CH_UP), ("[", R.CH_DOWN), ("x", R.STOP)):
            self.assertEqual(keys[pygame.key.key_code(name)], action)

    def test_names_fall_back_from_remote_to_skin_to_action(self):
        self.assertEqual(R.button_name("sony_rm_y195", R.BACK, "CANCEL"), "RESET")
        self.assertEqual(R.button_name("sony_rm_y195", R.GUIDE), "GUIDE")
        self.assertEqual(R.button_name("", R.BACK, "CANCEL"), "CANCEL")
        self.assertEqual(R.button_name("no-such-remote", R.SELECT), "SELECT")


if __name__ == "__main__":
    unittest.main()
