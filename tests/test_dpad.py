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


if __name__ == "__main__":
    unittest.main()
