"""The kernel: one UI thread, one event queue, a stack of screens.

Everything that changes state runs on the UI thread. Input, mpv's events,
timers and background work all arrive as events on SDL's queue; background
threads hand results over with `post()` instead of touching state. The loop
sleeps until something happens and draws only when something changed.
"""

import heapq
import itertools
import os
import threading
import time
from functools import partial
from typing import Callable, List, Optional

import pygame

from . import paths, playlist as m3u, remote as R
from .config import Config
from .epg import EPG
from .logos import LogoStore
from .playlist import Channel

_CALL = pygame.event.custom_type()     # run a callable on the UI thread
_FRAME = pygame.event.custom_type()    # mpv has a new video frame


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
        """(x, y, w, h) in canvas pixels to show the video in, or None to
        leave it to the screen below (the bottom of the stack means full)."""
        return None

    def on_video(self, kind: str, **data):
        """mpv events: 'video_started', 'video_ended' (reason=...)."""


class App:
    EPG_REFRESH = 6 * 3600      # well inside epg.KEEP_AHEAD
    EPG_RETRY = 15 * 60

    def __init__(self, config: Config, fullscreen: bool = False, size=(1280, 720),
                 start_channel: Optional[int] = None):
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
        self._timers = []
        self._seq = itertools.count()
        self._frame_pending = False
        self._epg_gen = 0
        self._repeat = None
        self.shot = None            # (path, seconds): save a frame and exit (tests, CI)
        self.script = []            # [(seconds, button)]: scripted presses (tests, CI)

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

    # ── Input ─────────────────────────────────────────────────────────────

    def press(self, action: str):
        """Offer a remote button to the screens, top first."""
        for s in reversed(self.screens):
            if s.handle(action):
                self.invalidate()
                return
        if action == R.FULLSCREEN:
            self.toggle_fullscreen()
        elif action == R.QUIT:
            self.running = False

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

    def load_playlist(self, url: str, epg_url: str = ""):
        """Fetch channels (and then the guide) off the UI thread."""
        def work():
            try:
                chans = m3u.load(url, user_agent=self.config.user_agent)
                err = "" if chans else "The playlist has no channels."
            except Exception as e:
                chans, err = [], f"Couldn't load the playlist: {e}"
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
        self.channels = chans
        self.config.playlist_url, self.config.epg_url = url, epg_url
        print(f"[cathode] {len(chans)} channels.")
        live.channels_loaded()
        self.load_epg()

    def load_epg(self):
        """Load the guide, then keep reloading it while this playlist stays
        loaded. A failed reload keeps the guide on screen and retries sooner.
        Results from a superseded load are dropped."""
        self._epg_gen += 1
        gen, url = self._epg_gen, self.config.epg_url
        if not url:
            return

        def work():
            try:
                epg = EPG()
                epg.load(url, user_agent=self.config.user_agent)
            except Exception as e:
                print(f"[cathode] EPG load failed: {e}")
                epg = None
            self.post(self._epg_loaded, gen, url, epg)
        print("[cathode] Loading EPG...")
        threading.Thread(target=work, daemon=True).start()

    def _epg_loaded(self, gen, url, epg):
        if gen != self._epg_gen or url != self.config.epg_url:
            return                      # the playlist changed under it
        if epg is not None:
            self.epg = epg
            print(f"[cathode] EPG loaded ({len(epg.channel_ids)} channels).")
            self.invalidate()
        self.after(self.EPG_REFRESH if epg is not None else self.EPG_RETRY,
                   lambda: gen == self._epg_gen and self.load_epg())

    # ── Video ─────────────────────────────────────────────────────────────

    def _on_video(self, kind, **data):
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
        self.gfx = Gfx(self.size, self.fullscreen)
        print(f"[cathode] GL {self.gfx.version} | {self.gfx.renderer}")
        R.sdl_controller.init()
        pygame.key.set_repeat(self.config.nav_repeat_delay,
                              int(1000 / max(1, self.config.nav_repeat_rate)))
        pygame.display.set_allow_screensaver(False)     # a TV box keeps the set awake
        self.remote = R.Remote(self.config.key_bindings, self.config.gamepad_bindings)
        self.logos = LogoStore(os.path.join(paths.cache_dir(), "logos"),
                               on_loaded=lambda: self.post(self.invalidate),
                               user_agent=self.config.user_agent)
        self.skin = load_skin(self.config.skin, self)
        self.video = Video(self._video_post, self.gfx.renderer,
                           user_agent=self.config.user_agent, volume=self.config.volume,
                           extra=_mpv_extra(self.config.mpv_extra_args))
        self.video.attach_gl(self.gfx.get_proc_address)
        self.video.muted = self.config.muted

        self.push(LiveTV(self))
        for t, button in self.script:
            self.after(t, partial(self.press, button))
        if self.config.playlist_url:
            self.load_playlist(self.config.playlist_url, self.config.epg_url)

        canvas = pygame.Surface(self.skin.canvas, pygame.SRCALPHA)
        self.running = True
        t_start = time.monotonic()
        try:
            while self.running:
                events = [pygame.event.wait(self._wait_ms())] + pygame.event.get()
                for e in events:
                    self._dispatch(e)
                self._run_timers()

                resized = self.gfx.begin()
                changed = resized or self.dirty
                if self._frame_pending or resized:
                    w, h = self.gfx.size
                    if self.video.render(self.gfx.video.fbo, w, h):
                        changed = True
                    elif resized:
                        self.video.redraw(self.gfx.video.fbo, w, h)
                    self._frame_pending = False
                anim = any(s.animating() for s in self.screens)
                if self.dirty or anim:
                    self.dirty = False
                    canvas.fill((0, 0, 0, 0))
                    for s in self._visible():
                        self.skin.draw(canvas, s)
                    self.gfx.upload_ui(canvas, nearest=self.skin.nearest)
                    changed = True
                if changed:
                    self._compose()
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

    def _compose(self):
        box = None
        for s in reversed(self.screens):
            box = s.video_box()
            if box is not None:
                break
        from .screens.live import LiveTV
        live = self.find(LiveTV)
        cover = live.cover() if live else None
        crt = (self.config.scanline_alpha / 115.0) if self.config.crt_enabled else 0.0
        self.gfx.compose(self.skin.canvas, video_box=box, cover=cover, crt=crt,
                         vignette=self.config.vignette_enabled, seed=time.monotonic() % 97)

    def _dispatch(self, e):
        if e.type == _CALL:
            e.fn()
        elif e.type == _FRAME:
            self._frame_pending = True
        elif e.type == pygame.QUIT:
            self.running = False
        elif e.type in (pygame.WINDOWRESIZED, pygame.WINDOWSIZECHANGED, pygame.WINDOWEXPOSED):
            self.invalidate()
        else:
            for action in self.remote.translate(e):
                self.press(action)
            if e.type in (pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERBUTTONUP,
                          pygame.CONTROLLERAXISMOTION):
                self._arm_repeat()

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


def _mpv_extra(args) -> dict:
    """config.mpv_extra_args (["--hwdec=no", ...]) as options for libmpv."""
    out = {}
    for a in args or []:
        a = a.lstrip("-")
        k, _, v = a.partition("=")
        out[k] = v or "yes"
    return out
