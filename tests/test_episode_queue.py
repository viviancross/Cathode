"""Sequence-play queue: starting a single episode queues the rest of the show."""

import unittest

from cathode.app import App


def rows(*keys):
    return [{"rating_key": k, "title": f"Episode {k}"} for k in keys]


class TestEpisodeQueue(unittest.TestCase):
    eps = rows("10", "11", "12", "13")

    def keys(self, queue):
        return [e["rating_key"] for e in queue]

    def test_queues_from_selected_to_end(self):
        self.assertEqual(self.keys(App._episode_queue(self.eps, "11")),
                         ["11", "12", "13"])

    def test_first_episode_queues_whole_show(self):
        self.assertEqual(App._episode_queue(self.eps, "10"), self.eps)

    def test_last_episode_has_no_queue(self):
        self.assertEqual(App._episode_queue(self.eps, "13"), [])

    def test_unknown_episode_has_no_queue(self):
        self.assertEqual(App._episode_queue(self.eps, "99"), [])


if __name__ == "__main__":
    unittest.main()
