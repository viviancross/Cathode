"""Window shapes: a 16:9 skin grows taller on a 16:10 or 4:3 screen (more
rows, its foot at the real foot), a 4:3 skin keeps its shape between bars or
stretches to fill, and the picture keeps its aspect in a box of any shape."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame  # noqa: E402

from cathode.gfx import fit  # noqa: E402
from cathode.skins import seams, skin_classes  # noqa: E402
from test_skins import FakeApp, screens  # noqa: E402


def make(name):
    app = FakeApp()
    app.config.skin = name
    app.skin = skin_classes()[name](app)
    return app.skin


class TestFit(unittest.TestCase):
    def test_a_43_skin_pillarboxes_or_stretches(self):
        self.assertEqual(fit((640, 480), (1280, 720)), (160, 0, 960, 720))
        self.assertEqual(fit((640, 480), (1280, 720), stretch=True), (0, 0, 1280, 720))

    def test_a_169_canvas_grows_to_the_window_shape(self):
        for name in ("classic", "indirect_hd", "plate_hd"):
            skin = make(name)
            for window, canvas in (((1024, 768), (1280, 960)), ((1280, 800), (1280, 800)),
                                   ((1920, 1080), (1280, 720)), ((2560, 1080), (1280, 720)),
                                   ((1000, 1000), (1280, 960)), ((1366, 768), (1280, 720))):
                skin.fit_window(window)
                self.assertEqual(skin.canvas, canvas, (name, window))
                self.assertEqual(skin.grow, canvas[1] - 720)

    def test_a_43_skin_keeps_its_pixels(self):
        for name in ("indirect", "plate"):
            skin = make(name)
            self.assertFalse(skin.fit_window((1280, 720)))
            self.assertEqual(skin.canvas, type(skin).canvas)

    def test_a_taller_guide_lists_more_channels(self):
        for name, rows in (("classic", 10), ("indirect_hd", 11), ("plate_hd", 11), ("indirect", 6), ("plate", 4)):
            skin = make(name)
            skin.fit_window((1024, 768))
            self.assertEqual(skin.guide_rows, rows, name)

    def test_a_taller_on_demand_lists_more(self):
        from test_skins import page_screens
        for name in ("indirect_hd", "plate_hd"):
            skin = make(name)
            s = page_screens()[0]
            for view in ("list", "wall"):
                s.view = view
                skin.fit_window((1280, 720))
                short = skin.ondemand_page(s)
                skin.fit_window((1024, 768))
                self.assertGreater(skin.ondemand_page(s), short, (name, view))


class TestSeam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.font.init()

    def test_where_a_screen_opens_up(self):
        s = pygame.Surface((64, 720), pygame.SRCALPHA)
        s.fill((255, 255, 255, 255), (0, 0, 64, 40))            # a top banner, clear below
        s.fill((255, 255, 255, 255), (0, 600, 64, 120))
        self.assertEqual(seams(s, 240), [(320, 240)])
        s.fill((0, 0, 0, 255))                                  # a notice centred on black
        s.fill((255, 255, 255, 255), (0, 330, 64, 60))
        self.assertEqual(seams(s, 240), [(165, 120), (555, 120)])
        for y in range(0, 720, 4):                              # never 8 alike: top and foot extended
            s.fill((y % 256, 0, 0, 255), (0, y, 64, 4))
        self.assertEqual(seams(s, 240), [(0, 120), (720, 120)])

    def test_top_stays_foot_moves_hits_and_boxes_follow(self):
        skin = make("indirect_hd")
        skin.fit_window((1024, 768))
        owner = screens(skin.app)[0]                # LiveTV
        canvas = pygame.Surface(skin.canvas, pygame.SRCALPHA)

        def draw(c):
            c.fill((255, 0, 0, 255), (0, 0, 1280, 60))         # a top banner
            c.fill((0, 0, 255, 255), (0, 640, 1280, 80))       # a foot bar
            skin.hit((10, 650, 50, 20), lambda: None)
        skin.paint(canvas, "live", draw, owner)
        self.assertEqual(canvas.get_at((5, 5))[:3], (255, 0, 0))
        self.assertEqual(canvas.get_at((5, 959))[:3], (0, 0, 255))
        self.assertEqual(canvas.get_at((5, 700))[3], 0)        # clear between
        self.assertEqual(skin.hits[-1][0].y, 650 + 240)
        self.assertEqual(skin.place_box(owner, (100, 650, 200, 50)), (100, 890, 200, 50))
        self.assertEqual(skin.place_box(owner, (100, 10, 200, 20)), (100, 10, 200, 20))

    def test_a_page_backdrop_spans_the_full_height(self):
        skin = make("indirect_hd")
        skin.fit_window((1024, 768))
        canvas = pygame.Surface(skin.canvas, pygame.SRCALPHA)
        skin.paint(canvas, "menu", lambda c: skin._page(c, skin.R(0, 192, 1280, 528)))
        self.assertEqual(canvas.get_at((640, 955))[3], 255)

    def test_the_picture_shows_through_a_held_backdrop(self):
        class Page:                                 # a screen with a picture box
            name = "menu"

            def video_box(self):
                return (600, 200, 400, 225)
        skin = make("plate_hd")
        skin.fit_window((1024, 768))
        canvas = pygame.Surface(skin.canvas, pygame.SRCALPHA)
        owner = Page()

        def draw(c):
            skin._page(c, (0, 0, 1280, 720))
            skin.hole(c, (600, 200, 400, 225))
        skin.paint(canvas, "menu", draw, owner)
        self.assertEqual(canvas.get_at((800, 300))[3], 0)
        self.assertEqual(canvas.get_at((300, 900))[3], 255)
        # A page that names a picture box but draws none keeps it covered.
        canvas.fill((0, 0, 0, 0))
        skin.paint(canvas, "keyboard", lambda c: skin._page(c, (0, 0, 1280, 720)), owner)
        self.assertEqual(canvas.get_at((800, 300))[3], 255)

    def test_every_screen_draws_on_a_grown_canvas(self):
        from test_skins import FakeOnDemand, page_screens
        for name in ("classic", "indirect_hd", "plate_hd"):
            skin = make(name)
            skin.app.ondemand = FakeOnDemand()
            for window in ((1024, 768), (1280, 800)):
                skin.fit_window(window)
                canvas = pygame.Surface(skin.canvas, pygame.SRCALPHA)
                for s in screens(skin.app) + page_screens():
                    with self.subTest(skin=name, window=window, screen=s.name):
                        canvas.fill((0, 0, 0, 0))
                        skin.hits = []
                        owner = None if type(s).__name__ == "SimpleNamespace" else s    # the made-up pages
                        skin.paint(canvas, s.name, lambda c, s=s: skin.draw(c, s), owner)
                        for r, _ in skin.hits:
                            self.assertTrue(canvas.get_rect().contains(r) or r.w == 0, (r, canvas.get_rect()))


if __name__ == "__main__":
    unittest.main()
