"""What real-world data throws at Cathode: a damaged settings file, wrong
setting types, playlists with BOMs, other encodings and stray characters,
names in scripts the skins' fonts don't have, runaway text."""

import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame  # noqa: E402

from cathode import playlist  # noqa: E402
from cathode.config import Config  # noqa: E402


class TestSettingsFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "config.json")

    def test_a_damaged_file_is_kept_aside_not_overwritten(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write('{"playlists": [{"name": "Mine", "playlist_url": "x"}], "volu')
        cfg = Config(self.path)
        self.assertEqual(cfg.playlists, [])
        self.assertEqual(cfg._load_error, "config.json.damaged")
        cfg.save()
        with open(self.path + ".damaged", encoding="utf-8") as f:
            self.assertIn('"Mine"', f.read())       # still there to recover by hand

    def test_a_wrong_value_costs_that_setting_only(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"volume": "loud", "muted": 1, "playlists": "x", "sub_size": 52, "skin": 5,
                       "subtitles": True, "display": 1.0}, f)
        cfg = Config(self.path)
        self.assertEqual((cfg.volume, cfg.muted, cfg.playlists, cfg.skin), (80, False, [], "classic"))
        self.assertEqual((cfg.sub_size, cfg.subtitles, cfg.display), (52, True, 1))
        self.assertIsInstance(cfg.display, int)
        self.assertEqual(cfg._load_error, "")

    def test_a_settings_file_with_a_bom_loads(self):
        with open(self.path, "w", encoding="utf-8-sig") as f:
            json.dump({"volume": 30}, f)
        self.assertEqual(Config(self.path).volume, 30)


class TestPlaylistsFromTheWild(unittest.TestCase):
    def _load(self, raw: bytes):
        path = os.path.join(tempfile.mkdtemp(), "list.m3u")
        with open(path, "wb") as f:
            f.write(raw)
        return playlist.load(path)

    def test_a_bom_does_not_become_a_channel(self):
        chans = self._load(b"\xef\xbb\xbf#EXTM3U\r\n#EXTINF:-1,One\r\nhttp://a\r\n")
        self.assertEqual([c.name for c in chans], ["One"])

    def test_windows_1252_entities_and_control_characters(self):
        chans = self._load(b"#EXTM3U\n#EXTINF:-1,Caf\xe9 &amp; Bar\x07\tTV\nhttp://a\n")
        self.assertEqual(chans[0].name, "Café & Bar TV")

    def test_a_runaway_name_is_cut(self):
        chans = self._load(b"#EXTM3U\n#EXTINF:-1," + b"A" * 5000 + b"\nhttp://a\n")
        self.assertEqual(len(chans[0].name), 120)


class TestPlexFailures(unittest.TestCase):
    def test_each_failure_reads_in_plain_words(self):
        import urllib.error
        from cathode.ondemand import plex_error_text
        from cathode.plex import PlexError
        self.assertEqual(plex_error_text(PlexError("This item is no longer available.")),
                         "This item is no longer available.")
        self.assertIn("expired", plex_error_text(urllib.error.HTTPError("u", 401, "x", {}, None)))
        self.assertIn("(500)", plex_error_text(urllib.error.HTTPError("u", 500, "x", {}, None)))
        self.assertIn("Couldn't reach", plex_error_text(urllib.error.URLError(ConnectionRefusedError())))
        self.assertIn("couldn't read", plex_error_text(KeyError("MediaContainer")))


class TestText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.font.init()
        from cathode.skins import Text
        cls.t = Text()
        cls.f = cls.t.font("VCR_OSD_MONO.ttf", 24)

    def test_scripts_the_font_lacks_fall_back_to_a_face_that_has_them(self):
        runs = self.t.runs(self.f, "CH 1 Первый")       # "Первый"
        if len(runs) == 1:
            self.skipTest("no system face with Cyrillic here")
        self.assertIs(runs[0][0], self.f)
        self.assertIsNot(runs[-1][0], self.f)
        img, _ = self.t.render(self.f, "CH 1 Первый", (255, 255, 255))
        self.assertEqual(img.get_width(), self.t.width(self.f, "CH 1 Первый"))

    def test_right_to_left_titles_read_right_to_left(self):
        s = "الأخبار العاجلة 24"
        runs = self.t.runs(self.f, s)
        if all(f is self.f for f, _ in runs):
            self.skipTest("no system face with Arabic here")
        texts = [t for _, t in runs]
        self.assertEqual(texts[0].strip(), "24")             # the number sits at the line's left end
        self.assertEqual(len(texts), 2)                      # both words, and the space between, one run
        self.assertIn(" ", texts[1].strip())

    def test_plain_text_keeps_its_own_font(self):
        self.assertEqual(self.t.runs(self.f, "Test Card"), [(self.f, "Test Card")])

    def test_a_runaway_title_fits_fast(self):
        s = "word " * 4000
        t0 = time.perf_counter()
        out = self.t.fit(self.f, s, 300)
        self.assertLess(time.perf_counter() - t0, 0.5)
        self.assertLessEqual(self.t.width(self.f, out), 300)
        self.assertTrue(out.endswith("..."))


if __name__ == "__main__":
    unittest.main()
