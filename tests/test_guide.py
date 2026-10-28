"""The guide's cell cursor: LEFT/RIGHT walk the cursor row's programmes and
the window slides only when the chosen cell would leave it; THEMES/OPTIONS
offer the categories as a list."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.epg import EPG, Program  # noqa: E402
from cathode.playlist import Channel  # noqa: E402
from cathode.screens import guide as guide_mod  # noqa: E402
from cathode.screens.guide import Guide  # noqa: E402

NOW = datetime(2026, 10, 18, 12, 7, tzinfo=timezone.utc)      # base (quarter hour) = 12:00


class FakeApp:
    def __init__(self, progs, hours=2, cats=("All", "Favorites", "News")):
        self.channels = [Channel(number=1, name="One", url="u", epg_id="one"),
                         Channel(number=2, name="Two", url="u", epg_id="two")]
        self.epg = EPG()
        self.epg.add_programs("one", [Program("one", t, a, b) for t, a, b in progs])
        self.skin = mock.Mock(guide_rows=5, guide_hours=hours, guide_jump_min=24 * 60, lists_title="CATEGORIES")
        self.live = mock.Mock(channel=self.channels[0])
        self.pushed = []
        self._cats = list(cats)

    def categories(self):
        return self._cats

    def channels_in(self, cat):
        return self.channels

    def epg_horizon_min(self):
        last = self.epg.last_stop()
        return int((last - NOW).total_seconds() // 60) if last else 0

    def push(self, screen):
        self.pushed.append(screen)

    def pop(self, screen):
        pass


def at(h, m=0):
    return NOW.replace(hour=h, minute=m)


class TestCellCursor(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(guide_mod, "datetime", wraps=datetime)
        self.dt = patcher.start()
        self.dt.now.return_value = NOW
        self.addCleanup(patcher.stop)
        # 11:30-12:30 airing now, then 12:30-13:00, 13:00-14:00, 14:00-15:00, 15:00-16:00
        self.app = FakeApp([("Airing", at(11, 30), at(12, 30)), ("Next", at(12, 30), at(13)),
                            ("Later", at(13), at(14)), ("Evening", at(14), at(15)), ("Late", at(15), at(16))])
        self.g = Guide(self.app)

    def test_right_walks_the_row_without_moving_the_window(self):
        g = self.g
        self.assertEqual((g.offset_min, g.sel_min), (0, 0))
        g.handle("RIGHT")
        self.assertEqual((g.offset_min, g.sel_min), (0, 30))          # Next, still in the 12:00-14:00 window
        g.handle("RIGHT")
        self.assertEqual((g.offset_min, g.sel_min), (0, 60))          # Later
        self.assertEqual(g.sel_time(), at(13))

    def test_the_window_slides_only_when_the_cell_leaves_it(self):
        g = self.g
        for _ in range(3):
            g.handle("RIGHT")
        # Evening starts at 14:00, past the window's end: the window slides so it's the last column.
        self.assertEqual(g.sel_min, 120)
        self.assertEqual(g.offset_min, 15)
        self.assertEqual(g.window()[0], at(12, 15))
        g.handle("LEFT")
        self.assertEqual((g.offset_min, g.sel_min), (15, 60))         # back to Later, no slide
        g.handle("LEFT")
        g.handle("LEFT")
        self.assertEqual((g.offset_min, g.sel_min), (0, 0))           # the cell airing now: window back to now

    def test_never_before_now_and_never_past_the_listings(self):
        g = self.g
        g.handle("LEFT")
        self.assertEqual((g.offset_min, g.sel_min), (0, 0))
        for _ in range(10):
            g.handle("RIGHT")
        self.assertEqual(g.sel_min, 180)                              # Late: the last programme
        self.assertLessEqual(g.offset_min + g.hours * 60, self.app.epg_horizon_min())

    def test_a_day_jump_keeps_the_cursor_inside_the_window(self):
        g = self.g
        g.handle("RIGHT")
        g.handle("FF")
        self.assertEqual(g.sel_min, g.offset_min)
        g.handle("REW")
        self.assertEqual((g.offset_min, g.sel_min), (0, 0))

    def test_the_header_describes_the_chosen_cell(self):
        g = self.g
        self.assertEqual(g.selected_program().title, "Airing")
        g.handle("RIGHT")
        self.assertEqual(g.selected_program().title, "Next")
        g.handle("DOWN")                                              # no listings on Two
        self.assertIsNone(g.selected_program())

    def test_a_row_without_listings_steps_by_quarter_hours(self):
        g = self.g
        g.handle("DOWN")                                              # channel Two: no listings
        g.handle("RIGHT")
        g.handle("RIGHT")
        self.assertEqual((g.offset_min, g.sel_min), (0, 30))
        g.handle("UP")                                                # back on One: the 12:30 cell is lit
        self.assertEqual(g.sel_time(), at(12, 30))


class TestCategoryList(unittest.TestCase):
    def test_themes_offers_the_lists_and_a_pick_filters_the_grid(self):
        app = FakeApp([])
        g = Guide(app, category="News")
        g.handle("THEMES")
        menu = app.pushed[-1]
        self.assertEqual(menu.name, "options")
        self.assertEqual([it.label for it in menu.items], ["All", "Favorites", "News"])
        self.assertEqual(menu.cursor, 2)                              # starts on the list in use
        menu.items[0].action()
        self.assertEqual(g.category, "All")
        self.assertEqual(g.focus, "grid")
        self.assertTrue(menu.items[0].close)

    def test_info_pops_up_the_chosen_cell(self):
        app = FakeApp([("Airing", NOW - timedelta(hours=1), NOW + timedelta(hours=1))])
        with mock.patch.object(guide_mod, "datetime", wraps=datetime) as dt:
            dt.now.return_value = NOW
            g = Guide(app)
            g.handle("INFO")
            info = app.pushed[-1]
            self.assertEqual(info.name, "program_info")
            self.assertEqual(info.title, "Airing")
            self.assertEqual(info.lines()[0], "1 One")
            self.assertIn("No further information", info.lines()[2])
            self.assertTrue(info.handle("INFO"))                      # closes; a volume key passes through
            self.assertFalse(info.handle("VOL_UP"))
            g.handle("DOWN")                                          # no listings
            g.handle("INFO")
            self.assertEqual(app.pushed[-1].title, "No information")

    def test_options_does_the_same_for_a_pad(self):
        app = FakeApp([])
        Guide(app).handle("OPTIONS")
        self.assertEqual(app.pushed[-1].title, "CATEGORIES")


if __name__ == "__main__":
    unittest.main()
