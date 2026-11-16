"""Phase 3: breaks. Commercials and bumpers from break libraries between
programmes, lined up with the clock; halfway breaks in long programmes;
the slate for what no clip fits; a dud clip and a skipped programme keep
the clock; the Player and the guide through a break; the defaults."""

import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import libchannels as lc, library, videochannels as vc
from tests.test_library import index as base_index
from tests.test_own import FakeApp, lineup


def index():
    idx = base_index()
    ads = library.Section("3", "Classic Commercials", "clip", "s1")
    for n in range(40):
        ads.add_item({"type": "movie", "ratingKey": f"7{n:02d}", "title": f"Ad {n}", "duration": (15 + 15 * (n % 4)) * 1000})
    idx.sections["3"] = ads
    idx._by_id = None
    return idx


def chan(order="cyclic_shuffle", *sources, **kw):
    return lc.new_channel("Chan", sources or [{"section": "51", "kind": "all"}], order, **kw)


BREAKS = {"ads": [{"section": "3", "kind": "all"}], "bumps": [{"section": "10", "kind": "all"}],
          "pad": 30, "mid": "halfway", "length": 120}


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._dir = library._dir
        library._dir = lambda: self.tmp

    def tearDown(self):
        library._dir = self._dir
        lc.SCHEDULES.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def day(self, c, idx=None):
        tl = lc.Timeline(c, idx or index(), store=False)
        tl.at(datetime.now(timezone.utc) + timedelta(days=1))
        return tl, [s for d in tl.days for s in d["slots"]]


def is_prog(s):
    """A programme's start (not a break's piece, nor a second half)."""
    return len(s) == 3 or not (s[3].get("brk") or s[3].get("part"))


class TestBreaks(Temp):
    def test_programmes_start_on_the_half_hour_with_a_break_between(self):
        tl, got = self.day(chan(breaks=BREAKS))
        progs = [s for s in got if is_prog(s)]
        self.assertGreater(len(progs), 30)
        for s in progs[1:]:
            lt = datetime.fromtimestamp(s[0])
            self.assertIn((lt.minute, lt.second), ((0, 0), (30, 0)), lt)          # 22-minute episodes, on the grid
        self.assertTrue(all(abs(a[0] + a[2] - b[0]) < 0.01 for a, b in zip(got, got[1:])))     # end to end
        k = got.index(progs[1]) - 1
        brk = []
        while k >= 0 and len(got[k]) > 3 and got[k][3].get("brk"):
            brk.insert(0, got[k])
            k -= 1
        kinds = [s[3]["brk"] for s in brk]
        self.assertEqual((kinds[0], kinds[-1]), ("bump", "bump"))                 # a bumper in, a bumper out
        self.assertIn("ad", kinds)
        self.assertLessEqual(kinds.count("brb"), 1)
        e = tl.at(datetime.fromtimestamp(brk[1][0] + 1, timezone.utc))["entry"]
        self.assertIn(e["kind"], ("ad", "brb"))

    def test_halfway_and_every_twenty_minutes(self):
        tl, got = self.day(chan("cyclic_shuffle", {"section": "38", "kind": "all"}, breaks=BREAKS))
        heist = [s for s in got if s[1] == "p901"]                                # a 100-minute film
        self.assertEqual([round(s[2]) for s in heist[:2]], [3000, 3000])
        self.assertEqual(heist[1][3], {"in": 3000.0, "part": 1})
        e = tl.at(datetime.fromtimestamp(heist[1][0] + 10, timezone.utc))["entry"]
        self.assertEqual((e["in"], e["part"], e["kind"]), (3000.0, 1, "show"))
        tl, got = self.day(chan("cyclic_shuffle", {"section": "38", "kind": "all"}, breaks=dict(BREAKS, mid="every20")))
        self.assertEqual([round(s[2]) for s in got if s[1] == "p901"][:5], [1200, 1200, 1200, 1200, 1200])
        tl, got = self.day(chan(breaks=dict(BREAKS, pad=0, mid="off")))
        progs = [s for s in got if is_prog(s)]
        gaps = [b[0] - (a[0] + a[2]) for a, b in zip(progs, progs[1:])]
        self.assertTrue(all(abs(g - 120) < 0.01 for g in gaps[:10]), gaps[:10])   # two-minute breaks, no clock

    def test_a_dud_commercial_is_the_slate_and_a_skipped_programme_keeps_the_clock(self):
        tl, got = self.day(chan(breaks=BREAKS))
        now = time.time()
        ad = next(s for s in got if len(s) > 3 and s[3].get("brk") == "ad" and s[0] > now + 600)
        at, dur = ad[0], ad[2]
        tl.drop(ad[1], datetime.now(timezone.utc))
        slots = [s for d in tl.days for s in d["slots"]]
        here = next(s for s in slots if abs(s[0] - at) < 0.01)
        self.assertEqual((here[1], round(here[2], 2)), (lc.BRB, round(dur, 2)))   # the slate in its place
        self.assertEqual(tl.at(datetime.fromtimestamp(at + 1, timezone.utc))["entry"]["kind"], "brb")
        prog = next(s for s in slots if is_prog(s) and s[0] > now + 600)
        tl.drop(prog[1], datetime.now(timezone.utc))
        slots = [s for d in tl.days for s in d["slots"]]
        for s in [s for s in slots if is_prog(s) and s[0] > now + 3600][:10]:
            lt = datetime.fromtimestamp(s[0])
            self.assertIn((lt.minute, lt.second), ((0, 0), (30, 0)))              # still on the grid
        self.assertTrue(all(abs(a[0] + a[2] - b[0]) < 0.01 for a, b in zip(slots, slots[1:])))

    def test_a_guide_opening_in_a_break_starts_with_the_programme(self):
        tl, got = self.day(chan(breaks=BREAKS))
        ch = vc.add_to(lineup(1), type("C", (), {"video_channels": [], "library_channels": [
            dict(chan(breaks=BREAKS), id=tl.c["id"])]})())[-1]
        brk = next(s for s in got if len(s) > 3 and s[3].get("brk") == "bump" and s[0] > time.time() + 3600)
        at = datetime.fromtimestamp(brk[0] + 2, timezone.utc)
        progs = vc.programmes([ch], {vc.cid_of(ch): tl}, now=at + timedelta(hours=1), hours=2)[ch.epg_id]
        self.assertTrue(progs[0].title in ("Alpha", "Bravo", "Charlie"), progs[0].title)
        self.assertLessEqual(progs[0].start, at)

    def test_the_guide_runs_a_programme_over_its_breaks(self):
        app = FakeApp([])
        app.config.video_channels = []
        app.config.library_channels = [chan("cyclic_shuffle", {"section": "38", "kind": "all"}, breaks=BREAKS)]
        app.library, app.listings, app.schedules = index(), {}, {}
        app.channels = vc.add_to(lineup(1), app.config)
        lc.rebuild(app)
        ch = app.channels[-1]
        progs = app.video_programmes[ch.epg_id]
        titles = {p.title for p in progs}
        self.assertTrue(titles <= {"Heist", "Laughs", "Space"}, titles)        # no commercials, no slates listed
        self.assertTrue(all(a.stop == b.start for a, b in zip(progs, progs[1:])))
        for a, b in zip(progs, progs[1:]):
            self.assertNotEqual((a.title, a.stop), (b.title, b.start))         # a film's second half isn't listed again
        heist = [p for p in progs if p.title == "Heist"]
        self.assertTrue(heist and (heist[0].stop - heist[0].start).total_seconds() > 6000)   # its halves and breaks

    def test_defaults_find_the_libraries(self):
        idx = index()
        c = chan("block_shuffle", {"kind": "studio", "value": "Cartoon Network"})
        b = lc.default_breaks(c, idx)
        self.assertEqual(b["ads"], [{"section": "3", "kind": "all"}])
        self.assertEqual(b["bumps"], [{"section": "10", "kind": "all"}])          # CN Bumps
        self.assertEqual(lc.default_breaks(chan(), idx)["bumps"], [])             # a genre channel: no studio's
        self.assertEqual(lc._brands({"sources": [{"kind": "studio", "value": "Nickelodeon"}]}), ["nick"])
        self.assertEqual(lc.clips([{"section": "3", "kind": "all"}], idx)[0]["duration"], 15)


class Video:
    def __init__(self):
        self.played, self.stopped = [], 0

    def play(self, url, headers=None, start=0, sub_delay=0.0, audio=None):
        self.played.append((url, round(start)))

    def stop(self):
        self.stopped += 1


class TestOnTheAir(Temp):
    def test_the_player_through_a_commercial_and_the_slate(self):
        from cathode.screens.live import LiveTV
        app = FakeApp([])
        app.video = Video()
        app.config.video_channels = []
        app.config.library_channels = [chan(breaks=BREAKS)]
        app.library, app.listings, app.schedules = index(), {}, {}
        app.channels = vc.add_to(lineup(1), app.config)
        lc.rebuild(app)
        cid = lc.PREFIX + app.config.library_channels[0]["id"]
        tl = lc.SCHEDULES[cid]
        now = time.time()
        tl.days = [{"day": "x", "start": now - 100, "state": {}, "slots": [
            [now - 10, "p701", 30.0, {"brk": "ad"}], [now + 20, lc.BRB, 10.0, {"brk": "brb"}],
            [now + 30, "p100101", 1320.0]]}]
        tl.state = {"t": now + 1350 + 4 * 86400}
        tl._index()
        calls = []
        app.post = lambda fn, *a, **k: calls.append((fn, a, k))
        old = lc.stream
        lc.stream = lambda app, e, at: {"video": f"http://plex/{e['plex']}", "headers": {}, "base": 0.0}
        try:
            live = LiveTV(app)
            live.tune(1)
            for _ in range(100):
                if calls:
                    break
                time.sleep(0.02)
            fn, a, k = calls.pop(0)
            fn(*a, **k)
            self.assertEqual(app.video.played[-1], ("http://plex/701", 0))       # a commercial: from its top
            self.assertIsNone(live.card)                                         # no name card for a commercial
            due = [t for t in app.timers if not t[3] and abs(t[0] - 20) < 2]
            due[-1][2]()                                                         # its end: the slate
            self.assertEqual(live.signoff["style"], "brb")
        finally:
            lc.stream = old


class TestDefaults(Temp):
    def test_every_channel_breaks_between_programmes_and_not_during_them(self):
        idx = index()
        c = chan("cyclic_shuffle", {"section": "38", "kind": "all"})          # breaks never set
        self.assertEqual(lc.breaks_of(c, idx)["mid"], "off")
        self.assertTrue(lc.breaks_of(c, idx)["ads"])
        tl, got = self.day(c, idx)
        self.assertTrue(any(len(s) > 3 and s[3].get("brk") == "ad" for s in got))   # breaks between
        self.assertEqual([round(s[2]) for s in got if s[1] == "p901"][:1], [6000])    # a film in one piece
        tl, got = self.day(dict(c, breaks={}), idx)                                    # switched off
        self.assertFalse(any(len(s) > 3 for s in got))
        self.assertEqual(lc.breaks_of(c, None), {})                                    # no library: nothing to break with

    def test_short_titles_break_only_near_the_mark(self):
        idx = index()
        clips = library.Section("70", "Shorts", "movie", "s1")
        for n in range(30):
            clips.add_item({"type": "movie", "ratingKey": f"6{n:02d}", "title": f"Short {n}", "duration": 240000})
        idx.sections["70"] = clips
        idx._by_id = None
        tl, got = self.day(chan("cyclic_shuffle", {"section": "70", "kind": "all"}, breaks=BREAKS), idx)
        progs = [s for s in got if is_prog(s)]
        runs = 0
        for a, b in zip(progs, progs[1:]):
            gap = b[0] - (a[0] + a[2])
            if gap > 0.01:
                runs += 1
                lt = datetime.fromtimestamp(b[0])
                self.assertIn((lt.minute, lt.second), ((0, 0), (30, 0)))      # a break, to the half hour
        self.assertGreater(len(progs) / max(1, runs), 4)                      # several shorts to a break, not one each


class TestMaker(Temp):
    def test_the_breaks_page_and_giving_every_channel_breaks(self):
        from types import SimpleNamespace
        from cathode import menus
        app = FakeApp([])
        app.ondemand = SimpleNamespace(signed_in=True)
        app.library = index()
        app.listings, app.schedules, app.live = {}, {}, None
        app.config.video_channels = [vc.new_channel("Hits", ["PLa"])]
        app.config.library_channels = [chan("block_shuffle", {"kind": "studio", "value": "Cartoon Network"})]
        app.channels = vc.add_to(lineup(1), app.config)
        app.top = lambda: SimpleNamespace(back=lambda: None, open=lambda *a: None, refresh=lambda *a: None)
        app.place_own_channels = lambda: None
        app.toast = lambda *a, **k: None
        c = app.config.library_channels[0]
        rows = {it.label: it for it in menus.breaks_items(app, c, lambda place=True: None)}
        self.assertEqual((rows["Breaks"].value(), rows["Commercials from"].value(), rows["Bumpers from"].value()),
                         ("On", "1", "1"))                                     # on from the start
        self.assertEqual((rows["Line up with the clock"].value(), rows["During programmes"].value()),
                         ("Half hours", "Off"))
        rows["Line up with the clock"].adjust(1)
        self.assertEqual(c["breaks"]["pad"], 60)
        libs = rows["Commercials from"].submenu()
        self.assertEqual([it.label for it in libs], ["Classic Commercials", "CN Bumps"])
        libs[1].action()
        self.assertEqual(len(c["breaks"]["ads"]), 2)
        rows["Breaks"].action()
        self.assertEqual((c["breaks"], rows["Breaks"].value()), ({}, "Off"))
        rows["Breaks"].action()
        self.assertEqual(("breaks" in c, rows["Breaks"].value()), (False, "On"))       # back to the defaults
        for it in rows.values():
            if it.value:
                self.assertIsInstance(it.value(), str)
        app.config.video_channels[0]["breaks"] = {}
        lst = {it.label: it for it in menus.library_channel_items(app)}
        lst["Give every channel breaks"].action()
        self.assertTrue(lc.breaks_of(app.config.video_channels[0], app.library)["ads"])
        mids = {it.label: it for it in menus.library_channel_items(app)}["Breaks during programmes"]
        self.assertEqual(mids.value(), "Off")
        mids.adjust(1)
        self.assertEqual(mids.value(), "Halfway")
        mids.adjust(-1)                                                            # switched off, everywhere
        self.assertEqual({lc.breaks_of(x, app.library)["mid"] for x in app.config.library_channels
                          + app.config.video_channels}, {"off"})


if __name__ == "__main__":
    unittest.main()
