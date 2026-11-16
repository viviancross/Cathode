"""Phase 8: profiles (each its own look and favourites), kids' profiles and
the channels they see, the parent PIN, the watch history."""

import os
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import libchannels as lc, lineup, profiles, videochannels as vc
from cathode.config import Config
from cathode.playlist import Channel


def app_with(cfg):
    app = SimpleNamespace(config=cfg, skins=[], relined=0)
    app.set_skin = lambda name: app.skins.append(name)
    app.relineup = lambda: setattr(app, "relined", app.relined + 1)
    return app


class TestProfiles(unittest.TestCase):
    def test_each_profile_its_look_and_favourites(self):
        cfg = Config("")
        cfg.skin, cfg.favorites = "passage", [5, 7]
        app = app_with(cfg)
        kid = profiles.new(cfg, "Sam", kids=True)
        self.assertEqual((kid["fields"]["skin"], kid["fields"]["favorites"]), ("passage", []))
        profiles.switch(app, kid["id"])
        self.assertEqual((cfg.profile, cfg.favorites, profiles.is_kids(cfg)), (kid["id"], [], True))
        cfg.skin, cfg.favorites = "classic", [2]                     # Sam's choices
        profiles.switch(app, "")
        self.assertEqual((cfg.skin, cfg.favorites, cfg.profile), ("passage", [5, 7], ""))
        self.assertEqual(kid["fields"]["skin"], "classic")
        profiles.switch(app, kid["id"])
        self.assertEqual((cfg.skin, cfg.favorites), ("classic", [2]))
        self.assertEqual(app.skins, ["passage", "passage", "classic"])      # Sam began with the look then on
        self.assertEqual(app.relined, 3)

    def test_a_kids_profile_sees_kids_channels(self):
        cfg = Config("")
        cfg.video_channels = []
        cfg.library_channels = [lc.new_channel("Saturday Morning", [{"kind": "all"}], content="kids"),
                                lc.new_channel("After Dark", [{"kind": "all"}], content="family")]
        chans = vc.add_to([Channel(number=n, name=f"Ch{n}", url=f"u{n}") for n in (2, 4)], cfg)
        cfg.channel_edits = {"u4": {"kids": True}}
        self.assertEqual(len(lineup.apply(chans, cfg)), 4)          # the main profile: everything
        kid = profiles.new(cfg, "Sam", kids=True)
        cfg.profile = kid["id"]
        self.assertEqual([c.name for c in lineup.apply(chans, cfg)], ["Ch4", "Saturday Morning"])


class TestPin(unittest.TestCase):
    def test_settings_ask_a_kids_profile_for_the_pin(self):
        from cathode import menus
        cfg = Config("")
        pushed, went, said = [], [], []
        app = SimpleNamespace(config=cfg, push=pushed.append, toast=lambda t, *a: said.append(t))
        menus._pin_then(app, lambda: went.append(1))
        self.assertEqual(went, [1])                                   # the main profile: straight in
        kid = profiles.new(cfg, "Sam", kids=True)
        cfg.profile = kid["id"]
        menus._pin_then(app, lambda: went.append(2))
        self.assertEqual(went, [1, 2])                                # no PIN set: in
        cfg.parent_pin = "4321"
        menus._pin_then(app, lambda: went.append(3))
        pushed[-1].on_done("1111")
        self.assertEqual((went, said[-1]), ([1, 2], "That's not the parent PIN."))
        menus._pin_then(app, lambda: went.append(4))
        pushed[-1].on_done("4321")
        self.assertEqual(went, [1, 2, 4])


class TestHistory(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "history.json")
        self._path = profiles._path
        profiles._path = lambda: self.path

    def tearDown(self):
        profiles._path = self._path

    def test_a_minute_or_more_is_history(self):
        ch = Channel(number=101, name="Laugh Track", url="u")
        profiles.note(ch, time.time() - 30, "Too short", "Main")
        self.assertEqual(profiles.history(), [])
        profiles.note(ch, time.time() - 1800, "Alpha", "Main")
        profiles.note(Channel(number=4, name="Ch4", url="v"), time.time() - 7200, "News", "Sam")
        rows = profiles.history()
        self.assertEqual([(r["ch"], r["title"], r["who"]) for r in rows], [("Laugh Track", "Alpha", "Main"),
                                                                          ("Ch4", "News", "Sam")])
        self.assertEqual([(k, round(h, 1)) for k, h in profiles.most_watched(rows)], [("4  Ch4", 2.0),
                                                                                    ("101  Laugh Track", 0.5)])
        profiles.clear()
        self.assertEqual(profiles.history(), [])

    def test_leaving_a_channel_notes_it(self):
        from cathode.screens.live import LiveTV
        from tests.test_live import FakeApp
        app = FakeApp()
        live = LiveTV(app)
        live.channels_loaded()
        live._watch_since = time.time() - 300
        live.tune(2)
        rows = profiles.history()
        self.assertEqual((rows[-1]["num"], rows[-1]["s"] >= 299), (app.channels[0].number, True))


class TestMenus(unittest.TestCase):
    def test_pages(self):
        from cathode import menus
        cfg = Config("")
        app = app_with(cfg)
        app.push = lambda s: None
        app.top = lambda: SimpleNamespace(refresh=lambda *a: None, back=lambda: None, close=lambda: None)
        app.toast = lambda *a, **k: None
        profiles.new(cfg, "Sam", kids=True)
        rows = menus.profile_items(app)
        self.assertEqual([it.label for it in rows], ["Who's watching", "Sam", "Add a profile...", "Parent PIN",
                                                     "Watch history"])
        who = menus.who_items(app)
        who[1].action()
        self.assertEqual(profiles.active(cfg)["name"], "Sam")
        page = {it.label: it for it in menus.profile_page(app, cfg.profiles[0])}
        page["Kids' profile"].adjust(1)
        self.assertFalse(cfg.profiles[0]["kids"])
        for it in rows + who + list(page.values()):
            if it.value:
                self.assertIsInstance(it.value(), str)


if __name__ == "__main__":
    unittest.main()
