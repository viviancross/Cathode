"""On Demand: the play queue, the keep-watching-this-show queue, sorts, and
the browse levels. Carried over from 3.4's test_plex_queue and
test_episode_queue."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.ondemand import SORTS, Queue, episode_queue, queue_entry, sort_label  # noqa: E402


def entries(n):
    return [queue_entry({"rating_key": str(i), "title": f"t{i}"}) for i in range(n)]


class TestQueue(unittest.TestCase):
    def test_adding_by_hand_marks_it_hand_built(self):
        q = Queue()
        self.assertEqual(q.add(entries(2)), 2)
        self.assertTrue(q.by_hand)

    def test_move_down_then_up_is_identity(self):
        q = Queue()
        q.add(entries(3))
        before = list(q.items)
        j = q.move(0, 1)
        q.move(j, -1)
        self.assertEqual(q.items, before)

    def test_moving_off_the_end_does_nothing(self):
        q = Queue()
        q.add(entries(2))
        self.assertEqual(q.move(1, 1), 1)
        self.assertEqual([e["title"] for e in q.items], ["t0", "t1"])

    def test_the_playing_marker_moves_with_its_item(self):
        q = Queue()
        q.add(entries(3))
        q.pos = 1
        q.move(1, 1)
        self.assertEqual(q.pos, 2)
        q.move(1, 1)            # swap the item now at 1 with the playing one at 2
        self.assertEqual(q.pos, 1)

    def test_removing_before_the_current_item_shifts_it(self):
        q = Queue()
        q.add(entries(4))
        q.pos = 2
        q.remove(0)
        self.assertEqual(q.items[q.pos]["title"], "t2")

    def test_removing_the_playing_item_advances_to_what_replaced_it(self):
        q = Queue()
        q.add(entries(3))
        q.pos = 1
        q.remove(1)
        self.assertEqual(q.items[q.step(1)]["title"], "t2")

    def test_clearing_resets_the_hand_built_flag(self):
        q = Queue()
        q.add(entries(2))
        q.clear()
        self.assertFalse(q.by_hand)
        self.assertEqual(q.items, [])

    def test_a_one_off_play_keeps_a_hand_built_queue(self):
        q = Queue()
        q.add(entries(2))
        q.one_off()
        self.assertEqual(len(q.items), 2)
        self.assertEqual(q.step(1), 0)          # the next skip starts it from the top

    def test_a_one_off_play_drops_an_automatic_queue(self):
        q = Queue()
        q.replace(entries(3))
        q.one_off()
        self.assertEqual(q.items, [])

    def test_stepping_off_either_end_is_none(self):
        q = Queue()
        q.replace(entries(2))
        self.assertIsNone(q.step(-1))
        q.pos = 1
        self.assertIsNone(q.step(1))


class TestEpisodeQueue(unittest.TestCase):
    eps = [{"rating_key": str(i)} for i in range(5)]

    def test_queues_from_the_selected_episode_to_the_end(self):
        self.assertEqual([e["rating_key"] for e in episode_queue(self.eps, "2")], ["2", "3", "4"])

    def test_the_first_episode_queues_the_whole_show(self):
        self.assertEqual(len(episode_queue(self.eps, "0")), 5)

    def test_the_last_episode_has_no_queue(self):
        self.assertEqual(episode_queue(self.eps, "4"), [])

    def test_an_unknown_episode_has_no_queue(self):
        self.assertEqual(episode_queue(self.eps, "x"), [])


class TestSorts(unittest.TestCase):
    def test_release_date_sorting_is_offered(self):
        values = [v for _, v in SORTS]
        self.assertIn("originallyAvailableAt:desc", values)
        self.assertIn("originallyAvailableAt:asc", values)

    def test_labels_are_distinct_and_short(self):
        labels = [n for n, _ in SORTS]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertTrue(all(len(n) <= 16 for n in labels))

    def test_an_unknown_sort_reads_as_default(self):
        self.assertEqual(sort_label("nonsense:asc"), "Default")


class TestInfoButtons(unittest.TestCase):
    def test_single_items_can_be_recorded(self):
        from cathode.screens.iteminfo import BUTTONS
        for kind in ("default", "episode"):
            self.assertIn("dvr", BUTTONS[kind], kind)

    def test_a_series_cannot(self):
        from cathode.screens.iteminfo import BUTTONS
        self.assertNotIn("dvr", BUTTONS["show"])

    def test_a_recording_offers_only_what_works_offline(self):
        from cathode.screens.iteminfo import BUTTONS
        self.assertEqual(BUTTONS["download"], ["play", "dvr", "back"])


class FakeOD:
    def __init__(self, recordings=()):
        self.listeners = []
        self.signed_in = False

        class D:
            def items(self_):
                return list(recordings)
        self.downloads = D()


class FakeApp:
    def __init__(self, od):
        from cathode.config import Config
        self.config = Config("")
        self.ondemand = od
        self.screens = []
        self.posted = []

    def invalidate(self):
        pass

    def after(self, s, fn):
        return [s, 0, fn, False]

    def cancel(self, t):
        pass

    def toast(self, *a, **k):
        pass

    def pop(self, s=None):
        pass


class TestBrowseLevels(unittest.TestCase):
    def screen(self, recordings=()):
        from cathode.screens.ondemand import OnDemandScreen
        od = FakeOD(recordings)
        od.run = lambda work, done=None, fail=None: None      # nothing reaches a server
        s = OnDemandScreen.__new__(OnDemandScreen)
        s.app, s.od, s.stack, s.status, s.mode = FakeApp(od), od, [], "", "browse"
        return s

    def test_the_server_list_replaces_the_recordings_stub(self):
        s = self.screen()
        s.show_libraries([s._recordings_row()], "CONNECTING...")
        s.show_libraries([{"type": "search", "title": "SEARCH"}, s._recordings_row(),
                          {"type": "section", "title": "MOVIES"}])
        self.assertEqual(len(s.stack), 1)
        self.assertEqual(len(s.rows), 3)

    def test_the_cursor_stays_on_my_recordings_when_the_list_grows(self):
        s = self.screen()
        s.show_libraries([s._recordings_row()])
        s.show_libraries([{"type": "search", "title": "SEARCH"}, s._recordings_row()])
        self.assertEqual(s.current()["type"], "downloads")

    def test_a_late_answer_does_not_yank_the_screen_away(self):
        s = self.screen()
        s.show_libraries([s._recordings_row()])
        s.push("MY RECORDINGS", [{"type": "download", "title": "A"}])
        s.show_libraries([{"type": "search", "title": "SEARCH"}, s._recordings_row()])
        self.assertEqual(s.level["title"], "MY RECORDINGS")
        self.assertEqual(len(s.stack[0]["rows"]), 2)        # updated underneath

    def test_sortable_lists_get_a_sort_row_and_start_below_it(self):
        s = self.screen()
        s.push("MOVIES", [{"type": "movie", "title": "A"}], loader=lambda srt: [])
        self.assertEqual(s.rows[0]["type"], "sort")
        self.assertEqual(s.sel, 1)


if __name__ == "__main__":
    unittest.main()
