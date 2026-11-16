"""Phase 9: settings backed up and put back (sign-ins and this Cathode's id
left out and kept), the weekly backup and how many are kept."""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import backup
from cathode.config import Config


class TestBackup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = Config(os.path.join(self.tmp, "config.json"))
        self.cfg.plex_token, self.cfg.sync_id, self.cfg.skin = "SECRET-PLEX", "me123", "passage"
        self.cfg.media_servers = [{"url": "http://den:8096", "user": "viv", "token": "SECRET-JF", "name": "Den"}]
        self.cfg.library_channels = [{"id": "a", "name": "Laugh Track", "sources": []}]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_and_restore_keep_the_sign_ins_out(self):
        path = backup.save(self.cfg)
        raw = open(path, encoding="utf-8").read()
        for secret in ("SECRET-PLEX", "SECRET-JF", "me123"):
            self.assertNotIn(secret, raw)
        self.assertEqual(json.loads(raw)["settings"]["library_channels"][0]["name"], "Laugh Track")
        other = Config(os.path.join(self.tmp, "other", "config.json"))       # another machine, its own sign-ins
        other.plex_token, other.sync_id = "OTHER-PLEX", "them456"
        other.media_servers = [{"url": "http://den:8096", "user": "viv", "token": "OTHER-JF"}]
        n = backup.restore(other, path)
        self.assertGreater(n, 50)
        self.assertEqual((other.skin, other.library_channels[0]["name"]), ("passage", "Laugh Track"))
        self.assertEqual((other.plex_token, other.sync_id), ("OTHER-PLEX", "them456"))
        self.assertEqual(other.media_servers[0]["token"], "OTHER-JF")        # its sign-in to the same server kept
        self.assertGreater(other.channels_edited, time.time() - 5)           # the other Cathodes take it
        bad = os.path.join(self.tmp, "bad.json")
        with open(bad, "w") as f:
            json.dump({"hello": 1}, f)
        with self.assertRaises(ValueError):
            backup.restore(other, bad)

    def test_weekly_and_eight_kept(self):
        self.assertIsNotNone(backup.weekly(self.cfg))
        self.assertIsNone(backup.weekly(self.cfg))                           # one this week already
        for n in range(10):                                                  # ten older weekly ones
            with open(os.path.join(backup.folder(self.cfg), f"cathode-2026010{n}-000000-auto.json"), "w") as f:
                json.dump({"cathode_backup": 1, "settings": {}}, f)
        backup.save(self.cfg, auto=True)
        autos = [b for b in backup.backups(self.cfg) if b["auto"]]
        self.assertEqual(len(autos), backup.KEEP_AUTO)

    def test_the_menu_rows(self):
        from types import SimpleNamespace
        from cathode import menus
        said = []
        app = SimpleNamespace(config=self.cfg, toast=lambda t, *a: said.append(t))
        menus._back_up(app)
        self.assertTrue(said[-1].startswith("Saved: "))
        rows = menus.restore_items(app)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].value(), "")


if __name__ == "__main__":
    unittest.main()
