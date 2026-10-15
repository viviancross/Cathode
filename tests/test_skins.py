"""Every skin draws every screen without a window, at its own canvas size,
in each of its colour themes: a skin-specific crash can't hide on a screen
nobody happened to open."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from cathode.config import Config  # noqa: E402
from cathode.epg import EPG, Program  # noqa: E402
from cathode.playlist import Channel  # noqa: E402
from cathode.skins import skin_classes  # noqa: E402


class FakeVideo:
    volume, muted, paused = 40, False, False

    def buffered_behind(self):
        return 30.0


class FakeApp:
    def __init__(self):
        from cathode.screens.live import LiveTV
        self.config = Config("")
        self.channels = [Channel(number=n, name=f"Channel {n}", url="u", epg_id=f"c{n}", group="News")
                         for n in (2, 4, 5, 7, 9, 11, 13)]
        self.epg = EPG()
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        for ch in self.channels:
            self.epg.add_programs(ch.epg_id, [
                Program(ch.epg_id, f"Show {i}", now + timedelta(minutes=30 * i),
                        now + timedelta(minutes=30 * (i + 1)), description="A description " * 8,
                        category="News", rating="TV-PG") for i in range(-2, 10)])
        self.video = FakeVideo()
        self.logos = None
        self.weather = None
        self.ondemand = None
        self.screens = []
        self.start_channel = None
        self.skin = None
        self.live = LiveTV(self)

    def after(self, s, fn):
        return [1e18, 0, fn, False]

    def cancel(self, t):
        pass

    def invalidate(self):
        pass

    def categories(self):
        return ["All", "Favorites", "News"]

    def channels_in(self, cat):
        return self.channels

    def is_favorite(self, ch):
        return ch.number == 4

    def push(self, s):
        self.screens.append(s)

    def pop(self, s=None):
        pass


def screens(app):
    from cathode.screens.boot import Boot
    from cathode.screens.browse import Browse
    from cathode.screens.diagnostics import Diagnostics
    from cathode.screens.guide import Guide
    from cathode.screens.menu import Item, Keyboard, Menu
    from cathode.screens.miniguide import MiniGuide
    from cathode.screens.screensaver import Screensaver
    live = app.live
    live.idx, live.phase = 1, "watch"
    live.show_banner()
    live.digits = "12"
    diag = Diagnostics.__new__(Diagnostics)
    diag.app, diag.stats = app, {"video-bitrate": 4e6, "width": 1280, "height": 720}
    pygame.key.start_text_input = lambda: None
    main = Menu(app, "MAIN MENU", [Item(f"Item {i}", lambda: None) for i in range(7)])
    sub = Menu(app, "SETTINGS", [Item("Value", value=lambda: "On", adjust=lambda d: None),
                                 Item("Sub", submenu=lambda: [])])
    return [live, Guide(app), Browse(app), MiniGuide(app), main, sub,
            Keyboard(app, "Prompt", lambda v: None, "text"), Boot(app), Screensaver(app), diag]


class TestEverySkinDrawsEveryScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.font.init()

    def test_all(self):
        for name, cls in skin_classes().items():
            app = FakeApp()
            app.config.skin = name
            skin = cls(app)
            app.skin = skin
            themes = [k for k, _ in skin.theme_choices() if k != "custom"][:3]
            for theme in themes:
                skin.set_theme_key(theme)
                skin.reload()
                canvas = pygame.Surface(skin.canvas, pygame.SRCALPHA)
                for s in screens(app):
                    with self.subTest(skin=name, theme=theme, screen=s.name):
                        canvas.fill((0, 0, 0, 0))
                        skin.hits = []
                        skin.draw(canvas, s)
                        if s.name in ("live", "guide", "menu", "keyboard", "boot", "diagnostics"):
                            self.assertIsNotNone(canvas.get_bounding_rect(min_alpha=1).w)

    def test_box_skins_cut_to_black_and_classic_keeps_static(self):
        classes = skin_classes()
        self.assertEqual(classes["classic"].tune_cover, "static")
        for name in ("indirect", "indirect_hd", "plate", "plate_hd"):
            self.assertEqual(classes[name].tune_cover, "black", name)

    def test_sd_skins_are_four_by_three(self):
        for name in ("indirect", "plate"):
            w, h = skin_classes()[name].canvas
            self.assertAlmostEqual(w / h, 4 / 3, places=2)

    def test_the_guide_keeps_its_video_box_on_the_canvas(self):
        for name, cls in skin_classes().items():
            app = FakeApp()
            skin = cls(app)
            x, y, w, h = skin.guide_video_box()
            W, H = skin.canvas
            self.assertTrue(0 <= x and 0 <= y and x + w <= W and y + h <= H, name)


if __name__ == "__main__":
    unittest.main()
