"""Cathode's own channels: where they sit in the lineup, their listings,
tuning to one (no stream, a page), and that each page draws."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import ownchannels as own
from cathode.config import Config
from cathode.epg import EPG, Program
from cathode.playlist import Channel
from cathode.screens.live import LiveTV
from cathode.weather import Weather

pygame.font.init()


def lineup(*nums):
    return [Channel(number=n, name=f"Ch{n}", url=f"u{n}", epg_id=f"dev{n}") for n in nums]


class FakeVideo:
    def __init__(self):
        self.played, self.stopped = [], 0

    def play(self, url, headers=None, start=0):
        self.played.append(url)

    def stop(self):
        self.stopped += 1


class FakeSkin:
    canvas = (1280, 720)
    tune_cover, tune_black = "static", 0.0
    logo = None


class FakeWeather:
    zip = "90210"

    def __init__(self, data):
        self.data = data

    def current(self):
        return self.data


class FakeApp:
    def __init__(self, chans):
        self.config = Config("")
        self.config.own_music = False      # the tests stay quiet
        self.channels = chans
        self.epg = EPG()
        self.video = FakeVideo()
        self.skin = FakeSkin()
        self.start_channel = None
        self.weather = None
        self.timers = []
        self.page_dirty = False

    def after(self, seconds, fn):
        t = [seconds, 0, fn, False]
        self.timers.append(t)
        return t

    @staticmethod
    def cancel(t):
        if t:
            t[3] = True

    def fire(self):
        for t in list(self.timers):
            if not t[3]:
                t[3] = True
                t[2]()

    def invalidate(self):
        pass

    def press_hint(self, a):
        return a


class TestLineup(unittest.TestCase):
    def test_auto_after_the_last_number(self):
        chans = own.add_to(lineup(2, 4, 13), Config(""))
        self.assertEqual([c.number for c in chans], [2, 4, 13, 14, 15])
        self.assertEqual(chans[3].name, "TV Guide")
        self.assertTrue(own.is_own(chans[4]) and own.kind_of(chans[4]) == "weather")

    def test_a_chosen_number_in_numeric_position(self):
        cfg = Config("")
        cfg.own_channels = {"tvguide": 3, "weather": "off"}
        chans = own.add_to(lineup(2, 4, 13), cfg)
        self.assertEqual([c.number for c in chans], [2, 3, 4, 13])

    def test_a_taken_number_moves_to_the_next_free(self):
        cfg = Config("")
        cfg.own_channels = {"tvguide": 4, "weather": "auto"}
        chans = own.add_to(lineup(2, 4, 5), cfg)
        self.assertEqual([(c.number, own.is_own(c)) for c in chans],
                         [(2, False), (4, False), (5, False), (6, True), (7, True)])

    def test_placing_again_does_not_double_them(self):
        cfg = Config("")
        once = own.add_to(lineup(1, 2), cfg)
        self.assertEqual([c.number for c in own.add_to(once, cfg)], [1, 2, 3, 4])

    def test_no_lineup_no_own_channels(self):
        self.assertEqual(own.add_to([], Config("")), [])


class TestGuide(unittest.TestCase):
    def test_listings_cover_now_and_the_guide_resolves_them(self):
        epg = EPG()
        own.fill_guide(epg)
        now = datetime.now(timezone.utc)
        for ch in own.add_to(lineup(1), Config(""))[1:]:
            cid = epg.resolve_channel_id(ch.epg_id, ch.name)
            self.assertEqual(cid, ch.epg_id)
            self.assertIsNotNone(epg.current_program(cid, now))
            self.assertIsNotNone(epg.current_program(cid, now + timedelta(hours=40)))
        self.assertEqual(own.real_ids(epg), [])
        own.fill_guide(epg)         # again: replaced, not doubled
        self.assertEqual(len(epg._programs["cathode.tvguide"]), 96)


class TestMusic(unittest.TestCase):
    def test_each_channel_has_its_tune(self):
        for kind in own.KINDS:
            self.assertTrue(own.music_file(kind), kind)

    def test_music_off_in_the_settings_plays_nothing(self):
        app = FakeApp([])
        own.play_music("tvguide", app)
        self.assertIsNone(own._playing)
        own.stop_music()                    # harmless when nothing plays


class TestTuning(unittest.TestCase):
    def test_an_own_channel_stops_the_stream_and_pages(self):
        app = FakeApp(own.add_to(lineup(1, 2), Config("")))
        own.fill_guide(app.epg)
        live = LiveTV(app)
        live.tune(2)                     # 3: TV Guide
        self.assertEqual(app.video.stopped, 1)
        self.assertEqual(app.video.played, [])
        self.assertIsInstance(live.page, own.TVGuidePage)
        self.assertEqual(live.phase, "cover")
        app.fire()                       # the page's first tick and the reveal
        self.assertTrue(app.page_dirty)
        self.assertEqual(live.phase, "reveal")
        live.on_video("video_ended", reason="eof")     # the stopped stream's last word: ignored
        self.assertFalse(live.dropped)
        live.tune(0)
        self.assertIsNone(live.page)
        self.assertEqual(app.video.played, ["u1"])


DAY = {"date": "2026-10-27", "maxtempF": "70", "mintempF": "50", "maxtempC": "21", "mintempC": "10",
       "astronomy": [{"sunrise": "07:12 AM", "sunset": "06:30 PM", "moon_phase": "Waxing Gibbous",
                      "moon_illumination": "62"}],
       "hourly": [{"time": str(h * 100), "tempF": str(50 + h), "tempC": str(10 + h // 2), "weatherCode": "116",
                   "weatherDesc": [{"value": "Partly cloudy"}], "chanceofrain": str(h)} for h in range(0, 24, 3)]}
J1 = {"current_condition": [{"temp_F": "64", "temp_C": "18", "humidity": "40", "weatherCode": "113",
                             "weatherDesc": [{"value": "Sunny"}], "FeelsLikeF": "63", "FeelsLikeC": "17",
                             "windspeedMiles": "8", "windspeedKmph": "13", "winddir16Point": "NW",
                             "pressureInches": "30", "pressure": "1016", "visibilityMiles": "10",
                             "visibility": "16", "uvIndex": "4"}],
      "nearest_area": [{"areaName": [{"value": "Beverly Hills"}]}],
      "weather": [DAY, dict(DAY, date="2026-10-28"), dict(DAY, date="2026-10-29")]}


class TestPages(unittest.TestCase):
    def setUp(self):
        self.app = FakeApp(own.add_to(lineup(2, 4), Config("")))
        own.fill_guide(self.app.epg)
        now = datetime.now(timezone.utc)
        self.app.epg.set_programs("dev2", [Program("dev2", "The Big Picture", now - timedelta(minutes=10),
                                                    now + timedelta(minutes=50), description="A look at things.")])

    def test_weather_parse(self):
        d = Weather.parse(J1, "F")
        self.assertEqual((d["temp"], d["feels"], d["wind_dir"], d["pressure"]), ("64", "63", "NW", "30 in"))
        self.assertEqual(len(d["days"]), 3)
        self.assertEqual(d["days"][0]["sunrise"], "07:12 AM")
        self.assertEqual(d["days"][0]["hours"][1], {"hour": 3, "temp": "53", "desc": "Partly cloudy",
                                                     "category": "partly", "rain": 3})
        self.assertEqual(Weather.parse(J1, "C")["pressure"], "1016 mb")

    def test_every_page_draws_at_the_skin_shape(self):
        import time
        for canvas in ((1280, 720), (640, 480)):
            FakeSkin.canvas = canvas
            try:
                guide = own.TVGuidePage(self.app)
                self.assertEqual(guide.size, (640, 360) if canvas[0] == 1280 else (640, 480))
                self.assertEqual(guide.frame().get_size(), guide.size)
                self.assertTrue(guide._candidates(datetime.now()))      # Ch2 has a programme to promote
                self.assertEqual(len(guide._rows[1]), len(self.app.channels))   # every row drawn once, then kept
                for wx in (None, FakeWeather(None), FakeWeather(Weather.parse(J1, "F"))):
                    self.app.weather = wx
                    page = own.WeatherPage(self.app)
                    for k in range(4):                  # every held page
                        page.t0 = time.monotonic() - k * page.HOLD
                        self.assertEqual(page.frame().get_size(), page.size)
            finally:
                FakeSkin.canvas = (1280, 720)


if __name__ == "__main__":
    unittest.main()
