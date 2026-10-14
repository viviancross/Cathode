"""XMLTV parsing, the retention window, and the app's refresh loop. Local
files only; no network."""

import gzip
import os
import shutil
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import epg as epg_mod  # noqa: E402
from cathode.epg import EPG, _parse_xmltv_dt  # noqa: E402

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


def _ts(dt):
    return dt.strftime("%Y%m%d%H%M%S +0000")


def _xmltv(progs):
    body = "".join(
        f'<programme channel="{ch}" start="{_ts(a)}" stop="{_ts(b)}">'
        f'<title>{t}</title><category>News</category>'
        f'<episode-num system="xmltv_ns">1.2.0/1</episode-num>'
        f'<episode-num system="onscreen">S02E03</episode-num></programme>'
        for ch, t, a, b in progs)
    return ('<?xml version="1.0"?><tv>'
            '<channel id="one.us"><display-name>One HD</display-name>'
            '<icon src="http://logo/one.png"/></channel>'
            f'{body}</tv>').encode()


class TestParse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def _sample(self):
        return _xmltv([
            ("one.us", "Now", NOW - timedelta(minutes=30), NOW + timedelta(minutes=30)),
            ("one.us", "Next", NOW + timedelta(minutes=30), NOW + timedelta(hours=1)),
            ("one.us", "Last week", NOW - timedelta(days=7), NOW - timedelta(days=7, hours=-1)),
            ("one.us", "Next week", NOW + timedelta(days=7), NOW + timedelta(days=7, hours=1)),
        ])

    def test_plain_and_gzip_load_the_same(self):
        for name, data in (("g.xml", self._sample()),
                           ("g.xml.gz", gzip.compress(self._sample()))):
            with self.subTest(name):
                e = EPG()
                e.load(self._write(name, data), now=NOW)
                self.assertEqual(e.current_program("one.us", NOW).title, "Now")
                self.assertEqual(e.next_program("one.us", NOW).title, "Next")
                self.assertEqual(e.icon_url("one.us"), "http://logo/one.png")
                self.assertEqual(e.current_program("one.us", NOW).episode, "S02E03")

    def test_streams_over_http(self):
        # The path real guides take: an HTTP body, gzipped, chunked or not.
        import http.server
        import functools
        self._write("g.xml.gz", gzip.compress(self._sample()))
        handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                    directory=self.tmp)
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            e = EPG()
            with mock.patch.object(http.server.SimpleHTTPRequestHandler,
                                   "log_message", lambda *a: None):
                e.load(f"http://127.0.0.1:{srv.server_address[1]}/g.xml.gz", now=NOW)
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(e.current_program("one.us", NOW).title, "Now")

    def test_only_the_window_around_now_is_kept(self):
        e = EPG()
        e.load(self._write("g.xml", self._sample()), now=NOW)
        titles = [p.title for p in e.programs_in_window(
            "one.us", NOW - timedelta(days=30), NOW + timedelta(days=30))]
        self.assertEqual(titles, ["Now", "Next"])

    def test_a_programme_spanning_the_window_edge_is_kept(self):
        long = ("one.us", "Marathon", NOW - timedelta(hours=10), NOW + timedelta(hours=1))
        e = EPG()
        e.load(self._write("g.xml", _xmltv([long])), now=NOW)
        self.assertEqual(e.current_program("one.us", NOW).title, "Marathon")

    def test_a_listing_flood_stops_at_the_ceiling(self):
        progs = [("one.us", f"P{i}", NOW + timedelta(minutes=i), NOW + timedelta(minutes=i + 1))
                 for i in range(50)]
        e = EPG()
        with mock.patch.object(epg_mod, "MAX_PROGRAMMES", 10):
            e.load(self._write("g.xml.gz", gzip.compress(_xmltv(progs))), now=NOW)
        self.assertEqual(len(e.programs_in_window(
            "one.us", NOW, NOW + timedelta(days=1))), 10)

    def test_channel_resolution(self):
        e = EPG()
        e.load(self._write("g.xml", self._sample()), now=NOW)
        self.assertEqual(e.resolve_channel_id("one.us", "whatever"), "one.us")
        self.assertEqual(e.resolve_channel_id("", "ONE HD"), "one.us")
        self.assertEqual(e.resolve_channel_id("", "One"), "one.us")     # fuzzy
        self.assertIsNone(e.resolve_channel_id("", "Two"))
        self.assertEqual(e.dominant_category("one.us"), "News")

    def test_datetime_formats(self):
        want = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
        for s in ("20261014120000 +0000", "20261014120000", "202610141200 +0000",
                  "202610141200", "20261014080000 -0400"):
            self.assertEqual(_parse_xmltv_dt(s), want, s)
        with self.assertRaises(ValueError):
            _parse_xmltv_dt("tomorrow")


class TestRefreshLoop(unittest.TestCase):
    def _app(self):
        from cathode.app import App
        from cathode.config import Config
        cfg = Config("")
        cfg.gamepad = False
        cfg.epg_url = "a.xml"
        app = App(config=cfg, width=320, height=240, fullscreen=False, demo=True)
        app.renderer.update = lambda: None
        app.EPG_REFRESH = app.EPG_RETRY = 0.01
        return app

    def test_reloads_and_stops_when_the_playlist_changes(self):
        app = self._app()
        loads = []

        def fake_load(self, url, **k):
            loads.append(url)
            if len(loads) == 3:
                app.config.epg_url = "b.xml"     # user switched playlists
        with mock.patch.object(EPG, "load", fake_load):
            t = threading.Thread(target=app._load_epg)
            t.start()
            t.join(5)
        self.assertFalse(t.is_alive())
        self.assertEqual(loads, ["a.xml"] * 3)

    def test_a_failed_reload_keeps_the_guide_on_screen(self):
        app = self._app()
        calls = []

        def flaky(self, url, **k):
            calls.append(1)
            if len(calls) == 2:
                raise OSError("server down")
            if len(calls) == 3:
                app._epg_stop.set()
        with mock.patch.object(EPG, "load", flaky):
            app._load_epg()
        self.assertIsNotNone(app.epg)
        self.assertIs(app.renderer.epg, app.epg)


if __name__ == "__main__":
    unittest.main()
