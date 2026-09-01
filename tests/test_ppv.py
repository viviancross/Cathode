"""PPV browse screen: variable-height rows + bar-focus nav (headless)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.ui.ppv import PPVScreen  # noqa: E402


def _rows():
    return [
        {"type": "movie", "title": "CNN", "meta": "2020", "playable": True},
        {"type": "movie", "title": "A Very Long Movie Title That Has To Wrap "
         "Onto A Second Line For Sure", "meta": "1999", "playable": True},
        {"type": "section", "title": "MOVIES", "meta": "", "playable": False},
    ]


class TestPPV(unittest.TestCase):
    def setUp(self):
        self.p = PPVScreen(1280, 720)
        self.p.show()
        self.p.set_browse("CHOOSE", _rows(), "crumb")

    def test_short_titles_one_line_long_wraps(self):
        # Asked through _row_h_at, which is what forces the measurement: row
        # heights are computed lazily so that opening a large library doesn't
        # measure thousands of titles nobody is looking at.
        short_h = self.p._row_h_at(0)               # CNN
        long_h = self.p._row_h_at(1)                # long title wraps
        self.assertGreater(long_h, short_h)
        self.assertEqual(self.p._row_lines[0], 1)
        self.assertEqual(self.p._row_lines[1], 2)
        self.p.render()                             # must not raise

    def test_row_heights_are_measured_only_when_needed(self):
        # The guard against the O(n) open: nothing is measured up front.
        p = PPVScreen(1280, 720)
        p.show()
        p.set_browse("CHOOSE", _rows(), "crumb")
        self.assertTrue(all(v is None for v in p._row_lines))
        p._row_h_at(1)
        self.assertIsNotNone(p._row_lines[1])
        self.assertIsNone(p._row_lines[2])          # untouched rows stay unmeasured

    def test_bar_focus_wraps_around(self):
        self.assertIsNone(self.p.bar_focus)
        self.p.move_up()                            # row0 -> bar
        self.assertEqual(self.p.bar_focus, "back")
        self.p.nav_horizontal(1)                    # back -> menu
        self.assertEqual(self.p.bar_focus, "menu")
        self.p.move_down()                          # bar -> row0
        self.assertIsNone(self.p.bar_focus)
        self.assertEqual(self.p.sel, 0)
        # Down past the last row wraps up to the bar.
        self.p.sel = len(self.p.rows) - 1
        self.p.move_down()
        self.assertEqual(self.p.bar_focus, "back")

    def test_render_with_bar_focus(self):
        self.p.move_up()
        self.p.render()                             # bar highlighted, no row highlight


if __name__ == "__main__":
    unittest.main()
