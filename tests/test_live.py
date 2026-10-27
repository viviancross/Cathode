"""Live TV tuning: every press lands, and only the stream we asked for can
lift the cover. Carried over from 3.4's test_tune_races."""

import os
import sys
import time
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

    def follow(self, url):
        self.followed = getattr(self, "followed", []) + [url]

    def buffered_behind(self):
        return 60.0


class FakeSkin:
    tune_cover = "static"
    tune_black = 0.0


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

    def note(self, text, seconds=2.5):
        self.notes = getattr(self, "notes", []) + [text]

    def toast(self, text, seconds=2.5):
        self.toasts = getattr(self, "toasts", []) + [text]

    # A screen stack, for screens that push and pop.
    screens = None

    def push(self, s):
        self.screens = (self.screens or []) + [s]

    def pop(self, s=None):
        self.screens.remove(s or self.screens[-1])

    @property
    def live(self):
        return self._live


class TestBrowse(unittest.TestCase):
    def setUp(self):
        from cathode.screens.browse import Browse
        self.app = FakeApp()
        self.app._live = LiveTV(self.app)
        self.app._live.channels_loaded()
        self.app.screens = [self.app._live]
        self.b = Browse(self.app)
        self.app.push(self.b)

    def test_browsing_does_not_tune(self):
        played = list(self.app.video.played)
        self.b.handle(R.UP)
        self.b.handle(R.UP)
        self.assertEqual(self.b.idx, 3)
        self.assertEqual(self.app.video.played, played)

    def test_ok_tunes_to_what_is_on_screen(self):
        self.b.handle(R.UP)
        self.b.handle(R.SELECT)
        self.assertEqual(self.app.live.idx, 2)
        self.assertNotIn(self.b, self.app.screens)

    def test_left_at_now_closes_it(self):
        self.b.handle(R.LEFT)
        self.assertNotIn(self.b, self.app.screens)

    def test_it_closes_itself_when_left_alone(self):
        self.app.fire(lambda t: t[0] == self.b.IDLE)
        self.assertNotIn(self.b, self.app.screens)


class TestBoot(unittest.TestCase):
    def test_a_skins_scenes_play_in_order_and_the_last_waits_for_loading(self):
        from cathode.screens.boot import Boot
        app = FakeApp()
        app._live = LiveTV(app)
        app.screens = [app._live]
        app.skin.boot_scenes = [("hello", 1.0), ("step1", 0.5), ("acquiring", 0.0)]
        app.channels = []                                   # still loading
        app._live.message = "Loading channels..."
        boot = Boot(app)
        self.assertEqual(boot.scene(), "hello")
        boot.start -= 1.2
        self.assertEqual(boot.scene(), "step1")
        boot.start -= 0.5
        self.assertEqual(boot.scene(), "acquiring")         # holds: nothing loaded yet
        boot.start -= 5
        self.assertEqual(boot.scene(), "acquiring")
        app.channels = [object()]
        app.config.epg_url = ""
        self.assertEqual(boot.scene(), "done")

    def test_a_box_with_no_boot_screen_names_no_scenes(self):
        from cathode.skins import skin_classes
        self.assertEqual(skin_classes()["indirect"].boot_scenes, [])
        self.assertTrue(skin_classes()["indirect_hd"].boot_scenes)

    def test_any_button_skips_it(self):
        from cathode.screens.boot import Boot
        app = FakeApp()
        app._live = LiveTV(app)
        app.screens = [app._live]
        boot = Boot(app)
        app.push(boot)
        boot.handle(R.UP)
        self.assertNotIn(boot, app.screens)


class TestTuning(unittest.TestCase):
    def setUp(self):
        self.app = FakeApp()
        self.live = LiveTV(self.app)
        self.live.channels_loaded()

    def test_every_press_moves_one_channel_and_mpv_ends_on_the_banner_channel(self):
        for _ in range(3):
            self.live.handle(R.UP)
        self.assertEqual(self.live.idx, 3)
        self.assertEqual(self.app.video.played, ["u0"])           # surfing: nothing loaded yet
        self.app.fire(lambda t: t[0] == LiveTV.SURF_SETTLE)
        self.assertEqual(self.app.video.played, ["u0", "u3"])     # once the presses stop: just the last
        self.assertEqual(self.app.video.played[-1], self.live.channel.url)

    def test_the_channel_surfed_past_cant_lift_the_cover(self):
        self.live.handle(R.UP)
        self.live.on_video("video_started")                         # the old stream, still coming in
        self.assertEqual(self.live.phase, "cover")

    def test_a_failing_stream_is_retried_less_often_each_time(self):
        self.live.on_video("video_started")
        self.live.phase = "watch"
        waits = []
        for _ in range(6):
            self.live.on_video("video_ended", reason="error")
            waits.append(self.app.timers[-1][0])
            self.app.timers[-1][2]()                                 # the retry itself
        self.assertEqual(waits, [0.5, 2.0, 5.0, 10.0, 20.0, 20.0])
        self.live.on_video("video_started")                          # it came back: start over
        self.live.on_video("video_ended", reason="error")
        self.assertEqual(self.app.timers[-1][0], 0.5)

    def test_a_source_that_ends_hands_over_behind_the_buffered_picture(self):
        self.live.on_video("video_started")
        self.live.phase, self.live.banner_until = "watch", 0.0
        self.live.behind = 30.0                                     # paused-live, behind
        loads = len(self.app.video.played)
        self.live.on_video("video_draining")
        self.live.on_video("video_draining")                        # once
        self.assertEqual(self.app.video.followed, [self.live.channel.url])
        self.assertEqual(len(self.app.video.played), loads)         # nothing cut off: it waits its turn
        self.assertEqual(self.live.phase, "watch")
        self.assertFalse(self.live.banner_visible())
        self.live.on_video("video_started")                         # the replacement took over
        self.assertEqual(self.live.behind, 0.0)                     # and it's live

    def test_a_stream_stuck_buffering_is_reconnected(self):
        self.live.on_video("video_started")
        self.live.phase = "watch"
        loads = len(self.app.video.played)
        self.live.on_video("video_buffering", on=True)
        self.live.on_video("video_buffering", on=False)            # a hiccup: it came back
        self.live.on_video("video_buffering", on=True)
        self.app.fire(lambda t: t[0] == LiveTV.STALL_LIMIT)
        self.assertTrue(self.live.dropped)
        self.app.timers[-1][2]()                                    # the reconnect
        self.assertEqual(len(self.app.video.played), loads + 1)
        self.assertEqual(self.live.phase, "watch")

    def test_a_dropped_stream_comes_back_under_its_last_picture(self):
        self.live.on_video("video_started")
        self.live.phase, self.live.banner_until = "watch", 0.0
        loads = len(self.app.video.played)
        self.live.on_video("video_ended", reason="eof")
        self.assertFalse(self.live.trick_visible())                 # mpv's hold isn't a pause
        self.app.timers[-1][2]()
        self.assertEqual(len(self.app.video.played), loads + 1)    # loaded again...
        self.assertEqual(self.live.phase, "watch")                  # ...no cover
        self.assertFalse(self.live.banner_visible())                # ...no banner
        self.assertFalse(self.live.standby)
        for _ in range(2):                                          # it keeps failing: say so
            self.live.on_video("video_ended", reason="error")
        self.assertTrue(self.live.standby)
        self.live.on_video("video_started")
        self.assertFalse(self.live.standby or self.live.dropped)

    def test_a_frame_lifts_the_cover(self):
        self.assertEqual(self.live.cover(), ("static", 1.0))
        self.live.on_video("video_started")
        self.assertEqual(self.live.phase, "reveal")

    def test_a_boxs_black_has_a_floor(self):
        # The real box sat black while its tuner locked; a frame that comes
        # at once waits out the skin's floor, then reveals.
        self.app.skin.tune_black = 1.5
        self.live.tune(1)
        self.live.on_video("video_started")
        self.assertEqual(self.live.phase, "cover")
        t = self.app.timers[-1]
        self.assertAlmostEqual(t[0], 1.5, delta=0.1)
        t[2]()
        self.assertEqual(self.live.phase, "reveal")
        self.app.skin.tune_black = 0.0

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

    def test_an_unknown_number_clears_and_says_so(self):
        for a in (R.DIGITS[9], R.DIGITS[9], R.SELECT):
            self.live.handle(a)
        self.assertEqual(self.live.idx, 0)
        self.assertEqual(self.live.digits, "")
        self.assertEqual(self.app.notes, ["No channel 99"])

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

    def test_select_banner_then_buttons_and_options_has_its_own_key(self):
        from cathode.screens.menu import Options
        self.app._live, self.app.toast = self.live, lambda *a, **k: None
        self.app.video.tracks = lambda kind: []
        self.app.cycle_format = self.app.cycle_subtitles = lambda *a: None
        self.live.hide_banner()
        self.live.handle(R.SELECT)                      # once: the banner
        self.assertTrue(self.live.banner_visible())
        self.assertIsNone(self.live.trick_focus)
        self.live.handle(R.SELECT)                      # twice: the playback buttons, on Play/Pause
        self.assertEqual(self.live.trick_focus, 1)
        self.live.handle(R.SELECT)                      # on them: pause
        self.assertTrue(self.app.video.paused)
        self.live.handle(R.LEFT)                        # LEFT moves along the buttons, not the volume
        self.assertEqual((self.live.trick_focus, self.app.video.volume), (0, 50))
        self.live.handle(R.OPTIONS)
        opts = self.app.screens[-1]
        self.assertIsInstance(opts, Options)
        self.assertEqual([it.label for it in opts.items],
                         ["Add to Favorites", "Picture format", "Subtitles", "On Demand"])


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
        import threading
        v._ids = threading.Lock()
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

    def test_a_start_reported_inside_loadfile_still_counts(self):
        # mpv's thread can report the new file (even its first frame) before
        # loadfile returns; it waits on the lock until play() has recorded
        # which file it asked for, so a retune's picture isn't taken for the
        # last channel's and dropped.
        import threading
        v, test = self.v, self
        v.play("http://x/one.ts")
        self.event("start", v._want)
        plain = type(v.player).command

        def command(player, *a):
            rv = plain(player, *a)
            n = rv["playlist_entry_id"]
            test.t = threading.Thread(target=lambda: (test.event("start", n), test.event("restart")))
            test.t.start()
            test.t.join(0.2)
            return rv
        type(v.player).command = command
        try:
            v.play("http://x/two.ts")
        finally:
            type(v.player).command = plain
        self.t.join(2)
        self.assertEqual(self.posts, ["video_started"])

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


class TestStreamEnd(unittest.TestCase):
    def test_a_stream_that_ends_is_reported_though_mpv_holds_it_paused(self):
        # keep-open sends no END_FILE at the end: eof-reached is the only sign.
        from cathode.video import Video
        import threading
        v = Video.__new__(Video)
        v._ids = threading.Lock()
        posted = []
        v._post = lambda kind, **d: posted.append((kind, d))
        v._want, v._current = 7, 6
        v._on_eof("eof-reached", True)                  # the file being replaced
        self.assertEqual(posted, [])
        v._current = 7
        v._on_eof("eof-reached", False)
        v._on_eof("eof-reached", True)
        self.assertEqual(posted, [("video_ended", {"reason": "eof"})])

    def test_a_source_read_to_its_end_is_reported_once(self):
        import threading
        from cathode.video import Video
        v = Video.__new__(Video)
        v._ids, v._drained = threading.Lock(), None
        posted = []
        v._post = lambda kind, **d: posted.append(kind)
        v._want, v._current = 7, 7
        v._on_cache("demuxer-cache-state", {"eof": False})
        v._on_cache("demuxer-cache-state", {"eof": True})
        v._on_cache("demuxer-cache-state", {"eof": True})
        self.assertEqual(posted, ["video_draining"])
        v._want = 8                                       # its replacement is queued
        v._current = 8
        v._on_cache("demuxer-cache-state", {"eof": True})
        self.assertEqual(posted, ["video_draining"] * 2)

class TestTrackCommandsDontCrash(unittest.TestCase):
    def test_mpv_refusing_a_subtitle_is_said_not_raised(self):
        from cathode.video import Video
        v = Video.__new__(Video)

        class Player(dict):
            def command(self, *a):
                raise SystemError("Error running mpv command", -12)

            def __setitem__(self, k, val):
                raise SystemError("Error setting property", -12)
        v.player = Player()
        self.assertFalse(v.add_subtitle("http://s/x.srt", "x", "en", select=True))
        self.assertFalse(v.remove_subtitle(3))
        v.set_track("sub", 9)                                       # no exception

class TestMpvLog(unittest.TestCase):
    def test_mpv_warnings_reach_the_log_once_with_a_count(self):
        import contextlib, io
        from cathode.video import Video
        v = Video.__new__(Video)
        v._last_log, v._log_repeats = None, 0
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for _ in range(3):
                v._on_log("warn", "ad", "Error decoding audio.")
            v._on_log("warn", "ao/wasapi", "Audio device underrun detected.")
        lines = out.getvalue().splitlines()
        self.assertEqual(lines, ["[mpv] warn ad: Error decoding audio.", "[mpv] (repeated 2 more times)",
                                 "[mpv] warn ao/wasapi: Audio device underrun detected."])


class TestSounds(unittest.TestCase):
    def test_only_the_hr20_skin_makes_them_and_off_silences_it(self):
        from types import SimpleNamespace
        from cathode.app import App
        from cathode.skins import skin_classes
        self.assertTrue(skin_classes()["indirect_hd"].ui_sounds)
        for name in ("indirect", "plate", "plate_hd", "classic"):
            self.assertFalse(skin_classes()[name].ui_sounds, name)
        app = App.__new__(App)
        played = []
        app._sounds = SimpleNamespace(level="medium", key=lambda: played.append("key"), bonk=lambda: played.append("bonk"))
        app.config = SimpleNamespace(sound_effects="medium")
        app.skin = SimpleNamespace(ui_sounds=True)
        app.sound("key"); app.sound("bonk")
        app.config.sound_effects = "off"
        app.sound("key")
        app.config.sound_effects = "high"
        app.skin = SimpleNamespace(ui_sounds=False)
        app.sound("key")
        self.assertEqual(played, ["key", "bonk"])

    def test_the_synthesised_sounds_build(self):
        import pygame
        from cathode import sounds
        try:
            pygame.mixer.init(frequency=sounds.RATE, size=-16, channels=2)
        except pygame.error as e:
            self.skipTest(f"no audio device: {e}")
        self.assertGreater(sounds.key_sound().get_length(), 0.01)
        self.assertGreater(sounds.bonk_sound().get_length(), 0.1)


class TestAudioOutput(unittest.TestCase):
    def test_an_output_that_cant_open_falls_back_to_the_default(self):
        from cathode.video import Video
        v = Video.__new__(Video)
        v._last_log, v._log_repeats = None, 0
        v.player = {"audio-device": "wasapi/{gone}"}
        posted = []
        v._post = lambda kind, **d: posted.append(kind)
        v._on_log("error", "cplayer", "Could not open/initialize audio device -> no sound.")
        self.assertEqual(v.player["audio-device"], "auto")
        self.assertEqual(posted, ["audio_fallback"])
        v._on_log("error", "cplayer", "Could not open/initialize audio device -> no sound.")
        self.assertEqual(posted, ["audio_fallback"])          # already on the default: once

    def test_a_saved_output_is_checked_against_the_list(self):
        from cathode.video import Video
        v = Video.__new__(Video)
        v.audio_devices = lambda: [{"name": "auto"}, {"name": "wasapi/{here}"}]
        self.assertTrue(v.has_audio_device("wasapi/{here}"))
        self.assertTrue(v.has_audio_device(""))
        self.assertFalse(v.has_audio_device("wasapi/{gone}"))


if __name__ == "__main__":
    unittest.main()


class TestCornerBugs(unittest.TestCase):
    """The rating mark as a programme (or a tune) begins, the up-next mark
    as it ends, neither over the banner."""

    def _live(self, start_ago, length, rating="TV-PG", nxt=True):
        from datetime import datetime, timedelta, timezone
        from cathode.epg import Program
        now = datetime.now(timezone.utc)
        cur = Program("c", "Now Show", now - timedelta(seconds=start_ago), now - timedelta(seconds=start_ago) + timedelta(seconds=length), rating=rating)
        after = Program("c", "Next Show", cur.stop, cur.stop + timedelta(hours=1))

        class Epg:
            def resolve_channel_id(self, *a):
                return "c"

            def current_program(self, cid, t):
                return cur

            def next_program(self, cid, t):
                return after if nxt else None
        app = FakeApp()
        app.epg = Epg()
        app._live = LiveTV(app)
        live = app._live
        live.idx = 0
        live.phase = "watch"
        live.hide_banner()
        return live

    def test_the_rating_shows_as_a_programme_begins_and_after_a_tune(self):
        live = self._live(start_ago=5, length=1800)
        live._watch_since = time.monotonic() - 60
        self.assertEqual(live.bug(), ("rating", "TV-PG"))
        live = self._live(start_ago=600, length=1800)
        live._watch_since = time.monotonic() - 3          # tuned 3 s ago
        self.assertEqual(live.bug(), ("rating", "TV-PG"))
        live._watch_since = time.monotonic() - 60         # settled: nothing
        self.assertIsNone(live.bug())

    def test_up_next_in_the_last_seconds_and_nothing_over_the_banner(self):
        live = self._live(start_ago=1740, length=1800)      # 60 s left
        live._watch_since = time.monotonic() - 60
        self.assertEqual(live.bug(), ("next", "Next Show"))
        live.show_banner()
        self.assertIsNone(live.bug())
        live = self._live(start_ago=1740, length=1800, nxt=False)
        live._watch_since = time.monotonic() - 60
        self.assertIsNone(live.bug())
        live = self._live(start_ago=5, length=1800, rating="")
        live._watch_since = time.monotonic() - 60
        self.assertIsNone(live.bug())                      # no rating in the guide: no mark
