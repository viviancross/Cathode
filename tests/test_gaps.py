"""5.3: NostalgiaTV's channel features Cathode lacked: content by season,
episode, collection and playlist; the watched filter; specials; parts back
to back; movies a day; grown-ups' hours; marathons; redirects; starting
over; the better copy of a duplicate; stream channels; the menus for them."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import libchannels as lc, library
from tests.test_library import Temp, chan, index


def slots(tl, hours=24):
    """The programmes (not breaks) of the next hours, as [(start, item)]."""
    now = datetime.now(timezone.utc)
    tl.at(now + timedelta(hours=hours))
    return [(s[0], s[1]) for s in tl._slots if s[1] not in (lc.OFF, lc.BRB) and not (len(s) > 3 and s[3].get("brk"))]


def tl_of(c, idx):
    c.setdefault("breaks", {})
    return lc.Timeline(c, idx, store=False)


class TestContent(Temp):
    def test_a_season_an_episode_a_collection_a_playlist(self):
        idx = index()
        idx.collections = {"c1": {"title": "Nick", "section": "51", "keys": ["100"]}}
        idx.playlists = {"p1": {"title": "Mine", "keys": ["200101", "901"]}}
        ids = lambda src: {i["plex"] for i in lc._matching(src, idx)}     # noqa: E731
        self.assertEqual(ids({"kind": "season", "value": "100:2"}), {"100201", "100202", "100203"})
        self.assertEqual(ids({"kind": "title", "value": ["200103"]}), {"200103"})
        self.assertEqual(ids({"kind": "collection", "value": "c1"}), {"100001", "100101", "100102", "100103",
                                                                       "100104", "100201", "100202", "100203"})
        self.assertEqual(ids({"kind": "playlist", "value": "p1"}), {"200101", "901"})
        self.assertIn(("100:2", "Alpha: Season 2", 3), lc.options(idx, "", "season"))
        self.assertEqual(lc.options(idx, "", "collection"), [("c1", "Nick", 1)])
        self.assertEqual(lc.source_label(idx, {"kind": "season", "section": "51", "value": "100:0"}), "Alpha: Specials")
        self.assertEqual(lc.source_label(idx, {"kind": "playlist", "value": "p1"}), "Playlist: Mine")

    def test_watched_filter_and_specials(self):
        idx = index()
        idx.watched = {"100101", "100102"}
        src = {"kind": "show", "value": "100"}
        got = lambda **kw: {i["plex"] for g in lc.groups(chan("A", "cyclic_shuffle", src, **kw), idx)  # noqa: E731
                            for i in g["items"]}
        self.assertEqual(got(watched="watched"), {"100101", "100102"})
        self.assertNotIn("100101", got(watched="unwatched"))
        self.assertIn("100001", got())
        self.assertNotIn("100001", got(specials=False))

    def test_extras_are_kept_for_a_start_without_the_server(self):
        class Plex:
            def library_sections(self):
                return [{"key": "51", "title": "TV Shows", "kind": "show", "stamp": "s1"}]

            def section_page(self, *a):
                return [], 0

            def extras(self, metas):
                return {"collections": {"c": {"title": "C", "keys": ["1"]}}, "playlists": {}, "watched": ["7"]}
        idx = library.build(Plex())
        self.assertEqual((idx.watched, list(idx.collections)), ({"7"}, ["c"]))
        self.assertEqual(library.cached().watched, {"7"})


class TestSchedule(Temp):
    def test_part_two_follows_part_one(self):
        idx = index()
        tv = idx.sections["51"]
        for i in tv.items:
            if i["show_key"] == "200":
                i["name"] = {1: "Big One, Part 1", 2: "Big One, Part 2"}.get(i["episode"], i["name"])
        tl = tl_of(chan("A", "random", {"kind": "show", "value": "200"}, {"kind": "show", "value": "100"}), idx)
        got = [s[1] for s in slots(tl, 48)]
        for k, x in enumerate(got[:-1]):
            if x == "p200101":
                self.assertEqual(got[k + 1], "p200102")
        self.assertIn("p200101", got)

    def test_movies_a_day_and_grown_ups_hours(self):
        idx = index()
        tl = tl_of(chan("A", "random", max_movies=1), idx)
        days = {}
        for t, x in slots(tl, 72):
            if idx.item(x)["type"] == "movie":
                days[lc.day_of(t)[0]] = days.get(lc.day_of(t)[0], 0) + 1
        self.assertTrue(days and max(days.values()) == 1)
        tl = tl_of(chan("A", "random", {"kind": "show", "value": "300"}, {"kind": "show", "value": "100"},
                        mature_from=22), idx)
        for t, x in slots(tl, 48):
            if idx.item(x)["rating"] == "TV-MA":
                h = datetime.fromtimestamp(t).hour
                self.assertTrue(h >= 22 or h < 6, h)

    def test_a_marathon_is_one_show_back_to_back(self):
        idx = index()
        c = chan("A", "random", marathons=True)
        tl = tl_of(c, idx)
        tl.at(datetime.now(timezone.utc) + timedelta(days=9))
        runs = [s for s in tl._slots if len(s) > 3 and s[3].get("flag") == "Marathon"]
        self.assertTrue(runs)
        self.assertEqual(len({idx.item(s[1])["show_key"] for s in runs[:3]}), 1)

    def test_episode_start_and_starting_over(self):
        idx = index()
        c = chan("A", "block_cyclic", {"kind": "show", "value": "200"}, block=1)
        first = slots(tl_of(dict(c), idx))[0][1]
        self.assertEqual(first, "p200101")
        rnd = slots(tl_of(dict(c, episode_start="random"), idx))[0][1]
        self.assertTrue(rnd.startswith("p2001"))
        tl = tl_of(dict(c), idx)
        slots(tl)
        tl.state["ptr"] = {"s200": "p200104"}
        tl.c["reset"] = 1
        tl.days, tl.state["t"] = [], 0
        self.assertEqual(slots(tl)[0][1], "p200101")

    def test_redirect_carries_another_channel_in_its_hours(self):
        idx = index()
        other = tl_of(chan("B", "cyclic_shuffle", {"kind": "show", "value": "300"}), idx)
        lc.SCHEDULES["lib.b"] = other
        me = tl_of(chan("A", "cyclic_shuffle", {"kind": "show", "value": "100"},
                        redirect={"to": "lib.b", "from": 0, "until": 24}), idx)
        now = datetime.now(timezone.utc)
        self.assertEqual(me.at(now)["entry"]["title"], "Charlie")
        h = datetime.now().hour
        me.c["redirect"] = {"to": "lib.b", "from": (h + 2) % 24, "until": (h + 3) % 24}
        self.assertEqual(me.at(now)["entry"]["title"], "Alpha")


class TestMenus(Temp):
    def test_the_new_pages_build_and_work(self):
        from types import SimpleNamespace
        from cathode import menus, videochannels as vc
        from tests.test_own import FakeApp, lineup
        app = FakeApp([])
        app.ondemand = SimpleNamespace(signed_in=True)
        app.config.video_channels = []
        app.library = index()
        app.listings, app.schedules, app.live = {}, {}, None
        app.config.library_channels = [chan("Comedy", "random", {"kind": "genre", "value": "Comedy"}, starter=True),
                                       chan("Drama", "random", {"kind": "genre", "value": "Drama"})]
        app.channels = vc.add_to(lineup(1), app.config)
        app.lineup_all = list(app.channels)
        app.relineup = lambda: None
        app.toast = lambda *a, **k: None
        opened = []
        app.push = lambda k: None
        app.top = lambda: SimpleNamespace(open=lambda t, items: opened.append((t, items)), pages=[], back=lambda: None)
        lc.rebuild(app)
        a, b = app.config.library_channels
        pages = {"prog": menus.programming_items(app, a, lambda place=True: None),
                 "bulk": menus.bulk_items(app), "redirect": menus.redirect_items(app, a, lambda place=True: None),
                 "hidden": menus.hidden_items(app), "add": menus.add_channel_items(app)}
        src = menus.library_source_items(app, a["id"])
        add = src[-1].submenu()
        for name in ("Add by Season or Episode", "Add by Collection", "Add by Playlist", "Copy From Another Channel"):
            pages[name] = next(it for it in add if it.label == name).submenu()
        for items in pages.values():
            for it in items:
                if it.value:
                    self.assertIsInstance(it.value(), str)
        prog = {it.label: it for it in pages["prog"]}
        prog["Max Movies Per Day"].adjust(1)
        prog["Restrict Ratings After"].adjust(1)
        self.assertEqual((a["max_movies"], a["mature_from"]), (1, 18))
        bulk = pages["bulk"]
        bulk[1].action()                                        # tick Comedy
        sets = {it.label: it for it in bulk[0].submenu()}
        next(it for it in sets["Watched Filter"].submenu() if it.label == "Unwatched only").action()
        self.assertEqual((a.get("watched"), b.get("watched")), ("unwatched", None))
        copy = pages["Copy From Another Channel"]
        copy[0].action()
        self.assertEqual(a["sources"], b["sources"])
        menus.move_channel(app, app.channels[-1], -1)            # Drama up past Comedy
        self.assertEqual(len(app.config.channel_edits), 2)


class TestDedupe(unittest.TestCase):
    def test_the_better_copy(self):
        a = library.Section("1", "Movies", "movie")
        b = library.Section("2", "4K Movies", "movie")
        a.items = [{"id": "pa", "type": "movie", "title": "X", "year": 1, "q": "HD"}]
        b.items = [{"id": "pb", "type": "movie", "title": "X", "year": 1, "q": "4K"}]
        idx = library.Index([a, b])
        idx.dedupe()
        self.assertEqual([len(a.items), len(b.items)], [1, 0])
        a.items = [{"id": "pa", "type": "movie", "title": "X", "year": 1, "q": "HD"}]
        b.items = [{"id": "pb", "type": "movie", "title": "X", "year": 1, "q": "4K"}]
        idx.dedupe("quality")
        self.assertEqual([len(a.items), len(b.items)], [0, 1])


if __name__ == "__main__":
    unittest.main()
