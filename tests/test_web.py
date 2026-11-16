"""Phase 7: Cathode's web page and outputs, over real HTTP on this machine.
The page and its state; keys, tuning and edits sent from it; the M3U,
XMLTV and HDHomeRun answers; a stream sent to the programme on now; what
stays shut when off; only this network answered."""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import libchannels as lc, library, lineup, sync, videochannels as vc, web
from tests.test_library import index
from tests.test_sync import App


class Web(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._dir = library._dir
        library._dir = lambda: self.tmp
        app = self.app = App("aaaa")
        app.config.library_channels = [lc.new_channel("Laugh Track", [{"section": "51", "kind": "all"}])]
        app.channels = vc.add_to(app.channels, app.config)          # (the library channel placed)
        app.lineup_all = list(app.channels)
        app.press = lambda key: None
        app.relineup = lambda: setattr(app, "channels", lineup.apply(app.lineup_all, app.config))
        app.live = SimpleNamespace(channel=app.channels[0], tune=lambda i: setattr(app, "tuned", i))
        lc.rebuild(app)
        app.run_posted()
        app.config.web_remote = app.config.share_channels = True
        self.s = sync.Sync(app)
        app.sync = self.s
        self.assertTrue(self.s.serve(0, host="127.0.0.1"))
        self.base = f"http://127.0.0.1:{self.s.port}"

    def tearDown(self):
        self.s.stop()
        library._dir = self._dir
        lc.SCHEDULES.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8")

    def post(self, body):
        req = urllib.request.Request(self.base + "/api/do", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())["said"]


class TestPage(Web):
    def test_the_page_and_its_state(self):
        code, kind, body = self.get("/")
        self.assertEqual((code, kind.split(";")[0]), (200, "text/html"))
        self.assertIn("<title>Cathode</title>", body)
        st = json.loads(self.get("/api/state")[2])
        self.assertEqual(st["on"]["number"], self.app.channels[0].number)
        self.assertIn("Laugh Track", [c["name"] for c in st["channels"]])
        lt = next(m for m in st["made"] if m["name"] == "Laugh Track")
        self.assertEqual((lt["kind"], lt["order"]), ("library", "cyclic_shuffle"))
        self.assertIn(["mix", "Mix"], lt["orders"])

    def test_keys_tuning_edits_and_channel_settings(self):
        app = self.app
        self.assertEqual(self.post({"do": "key", "key": "chup"}), "ok")
        self.assertEqual(self.post({"do": "key", "key": "selfdestruct"}), "no such key")
        fn, a, k = app.posted.pop(0)
        self.assertEqual(a, ("CH_UP",))
        target = app.channels[1].number
        self.assertEqual(self.post({"do": "tune", "number": target}), "ok")
        app.run_posted()
        self.assertEqual(app.tuned, 1)
        url = app.channels[0].url
        self.post({"do": "edit", "url": url, "name": "Renamed", "number": "10.5"})
        self.post({"do": "edit", "url": app.channels[1].url, "hide": True})
        app.run_posted()
        self.assertEqual(app.config.channel_edits[url], {"name": "Renamed", "number": 10.5})
        self.assertNotIn(app.lineup_all[1], app.channels)
        st = json.loads(self.get("/api/state")[2])
        self.assertIn(app.lineup_all[1].url, [h["url"] for h in st["hidden"]])
        cid = app.config.library_channels[0]["id"]
        old_place = lc.place
        lc.place = lambda app: None
        try:
            self.post({"do": "channel", "id": cid, "order": "block_shuffle", "hours": [6, 2], "breaks": True, "mid": "off"})
            app.run_posted()
        finally:
            lc.place = old_place
        c = app.config.library_channels[0]
        self.assertEqual((c["order"], c["hours"]), ("block_shuffle", [6, 2]))
        self.assertEqual(self.post({"do": "nonsense"}), "not understood")


class TestQr(unittest.TestCase):
    def test_the_address_as_a_qr_code_on_every_skin(self):
        import pygame
        from tests.test_skins import FakeApp as SkinApp
        from cathode.skins import skin_classes
        from cathode.screens.qrcode import QrCode
        from cathode import remote as R
        from cathode.config import Config
        self.assertTrue(Config("").share_channels)                      # sharing on from the start
        pygame.display.init()
        for name, cls in skin_classes().items():
            app = SkinApp()
            skin = cls(app)
            app.skin = skin
            popped = []
            app.pop = popped.append
            q = QrCode(app, "http://10.0.0.215:47810", "Phone remote", "Point your phone's camera here.")
            W, H = skin.canvas
            c = pygame.Surface((W, H), pygame.SRCALPHA)
            skin.draw(c, q)
            self.assertEqual(tuple(c.get_at((W // 2, H // 2 - int(H * 0.25))))[:3] in ((0, 0, 0), (255, 255, 255)), True)
            self.assertFalse(q.handle(R.VOL_UP))                         # the volume still works
            self.assertTrue(q.handle(R.BACK))
            self.assertEqual(popped, [q])


class TestOutputs(Web):
    def test_m3u_xmltv_and_hdhomerun(self):
        lib = next(ch for ch in self.app.channels if lc.is_library(ch))
        for _ in range(200):                    # the guide is built off the UI thread: wait for it
            self.app.run_posted()
            if (getattr(self.app, "video_programmes", None) or {}).get(lib.epg_id):
                break
            time.sleep(0.02)
        code, kind, m3u = self.get("/lineup.m3u")
        self.assertTrue(m3u.startswith("#EXTM3U"))
        self.assertIn(f'tvg-chno="{lib.number:g}"', m3u)
        self.assertIn(f"{self.base}/stream/{vc.cid_of(lib)}", m3u)
        self.assertNotIn("Ch1", m3u)                                   # the playlist's own channels: not ours to give
        xml = self.get("/xmltv.xml")[2]
        self.assertIn(f'<channel id="{lib.epg_id}">', xml)
        self.assertIn("<programme channel=", xml)
        disc = json.loads(self.get("/discover.json")[2])
        self.assertEqual((disc["LineupURL"], disc["DeviceID"]), (f"{self.base}/lineup.json", "AAAA"))
        hd = json.loads(self.get("/lineup.json")[2])
        self.assertEqual(hd, [{"GuideNumber": f"{lib.number:g}", "GuideName": "Laugh Track",
                               "URL": f"{self.base}/stream/{vc.cid_of(lib)}"}])
        self.assertEqual(json.loads(self.get("/lineup_status.json")[2])["ScanInProgress"], 0)

    def test_a_stream_goes_to_the_programme_on_now(self):
        lib = next(ch for ch in self.app.channels if lc.is_library(ch))
        old = web.stream_url
        web.stream_url = lambda app, cid: f"http://plex/transcode?cid={cid}&X-Plex-Token=t"
        try:
            req = urllib.request.Request(f"{self.base}/stream/{vc.cid_of(lib)}")
            opener = urllib.request.build_opener(type("NoRedirect", (urllib.request.HTTPRedirectHandler,),
                                                      {"redirect_request": lambda *a, **k: None}))
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                opener.open(req, timeout=5)
            self.assertEqual(ctx.exception.code, 302)
            self.assertEqual(ctx.exception.headers["Location"], f"http://plex/transcode?cid={vc.cid_of(lib)}&X-Plex-Token=t")
        finally:
            web.stream_url = old

    def test_what_is_off_stays_shut(self):
        self.app.config.share_channels = False
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/lineup.m3u")
        self.assertEqual(ctx.exception.code, 404)
        self.app.config.web_remote = False
        with self.assertRaises(urllib.error.HTTPError):
            self.get("/")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post({"do": "key", "key": "up"})
        self.assertEqual(ctx.exception.code, 403)

    def test_only_this_network(self):
        for addr, ok in (("192.168.1.20", True), ("10.0.0.215", True), ("127.0.0.1", True), ("172.16.4.4", True),
                         ("8.8.8.8", False), ("100.64.1.1", False), ("nonsense", False)):
            self.assertEqual(web.local(addr), ok, addr)


if __name__ == "__main__":
    unittest.main()
