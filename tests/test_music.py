"""Music channels: placement, the day's timeline, the guide blocks, titles,
and tuning (the stream resolved off the thread, the card, a song ending)."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import musicchannels as music, ytdl
from cathode.config import Config
from cathode.epg import EPG
from cathode.playlist import Channel
from cathode.screens.live import LiveTV
from tests.test_own import FakeApp, FakeSkin, lineup   # noqa: F401  (the fake app, quiet)

ENTRIES = [{"id": f"v{i}", "title": f"Artist {i} - Song {i} (Official Video)", "duration": 180 + 30 * i,
            "uploader": f"artist{i}VEVO"} for i in range(6)]


class TestPlacement(unittest.TestCase):
    def test_after_everything_named_from_the_cache_or_not(self):
        cfg = Config("")
        cfg.music_playlists = ["https://www.youtube.com/playlist?list=PLone", "PLtwo"]
        chans = music.add_to(lineup(2, 4), cfg, names={"PLone": "'80s Hits | Vevo"})
        self.assertEqual([(c.number, c.name) for c in chans[2:]], [(5, "'80s Hits"), (6, "Music Videos")])
        self.assertTrue(music.is_music(chans[2]) and music.plid(chans[2]) == "PLone")
        self.assertEqual(chans[2].epg_id, "cathode.music.PLone")
        self.assertEqual([c.number for c in music.add_to(chans, cfg)], [2, 4, 5, 6])    # again: not doubled
        self.assertEqual(music.add_to([], cfg), [])


class TestSchedule(unittest.TestCase):
    def test_the_day_is_laid_out_from_midnight_and_repeats(self):
        s = music.Schedule("PL", ENTRIES)
        day = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        first = s.at(day.astimezone(timezone.utc) + timedelta(seconds=10))
        self.assertEqual(first["offset"], 10)
        self.assertEqual(first["start"], day.astimezone(timezone.utc))
        self.assertIn(first["entry"], ENTRIES)
        # the same moment again: the same song, the same offset
        self.assertEqual(s.at(day.astimezone(timezone.utc) + timedelta(seconds=10))["entry"], first["entry"])
        # one full cycle later: the same song again
        again = s.at(day.astimezone(timezone.utc) + timedelta(seconds=10 + s.total))
        self.assertEqual(again["entry"], first["entry"])
        # every moment of the day lands in a song, each after the one before
        t, seen = day.astimezone(timezone.utc), []
        while t < day.astimezone(timezone.utc) + timedelta(seconds=s.total):
            cur = s.at(t)
            self.assertTrue(cur["start"] <= t < cur["stop"])
            seen.append(cur["entry"]["id"])
            t = cur["stop"] + timedelta(seconds=0.1)
        self.assertEqual(sorted(seen), sorted(e["id"] for e in ENTRIES))

    def test_another_day_another_order_and_a_dropped_song_closes_up(self):
        s = music.Schedule("PL", ENTRIES)
        today = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        orders = []
        for d in range(4):
            start = (today + timedelta(days=d)).astimezone(timezone.utc)
            t, ids = start, []
            while len(ids) < len(ENTRIES):
                cur = s.at(t)
                ids.append(cur["entry"]["id"])
                t = cur["stop"] + timedelta(seconds=0.1)
            orders.append(ids)
        self.assertTrue(any(o != orders[0] for o in orders[1:]))
        s.drop("v3")
        self.assertEqual(len(s.entries), 5)
        self.assertNotEqual(s.at(today.astimezone(timezone.utc))["entry"]["id"], None)
        self.assertEqual(music.Schedule("PL", []).at(datetime.now(timezone.utc)), None)


class TestGuide(unittest.TestCase):
    def test_blocks_name_the_songs_starting_in_them(self):
        cfg = Config("")
        cfg.music_playlists = ["PLone"]
        chans = music.add_to(lineup(1), cfg, names={"PLone": "Hits"})
        epg = EPG()
        music.fill_guide(epg, chans, {"PLone": music.Schedule("PLone", ENTRIES)})
        now = datetime.now(timezone.utc)
        p = epg.current_program("cathode.music.PLone", now)
        self.assertEqual((p.title, p.category), ("Hits", "Music"))
        self.assertIn("Artist", p.description)
        self.assertEqual(len(epg._programs["cathode.music.PLone"]), 96)
        music.fill_guide(epg, chans, {})                 # not resolved yet: nothing written, nothing broken
        self.assertEqual(len(epg._programs["cathode.music.PLone"]), 96)


class TestTitles(unittest.TestCase):
    def test_artist_and_song(self):
        self.assertEqual(music.parse_title("a-ha - Take On Me (Official Video) [4K]", "ahaVEVO"), ("a-ha", "Take On Me"))
        self.assertEqual(music.parse_title("Never Gonna Give You Up", "RickAstleyVEVO"), ("RickAstley", "Never Gonna Give You Up"))
        self.assertEqual(music.parse_title("Lionel Richie - All Night Long (All Night)", ""), ("Lionel Richie", "All Night Long (All Night)"))
        self.assertEqual(music.parse_title("Journey - Don't Stop Believin' | Live 1981", ""), ("Journey", "Don't Stop Believin'"))
        self.assertEqual(music.clean_name("I Want My '80s Videos! | Vevo Playlist"), "I Want My '80s Videos!")
        self.assertEqual(ytdl.playlist_id("https://www.youtube.com/playlist?list=PLabc&si=x"), "PLabc")
        self.assertEqual(ytdl.playlist_url("PLabc"), "https://www.youtube.com/playlist?list=PLabc")


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
        self.app.config.music_playlists = ["PLone"]
        self.app.channels = music.add_to(lineup(1), self.app.config, names={"PLone": "Hits"})
        self.app.music = {"PLone": music.Schedule("PLone", ENTRIES)}
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
            self.assertIsNotNone(live.music)
            # the worker ran on a thread and posted; run what it posted
            for _ in range(50):
                if self.calls:
                    break
                time.sleep(0.02)
            fn, a, k = self.calls.pop(0)
            fn(*a, **k)
            url, audio, start = self.app.video.played[-1]
            cur = self.app.music["PLone"].at(datetime.now(timezone.utc))
            self.assertEqual((url, audio), (f"V/{cur['entry']['id']}", f"A/{cur['entry']['id']}"))
            self.assertAlmostEqual(start, cur["offset"], delta=2)
            self.assertEqual(live.card["artist"], cur["entry"]["title"].split(" - ")[0])
            # the song ends: the next due is resolved and played, no stand-by
            live.phase = "watch"
            live.on_video("video_ended", reason="eof")
            self.assertFalse(live.standby)
            for _ in range(50):
                if self.calls:
                    break
                time.sleep(0.02)
            self.assertTrue(self.calls)
            # tuning away stops it, the card goes
            live.tune(0)
            self.assertIsNone(live.music)
            self.assertIsNone(live.card)
        finally:
            ytdl.stream = ytdl_stream


if __name__ == "__main__":
    unittest.main()
