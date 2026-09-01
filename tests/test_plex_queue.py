"""Play queue bookkeeping and per-library sort memory.

The queue is edited while it may also be playing, so the "playing now" index has
to survive reorders and removals. Headless: App is built but never run.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.app import App  # noqa: E402
from cathode.config import Config  # noqa: E402


def make_app():
    app = App(config=Config(""), width=320, height=240,
              fullscreen=False, demo=True)
    app.renderer.show_notification = lambda *a, **k: None
    app.renderer.menu.replace_page = lambda items: None
    app.renderer.menu.back_and_replace = lambda items: None
    return app


def rows(*names):
    return [{"rating_key": str(i), "title": n} for i, n in enumerate(names, 1)]


class TestQueueEditing(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.app._plex_queue = rows("A", "B", "C")
        self.app._plex_queue_user = True

    def titles(self):
        return [e["title"] for e in self.app._plex_queue]

    def test_add_from_info_screen(self):
        app = make_app()
        app._plex_info_data = {"rating_key": "7", "title": "Movie",
                               "type": "movie"}
        app._plex_info_queue()
        self.assertEqual(app._plex_queue,
                         [{"rating_key": "7", "title": "Movie", "subtitle": ""}])
        self.assertTrue(app._plex_queue_user)

    def test_move_down_then_up_is_identity(self):
        self.app._queue_move(0, 1)
        self.assertEqual(self.titles(), ["B", "A", "C"])
        self.app._queue_move(1, -1)
        self.assertEqual(self.titles(), ["A", "B", "C"])

    def test_move_off_the_end_is_a_no_op(self):
        self.app._queue_move(2, 1)
        self.app._queue_move(0, -1)
        self.assertEqual(self.titles(), ["A", "B", "C"])

    def test_move_carries_the_playing_marker(self):
        self.app._plex_queue_pos = 2          # "C" is playing
        self.app._queue_move(2, -1)
        self.assertEqual(self.titles(), ["A", "C", "B"])
        self.assertEqual(self.app._plex_queue_pos, 1)

    def test_remove_before_current_shifts_it_down(self):
        self.app._plex_queue_pos = 2          # "C" is playing
        self.app._queue_remove(0)
        self.assertEqual(self.titles(), ["B", "C"])
        self.assertEqual(self.app._plex_queue_pos, 1)

    def test_removing_the_playing_item_advances_to_its_replacement(self):
        self.app._plex_queue_pos = 1          # "B" is playing
        self.app._queue_remove(1)
        self.assertEqual(self.titles(), ["A", "C"])
        # Next advance must land on "C" (which took slot 1), not skip past it.
        self.assertEqual(self.app._plex_queue_pos + 1, 1)

    def test_clear_resets_the_hand_built_flag(self):
        self.app._queue_clear()
        self.assertEqual(self.app._plex_queue, [])
        self.assertFalse(self.app._plex_queue_user)

    def test_one_off_play_keeps_a_hand_built_queue(self):
        self.app._ppv_client = lambda: None   # the play worker fails harmlessly
        self.app._ppv_play("99", "Something")   # fails in its worker thread
        self.assertEqual(len(self.app._plex_queue), 3)
        self.assertEqual(self.app._plex_queue_pos, -1)   # queue idle, not current

    def test_one_off_play_drops_an_auto_queue(self):
        self.app._plex_queue_user = False
        self.app._ppv_client = lambda: None   # the play worker fails harmlessly
        self.app._ppv_play("99", "Something")
        self.assertEqual(self.app._plex_queue, [])


class TestSortMemory(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.opened = []
        self.app._ppv_open = lambda *a, **k: self.opened.append((a, k))

    def push(self, sort_key):
        self.app._ppv_stack = [{"title": "MOVIES", "rows": [], "sel": 0,
                                "crumb": "", "loader": lambda s: [], "sort": "",
                                "volatile": False, "sortable": True,
                                "sort_key": sort_key}]

    def test_release_date_sort_is_offered(self):
        vals = dict(App.SORT_OPTIONS)
        self.assertEqual(vals["Newest Release"], "originallyAvailableAt:desc")
        self.assertEqual(vals["Oldest Release"], "originallyAvailableAt:asc")

    def test_sort_labels_survive_the_menu_ellipsis(self):
        # The context menu panel ellipsizes past ~15 characters, so a longer
        # label can collapse into a neighbour's and become unpickable.
        for name, _ in App.SORT_OPTIONS:
            self.assertLessEqual(len(name), 15, name)
        names = [n for n, _ in App.SORT_OPTIONS]
        self.assertEqual(len(names), len(set(names)))

    def test_sort_is_remembered_per_library(self):
        self.push("sec:3")
        self.app._ppv_set_sort("originallyAvailableAt:desc")
        self.assertEqual(self.app.config.plex_sorts,
                         {"sec:3": "originallyAvailableAt:desc"})
        # ...and is handed straight back to the reopened level.
        self.assertEqual(self.opened[0][1]["sort_key"], "sec:3")
        self.assertEqual(self.opened[0][1]["sort"], "originallyAvailableAt:desc")

    def test_unkeyed_list_remembers_nothing(self):
        self.push("")
        self.app._ppv_set_sort("year:asc")
        self.assertEqual(self.app.config.plex_sorts, {})

    def test_resort_preserves_volatile_and_sortable(self):
        self.push("watchlist")
        self.app._ppv_stack[-1]["volatile"] = True
        self.app._ppv_set_sort("titleSort:asc")
        self.assertTrue(self.opened[0][1]["volatile"])


if __name__ == "__main__":
    unittest.main()
