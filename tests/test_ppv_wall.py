"""Poster wall: grid geometry, the cursor, and the artwork windowing rule."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.plex import _meta_row, PlexClient  # noqa: E402
from cathode.ui.ppv import PPVScreen            # noqa: E402


class CountingLogos:
    """Stands in for LogoStore, and records every request made of it."""

    def __init__(self, art=None):
        self.calls = []
        self.art = art

    def get(self, url, w, h, headers=None):
        self.calls.append(url)
        return self.art


def wall(w=1280, h=800, n=40, art=None, thumbs=True):
    s = PPVScreen(w, h)
    s.view = "wall"
    s.logos = CountingLogos(art)
    s.art_url = lambda p, tw, th: f"http://server/photo?url={p}&width={tw}"
    rows = [{"type": "movie", "rating_key": str(i), "title": f"Film {i}",
             "meta": "1982 R 8.2", "playable": True,
             "thumb": f"/library/metadata/{i}/thumb" if thumbs else "",
             "duration": 7200, "offset": 0}
            for i in range(n)]
    s.set_browse("MOVIES", rows, crumb="Library / Movies")
    s.show()
    return s


class TestRowArtwork(unittest.TestCase):
    """The enabling change: browse rows have to carry artwork and a duration."""

    def test_episode_falls_back_to_the_shows_thumb(self):
        # Episodes frequently have no thumb of their own; without the fallback a
        # season view is a wall of blank tiles.
        row = _meta_row({"type": "episode", "ratingKey": 7, "title": "Pilot",
                         "parentIndex": 1, "index": 1,
                         "grandparentThumb": "/library/metadata/1/thumb"})
        self.assertEqual(row["thumb"], "/library/metadata/1/thumb")

    def test_its_own_thumb_wins(self):
        row = _meta_row({"type": "episode", "ratingKey": 7, "title": "Pilot",
                         "thumb": "/own", "grandparentThumb": "/gp"})
        self.assertEqual(row["thumb"], "/own")

    def test_no_artwork_anywhere_is_an_empty_string(self):
        self.assertEqual(_meta_row({"type": "movie", "ratingKey": 1})["thumb"], "")

    def test_duration_is_seconds(self):
        # Without it the resume bar has no denominator and silently never draws.
        row = _meta_row({"type": "movie", "ratingKey": 1, "duration": 7200000})
        self.assertEqual(row["duration"], 7200)


class TestPhotoUrl(unittest.TestCase):
    def setUp(self):
        self.c = PlexClient("cid", token="SECRET-TOKEN")
        self.c.server = "http://box:32400"

    def test_carries_no_token(self):
        url = self.c.photo_url("/library/metadata/1/thumb", 200, 300)
        self.assertNotIn("SECRET-TOKEN", url)
        self.assertNotIn("X-Plex-Token", url)

    def test_asks_for_the_size_it_will_be_drawn_at(self):
        url = self.c.photo_url("/library/metadata/1/thumb", 200, 300)
        self.assertIn("width=200", url)
        self.assertIn("height=300", url)
        self.assertIn("/photo/:/transcode", url)

    def test_empty_path_is_empty_url(self):
        self.assertEqual(self.c.photo_url("", 10, 10), "")


class TestWallGeometry(unittest.TestCase):
    def test_two_whole_rows_fit(self):
        # A clipped second row reads as a rendering fault, not as "more below".
        for w, h in ((1280, 800), (1920, 1080), (1024, 768), (640, 480)):
            s = wall(w, h)
            cols, tw, ph, gap = s._wall_metrics()
            _, top, _, bottom = s._panel()
            need = 2 * s._wall_tile_h() + gap
            self.assertLessEqual(need, (bottom - top) - 12, f"{w}x{h}")
            self.assertGreaterEqual(s._wall_visible_rows(), 2, f"{w}x{h}")

    def test_tiles_fit_the_panel_width(self):
        for w, h in ((1280, 800), (1920, 1080), (640, 480)):
            s = wall(w, h)
            cols, tw, _, gap = s._wall_metrics()
            x0, _, x1, _ = s._panel()
            self.assertLessEqual(cols * tw + (cols - 1) * gap, (x1 - x0) - 12,
                                 f"{w}x{h}")

    def test_no_tile_escapes_the_panel(self):
        s = wall(1280, 800)
        x0, top, x1, bottom = s._panel()
        for (_, tx0, ty0, tx1, ty1) in s._wall_rects():
            self.assertGreaterEqual(tx0, x0)
            self.assertLessEqual(tx1, x1)
            self.assertGreaterEqual(ty0, top)
            self.assertLessEqual(ty1, bottom)


class TestWallCursor(unittest.TestCase):
    def test_down_steps_a_whole_row(self):
        s = wall()
        cols = s._wall_metrics()[0]
        s.sel = 0
        s.move_down()
        self.assertEqual(s.sel, cols)

    def test_up_steps_a_whole_row_back(self):
        s = wall()
        cols = s._wall_metrics()[0]
        s.sel = cols * 2
        s.move_up()
        self.assertEqual(s.sel, cols)

    def test_up_from_the_top_row_reaches_the_bar(self):
        s = wall()
        s.sel = 1                      # top row, not the first tile
        s.move_up()
        self.assertEqual(s.bar_focus, "back")

    def test_down_from_a_short_final_row_lands_on_the_last_item(self):
        # Refusing to move because sel+cols is past the end strands the cursor.
        s = wall(n=25)
        cols = s._wall_metrics()[0]
        self.assertGreater(cols, 5)     # otherwise the case isn't exercised
        s.sel = len(s.rows) - 3
        s.move_down()
        self.assertEqual(s.sel, len(s.rows) - 1)

    def test_left_right_step_one_tile_not_a_page(self):
        # The list pages by 10 sideways; on a grid that skips whole rows.
        s = wall()
        s.sel = 5
        s.nav_horizontal(1)
        self.assertEqual(s.sel, 6)
        s.nav_horizontal(-1)
        self.assertEqual(s.sel, 5)

    def test_the_list_view_still_steps_by_one(self):
        s = wall()
        s.view = "list"
        s.sel = 3
        s.move_down()
        self.assertEqual(s.sel, 4)

    def test_selection_scrolls_into_view(self):
        s = wall(n=200)
        s.sel = 150
        cols = s._wall_metrics()[0]
        shown = [i for (i, *_r) in s._wall_rects()]
        self.assertIn(150, shown)
        self.assertGreater(s._wall_top, 0)
        self.assertLessEqual(s._wall_top, 150 // cols)


class TestArtworkWindowing(unittest.TestCase):
    """LogoStore starts a thread per URL, so asking for every row of a large
    library would be hundreds of threads and downloads to fill twenty boxes."""

    def test_only_visible_tiles_are_requested(self):
        s = wall(n=500)
        s.render()
        shown = len(s._wall_rects())
        self.assertEqual(len(s.logos.calls), shown)
        self.assertLess(len(s.logos.calls), 60)

    def test_scrolling_does_not_accumulate_requests_for_offscreen_rows(self):
        s = wall(n=500)
        s.render()
        first = len(s.logos.calls)
        s.sel = 400
        s.logos.calls.clear()
        s.render()
        self.assertLessEqual(len(s.logos.calls), first)

    def test_a_row_with_no_thumb_is_never_requested(self):
        # Folders, genres and the pinned Sort row have no artwork to ask for.
        s = wall(n=20, thumbs=False)
        s.render()
        self.assertEqual(s.logos.calls, [])

    def test_the_list_view_asks_for_no_artwork_at_all(self):
        s = wall(n=500)
        s.view = "list"
        s.render()
        self.assertEqual(s.logos.calls, [])

    def test_the_token_stays_out_of_the_requested_url(self):
        s = wall(n=12)
        s.art_headers = {"X-Plex-Token": "SECRET"}
        s.render()
        self.assertTrue(s.logos.calls)
        for url in s.logos.calls:
            self.assertNotIn("SECRET", url)


class TestWallMouse(unittest.TestCase):
    def test_hit_test_finds_the_tile_under_the_cursor(self):
        s = wall()
        for (i, tx0, ty0, tx1, ty1) in s._wall_rects()[:12]:
            self.assertEqual(s.hit_test((tx0 + tx1) // 2, (ty0 + ty1) // 2), i)

    def test_a_click_outside_every_tile_hits_nothing(self):
        s = wall()
        self.assertIsNone(s.hit_test(2, 2))


class TestRenderSmoke(unittest.TestCase):
    def test_wall_renders_at_several_sizes_with_mixed_rows(self):
        for w, h in ((1280, 800), (1920, 1080), (640, 480)):
            s = wall(w, h, n=30)
            s.rows.insert(0, {"type": "sort", "title": "Sort by: Newest Release",
                              "meta": "", "playable": False})
            s.rows.insert(1, {"type": "genre", "title": "Science Fiction",
                              "meta": "", "playable": False})
            s.rows[5]["offset"] = 3600          # exercise the resume bar
            img = s.render()
            self.assertEqual(img.size, (w, h))

    def test_a_status_falls_back_to_the_list_view(self):
        # An empty level or an error has nothing to tile; the status screen and
        # its way out are drawn by the list path.
        s = wall(n=0)
        s.set_status("NOTHING HERE")
        s.render()
        self.assertEqual(s.logos.calls, [])


class TestViewOption(unittest.TestCase):
    """The menu toggle. Headless: App is built but never run."""

    def _app(self):
        from cathode.app import App
        from cathode.config import Config
        app = App(config=Config(""), width=320, height=240,
                  fullscreen=False, demo=True)
        app.config.save = lambda: None          # no config file in a test
        app.renderer.menu.replace_page = lambda items: None
        return app

    def test_default_is_the_list(self):
        # The wall is better for films, worse for episode lists where the titles
        # carry the information and the art is one repeated frame.
        app = self._app()
        self.assertEqual(app.config.ppv_view, "list")
        self.assertEqual(app.renderer.ppv.view, "list")

    def test_toggle_flips_both_the_config_and_the_screen(self):
        app = self._app()
        app._ppv_toggle_view()
        self.assertEqual(app.config.ppv_view, "wall")
        self.assertEqual(app.renderer.ppv.view, "wall")
        app._ppv_toggle_view()
        self.assertEqual(app.config.ppv_view, "list")
        self.assertEqual(app.renderer.ppv.view, "list")

    def test_the_option_row_names_the_current_view(self):
        app = self._app()
        app.config.plex_token = "t"             # the submenu is gated on this
        labels = [i.label for i in app._plex_options_submenu()]
        self.assertIn("View: List", labels)
        app._ppv_toggle_view()
        self.assertIn("View: Wall",
                      [i.label for i in app._plex_options_submenu()])

    def test_both_labels_survive_the_menu_ellipsis(self):
        # The panel truncates past ~15 characters; "View: Poster Wall" spent the
        # truncation on the word carrying no information.
        app = self._app()
        app.config.plex_token = "t"
        seen = set()
        for _ in range(2):
            row = next(i for i in app._plex_options_submenu()
                       if i.label.startswith("View:"))
            self.assertLessEqual(len(row.label), 15, row.label)
            seen.add(row.label)
            app._ppv_toggle_view()
        self.assertEqual(len(seen), 2)          # and they aren't the same label

    def test_the_option_row_does_not_close_the_menu(self):
        # menu.activate() runs the action first and applies close_after after,
        # so a row that rebuilds its own page must not close.
        app = self._app()
        app.config.plex_token = "t"
        row = next(i for i in app._plex_options_submenu()
                   if i.label.startswith("View:"))
        self.assertFalse(row.close_after)

    def test_a_junk_config_value_falls_back_to_the_list(self):
        from cathode.app import App
        from cathode.config import Config
        cfg = Config("")
        cfg.ppv_view = "posters"                # e.g. a hand-edited config file
        app = App(config=cfg, width=320, height=240, fullscreen=False, demo=True)
        self.assertEqual(app.renderer.ppv.view, "list")


if __name__ == "__main__":
    unittest.main()


class TestLargeLibraryScaling(unittest.TestCase):
    """A Plex library with thousands of titles is ordinary, and the browse
    screen used to fall over on one.

    `_ensure_visible` walked forward from the top re-summing the whole range on
    every step, so landing near the end of a 5000-row list was quadratic: it
    measured ~6.7 SECONDS, and the way to trigger it was mundane — scroll to
    the bottom of a big library, open something, press Back.
    """

    @staticmethod
    def _rows(n):
        return [{"type": "movie", "rating_key": str(i), "title": f"Title {i}",
                 "meta": "1982 R 8.2", "playable": True, "thumb": "",
                 "duration": 7200, "offset": 0} for i in range(n)]

    def _screen(self, n, view="list"):
        s = PPVScreen(1280, 800)
        s.view = view
        s.set_browse("BIG", self._rows(n))
        s.show()
        return s

    def test_opening_a_large_library_measures_nothing_up_front(self):
        s = self._screen(5000)
        self.assertEqual(len(s._row_lines), 5000)
        self.assertTrue(all(v is None for v in s._row_lines))

    def test_scrolling_to_the_end_stays_bounded(self):
        # The fix is structural, not a constant factor: the work done landing
        # at the end must not grow with the size of the library.
        import time
        timings = []
        for n in (1000, 8000):
            s = self._screen(n)
            s.sel = n - 1
            t0 = time.perf_counter()
            s._ensure_visible()
            timings.append(time.perf_counter() - t0)
        # 8x the rows must not mean 8x the work (it used to mean 64x).
        self.assertLess(timings[1], max(timings[0] * 3, 0.05),
                        f"ensure_visible scaled with library size: {timings}")

    def test_only_a_screenful_is_ever_measured(self):
        s = self._screen(5000)
        s.sel = 4999
        s.render()
        measured = sum(1 for v in s._row_lines if v is not None)
        self.assertLess(measured, 80, f"measured {measured} of 5000 rows")

    def test_the_selected_row_is_on_screen_after_a_long_jump(self):
        # The rewrite has to keep the actual guarantee, not just be fast.
        for n, sel in ((60, 59), (5000, 4999), (5000, 2500)):
            s = self._screen(n)
            s.sel = sel
            shown = [i for (i, *_r) in s._row_rects()]
            self.assertIn(sel, shown, f"n={n} sel={sel}")

    def test_scrolling_back_up_follows_the_selection(self):
        s = self._screen(500)
        s.sel = 499
        s._row_rects()
        s.sel = 0
        self.assertIn(0, [i for (i, *_r) in s._row_rects()])


class TestPosterClearsTheButtons(unittest.TestCase):
    """The poster is 2:3 and sized off the width; the button row is pinned to
    the bottom. On a 16:9 television they overlapped by 21px, which every
    render done at 1280x800 walks straight past."""

    def test_the_poster_clears_the_buttons(self):
        from cathode.ui.plexinfo import PlexInfoScreen
        for w, h in ((1280, 800), (1920, 1080), (1024, 768), (640, 480),
                     (1920, 1200), (3840, 2160)):
            s = PlexInfoScreen(w, h)
            s.show({"title": "T", "summary": "S"})
            self.assertLessEqual(s._poster_rect()[3], s._button_rects()[0][2],
                                 f"{w}x{h}: poster runs into the button row")

    def test_the_poster_keeps_its_shape_when_it_shrinks(self):
        from cathode.ui.plexinfo import PlexInfoScreen
        s = PlexInfoScreen(1920, 1080)
        s.show({"title": "T", "summary": "S"})
        x0, y0, x1, y1 = s._poster_rect()
        self.assertAlmostEqual((y1 - y0) / (x1 - x0), 1.5, delta=0.05)
