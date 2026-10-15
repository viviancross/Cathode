"""Kernel pieces that don't need a window: timers and the guide refresh.
The refresh tests are carried over from 3.4's test_epg TestRefreshLoop."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import app as app_mod
from cathode.app import App
from cathode.config import Config
from cathode.epg import EPG


class SyncThread:
    """Runs the thread's target inside start(), so loads finish in-line."""

    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


def make_app(epg_url="a.xml"):
    cfg = Config("")
    cfg.epg_url = epg_url
    a = App(cfg)
    a.post = lambda fn, *args, **kw: fn(*args, **kw)
    a.scheduled = []
    a.after = lambda secs, fn: a.scheduled.append((secs, fn)) or [0, 0, fn, False]
    return a


class TestGuideRefresh(unittest.TestCase):
    def test_a_loaded_guide_is_reloaded_later(self):
        a = make_app()
        with mock.patch.object(app_mod.threading, "Thread", SyncThread), \
                mock.patch.object(EPG, "load", lambda self, url, **k: None):
            a.load_epg()
        self.assertEqual([s for s, _ in a.scheduled], [App.EPG_REFRESH])

    def test_a_failed_reload_keeps_the_guide_and_retries_sooner(self):
        a = make_app()
        kept = a.epg
        toasts = []
        a.toast = lambda *args: toasts.append(args)

        def boom(self, url, **k):
            raise OSError("network down")
        with mock.patch.object(app_mod.threading, "Thread", SyncThread), \
                mock.patch.object(EPG, "load", boom), \
                mock.patch.object(EPG, "channel_ids", property(lambda self: ["one.us"])):
            a.load_epg()
        self.assertIs(a.epg, kept)
        self.assertEqual([s for s, _ in a.scheduled], [App.EPG_RETRY])
        self.assertEqual(toasts, [])                # the old guide stays, quietly

    def test_a_first_guide_that_fails_says_why(self):
        import urllib.error
        a = make_app()
        toasts = []
        a.toast = lambda text, *rest: toasts.append(text)

        def boom(self, url, **k):
            raise urllib.error.URLError(ConnectionRefusedError())
        with mock.patch.object(app_mod.threading, "Thread", SyncThread), \
                mock.patch.object(EPG, "load", boom):
            a.load_epg()
        self.assertEqual(len(toasts), 1)
        self.assertIn("didn't answer", toasts[0])
        self.assertIn("15 minutes", toasts[0])

    def test_reloads_stop_when_the_playlist_changes(self):
        a = make_app()
        with mock.patch.object(app_mod.threading, "Thread", SyncThread), \
                mock.patch.object(EPG, "load", lambda self, url, **k: None):
            a.load_epg()
            a.config.epg_url = "b.xml"
            a.load_epg()                   # the new playlist's own load
            loads = []
            with mock.patch.object(a, "load_epg", lambda: loads.append(1)):
                a.scheduled[0][1]()        # the old playlist's reload timer fires
        self.assertEqual(loads, [])

    def test_a_late_result_for_an_old_playlist_is_dropped(self):
        a = make_app()
        a._epg_gen = 5
        stale = EPG()
        a._epg_loaded(4, "a.xml", stale)
        self.assertIsNot(a.epg, stale)


class TestTimers(unittest.TestCase):
    def test_timers_run_in_order_and_cancelled_ones_do_not(self):
        a = App(Config(""))
        ran = []
        a.after(0, lambda: ran.append("b"))
        t = a.after(0, lambda: ran.append("x"))
        a.cancel(t)
        a.after(-1, lambda: ran.append("a"))
        a._run_timers()
        self.assertEqual(ran, ["a", "b"])

    def test_mpv_extra_args_become_options(self):
        self.assertEqual(app_mod._mpv_extra(["--hwdec=no", "--no-config", "gpu-context=wayland"]),
                         {"hwdec": "no", "no-config": "yes", "gpu-context": "wayland"})


if __name__ == "__main__":
    unittest.main()
