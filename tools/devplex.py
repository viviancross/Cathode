"""Run Cathode against a fake Plex server: canned libraries, movies and a
show whose 'streams' are mpv test patterns with an intro marker. For working
on the On Demand screens without a Plex account.

    python tools/devplex.py -w --config <a test config> [main.py options]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import plex  # noqa: E402

MOVIES = ["The Long Signal", "Static Hour: The Movie", "Return of the Test Card", "Night Shift",
          "Color Bars Forever", "Ku-Band", "Clarke Belt", "Uplink", "Late Edition", "Weather Watch",
          "Prime Time", "Rerun Theater"]


def _movie(i, title):
    return {"type": "movie", "rating_key": f"m{i}", "title": title.upper(),
            "meta": f"{1980 + i}   PG   {6 + i % 4}.{i % 10}", "playable": True,
            "thumb": "", "duration": 600, "offset": 120 if i % 4 == 1 else 0}


def _episode(n):
    return {"type": "episode", "rating_key": f"e{n}", "title": f"S1E{n}  Episode {n}",
            "meta": "", "playable": True, "thumb": "", "duration": 300, "offset": 0}


class FakePlex(plex.PlexClient):
    def discover_server(self, prefer=""):
        self.server = "http://fake-plex"
        return self.server

    def sections(self):
        return [{"key": "1", "title": "Movies", "type": "movie", "agent": "tv.plex.agents.movie"},
                {"key": "2", "title": "TV Shows", "type": "show", "agent": "tv.plex.agents.series"}]

    def list_servers(self):
        return []

    def home_users(self):
        return []

    def genres(self, key):
        return [{"id": "g1", "title": "Comedy"}, {"id": "g2", "title": "Drama"}]

    def section_filter(self, key, genre_id="", sort="", **kw):
        if key == "2":
            return [{"type": "show", "rating_key": "s1", "title": "TEST PATTERNS",
                     "meta": "8 eps", "playable": False, "thumb": "", "duration": 0, "offset": 0}]
        rows = [_movie(i, t) for i, t in enumerate(MOVIES)]
        return sorted(rows, key=lambda r: r["title"], reverse=sort.endswith("desc"))

    def children(self, key, sort=""):
        return [_episode(n) for n in range(1, 9)]

    def all_episodes(self, key):
        return self.children(key)

    def on_deck(self):
        return [_movie(1, MOVIES[1]), _episode(3)]

    def watchlist(self, sort=""):
        return []

    def search(self, q, limit=50):
        return [r for r in self.section_filter("1") if q.lower() in r["title"].lower()]

    def is_other_videos(self, section):
        return False

    def item_detail(self, rk):
        movie = rk.startswith("m")
        title = MOVIES[int(rk[1:])] if movie else ("Test Patterns" if rk == "s1" else f"Episode {rk[1:]}")
        return {"rating_key": rk, "title": title, "subtitle": "1984   PG   1h 40m" if movie else "S1",
                "summary": "A fake title for working on the On Demand screens. It plays one of "
                           "mpv's test patterns, with an intro marker from 0:02 to 0:20 so the "
                           "Skip Intro button shows.",
                "duration": 600, "offset": 120 if rk == "m1" else 0, "poster": "",
                "poster_headers": {}, "guid": f"plex://fake/{rk}",
                "type": "movie" if movie else ("show" if rk == "s1" else "episode"),
                "grandparent_key": "s1" if rk.startswith("e") else ""}

    def play_info(self, rk, quality="Original", resume=True):
        d = self.item_detail(rk)
        src = "testsrc2" if rk.startswith("m") else "smptehdbars"
        return {"url": f"av://lavfi:{src}=size=1280x720:rate=30:duration=600",
                "offset": d["offset"] if resume else 0, "time_base": 0, "duration": 600,
                "title": d["title"], "subtitle": d["subtitle"],
                "markers": [{"type": "intro", "start": 2, "end": 20}], "headers": {}}

    def report_timeline(self, *a, **k):
        pass

    def scrobble(self, rk):
        pass

    def watchlist_set(self, guid, add=True):
        return True

    def photo_url(self, path, w, h):
        return ""


if __name__ == "__main__":
    plex.PlexClient = FakePlex
    import main as cathode_main
    from cathode.config import Config
    # A signed-in account, without one. Only ever pass a throwaway --config.
    orig = Config._load

    def load(self):
        orig(self)
        self.plex_token = self.plex_token or "fake-token"
    Config._load = load
    cathode_main.main()
