"""The kernel: one UI thread, one event queue, a stack of screens.

Everything that changes state runs on the UI thread. Input, mpv's events,
timers and background work all arrive as events on SDL's queue; background
threads hand results over with `post()` instead of touching state. The loop
sleeps until something happens and draws only when something changed.
"""

import heapq
import itertools
import os
import sys
import threading
import time
from functools import partial
from typing import Callable, List, Optional

import pygame

from . import ownchannels, paths, playlist as m3u, remote as R, videochannels
from .config import Config
from .epg import EPG
from .logos import LogoStore
from .playlist import Channel

_CALL = pygame.event.custom_type()     # run a callable on the UI thread
_FRAME = pygame.event.custom_type()    # mpv has a new video frame


TUBE_ON, TUBE_OFF = 0.6, 0.44     # seconds


def draw_tube(c, t, off=False):
    """The set's tube, over any skin's frame, t from 0 to 1 through the move.
    On: a bright line opens into the picture. Off: the picture squashes into
    a bright line, the line pinches to a dot, the dot fades."""
    W, H = c.get_size()
    t, line = min(1.0, t), max(2, H // 240)
    v = None                                # the rect's own solid grey, when it holds no picture
    if not off:
        w, h, veil = max(2, int(W * min(1, t * 3))), max(line, int(H * t * t)), int(255 * (1 - t))
    elif t < 0.5:                           # ease out: the scan dies fast, then settles
        p = 1 - (1 - t / 0.5) ** 4
        w, h, veil = W, max(line, int(H * (1 - p))), int(255 * p)
    elif t < 0.77:
        w, h, v, veil = max(line, int(W * (1 - (t - 0.5) / 0.27) ** 2)), line, 255, 0
    else:
        w, h, v, veil = line * 2, line * 2, int(255 * (1 - (t - 0.77) / 0.23)), 0
    r = pygame.Rect((W - w) // 2, (H - h) // 2, w, h)
    for band in ((0, 0, W, r.y), (0, r.bottom, W, H - r.bottom), (0, r.y, r.x, h), (r.right, r.y, W - r.right, h)):
        c.fill((0, 0, 0, 255), band)
    if v is not None:
        c.fill((v, v, v, 255), r)
    elif veil:
        layer = pygame.Surface(r.size, pygame.SRCALPHA)
        layer.fill((255, 255, 255, veil))
        c.blit(layer, r)


class Screen:
    """Something on the stack. Screens hold state and react to remote
    buttons; the skin draws them."""
    name = "screen"     # the skin draws it with draw_<name>
    opaque = False      # hides everything below it

    def __init__(self, app: "App"):
        self.app = app

    def handle(self, action: str) -> bool:
        """True when the button was used; unused buttons fall through to the
        screen below."""
        return False

    def animating(self) -> bool:
        """True while the screen needs a frame every refresh."""
        return False

    def video_box(self):
        """Where this screen wants the video: "full", (x, y, w, h) in canvas
        pixels, or None for no say. An opaque screen with no say hides it
        (a full page has no picture behind it, and on a 4:3 skin it would
        otherwise show in the bars at the sides)."""
        return None

    def on_video(self, kind: str, **data):
        """mpv events: 'video_started', 'video_ended' (reason=...)."""


class App:
    EPG_REFRESH = 6 * 3600      # well inside epg.KEEP_AHEAD
    EPG_RETRY = 15 * 60

    def __init__(self, config: Config, fullscreen: bool = False, size=(1280, 720),
                 start_channel: Optional[int] = None):
        # Work on other threads (the video channels' schedules, yt-dlp) is
        # pure Python and holds the interpreter lock for 5 ms at a time by
        # default; this thread gives the lock up dozens of times a frame
        # (each mpv and GL call) and waited that long to get it back, so
        # frames ran late and mpv dropped them. Half a millisecond instead.
        sys.setswitchinterval(0.0005)
        self.config = config
        self.fullscreen = fullscreen
        self.size = size
        self.start_channel = start_channel
        self.channels: List[Channel] = []
        self.epg = EPG()
        self.screens: List[Screen] = []
        self.running = False
        self.dirty = True
        self.gfx = self.video = self.skin = self.remote = self.logos = None
        self.ondemand = None
        self._timers = []
        self._seq = itertools.count()
        self._frame_pending = False
        self.page_dirty = False     # an own channel's page has a new frame to show
        self._epg_gen = 0
        self._epg_checked = None    # the guide address last checked against the channels
        self.epg_failed = False     # the last guide load failed (vs loaded and empty)
        self._repeat = None
        self.shot = None            # (path, seconds): save a frame and exit (tests, CI)
        self._cursor_timer = None
        self.script = []            # [(seconds, button)]: scripted presses (tests, CI)
        self.toast_text, self.toast_until = "", 0.0
        self.note_text, self.note_until = "", 0.0   # a key's notice (FORMAT, SUBTITLE)
        self.guide_progress = None  # a guide load: None idle, -1 size unknown, else 0..1
        self._cats = None           # category list, rebuilt when channels or guide change
        self.last_input = time.monotonic()
        self.weather = None
        self.listings = {}          # a video channel source -> its fetched list (videochannels)
        self.schedules = {}         # video channel id -> videochannels.Schedule
        from . import spelunkr
        if spelunkr.ship(config) | videochannels.migrate(config):
            config.save()
        self.pending_update = None  # install script to run once we've quit
        self.restarting = False     # quit, then start again (the menu's Restart Cathode)
        self._tube_on_at = self._tube_off_at = None
        self._tube_open = False
        self.agent = config.user_agent  # the User-Agent the current playlist's provider answers to

    # ── Threads -> UI thread ──────────────────────────────────────────────

    def post(self, fn: Callable, *args, **kw):
        """Run fn(*args) on the UI thread. Safe from any thread."""
        pygame.event.post(pygame.event.Event(_CALL, fn=partial(fn, *args, **kw)))

    def _video_post(self, kind: str, **data):
        """mpv's threads call this. Frames are coalesced into one event."""
        if kind == "frame":
            pygame.event.post(pygame.event.Event(_FRAME))
        else:
            self.post(self._on_video, kind, **data)

    # ── Timers (UI thread only) ───────────────────────────────────────────

    def after(self, seconds: float, fn: Callable) -> list:
        t = [time.monotonic() + seconds, next(self._seq), fn, False]
        heapq.heappush(self._timers, t)
        return t

    @staticmethod
    def cancel(timer: Optional[list]):
        if timer:
            timer[3] = True

    def _run_timers(self):
        now = time.monotonic()
        while self._timers and self._timers[0][0] <= now:
            _, _, fn, cancelled = heapq.heappop(self._timers)
            if not cancelled:
                fn()

    def _tube(self):
        """(t, off) while the set is switching on or off, else None."""
        if self.shot or not self.config.motion_enabled:
            return None
        now = time.monotonic()
        if not self.running:
            self._tube_off_at = self._tube_off_at or now
            return (now - self._tube_off_at) / TUBE_OFF, True
        self._tube_on_at = self._tube_on_at or now
        t = (now - self._tube_on_at) / TUBE_ON
        if t < 1:
            return t, False
        if not self._tube_open:             # one clean frame to finish on
            self._tube_open = self.dirty = True
        return None

    def _wait_ms(self) -> int:
        if any(s.animating() for s in self.screens):
            return 1                    # vsync (or the GPU) paces animation
        while self._timers and self._timers[0][3]:
            heapq.heappop(self._timers)
        if not self._timers:
            return 1000
        return max(1, min(1000, int((self._timers[0][0] - time.monotonic()) * 1000) + 1))

    # ── Screens ───────────────────────────────────────────────────────────

    def push(self, screen: Screen):
        self.screens.append(screen)
        self.invalidate()

    def pop(self, screen: Optional[Screen] = None):
        if screen is None:
            screen = self.screens[-1]
        if screen in self.screens and len(self.screens) > 1:
            self.screens.remove(screen)
            self.invalidate()

    def top(self) -> Screen:
        return self.screens[-1]

    def find(self, cls):
        return next((s for s in self.screens if isinstance(s, cls)), None)

    def invalidate(self):
        self.dirty = True

    @property
    def live(self):
        from .screens.live import LiveTV
        return self.find(LiveTV)

    def toast(self, text: str, seconds: float = 2.5):
        """A short message over whatever is on screen."""
        self.toast_text, self.toast_until = text, time.monotonic() + seconds
        self.after(seconds + 0.01, self.invalidate)
        self.invalidate()

    # ── Channels, categories, favourites ──────────────────────────────────

    def categories(self) -> List[str]:
        """'All', 'Favorites', then every genre the lineup has: the guide's
        dominant XMLTV category for the channel, else its M3U group."""
        if self._cats is None:
            names = set()
            for ch in self.channels:
                cid = self.epg.resolve_channel_id(ch.epg_id, ch.name)
                ch.category = (self.epg.dominant_category(cid) if cid else "") or ch.group or ""
                if ch.category:
                    names.add(ch.category)
            self._cats = ["All", "Favorites"] + sorted(names, key=str.lower)
        return self._cats

    def channels_in(self, category: str) -> List[Channel]:
        self.categories()               # tags ch.category
        if category == "All":
            return self.channels
        if category == "Favorites":
            favs = set(self.config.favorites)
            return [c for c in self.channels if c.number in favs]
        return [c for c in self.channels if getattr(c, "category", "") == category]

    def is_favorite(self, ch: Channel) -> bool:
        return ch.number in self.config.favorites

    def toggle_favorite(self, ch: Channel):
        favs = self.config.favorites
        if ch.number in favs:
            favs.remove(ch.number)
            self.toast(f"Removed {ch.number} from favorites")
        else:
            favs.append(ch.number)
            self.toast(f"Added {ch.number} to favorites")
        self.config.save()

    def epg_horizon_min(self) -> int:
        """Minutes from now to the last programme the guide data has."""
        from datetime import datetime, timezone
        last = self.epg.last_stop()
        if not last:
            return 0
        return int((last - datetime.now(timezone.utc)).total_seconds() // 60)

    # ── Input ─────────────────────────────────────────────────────────────

    IDLE_SCREENSAVER = 300.0    # seconds of no input on a static page

    def _idle_check(self):
        """Arm the screensaver over pages that never change by themselves."""
        from .screens.boot import Boot
        from .screens.screensaver import Screensaver
        top = self.top()
        idle = time.monotonic() - self.last_input
        static = top.opaque or not self.channels    # a full page, or no TV playing
        if (self.config.screensaver and idle >= self.IDLE_SCREENSAVER and static
                and not isinstance(top, (Boot, Screensaver)) and top.name != "playback"):
            self.push(Screensaver(self))
        self.after(10.0, self._idle_check)

    def cycle_format(self, d: int = 1):
        """The FORMAT key: the next picture format, on every screen, kept
        across restarts; its notice shows the one now in use."""
        from .video import FORMATS
        keys = [k for k, _, _ in FORMATS]
        cur = self.config.picture_format
        self.config.picture_format = keys[((keys.index(cur) if cur in keys else 0) + d) % len(keys)]
        self.config.save()
        self.video.set_format(self.config.picture_format)
        from .video import format_label
        self.note(f"Format: {format_label(self.config.picture_format)}")

    def note(self, text: str, seconds: float = 2.5):
        """A key's notice, drawn in the skin's own style over any screen."""
        self.note_text, self.note_until = text, time.monotonic() + seconds
        self.after(seconds + 0.01, self.invalidate)
        self.invalidate()

    def cycle_subtitles(self):
        """The SUBTITLE key: off, then each of the stream's tracks (broadcast
        captions included); the choice carries on to the next channel."""
        name = self.video.cycle_subtitles()
        if name is None:
            self.note("Subtitles: none on this stream")
            return
        self.config.subtitles = bool(name)
        self.config.save()
        self.note(f"Subtitles: {name or 'Off'}")

    def press(self, action: str):
        """Offer a remote button to the screens, top first."""
        self.last_input = time.monotonic()
        self.sound("key")
        if action == R.FORMAT:          # like the box's key: works over any screen
            self.cycle_format()
            return
        if action == R.SUBTITLE:
            self.cycle_subtitles()
            return
        for s in reversed(self.screens):
            if s.handle(action):
                self.invalidate()
                return
        from . import menus
        if menus.handles_menu_button(self, action):
            self.invalidate()
        elif action == R.FULLSCREEN:
            self.toggle_fullscreen()
        elif action == R.QUIT:
            self.confirm_quit()

    def sound(self, which: str):
        """The box's UI sound, on a skin whose box made them ('key' on a
        press, 'bonk' on an error), at the Sound Effects level."""
        if not getattr(self.skin, "ui_sounds", False) or self.config.sound_effects == "off":
            return
        snd = getattr(self, "_sounds", None)
        if snd is None:
            from .sounds import Sounds
            snd = self._sounds = Sounds(self.config.sound_effects)
        snd.level = self.config.sound_effects
        getattr(snd, which)()

    def quit(self):
        self.running = False

    def restart(self):
        """Quit and start again as the same program with the same arguments."""
        self.restarting = True
        self.running = False

    def confirm_quit(self):
        """QUIT (Q) asks first, as the menu's Exit Cathode does: a key hunted
        for by a keyboard user mustn't end the evening. Q again on the
        question quits."""
        from .menus import _confirm
        from .screens.menu import Menu
        top = self.top()
        if isinstance(top, Menu) and top.title == "EXIT CATHODE?":
            self.quit()
            return
        self.push(Menu(self, "EXIT CATHODE?", _confirm(self, "Exit Cathode", self.quit, "Keep watching", close=True)))

    def click(self, wx: int, wy: int, button: int = 1):
        """A mouse click at window pixels. Left clicks hit what the skin drew
        last frame (topmost first); right is BACK, as a remote's back button."""
        if self.top().name == "screensaver":
            self.press(R.SELECT)        # any input just wakes it
            return
        if button == 3:
            self.press(R.BACK)
            return
        pt = self.gfx.to_canvas(self.skin.canvas, wx, wy)
        if pt is None:
            return
        for rect, fn in reversed(self.skin.hits):
            if rect.collidepoint(pt):
                fn()
                self.invalidate()
                return
        if button == 1 and len(self.screens) == 1:
            self.press(R.INFO)          # a click on plain live TV shows the banner

    def reload_remote(self):
        old = self.remote
        self.remote = R.Remote(self.config.key_bindings, self.config.gamepad_bindings)
        for keep in ("controllers", "families", "last_device", "pad_family"):
            setattr(self.remote, keep, getattr(old, keep))

    def set_skin(self, name: str):
        from .skins import load_skin
        self.config.skin = name
        self.config.save()
        self.skin = load_skin(name, self)
        self.invalidate()

    def switch_playlist(self, pl: dict):
        self.live.message = "Loading channels..."
        self.channels, self._cats = [], None
        self.use_agent(pl.get("user_agent", ""))
        self.load_playlist(pl.get("playlist_url", ""), pl.get("epg_url", ""))
        self.invalidate()

    def use_agent(self, agent: str):
        """The User-Agent this playlist's provider answers to (a player's,
        when it refused Cathode's own), for its fetches and its streams."""
        self.agent = agent or self.config.user_agent
        if getattr(self, "video", None) is not None:
            self.video.player["user-agent"] = self.agent

    def move_to_display(self, index: int):
        self.config.display = index
        self.config.save()
        self.gfx.move_to_display(index, self.fullscreen)
        self.invalidate()

    def _arm_repeat(self):
        """Held controller directions repeat on a timer (keyboards repeat by
        themselves via pygame.key.set_repeat)."""
        self.cancel(self._repeat)
        action = self.remote.held_action
        if action in R.REPEATABLE:
            def again():
                if self.remote.held_action == action:
                    self.press(action)
                    self._repeat = self.after(1 / self.config.nav_repeat_rate, again)
            self._repeat = self.after(self.config.nav_repeat_delay / 1000, again)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        pygame.display.toggle_fullscreen()
        self.invalidate()

    # ── Data ──────────────────────────────────────────────────────────────

    def key_name(self, action: str) -> str:
        """The first keyboard key bound to an action, for on-screen hints
        ('C' for MENU); '' when none is."""
        keys = [k.strip() or "," for k in self.remote.key_for(action).split(", ")] if self.remote else ["-"]
        # A letter first ("P", not "`"), then any typed key, then a media one ("AC Back").
        k = min(keys, key=lambda k: (k.lower().startswith(("ac ", "audio")), not (len(k) == 1 and k.isalnum())))
        return "" if k == "-" else k.upper()

    def press_hint(self, action: str) -> str:
        """'MENU (C)': the remote button and, for keyboards, its key; with a
        remote chosen in Settings, that remote's name for the button."""
        if self.remote and self.remote.last_device == "pad" and self.remote.pad_label(action):
            return self.remote.pad_label(action)
        if R.REMOTES.get(self.config.remote, R.REMOTES[""])[1]:
            return R.button_name(self.config.remote, action)
        k = self.key_name(action)
        return f"{action} ({k})" if k else action

    def load_playlist(self, url: str, epg_url: str = ""):
        """Fetch channels (and then the guide) off the UI thread."""
        if url.startswith("xtream://") and "/xmltv.php?" in epg_url:
            epg_url = url           # the line's guide comes the way its channels did
        def work():
            try:
                chans, agent, _used = m3u.load_as(url, user_agent=self.agent)
                if agent != self.agent:         # a provider that wanted a player's agent: keep it
                    self.agent = agent
                    for pl in self.config.playlists:
                        if pl.get("playlist_url") == url:
                            pl["user_agent"] = agent
                    self.config.save()
                    self.post(self.use_agent, agent)
                err = "" if chans else (f"Your playlist has no channels in it. Press {self.press_hint(R.MENU)} "
                                        "to check its address under Settings > Channels.")
            except Exception as e:
                print(f"[cathode] playlist load failed: {e!r}")
                chans, err = [], (f"Couldn't load your channels: {load_error_text(e)}. Press "
                                  f"{self.press_hint(R.MENU)} to check the address under Settings > Channels.")
            self.post(self._playlist_loaded, url, epg_url, chans, err)
        threading.Thread(target=work, daemon=True).start()

    def _playlist_loaded(self, url, epg_url, chans, err):
        from .screens.live import LiveTV
        live = self.find(LiveTV)
        if err:
            print(f"[cathode] {err}")
            live.message = err
            self.invalidate()
            return
        self.channels = videochannels.add_to(ownchannels.add_to(chans, self.config), self.config)
        self._cats = None
        self.config.playlist_url, self.config.epg_url = url, epg_url
        print(f"[cathode] {len(chans)} channels.")
        ownchannels.fill_guide(self.epg)
        videochannels.rebuild(self)         # Spelunkr's schedules and guide now, not after YouTube's lists
        videochannels.load(self)
        self.check_ytdl()
        live.channels_loaded()
        self._lineup_gen = getattr(self, "_lineup_gen", 0) + 1
        self.after(self.lineup_every(), lambda gen=self._lineup_gen: gen == self._lineup_gen and self.refresh_lineup())
        if not self.config.key_tip_shown and self.remote and not self.shot:
            # Once ever: which keys do what, the first time channels play.
            self.config.key_tip_shown = True
            self.config.save()
            # In the words of what's in hand: a pad's buttons, a chosen
            # remote's names, or the keyboard's letters.
            self.toast("   ".join(self.press_hint(a) for a in (R.GUIDE, R.MENU, R.INFO, R.OPTIONS))
                       + "   Channels: Up/Down", 9.0)
        self.load_epg()

    def lineup_every(self) -> float:
        """How often the lineup is fetched again: Spelunkr's every five
        minutes (as the site polls it: new channels, new versions), the
        rest with the guide."""
        from . import spelunkr
        return spelunkr.REFRESH if self.config.playlist_url == spelunkr.URL else self.EPG_REFRESH

    def refresh_lineup(self):
        """Fetch the playlist again, quietly: a channel added or removed on
        the server shows up without a restart. The channel playing stays
        playing; nothing is retuned."""
        url, gen = self.config.playlist_url, self._lineup_gen
        if not url:
            return

        def work():
            try:
                chans, _agent, _used = m3u.load_as(url, user_agent=self.agent)
            except Exception as e:
                print(f"[cathode] lineup refresh failed: {e!r}")
                chans = []
            self.post(self._lineup_refreshed, gen, url, chans)
        threading.Thread(target=work, daemon=True).start()

    def _lineup_refreshed(self, gen, url, chans):
        if gen != self._lineup_gen or url != self.config.playlist_url:
            return                          # the playlist changed under it
        self.after(self.lineup_every(), lambda: gen == self._lineup_gen and self.refresh_lineup())
        if not chans:
            return
        from . import spelunkr
        if url == spelunkr.URL:
            videochannels.rebuild(self)     # new versions on the air, the guide rolled on
        from .screens.live import LiveTV
        live = self.find(LiveTV)
        had = [c for c in self.channels if not ownchannels.is_own(c) and not videochannels.is_made(c)]
        before = {c.number for c in had}
        after = {c.number for c in chans}
        if before == after and [c.name for c in had] == [c.name for c in chans]:
            return
        current = live.channel.number if live and live.channel else None
        self.channels = videochannels.add_to(ownchannels.add_to(chans, self.config), self.config)
        videochannels.rebuild(self)
        self._cats = None
        if live and current is not None:
            live.idx = live.number_to_idx(current)
        print(f"[cathode] lineup refreshed: {len(chans)} channels "
              f"(+{len(after - before)}, -{len(before - after)}).")
        self.invalidate()

    def place_own_channels(self):
        """Cathode's own channels put in, moved or taken out after a settings
        change, the channel playing kept (retuned to the first if it went)."""
        live = self.live
        current = live.channel.number if live and live.channel else None
        plain = [c for c in self.channels if not ownchannels.is_own(c) and not videochannels.is_made(c)]
        self.channels = videochannels.add_to(ownchannels.add_to(plain, self.config), self.config)
        self._cats = None
        ownchannels.fill_guide(self.epg)
        videochannels.rebuild(self)
        if not getattr(self, "video_loading", False):
            videochannels.load(self)
        if live and current is not None and self.channels:
            idx = live.number_to_idx(current)
            if self.channels[idx].number != current:
                live.tune(idx)
            else:
                live.idx = idx
        self.invalidate()

    def load_epg(self):
        """Load the guide, then keep reloading it while this playlist stays
        loaded. A failed reload keeps the guide on screen and retries sooner.
        Results from a superseded load are dropped."""
        self._epg_gen += 1
        gen, url = self._epg_gen, self.config.epg_url
        if not url:
            return

        def progress(frac):
            self.post(self._guide_progress, gen, -1 if frac is None else frac)

        def work():
            err = ""
            try:
                epg = EPG()
                epg.load(url, user_agent=self.agent, progress=progress)
            except Exception as e:
                print(f"[cathode] EPG load failed: {e!r}")
                epg, err = None, load_error_text(e, "guide")
            self.post(self._epg_loaded, gen, url, epg, err)
        print("[cathode] Loading EPG...")
        self.guide_progress = -1
        threading.Thread(target=work, daemon=True).start()

    def _guide_progress(self, gen, frac):
        if gen == self._epg_gen and self.guide_progress is not None:
            self.guide_progress = frac
            self.invalidate()

    YTDL_CHECK = 7 * 86400

    def check_ytdl(self, manual: bool = False):
        """A newer yt-dlp fetched into the cache (it loads at the next start):
        weekly on its own, or now from Settings, which also says the result."""
        from . import ytdl
        if not manual and time.time() - self.config.ytdl_checked < self.YTDL_CHECK:
            return
        if manual:
            self.toast(f"Checking for a newer yt-dlp (running {ytdl.version()})...", 20.0)

        def work():
            try:
                got = ytdl.update()
                msg = (f"yt-dlp {got} fetched; it takes over when Cathode next starts." if got
                       else f"yt-dlp {ytdl.version()} is the newest.")
                ok = True
            except Exception as e:
                msg, ok = f"Couldn't update yt-dlp: {e.__class__.__name__}: {str(e)[:60]}", False
            print(f"[ytdl] {msg}")
            if manual or (ok and got):
                self.post(self.toast, msg, 8.0)
            if ok:
                self.post(self._ytdl_checked)
        threading.Thread(target=work, daemon=True).start()

    def _ytdl_checked(self):
        self.config.ytdl_checked = time.time()
        self.config.save()

    def _epg_loaded(self, gen, url, epg, err=""):
        if gen != self._epg_gen or url != self.config.epg_url:
            return                      # the playlist changed under it
        self.guide_progress = None
        self.epg_failed = epg is None
        if epg is not None:
            self.epg = epg
            self._cats = None           # genres come from the guide
            ids = ownchannels.real_ids(epg)
            print(f"[cathode] EPG loaded ({len(ids)} channels).")
            ownchannels.fill_guide(epg)
            for eid, progs in getattr(self, "video_programmes", {}).items():
                epg.set_programs(eid, progs)        # the video channels' last listings, at once
            videochannels.rebuild(self)             # and fresh ones, worked out off this thread
            if url != self._epg_checked:        # once per guide: one that matches nothing says so
                self._epg_checked = url
                chans = [ch for ch in self.channels if not ownchannels.is_own(ch) and not videochannels.is_video(ch)]
                missed = [ch for ch in chans if not epg.resolve_channel_id(ch.epg_id, ch.name)]
                print(f"[cathode] guide covers {len(chans) - len(missed)} of {len(chans)} channels"
                      + (f"; e.g. not " + ", ".join(f"{ch.name} (epg id {ch.epg_id or 'none'})" for ch in missed[:3])
                         if missed else "") + (f"; guide ids e.g. {', '.join(ids[:3])}" if missed else ""))
                if not ids:
                    self.toast("The guide loaded, but there's nothing in it. Check its address in "
                               "Settings > Channels.", 8.0)
                elif chans and not any(epg.resolve_channel_id(ch.epg_id, ch.name) for ch in chans):
                    self.toast("The guide loaded, but it lists none of these channels. Is it the guide "
                               "for this playlist?", 8.0)
            self.invalidate()
        elif not ownchannels.real_ids(self.epg):   # nothing to show: say why (a reload keeps the old guide quietly)
            self.toast(f"Couldn't load the guide: {err or 'it failed'}. Trying again in "
                       f"{self.EPG_RETRY // 60} minutes.", 8.0)
        self.after(self.EPG_REFRESH if epg is not None else self.EPG_RETRY,
                   lambda: gen == self._epg_gen and self.load_epg())

    # ── Video ─────────────────────────────────────────────────────────────

    def _on_video(self, kind, **data):
        if kind == "audio_fallback":        # the chosen output went away mid-session
            self.config.audio_device = ""
            self.config.save()
            self.toast("The audio output went away, so sound is on the default one.", 6.0)
            return
        if kind in ("video_started", "tracks_changed"):
            self.video.apply_subtitles(self.config.subtitles)
        for s in reversed(self.screens):
            s.on_video(kind, **data)
        self.invalidate()

    # ── Run ───────────────────────────────────────────────────────────────

    def run(self):
        from .gfx import Gfx
        from .video import Video
        from .skins import load_skin
        from .screens.live import LiveTV

        pygame.font.init()
        self.gfx = Gfx(self.size, self.fullscreen, display=self.config.display)
        print(f"[cathode] GL {self.gfx.version} | {self.gfx.renderer}")
        R.sdl_controller.init()
        pygame.key.set_repeat(self.config.nav_repeat_delay,
                              int(1000 / max(1, self.config.nav_repeat_rate)))
        pygame.display.set_allow_screensaver(False)     # a TV box keeps the set awake
        self._cursor_timer = self.after(self.CURSOR_HIDE, self._hide_cursor)   # a TV has no pointer
        self.remote = R.Remote(self.config.key_bindings, self.config.gamepad_bindings)
        self.logos = LogoStore(os.path.join(paths.cache_dir(), "logos"),
                               on_loaded=lambda: self.post(self.invalidate),
                               user_agent=self.config.user_agent)
        self.skin = load_skin(self.config.skin, self)
        self.video = Video(self._video_post, self.gfx.renderer,
                           user_agent=self.config.user_agent, volume=self.config.volume,
                           extra=_mpv_extra(self.config.mpv_extra_args),
                           log_path=os.path.join(paths.cache_dir(), "mpv.log") if self.config.mpv_verbose_log else "")
        self.video.attach_gl(self.gfx.get_proc_address)
        self.video.muted = self.config.muted
        self.video.set_format(self.config.picture_format)
        cfg = self.config
        self.video.sub_style(font=cfg.sub_font or None, size=cfg.sub_size, color=cfg.sub_color, back=cfg.sub_back)
        if self.config.audio_device:
            if self.video.has_audio_device(self.config.audio_device):
                self.video.audio_device = self.config.audio_device
            else:                           # saved on another PC, or unplugged: the default, and say so
                print(f"[cathode] audio output {self.config.audio_device!r} isn't on this computer: using the default")
                self.config.audio_device = ""
                self.config.save()
                self.after(1.5, lambda: self.toast("The saved audio output isn't on this computer, so sound is on "
                                                   "the default one. Change it under Settings > System > Audio output.", 8.0))
        from .ondemand import OnDemand
        self.ondemand = OnDemand(self)
        self.ondemand.downloads.resume()     # anything a quit or a dropout interrupted
        from .weather import Weather
        self.weather = Weather(self.config.weather_zip, self.config.weather_units,
                               self.config.weather_country,
                               on_update=lambda: self.post(self.invalidate),
                               user_agent=self.config.user_agent)
        if self.config.update_check and not self.shot:
            from . import update_flow
            update_flow.launch_check(self)
        self.after(10.0, self._idle_check)

        self.push(LiveTV(self))
        if self.config._load_error:
            self.after(1.5, lambda: self.toast(f"Your settings couldn't be read, so Cathode started fresh. "
                                               f"The old file was kept as {self.config._load_error}.", 10.0))
        for t, button in self.script:
            self.after(t, partial(self.press, button))
        if self.config.playlist_url:
            # The saved playlist's own agent, if its provider wanted a player's.
            self.use_agent(next((pl.get("user_agent", "") for pl in self.config.playlists
                                 if pl.get("playlist_url") == self.config.playlist_url), ""))
            self.load_playlist(self.config.playlist_url, self.config.epg_url)
            if self.config.boot_sequence and getattr(self.skin, "boot_scenes", None) != []:
                from .screens.boot import Boot
                self.push(Boot(self))
        else:
            from . import menus
            self.live.message = f"No channels yet. Press {self.press_hint(R.MENU)} to set up your channels."
            menus.open_welcome(self)

        canvas = pygame.Surface(self.skin.canvas, pygame.SRCALPHA)
        self.running = True
        t_start = time.monotonic()
        try:
            while True:
                tube = self._tube()
                if not self.running and (not tube or tube[0] >= 1):
                    break
                events = [pygame.event.wait(1 if tube or self.dirty else self._wait_ms())] + pygame.event.get()
                for e in events:
                    self._dispatch(e)
                self._run_timers()

                resized = self.gfx.begin()
                self._fit()
                # A scripted shot is taken on time even when nothing redraws
                # (a dead channel, a static page).
                due = bool(self.shot) and time.monotonic() - t_start >= self.shot[1]
                changed = resized or self.dirty or due
                anim = any(s.animating() for s in self.screens)
                if self.dirty or anim or tube:
                    self.dirty = False
                    if canvas.get_size() != self.skin.canvas:     # skin or window shape changed
                        canvas = pygame.Surface(self.skin.canvas, pygame.SRCALPHA)
                    canvas.fill((0, 0, 0, 0))
                    self.skin.hits = []
                    skin = self.skin
                    for s in self._visible():
                        skin.paint(canvas, s.name, lambda c, s=s: skin.draw(c, s), s)
                    top = self.top()
                    if self.guide_progress is not None and top.name in ("live", "guide"):
                        skin.paint(canvas, "progress", lambda c: skin.draw_guide_progress(c, self.guide_progress))
                    if time.monotonic() < self.note_until:
                        skin.paint(canvas, "note", lambda c: skin.draw_note(c, self.note_text))
                    if time.monotonic() < self.toast_until:
                        skin.paint(canvas, "toast", lambda c: skin.draw_toast(c, self.toast_text))
                    if tube:
                        draw_tube(canvas, *tube)
                    self.gfx.upload_ui(canvas, nearest=self.skin.nearest)
                    changed = True
                # After the UI: a menu just opened may want the picture in a box.
                box = self._video_box()
                vfbo, (vw, vh) = self.gfx.video.fbo, self.gfx.video.size
                page = self.live.page if self.live else None
                if page is not None:            # an own channel: its page is the picture
                    if self.page_dirty or self.gfx.video.size != page.size:
                        self.gfx.upload_video(page.frame())
                        self.page_dirty, changed = False, True
                    self._frame_pending = False
                elif self.gfx.fit_video(self.skin.canvas, box):     # reshaped: draw the frame again
                    vw, vh = self.gfx.video.size
                    if not self.video.render(vfbo, vw, vh):
                        self.video.redraw(vfbo, vw, vh)
                    changed, self._frame_pending = True, False
                elif self._frame_pending:
                    if self.video.render(vfbo, vw, vh):
                        changed = True
                    self._frame_pending = False
                if changed:
                    self._compose(box)
                    if self.shot and time.monotonic() - t_start >= self.shot[1]:
                        self.gfx.read_pixels().save(self.shot[0])
                        print(f"[cathode] saved {self.shot[0]}")
                        self.running = False
                    self.gfx.flip()
                    self.video.report_swap()
        finally:
            self._shutdown()

    def _visible(self):
        start = 0
        for i, s in enumerate(self.screens):
            if s.opaque:
                start = i
        return self.screens[start:]

    def _fit(self):
        """The skin's canvas for this window's shape (a 16:9 skin grows
        taller on a squarer one), and whether a 4:3 skin stretches to fill
        a wider one instead of sitting between bars."""
        cw, ch = type(self.skin).canvas
        self.gfx.stretch = self.config.stretch_43 and cw * 3 == ch * 4
        if self.skin.fit_window(self.gfx.size):
            self.dirty = True

    def _video_box(self):
        """Where the picture goes: "full", "hidden" or a canvas box (moved
        with its screen on a grown canvas)."""
        for s in reversed(self.screens):
            want = s.video_box()
            if want is not None:
                return self.skin.place_box(s, want) if isinstance(want, tuple) else want
            if s.opaque:
                return "hidden"
        return "full"

    def _compose(self, box):
        from .screens.live import LiveTV
        live = self.find(LiveTV)
        cover = live.cover() if live else None
        crt = (self.config.scanline_alpha / 115.0) if self.config.crt_enabled else 0.0
        self.gfx.compose(self.skin.canvas, video_box=box, cover=cover, crt=crt,
                         vignette=self.config.vignette_enabled, seed=time.monotonic() % 97)

    CURSOR_HIDE = 3.0           # seconds the mouse sits still before its pointer goes

    def _cursor_seen(self):
        """The mouse moved or clicked: show the pointer until it sits still."""
        pygame.mouse.set_visible(True)
        self.cancel(self._cursor_timer)
        self._cursor_timer = self.after(self.CURSOR_HIDE, self._hide_cursor)

    def _hide_cursor(self):
        self._cursor_timer = None
        pygame.mouse.set_visible(False)

    def _dispatch(self, e):
        if e.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEWHEEL):
            self._cursor_seen()
        elif e.type in (pygame.KEYDOWN, pygame.CONTROLLERBUTTONDOWN) and self._cursor_timer:
            self._hide_cursor()             # a remote or key in hand: the pointer is in the way
        if e.type == _CALL:
            e.fn()
        elif e.type == _FRAME:
            self._frame_pending = True
        elif e.type == pygame.QUIT:
            self.running = False
        elif e.type in (pygame.WINDOWRESIZED, pygame.WINDOWSIZECHANGED, pygame.WINDOWEXPOSED):
            self.invalidate()
        elif e.type == pygame.WINDOWFOCUSGAINED and self.ondemand:
            self.ondemand.downloads.resume()     # a sleep or a dropout may have paused it
        elif getattr(self.top(), "wants_raw", False) and self.top().raw(e):
            self.invalidate()           # a remap capture took it
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 3):
            self.click(*e.pos, button=e.button)
        elif getattr(self.top(), "wants_text", False) and self._text_event(e):
            pass
        else:
            for action in self.remote.translate(e):
                self.press(action)
            if e.type in (pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERBUTTONUP,
                          pygame.CONTROLLERAXISMOTION):
                self._arm_repeat()

    def _text_event(self, e) -> bool:
        """A real keyboard typing into the on-screen one: characters go in as
        typed, Enter submits, Ctrl+V pastes. Arrows, Backspace and Esc still
        act as remote buttons."""
        kb = self.top()
        self.last_input = time.monotonic()
        if e.type == pygame.TEXTINPUT:
            kb.text(e.text)
            return True
        if e.type != pygame.KEYDOWN:
            return False
        if e.key == pygame.K_v and e.mod & (pygame.KMOD_CTRL | pygame.KMOD_META):
            kb.paste()
            return True
        if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            kb._press("DONE")
            return True
        # Printable keys arrive again as TEXTINPUT; don't also run them as buttons.
        return bool(e.unicode) and e.unicode.isprintable() and not e.mod & pygame.KMOD_CTRL

    def _shutdown(self):
        try:
            self.config.volume = self.video.volume
            self.config.muted = self.video.muted
            self.config.save()
        except Exception as e:
            print(f"[cathode] couldn't save config: {e}")
        if self.video:
            self.video.terminate()
        pygame.quit()
        if self.pending_update:
            from . import updater
            updater.spawn_apply(self.pending_update)
        elif self.restarting:
            _relaunch()


def _relaunch():
    """This program again, detached, with the arguments it was started with:
    the frozen exe, the AppImage, or the interpreter on main.py."""
    import subprocess
    import sys
    if os.environ.get("APPIMAGE"):
        cmd = [os.environ["APPIMAGE"]] + sys.argv[1:]
    elif getattr(sys, "frozen", False):
        cmd = [sys.executable] + sys.argv[1:]
    else:
        cmd = [sys.executable] + sys.argv
    print(f"[cathode] restarting: {cmd[0]}")
    kw = {"creationflags": 0x00000208} if os.name == "nt" else {"start_new_session": True}   # detached, own group
    try:
        subprocess.Popen(cmd, close_fds=True, **kw)
    except Exception as e:
        print(f"[cathode] couldn't restart: {e!r}")


def load_error_text(e: Exception, what: str = "playlist") -> str:
    """Why a playlist didn't load, in words for the couch (the raw error
    goes to the log)."""
    import urllib.error
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 404:
            return "the server said it isn't there"
        if e.code == 401 or e.code >= 505 and e.code not in (505, 507, 508, 510, 511):
            # A provider panel's own codes (884, 512...) and the plain ones
            # mean the same: it doesn't accept these details.
            return (f"the provider didn't accept that link ({e.code}). Check the username and password in it, "
                    "that the line is active, and that no other app is signed in with it")
        return f"the server refused it ({e.code})"
    if isinstance(e, FileNotFoundError):
        return "there's no file at that address"
    if isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError)):
        return "the server didn't answer"
    if isinstance(e, ValueError):
        return f"that isn't a {what} address"
    return f"it isn't a {what} Cathode can read"


def _mpv_extra(args) -> dict:
    """config.mpv_extra_args (["--hwdec=no", ...]) as options for libmpv."""
    out = {}
    for a in args or []:
        a = a.lstrip("-")
        k, _, v = a.partition("=")
        out[k] = v or "yes"
    return out
