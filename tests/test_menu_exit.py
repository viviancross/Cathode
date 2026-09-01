"""Every menu page shows its own way out.

Cathode's rule is that whatever a button does, an on-screen control does too —
Game Mode has no desktop, and a phone has no B button. The context menu used to
show "< Back" on submenus only, so on the root page the sole escape was tapping
outside the panel, which nothing on screen advertises. On a touchscreen that
read as "this menu has trapped me".
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.ui.menu import ContextMenu, MenuItem


def _menu():
    m = ContextMenu(1280, 720)
    m.open_with([MenuItem("One"), MenuItem("Two", submenu=[MenuItem("Deep")])],
                title="TEST")
    return m


class TestTheWayOut(unittest.TestCase):
    def test_the_root_page_offers_an_exit(self):
        m = _menu()
        self.assertIsNotNone(m._back_rect())

    def test_a_submenu_offers_one_too(self):
        m = _menu()
        m.move(1)
        m.activate()                       # into the submenu
        self.assertIsNotNone(m._back_rect())

    def test_the_exit_is_reachable_by_pointer(self):
        m = _menu()
        x0, y0, x1, y1 = m._back_rect()
        hit = m.hit_test((x0 + x1) // 2, (y0 + y1) // 2)
        self.assertEqual(hit, len(m._items()))   # the sentinel index

    def test_activating_it_closes_the_root_menu(self):
        m = _menu()
        x0, y0, x1, y1 = m._back_rect()
        m.set_hover((x0 + x1) // 2, (y0 + y1) // 2)
        m.activate()
        self.assertFalse(m.open)

    def test_activating_it_leaves_a_submenu_without_closing(self):
        m = _menu()
        m.move(1)
        m.activate()
        x0, y0, x1, y1 = m._back_rect()
        m.set_hover((x0 + x1) // 2, (y0 + y1) // 2)
        m.activate()
        self.assertTrue(m.open)            # back to the root, still open
        self.assertEqual(len(m._stack), 1)

    def test_the_panel_grows_to_fit_the_exit_row(self):
        # The row is real estate, not an overlay: the panel has to allow for it
        # or it would draw on top of the last item.
        m = _menu()
        _, _, _, ph, row_h, pad = m._geometry()
        rows = 1 + len(m._items()) + 1     # title + items + exit
        self.assertEqual(ph, pad * 2 + row_h * rows)


if __name__ == "__main__":
    unittest.main()
