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
        tl.at(datetime.now(timezone.utc) + timedelta(days=30))
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
        pushed = []
        app.push = pushed.append
        ch = app.channels[-1]
        start = datetime.now(timezone.utc)
        prog = type("P", (), {"start": start})()
        menus.open_guide_options(app, ch, prog)
        rows = {it.label: it for it in pushed[-1].items}
        self.assertIn("Browse this channel", rows)
        self.assertTrue(rows["Browse this channel"].submenu())
        add = next(it for k, it in rows.items() if k.startswith("Add "))
        add.submenu()[0].action()                               # onto Comedy
        self.assertEqual(len(a["sources"]), 2)
        menus.move_channel(app, app.channels[-1], -1)            # Drama up past Comedy
        self.assertEqual(len(app.config.channel_edits), 2)


class TestScheduling(Temp):
    def test_a_pinned_show_starts_on_the_minute(self):
        idx = index()
        c = chan("A", "random", pins=[{"at": "20:00", "days": None, "src": {"kind": "show", "value": "300"}}])
        tl = tl_of(c, idx)
        got = slots(tl, 48)
        eights = [x for t, x in got if datetime.fromtimestamp(t).strftime("%H:%M") == "20:00"]
        self.assertTrue(eights)
        self.assertTrue(all(idx.item(x)["show_key"] == "300" for x in eights))

    def test_title_weights_and_count_balance(self):
        idx = index()
        tl = tl_of(chan("A", "random", title_weights={"m901": 0, "m902": 0, "m903": 0}), idx)
        self.assertFalse(any(idx.item(x)["type"] == "movie" for _t, x in slots(tl, 48)))
        tl = tl_of(chan("A", "mix", {"kind": "show", "value": "100"}, {"section": "38", "kind": "all"},
                        balance="count"), idx)
        got = [idx.item(x)["type"] for _t, x in slots(tl, 72)]
        self.assertGreater(got.count("episode"), got.count("movie"))

    def test_premieres_back_to_back_with_a_pre_roll(self):
        idx = index()
        for i in idx.sections["51"].items:
            i["added"] = int(datetime.now().timestamp())
        c = chan("A", "random", premieres="prime", premiere_count=2, premiere_times=[21], premiere_preroll="10")
        tl = tl_of(c, idx)
        tl.at(datetime.now(timezone.utc) + timedelta(hours=30))
        prem = [k for k, s in enumerate(tl._slots) if len(s) > 3 and s[3].get("premiere")]
        self.assertGreaterEqual(len(prem), 2)
        first = tl._slots[prem[0]]
        self.assertGreaterEqual(datetime.fromtimestamp(first[0]).hour, 21)
        self.assertEqual(tl._slots[prem[0] - 1][3].get("brk"), "bump")      # the pre-roll

    def test_holiday_titles_only_in_season(self):
        idx = index()
        for i in idx.sections["51"].items:
            if i["show_key"] == "200":
                i["name"] = "A Very Bravo Christmas" if i["episode"] == 1 else "Halloween Spooktacular" if i["episode"] == 2                     else i["name"]
        self.assertEqual(lc.holiday({"type": "episode", "title": "X", "name": "Treehouse of Horror V"}), "Halloween")
        tl = tl_of(chan("A", "random"), idx)
        lt = datetime.now()
        got = {x for _t, x in slots(tl, 48)}
        for x, h in (("p200101", "Christmas"), ("p200102", "Halloween")):
            if not lc.in_season(h, lt):
                self.assertNotIn(x, got)

    def test_the_pages(self):
        from types import SimpleNamespace
        from cathode import menus
        idx = index()
        c = chan("A", "random")
        lc.SCHEDULES[lc.PREFIX + c["id"]] = tl_of(c, idx)
        app = SimpleNamespace(library=idx, toast=lambda *a: None, push=lambda k: None)
        save = lambda place=True: None       # noqa: E731
        for items in (menus.premiere_items(app, c, save), menus.pin_items(app, c, save),
                      menus.weight_items(app, c, save), menus.running_order_items(app, lc.PREFIX + c["id"])):
            for it in items:
                if it.value:
                    self.assertIsInstance(it.value(), str)
        w = menus.weight_items(app, c, save)
        w[0].adjust(1)
        self.assertEqual(c["title_weights"], {"s100": 2})
        self.assertTrue(any(it.label.startswith("   Break") or it.label.startswith("--")
                            for it in menus.running_order_items(app, lc.PREFIX + c["id"])))


def with_ads(idx):
    long = library.Section("70", "Old Ads Show", "show", "s1")
    long.add_show({"ratingKey": "7", "title": "Old Ads", "year": 1990})
    for e in range(1, 3):
        long.add_item({"type": "episode", "ratingKey": f"70{e}", "grandparentRatingKey": "7", "grandparentTitle": "Old Ads",
                       "parentIndex": 1, "index": e, "title": f"Reel {e}", "duration": 1800000})
    ads = library.Section("11", "Classic Commercials", "clip", "s1")
    for n in range(6):
        ads.add_item({"type": "movie", "ratingKey": f"6{n}", "title": f"Ad {n}", "duration": 30000})
    idx.sections.update({"70": long, "11": ads})
    idx._by_id = None
    return idx


class TestBreaks(Temp):
    def brk_tl(self, **brk):
        idx = with_ads(index())
        b = {"ads": [{"section": "11", "kind": "all"}], "bumps": [{"section": "10", "kind": "all"}], "pad": 30,
             "mid": "off", "length": 120}
        b.update(brk)
        c = chan("A", "random", {"kind": "show", "value": "100"}, {"kind": "show", "value": "200"}, breaks=b)
        return lc.Timeline(c, idx, store=False), idx

    def breaks(self, tl):
        tl.at(datetime.now(timezone.utc) + timedelta(hours=8))
        out, cur = [], []
        for s in tl._slots:
            if len(s) > 3 and s[3].get("brk"):
                cur.append(s)
            elif cur:
                out.append(cur)
                cur = []
        return out

    def test_so_many_commercials_and_the_next_card(self):
        tl, _idx = self.brk_tl(count=2, next_card=True)
        for b in self.breaks(tl)[:5]:
            self.assertEqual(sum(1 for s in b if s[3]["brk"] == "ad"), 2)
            self.assertEqual(b[-1][1], lc.NEXT)
        k = next(n for n, s in enumerate(tl._slots) if s[1] == lc.NEXT)
        e = tl.at(datetime.fromtimestamp(tl._slots[k][0] + 1, timezone.utc))["entry"]
        self.assertEqual((e["style"], e["kind"]), ("next", "brb"))
        self.assertIn(e["next"]["title"], ("Alpha", "Bravo"))

    def test_idents_in_order_and_pieces_of_a_long_video(self):
        tl, idx = self.brk_tl(idents=[{"section": "10", "kind": "all"}], ad_order="in_order")
        bs = self.breaks(tl)
        self.assertTrue(all(b[0][3]["brk"] == "bump" for b in bs))
        ads = [s[1] for b in bs for s in b if s[3]["brk"] == "ad"]
        self.assertEqual(ads[:6], [f"p6{n}" for n in range(6)])
        tl, idx = self.brk_tl(ads=[{"section": "70", "kind": "all", "chunks": True}])
        pieces = [s for b in self.breaks(tl) for s in b if s[3]["brk"] == "ad"]
        self.assertTrue(pieces and all(s[1] in ("p701", "p702") and 20 <= s[2] <= 90 and "in" in s[3] for s in pieces))

    def test_mid_breaks_every_ten_minutes_and_at_quiet_moments(self):
        from cathode import marks
        tl, idx = self.brk_tl(mid="every10")
        parts = [s for s in tl._slots if len(s) > 3 and s[3].get("part")]
        tl.at(datetime.now(timezone.utc) + timedelta(hours=4))
        parts = [s for s in tl._slots if len(s) > 3 and s[3].get("part")]
        self.assertTrue(parts and all(s[3]["in"] in (600.0, 1200.0) for s in parts))
        marks._cache = {"chapters": {}, "silences": {"100101": [[272.7, 2.5], [745.0, 2.0], [800.0, 0.6], [5, 3]]}}
        try:
            self.assertEqual(marks.cuts(idx.item("p100101"), "silences"), [272.7, 745.0])
            self.assertIsNone(marks.cuts(idx.item("p100102"), "silences"))
        finally:
            marks._cache = None

    def test_a_day_with_a_slate_is_kept_on_disk(self):
        idx = index()
        c = chan("A", "random", breaks={"ads": [], "bumps": [{"section": "10", "kind": "all"}], "pad": 30})
        tl = lc.Timeline(c, idx)
        tl.at(datetime.now(timezone.utc))
        self.assertTrue(any(s[1] == lc.BRB for s in tl._slots))
        again = lc.Timeline(c, idx)
        self.assertEqual(again.days[0]["slots"], tl.days[0]["slots"])


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


class TestOnScreen(unittest.TestCase):
    def test_overlays_draw_in_every_skin(self):
        import time as _t
        import pygame
        from tests.test_skins import FakeApp
        from cathode.skins import skin_classes, overlays
        from cathode.screens.guide import Guide
        from datetime import date
        self.assertEqual(overlays.season(date(2026, 12, 20)), "snow")
        self.assertEqual(overlays.season(date(2027, 1, 3)), "snow")
        self.assertEqual(overlays.season(date(2026, 5, 3)), "")
        for name, cls in skin_classes().items():
            app = FakeApp()
            skin = cls(app)
            app.skin = skin
            live = app.live
            live.idx, live.phase, live.message = 1, "watch", None
            app.top = lambda: live
            live.rating = {"text": "TV-14", "until": _t.monotonic() + 9}
            live.upnext = {"title": "Rugrats", "at": datetime.now(timezone.utc) + timedelta(seconds=20)}
            c = pygame.Surface(skin.canvas, pygame.SRCALPHA)
            for bez in ("off", "wood", "black", "silver"):
                app.config.bezel = bez
                skin.draw(c, live)
                overlays.draw_bezel(skin, c)
            app.config.tune_screen = "logo"
            live.phase = "cover"
            skin.draw(c, live)
            self.assertEqual(live.cover()[0], "black")
            skin.draw(c, Guide(app))
            skin.draw_signoff(c, {"name": "N", "back": datetime.now(timezone.utc), "style": "next",
                                  "next": {"title": "Doug", "episode": "S1E1 - Pilot"}})

    def test_logo_modes(self):
        import time as _t
        from types import SimpleNamespace as NS
        from cathode.skins import overlays
        cfg = NS(bug_mode="change")
        skin = NS(app=NS(config=cfg, after=lambda *a: None, invalidate=lambda: None))
        live = NS(tuned_at=_t.monotonic(), prog_at=0.0)
        self.assertTrue(overlays.bug_shown(skin, live))
        live.tuned_at = _t.monotonic() - 60
        self.assertFalse(overlays.bug_shown(skin, live))
        cfg.bug_mode = "always"
        self.assertTrue(overlays.bug_shown(skin, live))


class TestPlayback(unittest.TestCase):
    def test_preferred_version(self):
        from cathode.plex import _pick_media
        meta = {"Media": [{"videoResolution": "720", "bitrate": 3000, "Part": [{"key": "/a", "size": 9}]},
                          {"videoResolution": "1080", "bitrate": 8000, "Part": [{"key": "/b", "size": 20}]},
                          {"videoResolution": "sd", "bitrate": 900, "Part": [{"key": "/c", "size": 3}]}]}
        self.assertEqual(_pick_media(meta, "first")[0], 0)
        self.assertEqual(_pick_media(meta, "best")[0], 1)
        self.assertEqual(_pick_media(meta, "smallest")[0], 2)

    def test_mpv_conf(self):
        import tempfile
        from unittest import mock
        from cathode import app as appmod
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "mpv.conf"), "w") as f:
            f.write("# mine\nvolume-max=150\n--deband\n[profile]\n")
        with mock.patch("cathode.paths.config_path", lambda: os.path.join(d, "config.json")):
            self.assertEqual(appmod._mpv_conf(), {"volume_max": "150", "deband": "yes"})

    def test_watched_in_plex_after_most_of_it(self):
        from types import SimpleNamespace as NS
        from cathode import videochannels as vc
        calls = []
        client = NS(report_timeline=lambda *a: calls.append(("t",) + a), scrobble=lambda rk: calls.append(("s", rk)))
        app = NS(config=NS(plex_scrobble=True), ondemand=NS(signed_in=True, client=lambda: client),
                 video=NS(paused=False), after=lambda *a: None)
        p = vc.Player.__new__(vc.Player)
        p.app, p._watch = app, None
        e = {"plex": "55", "kind": "show", "duration": 1000.0}
        import threading as th
        real = th.Thread
        th.Thread = lambda target, daemon=True: NS(start=target)
        try:
            p._watching(e, 0.0)
            p._watch["t0"] -= 950                      # 950 s of it seen
            p._watching({"kind": "ad"}, 0.0)           # a break
            p._watching(dict(e, **{"in": 950.0}), 0.0)
            p._watch["t0"] -= 40
            p._watch_done(p._watch)
        finally:
            th.Thread = real
        self.assertIn(("s", "55"), calls)
        self.assertTrue(any(c[0] == "t" and c[-1] == "stopped" for c in calls))


class TestSpecialChannels(Temp):
    def test_radar_tiles_and_alerts(self):
        from cathode import radar
        x, y = radar.tile_of(0.0, 0.0, 6)
        self.assertEqual((x, y), (32.0, 32.0))
        a = radar.parse({"event": "Tornado Warning", "headline": "Tornado Warning until 5 PM", "severity": "Extreme"})
        self.assertEqual((a["event"], a["severity"]), ("Tornado Warning", "Extreme"))

    def test_whole_albums(self):
        music = library.Section("80", "Music", "music", "s1")
        music.add_show({"ratingKey": "a1", "title": "Band"})
        for n, alb in enumerate(["One"] * 3 + ["Two"] * 2):
            music.add_item({"type": "track", "ratingKey": f"t{n}", "grandparentRatingKey": "a1", "grandparentTitle": "Band",
                            "parentTitle": alb, "title": f"Song {n}", "index": n + 1, "duration": 200000})
        idx = library.Index([music])
        c = chan("Radio", "album", {"section": "80", "kind": "all", "only": "music"}, breaks={})
        gs = lc.groups(c, idx)
        self.assertEqual(sorted(len(g["items"]) for g in gs), [2, 3])
        tl = lc.Timeline(c, idx, store=False)
        order = [idx.item(x)["album"] for _t, x in slots(tl, 1)][:5]
        self.assertTrue(order[:3] == ["One"] * 3 or order[:2] == ["Two"] * 2)

    def test_the_store_and_a_locked_channel(self):
        from types import SimpleNamespace as NS
        from cathode import menus
        from cathode.playlist import Channel
        idx = index()
        pushed = []
        app = NS(library=idx, push=pushed.append, toast=lambda *a: None, config=NS(parent_pin="", channel_edits={}))
        menus.open_store(app)
        rows = {it.label: it for it in pushed[-1].items}
        self.assertIn("New Releases", rows)
        self.assertTrue(rows["Action"].submenu())
        menus._lock(app, "u1")
        self.assertEqual(app.config.channel_edits, {})          # no PIN: not locked
        app.config.parent_pin = "1234"
        app.config.save = lambda: None
        app.live = None
        menus._lock(app, "u1")
        self.assertTrue(app.config.channel_edits["u1"]["locked"])
