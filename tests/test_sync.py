"""Sync: two Cathodes over real HTTP on this machine. Which channel lists
win (edits, never-edited ties, an edit here since), schedules (older line,
then more worked on, skipped titles on both), YouTube lists (newer), the
hello, and that nothing takes a malformed answer."""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import libchannels as lc, library, sync, videochannels as vc, ytdl
from cathode.config import Config
from cathode.epg import EPG
from tests.test_library import index
from tests.test_own import lineup


class App:
    """Just enough of one Cathode: config, lineup, guide, timers, a post queue."""

    def __init__(self, sid):
        self.config = Config("")
        self.config.sync_id = sid
        self.config.video_channels = []
        self.epg = EPG()
        self.listings, self.schedules = {}, {}
        self.library = index()
        self.posted, self.toasts, self.timers = [], [], []
        self.live = None
        self.channels = vc.add_to(lineup(1, 2), self.config)

    def after(self, s, fn):
        t = [s, 0, fn, False]
        self.timers.append(t)
        return t

    @staticmethod
    def cancel(t):
        if t:
            t[3] = True

    def post(self, fn, *a, **k):
        self.posted.append((fn, a, k))

    def run_posted(self):
        for _ in range(200):
            while self.posted:
                fn, a, k = self.posted.pop(0)
                fn(*a, **k)
            time.sleep(0.01)
            if not self.posted:
                return

    def invalidate(self):
        pass

    def toast(self, text, seconds=2.5):
        self.toasts.append(text)

    def place_own_channels(self):
        plain = [c for c in self.channels if not vc.is_made(c)]
        self.channels = vc.add_to(plain, self.config)


class Two(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._dir = library._dir
        library._dir = lambda: self.tmp
        self.a, self.b = App("aaaa"), App("bbbb")
        self.sa, self.sb = sync.Sync(self.a), sync.Sync(self.b)
        self.a.sync, self.b.sync = self.sa, self.sb
        self.assertTrue(self.sa.serve(0, host="127.0.0.1"))
        self.assertTrue(self.sb.serve(0, host="127.0.0.1"))
        self.peer_a = {"id": "aaaa", "ip": "127.0.0.1", "port": self.sa.port, "name": "PC", "seen": time.monotonic()}
        self.peer_b = {"id": "bbbb", "ip": "127.0.0.1", "port": self.sb.port, "name": "Deck", "seen": time.monotonic()}

    def tearDown(self):
        self.sa.stop()
        self.sb.stop()
        library._dir = self._dir
        lc.SCHEDULES.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def settle(self):
        """Both sides' pictures up to date."""
        self.sa.tick()
        self.sb.tick()

    def b_asks_a(self):
        self.settle()
        self.sb.ask(self.peer_a)
        self.b.run_posted()


class TestChannels(Two):
    def test_an_edit_anywhere_wins_and_a_never_edited_cathode_takes_it(self):
        self.a.config.library_channels = [lc.new_channel("Laugh Track", [{"kind": "genre", "value": "Comedy"}])]
        self.settle()                                               # an edit on the PC: stamped
        self.assertEqual(self.a.config.channels_editor, "aaaa")
        self.assertGreater(self.a.config.channels_edited, 0)
        self.b_asks_a()
        self.assertEqual([c["name"] for c in self.b.config.library_channels], ["Laugh Track"])
        self.assertEqual(self.b.config.library_channels[0]["id"], self.a.config.library_channels[0]["id"])
        self.assertEqual(self.b.config.channels_editor, "aaaa")    # taken, not an edit of the Deck's
        self.assertTrue(self.b.config.library_starter_done)
        self.assertIn("PC", self.b.toasts[-1])
        self.assertTrue(any(lc.is_library(c) for c in self.b.channels))
        self.sb.tick()
        self.assertEqual(self.b.config.channels_editor, "aaaa")    # still not stamped as the Deck's own

    def test_a_later_edit_on_the_other_wins_back_and_ties_settle_on_one(self):
        self.a.config.library_channels = [lc.new_channel("One")]
        self.settle()
        self.b_asks_a()
        time.sleep(0.01)
        self.b.config.library_channels[0]["name"] = "Renamed on the Deck"
        self.sb.tick()
        self.settle()
        self.sa.ask(self.peer_b)
        self.a.run_posted()
        self.assertEqual(self.a.config.library_channels[0]["name"], "Renamed on the Deck")
        self.b.run_posted()
        del self.b.posted[:]
        self.sb.ask(self.peer_a)                                    # nothing newer there now
        self.assertFalse([f for f, _a, _k in self.b.posted if f.__name__.startswith("take")])
        # never edited on either, the lists different (the video prefill's ids): the higher id's lists win
        a2, b2 = App("aaaa"), App("bbbb")
        a2.config.video_channels, b2.config.video_channels = [vc.new_channel("X")], [vc.new_channel("Y")]
        s_a, s_b = sync.Sync(a2), sync.Sync(b2)
        s_a.serve(0, host="127.0.0.1"), s_b.serve(0, host="127.0.0.1")
        try:
            s_a.tick(), s_b.tick()
            s_a.ask({"id": "bbbb", "ip": "127.0.0.1", "port": s_b.port, "name": "Deck", "seen": 0})
            a2.run_posted()
            s_a.tick()
            s_b.ask({"id": "aaaa", "ip": "127.0.0.1", "port": s_a.port, "name": "PC", "seen": 0})
            self.assertFalse([f for f, _a, _k in b2.posted if f.__name__.startswith("take")])   # bbbb's stay; aaaa took them
            self.assertEqual([c["name"] for c in a2.config.video_channels], ["Y"])
        finally:
            s_a.stop(), s_b.stop()

    def test_an_edit_here_since_the_question_keeps_it(self):
        self.a.config.library_channels = [lc.new_channel("Theirs")]
        self.settle()
        doc = self.sa.channels_doc()
        self.b.config.library_channels = [lc.new_channel("Mine, just now")]
        self.b.config.channels_edited, self.b.config.channels_editor = time.time() + 5, "bbbb"
        self.sb.take_channels(self.peer_a, doc)
        self.assertEqual(self.b.config.library_channels[0]["name"], "Mine, just now")

    def test_the_starter_lineup_is_not_an_edit_and_matches_on_both(self):
        made_a, made_b = lc.starter(self.a.library), lc.starter(self.b.library)
        self.assertEqual([c["id"] for c in made_a], [c["id"] for c in made_b])     # same library, same ids
        self.b.config.library_channels = made_b
        sync.quiet(self.b)
        self.sb.tick()
        self.assertEqual(self.b.config.channels_edited, 0.0)

    def test_a_malformed_answer_is_not_taken(self):
        for bad in ({"library_channels": "x"}, {"library_channels": [], "video_channels": [], "own_channels": []},
                    {"library_channels": [{"name": "no id"}], "video_channels": [], "own_channels": {}}, []):
            self.assertFalse(sync._is_channels(bad))
        self.assertTrue(sync._is_channels(self.sa.channels_doc()))
        self.assertFalse(lc.is_doc({"v": lc.VERSION, "days": [{"day": 1}], "state": {}, "dropped": {}}))


class TestSchedules(Two):
    def setUp(self):
        super().setUp()
        c = lc.new_channel("Alpha", [{"section": "51", "kind": "show", "value": "100"}], "playlist")
        for app in (self.a, self.b):
            app.config.library_channels = [json.loads(json.dumps(c))]
        self.cid = lc.PREFIX + c["id"]
        self.ta = lc.Timeline(c, self.a.library, store=False)
        self.ta.at(datetime.now(timezone.utc))
        self.ta.at(datetime.now(timezone.utc) + timedelta(days=1))  # drawn a day further on the PC
        time.sleep(0.01)
        self.tb = lc.Timeline(c, self.b.library, store=False)
        self.tb.at(datetime.now(timezone.utc) + timedelta(hours=7))  # the Deck started later: its own line
        self.b.config.channels_edited = self.a.config.channels_edited = 1.0
        self.b.config.channels_editor = self.a.config.channels_editor = "aaaa"
        sync.quiet(self.a), sync.quiet(self.b)

    def serve(self, which):
        lc.SCHEDULES.clear()
        lc.SCHEDULES[self.cid] = which

    def test_the_older_line_wins_and_the_same_thing_is_on(self):
        self.assertTrue(lc.beats(self.ta.version(), self.tb.version()))
        self.assertFalse(lc.beats(self.tb.version(), self.ta.version()))
        doc = self.ta.doc()
        self.assertTrue(self.tb.adopt(doc))
        now = datetime.now(timezone.utc)
        for h in (0, 5, 20, 30):
            t = now + timedelta(hours=h)
            self.assertEqual(self.tb.at(t)["entry"]["id"], self.ta.at(t)["entry"]["id"])
            self.assertEqual(self.tb.at(t)["start"], self.ta.at(t)["start"])
        self.assertFalse(self.tb.adopt(doc))                        # the same again: nothing to take
        self.assertFalse(self.ta.adopt(self.tb.doc()))
        other = dict(doc, sig="different")                          # another edit of the channel: not taken
        self.assertFalse(lc.beats(other, self.tb.version()))

    def test_a_title_skipped_on_one_is_skipped_on_both(self):
        self.tb.adopt(self.ta.doc())
        now = datetime.now(timezone.utc)
        on = self.ta.at(now)["entry"]["id"]
        sync.ME = "bbbb"
        self.tb.drop(on, now)                                       # the Deck couldn't play it
        self.assertTrue(lc.beats(self.tb.version(), self.ta.version()))     # more worked on: it wins now
        self.assertTrue(self.ta.adopt(self.tb.doc()))
        self.assertIn(on, self.ta.dropped)
        self.assertEqual(self.ta.at(now)["entry"]["id"], self.tb.at(now)["entry"]["id"])
        # skipped on each, separately: after taking the other's, both are out of both
        t = now + timedelta(hours=3)
        x, y = self.ta.at(t)["entry"]["id"], self.ta.at(t + timedelta(hours=2))["entry"]["id"]
        sync.ME = "aaaa"                                            # (two Cathodes, one module: each its own id)
        self.ta.drop(x, now)
        sync.ME = "bbbb"
        self.tb.drop(y, now)
        winner, loser = (self.ta, self.tb) if lc.beats(self.ta.version(), self.tb.version()) else (self.tb, self.ta)
        self.assertTrue(loser.adopt(winner.doc()))
        self.assertTrue(winner.adopt(loser.doc()))                  # the loser's own skip, back again
        self.assertEqual(set(self.ta.dropped), set(self.tb.dropped))
        self.assertTrue({x, y} <= set(self.ta.dropped))

    def test_over_the_network(self):
        self.serve(self.ta)
        self.sa.tick()
        lc.SCHEDULES[self.cid] = self.tb
        self.sb.tick()
        lc.SCHEDULES[self.cid] = self.ta                            # (one module, two Cathodes: A answers)
        mine = self.sb.snapshot
        self.assertIn(self.cid, json.loads(mine)["schedules"])
        st = self.sb._get(self.peer_a, "/cathode/sync")
        self.assertEqual(st["schedules"][self.cid]["lineage"], self.ta.lineage)
        doc = self.sb._get(self.peer_a, "/cathode/schedule?id=" + self.cid)
        lc.SCHEDULES[self.cid] = self.tb
        self.sb.take_schedule(self.peer_a, self.cid, doc)
        self.assertEqual(self.tb.lineage, self.ta.lineage)
        now = datetime.now(timezone.utc)
        self.assertEqual(self.tb.at(now)["entry"]["id"], self.ta.at(now)["entry"]["id"])

    def test_new_schedules_are_the_newest_line_until_saved(self):
        late = lc.Timeline(self.a.config.library_channels[0], self.a.library, store=False)
        self.assertTrue(lc.beats(self.ta.version(), late.version()))


class TestListings(Two):
    def test_a_newer_youtube_list_is_taken_and_cached(self):
        kept = {}
        old_keep = ytdl.keep_listing
        ytdl.keep_listing = lambda url, lst: kept.setdefault(url, lst)
        try:
            for app in (self.a, self.b):
                app.config.video_channels = [vc.new_channel("Mix", ["PLa"])]
                app.config.video_channels[0]["id"] = "same"
            self.a.listings = {"PLa": {"title": "Hits", "fetched": time.time(), "entries": [{"id": "v1", "duration": 200}]}}
            self.b.listings = {"PLa": {"title": "Hits", "fetched": time.time() - 86400, "entries": []}}
            self.b.config.channels_edited = self.a.config.channels_edited = 1.0
            self.b.config.channels_editor = self.a.config.channels_editor = "aaaa"
            sync.quiet(self.a), sync.quiet(self.b)
            self.b_asks_a()
            self.assertEqual(self.b.listings["PLa"]["entries"][0]["id"], "v1")
            self.assertIn("PLa", kept)
            self.b_asks_a()                                         # the same now: not again
            self.assertEqual(len(kept), 1)
        finally:
            ytdl.keep_listing = old_keep


class TestHello(unittest.TestCase):
    def test_hellos_are_heard_and_odd_ones_ignored(self):
        app = App("me")
        s = sync.Sync(app)
        s.port = 1234
        s.heard(s.hello(), "10.0.0.5")                              # its own: ignored
        self.assertEqual(s.peers, {})
        s.heard(json.dumps({"cathode": "sync", "v": sync.V, "id": "deck", "name": "steamdeck", "port": 47810}).encode(),
                "10.0.0.9")
        self.assertEqual((s.peers["deck"]["ip"], s.peers["deck"]["port"]), ("10.0.0.9", 47810))
        self.assertEqual([p["name"] for p in s.others()], ["steamdeck"])
        for bad in (b"junk", b"[]", json.dumps({"cathode": "sync", "v": 99, "id": "x", "port": 1}).encode(),
                    json.dumps({"cathode": "sync", "v": sync.V, "id": "y", "port": 70000}).encode()):
            s.heard(bad, "10.0.0.7")
        self.assertEqual(list(s.peers), ["deck"])
        s.peers["deck"]["seen"] -= sync.GONE + 1
        self.assertEqual(s.others(), [])

    def test_the_menu_row_reads_and_toggles(self):
        from cathode import menus
        app = App("me")
        app.ondemand = None
        row = next(it for it in menus.channel_items(app) if it.label == "Sync with other Cathodes")
        self.assertEqual(row.value(), "Off")                        # not started in a test
        app.sync = sync.Sync(app)
        app.sync.peers = {"d": {"id": "d", "ip": "x", "port": 1, "name": "steamdeck", "seen": time.monotonic()}}
        self.assertEqual(row.value(), "On: steamdeck")
        app.sync = None
        old = sync.start
        sync.start = lambda a: None
        try:
            row.adjust(1)
            self.assertFalse(app.config.lan_sync)
            row.adjust(1)
            self.assertTrue(app.config.lan_sync)
        finally:
            sync.start = old


if __name__ == "__main__":
    unittest.main()
