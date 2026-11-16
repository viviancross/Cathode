"""Library channels: the index (rows, its file, what the server is asked),
what a channel draws from, the nine sort methods, the written-down days
(continuity, the file, edits), the starter lineup, placement, the guide,
tuning (the stream asked of Plex, a title that can't play), the maker."""

import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import libchannels as lc, library, videochannels as vc
from cathode.screens.live import LiveTV
from tests.test_own import FakeApp, lineup   # noqa: F401

SHOWS = [  # key, title, year, genres, studio, rating, [(season, episodes)]
    ("100", "Alpha", 1994, ["Comedy"], "Nickelodeon Productions", "TV-Y7", [(0, 1), (1, 4), (2, 3)]),
    ("200", "Bravo", 1998, ["Comedy", "Animation"], "Nickelodeon Animation Studio", "TV-PG", [(1, 5)]),
    ("300", "Charlie", 2004, ["Drama"], "BBC", "TV-MA", [(1, 3)]),
]
MOVIES = [("901", "Heist", 1995, ["Action"], 6000), ("902", "Laughs", 1999, ["Comedy"], 5400),
          ("903", "Space", 2003, ["Science Fiction"], 7200)]


def index(stamp="s1"):
    tv = library.Section("51", "TV Shows", "show", stamp)
    for key, title, year, genres, studio, rating, seasons in SHOWS:
        tv.add_show({"ratingKey": key, "title": title, "year": year, "Genre": [{"tag": g} for g in genres],
                     "studio": studio, "contentRating": rating, "thumb": f"/t/{key}"})
        for s, n in seasons:
            for e in range(1, n + 1):
                tv.add_item({"type": "episode", "ratingKey": f"{key}{s}{e:02d}", "grandparentRatingKey": key,
                             "grandparentTitle": title, "parentIndex": s, "index": e, "title": f"{title} {s}x{e}",
                             "duration": 1320000, "summary": "Things happen.", "contentRating": rating})
    mv = library.Section("38", "Movies", "movie", stamp)
    for key, title, year, genres, secs in MOVIES:
        mv.add_item({"type": "movie", "ratingKey": key, "title": title, "year": year, "duration": secs * 1000,
                     "Genre": [{"tag": g} for g in genres], "summary": "A film."})
    ads = library.Section("10", "CN Bumps", "clip", stamp)
    for n in range(5):
        ads.add_item({"type": "movie", "ratingKey": f"8{n}", "title": f"Bump {n}", "duration": 15000})
    return library.Index([tv, mv, ads])


def chan(name="Chan", order="cyclic_shuffle", *sources, **kw):
    return lc.new_channel(name, sources or [{"kind": "all"}], order, **kw)


class Temp(unittest.TestCase):
    """The cache folder is a temporary one."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._dir = library._dir
        library._dir = lambda: self.tmp

    def tearDown(self):
        library._dir = self._dir
        lc.SCHEDULES.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestIndex(Temp):
    def test_episodes_take_their_shows_genres_and_the_file_reads_back(self):
        idx = index()
        tv = idx.sections["51"]
        ep = idx.item("p100101")
        self.assertEqual((ep["title"], ep["name"], ep["season"], ep["episode"], ep["genres"], ep["studio"]),
                         ("Alpha", "Alpha 1x1", 1, 1, ["Comedy"], "Nickelodeon Productions"))
        self.assertEqual(ep["duration"], 1320)
        self.assertTrue(idx.sections["10"].breaks)              # clips of 15 s: break material
        self.assertEqual([s.title for s in idx.programme_sections()], ["TV Shows", "Movies"])
        for s in idx.sections.values():
            s.save()
            back = library.Section.load(s.key)
            self.assertEqual(back.items, s.items)
            self.assertEqual((back.title, back.kind, back.stamp), (s.title, s.kind, s.stamp))
        self.assertEqual(len(library.cached().sections), 3)
        self.assertEqual(library.cached({"38"}).sections["38"].hidden, True)
        self.assertIs(tv.shows["100"]["genres"], ep["genres"])  # shared, not copied 40,000 times

    def test_a_library_is_fetched_only_when_the_server_says_it_changed(self):
        src = index()

        class Client:
            asked = []
            stamps = {"51": "a", "38": "a"}

            def library_sections(self):
                return [{"key": k, "title": src.sections[k].title, "kind": src.sections[k].kind, "stamp": v}
                        for k, v in self.stamps.items()]

            def section_page(self, key, type_, start, size):
                self.asked.append((key, type_, start))
                sec = src.sections[key]
                if type_ == 2:
                    rows = [{"ratingKey": s["key"], "title": s["title"], "year": s["year"], "studio": s["studio"],
                             "Genre": [{"tag": g} for g in s["genres"]], "contentRating": s["rating"]}
                            for s in sec.shows.values()]
                else:
                    rows = [{"type": "episode" if i["type"] == "episode" else "movie", "ratingKey": i["plex"],
                             "title": i["name"] or i["title"], "grandparentTitle": i["title"],
                             "grandparentRatingKey": i.get("show_key"), "parentIndex": i.get("season"),
                             "index": i.get("episode"), "duration": i["duration"] * 1000, "year": i["year"]}
                            for i in sec.items]
                return rows[start:start + 5], len(rows)         # five to a page

        c = Client()
        idx = library.build(c)
        self.assertEqual(idx.count(), 19)
        self.assertEqual([a for a in c.asked if a[0] == "51" and a[1] == 4], [("51", 4, 0), ("51", 4, 5), ("51", 4, 10), ("51", 4, 15)])
        del c.asked[:]
        self.assertEqual(library.build(c).count(), 19)
        self.assertEqual(c.asked, [])                           # same stamps: the files
        c.stamps["38"] = "b"
        library.build(c, hidden={"38"})
        self.assertEqual({a[0] for a in c.asked}, {"38"})       # only the one that changed (hidden ones are read too)


class TestSources(Temp):
    def test_a_genre_a_decade_a_studio_a_rating_a_show(self):
        idx = index()

        def titles(*sources):
            return [(g["title"], len(g["items"])) for g in lc.groups({"sources": list(sources)}, idx)]
        self.assertEqual(titles({"kind": "genre", "value": "Comedy"}), [("Alpha", 7), ("Bravo", 5), ("Laughs", 1)])
        self.assertEqual(titles({"kind": "genre", "value": "Comedy", "only": "show"}), [("Alpha", 7), ("Bravo", 5)])
        self.assertEqual(titles({"kind": "decade", "value": 1990}), [("Alpha", 7), ("Bravo", 5), ("Heist", 1), ("Laughs", 1)])
        self.assertEqual(titles({"kind": "studio", "value": "Nickelodeon"}), [("Alpha", 7), ("Bravo", 5)])
        self.assertEqual(titles({"kind": "rating", "value": lc.MATURE}), [("Charlie", 3)])
        self.assertEqual(titles({"section": "51", "kind": "show", "value": "200"}), [("Bravo", 5)])
        self.assertEqual(len(titles({"kind": "all"})), 6)       # the bumpers stay out of everything
        self.assertEqual(titles({"section": "10", "kind": "all"}), [])      # (and are too short for a programme)
        # twice matched, once in; a show's specials left out; its episodes in order
        g = lc.groups({"sources": [{"kind": "genre", "value": "Comedy"}, {"kind": "decade", "value": 1990}]}, idx)
        self.assertEqual([x["title"] for x in g], ["Alpha", "Bravo", "Heist", "Laughs"])
        self.assertEqual([(i["season"], i["episode"]) for i in g[0]["items"]],
                         [(1, 1), (1, 2), (1, 3), (1, 4), (2, 1), (2, 2), (2, 3)])
        idx.sections["38"].hidden = True
        self.assertEqual(len(titles({"kind": "all"})), 3)       # hidden from On Demand: not taken unasked
        self.assertEqual(len(titles({"section": "38", "kind": "all"})), 3)  # but there when asked for

    def test_a_studio_without_its_trade(self):
        for full, short in [("Nickelodeon Animation Studio", "Nickelodeon"), ("Disney Television Animation", "Disney"),
                            ("Cartoon Network Studios", "Cartoon Network"), ("Hanna-Barbera Cartoons", "Hanna-Barbera"),
                            ("20th Century Fox Television", "20th Century Fox"), ("MTV Networks", "MTV"), ("BBC", "BBC")]:
            self.assertEqual(lc.brand(full), short)


class TestSorts(Temp):
    def draw(self, order, n, state=None, block=0, sources=({"section": "51", "kind": "all"},)):
        groups = lc.groups({"sources": list(sources)}, index())
        r = lc.Rotor("lib.x", order, block, groups, {} if state is None else state)
        return [r.next() for _ in range(n)]

    @staticmethod
    def tag(i):
        return f"{i['title'][0]}{i['season']}.{i['episode']}"

    def test_cyclic_shuffle_airs_everything_once_a_cycle(self):
        got = [i["id"] for i in self.draw("cyclic_shuffle", 45)]
        for k in range(3):
            self.assertEqual(len(set(got[k * 15:k * 15 + 15])), 15)
        self.assertNotEqual(got[:15], got[15:30])
        self.assertNotEqual(got[14], got[15])                   # a cycle doesn't open on the last one's closer

    def test_random_keeps_recent_titles_away(self):
        got = [i["id"] for i in self.draw("random", 200)]
        self.assertGreater(len(set(got)), 12)
        self.assertTrue(all(got[n] not in got[n - 3:n] for n in range(3, 200)))

    def test_blocks_run_in_order_and_shows_take_turns(self):
        self.assertEqual([self.tag(i) for i in self.draw("block_cyclic", 8)],
                         ["A1.1", "A1.2", "B1.1", "B1.2", "C1.1", "C1.2", "A1.3", "A1.4"])
        self.assertEqual([self.tag(i) for i in self.draw("block_cyclic", 4, block=3)], ["A1.1", "A1.2", "A1.3", "B1.1"])
        self.assertEqual([self.tag(i) for i in self.draw("round_robin_cyclic", 5)], ["A1.1", "B1.1", "C1.1", "A1.2", "B1.2"])
        got = [self.tag(i) for i in self.draw("block_shuffle", 40)]
        for n in range(0, 40, 2):
            self.assertEqual(got[n][0], got[n + 1][0])          # two of a show together
            if n:
                self.assertNotEqual(got[n][0], got[n - 1][0])   # then another show
        for show in "ABC":                                      # each show's episodes in its own order, round again
            mine = [t for t in got if t[0] == show]
            self.assertEqual(mine[:3], [f"{show}1.1", f"{show}1.2", f"{show}1.3"])

    def test_marathons_and_round_robin_shuffle_and_playlist(self):
        got = [self.tag(i) for i in self.draw("marathon_cyclic", 13)]
        self.assertEqual(got[:7], ["A1.1", "A1.2", "A1.3", "A1.4", "A2.1", "A2.2", "A2.3"])
        self.assertEqual((got[7], got[11], got[12]), ("A1.1", "A2.1", "B1.1"))   # twelve of Alpha, then Bravo
        got = [self.tag(i)[0] for i in self.draw("round_robin_shuffle", 12)]
        for n in range(0, 12, 3):
            self.assertEqual(sorted(got[n:n + 3]), ["A", "B", "C"])     # every show once a round
        got = [self.tag(i) for i in self.draw("playlist", 16)]
        self.assertEqual(got[:7] + got[7:12] + got[12:15] + got[15:],
                         ["A1.1", "A1.2", "A1.3", "A1.4", "A2.1", "A2.2", "A2.3", "B1.1", "B1.2", "B1.3", "B1.4",
                          "B1.5", "C1.1", "C1.2", "C1.3", "A1.1"])

    def test_the_state_carries_the_rotation_on(self):
        import json
        for order in [o for o, _ in lc.ORDERS]:
            straight = [i["id"] for i in self.draw(order, 30)]
            state = {}
            first = [i["id"] for i in self.draw(order, 11, state)]
            rest = [i["id"] for i in self.draw(order, 19, json.loads(json.dumps(state)))]   # as read back from disk
            self.assertEqual(first + rest, straight, order)

    def test_movies_are_groups_of_one(self):
        got = [i["title"] for i in self.draw("playlist", 4, sources=({"section": "38", "kind": "all"},))]
        self.assertEqual(got, ["Heist", "Laughs", "Space", "Heist"])
        self.assertIsNone(lc.Rotor("x", "random", 0, [], {}).next())


class TestTimeline(Temp):
    def test_every_moment_is_in_a_title_and_tomorrow_carries_on(self):
        c = chan("Alpha", "playlist", {"section": "51", "kind": "show", "value": "100"})
        tl = lc.Timeline(c, index())
        now = datetime.now(timezone.utc)
        cur = tl.at(now)
        self.assertTrue(cur["start"] <= now < cur["stop"])
        self.assertEqual(cur["entry"]["kind"], "show")
        self.assertEqual(cur["entry"]["plex"], cur["entry"]["id"][1:])
        day = tl.days[-1]
        self.assertEqual(datetime.fromtimestamp(day["start"]).hour, 4)
        seen, t = [], day["start"]
        for start, item_id, dur in day["slots"]:
            self.assertAlmostEqual(start, t, places=3)          # end to end
            t = start + dur
            seen.append(item_id)
        self.assertGreaterEqual(t, lc._next_day(day["start"]))
        self.assertEqual(seen[:8], ["p100101", "p100102", "p100103", "p100104", "p100201", "p100202", "p100203", "p100101"])
        last = seen[-1]
        tomorrow = tl.at(now + timedelta(days=1))
        self.assertEqual(len(tl.days), 2)
        order = ["p100101", "p100102", "p100103", "p100104", "p100201", "p100202", "p100203"]
        first = tl.days[1]["slots"][0]
        self.assertEqual(first[1], order[(order.index(last) + 1) % 7])     # the episode after yesterday's last
        self.assertAlmostEqual(first[0], t, places=3)           # from where yesterday's last ended, past 4 AM
        self.assertTrue(tomorrow["start"] <= now + timedelta(days=1) < tomorrow["stop"])

    def test_the_days_are_on_disk_and_read_back_the_same(self):
        c = chan("Mix", "block_shuffle")
        now = datetime.now(timezone.utc)
        a = lc.Timeline(c, index())
        mine = [a.at(now + timedelta(hours=h))["entry"]["id"] for h in range(0, 40, 3)]
        self.assertTrue(os.path.exists(os.path.join(self.tmp, f"sched-{c['id']}.json")))
        b = lc.Timeline(c, index())
        self.assertEqual(len(b.days), len(a.days))
        self.assertEqual([b.at(now + timedelta(hours=h))["entry"]["id"] for h in range(0, 40, 3)], mine)
        far = b.at(now + timedelta(days=3))                     # further on: drawn up from where the file ended
        again = lc.Timeline(c, index()).at(now + timedelta(days=3))
        self.assertEqual(far["entry"]["id"], again["entry"]["id"])

    def test_an_edit_redraws_today_onward_and_a_changed_library_tomorrow_onward(self):
        c = chan("Mix", "cyclic_shuffle")
        now = datetime.now(timezone.utc)
        a = lc.Timeline(c, index())
        a.at(now + timedelta(days=2))
        today = [s[1] for s in a.days[0]["slots"]]
        later = [s[1] for s in a.days[1]["slots"]]
        b = lc.Timeline(dict(c, order="playlist"), index())     # edited
        self.assertEqual(b.days, [])
        b.at(now)
        self.assertNotEqual([s[1] for s in b.days[0]["slots"]], today)
        self.assertEqual([s[1] for s in b.days[0]["slots"]][:3], ["p100101", "p100102", "p100103"])
        a2 = lc.Timeline(c, index())                            # (the file is b's now: read as an edit back)
        a2.at(now + timedelta(days=2))
        d = lc.Timeline(c, index("s2"))                         # the library scanned something in
        self.assertEqual(len(d.days), 1)                        # today stays as it was drawn
        self.assertEqual([s[1] for s in d.days[0]["slots"]], [s[1] for s in a2.days[0]["slots"]])
        idx = index()
        gone = a2.days[0]["slots"][0][1]
        for sec in idx.sections.values():
            sec.items = [i for i in sec.items if i["id"] != gone]
        e = lc.Timeline(c, idx)                                 # a title left the library: its day is drawn again
        self.assertEqual(e.days, [])
        self.assertIsNotNone(e.at(now))
        self.assertNotIn(gone, [s[1] for s in e.days[0]["slots"]])
        self.assertEqual(later, later)

    def test_a_refresh_draws_the_days_differently_and_an_empty_channel_is_quiet(self):
        c = chan("Mix", "cyclic_shuffle")
        now = datetime.now(timezone.utc)
        a = lc.Timeline(c, index(), store=False)
        b = lc.Timeline(dict(c, seed=123), index(), store=False)
        a.at(now), b.at(now)
        self.assertNotEqual([s[1] for s in a.days[0]["slots"]][:15], [s[1] for s in b.days[0]["slots"]][:15])
        none = lc.Timeline(chan("None", "random", {"kind": "genre", "value": "Western"}), index(), store=False)
        self.assertEqual(none.entries, [])
        self.assertIsNone(none.at(now))


class TestLineup(Temp):
    def test_library_channels_sit_in_a_block_after_the_lineup(self):
        app = FakeApp([])
        cfg = app.config
        cfg.video_channels = []
        cfg.library_channels = [chan("Comedy"), chan("Picked", number=7), chan("Movies")]
        chans = vc.add_to(lineup(2, 4, 69), cfg)
        self.assertEqual([(c.number, c.name) for c in chans],
                         [(2, "Ch2"), (4, "Ch4"), (7, "Picked"), (69, "Ch69"), (101, "Comedy"), (102, "Movies")])
        self.assertTrue(all(lc.is_library(c) for c in chans if c.number in (7, 101, 102)))
        self.assertTrue(vc.is_made(chans[-1]))
        self.assertEqual([c.number for c in vc.add_to(chans, cfg)], [2, 4, 7, 69, 101, 102])    # again: not doubled
        self.assertEqual([c.name for c in vc.add_to([], cfg)][:1], ["Comedy"])    # no playlist: Cathode's own, from 1
        self.assertEqual(vc.entry(cfg, lc.PREFIX + cfg.library_channels[0]["id"])["name"], "Comedy")

    def test_the_starter_lineup_follows_the_library(self):
        old = (lc.MAIN_SHOWS, lc.GENRE_SHOWS, lc.DECADE_SHOWS, lc.STUDIO_SHOWS, lc.GENRE_MOVIES, lc.DECADE_MOVIES,
               lc.MARATHON_EPISODES)
        lc.MAIN_SHOWS, lc.GENRE_SHOWS, lc.DECADE_SHOWS, lc.STUDIO_SHOWS = 3, 2, 2, 2
        lc.GENRE_MOVIES, lc.DECADE_MOVIES, lc.MARATHON_EPISODES = 1, 2, 6
        try:
            idx = index()
            made = lc.starter(idx)
            names = [c["name"] for c in made]
            self.assertEqual(names, ["Laugh Track", "The '90s", "Slimetime", "Alpha", "Movies", "Action Movies",
                                     "Comedy Movies", "Sci-Fi Movies", "'90s Movies"])     # placeholders of our own
            self.assertTrue(all(c["starter"] for c in made))
            for c in made:
                self.assertTrue(lc.groups(c, idx), c["name"])           # none of them empty
            app = FakeApp([])
            app.config.library_channels = [chan("Laugh Track")]         # one of yours by that name: left alone
            self.assertEqual(lc.add_starter(app.config, idx), 8)
            self.assertEqual(lc.add_starter(app.config, idx), 0)
            self.assertFalse(app.config.library_channels[0]["starter"])
        finally:
            (lc.MAIN_SHOWS, lc.GENRE_SHOWS, lc.DECADE_SHOWS, lc.STUDIO_SHOWS, lc.GENRE_MOVIES, lc.DECADE_MOVIES,
             lc.MARATHON_EPISODES) = old


class FakeVideo2:
    def __init__(self):
        self.played = []

    def play(self, url, headers=None, start=0, sub_delay=0.0, audio=None):
        self.played.append((url, headers, round(start)))

    def stop(self):
        pass


class TestOnTheAir(Temp):
    def setUp(self):
        super().setUp()
        self.app = app = FakeApp([])
        app.video = FakeVideo2()
        app.config.video_channels = []
        app.config.library_channels = [chan("Alpha", "playlist", {"section": "51", "kind": "show", "value": "100"},
                                            card=True)]
        app.library = index()
        app.listings, app.schedules = {}, {}
        app.channels = vc.add_to(lineup(1), app.config)
        lc.rebuild(app)                                         # no event loop: built in line, the guide filled
        self.cid = lc.PREFIX + app.config.library_channels[0]["id"]
        self.calls = []
        app.post = lambda fn, *a, **k: self.calls.append((fn, a, k))
        self._stream = lc.stream

    def tearDown(self):
        lc.stream = self._stream
        super().tearDown()

    def run_posted(self):
        for _ in range(100):
            if self.calls:
                break
            time.sleep(0.02)
        fn, a, k = self.calls.pop(0)
        fn(*a, **k)

    def test_the_guide_lists_each_programme_with_its_episode(self):
        ch = self.app.channels[-1]
        now = datetime.now(timezone.utc)
        cur = self.app.epg.current(ch.epg_id, now) if hasattr(self.app.epg, "current") else None
        progs = self.app.video_programmes[ch.epg_id]
        self.assertGreater(len(progs), 100)                     # two days of 22-minute episodes
        on = next(p for p in progs if p.start <= now < p.stop)
        tl = lc.SCHEDULES[self.cid]
        e = tl.at(now)["entry"]
        self.assertEqual((on.title, on.episode, on.category, on.rating), ("Alpha", e["episode_text"], "Comedy", "TV-Y7"))
        self.assertIn(e["name"], on.description)
        self.assertTrue(all(a.stop == b.start for a, b in zip(progs, progs[1:])))
        self.assertIsNotNone(cur if cur is not None else on)

    def test_tuning_asks_plex_for_the_stream_from_where_the_title_is(self):
        asked = []

        def stream(app, e, at):
            asked.append((e["plex"], at))
            return {"video": f"http://plex/{e['plex']}", "headers": {"X-Plex-Token": "t"}, "base": 0.0}
        lc.stream = stream
        live = LiveTV(self.app)
        live.tune(len(self.app.channels) - 1)
        self.assertIsNotNone(live.vplayer)
        self.run_posted()
        cur = lc.SCHEDULES[self.cid].at(datetime.now(timezone.utc))
        url, headers, start = self.app.video.played[-1]
        self.assertEqual((url, headers), (f"http://plex/{cur['entry']['plex']}", {"X-Plex-Token": "t"}))
        self.assertAlmostEqual(start, cur["offset"], delta=2)   # mid-programme, as the clock has it
        self.assertAlmostEqual(asked[0][1], cur["offset"], delta=2)
        self.assertEqual((live.card["artist"], live.card["song"]), ("Alpha", "Alpha"))
        # a transcode starts at its base: the player starts at its top
        lc.stream = lambda app, e, at: {"video": "http://plex/t.m3u8", "headers": {}, "base": float(int(at))}
        live.vplayer.start()
        self.run_posted()
        self.assertLessEqual(self.app.video.played[-1][2], 1)
        left = (cur["stop"] - datetime.now(timezone.utc)).total_seconds()
        self.assertTrue(any(abs(t[0] - left) < 3 and not t[3] for t in self.app.timers), "the next is due at the stop")

    def test_a_broken_file_is_skipped_and_what_follows_moves_up(self):
        from cathode.plex import PlexError
        tl = lc.SCHEDULES[self.cid]
        ch = self.app.channels[-1]
        now = datetime.now(timezone.utc)
        cur = tl.at(now)
        nxt = tl.at(cur["stop"] + timedelta(seconds=1))
        bad, was_due = cur["entry"], nxt["start"]

        def stream(app, e, at):
            if e["plex"] == bad["plex"]:
                raise PlexError("The server can't read this file.")
            return {"video": f"http://plex/{e['plex']}", "headers": {}, "base": 0.0}
        lc.stream = stream
        live = LiveTV(self.app)
        live.tune(len(self.app.channels) - 1)
        self.run_posted()                                       # the file can't be read: skipped
        self.run_posted()                                       # the next title's stream
        url, _h, start = self.app.video.played[-1]
        self.assertEqual(url, f"http://plex/{nxt['entry']['plex']}")
        self.assertLessEqual(start, 2)                          # from its top, now: not when it was due
        self.assertFalse(live.standby)
        on = tl.at(datetime.now(timezone.utc))
        self.assertEqual(on["entry"]["id"], nxt["entry"]["id"])
        self.assertLess(on["start"], was_due)
        self.assertLess(abs((on["start"] - now).total_seconds()), 5)
        progs = vc.programmes([ch], {self.cid: tl})[ch.epg_id]  # the guide moved up with it, no hole in it
        self.assertTrue(all(a.stop == b.start for a, b in zip(progs, progs[1:])))
        listed = next(p for p in progs if p.start <= datetime.now(timezone.utc) < p.stop)
        self.assertIn(nxt["entry"]["name"], listed.description)
        tl.at(now + timedelta(days=2))                          # and it's off the days drawn up from here
        ahead = [s[1] for d in tl.days for s in d["slots"] if s[0] > now.timestamp() + 5]
        self.assertGreater(len(ahead), 150)
        self.assertNotIn(bad["id"], ahead)
        again = lc.Timeline(self.app.config.library_channels[0], self.app.library)     # a restart remembers
        self.assertIn(bad["id"], again.dropped)
        self.assertEqual(again.at(datetime.now(timezone.utc))["entry"]["id"], nxt["entry"]["id"])
        # a file that breaks off part-way is skipped the same way
        live.phase = "watch"
        third = tl.at(on["stop"] + timedelta(seconds=1))
        live.on_video("video_ended", reason="error")
        self.run_posted()
        self.assertEqual(self.app.video.played[-1][0], f"http://plex/{third['entry']['plex']}")
        self.assertFalse(live.standby)

    def test_the_title_due_next_is_checked_ahead_and_skipped_before_its_time(self):
        from cathode.plex import PlexError
        tl = lc.SCHEDULES[self.cid]
        cur = tl.at(datetime.now(timezone.utc))
        nxt = tl.at(cur["stop"] + timedelta(seconds=1))
        after = tl.at(nxt["stop"] + timedelta(seconds=1))

        def stream(app, e, at):
            if e["plex"] == nxt["entry"]["plex"]:
                raise PlexError("The server can't read this file.")
            return {"video": f"http://plex/{e['plex']}", "headers": {}, "base": 0.0}
        lc.stream = stream
        live = LiveTV(self.app)
        live.tune(len(self.app.channels) - 1)
        self.run_posted()
        left = (cur["stop"] - datetime.now(timezone.utc)).total_seconds()
        ahead = [t for t in self.app.timers if not t[3] and abs(t[0] - max(0.5, left - vc.AHEAD)) < 3]
        self.assertTrue(ahead)
        ahead[-1][2]()                                          # twenty seconds before the stop: asked ahead
        self.run_posted()
        self.assertEqual(len(self.app.video.played), 1)         # what's on carries on
        follows = tl.at(cur["stop"] + timedelta(seconds=1))
        self.assertEqual(follows["entry"]["id"], after["entry"]["id"])
        self.assertEqual(follows["start"], cur["stop"])

    def test_failures_in_a_row_stop_at_the_stand_by_card(self):
        from cathode.plex import PlexError

        def stream(app, e, at):
            raise PlexError("The server can't read this file.")
        lc.stream = stream
        old, vc.MAX_SKIPS = vc.MAX_SKIPS, 3
        try:
            live = LiveTV(self.app)
            live.tune(len(self.app.channels) - 1)
            for _ in range(4):
                self.run_posted()
            self.assertTrue(live.standby)
            self.assertEqual(self.app.video.played, [])
            self.assertEqual(len(lc.SCHEDULES[self.cid].dropped), 3)       # three skipped; the fourth held
            self.assertEqual(self.calls, [])
        finally:
            vc.MAX_SKIPS = old

    def test_the_server_being_away_holds_the_stand_by_and_tries_again(self):
        def away(app, e, at):
            raise OSError("connection refused")
        lc.stream = away
        live = LiveTV(self.app)
        live.tune(len(self.app.channels) - 1)
        self.run_posted()
        self.assertTrue(live.standby)
        self.assertEqual(self.app.video.played, [])
        self.assertEqual(lc.SCHEDULES[self.cid].dropped, {})    # nothing is skipped for the server's sake
        cur = lc.SCHEDULES[self.cid].at(datetime.now(timezone.utc))
        left = (cur["stop"] - datetime.now(timezone.utc)).total_seconds()
        retry = [t for t in self.app.timers if not t[3] and abs(t[0] - min(left, 60.0)) < 3]
        self.assertTrue(retry, "another try in a minute, or the next title at the stop")
        lc.stream = lambda app, e, at: {"video": "http://plex/ok", "headers": {}, "base": 0.0}
        retry[-1][2]()                                          # the server is back
        self.run_posted()
        self.assertEqual(self.app.video.played[-1][0], "http://plex/ok")

    def test_a_channel_with_nothing_left_to_play_waits_quietly(self):
        tl = lc.SCHEDULES[self.cid]
        for i in list(tl.entries):
            tl.drop(i["id"])
        self.assertIsNone(tl.at(datetime.now(timezone.utc)))
        live = LiveTV(self.app)
        live.tune(len(self.app.channels) - 1)                   # no recursion, no thread: the stand-by card
        self.assertTrue(live.standby)
        self.assertEqual(self.calls, [])


class TestMaker(Temp):
    def test_pages_build_and_values_read(self):
        from cathode import menus
        from types import SimpleNamespace
        app = FakeApp([])
        app.ondemand = SimpleNamespace(signed_in=False)
        app.config.video_channels = []
        self.assertFalse(menus.library_channel_items(app)[0].enabled)      # not linked: says so
        app.ondemand.signed_in = True
        app.library = index()
        app.listings, app.schedules, app.live = {}, {}, None
        app.config.library_channels = [chan("Comedy", "block_shuffle", {"kind": "genre", "value": "Comedy"}, starter=True)]
        app.channels = vc.add_to(lineup(1), app.config)
        lc.rebuild(app)
        cid = app.config.library_channels[0]["id"]
        pages = [menus.library_channel_items(app), menus.library_channel_page(app, cid),
                 menus.library_source_items(app, cid)]
        pages.append(pages[2][-1].submenu())                    # Add...: where
        pages.append(pages[3][0].submenu())                     # Every library: what kind
        pages.append(next(it for it in pages[4] if it.label == "A genre...").submenu())
        pages.append(next(it for it in pages[3] if it.label == "TV Shows").submenu())
        for items in pages:
            for it in items:
                self.assertTrue(it.label)
                if it.value:
                    self.assertIsInstance(it.value(), str)
        self.assertEqual([it.label for it in pages[0]],
                         ["Comedy", "Add a channel...", "Content groups", "Breaks during programmes", "Give every channel breaks", "Add the starter lineup", "Remove the starter lineup",
                          "Read the library again"])
        self.assertEqual(pages[0][0].value(), "101")
        self.assertEqual(pages[1][2].value(), "13 titles, 6 h")
        self.assertEqual((pages[1][3].value(), pages[1][4].value()), ("Block Shuffle", "2 episodes"))
        self.assertEqual(pages[2][0].label, "Everything: Comedy")
        self.assertEqual([(it.label, it.value()) for it in pages[5]][:2], [("Comedy", "3"), ("Action", "1")])
        self.assertIn("A show...", [it.label for it in pages[6]])
        movies = next(it for it in pages[3] if it.label == "Movies").submenu()
        self.assertNotIn("A show...", [it.label for it in movies])
        self.assertEqual(lc.source_label(app.library, {"section": "51", "kind": "show", "value": "200"}), "Bravo")
        self.assertFalse(menus.library_channel_page(app, "nope")[0].enabled)


if __name__ == "__main__":
    unittest.main()
