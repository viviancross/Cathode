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

    def test_progress_reports_the_real_read_and_ends_at_one(self):
        # Gzipped too: the count is of the source's bytes, not the XML's.
        for name, data in (("g.xml", self._sample() * 1), ("g.xml.gz", gzip.compress(self._sample()))):
            with self.subTest(name):
                seen = []
                EPG().load(self._write(name, data), now=NOW, progress=seen.append)
                self.assertTrue(seen)
                self.assertEqual(seen, sorted(seen))          # never goes backwards
                self.assertEqual(seen[-1], 1.0)
                self.assertTrue(all(0 <= f <= 1 for f in seen))

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




class TestLineGuide(unittest.TestCase):
    """A provider line (xtream://): xmltv.php when it answers, else the
    panel's per-channel API, titles base64 as the panels send them."""

    def _panel(self, xmltv_code):
        import base64
        import json
        import urllib.error
        from urllib.parse import parse_qs, urlsplit
        calls = []

        def R(body):
            import io
            r = io.BytesIO(body)
            r.headers = {}
            return r

        def urlopen(req, timeout=0, context=None):
            u = urlsplit(req.full_url)
            q = parse_qs(u.query)
            action, sid = q.get("action", [""])[0], q.get("stream_id", [""])[0]
            calls.append((u.path, action, sid))
            if u.path == "/xmltv.php":
                if xmltv_code != 200:
                    raise urllib.error.HTTPError(req.full_url, xmltv_code, "Locked", {}, None)
                return R(_xmltv([("alpha.1", "From XMLTV", NOW, NOW + timedelta(hours=1))]))
            if action == "get_live_streams":
                return R(json.dumps([{"stream_id": 7, "name": "Alpha", "epg_channel_id": "alpha.1"},
                                     {"stream_id": 8, "name": "Beta", "epg_channel_id": ""}]).encode())
            t = int(NOW.timestamp())

            def e(x):
                return base64.b64encode(x.encode()).decode()
            rows = {"7": [{"title": e("News Hour"), "description": e("Headlines"),
                           "start_timestamp": str(t - 600), "stop_timestamp": str(t + 3000)},
                          {"title": e("Old"), "start_timestamp": str(t - 90000), "stop_timestamp": str(t - 86400)}],
                    "8": [{"title": "Plain Title", "start_timestamp": t + 60, "stop_timestamp": t + 3660}]}
            return R(json.dumps({"epg_listings": rows[sid]}).encode())
        return urlopen, calls

    def _load(self, code, **kw):
        urlopen, calls = self._panel(code)
        with mock.patch.object(epg_mod.urllib.request, "urlopen", urlopen):
            with mock.patch("cathode.servers.urllib.request.urlopen", urlopen):
                g = EPG()
                g.load("xtream://h:80/u/p", now=NOW, **kw)
        return g, calls

    def test_a_locked_xmltv_falls_back_to_the_api_per_channel(self):
        seen = []
        g, calls = self._load(513, progress=seen.append)
        self.assertEqual(g.current_program("alpha.1", NOW).title, "News Hour")
        self.assertEqual(g.current_program("alpha.1", NOW).description, "Headlines")
        self.assertEqual([p.title for p in g._programs["alpha.1"]], ["News Hour"])   # outside the window: dropped
        self.assertEqual(g.next_program("xtream:8", NOW).title, "Plain Title")      # no EPG id: filed by stream id
        self.assertEqual(g.resolve_channel_id("xtream:8", "Beta"), "xtream:8")
        self.assertEqual(seen, [1.0])
        self.assertEqual(calls[0], ("/xmltv.php", "", ""))
        self.assertEqual(sorted(c[2] for c in calls if c[1] == "get_simple_data_table"), ["7", "8"])

    def test_a_served_xmltv_is_used_as_is(self):
        g, calls = self._load(200)
        self.assertEqual(g.current_program("alpha.1", NOW).title, "From XMLTV")
        self.assertEqual(len(calls), 1)
