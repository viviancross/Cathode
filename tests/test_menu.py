"""Context-menu windowing + back-row navigation (headless: PIL only)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.ui.menu import ContextMenu, MenuItem  # noqa: E402


def _menu(n):
    m = ContextMenu(1280, 720)
    m.open_with([MenuItem(f"Item {i}") for i in range(n)], title="CATEGORIES")
    return m


class TestMenuScroll(unittest.TestCase):
    def test_long_list_windows_not_squashes(self):
        m = _menu(40)
        first, count = m._window()
        self.assertEqual(first, 0)
        self.assertLess(count, 40)           # only a window is shown
        self.assertGreater(count, 3)
        m.render()                           # must not raise

    def test_window_follows_selection(self):
        m = _menu(40)
        for _ in range(39):
            m.move_down()
        first, count = m._window()
        self.assertEqual(m._page[1], 39)
        self.assertTrue(first <= 39 < first + count)   # selection stays visible
        m.render()

    def test_short_list_shows_all(self):
        m = _menu(5)
        first, count = m._window()
        self.assertEqual((first, count), (0, 5))

    def test_visible_row_hit_test_returns_global_index(self):
        m = _menu(40)
        for _ in range(30):
            m.move_down()
        rects = m._row_rects()
        gi, x0, y0, x1, y1 = rects[0]
        self.assertEqual(m.hit_test((x0 + x1) // 2, (y0 + y1) // 2), gi)
        self.assertGreater(gi, 0)            # scrolled — first visible isn't item 0


class TestBackRow(unittest.TestCase):
    def test_back_row_pops_submenu(self):
        m = ContextMenu(1280, 720)
        m.open_with([MenuItem("A", submenu=[MenuItem("X"), MenuItem("Y")])])
        m.activate()                         # enter submenu
        self.assertEqual(len(m._stack), 2)
        m._page[1] = len(m._items())         # select the synthetic Back row
        m.activate()
        self.assertEqual(len(m._stack), 1)   # popped back


if __name__ == "__main__":
    unittest.main()
