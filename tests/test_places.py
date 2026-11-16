"""Phase 6: more places for library channels. Lengths read from MP4,
Matroska and AVI headers; folders as movies, shows and clips; a Jellyfin
(or Emby) server over real HTTP on this machine; a title in two places kept
once; a place that doesn't answer keeping what was read of it."""

import json
import os
import shutil
import struct
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import folders, jellyfin, libchannels as lc, library
from cathode.plex import PlexError
from tests.test_library import index


def mp4(seconds):
    mvhd = struct.pack(">I4sB3sIIII", 28, b"mvhd", 0, b"\0\0\0", 0, 0, 1000, int(seconds * 1000))
    return struct.pack(">I4s4sI", 16, b"ftyp", b"isom", 0x200) + struct.pack(">I4s", 8 + len(mvhd), b"moov") + mvhd


def mkv(seconds):
    info = bytes.fromhex("2AD7B1") + bytes([0x83]) + (1000000).to_bytes(3, "big") \
        + bytes.fromhex("4489") + bytes([0x88]) + struct.pack(">d", seconds * 1000)
    return (bytes.fromhex("1A45DFA3") + bytes([0x80]) + bytes.fromhex("18538067") + bytes.fromhex("01FFFFFFFFFFFFFF")
            + bytes.fromhex("1549A966") + bytes([0x80 | len(info)]) + info + bytes.fromhex("1654AE6B") + bytes([0x80]))


def avi(seconds):
    avih = struct.pack("<IIIII", 40000, 0, 0, 0, int(seconds * 25)) + b"\0" * 36
    hdrl = b"hdrl" + b"avih" + struct.pack("<I", len(avih)) + avih
    return b"RIFF" + struct.pack("<I", 4 + 8 + len(hdrl)) + b"AVI " + b"LIST" + struct.pack("<I", len(hdrl)) + hdrl


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._dir = library._dir
        library._dir = lambda: os.path.join(self.tmp, "cache")
        os.makedirs(library._dir())

    def tearDown(self):
        library._dir = self._dir
        lc.SCHEDULES.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, rel, data):
        p = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
        return p


class TestLengths(Temp):
    def test_mp4_mkv_avi(self):
        self.assertAlmostEqual(folders.duration(self.put("a.mp4", mp4(5400.5))), 5400.5, places=2)
        self.assertAlmostEqual(folders.duration(self.put("b.mkv", mkv(1320.25))), 1320.25, places=2)
        self.assertAlmostEqual(folders.duration(self.put("c.avi", avi(60))), 60.0, places=2)
        self.assertEqual(folders.duration(self.put("d.mkv", b"\0" * 64)), 0.0)        # a damaged file: no length
        self.assertEqual(folders.duration(os.path.join(self.tmp, "nope.mp4")), 0.0)


class TestFolders(Temp):
    def test_movies_shows_and_clips(self):
        self.put("Movies/Some.Film.(1999).1080p.mp4", mp4(6000))
        self.put("Movies/Broken.mkv", b"\0" * 32)
        self.put("Movies/notes.txt", b"hi")
        self.put("Shows/Alpha/Season 1/Alpha S01E02 The Pilot.mkv", mkv(1320))
        self.put("Shows/Alpha/Season 1/Alpha.S01E01.mkv", mkv(1300))
        self.put("Bumps/bump1.avi", avi(15))
        fs = folders.Folders([{"path": os.path.join(self.tmp, "Movies"), "kind": "movie"},
                              {"path": os.path.join(self.tmp, "Shows"), "kind": "show", "name": "My Shows"},
                              {"path": os.path.join(self.tmp, "Bumps"), "kind": "clip"}])
        idx = library.build([fs])
        secs = {s.title: s for s in idx.sections.values()}
        self.assertEqual(sorted(secs), ["Bumps", "Movies", "My Shows"])
        film = secs["Movies"].items
        self.assertEqual([(i["title"], i["year"], round(i["duration"])) for i in film], [("Some Film", 1999, 6000)])
        eps = sorted(secs["My Shows"].items, key=lambda i: i["episode"])
        self.assertEqual([(i["title"], i["season"], i["episode"], i["name"]) for i in eps],
                         [("Alpha", 1, 1, ""), ("Alpha", 1, 2, "The Pilot")])
        self.assertTrue(secs["Bumps"].breaks)
        c = lc.new_channel("Alpha", [{"section": secs["My Shows"].key, "kind": "all"}], "playlist")
        tl = lc.Timeline(c, idx, store=False)
        self.assertEqual([i["name"] for g in tl.groups for i in g["items"]], ["", "The Pilot"])
        s = lc.stream(SimpleNamespace(config=SimpleNamespace()), eps[1], 30)
        self.assertEqual((os.path.normpath(s["video"]), s["base"]),
                         (os.path.normpath(os.path.join(self.tmp, "Shows/Alpha/Season 1/Alpha S01E02 The Pilot.mkv")), 0.0))
        os.remove(s["video"])
        with self.assertRaises(PlexError) as ctx:
            lc.stream(None, eps[1], 0)
        self.assertTrue(lc.broken(ctx.exception))                      # gone: the next title, not the stand-by
        again = library.build([fs])                                    # unchanged files: their lengths not read again
        self.assertEqual(len(again.sections), 3)


class FakeJellyfin(BaseHTTPRequestHandler):
    VIEWS = [{"Id": "v1", "Name": "Movies", "CollectionType": "movies"},
             {"Id": "v2", "Name": "TV", "CollectionType": "tvshows"},
             {"Id": "v3", "Name": "Photos", "CollectionType": "photos"}]
    ITEMS = {"v1": {"Movie": [{"Id": "m1", "Name": "Heist", "Type": "Movie", "ProductionYear": 1995, "RunTimeTicks": 60000000000,
                               "Genres": ["Action"], "MediaSources": [{}]},
                              {"Id": "m2", "Name": "Jelly Only", "Type": "Movie", "ProductionYear": 2001,
                               "RunTimeTicks": 54000000000, "Genres": ["Comedy"], "MediaSources": [{}]}]},
             "v2": {"Series": [{"Id": "s1", "Name": "Delta", "Type": "Series", "ProductionYear": 1997, "Genres": ["Drama"]}],
                    "Episode": [{"Id": f"e{n}", "Name": f"Ep {n}", "Type": "Episode", "SeriesId": "s1", "SeriesName": "Delta",
                                 "ParentIndexNumber": 1, "IndexNumber": n, "RunTimeTicks": 13200000000,
                                 "MediaSources": [{}]} for n in (1, 2, 3)]}}

    def log_message(self, *a):
        pass

    def reply(self, d, code=200):
        body = json.dumps(d).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        d = json.loads(self.rfile.read(n))
        if self.path == "/Users/AuthenticateByName" and d == {"Username": "viv", "Pw": "pw"}:
            return self.reply({"User": {"Id": "u1"}, "AccessToken": "tok"})
        self.reply({}, 401)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path == "/System/Info/Public":
            return self.reply({"ServerName": "Den", "ProductName": "Jellyfin Server"})
        if self.headers.get("X-Emby-Token") != "tok":
            return self.reply({}, 401)
        if u.path == "/Users/u1/Views":
            return self.reply({"Items": self.VIEWS})
        if u.path == "/Users/u1/Items":
            pool = self.ITEMS.get(q.get("ParentId"), {})
            items = pool.get(q.get("IncludeItemTypes"), []) if "IncludeItemTypes" in q else sum(pool.values(), [])
            s, n = int(q.get("StartIndex", 0)), int(q.get("Limit", 100))
            return self.reply({"Items": items[s:s + n], "TotalRecordCount": len(items)})
        if u.path.startswith("/Users/u1/Items/"):
            iid = u.path.rsplit("/", 1)[1]
            for pool in self.ITEMS.values():
                for items in pool.values():
                    for i in items:
                        if i["Id"] == iid:
                            return self.reply(i)
            return self.reply({}, 404)
        self.reply({}, 404)


class TestJellyfin(Temp):
    def setUp(self):
        super().setUp()
        self.srv = HTTPServer(("127.0.0.1", 0), FakeJellyfin)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        super().tearDown()

    def test_sign_in_read_play_and_fold_duplicates(self):
        with self.assertRaises(Exception):
            jellyfin.sign_in(self.url, "viv", "wrong")
        s = jellyfin.sign_in(self.url, "viv", "pw", "dev1")
        self.assertEqual((s["token"], s["user_id"], s["name"], s["kind"]), ("tok", "u1", "Den", "Jellyfin"))
        self.assertNotIn("pw", json.dumps(s))                          # the password isn't kept
        cfg = SimpleNamespace(media_servers=[s])
        cl = jellyfin.clients(cfg)[0]
        metas = cl.library_sections()
        self.assertEqual([(m["key"], m["kind"], m["stamp"]) for m in metas], [("j1_v1", "movie", "2"), ("j1_v2", "show", "4")])
        plex = index()

        class Plex:                                                    # the Plex libraries, as if read
            def library_sections(self):
                return [{"key": k, "title": sec.title, "kind": sec.kind, "stamp": sec.stamp} for k, sec in plex.sections.items()]

            def fetch_section(self, meta, old=None):
                return plex.sections[meta["key"]]
        idx = library.build([Plex(), cl])
        jm = idx.sections["j1_v1"]
        self.assertEqual([i["title"] for i in jm.items], ["Jelly Only"])         # Heist (1995) kept from Plex
        self.assertIn("p901", [i["id"] for i in idx.sections["38"].items])
        tv = idx.sections["j1_v2"]
        self.assertEqual(([i["name"] for i in tv.items], tv.shows["J1:s1"]["title"]), (["Ep 1", "Ep 2", "Ep 3"], "Delta"))
        c = lc.new_channel("Delta", [{"section": "j1_v2", "kind": "show", "value": "J1:s1"}], "playlist")
        tl = lc.Timeline(c, idx, store=False)
        self.assertEqual(len(tl.entries), 3)
        app = SimpleNamespace(config=SimpleNamespace(media_servers=[s], plex_quality="Original"))
        e = tv.items[1]
        got = lc.stream(app, e, 100)
        self.assertEqual((got["video"], got["headers"]), (f"{self.url}/Videos/e2/stream?static=true", {"X-Emby-Token": "tok"}))
        with self.assertRaises(Exception) as ctx:
            lc.stream(app, dict(e, plex="J1:gone"), 0)
        self.assertTrue(lc.broken(ctx.exception))
        self.srv.shutdown()                                            # the server goes away
        self.srv.server_close()
        old, jellyfin.TIMEOUT = jellyfin.TIMEOUT, 2
        try:
            idx2 = library.build([Plex(), cl])
        finally:
            jellyfin.TIMEOUT = old
        self.assertIn("j1_v2", idx2.sections)                          # what was read of it last


if __name__ == "__main__":
    unittest.main()
