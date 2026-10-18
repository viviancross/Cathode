"""Menus, the on-screen keyboard, and the login-item files. Menu and keyboard
cases carried over from 3.4's test_menu, test_menu_exit and test_osk."""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from cathode import autostart, remote as R  # noqa: E402
from cathode.screens.menu import Item, Keyboard, Menu  # noqa: E402


class FakeApp:
    def __init__(self):
        self.screens = []

    def push(self, s):
        self.screens.append(s)

    def pop(self, s=None):
        self.screens.remove(s or self.screens[-1])

    def invalidate(self):
        pass


def menu(app, n=3, **kw):
    ran = []
    items = [Item(f"item{i}", (lambda i=i: ran.append(i)), **kw) for i in range(n)]
    m = Menu(app, "T", items)
    app.push(m)
    return m, ran


class TestMenu(unittest.TestCase):
    def test_digits_pick_rows_like_a_numbered_box_menu(self):
        app = FakeApp()
        m, ran = menu(app)
        m.handle(R.DIGITS[2])
        self.assertEqual(ran, [1])

    def test_a_digit_past_the_end_does_nothing(self):
        app = FakeApp()
        m, ran = menu(app)
        m.handle(R.DIGITS[9])
        self.assertEqual(ran, [])

    def test_movement_wraps_and_skips_disabled_rows(self):
        app = FakeApp()
        m = Menu(app, "T", [Item("a"), Item("b", enabled=False), Item("c")])
        m.handle(R.DOWN)
        self.assertEqual(m.cursor, 2)
        m.handle(R.DOWN)
        self.assertEqual(m.cursor, 0)

    def test_back_pops_a_submenu_then_closes_at_the_root(self):
        app = FakeApp()
        m = Menu(app, "T", [Item("sub", submenu=lambda: [Item("x")])])
        app.push(m)
        m.handle(R.SELECT)
        self.assertEqual(m.title, "sub")
        m.handle(R.BACK)
        self.assertEqual(m.title, "T")
        m.handle(R.BACK)
        self.assertNotIn(m, app.screens)

    def test_exit_closes_from_any_depth(self):
        app = FakeApp()
        m = Menu(app, "T", [Item("sub", submenu=lambda: [Item("x")])])
        app.push(m)
        m.handle(R.SELECT)
        m.handle(R.EXIT)
        self.assertNotIn(m, app.screens)

    def test_left_right_adjust_a_value_in_place(self):
        app = FakeApp()
        got = []
        m = Menu(app, "T", [Item("v", value=lambda: "x", adjust=got.append)])
        m.handle(R.RIGHT)
        m.handle(R.LEFT)
        self.assertEqual(got, [1, -1])

    def test_volume_still_reaches_live_tv(self):
        app = FakeApp()
        m, _ = menu(app)
        self.assertFalse(m.handle(R.VOL_UP))


class GridSkin:
    """Two columns of five, filled a column at a time."""
    def menu_cols(self, menu):
        return 2

    def menu_rows(self, menu):
        return 5


class TestGridMenu(unittest.TestCase):
    def test_arrows_follow_the_columns_as_drawn(self):
        app = FakeApp()
        app.skin = GridSkin()
        m, _ = menu(app, n=7)                 # 1-5 down the left, 6-7 down the right
        moves = []
        for a in (R.RIGHT, R.DOWN, R.DOWN, R.LEFT, R.DOWN, R.DOWN, R.DOWN, R.RIGHT, R.UP):
            m.handle(a)
            moves.append(m.cursor)
        # 0 -> 5 (across), 6, 6 (column end), 1 (back across), 2, 3, 4, 6 (shorter column: its last), 5
        self.assertEqual(moves, [5, 6, 6, 1, 2, 3, 4, 6, 5])


class TestKeyboard(unittest.TestCase):
    def setUp(self):
        self.app = FakeApp()
        self.result = []
        with mock.patch.object(pygame.key, "start_text_input"):
            self.kb = Keyboard(self.app, "p", self.result.append, initial="abc")
        self.app.push(self.kb)
        patcher = mock.patch.object(pygame.key, "stop_text_input")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_caret_starts_at_the_end(self):
        self.assertEqual(self.kb.caret, 3)

    def test_insert_and_backspace_work_at_the_caret(self):
        self.kb.handle(R.CH_DOWN)             # caret left
        self.kb.insert("X")
        self.assertEqual(self.kb.value, "abXc")
        self.kb.handle(R.BACK)
        self.assertEqual(self.kb.value, "abc")

    def test_the_caret_clamps(self):
        for _ in range(10):
            self.kb.handle(R.CH_UP)
        self.assertEqual(self.kb.caret, 3)
        for _ in range(10):
            self.kb.handle(R.CH_DOWN)
        self.assertEqual(self.kb.caret, 0)

    def test_clear_resets_the_caret(self):
        self.kb._press("CLEAR")
        self.assertEqual((self.kb.value, self.kb.caret), ("", 0))

    def test_done_hands_back_the_text(self):
        self.kb.text(" d ")
        self.kb._press("DONE")
        self.assertEqual(self.result, ["abc d"])
        self.assertNotIn(self.kb, self.app.screens)

    def test_cancel_hands_back_none(self):
        self.kb.handle(R.EXIT)
        self.assertEqual(self.result, [None])

    def test_typed_control_characters_are_dropped(self):
        self.kb.text("x\x07y")
        self.assertEqual(self.kb.value, "abcxy")

    def test_shift_and_symbols_change_the_keys(self):
        self.kb._press("SHIFT")
        self.assertIn("Q", self.kb.grid()[1])
        self.kb._press("SYM")
        self.assertIn("@", self.kb.grid()[0])


class TestAutostart(unittest.TestCase):
    def test_the_mac_agent_runs_at_login_and_escapes_paths(self):
        text = autostart.mac_plist_text(["/Apps/A & B/python", "main.py"])
        self.assertIn("<key>RunAtLoad</key>", text)
        self.assertIn("A &amp; B", text)

    def test_the_linux_entry_quotes_its_command(self):
        text = autostart.linux_desktop_text(["/opt/my apps/python", "main.py"])
        self.assertIn("Exec='/opt/my apps/python' main.py", text)

    @unittest.skipIf(sys.platform in ("win32", "darwin"), "file-based autostart only")
    def test_turning_it_on_and_off_on_linux(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": d}):
            autostart.set_enabled(True)
            self.assertTrue(autostart.enabled())
            autostart.set_enabled(False)
            self.assertFalse(autostart.enabled())


class SetupApp(FakeApp):
    """Enough of the app for the first-run setup prompts."""
    def __init__(self, playlists=None, url=""):
        from cathode.config import Config
        super().__init__()
        self.config = Config("")
        self.config.playlists = list(playlists or [])
        self.config.playlist_url = url
        self.switched = []
        self.screens.append(object())       # live TV, always underneath

    def top(self):
        return self.screens[-1]

    def switch_playlist(self, pl):
        self.switched.append(pl)

    def post(self, fn, *a, **k):
        fn(*a, **k)

    def quit(self):
        pass


class FakeSkin:
    theme = "native"

    def theme_choices(self):
        return [("native", "Original"), ("blue", "Blue"), ("custom", "Custom")]

    def theme_key(self):
        return self.theme

    def set_theme_key(self, k):
        self.theme = k

    def reload(self):
        pass

    def menu_cols(self, menu):
        return 1


class TestFirstRun(unittest.TestCase):
    def setUp(self):
        for name in ("start_text_input", "stop_text_input"):
            patcher = mock.patch.object(pygame.key, name)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _type(self, app, text):
        kb = app.top()
        self.assertIsInstance(kb, Keyboard)
        kb.value = text
        kb._press("DONE")
        return kb.prompt

    def _checked(self, n=5, err="", server=None):
        from cathode import menus
        patcher = mock.patch.object(menus, "_check_playlist", lambda app, url, done: done(n, err))
        patcher.start()
        self.addCleanup(patcher.stop)
        finder = mock.patch.object(menus, "_find_server", lambda app, address, done: done(server))
        finder.start()
        self.addCleanup(finder.stop)

    def test_setup_asks_for_the_addresses_then_the_name(self):
        from cathode import menus
        self._checked()
        app = SetupApp()
        app.toast = lambda *a: None
        menus.add_playlist(app)
        prompts = [self._type(app, "http://provider/list.m3u"), self._type(app, ""), self._type(app, "")]
        self.assertIn("Server address", prompts[0])          # a playlist link is taken as it is
        self.assertIn("Guide address", prompts[1])
        self.assertIn("Name", prompts[2])
        self.assertEqual(app.switched, [{"name": "My Channels", "playlist_url": "http://provider/list.m3u",
                                         "epg_url": ""}])

    def test_a_saved_playlist_can_be_renamed(self):
        from cathode import menus
        pl = {"name": "Old", "playlist_url": "a"}
        app = SetupApp(playlists=[pl], url="a")
        app.toast = lambda *a: None
        m = Menu(app, "CHANNELS", menus.channel_items(app))
        app.push(m)
        m.activate(0)                                   # the playlist's page
        rename = next(i for i, it in enumerate(m.items) if it.label.startswith("Rename"))
        m.activate(rename)
        self._type(app, "Movies")
        self.assertEqual(pl["name"], "Movies")
        self.assertIn("Movies", m.items[0].label)       # back on the list, renamed

    def test_the_look_wizard_previews_as_the_cursor_moves(self):
        from cathode import menus
        app = SetupApp()
        skins = []
        app.skin = FakeSkin()
        app.set_skin = lambda k: (skins.append(k), setattr(app.config, "skin", k))
        menus.open_welcome(app)
        m = app.top()
        self.assertEqual(m.title, "WELCOME TO CATHODE")         # what's coming, and what to have ready
        self.assertIn("M3U", m.items[0].help)
        m.handle(R.SELECT)
        self.assertEqual(m.title, "1/3 CHOOSE YOUR BOX")
        m.handle(R.DOWN)
        self.assertEqual(skins, ["indirect"])           # the page redrew as that box
        m.handle(R.SELECT)
        self.assertEqual(m.title, "2/3 CHOOSE COLORS")
        m.handle(R.DOWN)
        self.assertEqual(app.skin.theme, "blue")       # recoloured on the way past
        m.handle(R.SELECT)
        self.assertEqual(m.title, "3/3 YOUR CHANNELS")
        self.assertTrue(app.config.look_chosen)
        m.handle(R.BACK)
        self.assertEqual(m.title, "2/3 CHOOSE COLORS")
        app2 = SetupApp()
        app2.config.look_chosen = True
        menus.open_welcome(app2)
        self.assertEqual(app2.top().title, "WELCOME TO CATHODE")

    def test_a_bad_address_is_asked_for_again_with_what_was_typed(self):
        from cathode import menus
        self._checked(0, "the server said no")
        app = SetupApp()
        said = []
        app.toast = lambda text, *a: said.append(text)
        menus.add_playlist(app)
        prompt = self._type(app, "http://provider/typo.m3u")
        self.assertIn("Server address", prompt)
        self.assertEqual(app.top().value, "http://provider/typo.m3u")     # back, to fix it
        self.assertIn("the server said no", said[-1])

    def test_a_playlists_addresses_can_be_changed(self):
        from cathode import menus
        pl = {"name": "Mine", "playlist_url": "http://old/list.m3u", "epg_url": ""}
        app = SetupApp(playlists=[pl], url="http://old/list.m3u")
        app.toast = lambda *a: None
        items = menus.playlist_items(app, pl)
        self.assertEqual(next(it for it in items if it.label == "Guide address").value(), "None")
        next(it for it in items if it.label == "Guide address").action()
        self._type(app, "http://old/guide.xml")
        self.assertEqual(pl["epg_url"], "http://old/guide.xml")
        self.assertEqual(app.switched[-1], pl)          # in use: loaded again

    def test_adding_another_playlist_asks_for_its_name_last(self):
        from cathode import menus
        self._checked()
        app = SetupApp(playlists=[{"name": "Old", "playlist_url": "a"}], url="a")
        app.toast = lambda *a: None
        menus.add_playlist(app)
        prompts = [self._type(app, "b.m3u"), self._type(app, "g.xml"), self._type(app, "Sports")]
        self.assertIn("Name", prompts[2])
        self.assertEqual(app.switched[0]["name"], "Sports")

    def test_menu_reopens_the_welcome_until_channels_are_set_up(self):
        from cathode import menus
        with mock.patch.object(menus, "open_welcome") as welcome, mock.patch.object(menus, "open_main") as main:
            app = SetupApp()
            app.push(object())
            menus.handles_menu_button(app, R.MENU)
            app2 = SetupApp(playlists=[{"name": "Mine", "playlist_url": "x"}], url="x")
            app2.push(object())
            menus.handles_menu_button(app2, R.MENU)
        welcome.assert_called_once_with(app)
        main.assert_called_once_with(app2)


class TestLoadErrors(unittest.TestCase):
    def test_each_failure_reads_in_plain_words(self):
        import urllib.error
        from cathode.app import load_error_text
        cases = [(urllib.error.HTTPError("u", 404, "nf", {}, None), "isn't there"),
                 (urllib.error.HTTPError("u", 403, "no", {}, None), "refused it (403)"),
                 (FileNotFoundError("x"), "no file"),
                 (urllib.error.URLError(ConnectionRefusedError()), "didn't answer"),
                 (TimeoutError(), "didn't answer"),
                 (ValueError("unknown url type"), "isn't a playlist address"),
                 (RuntimeError("?"), "can read")]
        for e, words in cases:
            with self.subTest(e=type(e).__name__):
                self.assertIn(words, load_error_text(e))


class TestSubtitleFonts(unittest.TestCase):
    def test_the_closed_caption_font_is_offered_by_name_once(self):
        import pygame
        from cathode import menus
        pygame.font.init()
        fonts = menus._subtitle_fonts()
        families = [f for f, _ in fonts]
        self.assertEqual(len(families), len(set(families)))
        self.assertIn(("Space Mono", "Closed Caption"), fonts)     # mpv matches the family


class TestServerSetup(unittest.TestCase):
    """One address: a Tunarr or ErsatzTV fills in both links and the name."""

    def test_a_known_server_fills_in_the_links_and_skips_the_guide_step(self):
        from cathode import menus, servers
        from test_menus import TestFirstRun
        TestFirstRun._checked(self, 26, server=servers.Server("tunarr", "http://10.0.0.215:8000", "2026.10.1"))
        app = SetupApp()
        said = []
        app.toast = lambda text, *a: said.append(text)
        menus.add_playlist(app)
        TestFirstRun._type(self, app, "10.0.0.215:8000")
        self.assertEqual(app.switched, [{"name": "Tunarr", "server": "http://10.0.0.215:8000",
                                         "playlist_url": "http://10.0.0.215:8000/api/channels.m3u",
                                         "epg_url": "http://10.0.0.215:8000/api/xmltv.xml"}])
        self.assertIn("Found Tunarr 2026.10.1: 26 channels.", said)

    def test_an_address_that_is_no_server_goes_on_as_a_playlist_link(self):
        from cathode import menus
        from test_menus import TestFirstRun
        TestFirstRun._checked(self, 5, server=None)
        app = SetupApp()
        app.toast = lambda *a: None
        menus.add_playlist(app)
        TestFirstRun._type(self, app, "provider.example")
        self.assertIn("Guide address", app.top().prompt)    # checked as an M3U, then the guide is asked

    def test_what_the_servers_say_and_where_their_files_are(self):
        from cathode import servers
        self.assertEqual(servers.identify({"tunarr": "2026.10.1", "ffmpeg": "n8"}), ("tunarr", "2026.10.1"))
        self.assertEqual(servers.identify({"apiVersion": 3, "appVersion": "v26.11.3"}), ("ersatztv", "26.11.3"))
        self.assertIsNone(servers.identify({"FriendlyName": "HDHomeRun"}))
        self.assertIsNone(servers.identify("<html>"))
        e = servers.Server("ersatztv", "http://nas:8409", "26.11.3")
        self.assertEqual(e.playlist_url, "http://nas:8409/iptv/channels.m3u?mode=segmenter")
        self.assertEqual(e.epg_url, "http://nas:8409/iptv/xmltv.xml")
        self.assertEqual(str(e), "ErsatzTV 26.11.3")
        self.assertEqual(servers.candidates("10.0.0.215"),
                         ["http://10.0.0.215", "http://10.0.0.215:8000", "http://10.0.0.215:8409"])
        self.assertEqual(servers.candidates("https://tv.example.com:9000/"), ["https://tv.example.com:9000"])
        self.assertTrue(servers.looks_like_address("10.0.0.215:8000"))
        self.assertFalse(servers.looks_like_address("http://provider/list.m3u"))
        self.assertFalse(servers.looks_like_address("C:/lists/x.m3u"))

    def test_a_servers_own_localhost_means_the_server(self):
        from cathode.net import as_seen_from
        base = "http://10.0.0.215:8000/api/channels.m3u"
        self.assertEqual(as_seen_from("http://localhost:8000/images/a.png", base),
                         "http://10.0.0.215:8000/images/a.png")
        for same in ("http://10.0.0.215:8000/images/a.png", "https://upload.example/a.png", ""):
            self.assertEqual(as_seen_from(same, base), same)
        self.assertEqual(as_seen_from("http://localhost/a.png", "http://localhost:8000/x.m3u"), "http://localhost/a.png")
        self.assertEqual(as_seen_from("http://localhost/a.png", "C:/lists/x.m3u"), "http://localhost/a.png")


class TestDiagnosticsZip(unittest.TestCase):
    def test_the_zip_holds_the_logs_and_a_config_without_tokens(self):
        import json
        import zipfile
        from types import SimpleNamespace
        from cathode import diagnostics_zip, paths
        from cathode.config import Config
        cfg = Config("")
        cfg.plex_token, cfg.plex_user_name, cfg.skin = "secret-token", "Vivian", "plate_hd"
        app = SimpleNamespace(config=cfg, gfx=SimpleNamespace(version="3.2", renderer="Test GPU", size=(1280, 720)),
                              video=None, fullscreen=False)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(paths, "cache_dir", lambda: d):
            open(os.path.join(d, "cathode.log"), "w").write("[cathode] Tuning to [4] Test Card\n")
            path = diagnostics_zip.write(app, out_dir=d)
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
                self.assertEqual(names, {"system.txt", "config.json", "cathode.log"})
                conf = json.loads(z.read("config.json"))
                self.assertEqual(conf["plex_token"], "<removed>")
                self.assertEqual(conf["plex_user_name"], "<removed>")
                self.assertEqual(conf["skin"], "plate_hd")
                self.assertNotIn("secret-token", z.read("config.json").decode())
                self.assertIn("Test GPU", z.read("system.txt").decode())
                self.assertIn("Tuning to", z.read("cathode.log").decode())


if __name__ == "__main__":
    unittest.main()
