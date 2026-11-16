"""Phase 4: a Plex music library as channels (artists as shows, tracks as
their episodes, the radio card), and the Weather channel's almanac when no
forecast can be had."""

import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import libchannels as lc, library, weather
from tests.test_library import index as base_index


def index():
    idx = base_index()
    mu = library.Section("60", "Music", "music", "s1")
    for key, artist, genre in (("801", "The Band", "Rock"), ("802", "Singer", "Pop")):
        mu.add_show({"ratingKey": key, "title": artist, "Genre": [{"tag": genre}], "thumb": f"/a/{key}"})
        for album in ("First", "Second"):
            for n in range(1, 4):
                mu.add_item({"type": "track", "ratingKey": f"{key}{album[0]}{n}", "grandparentRatingKey": key,
                             "grandparentTitle": artist, "title": f"{album} song {n}", "parentTitle": album, "index": n,
                             "duration": 200000, "parentThumb": f"/al/{key}{album}", "parentYear": 1991})
    idx.sections["60"] = mu
    idx._by_id = None
    return idx


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._dir = library._dir
        library._dir = lambda: self.tmp

    def tearDown(self):
        library._dir = self._dir
        lc.SCHEDULES.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestMusic(Temp):
    def test_artists_are_shows_and_tracks_run_album_by_album(self):
        idx = index()
        mu = idx.sections["60"]
        mu.save()
        back = library.Section.load("60")
        self.assertEqual(back.items, mu.items)
        c = lc.new_channel("Rock Radio", [{"section": "60", "kind": "genre", "value": "Rock"}], "playlist")
        g = lc.groups(c, idx)
        self.assertEqual([x["title"] for x in g], ["The Band"])
        self.assertEqual([i["name"] for i in g[0]["items"]][:4], ["First song 1", "First song 2", "First song 3",
                                                                 "Second song 1"])
        everything = lc.new_channel("All", [{"kind": "all"}])
        self.assertFalse(any(i["type"] == "track" for x in lc.groups(everything, idx) for i in x["items"]))
        self.assertEqual(lc.options(idx, "60", "show"), [("802", "Singer", 1), ("801", "The Band", 1)])
        tl = lc.Timeline(c, idx, poster=lambda p: f"http://plex/photo{p}", store=False)
        e = tl.at(datetime.now(timezone.utc))["entry"]
        self.assertEqual((e["category"], e["radio"]["artist"]), ("Music", "The Band"))
        self.assertTrue(e["radio"]["art"].startswith("http://plex/photo/al/"))
        self.assertTrue(e["radio"]["song"].endswith(("song 1", "song 2", "song 3")))
        self.assertFalse(lc.starter(idx) and any(x["name"] == "Music" for x in lc.starter(idx)))   # no premade music

    def test_every_skin_draws_the_radio_card(self):
        import pygame
        from tests.test_skins import FakeApp as SkinApp
        from cathode.skins import skin_classes
        from cathode.playlist import Channel
        pygame.display.init()
        for name, cls in skin_classes().items():
            app = SkinApp()
            skin = cls(app)
            app.skin = skin
            W, H = skin.canvas
            c = pygame.Surface((W, H), pygame.SRCALPHA)
            skin.draw_radio(c, {"artist": "The Band", "song": "First song 1", "album": "First", "art": ""},
                            Channel(number=101, name="Rock Radio", url="u"))
            self.assertNotEqual(tuple(c.get_at((W // 2, 2)))[:3], (0, 0, 0), name)


class TestAlmanac(unittest.TestCase):
    def test_the_almanac_stands_in_for_a_forecast(self):
        w = weather.Weather("02134", "F", "US")
        w._place_path = lambda: os.path.join(tempfile.gettempdir(), "cathode-test-place.json")
        try:
            os.remove(w._place_path())
        except OSError:
            pass
        w._keep_place({"nearest_area": [{"latitude": "42.35", "longitude": "-71.13",
                                         "areaName": [{"value": "Allston"}]}]})
        a = w.almanac(date(2026, 7, 20))
        self.assertTrue(a["almanac"])
        self.assertEqual((a["city"], a["units"], len(a["days"])), ("Allston", "F", 3))
        summer = int(a["days"][0]["hi"])
        winter = int(w.almanac(date(2026, 1, 20))["days"][0]["hi"])
        self.assertTrue(70 <= summer <= 95 and winter < summer - 20, (summer, winter))
        self.assertRegex(a["days"][0]["sunrise"], r"^0[3-7]:\d\d AM$")
        self.assertRegex(a["days"][0]["sunset"], r"^0[6-9]:\d\d PM$")
        self.assertEqual(len(a["days"][0]["hours"]), 8)
        self.assertEqual(weather._moon(date(2026, 11, 24))[0], "Full Moon")
        self.assertEqual(weather._moon(date(2026, 11, 9))[0], "New Moon")
        w.zip = "90210"                                             # another place: not this one's sun
        self.assertEqual(w.almanac(date(2026, 7, 20))["city"], "90210")
        os.remove(w._place_path())

    def test_a_failed_fetch_with_nothing_in_hand_gives_the_almanac(self):
        w = weather.Weather("02134", "C", "US")
        w._fetch = lambda: (_ for _ in ()).throw(OSError("offline"))
        w._refresh()
        self.assertTrue(w._data["almanac"])
        w._fetch = lambda: {"temp": "12", "units": "C"}
        w._refresh()
        self.assertNotIn("almanac", w._data)                        # a real forecast takes over


if __name__ == "__main__":
    unittest.main()
