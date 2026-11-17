"""Phase 5: the lineup as edited. Hiding, renaming, renumbering (decimals),
an edit cleared bringing the channel's own back, packs as guide tabs, the
editor's pages, no playlist at all, an HDHomeRun tuner's lineup."""

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import lineup, playlist
from cathode.config import Config
from cathode.playlist import Channel


def chans():
    return [Channel(number=n, name=f"Ch{n}", url=f"u{n}") for n in (2, 4, 5, 7)]


class TestApply(unittest.TestCase):
    def test_hide_rename_renumber_and_back_as_it_came(self):
        cfg = Config("")
        cs = chans()
        lineup.edit(cfg, cs[1], hide=True)
        lineup.edit(cfg, cs[2], name="Local News", number=10.5)
        lineup.edit(cfg, cs[3], number=1)
        out = lineup.apply(cs, cfg)
        self.assertEqual([(c.number, c.name) for c in out], [(1, "Ch7"), (2, "Ch2"), (10.5, "Local News")])
        lineup.edit(cfg, cs[2], name=None, number=None)               # cleared: its own again
        lineup.edit(cfg, cs[1], hide=None)
        out = lineup.apply(cs, cfg)
        self.assertEqual([(c.number, c.name) for c in out], [(1, "Ch7"), (2, "Ch2"), (4, "Ch4"), (5, "Ch5")])
        self.assertEqual(cfg.channel_edits, {"u7": {"number": 1}})    # nothing left of the cleared ones

    def test_numbers(self):
        self.assertEqual([lineup.number(t) for t in ("12", "10.5", " 7 ", "0", "x", "100000", "3.0")],
                         [12, 10.5, 7, None, None, None, 3])

    def test_packs(self):
        cfg = Config("")
        cs = chans()
        cfg.packs = [{"name": "Kids", "keys": ["u4", "u7"]}, {"name": "", "keys": []}]
        self.assertEqual([p["name"] for p in lineup.packs(cfg)], ["Kids"])
        self.assertEqual([c.name for c in lineup.in_pack(cfg, "Kids", cs)], ["Ch4", "Ch7"])


class TestApp(unittest.TestCase):
    def test_packs_are_guide_tabs(self):
        from cathode.app import App
        from cathode.epg import EPG
        app = SimpleNamespace(config=Config(""), epg=EPG(), _cats=None)
        app.categories = lambda: App.categories(app)
        app.channels = chans()
        app.config.packs = [{"name": "Kids", "keys": ["u4"]}]
        cats = App.categories(app)
        self.assertEqual(cats[:3], ["All", "Favorites", "Kids"])
        self.assertEqual([c.name for c in App.channels_in(app, "Kids")], ["Ch4"])


class TestMaker(unittest.TestCase):
    def test_pages(self):
        from cathode import menus
        cfg = Config("")
        cs = chans()
        shown = []
        app = SimpleNamespace(config=cfg, lineup_all=cs, channels=cs, _cats=None)
        app.relineup = lambda: shown.append(lineup.apply(cs, cfg))
        pushed = []
        app.push = pushed.append
        app.top = lambda: SimpleNamespace(pages=[["Channels", [], 0], ["4  Ch4", [], 0]], refresh=lambda *a: None,
                                          back=lambda: None)
        app.toast = lambda *a, **k: None
        app.ondemand = SimpleNamespace(signed_in=False)
        app.toggle_favorite = lambda ch: cfg.favorites.append(ch.number)
        app.invalidate = lambda: None
        rows = menus.channels_tab(app)
        self.assertIn("2  Ch2", [it.label for it in rows])
        self.assertEqual(rows[0].label, "Add Custom Channel")
        page = {it.label: it for it in menus.channel_editor(app, cs[1])}
        page["Channel Visible"].action()
        self.assertEqual(cfg.channel_edits["u4"], {"hide": True})
        self.assertNotIn("Ch4", [c.name for c in shown[-1]])
        self.assertEqual(page["Channel Visible"].value(), "No")
        hidden = menus.hidden_items(app)
        self.assertEqual([it.label for it in hidden], ["Hide Empty Channels", "Hide Starter Channels", "Hide All",
                                                       "Show All", "4  Ch4"])
        hidden[4].action()                                             # Restore
        self.assertNotIn("u4", cfg.channel_edits)
        page["Favorite"].action()
        self.assertEqual(page["Favorite"].value(), "Yes")
        page["Channel Number"].action()
        pushed[-1].on_done("10.5")                                     # typed on the keyboard
        self.assertEqual(cfg.channel_edits["u4"].get("number"), 10.5)
        bug = {it.label: it for it in page["Screen Bug"].submenu()}    # the channel's own bug look
        bug["Position"].adjust(1)
        bug["Opacity"].adjust(1)
        self.assertEqual(cfg.channel_edits["u4"]["bug_look"], {"corner": "bottom left", "opacity": 20})
        bug["Show It"].action()
        self.assertTrue(cfg.channel_edits["u4"]["bug_look"]["off"])
        bug["As It Came"].action()
        self.assertNotIn("bug_look", cfg.channel_edits["u4"])
        page["As it came"].action()
        self.assertNotIn("u4", cfg.channel_edits)
        cfg.packs = [{"name": "Kids", "keys": []}]
        packs = page["Channel Packs"].submenu()
        packs[0].action()
        self.assertEqual(cfg.packs[0]["keys"], ["u4"])
        pp = {it.label: it for it in menus.pack_page(app, cfg.packs[0])}
        self.assertEqual(pp["Channels"].value(), "1")
        chs = pp["Channels"].submenu()
        chs[0].action()
        self.assertEqual(cfg.packs[0]["keys"], ["u4", "u2"])
        for it in rows + list(page.values()) + list(pp.values()):
            if it.value:
                self.assertIsInstance(it.value(), str)


class TestSources(unittest.TestCase):
    def test_no_playlist_is_empty_and_an_hdhomerun_lineup_loads(self):
        self.assertEqual(playlist.load(lineup.NONE), [])
        rows = [{"GuideNumber": "2.1", "GuideName": "WGBH", "URL": "http://tuner/auto/v2.1", "HD": 1},
                {"GuideNumber": "4", "GuideName": "WBZ", "URL": "http://tuner/auto/v4"},
                {"GuideName": "no url"}]

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps(rows).encode()
                self.send_response(200 if self.path == "/lineup.json" else 404)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            for src in (f"hdhomerun://127.0.0.1:{srv.server_address[1]}",
                        f"http://127.0.0.1:{srv.server_address[1]}/lineup.json"):
                got = playlist.load(src)
                self.assertEqual([(c.number, c.name, c.url, c.group) for c in got],
                                 [(2.1, "WGBH", "http://tuner/auto/v2.1", "HD"), (4, "WBZ", "http://tuner/auto/v4", "Antenna")])
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
