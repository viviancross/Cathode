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


class TestBarGoes(unittest.TestCase):
    def _pb(self):
        pb = Playback.__new__(Playback)
        drawn, stopped = [], []
        pb.app = SimpleNamespace(screens=[pb], invalidate=lambda: drawn.append(1), after=lambda s, fn: None,
                                 video=SimpleNamespace(paused=False, prop=lambda k: None))
        pb.tfocus, pb.skip_label, pb.markers, pb.dur, pb.pos, pb.time_base = None, "", [], 600.0, 0.0, 0.0
        pb._shown, pb._last_report = False, 1e18
        pb.stop = lambda: stopped.append(1)
        return pb, drawn, stopped

    def test_the_bar_is_taken_off_the_screen_when_it_times_out(self):
        pb, drawn, _ = self._pb()
        pb.show_bar()
        pb._monitor()
        pb.bar_until = 0.0                              # its five seconds are up
        drawn.clear()
        pb._monitor()
        self.assertEqual(len(drawn), 1)                 # one more frame, without it
        pb._monitor()
        self.assertEqual(len(drawn), 1)                 # then nothing to draw

    def test_back_hides_the_bar_then_leaves(self):
        pb, _, stopped = self._pb()
        pb.show_bar()
        pb.handle(R.BACK)
        self.assertFalse(pb.bar_visible())
        self.assertEqual(stopped, [])
        pb.handle(R.BACK)
        self.assertEqual(stopped, [1])

class TestNextInQueue(unittest.TestCase):
    def test_a_title_that_runs_out_plays_the_next(self):
        from cathode.ondemand import Queue
        pb = Playback.__new__(Playback)
        played, q = [], Queue()
        q.replace([{"rating_key": "e1"}, {"rating_key": "e2"}])
        pb.od = SimpleNamespace(queue=q, report=lambda *a, **k: None, remember_offset=lambda *a: None,
                                play_queue_at=played.append)
        pb.rk, pb.pos, pb.dur, pb._subs_added = "e1", 600.0, 600.0, True
        pb.on_video("video_ended", reason="eof")        # mpv's end, now that it's reported
        self.assertEqual(played, [1])


class TestSubtitleReload(unittest.TestCase):
    """Auto-sync switched mid-title: the files go back to mpv, the one
    showing stays shown, and one the server won't sync comes back plain."""

    def _pb(self, refuse=()):
        pb = Playback.__new__(Playback)
        added, removed = [], []

        class V:
            def tracks(self, kind):
                return [{"id": 1, "external": True, "selected": False, "file": "http://s/streams/1"},
                        {"id": 2, "external": True, "selected": True, "file": "http://s/streams/2?autoAdjustSubtitle=1"}]

            def remove_subtitle(self, tid):
                removed.append(tid)
                return True

            def add_subtitle(self, url, title="", lang="", select=False):
                if url in refuse:
                    return False
                added.append((url, select))
                return True
        pb.app = SimpleNamespace(video=V(), config=SimpleNamespace(sub_auto_sync=True))
        pb.subs = [{"url": "http://s/streams/1", "title": "A", "lang": "en"},
                   {"url": "http://s/streams/2", "title": "B", "lang": "en", "sync": True}]
        return pb, added, removed

    def test_the_shown_file_stays_shown(self):
        pb, added, removed = self._pb()
        pb.reload_subs()
        self.assertEqual(removed, [1, 2])
        self.assertEqual(added, [("http://s/streams/1", False),
                                 ("http://s/streams/2?autoAdjustSubtitle=1", True)])

    def test_a_sync_the_server_refuses_falls_back_to_the_file(self):
        pb, added, _ = self._pb(refuse={"http://s/streams/2?autoAdjustSubtitle=1"})
        pb.reload_subs()
        self.assertIn(("http://s/streams/2", True), added)

if __name__ == "__main__":
    unittest.main()
