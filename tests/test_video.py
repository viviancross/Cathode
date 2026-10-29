"""Video channels: placement, the day's timeline (sampling, weighting, the
4 AM day), the guide (per video and in blocks), titles, migration, the
yt-dlp update guard, and tuning (resolve off the thread, card, a video
ending)."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import videochannels as vc, ytdl
from cathode.config import Config
from cathode.epg import EPG
from cathode.screens.live import LiveTV
from tests.test_own import FakeApp, lineup   # noqa: F401  (the fake app, quiet)


def songs(n, who="Artist"):
    return [{"id": f"{who[:2]}{i}", "title": f"{who} {i} - Song {i} (Official Video)", "duration": 180 + 10 * (i % 7),
             "uploader": f"{who}{i}VEVO"} for i in range(n)]


def episodes(n, who):
    return [{"id": f"{who[:3]}{i}", "title": f"Episode {i} - {who}", "duration": 900 + 60 * (i % 5), "uploader": who}
            for i in range(n)]


def chan(name="Mix", sources=("PLa", "@Bob"), **kw):
    c = vc.new_channel(name, sources)
    c.update(kw)
    return c


def listings(**kw):
    return {u: {"title": t, "fetched": 0, "entries": es} for u, (t, es) in kw.items()}


class TestConfig(unittest.TestCase):
    def test_a_fresh_config_has_the_prefill(self):
        cfg = Config("")
        self.assertEqual([len(c["sources"]) for c in cfg.video_channels], [1, 1, 1, 14])
        self.assertEqual((cfg.video_channels[3]["name"], cfg.video_channels[3]["max_seconds"]), ("bideogaymin", 14400))
        self.assertEqual(cfg.video_channels[0]["max_seconds"], 0)
        self.assertFalse(vc.migrate(cfg))                   # nothing to change

    def test_music_playlists_of_4_34_migrate(self):
        cfg = Config("")
        cfg.video_channels, cfg.music_playlists = [], ["PLx", "PLy"]
        self.assertTrue(vc.migrate(cfg))
        self.assertEqual([c["sources"][0]["url"] for c in cfg.video_channels[:2]], ["PLx", "PLy"])
        self.assertEqual(cfg.video_channels[2]["name"], "bideogaymin")
        self.assertEqual(cfg.music_playlists, [])
        self.assertEqual(cfg.video_channels[0]["weighting"], "auto")


class TestPlacement(unittest.TestCase):
    def test_after_everything_or_at_a_chosen_number(self):
        cfg = Config("")
        cfg.video_channels = [chan("Mix"), chan("Picked", number=3), chan("", sources=("PLz",))]
        chans = vc.add_to(lineup(2, 4), cfg, names={cfg.video_channels[2]["id"]: "From Source"})
        self.assertEqual([(c.number, c.name) for c in chans], [(2, "Ch2"), (3, "Picked"), (4, "Ch4"), (5, "Mix"), (6, "From Source")])
        self.assertTrue(vc.is_video(chans[1]) and chans[1].epg_id == "cathode.video." + cfg.video_channels[1]["id"])
        self.assertEqual([c.number for c in vc.add_to(chans, cfg)], [2, 3, 4, 5, 6])    # again: not doubled
        self.assertEqual(vc.add_to([], cfg), [])


class TestSchedule(unittest.TestCase):
    def test_the_day_runs_from_4am_and_every_moment_is_in_a_video(self):
        c = chan()
        s = vc.Schedule(c, listings(PLa=("Hits", songs(6)), **{"@Bob": ("Bob", episodes(4, "Bob"))}))
        now = datetime.now(timezone.utc)
        day, start = s.day_of(now.astimezone())
        self.assertEqual(start.hour, 4)
        first = s.at(start.astimezone(timezone.utc) + timedelta(seconds=10))
        self.assertEqual(first["offset"], 10)
        self.assertEqual(first["start"], start.astimezone(timezone.utc))
        t, seen = start.astimezone(timezone.utc), []
        while t < start.astimezone(timezone.utc) + timedelta(seconds=s.total):
            cur = s.at(t)
            self.assertTrue(cur["start"] <= t < cur["stop"])
            seen.append(cur["entry"]["id"])
            t = cur["stop"] + timedelta(seconds=0.1)
        self.assertEqual(len(seen), 10)                     # every video once a cycle
        self.assertEqual(s.at(t + timedelta(seconds=s.total))["entry"], s.at(t)["entry"])    # repeats
        # 3:59 belongs to the day before
        early = start.replace(hour=3, minute=59)
        self.assertEqual(s.day_of(early)[0], (start - timedelta(days=1)).date())

    def test_weighting_shares_the_airtime(self):
        big, small = songs(200, "Big"), songs(10, "Small")
        lst = listings(PLa=("Big", big), **{"@Bob": ("Small", small)})

        def share(mode, weights=(1, 1)):
            c = chan(weighting=mode)
            for src, w in zip(c["sources"], weights):
                src["weight"] = w
            order, _ = vc.Schedule(c, lst)._for(datetime.now().date())
            small_t = sum(e["duration"] for e in order if e["id"].startswith("Sm"))
            return small_t / sum(e["duration"] for e in order)
        self.assertAlmostEqual(share("equal"), 0.5, delta=0.05)
        auto = share("auto")
        self.assertGreaterEqual(auto, 0.045)                # the floor: not drowned
        self.assertLess(auto, 0.2)
        self.assertAlmostEqual(share("manual", (1, 3)), 0.75, delta=0.06)

    def test_sampling_filters_and_dropping(self):
        many = songs(700, "Many")
        many[0]["duration"] = 30                            # too short
        many[1]["short"] = True                             # a Short
        many[2]["live"] = True                              # a stream's recording
        many[3]["duration"] = 20000                         # a day-long upload
        s = vc.Schedule(chan(sources=("PLa",)), listings(PLa=("Many", many)))
        order, _ = s._for(datetime.now().date())
        self.assertEqual(len(order), vc.SAMPLE)
        self.assertEqual(len(set(e["id"] for e in order)), vc.SAMPLE)
        self.assertNotIn("Ma0", [e["id"] for e in order])
        self.assertNotIn("Ma1", [e["id"] for e in order])
        self.assertNotIn("Ma2", [e["id"] for e in order])
        self.assertIn("Ma3", [e["id"] for e in s.entries])  # any length, by default
        capped = vc.Schedule(chan(sources=("PLa",), max_seconds=14400), listings(PLa=("Many", many)))
        self.assertNotIn("Ma3", [e["id"] for e in capped.entries])
        # live streams back in: the streams tab's entries join the videos'
        both = vc.Schedule(chan(sources=("@Bob",), skip_live=False),
                           listings(**{"@Bob": ("Bob", episodes(3, "Bob")),
                                       "@Bob#live": ("Bob", [dict(e, id="L" + e["id"], live=True) for e in episodes(2, "Bob")])}))
        self.assertEqual(len(both.entries), 5)
        self.assertEqual(ytdl.source_url("@Bob#live"), "https://www.youtube.com/@Bob/streams")
        other, _ = s._for(datetime.now().date() + timedelta(days=1))
        self.assertNotEqual([e["id"] for e in order], [e["id"] for e in other])     # another day, another sample
        s.drop(order[0]["id"])
        self.assertNotIn(order[0]["id"], [e["id"] for e in s._for(datetime.now().date())[0]])
        self.assertIsNone(vc.Schedule(chan(sources=("PLa",)), {}).at(datetime.now(timezone.utc)))
        loose = vc.Schedule(chan(sources=("PLa",), min_seconds=0, skip_shorts=False, skip_live=False), listings(PLa=("Many", many)))
        self.assertEqual(len(loose.entries), 700)

    def test_a_source_in_order_or_shuffled_and_a_refresh(self):
        eps = episodes(5, "Bob")
        day = datetime.now().date()

        def ids(c):
            return [e["id"] for e in vc.Schedule(c, listings(**{"@Bob": ("Bob", eps)}))._for(day)[0]]
        c = chan(sources=("@Bob",))
        c["sources"][0].update(shuffle=False)
        self.assertEqual(ids(c), ["Bob0", "Bob1", "Bob2", "Bob3", "Bob4"])          # as listed
        c["sources"][0].update(order="reversed")
        self.assertEqual(ids(c), ["Bob4", "Bob3", "Bob2", "Bob1", "Bob0"])
        c["sources"][0].update(order="title")
        self.assertEqual(ids(c), ["Bob0", "Bob1", "Bob2", "Bob3", "Bob4"])          # "Episode 0 - Bob" ...
        c["sources"][0].update(shuffle=True)
        shuffled = ids(c)
        self.assertEqual(sorted(shuffled), sorted(["Bob0", "Bob1", "Bob2", "Bob3", "Bob4"]))
        self.assertEqual(ids(c), shuffled)                                         # the same all day
        c["seed"] = 12345                                                          # a refresh: drawn again
        self.assertNotEqual(ids(c), shuffled)
        # a big list's daily sample keeps the list's order when it isn't shuffled
        many = songs(700, "Many")
        c2 = chan(sources=("PLa",))
        c2["sources"][0].update(shuffle=False)
        order = [e["id"] for e in vc.Schedule(c2, listings(PLa=("Many", many)))._for(day)[0]]
        self.assertEqual(len(order), vc.SAMPLE)
        pos = {e["id"]: i for i, e in enumerate(many)}
        self.assertEqual(order, sorted(order, key=pos.get))


class TestGuide(unittest.TestCase):
    def test_episodes_get_their_own_programmes_and_songs_get_blocks(self):
        cfg = Config("")
        cfg.video_channels = [chan("Shows", sources=("@Bob",)), chan("Hits", sources=("PLa",))]
        chans = vc.add_to(lineup(1), cfg)
        lst = listings(PLa=("Hits", songs(30)), **{"@Bob": ("Bob", episodes(40, "Bob"))})
        scheds = {c["id"]: vc.Schedule(c, lst) for c in cfg.video_channels}
        epg = EPG()
        vc.fill_guide(epg, chans, scheds, cfg)
        now = datetime.now(timezone.utc)
        shows, hits = chans[1], chans[2]
        p = epg.current_program(shows.epg_id, now)
        self.assertTrue(p.title.startswith("Episode"))
        self.assertIn("From Bob, ", p.description)
        self.assertLess((p.stop - p.start).total_seconds(), 1300)
        q = epg.current_program(hits.epg_id, now)
        self.assertEqual((q.title, (q.stop - q.start).total_seconds()), ("Hits", 1800))
        self.assertIn("Artist", q.description)
        cfg.video_channels[0]["guide"] = "blocks"
        vc.fill_guide(epg, chans, scheds, cfg)
        self.assertEqual((epg.current_program(shows.epg_id, now).stop - epg.current_program(shows.epg_id, now).start).total_seconds(), 1800)


class TestTitles(unittest.TestCase):
    def test_artist_and_song_or_uploader_and_title(self):
        self.assertEqual(vc.parse_title("a-ha - Take On Me (Official Video) [4K]", "ahaVEVO"), ("a-ha", "Take On Me"))
        self.assertEqual(vc.parse_title("Game Boy Camera - Scott The Woz", "Scott The Woz"), ("Scott The Woz", "Game Boy Camera"))
        self.assertEqual(vc.parse_title("The Big Rigs Retrospective", "Caddicarus"), ("Caddicarus", "The Big Rigs Retrospective"))
        self.assertEqual(vc.parse_title("Lionel Richie - All Night Long (All Night)", ""), ("Lionel Richie", "All Night Long (All Night)"))
        self.assertEqual(vc.clean_name("I Want My '80s Videos! | Vevo Playlist"), "I Want My '80s Videos!")
        self.assertEqual(vc.clean_name("Scott The Woz - Videos"), "Scott The Woz")
        self.assertEqual(ytdl.source_url("@LGR"), "https://www.youtube.com/@LGR/videos")
        self.assertEqual(ytdl.source_url("https://www.youtube.com/@LGR"), "https://www.youtube.com/@LGR/videos")
        self.assertEqual(ytdl.source_url("PLabc"), "https://www.youtube.com/playlist?list=PLabc")
        self.assertEqual(ytdl.source_key("https://www.youtube.com/playlist?list=PLabc&si=x"), "PLabc")


class TestUpdate(unittest.TestCase):
    """The yt-dlp fetch: a bad download never replaces anything; a good one
    lands as the zip imported at the next start."""

    def test_bad_then_good(self):
        import tempfile, zipfile
        keep = (ytdl.cache_dir, ytdl.latest_version, ytdl.ZIPAPP, ytdl.version)
        tmp = tempfile.mkdtemp()
        try:
            ytdl.cache_dir = lambda: tmp
            ytdl.latest_version = lambda: "9999.01.01"
            ytdl.version = lambda: "2026.10.26"
            bad = os.path.join(tmp, "bad.bin")
            with open(bad, "wb") as f:
                f.write(b"<html>not a zip</html>")
            ytdl.ZIPAPP = "file:///" + bad.replace("\\", "/")
            with self.assertRaises(Exception):
                ytdl.update()
            self.assertFalse(os.path.exists(os.path.join(tmp, "yt-dlp.zip")))
            good = os.path.join(tmp, "good.zip")
            with zipfile.ZipFile(good, "w") as z:
                z.writestr("yt_dlp/version.py", "__version__ = '9999.01.01'" + chr(10))
            ytdl.ZIPAPP = "file:///" + good.replace("\\", "/")
            self.assertEqual(ytdl.update(), "9999.01.01")
            self.assertTrue(os.path.exists(os.path.join(tmp, "yt-dlp.zip")))
            ytdl.latest_version = lambda: "2026.10.26"
            self.assertIsNone(ytdl.update())            # already current: nothing fetched
        finally:
            ytdl.cache_dir, ytdl.latest_version, ytdl.ZIPAPP, ytdl.version = keep


class TestMaker(unittest.TestCase):
    """Settings > Channels > Video Channels: every page builds and every
    value reads, before and after the sources are known."""

    def test_pages_build_and_values_read(self):
        from cathode import menus
        app = FakeApp([])
        app.config.video_channels = [chan("Mix"), chan("", sources=("PLz",))]
        app.channels = vc.add_to(lineup(1), app.config)
        app.listings, app.schedules = {}, {}
        app.live = None
        for lst in ({}, listings(PLa=("Hits", songs(5)), **{"@Bob": ("Bob", episodes(3, "Bob"))})):
            app.listings = lst
            vc.rebuild(app)
            pages = [menus.video_channel_items(app)]
            cid = app.config.video_channels[0]["id"]
            pages.append(menus.video_channel_page(app, cid))
            pages.append(menus.video_source_items(app, cid))
            pages.append(menus.video_source_page(app, cid, 0))
            pages.append(menus.video_source_page(app, cid, 1))
            for items in pages:
                for it in items:
                    self.assertTrue(it.label)
                    if it.value:
                        self.assertIsInstance(it.value(), str)
            self.assertEqual([it.label for it in pages[0]][:2], ["Mix", "Video Channel"])
        self.assertEqual([it.label for it in pages[2]][:2], ["Hits", "Bob"])
        self.assertEqual(pages[1][2].value(), "2")              # Sources: 2
        self.assertEqual(menus.video_channel_page(app, "nope")[0].enabled, False)
        self.assertEqual(menus.video_source_page(app, cid, 9)[0].enabled, False)


class TestQuality(unittest.TestCase):
    def test_the_format_follows_the_cap(self):
        self.assertIn("[height<=720][vcodec^=avc1]", ytdl.fmt(720))
        self.assertTrue(ytdl.fmt(480).endswith("/best[height<=480]/best"))
        old = ytdl.MAX_HEIGHT
        try:
            ytdl.MAX_HEIGHT = 360
            self.assertIn("height<=360", ytdl.fmt())
        finally:
            ytdl.MAX_HEIGHT = old


class FakeVideo2:
    def __init__(self):
        self.played, self.stopped = [], 0

    def play(self, url, headers=None, start=0, sub_delay=0.0, audio=None):
        self.played.append((url, audio, round(start)))

    def stop(self):
        self.stopped += 1


class TestTuning(unittest.TestCase):
    def setUp(self):
        self.app = FakeApp([])
        self.app.video = FakeVideo2()
        self.app.config.video_channels = [chan("Mix")]
        self.cid = self.app.config.video_channels[0]["id"]
        self.app.channels = vc.add_to(lineup(1), self.app.config)
        self.app.listings = listings(PLa=("Hits", songs(6)), **{"@Bob": ("Bob", episodes(4, "Bob"))})
        self.app.schedules = {self.cid: vc.Schedule(self.app.config.video_channels[0], self.app.listings)}
        self.calls = []
        self.app.post = lambda fn, *a, **k: self.calls.append((fn, a, k))      # threads' results, held

    def test_tune_resolves_then_plays_from_the_offset_with_the_card(self):
        import time
        resolved = {}
        ytdl_stream = ytdl.stream
        ytdl.stream = lambda vid: resolved.setdefault(vid, {"video": f"V/{vid}", "audio": f"A/{vid}", "headers": {}, "expires": time.time() + 3600})
        try:
            live = LiveTV(self.app)
            live.tune(1)
            self.assertIsNotNone(live.vplayer)
            for _ in range(50):                 # the worker ran on a thread and posted; run what it posted
                if self.calls:
                    break
                time.sleep(0.02)
            fn, a, k = self.calls.pop(0)
            fn(*a, **k)
            url, audio, start = self.app.video.played[-1]
            cur = self.app.schedules[self.cid].at(datetime.now(timezone.utc))
            self.assertEqual((url, audio), (f"V/{cur['entry']['id']}", f"A/{cur['entry']['id']}"))
            self.assertAlmostEqual(start, 0 if cur["offset"] < vc.GRACE else cur["offset"], delta=2)
            left = (cur["stop"] - datetime.now(timezone.utc)).total_seconds()
            self.assertTrue(any(abs(t[0] - left) < 2 and not t[3] for t in self.app.timers), "the next is due at the stop")
            self.assertTrue(live.card["song"])
            live.phase = "watch"
            live.on_video("video_ended", reason="eof")      # the video ends: the next due, no stand-by
            self.assertFalse(live.standby)
            for _ in range(50):
                if self.calls:
                    break
                time.sleep(0.02)
            self.assertTrue(self.calls)
            live.tune(0)                                    # away: stopped, the card gone
            self.assertIsNone(live.vplayer)
            self.assertIsNone(live.card)
        finally:
            ytdl.stream = ytdl_stream

    def test_after_a_video_ends_the_next_plays_from_its_top_however_late(self):
        import time
        ytdl_stream = ytdl.stream
        ytdl.stream = lambda vid: {"video": f"V/{vid}", "audio": f"A/{vid}", "headers": {}, "expires": time.time() + 3600}
        real_dt = vc.datetime
        try:
            live = LiveTV(self.app)
            live.tune(1)
            for _ in range(50):
                if self.calls:
                    break
                time.sleep(0.02)
            fn, a, k = self.calls.pop(0)
            fn(*a, **k)
            p = live.vplayer
            nxt = self.app.schedules[self.cid].at(p.cur["stop"] + timedelta(seconds=1))
            late = nxt["start"] + timedelta(seconds=vc.GRACE + 40)   # the stream ran a minute past the handover

            class Late(real_dt):
                @classmethod
                def now(cls, tz=None):
                    return late if tz else late.replace(tzinfo=None)
            vc.datetime = Late
            live.phase = "watch"
            live.on_video("video_ended", reason="eof")
            for _ in range(50):
                if self.calls:
                    break
                time.sleep(0.02)
            fn, a, k = self.calls.pop(0)
            fn(*a, **k)
            url, audio, start = self.app.video.played[-1]
            self.assertEqual(url, f"V/{nxt['entry']['id']}", "the one after it")
            self.assertEqual(start, 0, "from its top, not a minute in")
            live.tune(0)
        finally:
            ytdl.stream = ytdl_stream
            vc.datetime = real_dt


if __name__ == "__main__":
    unittest.main()
