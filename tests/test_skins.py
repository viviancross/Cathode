"""Every skin draws every screen without a window, at its own canvas size,
in each of its colour themes: a skin-specific crash can't hide on a screen
nobody happened to open."""

import os
import sys
import time
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

    def note(self, text, seconds=2.5):
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
             summary="A summary of the film that runs well past what any box could hold. " * 6,
             offset=120 if i == 2 else 0, duration=6000) for i in range(14)]
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
    pb.transport = lambda: [(k, k, lambda: None) for k in ("prev", "back", "pause", "stop", "fwd", "next", "vol")]
    pb.handle = lambda a: True
    cap = NS(name="capture", prompt="Press the key for Guide  (Esc cancels)")
    rec = NS(**{**vars(info), "kind": "download"})       # a recording: Program Information, not an offer
    return [od(), od(view="wall"), od(depth=1), od(mode="auth"), od(key="recordings", rws=recs), info, rec, pb, cap]


class TestTube(unittest.TestCase):
    def frame(self, t, off=False):
        from cathode.app import draw_tube
        c = pygame.Surface((64, 48), pygame.SRCALPHA)     # all picture: transparent
        draw_tube(c, t, off)
        return c

    def test_on_opens_a_line_into_the_untouched_picture(self):
        c = self.frame(0.0)
        self.assertEqual(c.get_at((0, 0)), (0, 0, 0, 255))
        self.assertEqual(c.get_at((32, 24))[:3], (255, 255, 255))
        c = self.frame(1.0)
        self.assertEqual(c.get_at((0, 0)).a, 0)
        self.assertEqual(c.get_at((32, 24)).a, 0)

    def test_off_squashes_pinches_and_goes_dark(self):
        c = self.frame(0.6, off=True)                     # the line
        self.assertEqual(c.get_at((32, 24))[:3], (255, 255, 255))
        self.assertEqual(c.get_at((32, 10)), (0, 0, 0, 255))
        c = self.frame(1.0, off=True)
        for at in ((0, 0), (32, 24), (63, 47)):
            self.assertEqual(c.get_at(at), (0, 0, 0, 255))


class TestOnDemandEpisodes(unittest.TestCase):
    def view(self, wall_episodes, rows):
        from cathode.screens.ondemand import OnDemandScreen
        app = NS(config=NS(ppv_view="wall"), skin=NS(poster_wall=True, wall_episodes=wall_episodes))
        return OnDemandScreen.view.fget(NS(app=app, rows=rows))

    def test_a_skin_can_keep_a_season_a_list(self):
        sort, ep = dict(type="sort"), dict(type="episode", playable=True)
        self.assertEqual(self.view(False, [sort, ep]), "list")
        self.assertEqual(self.view(True, [sort, ep]), "wall")
        self.assertEqual(self.view(False, [sort, dict(type="movie", playable=True)]), "wall")
        self.assertEqual(self.view(False, [ep, dict(type="movie", playable=True)]), "wall")   # Continue Watching

    def test_browse_rows_carry_the_summary(self):
        from cathode.plex import _meta_row
        self.assertEqual(_meta_row(dict(type="movie", title="T", summary="S"))["summary"], "S")


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
        for name in ("indirect", "indirect_hd", "plate", "plate_hd", "igrid", "passage"):
            self.assertEqual(classes[name].tune_cover, "black", name)

    def test_the_cable_boxes_chrome_is_drawn_not_cut(self):
        """Every sprite the cable skins blit renders from chrome.py at its
        declared size; the asset folders hold only the brand marks."""
        import os
        from cathode.skins import chrome
        from cathode.paths import asset
        for skin, table in chrome.CHROME.items():
            for name, (size, ops) in table.items():
                self.assertEqual(chrome.render(size, ops).get_size(), size, f"{skin}/{name}")
            self.assertFalse(set(os.listdir(asset("skins", skin))) - {"cumcast.png", "tvgrid.png", "mark.png"}, skin)
        self.assertEqual(chrome.render((240, 180), chrome.passage_card(240, 180)).get_size(), (240, 180))

    def test_sd_skins_are_four_by_three(self):
        for name in ("indirect", "plate", "igrid", "passage"):
            w, h = skin_classes()[name].canvas
            self.assertAlmostEqual(w / h, 4 / 3, places=2)

    def test_the_guide_keeps_its_video_box_on_the_canvas(self):
        for name, cls in skin_classes().items():
            app = FakeApp()
            skin = cls(app)
            box = skin.guide_video_box()
            if box in ("hidden", "full"):   # a full-page guide (the DSS had none)
                continue
            x, y, w, h = box
            W, H = skin.canvas
            self.assertTrue(0 <= x and 0 <= y and x + w <= W and y + h <= H, name)


class TestCritique4(unittest.TestCase):
    def test_a_skin_knows_which_screen_is_on_top(self):
        app = FakeApp()
        skin = skin_classes()["classic"](app)
        a, b = object(), object()
        app.screens = [a, b]
        self.assertTrue(skin.on_top(b))
        self.assertFalse(skin.on_top(a))


if __name__ == "__main__":
    unittest.main()


class TestDisplayCasing(unittest.TestCase):
    def test_titles_keep_mixed_case_and_fix_capitals(self):
        from cathode.skins.box import nice
        self.assertEqual(nice("TV Shows"), "TV Shows")
        self.assertEqual(nice("TV SHOWS"), "TV Shows")
        self.assertEqual(nice("RETURN OF THE TEST CARD"), "Return of the Test Card")
        self.assertEqual(nice("STATIC HOUR: THE MOVIE"), "Static Hour: The Movie")


class TestPersonaFixes(unittest.TestCase):
    def test_plate_sd_puts_a_valueless_list_in_two_columns(self):
        from cathode.screens.menu import Item
        skin = skin_classes()["plate"](FakeApp())

        def menu(title, items, depth=2):
            return NS(title=title, items=items, pages=[None] * depth)
        rows = [Item(f"Row {i}", submenu=lambda: []) for i in range(7)]
        self.assertEqual(skin.menu_cols(menu("SETTINGS", rows)), 2)
        self.assertEqual(skin.menu_cols(menu("SETTINGS", rows[:6])), 1)        # fits as a list
        valued = rows[:6] + [Item("Motion", value=lambda: "On", adjust=lambda d: None)]
        self.assertEqual(skin.menu_cols(menu("PICTURE", valued)), 1)          # LEFT/RIGHT change values
        self.assertEqual(skin.menu_cols(menu("MAIN MENU", rows, depth=1)), 2)

    def test_diagnostics_name_the_codec(self):
        from cathode.screens.diagnostics import codec_name
        self.assertEqual(codec_name("h264"), "H.264")
        self.assertEqual(codec_name("prores"), "PRORES")
        self.assertEqual(codec_name(None), "-")

    def test_a_chip_names_the_keyboard_key_only_on_a_keyboard(self):
        app = FakeApp()
        app.remote = NS(last_device="keys")
        app.key_name = lambda a: {"MENU": "C"}.get(a, "")
        skin = skin_classes()["indirect_hd"](app)
        self.assertEqual(skin.key_also("MENU"), " (C)")
        app.remote.last_device = "pad"
        self.assertEqual(skin.key_also("MENU"), "")
        app.remote.last_device = "keys"
        app.config.remote = "sony_rm_y195"          # a remote chosen: its buttons, not keys
        self.assertEqual(skin.key_also("MENU"), "")


class TestProgrammeInfo(unittest.TestCase):
    """NostalgiaTV's info: the episode under the title in a cell that has
    room, a line of facts kept whole and spaced, every skin drawing them."""

    def test_cells_facts_and_wrapping(self):
        pygame.font.init()
        app = FakeApp()
        skin = skin_classes()["passage"](app)
        p = Program("c", "Futurama", datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(minutes=30),
                    episode="S2E4 - Xmas Story", rating="TV-14", air="Dec 19, 1999", quality="HD", minutes=22, score="8.0")
        f, lines = skin.cell_text(p.title, 400, 80, lambda s: skin.f(s), 20)
        self.assertEqual(lines, ["Futurama"])                   # a cell: the title alone
        f = skin.f(20)
        self.assertEqual(skin.fit_facts(f, "6:00", p, 10_000), "6:00   Dec 19, 1999   TV-14   HD   22 min   8.0/10")
        short = skin.fit_facts(f, "6:00", p, skin.width(f, "6:00   Dec 19, 1999   TV-1"))
        self.assertEqual(short, "6:00   Dec 19, 1999")                    # a fact dropped whole, never cut
        self.assertEqual(skin.text.wrap(f, "a   b\nc", 10_000, 2), ["a   b c"])


class TestLogosAndBug(unittest.TestCase):
    """Your logos (a folder, or a pick on the channel's page), one of its
    own for a channel Cathode made, animated GIF and APNG, and the screen
    bug: the logo at 15% in the bottom right while the channel is watched."""

    def setUp(self):
        import tempfile
        from cathode import logos
        self.tmp = tempfile.mkdtemp()
        self._folder = logos.folder
        logos.folder = lambda config: os.path.join(self.tmp, "logos")
        logos._listing["dir"] = None
        os.makedirs(os.path.join(self.tmp, "logos"))
        pygame.font.init()

    def tearDown(self):
        import shutil
        from cathode import logos
        logos.folder = self._folder
        logos._listing["dir"] = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def picture(self, name, color=(255, 0, 0, 255), frames=1):
        from PIL import Image
        p = os.path.join(self.tmp, "logos", name)
        ims = [Image.new("RGBA", (40, 20), color if k % 2 == 0 else (0, 0, 255, 255)) for k in range(frames)]
        ims[0].save(p, save_all=frames > 1, append_images=ims[1:], duration=100, loop=0)
        return p

    def test_whose_logo(self):
        from cathode import logos, lineup
        app = FakeApp()
        ch = app.channels[1]                                    # "Channel 4", from a playlist: no logo
        self.assertEqual(logos.url_for(app, ch), "")
        p = self.picture("channel 4.png")
        logos._listing["dir"] = None
        self.assertEqual(logos.url_for(app, ch), p)             # named for it
        self.assertEqual(logos.url_for(app, ch, "bug"), p)      # its bug: its logo
        bug = self.picture("Channel-4 Bug.gif")
        logos._listing["dir"] = None
        self.assertEqual(logos.url_for(app, ch, "bug"), bug)
        lineup.edit(app.config, ch, bug="off")
        self.assertEqual(logos.url_for(app, ch, "bug"), "")
        num = self.picture("4.png")
        logos._listing["dir"] = None
        lineup.edit(app.config, ch, logo="4.png", bug=None)
        self.assertEqual(logos.url_for(app, ch), num)           # picked on its page
        from cathode import libchannels as lc
        net = Channel(number=101, name="Cartoon Network", url="cathode://video/lib.ab12", epg_id="x",
                      logo="https://upload.wikimedia.org/Cartoon_Network_logo_%281992-2004%29.png")
        self.assertIn("Cartoon_Network_logo_%281992-2004%29", logos.url_for(app, net))     # the network's real one
        own = Channel(number=163, name="Nickelodeon", url="cathode://video/lib.ef56", epg_id="z",
                      logo="asset:channels/nickelodeon.png")
        self.assertTrue(os.path.isfile(logos.url_for(app, own)))        # one that comes with Cathode
        show = Channel(number=102, name="The Simpsons 24/7", url="cathode://video/lib.cd34", epg_id="y",
                       logo="/library/metadata/7/clearLogo/1")
        self.assertEqual(logos.url_for(app, show), "")                 # its title art needs the Plex server
        app.ondemand = NS(signed_in=True, client=lambda: NS(server="http://plex:32400",
                                                            photo_url=lambda path, w, h: f"http://plex:32400/photo{path}"))
        self.assertEqual(logos.url_for(app, show), "http://plex:32400/photo/library/metadata/7/clearLogo/1")

    def test_animated_gif_and_apng(self):
        from PIL import Image
        from cathode.logos import Animation, LogoStore
        store = LogoStore(os.path.join(self.tmp, "cache"))
        for name in ("a.gif", "a.png"):                         # (a PNG with frames is an APNG)
            with Image.open(self.picture(name, frames=3)) as f:
                im = store._decode(f)
            self.assertIsInstance(im, Animation, name)
            self.assertEqual((len(im.frames), im.at(0.15)[0]), (3, 1))

    def test_the_bug(self):
        from cathode import logos
        from cathode.logos import LogoStore
        from cathode.skins import skin_classes
        pygame.display.init()
        app = FakeApp()
        app.logos = LogoStore(os.path.join(self.tmp, "cache"))
        self.picture("channel 4.png", color=(255, 255, 255, 255))
        logos._listing["dir"] = None
        live = app.live
        live.idx, live.phase, live.message = 1, "watch", ""
        live.banner_until = 0
        app.top = lambda: live
        skin = skin_classes()["plate_hd"](app)
        app.skin = skin
        W, H = skin.canvas

        def draw():
            c = pygame.Surface((W, H), pygame.SRCALPHA)
            skin.draw(c, live)                                  # (the live screen, banner down)
            return c
        for _ in range(100):                                    # the logo loads off the UI thread
            if skin.logo(logos.url_for(app, live.channel, "bug"), 10, 10) is not None:
                break
            time.sleep(0.02)
        c = draw()
        m, size = H * 4 // 100, H * 9 // 100
        x, y = W - m - 2, H - m - size // 2                     # inside it, bottom right
        self.assertAlmostEqual(c.get_at((x, y))[3], 38, delta=3)        # 15%
        self.assertEqual(c.get_at((m + 2, H - m - size // 2))[3], 0)  # not bottom left
        app.config.bug_corner, app.config.bug_opacity = "top left", 50
        c = draw()
        self.assertAlmostEqual(c.get_at((m + 2, m + 2))[3], 128, delta=3)
        app.top = lambda: object()                              # a menu over the picture: no bug
        self.assertEqual(draw().get_at((m + 2, m + 2))[3], 0)
        app.top = lambda: live
        skin._in_break = lambda ch: True                        # a commercial: no bug, unless asked for
        self.assertEqual(draw().get_at((m + 2, m + 2))[3], 0)
        app.config.bug_in_breaks = True
        self.assertGreater(draw().get_at((m + 2, m + 2))[3], 0)
        app.config.bug_on = False
        self.assertEqual(draw().get_at((m + 2, m + 2))[3], 0)
        app.config.bug_on, app.config.bug_in_breaks = True, False
        skin._in_break = lambda ch: False
        skin.own_bug = lambda ch: {"corner": "top right", "width": 10, "opacity": 30, "margin": [5, 5]}  # Tunarr's
        c = draw()
        at = (W - W * 5 // 100 - 2, H * 5 // 100 + 2)
        self.assertAlmostEqual(c.get_at(at)[3], 77, delta=3)           # its corner, its opacity
        self.assertEqual(c.get_at((m + 2, m + 2))[3], 0)               # not the usual corner
        skin.own_bug = lambda ch: {"off": True}                         # none on this channel
        self.assertEqual(draw().get_at(at)[3], 0)
        del skin.own_bug
        app.config.bug_corner, app.config.bug_opacity = "bottom right", 15
        for name, cls in skin_classes().items():                # every skin's way of drawing the live screen
            skin = app.skin = cls(app)
            skin.reload()
            W, H = skin.canvas
            m, size = H * 4 // 100, H * 9 // 100
            for _ in range(100):
                if skin.logo(logos.url_for(app, live.channel, "bug"), size * 5 // 2, size) is not None:
                    break
                time.sleep(0.02)
            self.assertAlmostEqual(draw().get_at((W - m - 2, H - m - size // 2))[3], 38, delta=3, msg=name)
