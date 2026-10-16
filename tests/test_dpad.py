"""D-pad reach: On Demand's transport row is reachable by DOWN and works by
LEFT/RIGHT/SELECT, as live TV's playback buttons do."""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import remote as R  # noqa: E402
from cathode.screens.playback import Playback  # noqa: E402


class TestTransportRow(unittest.TestCase):
    def test_down_moves_in_then_left_right_select_and_up_leaves(self):
        pb = Playback.__new__(Playback)
        pressed = []
        pb.app = SimpleNamespace(screens=[pb], invalidate=lambda: None)
        pb.tfocus = None
        pb.transport = lambda: [(k, k, lambda k=k: pressed.append(k)) for k in "abcdef"]
        pb.show_bar = lambda seconds=5.0: None
        pb.bar_visible = lambda: True
        self.assertTrue(pb._row_keys(R.DOWN))
        self.assertEqual(pb.tfocus, 2)                  # on Play/Pause
        pb._row_keys(R.RIGHT)
        pb._row_keys(R.SELECT)
        self.assertEqual(pressed, ["d"])
        pb._row_keys(R.UP)
        self.assertIsNone(pb.tfocus)
        self.assertFalse(pb._row_keys(R.LEFT))         # out of the row, LEFT seeks again


class TestAddressKeyboard(unittest.TestCase):
    def _kb(self, rows):
        from cathode.screens.menu import Keyboard
        kb = Keyboard.__new__(Keyboard)
        kb.app = SimpleNamespace(skin=SimpleNamespace(keyboard_rows=lambda layer: rows), invalidate=lambda: None)
        kb.url, kb.layer, kb.value, kb.caret, kb._back_at = True, "abc", "", 0, 0.0
        kb.done = []
        kb._finish = kb.done.append
        return kb

    def test_colon_and_slash_reach_the_first_layer(self):
        plate = self._kb([list("uvwxyz'-.&"), ["DONE"]]).grid()
        self.assertEqual(plate[0], list("uvwxyz:-./"))
        hr20 = self._kb([list("abcdef"), list("567890"), ["DONE"]]).grid()
        self.assertEqual(hr20[2], list("./:-_?"))         # a row of its own, before the actions

    def test_back_on_an_empty_field_leaves_but_not_mid_erase(self):
        kb = self._kb([list("abc"), ["DONE"]])
        kb.value, kb.caret = "a", 1
        kb.handle(R.BACK)                                 # erases the last letter
        kb.handle(R.BACK)                                 # held: just emptied, stays
        self.assertEqual(kb.done, [])
        kb._back_at = 0.0                                 # a fresh press later
        kb.handle(R.BACK)
        self.assertEqual(kb.done, [None])


if __name__ == "__main__":
    unittest.main()
