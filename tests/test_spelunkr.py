"""Spelunkr: the shipped playlist entry, and a channel's timeline from its
version's epoch and first file (no network)."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cathode import spelunkr  # noqa: E402


def man(items, bumps=None):
    return {"engine": 5, "items": items, "bumps": bumps or []}


def tl(start_index=1, epoch=0):
    items = [{"id": f"f{k}", "file": f"f{k}.mp4", "duration": d, "title": f"Show {k}"} for k, d in enumerate((100, 200, 300))]
    return spelunkr.Timeline("spelunkr.t", {"v": 1, "epochMs": epoch, "effectiveAtMs": epoch, "startIndex": start_index},
                             man(items), None, [], spelunkr.AUDIO)


class TestSpelunkr(unittest.TestCase):
    def test_shipped_once_and_a_deleted_one_stays_deleted(self):
        cfg = NS(playlists=[{"name": "Mine", "playlist_url": "http://x"}], spelunkr_shipped=False)
        self.assertTrue(spelunkr.ship(cfg))
        self.assertEqual([p["playlist_url"] for p in cfg.playlists], ["http://x", spelunkr.URL])
        cfg.playlists.pop()
        self.assertFalse(spelunkr.ship(cfg))
        self.assertEqual(len(cfg.playlists), 1)

    def test_the_timeline_starts_at_the_first_file_on_the_epoch_and_wraps(self):
        epoch = datetime(2026, 11, 1, tzinfo=timezone.utc)
        e0 = int(epoch.timestamp() * 1000)
        s = spelunkr.Schedule("spelunkr.t", "T", [tl(1, e0)], "X")
        cur = s.at(epoch + timedelta(seconds=50))
        self.assertEqual((cur["entry"]["id"], round(cur["offset"])), ("f1/f1.mp4", 50))   # cycle 0 from file 1
        self.assertEqual(s.at(epoch + timedelta(seconds=250))["entry"]["id"], "f2/f2.mp4")
        self.assertEqual(s.at(epoch + timedelta(seconds=550))["entry"]["id"], "f0/f0.mp4")  # cycle 1: every file
        again = s.at(epoch + timedelta(seconds=500 + 600 + 100 + 50))                       # a whole cycle later, the same
        self.assertEqual((again["entry"]["id"], round(again["offset"])), ("f1/f1.mp4", 50))
        self.assertEqual(again["stop"] - again["start"], timedelta(seconds=200))

    def test_a_newer_version_takes_over_at_its_moment(self):
        e0 = 1_800_000_000_000
        old, new = tl(0, e0), tl(2, e0 + 30_000)
        new.v = 2
        s = spelunkr.Schedule("spelunkr.t", "T", [old, new], "X")
        before = s.at(datetime.fromtimestamp((e0 + 10_000) / 1000, timezone.utc))
        self.assertEqual(before["entry"]["id"], "f0/f0.mp4")
        self.assertEqual(before["stop"].timestamp() * 1000, e0 + 30_000)                # cut where v2 starts
        self.assertEqual(s.at(datetime.fromtimestamp((e0 + 31_000) / 1000, timezone.utc))["entry"]["id"], "f2/f2.mp4")

    def test_bumpers_sit_between_shows_for_their_slides_time(self):
        items = [{"id": "a", "file": "a.mp4", "duration": 60, "title": "A"}, {"id": "b", "file": "b.mp4", "duration": 60, "title": "B"}]
        bump = {"id": "x", "slides": [{"text": "hi"}]}
        t = spelunkr.Timeline("spelunkr.t", {"v": 1, "epochMs": 0, "startIndex": 0}, man(items, [bump]),
                              {"bumps": [{"id": "p", "slides": [{"text": "yo"}]}]}, [], spelunkr.AUDIO)
        kinds = [e["type"] for e in t.cycle(0)[2]]
        self.assertEqual(kinds, ["video", "bump", "video", "bump"])
        self.assertEqual(t.cycle(0)[2][1]["durMs"], 3500 + 2500 + 1000 + 1000 + 300 + 2500 + 1000 + 1000)

    def test_the_site_s_random_numbers_and_hash(self):
        r = spelunkr._rng(0)
        self.assertTrue(all(0 <= r() < 1 for _ in range(100)))
        self.assertEqual(spelunkr._hash("a"), 97)
        self.assertEqual(spelunkr._hash("ab"), 97 * 31 + 98)

if __name__ == "__main__":
    unittest.main()
