"""Phase 2's rules on the timeline: on-air hours and the sign-off, time
slots and seasons, leaving sources out, word and rating filters, Mix
across library sources; the Player at a sign-off; the colour bars on every
skin; the maker's new rows."""

import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import libchannels as lc, library, videochannels as vc, ytdl
from cathode.screens.live import LiveTV
from tests.test_library import index
from tests.test_own import FakeApp, lineup


def chan(order="block_shuffle", *sources, **kw):
    return lc.new_channel("Chan", sources or [{"section": "51", "kind": "all"}], order, **kw)


def slots(tl, days=7):
    tl.at(datetime.now(timezone.utc) + timedelta(days=days))
    return [s for d in tl.days for s in d["slots"]]


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._dir = library._dir
        library._dir = lambda: self.tmp

    def tearDown(self):
        library._dir = self._dir
        lc.SCHEDULES.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestClock(unittest.TestCase):
    def test_on_the_air(self):
        at = lambda h, m=0: datetime(2026, 11, 14, h, m).timestamp()     # a Saturday
        c = {"hours": [6, 2]}
        self.assertTrue(lc.on_air(c, at(6)))
        self.assertTrue(lc.on_air(c, at(23, 59)))
        self.assertTrue(lc.on_air(c, at(1, 59)))
        self.assertFalse(lc.on_air(c, at(2)))
        self.assertFalse(lc.on_air(c, at(5, 59)))
        self.assertEqual(datetime.fromtimestamp(lc.next_on(c, at(3))), datetime(2026, 11, 14, 6))
        day = {"hours": [7, 23]}
        self.assertFalse(lc.on_air(day, at(23, 30)))
        self.assertEqual(datetime.fromtimestamp(lc.next_on(day, at(23, 30))), datetime(2026, 11, 15, 7))
        self.assertTrue(lc.on_air({}, at(3)) and lc.on_air({"hours": None}, at(3)))

    def test_slots_and_seasons(self):
        sat_morning = {"airs": {"days": [5], "from": 7, "to": 12}}
        self.assertTrue(lc.active(sat_morning, datetime(2026, 11, 14, 9)))       # Saturday
        self.assertFalse(lc.active(sat_morning, datetime(2026, 11, 13, 9)))      # Friday
        self.assertFalse(lc.active(sat_morning, datetime(2026, 11, 14, 12)))
        nights = {"airs": {"days": [4, 5], "from": 20, "to": 2}}
        self.assertTrue(lc.active(nights, datetime(2026, 11, 14, 1)))            # 1 AM Saturday: Friday night's
        self.assertTrue(lc.active(nights, datetime(2026, 11, 15, 1)))            # 1 AM Sunday: Saturday night's
        self.assertFalse(lc.active(nights, datetime(2026, 11, 16, 1)))           # 1 AM Monday: Sunday's: no
        self.assertFalse(lc.active(nights, datetime(2026, 11, 14, 3)))
        xmas = {"season": [12]}
        self.assertTrue(lc.active(xmas, datetime(2026, 12, 3, 9)))
        self.assertFalse(lc.active(xmas, datetime(2026, 11, 3, 9)))
        self.assertTrue(lc.active({}, datetime(2026, 11, 3, 9)))


class TestHours(Temp):
    def test_off_the_air_between_sign_off_and_sign_on(self):
        c = chan("cyclic_shuffle", hours=[6, 2])
        tl = lc.Timeline(c, index(), store=False)
        got = slots(tl)
        offs = [s for s in got if s[1] == lc.OFF]
        self.assertGreaterEqual(len(offs), 6)
        for start, item, dur in got:
            if item == lc.OFF:
                back = datetime.fromtimestamp(start + dur)
                self.assertEqual((back.hour, back.minute, back.second), (6, 0, 0))     # signs on at six sharp
                self.assertFalse(lc.on_air(c, start + dur / 2))
            else:
                self.assertTrue(lc.on_air(c, start), datetime.fromtimestamp(start))   # nothing starts off the air
        self.assertTrue(all(abs(a[0] + a[2] - b[0]) < 0.01 for a, b in zip(got, got[1:])))   # end to end
        off = next(s for s in offs if s[0] > time.time())
        cur = tl.at(datetime.fromtimestamp(off[0] + 60, timezone.utc))
        self.assertEqual((cur["entry"]["kind"], cur["entry"]["title"]), ("signoff", "Off the air"))

    def test_the_guide_says_when_it_is_back(self):
        app = FakeApp([])
        app.config.video_channels = []
        app.config.library_channels = [chan("cyclic_shuffle", hours=[6, 2])]
        app.library, app.listings, app.schedules = index(), {}, {}
        app.channels = vc.add_to(lineup(1), app.config)
        lc.rebuild(app)
        ch = app.channels[-1]
        progs = vc.programmes([ch], {lc.PREFIX + app.config.library_channels[0]["id"]:
                                     lc.SCHEDULES[lc.PREFIX + app.config.library_channels[0]["id"]]}, hours=48)[ch.epg_id]
        off = [p for p in progs if p.title == "Off the air"]
        self.assertTrue(off)
        self.assertIn("Back at 6:00 AM.", off[0].description)

    def test_a_skip_before_sign_off_leaves_sign_on_where_it_was(self):
        c = chan("cyclic_shuffle", hours=[6, 2])
        tl = lc.Timeline(c, index(), store=False)
        got = slots(tl, 2)
        off = next(s for s in got if s[1] == lc.OFF and s[0] > time.time() + 3600)
        before = [s for s in got if s[1] != lc.OFF and s[0] < off[0] and s[0] > time.time()]
        off_at, on_at = off[0], off[0] + off[2]                 # (the slots change in place)
        tl.drop(before[-1][1], datetime.now(timezone.utc))
        after = next(s for d in tl.days for s in d["slots"] if s[1] == lc.OFF and abs(s[0] + s[2] - on_at) < 0.01)
        self.assertLess(after[0], off_at)                       # signs off sooner
        self.assertAlmostEqual(after[0] + after[2], on_at, places=3)    # back at six all the same


class TestSlots(Temp):
    def test_a_slots_sources_take_over_in_their_time(self):
        c = chan("block_shuffle", {"section": "51", "kind": "show", "value": "300"},          # Charlie, any time
                 {"section": "51", "kind": "show", "value": "100", "airs": {"from": 7, "to": 12}})   # Alpha, mornings
        tl = lc.Timeline(c, index(), store=False)
        got = slots(tl, 3)
        mornings = others = 0
        for start, item, _d in got:
            lt = datetime.fromtimestamp(start)
            show = item[1:4]
            if 7 <= lt.hour < 12:
                self.assertEqual(show, "100", lt)
                mornings += 1
            else:
                self.assertEqual(show, "300", lt)
                others += 1
        self.assertTrue(mornings and others)
        self.assertIn("slots", tl.state)                        # the morning's rotation kept apart

    def test_a_season_joins_only_in_its_months(self):
        month = datetime.now().month
        later = month % 12 + 1
        for season, there in (([month], True), ([later], False)):
            c = chan("cyclic_shuffle", {"section": "51", "kind": "show", "value": "300"},
                     {"section": "51", "kind": "show", "value": "100", "season": season})
            got = {s[1][1:4] for s in slots(lc.Timeline(c, index(), store=False), 1) if s[1] != lc.OFF}
            self.assertEqual("100" in got, there, season)

    def test_nothing_in_season_is_off_the_air(self):
        later = datetime.now().month % 12 + 1
        c = chan("cyclic_shuffle", {"section": "51", "kind": "show", "value": "100", "season": [later]})
        tl = lc.Timeline(c, index(), store=False)
        cur = tl.at(datetime.now(timezone.utc))
        self.assertEqual(cur["entry"]["kind"], "signoff")


class TestFilters(Temp):
    def test_leave_out_words_ratings(self):
        idx = index()

        def shows(**kw):
            c = chan("cyclic_shuffle", *kw.pop("sources", [{"section": "51", "kind": "all"}]), **kw)
            return sorted(g["title"] for g in lc.groups(c, idx))
        self.assertEqual(shows(), ["Alpha", "Bravo", "Charlie"])
        self.assertEqual(shows(sources=[{"section": "51", "kind": "all"},
                                        {"section": "51", "kind": "show", "value": "200", "exclude": True}]),
                         ["Alpha", "Charlie"])
        self.assertEqual(shows(words_out=["charlie"]), ["Alpha", "Bravo"])
        self.assertEqual(shows(words_in=["alpha 1x"]), ["Alpha"])                  # (episode names)
        self.assertEqual(shows(content="kids"), ["Alpha"])
        self.assertEqual(shows(content="family"), ["Alpha", "Bravo"])

    def test_mix_shares_library_sources(self):
        c = chan("mix", {"section": "51", "kind": "show", "value": "100", "weight": 1},
                 {"section": "51", "kind": "show", "value": "200", "weight": 3}, weighting="manual")
        got = slots(lc.Timeline(c, index(), store=False), 1)
        b = sum(d for _s, i, d in got if i.startswith("p200"))
        self.assertAlmostEqual(b / sum(d for _s, _i, d in got), 0.75, delta=0.05)
        c["sources"][0]["shuffle"] = False                      # in its order, carrying on
        got = [i for _s, i, _d in slots(lc.Timeline(c, index(), store=False), 1) if i.startswith("p100")]
        self.assertEqual(got[:4], ["p100101", "p100102", "p100103", "p100104"])


class FakeVideo:
    def __init__(self):
        self.played, self.stopped = [], 0

    def play(self, url, headers=None, start=0, sub_delay=0.0, audio=None):
        self.played.append((url, round(start)))

    def stop(self):
        self.stopped += 1


class TestPlayer(Temp):
    def test_the_bars_while_off_the_air_then_the_next_programme(self):
        app = FakeApp([])
        app.video = FakeVideo()
        app.config.library_channels = []
        app.config.video_channels = [vc.new_channel("Hits", ["PLa"])]
        cid = app.config.video_channels[0]["id"]
        app.channels = vc.add_to(lineup(1), app.config)
        lst = {"PLa": {"title": "Hits", "fetched": 1, "entries": [
            {"id": f"S{n}", "title": f"Artist {n} - Song {n}", "duration": 200} for n in range(5)]}}
        tl = lc.Timeline(app.config.video_channels[0], made=(lc.yt_groups(app.config.video_channels[0], lst), ""),
                         cid=cid, store=False)
        now = time.time()
        tl.days = [{"day": "x", "start": now - 600, "state": {},
                    "slots": [[now - 600, "S0", 200], [now - 400, lc.OFF, 700], [now + 300, "S1", 200]]}]
        tl.state = {"t": now + 500 + 86400 * 3}
        tl._index()
        app.schedules = {cid: tl}
        calls = []
        app.post = lambda fn, *a, **k: calls.append((fn, a, k))
        old = ytdl.stream
        ytdl.stream = lambda vid: {"video": f"V/{vid}", "headers": {}}
        try:
            live = LiveTV(app)
            live.tune(1)
            self.assertEqual(live.signoff["name"], "Hits")
            self.assertGreater(app.video.stopped, 0)
            self.assertEqual(app.video.played, [])
            due = [t for t in app.timers if not t[3] and abs(t[0] - 300) < 3]
            self.assertTrue(due, "the next programme at sign-on")
            live.on_video("video_ended", reason="stop")         # the stopped picture: nothing else happens
            self.assertEqual(calls, [])
            due[-1][2]()                                        # sign-on
            for _ in range(100):
                if calls:
                    break
                time.sleep(0.02)
            fn, a, k = calls.pop(0)
            fn(*a, **k)
            self.assertIsNone(live.signoff)
            self.assertEqual(app.video.played[-1][0], "V/S1")
        finally:
            ytdl.stream = old


class TestBars(unittest.TestCase):
    def test_every_skin_draws_the_colour_bars(self):
        import pygame
        from tests.test_skins import FakeApp as SkinApp
        from cathode.skins import skin_classes
        pygame.display.init()
        for name, cls in skin_classes().items():
            app = SkinApp()
            skin = cls(app)
            app.skin = skin
            W, H = skin.canvas
            c = pygame.Surface((W, H), pygame.SRCALPHA)
            skin.draw_signoff(c, {"name": "Laugh Track", "back": datetime.now(timezone.utc) + timedelta(hours=3)})
            self.assertEqual(tuple(c.get_at((2, 2)))[:3], (192, 192, 192), name)      # the first bar
            self.assertEqual(tuple(c.get_at((W - 2, 2)))[:3], (0, 0, 192), name)     # the last
            self.assertEqual(tuple(c.get_at((W // 2, int(H * 0.36))))[:3] != (0, 192, 0), True)   # the card over them


class TestMaker(Temp):
    def test_the_new_rows_build_read_and_change(self):
        from types import SimpleNamespace
        from cathode import menus
        app = FakeApp([])
        app.ondemand = SimpleNamespace(signed_in=True)
        app.library = index()
        app.listings, app.schedules, app.live = {}, {}, None
        app.config.video_channels = [vc.new_channel("Hits", ["PLa"])]
        app.config.library_channels = [chan("block_shuffle", {"section": "51", "kind": "all"})]
        app.channels = vc.add_to(lineup(1), app.config)
        app.top = lambda: SimpleNamespace(back=lambda: None, open=lambda *a: None, refresh=lambda *a: None)
        app.push = lambda s: None
        app.place_own_channels = lambda: None
        app.toast = lambda *a, **k: None
        lc.rebuild(app)
        lid = app.config.library_channels[0]["id"]
        vid = app.config.video_channels[0]["id"]
        lib_page = menus.library_channel_page(app, lid)
        vid_page = menus.video_channel_page(app, vid)
        pages = [lib_page, vid_page, menus.library_source_page(app, lid, 0), menus.video_source_page(app, vid, 0),
                 menus.coming_up_items(app, lc.PREFIX + lid), menus.skipped_items(app, lc.PREFIX + lid),
                 menus.channel_items(app)]
        for items in pages:
            for it in items:
                self.assertTrue(it.label)
                if it.value:
                    self.assertIsInstance(it.value(), str, it.label)
        rows = {it.label: it for it in lib_page}
        self.assertEqual(rows["Sort method"].value(), "Block Shuffle")
        self.assertEqual(rows["Block length"].value(), "2 episodes")
        self.assertEqual(rows["Weighting"].value(), "-")
        rows["On the air"].adjust(1)
        self.assertEqual(app.config.library_channels[0]["hours"], [6, 2])
        self.assertEqual(rows["On the air"].value(), "6 AM to 2 AM")
        rows["Ratings"].adjust(1)
        self.assertEqual(app.config.library_channels[0]["content"], "family")
        self.assertEqual(len(pages[4]), 30)                         # coming up: thirty programmes
        src = {it.label: it for it in pages[2]}
        src["Airs"].adjust(1)
        src["Season"].adjust(3)
        src["Leave these out"].adjust(1)
        s = app.config.library_channels[0]["sources"][0]
        self.assertEqual((s["airs"], s["season"], s["exclude"]), ({"from": 6, "to": 12}, [12], True))
        self.assertEqual(src["Airs"].value(), "Mornings")
        vrows = {it.label: it for it in vid_page}
        self.assertEqual((vrows["Sort method"].value(), vrows["Weighting"].value()), ("Mix", "Auto"))
        vsrc = {it.label: it for it in pages[3]}
        self.assertEqual((vsrc["Plays as"].value(), vsrc["Newest only"].value()), ("Separate videos", "All"))
        vsrc["Newest only"].adjust(2)
        self.assertEqual(app.config.video_channels[0]["sources"][0]["limit"], 50)
        # a skipped title, and putting it back
        s.update(airs=None, season=None, exclude=False)
        lc.rebuild(app)
        tl = lc.SCHEDULES[lc.PREFIX + lid]
        first = tl.at(datetime.now(timezone.utc))["entry"]["id"]
        tl.drop(first)
        skipped = menus.skipped_items(app, lc.PREFIX + lid)
        self.assertEqual(skipped[0].label, tl.title_of(first))
        skipped[0].action()
        self.assertNotIn(first, tl.dropped)
        # a copy, after the original
        rows["Make a copy"].action()
        self.assertEqual([c["name"] for c in app.config.library_channels], ["Chan", "Chan (copy)"])
        self.assertNotEqual(app.config.library_channels[1]["id"], lid)
        guide = next(it for it in pages[6] if it.label == "Guide listings")
        self.assertEqual(guide.value(), "2 days")
        guide.adjust(1)
        self.assertEqual(app.config.guide_days, 7)


class TestPremieresAndGroups(Temp):
    def test_the_newest_arrival_premieres_at_eight_and_new_titles_say_so(self):
        idx = index()
        fresh = idx.item("p300103")
        fresh["added"] = time.time() - 3600                     # added an hour ago
        c = chan("cyclic_shuffle", premieres="prime")
        tl = lc.Timeline(c, idx, store=False)
        got = slots(tl, 3)
        prem = [s for s in got if len(s) > 3 and s[3].get("premiere")]
        self.assertEqual([s[1] for s in prem], ["p300103"])      # once, not every night
        lt = datetime.fromtimestamp(prem[0][0])
        self.assertGreaterEqual(lt.hour, lc.PREMIERE_HOUR)
        before = [s for s in got if s[0] < prem[0][0]]
        self.assertLess(datetime.fromtimestamp(before[-1][0]).hour * 60 + datetime.fromtimestamp(before[-1][0]).minute,
                        lc.PREMIERE_HOUR * 60 + 1)              # the first programme from eight
        e = tl.at(datetime.fromtimestamp(prem[0][0] + 5, timezone.utc))["entry"]
        self.assertTrue(e["desc"].startswith("Premiere! "))
        self.assertTrue(e["episode_text"].endswith("New"))
        self.assertTrue(lc.is_doc(tl.doc()))                    # four-part slots travel to other Cathodes
        quiet = lc.Timeline(chan("cyclic_shuffle"), idx, store=False)
        self.assertFalse(any(len(s) > 3 for s in slots(quiet, 2)))

    def test_a_content_group_is_its_sources_wherever_it_is_named(self):
        from types import SimpleNamespace
        cfg = SimpleNamespace(content_groups=[{"id": "g1", "name": "Nick", "sources": [
            {"section": "51", "kind": "show", "value": "100"}, {"section": "51", "kind": "show", "value": "200"}]}])
        c = chan("block_shuffle", {"kind": "group", "value": "g1", "label": "Nick", "airs": {"from": 7, "to": 12}},
                 {"section": "51", "kind": "show", "value": "300"})
        e = lc.expand(c, cfg)
        self.assertEqual([s.get("value") for s in e["sources"]], ["100", "200", "300"])
        self.assertEqual(e["sources"][0]["airs"], {"from": 7, "to": 12})          # the naming source's slot
        self.assertEqual(sorted(g["title"] for g in lc.groups(e, index())), ["Alpha", "Bravo", "Charlie"])
        self.assertEqual(lc.source_label(index(), c["sources"][0]), "Group: Nick")
        cfg.content_groups[0]["sources"].pop()
        self.assertNotEqual(lc.signature(lc.expand(c, cfg)), lc.signature(e))     # the group changed: redrawn

    def test_a_one_show_slot_is_a_marathon(self):
        c = chan("block_shuffle", {"section": "51", "kind": "all"},
                 {"section": "51", "kind": "show", "value": "200", "airs": {"days": [5], "from": 12, "to": 18}})
        tl = lc.Timeline(c, index(), store=False)
        got = slots(tl, 7)
        sat = [s for s in got if datetime.fromtimestamp(s[0]).weekday() == 5 and 12 <= datetime.fromtimestamp(s[0]).hour < 18]
        self.assertTrue(sat)
        self.assertTrue(all(s[1].startswith("p200") for s in sat))
        bravo = [s[1] for s in sat]
        self.assertEqual(bravo[:5], sorted(bravo[:5]) if bravo[0] == "p200101" else bravo[:5])     # in order


if __name__ == "__main__":
    unittest.main()
