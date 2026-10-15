"""Live TV tuning: every press lands, and only the stream we asked for can
lift the cover. Carried over from 3.4's test_tune_races."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import remote as R
from cathode.config import Config
from cathode.playlist import Channel
from cathode.screens.live import LiveTV


class FakeVideo:
    def __init__(self):
        self.played = []
        self.seeks = []
        self.volume, self.muted, self.paused = 50, False, False

    def play(self, url, headers=None, start=0):
        self.played.append(url)
        self.paused = False

    def seek(self, s, mode="relative"):
        self.seeks.append(s)

    def buffered_behind(self):
        return 60.0


class FakeSkin:
    tune_cover = "static"


class FakeApp:
    """Just enough kernel: timers that only fire when the test says so."""

    def __init__(self, n=5):
        self.config = Config("")
        self.channels = [Channel(number=i * 2 + 2, name=f"Ch{i}", url=f"u{i}") for i in range(n)]
        self.epg = None
        self.video = FakeVideo()
        self.skin = FakeSkin()
        self.start_channel = None
        self.timers = []

    def after(self, seconds, fn):
        t = [seconds, 0, fn, False]
        self.timers.append(t)
        return t

    @staticmethod
    def cancel(t):
        if t:
            t[3] = True

    def fire(self, pred=lambda t: True):
        """Run every live timer matching pred, as the kernel would when due."""
        for t in list(self.timers):
            if not t[3] and pred(t):
                t[3] = True
                t[2]()

    def invalidate(self):
        pass


class TestTuning(unittest.TestCase):
    def setUp(self):
        self.app = FakeApp()
        self.live = LiveTV(self.app)
        self.live.channels_loaded()

    def test_every_press_moves_one_channel_and_mpv_ends_on_the_banner_channel(self):
        for _ in range(3):
            self.live.handle(R.UP)
        self.assertEqual(self.live.idx, 3)
        self.assertEqual(self.app.video.played, ["u0", "u1", "u2", "u3"])
        self.assertEqual(self.app.video.played[-1], self.live.channel.url)

    def test_a_frame_lifts_the_cover(self):
        self.assertEqual(self.live.cover(), ("static", 1.0))
        self.live.on_video("video_started")
        self.assertEqual(self.live.phase, "reveal")

    def test_a_stale_timeout_does_not_reveal_the_next_channel(self):
        self.live.handle(R.UP)                     # tune again: first timeout is cancelled
        self.app.fire(lambda t: t[0] == self.app.config.tune_timeout and t is self.app.timers[0])
        self.assertEqual(self.live.phase, "cover")
        self.assertFalse(self.live.standby)

    def test_a_dead_stream_reveals_onto_the_standby_card(self):
        self.app.fire(lambda t: t[0] == self.app.config.tune_timeout)
        self.assertTrue(self.live.standby)
        self.live.on_video("video_started")        # a late frame replaces the card
        self.assertFalse(self.live.standby)

    def test_prev_goes_back_to_the_channel_before(self):
        self.live.handle(R.UP)
        self.live.handle(R.UP)
        self.live.handle(R.PREV)
        self.assertEqual(self.live.idx, 1)
        self.live.handle(R.PREV)
        self.assertEqual(self.live.idx, 2)

    def test_typed_digits_tune_that_number(self):
        for a in (R.DIGITS[6], R.SELECT):
            self.live.handle(a)
        self.assertEqual(self.live.channel.number, 6)

    def test_an_unknown_number_just_clears(self):
        for a in (R.DIGITS[9], R.DIGITS[9], R.SELECT):
            self.live.handle(a)
        self.assertEqual(self.live.idx, 0)
        self.assertEqual(self.live.digits, "")

    def test_digits_tune_on_their_own_after_a_pause(self):
        self.live.handle(R.DIGITS[4])
        self.app.fire(lambda t: t[0] == LiveTV.DIGIT_WAIT)
        self.assertEqual(self.live.channel.number, 4)

    def test_info_twice_expands_the_banner(self):
        self.live.hide_banner()
        self.live.handle(R.INFO)
        self.assertFalse(self.live.banner_full)
        self.live.handle(R.INFO)
        self.assertTrue(self.live.banner_full)


class TestPauseLive(unittest.TestCase):
    def setUp(self):
        self.app = FakeApp()
        self.app.toast = lambda *a, **k: None
        self.live = LiveTV(self.app)
        self.live.channels_loaded()
        self.clock = [100.0]
        p = mock.patch("cathode.screens.live.time.monotonic", lambda: self.clock[0])
        p.start()
        self.addCleanup(p.stop)

    def test_time_spent_paused_puts_you_behind_live(self):
        self.live.handle(R.PAUSE)
        self.clock[0] += 30
        self.assertAlmostEqual(self.live.behind_now(), 30)
        self.live.handle(R.PAUSE)
        self.clock[0] += 30
        self.assertAlmostEqual(self.live.behind_now(), 30)    # playing again: gap holds

    def test_rewind_and_fast_forward_move_through_the_buffer(self):
        self.live.handle(R.REW)
        self.live.handle(R.REW)
        self.assertEqual(self.live.behind_now(), 20)
        self.live.handle(R.FF)
        self.assertEqual(self.live.behind_now(), 10)
        self.assertEqual(self.app.video.seeks, [-10, -10, 10])

    def test_fast_forward_never_passes_live(self):
        self.live.handle(R.FF)
        self.assertEqual(self.app.video.seeks, [])
        self.assertEqual(self.live.behind_now(), 0)

    def test_skip_jumps_back_to_live(self):
        self.live.handle(R.REW)
        played = len(self.app.video.played)
        self.live.handle(R.SKIP)
        self.assertEqual(len(self.app.video.played), played + 1)
        self.assertEqual(self.live.behind_now(), 0)

    def test_a_new_channel_is_live(self):
        self.live.handle(R.REW)
        self.live.handle(R.UP)
        self.assertEqual(self.live.behind_now(), 0)


class TestNoChannels(unittest.TestCase):
    def test_tuning_with_nothing_loaded_is_safe(self):
        app = FakeApp(n=0)
        live = LiveTV(app)
        live.tune(3)
        for a in (R.UP, R.PREV, R.DIGITS[1], R.SELECT):
            live.handle(a)
        self.assertEqual(app.video.played, [])


class TestVideoEventFilter(unittest.TestCase):
    """Only the load we asked for may report it started."""

    def setUp(self):
        try:
            from cathode import video
        except (ImportError, OSError) as e:
            self.skipTest(f"libmpv not available: {e}")
        self.video_mod = video
        self.posts = []
        v = video.Video.__new__(video.Video)
        v._post = lambda kind, **d: self.posts.append(kind)
        v._want = v._current = None
        self.calls = []
        test = self

        class Player(dict):
            pause = False

            def __setitem__(self, k, val):
                test.calls.append(("set", k, val))

            def command(self, *a):
                test.calls.append(("cmd",) + a)
                Player.entry = getattr(Player, "entry", 0) + 1
                return {"playlist_entry_id": Player.entry}
        v.player = Player()
        self.v = v

    def event(self, kind, entry=None, reason=0):
        mpv = self.video_mod.mpv
        ids = {"start": mpv.MpvEventID.START_FILE, "restart": mpv.MpvEventID.PLAYBACK_RESTART,
               "end": mpv.MpvEventID.END_FILE}

        class Data:
            playlist_entry_id = entry
            EOF, ERROR = 0, 4

        Data.reason = reason

        class Ev:
            pass
        e = Ev()
        e.event_id = type("I", (), {"value": ids[kind]})()
        e.data = Data()
        self.v._on_event(e)

    def test_a_late_restart_from_the_last_file_is_not_this_ones(self):
        self.v.play("a")
        self.v.play("b")                 # entry 2 wanted now
        self.event("start", entry=1)     # mpv still finishing the old load
        self.event("restart")
        self.assertEqual(self.posts, [])
        self.event("start", entry=2)
        self.event("restart")
        self.assertEqual(self.posts, ["video_started"])

    def test_the_end_of_the_replaced_file_is_ignored(self):
        self.v.play("a")
        self.v.play("b")
        self.event("end", entry=1, reason=4)
        self.assertEqual(self.posts, [])
        self.event("end", entry=2, reason=4)
        self.assertEqual(self.posts, ["video_ended"])

    def test_headers_go_out_before_the_load_they_belong_to(self):
        self.v.play("x", headers={"X-Plex-Token": "t"})
        kinds = [c[1] for c in self.calls]
        self.assertLess(kinds.index("http-header-fields"), kinds.index("loadfile"))

    def test_a_live_stream_never_inherits_a_previous_token(self):
        self.v.play("plex", headers={"X-Plex-Token": "t"})
        self.v.play("live")
        sets = [c for c in self.calls if c[:2] == ("set", "http-header-fields")]
        self.assertEqual(sets[-1][2], [])


if __name__ == "__main__":
    unittest.main()
