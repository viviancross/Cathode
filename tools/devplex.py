"""Run Cathode against a fake Plex server: canned libraries, movies and a
show whose 'streams' are mpv test patterns with an intro marker. For working
on the On Demand screens without a Plex account.

    python tools/devplex.py -w --config <a test config> [main.py options]
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import plex  # noqa: E402

MOVIES = ["The Long Signal", "Static Hour: The Movie", "Return of the Test Card", "Night Shift",
          "Color Bars Forever", "Ku-Band", "Clarke Belt", "Uplink", "Late Edition", "Weather Watch",
          "Prime Time", "Rerun Theater"]


FONT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts",
                    "LiberationSans-Bold.ttf")


def _poster(key, title, hue):
    """A made-up 2:3 poster (a file in the temp folder), so the On Demand
    screens show art."""
    path = os.path.join(tempfile.gettempdir(), f"cathode-devplex-poster-{key}.png")
    if not os.path.exists(path):
        import colorsys
        from PIL import Image, ImageDraw, ImageFont
        im = Image.new("RGB", (300, 450))
        d = ImageDraw.Draw(im)
        for y in range(450):
            r, g, b = colorsys.hsv_to_rgb(hue % 1, 0.7, 0.9 - 0.65 * y / 450)
            d.line([(0, y), (300, y)], fill=(int(r * 255), int(g * 255), int(b * 255)))
        d.ellipse((60, 70, 240, 250), outline=(255, 255, 255), width=6)
        small, big = ImageFont.truetype(FONT, 16), ImageFont.truetype(FONT, 36)
        d.text((150, 30), "A CATHODE PICTURE", font=small, fill=(255, 255, 255), anchor="mm")
        lines, line = [], ""
        for word in title.upper().split():
            if line and d.textlength(f"{line} {word}", font=big) > 260:
                lines.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        lines.append(line)
        for k, ln in enumerate(lines):
            d.text((150, 300 + k * 42), ln, font=big, fill=(255, 255, 255), anchor="mm")
        im.save(path)
    return path


def _movie(i, title):
    return {"type": "movie", "rating_key": f"m{i}", "title": title.upper(),
            "meta": f"{1980 + i}   PG   {6 + i % 4}.{i % 10}", "playable": True,
            "thumb": _poster(f"m{i}", title, i * 0.083), "duration": 600, "offset": 120 if i % 4 == 1 else 0}


def _episode(n):
    return {"type": "episode", "rating_key": f"e{n}", "title": f"S1E{n}  Episode {n}",
            "meta": "", "playable": True, "thumb": _poster("s1", "Test Patterns", 0.55), "duration": 300,
            "offset": 0}


SRT = "1\n00:00:01,000 --> 00:10:00,000\nSubtitles fetched for {title} ({lang}).\n"


class FakePlex(plex.PlexClient):
    fetched = {}                    # rating key -> subtitle files 'downloaded'

    def search_subtitles(self, rk, language="en"):
        stem = self.item_detail(rk)["title"].replace(" ", ".").replace(":", "")
        return [{"key": f"/fake/{rk}/{n}", "title": f"{stem}.{tag}.srt", "lang": language,
                 "provider": "OpenSubtitles", "exact": n == 0, "hi": n == 2, "forced": False}
                for n, tag in enumerate(["1984.1080p.BluRay.x264-CATHODE", "1984.DVDRip.XviD", "1984.SDH"])]

    def download_subtitle(self, rk, key):
        path = os.path.join(tempfile.gettempdir(), f"cathode-devplex-{rk}-{key.rsplit('/', 1)[-1]}.srt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(SRT.format(title=self.item_detail(rk)["title"], lang="English"))
        self.fetched.setdefault(rk, []).append({"url": path, "title": "English (SRT)", "lang": "en"})

    def subtitle_files(self, rk):
        return list(self.fetched.get(rk, []))

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
                     "meta": "8 eps", "playable": False, "thumb": _poster("s1", "Test Patterns", 0.55), "duration": 0,
                     "offset": 0}]
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
        return {"rating_key": rk, "title": title, "subtitle": "1984   PG   7.2" if movie else "S1",
                "summary": "A fake title for working on the On Demand screens. It plays one of "
                           "mpv's test patterns, with an intro marker from 0:02 to 0:20 so the "
                           "Skip Intro button shows.",
                "duration": 600, "offset": 120 if rk == "m1" else 0,
                "poster": _poster(rk, title, int(rk[1:]) * 0.083) if movie else _poster("s1", "Test Patterns", 0.55),
                "poster_headers": {}, "guid": f"plex://fake/{rk}",
                "type": "movie" if movie else ("show" if rk == "s1" else "episode"),
                "grandparent_key": "s1" if rk.startswith("e") else ""}

    def play_info(self, rk, quality="Original", resume=True):
        d = self.item_detail(rk)
        src = "testsrc2" if rk.startswith("m") else "smptehdbars"
        return {"url": f"av://lavfi:{src}=size=1280x720:rate=30:duration=600",
                "offset": d["offset"] if resume else 0, "time_base": 0, "duration": 600,
                "title": d["title"], "subtitle": d["subtitle"],
                "markers": [{"type": "intro", "start": 2, "end": 20}], "headers": {},
                "subs": self.subtitle_files(rk)}

    def report_timeline(self, *a, **k):
        pass

    def scrobble(self, rk):
        pass

    def watchlist_set(self, guid, add=True):
        return True

    def photo_url(self, path, w, h):
        return path                 # the made-up posters are files


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
