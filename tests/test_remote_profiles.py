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


class TestPadPrompts(unittest.TestCase):
    def test_family_from_vendor_or_name(self):
        self.assertEqual(R.pad_family("Wireless Controller", "030000004c050000cc09000000006800"), "playstation")
        self.assertEqual(R.pad_family("Nintendo Switch Pro Controller"), "nintendo")
        self.assertEqual(R.pad_family("Steam Deck"), "xbox")

    def test_label_follows_the_pad_and_its_bindings(self):
        r = R.Remote()
        r.pad_family = "playstation"
        self.assertEqual(r.pad_label(R.SELECT), "✕")
        self.assertEqual(r.pad_label(R.MENU), "OPTIONS")      # START before BACK
        self.assertEqual(r.pad_label(R.FAV), "")              # unbound: the hint names the remote's
        r.pad_family = "xbox"
        self.assertEqual(r.pad_label(R.CH_UP), "RB")


class TestAutoSyncURL(unittest.TestCase):
    def test_only_where_the_server_offers_it(self):
        from types import SimpleNamespace
        from cathode.screens.playback import Playback
        pb = Playback.__new__(Playback)
        pb.app = SimpleNamespace(config=SimpleNamespace(sub_auto_sync=True))
        on = {"url": "http://s/library/streams/7", "sync": True}
        self.assertTrue(pb.sub_url(on).endswith("/7?autoAdjustSubtitle=1"))
        self.assertEqual(pb.sub_url({"url": "http://s/library/streams/8", "sync": False}), "http://s/library/streams/8")
        pb.app.config.sub_auto_sync = False
        self.assertEqual(pb.sub_url(on), "http://s/library/streams/7")


if __name__ == "__main__":
    unittest.main()
