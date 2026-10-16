"""Every skin draws every screen without a window, at its own canvas size,
in each of its colour themes: a skin-specific crash can't hide on a screen
nobody happened to open."""

import os
import sys
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from cathode.config import Config  # noqa: E402
from cathode.epg import EPG, Program  # noqa: E402
from cathode.playlist import Channel  # noqa: E402
from cathode.skins import skin_classes  # noqa: E402


class FakeVideo:
    volume, muted, paused = 40, False, False

    def buffered_behind(self):
        return 30.0


class FakeApp:
    def __init__(self):
        from cathode.screens.live import LiveTV
        self.config = Config("")
        self.channels = [Channel(number=n, name=f"Channel {n}", url="u", epg_id=f"c{n}", group="News")
                         for n in (2, 4, 5, 7, 9, 11, 13)]
        self.epg = EPG()
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        for ch in self.channels:
            self.epg.add_programs(ch.epg_id, [
                Program(ch.epg_id, f"Show {i}", now + timedelta(minutes=30 * i),
                        now + timedelta(minutes=30 * (i + 1)), description="A description " * 8,
                        category="News", rating="TV-PG") for i in range(-2, 10)])
        self.video = FakeVideo()
        self.logos = None
        self.weather = None
        self.ondemand = None
        self.screens = []
        self.start_channel = None
        self.skin = None
        self.live = LiveTV(self)

    def after(self, s, fn):
        return [1e18, 0, fn, False]

    def cancel(self, t):
        pass

    def invalidate(self):
        pass

    def categories(self):
        return ["All", "Favorites", "News"]

    def channels_in(self, cat):
        return self.channels

    def is_favorite(self, ch):
        return ch.number == 4

    def push(self, s):
        self.screens.append(s)

    def pop(self, s=None):
        pass


def screens(app):
    from cathode.screens.boot import Boot
    from cathode.screens.browse import Browse
    from cathode.screens.diagnostics import Diagnostics
    from cathode.screens.guide import Guide
    from cathode.screens.menu import Item, Keyboard, Menu
    from cathode.screens.miniguide import MiniGuide
    from cathode.screens.screensaver import Screensaver
    live = app.live
    live.idx, live.phase = 1, "watch"
    live.show_banner()
    live.digits = "12"
    diag = Diagnostics.__new__(Diagnostics)
    diag.app, diag.stats = app, {"video-bitrate": 4e6, "width": 1280, "height": 720}
    pygame.key.start_text_input = lambda: None
    main = Menu(app, "MAIN MENU", [Item(f"Item {i}", lambda: None) for i in range(7)])
    sub = Menu(app, "SETTINGS", [Item("Value", value=lambda: "On", adjust=lambda d: None),
                                 Item("Sub", submenu=lambda: [])])
    return [live, Guide(app), Browse(app), MiniGuide(app), main, sub,
            Keyboard(app, "Prompt", lambda v: None, "text"), Boot(app), Screensaver(app), diag]


class FakeOnDemand:
    def __init__(self):
        self.queue = NS(items=[1, 2, 3], pos=0)
        self.downloads = NS(root=".")

    def poster(self, *a):
        return None


def page_screens():
    """On Demand (list, wall, top level, link code, My Recordings), an item's
    info, playback and the remote-capture prompt, from made-up data."""
    rows = [dict(type="sort", title="Sort by: Title", meta="")] + [
        dict(type="movie", title=f"MOVIE NUMBER {i}", meta=f"{1980 + i}   PG   7.{i}", playable=True,
             offset=120 if i == 2 else 0, duration=600) for i in range(14)]
    recs = [dict(type="download", title=f"Recording {i}", meta="42%" if i == 1 else "", playable=i != 1,
                 state="downloading" if i == 1 else "done") for i in range(8)]

    def od(view="list", mode="browse", key="", depth=2, rws=rows):
        level = dict(title="ALL MOVIES", rows=rws, sel=3, key=key)
        parent = dict(title="MOVIES", rows=[dict(title="ALL MOVIES"), dict(title="COMEDY")], sel=0, key="")
        s = NS(name="ondemand", mode=mode, status="", view=view, stack=([parent] if depth > 1 else []) + [level],
               level=level, rows=rws, sel=3, wall_offset=1 if rws is rows else 0, auth_code="AB12",
               auth_link="plex.tv/link", side=None)
        s.crumb = lambda: "On Demand / Movies"
        s.current = lambda: rws[3]
        s.select = s.back = lambda: None
        s.handle = lambda a: True
        return s
    info = NS(name="iteminfo", focus=1, kind="default", detail=dict(title="Movie Number 3", subtitle="1983   PG   7.3",
                                                    summary="A summary of the film. " * 12, duration=6000, offset=120))
    info.buttons = lambda: ["play", "dvr", "queue", "watchlist", "back"]
    info.label = lambda b: {"play": "PLAY", "dvr": "REC 40%", "queue": "+ QUEUE", "watchlist": "+ WATCHLIST",
                            "back": "BACK"}[b]
    info.press = lambda b: None
    pb = NS(name="playback", title="Movie Number 3", subtitle="1983", pos=120.0, dur=600.0, skip_label="SKIP INTRO",
            flash=("", 0))
    pb.bar_visible = lambda: True
    pb.seek_to = pb.toggle_pause = pb.stop = pb.skip = pb.seek = lambda *a: None
    pb.transport = lambda: [(k, k, lambda: None) for k in ("prev", "back", "pause", "stop", "fwd", "next")]
    pb.handle = lambda a: True
    cap = NS(name="capture", prompt="Press the key for Guide  (Esc cancels)")
    rec = NS(**{**vars(info), "kind": "download"})       # a recording: Program Information, not an offer
    return [od(), od(view="wall"), od(depth=1), od(mode="auth"), od(key="recordings", rws=recs), info, rec, pb, cap]


class TestPictureFormat(unittest.TestCase):
    def test_every_format_sets_mpv_and_unknown_keys_fall_back(self):
        from cathode.video import FORMATS, Video
        v = Video.__new__(Video)
        v.player = {}
        for key, _, props in FORMATS:
            v.set_format(key)
            self.assertEqual({k: v.player[k] for k in props}, props)
        v.set_format("nonsense")
        self.assertEqual(v.player["panscan"], 0.0)
        self.assertIs(v.player["keepaspect"], True)


class FakePlayer:
    """mpv's track list and sid, as Video reads and sets them."""
    def __init__(self, subs):
        self.track_list = [{"type": "audio", "id": 1, "selected": True}] + subs

    def __setitem__(self, name, value):
        for t in self.track_list:
            if t["type"] == "sub" and name == "sid":
                t["selected"] = t["id"] == value


class TestSubtitles(unittest.TestCase):
    def _video(self, *subs):
        from cathode.video import Video
        v = Video.__new__(Video)
        v.player = FakePlayer([dict(type="sub", selected=False, **s) for s in subs])
        return v

    def _on(self, v):
        return [t["name"] for t in v.tracks("sub") if t["selected"]]

    def test_tracks_get_names_a_person_would_use(self):
        v = self._video({"id": 1, "codec": "eia_608"}, {"id": 2, "lang": "eng"}, {"id": 3, "title": "Commentary"},
                        {"id": 4})
        self.assertEqual([t["name"] for t in v.tracks("sub")], ["Closed captions", "ENG", "Commentary", "Track 4"])

    def test_the_setting_picks_the_first_track_or_none(self):
        v = self._video({"id": 1, "codec": "eia_608"}, {"id": 2, "lang": "eng"})
        v.apply_subtitles(True)
        self.assertEqual(self._on(v), ["Closed captions"])
        v.set_track("sub", 2)
        v.apply_subtitles(True)                     # a chosen track is kept
        self.assertEqual(self._on(v), ["ENG"])
        v.apply_subtitles(False)
        self.assertEqual(self._on(v), [])

    def test_the_key_cycles_off_then_each_track(self):
        v = self._video({"id": 1, "codec": "eia_608"}, {"id": 2, "lang": "eng"})
        self.assertEqual([v.cycle_subtitles() for _ in range(4)], ["Closed captions", "ENG", "", "Closed captions"])
        self.assertIsNone(self._video().cycle_subtitles())


class TestEverySkinDrawsEveryScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.font.init()

    def test_all(self):
        for name, cls in skin_classes().items():
            app = FakeApp()
            app.config.skin = name
            skin = cls(app)
            app.skin = skin
            themes = [k for k, _ in skin.theme_choices() if k != "custom"][:3]
            for theme in themes:
                skin.set_theme_key(theme)
                skin.reload()
                canvas = pygame.Surface(skin.canvas, pygame.SRCALPHA)
                for s in screens(app):
                    with self.subTest(skin=name, theme=theme, screen=s.name):
                        canvas.fill((0, 0, 0, 0))
                        skin.hits = []
                        skin.draw(canvas, s)
                        if s.name in ("live", "guide", "menu", "keyboard", "boot", "diagnostics"):
                            self.assertIsNotNone(canvas.get_bounding_rect(min_alpha=1).w)

    def test_on_demand_pages_toasts_and_messages(self):
        for name, cls in skin_classes().items():
            app = FakeApp()
            app.config.skin = name
            app.ondemand = FakeOnDemand()
            skin = cls(app)
            app.skin = skin
            for theme in [k for k, _ in skin.theme_choices() if k != "custom"][:3]:
                skin.set_theme_key(theme)
                skin.reload()
                canvas = pygame.Surface(skin.canvas, pygame.SRCALPHA)
                for k, s in enumerate(page_screens()):
                    with self.subTest(skin=name, theme=theme, screen=f"{s.name}{k}"):
                        canvas.fill((0, 0, 0, 0))
                        skin.hits = []
                        skin.draw(canvas, s)
                        self.assertIsNotNone(canvas.get_bounding_rect(min_alpha=1).w)
                with self.subTest(skin=name, theme=theme, screen="toast+message"):
                    skin.draw_toast(canvas, "Deleted from My Recordings")
                    skin._message(canvas, "Couldn't load the playlist: the server said no.")
                for frac in (-1, 0.0, 0.4, 1.0):
                    with self.subTest(skin=name, theme=theme, screen=f"guide progress {frac}"):
                        canvas.fill((0, 0, 0, 0))
                        skin.draw_guide_progress(canvas, frac)
                        self.assertIsNotNone(canvas.get_bounding_rect(min_alpha=1).w)
                with self.subTest(skin=name, theme=theme, screen="empty favorites"):
                    from cathode.screens.guide import Guide
                    g = Guide(app, category="Favorites")
                    with mock.patch.object(app, "channels_in", lambda cat: []):
                        canvas.fill((0, 0, 0, 0))
                        skin.draw(canvas, g)
                    self.assertIn("favorites", skin.empty_guide(g))
                with self.subTest(skin=name, theme=theme, screen="format"):
                    for label in ("Original", "Zoom", "Stretch", "4:3"):
                        skin.draw_note(canvas, f"Format: {label}")
                    skin.draw_note(canvas, "Subtitles: Closed captions")

    def test_box_skins_cut_to_black_and_classic_keeps_static(self):
        classes = skin_classes()
        self.assertEqual(classes["classic"].tune_cover, "static")
        for name in ("indirect", "indirect_hd", "plate", "plate_hd"):
            self.assertEqual(classes[name].tune_cover, "black", name)

    def test_sd_skins_are_four_by_three(self):
        for name in ("indirect", "plate"):
            w, h = skin_classes()[name].canvas
            self.assertAlmostEqual(w / h, 4 / 3, places=2)

    def test_the_guide_keeps_its_video_box_on_the_canvas(self):
        for name, cls in skin_classes().items():
            app = FakeApp()
            skin = cls(app)
            box = skin.guide_video_box()
            if box == "hidden":             # a full-page guide (the DSS had no picture window)
                continue
            x, y, w, h = box
            W, H = skin.canvas
            self.assertTrue(0 <= x and 0 <= y and x + w <= W and y + h <= H, name)


if __name__ == "__main__":
    unittest.main()
