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
        self.assertEqual(self.p._row_lines[0], 1)   # CNN
        self.assertEqual(self.p._row_lines[1], 2)   # long title wraps
        self.p.render()                             # must not raise

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
