"""Unit tests for cathode.plex — the Plex client + JSON helpers.

Pure-stdlib (unittest + mock); no network. Run:  python -m unittest discover tests
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import plex  # noqa: E402


# ── JSON helpers ────────────────────────────────────────────────────────────

class TestJSONHelpers(unittest.TestCase):
    def test_container_returns_list(self):
        data = {"MediaContainer": {"Metadata": [{"a": 1}, {"a": 2}]}}
        self.assertEqual(plex._container(data, "Metadata"), [{"a": 1}, {"a": 2}])

    def test_container_missing_key(self):
        self.assertEqual(plex._container({"MediaContainer": {}}, "Metadata"), [])
        self.assertEqual(plex._container({}, "Metadata"), [])
        self.assertEqual(plex._container("not a dict", "Metadata"), [])

    def test_container_non_list_value(self):
        data = {"MediaContainer": {"Metadata": "scalar"}}
        self.assertEqual(plex._container(data, "Metadata"), [])

    def test_first_part(self):
        meta = {"Media": [{"Part": [{"key": "/library/parts/1/file.mkv"}]}]}
        self.assertEqual(plex._first_part(meta), "/library/parts/1/file.mkv")

    def test_first_part_none(self):
        self.assertIsNone(plex._first_part({}))
        self.assertIsNone(plex._first_part({"Media": [{"Part": [{}]}]}))

    def test_display_title_episode(self):
        m = {"type": "episode", "grandparentTitle": "Show",
             "parentIndex": 2, "index": 5, "title": "The One"}
        title, sub = plex._display_title(m)
        self.assertEqual(title, "Show")
        self.assertIn("S2E5", sub)
        self.assertIn("The One", sub)

    def test_display_title_movie(self):
        m = {"type": "movie", "title": "Film", "year": 1999,
             "contentRating": "R", "rating": 8.5}
        title, sub = plex._display_title(m)
        self.assertEqual(title, "Film")
        self.assertIn("1999", sub)
        self.assertIn("R", sub)
        self.assertIn("8.5", sub)

    def test_meta_row_playable_by_media(self):
        # A "clip"/"" item with Media is playable (covers Other Videos).
        row = plex._meta_row({"type": "", "ratingKey": 7,
                              "title": "Clip", "Media": [{}]})
        self.assertTrue(row["playable"])
        self.assertEqual(row["rating_key"], "7")

    def test_meta_row_not_playable_folder_like(self):
        row = plex._meta_row({"type": "show", "ratingKey": 9, "title": "Series"})
        self.assertFalse(row["playable"])

    def test_meta_row_offset_ms_to_s(self):
        row = plex._meta_row({"type": "movie", "ratingKey": 1, "title": "M",
                              "Media": [{}], "viewOffset": 90000})
        self.assertEqual(row["offset"], 90)


# ── URL building ──────────────────────────────────────────────────────────

class TestURLBuilding(unittest.TestCase):
    def setUp(self):
        self.c = plex.PlexClient("cid", token="acct", admin_token="acct")
        self.c.server = "http://server:32400"
        self.c._server_token = "srvtok"

    def test_abs_url_variants(self):
        self.assertEqual(self.c._abs_url("http://x/y"), "http://x/y")
        self.assertEqual(self.c._abs_url("/library/x"),
                         "http://server:32400/library/x")
        self.assertEqual(self.c._abs_url("library/x"),
                         "http://server:32400/library/x")

    def test_join_sort(self):
        self.assertEqual(plex.PlexClient._join("/p"), "/p")
        self.assertEqual(plex.PlexClient._join("/p", "year:desc"),
                         "/p?sort=year:desc")
        self.assertEqual(plex.PlexClient._join("/p?x=1", "year:desc"),
                         "/p?x=1&sort=year:desc")

    def test_transcode_url_has_no_token(self):
        url = self.c._transcode_url("123", 4000, 30)
        self.assertNotIn("X-Plex-Token", url)
        self.assertIn("maxVideoBitrate=4000", url)
        self.assertIn("start.m3u8", url)


# ── play_info: token in header, not URL ─────────────────────────────────────

class TestPlayInfo(unittest.TestCase):
    def setUp(self):
        self.c = plex.PlexClient("cid", token="acct")
        self.c.server = "http://server:32400"
        self.c._server_token = "srvtok"

    def _meta(self, **over):
        m = {"type": "movie", "title": "Film", "year": 2001,
             "viewOffset": 60000,
             "Media": [{"Part": [{"key": "/library/parts/9/file.mkv"}]}]}
        m.update(over)
        return {"MediaContainer": {"Metadata": [m]}}

    def test_direct_play_url_clean_token_in_header(self):
        with mock.patch.object(self.c, "_get", return_value=self._meta()):
            info = self.c.play_info("9", quality="Original")
        self.assertEqual(info["url"], "http://server:32400/library/parts/9/file.mkv")
        self.assertNotIn("X-Plex-Token", info["url"])
        self.assertEqual(info["headers"], {"X-Plex-Token": "srvtok"})
        self.assertEqual(info["offset"], 60)   # ms -> s

    def test_transcode_quality_resets_offset(self):
        with mock.patch.object(self.c, "_get", return_value=self._meta()):
            info = self.c.play_info("9", quality="720p (4 Mbps)")
        self.assertIn("start.m3u8", info["url"])
        self.assertNotIn("X-Plex-Token", info["url"])
        self.assertEqual(info["offset"], 0)    # transcoder starts at the offset

    def test_no_part_raises(self):
        bad = {"MediaContainer": {"Metadata": [{"type": "movie", "title": "x"}]}}
        with mock.patch.object(self.c, "_get", return_value=bad):
            with self.assertRaises(plex.PlexError):
                self.c.play_info("9")

    def test_item_detail_poster_url_token_free(self):
        meta = {"MediaContainer": {"Metadata": [{
            "type": "movie", "title": "Film", "thumb": "/library/metadata/9/thumb/1",
            "duration": 7200000, "viewOffset": 0}]}}
        with mock.patch.object(self.c, "_get", return_value=meta):
            d = self.c.item_detail("9")
        self.assertEqual(d["poster"], "http://server:32400/library/metadata/9/thumb/1")
        self.assertNotIn("X-Plex-Token", d["poster"])
        self.assertEqual(d["poster_headers"], {"X-Plex-Token": "srvtok"})


# ── find_on_server: single cross-library query ──────────────────────────────

class TestFindOnServer(unittest.TestCase):
    def setUp(self):
        self.c = plex.PlexClient("cid", token="acct")
        self.c.server = "http://server:32400"
        self.c._server_token = "srvtok"

    def test_uses_library_all_and_returns_rating_key(self):
        calls = []

        def fake_get(url, token=None, timeout=plex._TIMEOUT):
            calls.append(url)
            return {"MediaContainer": {"Metadata": [{"ratingKey": 42}]}}

        with mock.patch.object(self.c, "_get", side_effect=fake_get):
            rk = self.c.find_on_server("plex://movie/abc")
        self.assertEqual(rk, "42")
        self.assertEqual(len(calls), 1)               # one request, not per-section
        self.assertIn("/library/all?", calls[0])

    def test_falls_back_to_trailing_id(self):
        def fake_get(url, token=None, timeout=plex._TIMEOUT):
            # First query (full guid) finds nothing; second (bare id) hits.
            if "abc" in url and "plex" in url:
                return {"MediaContainer": {"Metadata": []}}
            return {"MediaContainer": {"Metadata": [{"ratingKey": 7}]}}

        with mock.patch.object(self.c, "_get", side_effect=fake_get):
            rk = self.c.find_on_server("plex://movie/abc")
        self.assertEqual(rk, "7")

    def test_empty_guid(self):
        self.assertIsNone(self.c.find_on_server(""))


# ── discover_server: parallel probe picks most-preferred reachable ──────────

class TestDiscover(unittest.TestCase):
    def setUp(self):
        self.c = plex.PlexClient("cid", token="acct")

    def test_first_reachable_prefers_earlier_candidate(self):
        # Both reachable; the earlier (more-preferred) one must win even if the
        # later one would "finish" first.
        cands = [("http://local:32400", "t"), ("http://remote:32400", "t")]
        with mock.patch.object(self.c, "_reachable", return_value=True):
            self.assertEqual(self.c._first_reachable(cands), cands[0])

    def test_first_reachable_skips_dead(self):
        cands = [("http://dead:32400", "t"), ("http://live:32400", "t")]

        def reach(uri, token, timeout=5):
            return "live" in uri

        with mock.patch.object(self.c, "_reachable", side_effect=reach):
            self.assertEqual(self.c._first_reachable(cands), cands[1])

    def test_first_reachable_none(self):
        self.assertIsNone(self.c._first_reachable([]))

    def test_discover_picks_local_over_remote(self):
        resources = [{
            "provides": "server", "owned": True, "accessToken": "srvtok",
            "connections": [
                {"uri": "http://remote:32400", "local": False},
                {"uri": "http://local:32400", "local": True},
            ],
        }]

        def fake_get(url, token=None, timeout=plex._TIMEOUT):
            if "/identity" in url:
                if "local" in url:
                    return {}                      # local reachable
                raise OSError("remote down")
            return resources                       # the resources listing

        with mock.patch.object(self.c, "_get", side_effect=fake_get):
            chosen = self.c.discover_server()
        self.assertEqual(chosen, "http://local:32400")
        self.assertEqual(self.c.server, "http://local:32400")
        self.assertEqual(self.c._server_token, "srvtok")

    def test_discover_no_servers_raises(self):
        with mock.patch.object(self.c, "_get", return_value=[]):
            with self.assertRaises(plex.PlexError):
                self.c.discover_server()


class TestFolderBrowsing(unittest.TestCase):
    def setUp(self):
        self.c = plex.PlexClient("cid", token="acct")
        self.c.server = "http://server:32400"
        self.c._server_token = "srvtok"

    def test_folder_url_absolute_passthrough(self):
        d = {"key": "/library/sections/2/folder?parent=44159"}
        self.assertEqual(self.c._folder_url("2", d),
                         "/library/sections/2/folder?parent=44159")

    def test_folder_url_relative_rebuild(self):
        d = {"key": "folder?parent=44159"}
        self.assertEqual(self.c._folder_url("2", d),
                         "/library/sections/2/folder?parent=44159")

    def test_folder_url_bare_id_or_rating_key(self):
        self.assertEqual(self.c._folder_url("2", {"ratingKey": 99}),
                         "/library/sections/2/folder?parent=99")
        self.assertEqual(self.c._folder_url("2", {"key": "12345"}),
                         "/library/sections/2/folder?parent=12345")

    def test_non_playable_metadata_becomes_folder_not_children(self):
        # A folder returned as a Metadata node with no playable Part must be
        # routed back through the folder endpoint, never /children (404).
        data = {"MediaContainer": {
            "Directory": [{"key": "/library/sections/2/folder?parent=10",
                           "title": "Sub"}],
            "Metadata": [
                {"type": "clip", "ratingKey": 5, "title": "Clip",
                 "Media": [{"Part": [{"key": "/p.mkv"}]}]},      # playable video
                {"type": "", "ratingKey": 77, "title": "NestedFolder"},  # folder-as-metadata
            ]}}
        with mock.patch.object(self.c, "_get", return_value=data):
            rows = self.c.folder_items("/library/sections/2/folder", section="2")
        by_title = {r["title"]: r for r in rows}
        self.assertEqual(by_title["Sub"]["type"], "folder")
        self.assertTrue(by_title["Clip"]["playable"])
        self.assertEqual(by_title["NestedFolder"]["type"], "folder")
        self.assertEqual(by_title["NestedFolder"]["folder"],
                         "/library/sections/2/folder?parent=77")
        # section is threaded onto folder rows for deeper navigation
        self.assertEqual(by_title["NestedFolder"]["section"], "2")

    def test_folder_unavailable_wraps_404(self):
        import urllib.error
        def boom(*a, **k):
            raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with mock.patch.object(self.c, "_get", side_effect=boom):
            with self.assertRaises(plex.PlexError):
                self.c.folder_items("/library/sections/2/folder", section="2")


if __name__ == "__main__":
    unittest.main()
