"""Main application — wires player, playlist, EPG, and UI together."""

from __future__ import annotations

import os
import sys
import time
import threading
from typing import Optional, List

from .config import Config
from .player import Player
from . import playlist as m3u
from . import plex
from . import weather
from .epg import EPG
from .playlist import Channel
from .ui.renderer import Renderer, UIState
from .ui import theme
from .ui.menu import MenuItem


class App:
    """
    Cathode application.

    Key map (Steam Deck / keyboard):
      CH UP / CH DOWN   : Up / Down arrow
      Direct channel    : 0-9 (then Enter or 2-sec timeout)
      Volume up/down    : Right / Left arrow (in WATCHING mode)
      Mute              : M
      Info / OSD toggle : I  or  Tab
      Guide toggle      : G
      Guide navigate    : Up/Down/Left/Right inside guide
      Guide select      : Enter
      Fullscreen toggle : W  (or double-click the window)
      Context menu      : right-click  (arrows/Enter/click to navigate)
      Quit              : Q
      Escape            : closes menu/guide/OSD, else exits fullscreen
    """

    DIGIT_TIMEOUT = 2.0  # seconds to wait after last digit before tuning

    # Built-in look presets (theme + font + scanline intensity). Not deletable.
    BUILTIN_PROFILES = {
        "Classic Blue":   {"theme": "blue",  "font": "vcr",        "scanline_alpha": 40},
        "Amber Terminal": {"theme": "amber", "font": "vt220",      "scanline_alpha": 50},
        "Green Phosphor": {"theme": "green", "font": "ibm",        "scanline_alpha": 50},
        "Synthwave":      {"theme": "synth", "font": "handjet", "scanline_alpha": 40},
        "Commodore":      {"theme": "c64",   "font": "dotgothic", "scanline_alpha": 40},
        "Monochrome":     {"theme": "mono",  "font": "dejavu",     "scanline_alpha": 30},
    }

    def __init__(
        self,
        config: Config,
        width: int = 1920,
        height: int = 1080,
        fullscreen: bool = True,
        start_channel: Optional[int] = None,
        demo: bool = False,
        mpv_backend: str = "auto",
    ):
        self.config     = config
        self.width      = width
        self.height     = height
        self.demo       = demo
        self.channels:  List[Channel] = []
        self.epg:       Optional[EPG] = None

        # Digit-entry state for direct channel selection
        self._digit_buf: str = ""
        self._digit_timer: Optional[threading.Timer] = None

        # Runtime dir shared with mpv for the IPC socket + overlay buffer.
        if os.name == "nt":
            cache_base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        else:
            cache_base = os.environ.get(
                "XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
        runtime_dir = os.path.join(cache_base, "cathode")
        os.makedirs(runtime_dir, exist_ok=True)
        self._runtime_dir = runtime_dir       # also holds downloaded updates
        overlay_path = os.path.join(runtime_dir, "overlay.bgra")

        # Appearance: resolve + apply the active color theme (migrating any
        # legacy config fields), then the font (with graceful fallback).
        self._migrate_themes()
        self._active_theme = self._resolve_initial_theme()
        self._apply_theme_colors(self._active_theme)
        if not theme.set_font(config.font):
            avail = theme.available_fonts()
            if avail:
                theme.set_font(avail[0])

        # Player (controls Flatpak/system mpv over JSON IPC)
        self.player = Player(
            runtime_dir=runtime_dir,
            width=width,
            height=height,
            fullscreen=fullscreen,
            user_agent=config.user_agent,
            on_eof=self._on_eof,
            on_resize=self._on_osd_resize,
            on_playback_started=self._on_playback_started,
            on_mouse_pos=self._on_mouse_pos,
            backend=mpv_backend,
            extra_args=config.mpv_extra_args,
            mpv_path=config.mpv_path,
            ar_delay=config.nav_repeat_delay,
            ar_rate=config.nav_repeat_rate,
        )
        self._fullscreen = fullscreen   # tracked so Esc can exit fullscreen
        self._active_profile = None     # last-applied look profile (for editor "Save")
        self._last_mouse = (0, 0)       # last reported mouse position
        self._input_mode = "key"        # "key" or "gamepad" — drives nav hints

        # Plex-Per-View
        self._plex = None               # lazy PlexClient
        self._ppv_stack = []            # browse levels: [{title, rows, sel, crumb}]
        self._ppv_pin_id = None
        self._plex_paused = False
        self._plex_duration = None
        self._plex_monitor = False
        self._plex_osd_until = 0.0
        self._plex_pos = 0.0            # last known playback position (s)
        self._plex_now_rk = ""          # ratingKey of the item playing now
        self._plex_info_data = None     # detail dict for the info screen
        self._plex_queue = []           # ordered ratingKeys (Play All / Shuffle)
        self._plex_queue_pos = 0        # index of the item playing now
        self._plex_last_report = 0.0    # monotonic ts of last timeline heartbeat
        self._plex_lock = threading.Lock()   # guards PlexClient access/rebuild
        self._plex_markers = []         # intro/credits ranges for the item playing now

        # Renderer
        self.renderer = Renderer(
            player=self.player,
            width=width,
            height=height,
            overlay_path=overlay_path,
            scanline_alpha=config.scanline_alpha,
            epg_hours=config.guide_hours,
        )
        self.renderer.crt_on = bool(config.crt_enabled)
        self.renderer.vignette_on = bool(config.vignette_enabled)

        # Favorite channels (persisted set of channel numbers) → guide category
        self._favorites = set(int(n) for n in (config.favorites or []))
        self.renderer.set_guide_favorites(self._favorites)

        # Channel logos (fetched from XMLTV <icon> URLs, cached on disk)
        from .logos import LogoStore
        self.renderer.logos = LogoStore(
            os.path.join(runtime_dir, "logos"),
            on_loaded=self.renderer.mark_dirty,
            user_agent=config.user_agent)
        self.renderer.plexinfo.logos = self.renderer.logos   # posters

        # Current weather for the guide header (off unless a zip is configured)
        from .weather import Weather
        self.renderer.weather = Weather(
            config.weather_zip, config.weather_units, config.weather_country,
            on_update=self.renderer.mark_dirty, user_agent=config.user_agent)

        # Current channel
        self._ch_idx: int = 0

        # Channel-change sync (static cover held until stream's first frame)
        self._awaiting_playback: bool = False
        self._tune_timeout: Optional[threading.Timer] = None

        self._start_channel = start_channel
        self._quit = False

        # Sleep timer + idle screensaver.
        self._last_input = time.monotonic()
        self._sleep_deadline = None          # monotonic ts, or None when off
        self._screensaver_delay = 180        # seconds idle before the screensaver
        self._pending_apply = None           # apply-script path, run on quit

    # ── Public entry point ────────────────────────────────────────────────

    def run(self):
        if self.demo:
            from . import demo
            print("[cathode] DEMO MODE — built-in test-pattern channels.")
            self.channels = demo.build_channels(self.width, self.height)
            self.epg = demo.build_epg(self.channels)
            print(f"[cathode] {len(self.channels)} demo channels ready.")

        # Launch mpv FIRST so on-screen overlays (incl. the keyboard) can show.
        print("[cathode] Starting mpv…")
        try:
            self.player.start()
        except RuntimeError as e:
            print(f"[cathode] {e}")
            sys.exit(1)

        # Wire up key handlers (sent to mpv over IPC, so must be after start)
        self._register_keys()

        # Start renderer (channels may still be empty; the OSK can now show)
        self.renderer.channels = self.channels
        self.renderer.epg      = self.epg
        self.renderer.volume   = self.config.volume
        self.renderer.muted    = self.config.muted
        if self.channels:
            self._rebuild_categories()
        self.renderer.start()

        # Set volume
        self.player.volume = self.config.volume
        self.player.muted  = self.config.muted

        # Track the mouse so the on-screen menu button and dialogs are clickable.
        self.player.set_mouse_tracking(True)

        # Native gamepad input (XInput on Windows, /dev/input/js* on Linux) —
        # used on every build instead of mpv's SDL gamepad.
        self._gamepad_reader = None
        if self.config.gamepad:
            self._build_gamepad_buttons()
            from .gamepad import GamepadReader
            self._gamepad_reader = GamepadReader(self._gamepad_action)
            self._gamepad_reader.start()
            print("[cathode] Native gamepad reader active.")

        # Demo mode boots straight into the test channels.  Otherwise show the
        # home screen, unless the user disabled it AND has a playlist to boot
        # into (first run, with no playlist, always lands on the home screen
        # rather than jumping straight to a text-entry prompt).
        if self.demo:
            self._tune(self._initial_channel_idx(), initial=True)
        elif self.config.main_menu_on_launch or not self.config.playlist_url:
            self.renderer.main_menu.show(self._main_menu_select)
            self.renderer.update()
            self._sync_nav_repeat()
        else:
            self._start_from_playlist({
                "name": "Configured",
                "playlist_url": self.config.playlist_url,
                "epg_url": self.config.epg_url,
            })

        print("[cathode] Ready.")

        # Background ticker: sleep timer + idle screensaver.
        threading.Thread(target=self._housekeeping_loop, daemon=True).start()

        # One-shot update check on launch (notify only).
        if self.config.update_check:
            threading.Thread(target=self._update_check_launch, daemon=True).start()

        # Block until mpv exits
        try:
            self.player.wait_for_playback()
        except KeyboardInterrupt:
            pass

        self._shutdown()

    # ── Channel navigation ────────────────────────────────────────────────

    def _tune(self, idx: int, initial: bool = False):
        self._plex_end()                 # entering live TV ends any Plex stream
        idx = idx % len(self.channels)
        self._ch_idx = idx
        ch = self.channels[idx]

        self.renderer.current_channel_idx = idx
        self._cancel_tune_timeout()

        # Cover the screen with static and hold it until mpv reports the new
        # stream's first frame (see _on_playback_started).  Applies to the
        # initial channel too, so launch shows "tuning" instead of a black gap.
        self._awaiting_playback = True
        self.renderer.begin_channel_change(self.config.reveal_duration)
        self.renderer.update()

        print(f"[cathode] Tuning to [{ch.number}] {ch.name}")
        self.player.play(ch.url)

        # Safety net: if the stream never produces a frame, reveal anyway.
        self._tune_timeout = threading.Timer(
            self.config.tune_timeout, self._finish_tune,
        )
        self._tune_timeout.daemon = True
        self._tune_timeout.start()

    def _on_playback_started(self):
        """mpv displayed the first frame of the newly-loaded stream."""
        self._finish_tune()

    def _finish_tune(self):
        """Reveal the new channel (fade the static out)."""
        if not self._awaiting_playback:
            return
        self._awaiting_playback = False
        self._cancel_tune_timeout()
        self.renderer.reveal_channel(osd_timeout=self.config.osd_timeout)
        self.renderer.update()

    def _cancel_tune_timeout(self):
        if self._tune_timeout:
            self._tune_timeout.cancel()
            self._tune_timeout = None

    def _channel_up(self):
        self._tune((self._ch_idx + 1) % len(self.channels))

    def _channel_down(self):
        self._tune((self._ch_idx - 1) % len(self.channels))

    def _initial_channel_idx(self) -> int:
        """Where to start playback: explicit --channel, else last-watched, else 0."""
        if self._start_channel is not None:
            return self._channel_number_to_idx(self._start_channel)
        if self.config.last_channel:
            return self._channel_number_to_idx(self.config.last_channel)
        return 0

    def _channel_number_to_idx(self, number: int) -> int:
        for i, ch in enumerate(self.channels):
            if ch.number == number:
                return i
        return 0

    # ── Digit buffer (direct channel entry) ───────────────────────────────

    def _digit_press(self, d: str):
        self._digit_buf += d
        if self._digit_timer:
            self._digit_timer.cancel()
        self._digit_timer = threading.Timer(self.DIGIT_TIMEOUT, self._commit_digits)
        self._digit_timer.start()
        # Show the accumulating number on screen as it's typed.
        self.renderer.show_digit_entry(self._digit_buf, self.DIGIT_TIMEOUT + 0.5)
        self.renderer.update()

    def _commit_digits(self):
        if not self._digit_buf:
            return
        number = int(self._digit_buf)
        self._digit_buf = ""
        self.renderer.clear_digit_entry()
        idx = self._channel_number_to_idx(number)
        self._tune(idx)

    # ── Volume ────────────────────────────────────────────────────────────

    def _unmute_if_muted(self):
        """Any volume change implies the user wants to hear something."""
        if self.player.muted:
            self.player.muted = False
            self.config.muted = False
            self.renderer.muted = False

    def _vol_up(self):
        self._unmute_if_muted()
        vol = self.player.volume_up(5)
        self.config.volume = vol
        self.renderer.volume = vol
        self.renderer.show_volume_osd()
        self.renderer.update()

    def _vol_down(self):
        self._unmute_if_muted()
        vol = self.player.volume_down(5)
        self.config.volume = vol
        self.renderer.volume = vol
        self.renderer.show_volume_osd()
        self.renderer.update()

    def _toggle_mute(self):
        muted = self.player.toggle_mute()
        self.config.muted = muted
        self.renderer.muted = muted
        self.renderer.plexosd.muted = muted
        self.renderer.show_volume_osd()
        self.renderer.update()

    # ── Guide ────────────────────────────────────────────────────────────

    def _toggle_guide(self):
        if self.renderer.plex_playing:
            return   # the program guide is disabled during Plex playback
        if self.renderer.state == UIState.GUIDE_OPEN:
            self.renderer.close_guide()
        else:
            self.renderer.open_guide()   # restores the session category first
            self.renderer.guide.jump_to_channel(self.channels, self._ch_idx)
        self.renderer.update()

    # ── Categories & favorites ─────────────────────────────────────────────

    def _channel_category(self, ch) -> str:
        """A channel's category: its dominant EPG genre, else its M3U group."""
        if self.epg:
            cid = self.epg.resolve_channel_id(ch.epg_id, ch.name)
            if cid:
                cat = self.epg.dominant_category(cid)
                if cat:
                    return cat
        return ch.group or ""

    def _rebuild_categories(self):
        """Tag each channel with its category and refresh the guide's selector
        list (All + Favorites + the genres present)."""
        genres = set()
        for ch in self.channels:
            cat = self._channel_category(ch)
            ch.category = cat
            if cat:
                genres.add(cat)
        ordered = ["All", "Favorites"] + sorted(genres)
        self.renderer.set_guide_categories(ordered)

    def _favorite_target(self):
        """The channel a favorite toggle applies to: the guide's highlighted
        channel if the guide is open, else the channel being watched."""
        if self.renderer.state == UIState.GUIDE_OPEN:
            ch = self.renderer.guide.selected_channel()
            if ch is not None:
                return ch
        if self.channels and 0 <= self._ch_idx < len(self.channels):
            return self.channels[self._ch_idx]
        return None

    def _toggle_favorite(self):
        ch = self._favorite_target()
        if ch is None:
            return
        if ch.number in self._favorites:
            self._favorites.discard(ch.number)
            verb = "removed from"
        else:
            self._favorites.add(ch.number)
            verb = "added to"
        self.config.favorites = sorted(self._favorites)
        self.config.save()
        self.renderer.set_guide_favorites(self._favorites)
        print(f"[cathode] [{ch.number}] {ch.name} {verb} favorites")
        # Transient on-screen confirmation (also re-renders the guide).
        self.renderer.show_notification(f"[{ch.number}] {ch.name} {verb} Favorites")

    def _guide_up(self):
        if self.renderer.osk.open:
            self.renderer.osk.move_up(); self.renderer.mark_dirty(); return
        if self.renderer.editor.open:
            self.renderer.editor.move_up(); self.renderer.mark_dirty(); return
        if self.renderer.menu.open:
            self.renderer.menu.move_up(); self.renderer.mark_dirty(); return
        if self.renderer.main_menu.open:
            self.renderer.main_menu.move_up(); self.renderer.mark_dirty(); return
        if self.renderer.ppv.open:
            self.renderer.ppv.move_up(); self.renderer.mark_dirty(); return
        if self.renderer.plexinfo.open:
            self.renderer.plexinfo.move(-1); self.renderer.mark_dirty(); return
        if self.renderer.plex_playing:
            self._plex_focus(-1); return
        if self.renderer.state == UIState.GUIDE_OPEN:
            self.renderer.guide.move_up()
            self.renderer.update()
        else:
            self._channel_up()

    def _guide_down(self):
        if self.renderer.osk.open:
            self.renderer.osk.move_down(); self.renderer.mark_dirty(); return
        if self.renderer.editor.open:
            self.renderer.editor.move_down(); self.renderer.mark_dirty(); return
        if self.renderer.menu.open:
            self.renderer.menu.move_down(); self.renderer.mark_dirty(); return
        if self.renderer.main_menu.open:
            self.renderer.main_menu.move_down(); self.renderer.mark_dirty(); return
        if self.renderer.ppv.open:
            self.renderer.ppv.move_down(); self.renderer.mark_dirty(); return
        if self.renderer.plexinfo.open:
            self.renderer.plexinfo.move(1); self.renderer.mark_dirty(); return
        if self.renderer.plex_playing:
            self._plex_focus(1); return
        if self.renderer.state == UIState.GUIDE_OPEN:
            self.renderer.guide.move_down()
            self.renderer.update()
        else:
            self._channel_down()

    def _guide_left(self):
        if self.renderer.osk.open:
            self.renderer.osk.move_left(); self.renderer.mark_dirty(); return
        if self.renderer.editor.open:
            self.renderer.editor.left(); self.renderer.mark_dirty(); return
        if self.renderer.menu.open:
            return  # arrows don't navigate the context menu (Up/Down + Enter/Back)
        if self.renderer.main_menu.open:
            return  # home screen has no horizontal navigation
        if self.renderer.ppv.open:
            self.renderer.ppv.scroll(-10); self.renderer.mark_dirty(); return
        if self.renderer.plexinfo.open:
            self.renderer.plexinfo.move(-1); self.renderer.mark_dirty(); return
        if self.renderer.plex_playing:
            self._plex_dpad(-1); return
        if self.renderer.state == UIState.GUIDE_OPEN:
            self.renderer.guide.move_left()
            self.renderer.update()
        else:
            self._vol_down()

    def _guide_right(self):
        if self.renderer.osk.open:
            self.renderer.osk.move_right(); self.renderer.mark_dirty(); return
        if self.renderer.editor.open:
            self.renderer.editor.right(); self.renderer.mark_dirty(); return
        if self.renderer.menu.open:
            return  # arrows don't navigate the context menu (Up/Down + Enter/Back)
        if self.renderer.main_menu.open:
            return  # home screen has no horizontal navigation
        if self.renderer.ppv.open:
            self.renderer.ppv.scroll(10); self.renderer.mark_dirty(); return
        if self.renderer.plexinfo.open:
            self.renderer.plexinfo.move(1); self.renderer.mark_dirty(); return
        if self.renderer.plex_playing:
            self._plex_dpad(1); return
        if self.renderer.state == UIState.GUIDE_OPEN:
            self.renderer.guide.move_right()
            self.renderer.update()
        else:
            self._vol_up()

    def _grid_select(self):
        """Both Enter keys (and gamepad A): press/select the highlighted item.
        In the on-screen keyboard this types the highlighted key (use the grid's
        DONE key to submit)."""
        if self.renderer.osk.open:
            self.renderer.osk.press(); self.renderer.mark_dirty(); return
        self._activate_highlighted()

    def _activate_highlighted(self):
        if self.renderer.editor.open:
            self.renderer.editor.press(); self.renderer.mark_dirty(); return
        if self.renderer.menu.open:
            self.renderer.menu.activate(); self._after_menu_action(); return
        if self.renderer.main_menu.open:
            self.renderer.main_menu.press(); return
        if self.renderer.ppv.open:
            self._ppv_select(); return
        if self.renderer.plexinfo.open:
            self._plex_info_activate(); return
        if self.renderer.plex_playing:
            self._plex_activate(); return
        if self.renderer.state == UIState.GUIDE_OPEN:
            if self.renderer.guide.focus == "category":
                return   # category selector: use Left/Right to change it
            ch = self.renderer.guide.selected_channel()
            if ch is None:
                return
            self.renderer.close_guide()
            self._tune(self.channels.index(ch))
        elif self.renderer.osd_visible:
            # Info bar is up → Enter opens the context menu.
            self._toggle_context_menu()
        else:
            self.renderer.show_osd(timeout=self.config.osd_timeout_info)
            self.renderer.update()

    # ── Key registration ──────────────────────────────────────────────────

    def _register_keys(self):
        """
        Bind keyboard keys in mpv to Python callbacks over IPC.

        Gamepad input is handled separately by the native reader (see
        cathode/gamepad.py and _build_gamepad_buttons), not through mpv.  On the
        Steam Deck in Game Mode a Steam Input profile mapping the controller to
        these keyboard keys also works.
        """
        import string
        p = self.player

        # Letter hotkeys → action (built from the remappable bindings; the char
        # router uses this map).
        self._build_hotkeys()

        # Navigation / dialog keys — always active.  Both Enter keys behave the
        # same: press/select the highlighted item (no separate "confirm").
        nav = {
            "UP": self._guide_up, "DOWN": self._guide_down,
            "LEFT": self._guide_left, "RIGHT": self._guide_right,
            "ENTER": self._grid_select, "KP_ENTER": self._grid_select,
            "ESC": self._handle_escape,
            "SPACE": self._space_key,
            "MBTN_RIGHT": self._right_click, "MBTN_LEFT": self._menu_click,
            "WHEEL_UP": self._wheel_up, "WHEEL_DOWN": self._wheel_down,
            "ctrl+v": self._osk_paste, "ctrl+c": self._osk_copy,
        }
        for key, handler in nav.items():
            p.bind_key(key, handler)
        # Backspace = universal one-level back (same as the controller's B):
        # deletes a char in the keyboard, else backs out menu / screen.
        # Repeatable so holding it chews through a long string in text entry.
        p.bind_key("BS", self._gamepad_back, repeatable=True)

        # Arrow keys are made repeatable on the fly (only while a menu / OSK /
        # editor / guide is open) so a held key cycles items or moves sliders,
        # while staying single-shot for channel / volume changes when watching.
        self._nav_handlers = {"UP": self._guide_up, "DOWN": self._guide_down,
                              "LEFT": self._guide_left, "RIGHT": self._guide_right}
        self._nav_repeat_on = False
        p.on_after_key = self._after_key

        # Non-character hotkeys — ignored while a dialog is open.
        hotkeys = {
            "TAB": self._show_info,
            "PGUP":  lambda: self._tune(max(0, self._ch_idx - 10)),
            "PGDWN": lambda: self._tune(min(len(self.channels) - 1, self._ch_idx + 10)),
        }
        for key, handler in hotkeys.items():
            p.bind_key(key, self._guard_hotkey(handler), name=f"hk_{key}")

        # NB: the gamepad is handled by the native reader (cathode/gamepad.py),
        # not mpv's SDL input — see _build_gamepad_buttons / _gamepad_action.

        # Every printable character routes through _char_typed: it types into
        # the on-screen keyboard when open, else runs the key's hotkey/digit
        # action (and is ignored while the menu is open).
        url_syms = "./:-_?=&%@~#+,;!$'()[]*"
        for ch in string.ascii_letters + string.digits + url_syms:
            p.bind_key(ch, (lambda c: lambda: self._char_typed(c))(ch),
                       name=f"ch_{ord(ch)}")

        # Numeric keypad digits → same as the top-row digits (direct channel
        # entry while watching, typing into the text-entry dialogs otherwise).
        for d in range(10):
            p.bind_key(f"KP{d}", (lambda n: lambda: self._char_typed(str(n)))(d),
                       name=f"kp_{d}")
        # Keypad "." (mpv calls it KP_DEC) types a period in text entry.
        p.bind_key("KP_DEC", lambda: self._char_typed("."), name="kp_dec")

    def _dialog_open(self) -> bool:
        return (self.renderer.osk.open or self.renderer.menu.open
                or self.renderer.editor.open or self.renderer.main_menu.open
                or self.renderer.ppv.open or self.renderer.plexinfo.open)

    def _nav_context_active(self) -> bool:
        r = self.renderer
        return (r.osk.open or r.menu.open or r.editor.open or r.main_menu.open
                or r.ppv.open or r.plexinfo.open or r.plex_playing
                or r.state == UIState.GUIDE_OPEN)

    def _set_input_mode(self, mode):
        """Track the active input device so the on-screen hints match it."""
        if mode == self._input_mode:
            return
        self._input_mode = mode
        self.renderer.ppv.input_mode = mode
        self.renderer.mark_dirty()

    def _after_key(self):
        """Runs after every keyboard/mouse key handler (player.on_after_key)."""
        self._mark_activity()
        self._set_input_mode("key")
        self._sync_nav_repeat()

    def _mark_activity(self) -> bool:
        """Record input + dismiss the screensaver. Returns True if this input
        only woke the screensaver (caller may swallow it)."""
        self._last_input = time.monotonic()
        if self.renderer.screensaver.active:
            self.renderer.screensaver.active = False
            self.renderer.update()
            return True
        return False

    # ── Sleep timer + screensaver ─────────────────────────────────────────

    def _actively_playing(self) -> bool:
        """True when video is actually on screen (don't screensaver over it)."""
        r = self.renderer
        if r.state == UIState.CHANNEL_CHANGING:
            return True
        if r.plex_playing:
            return not self._plex_paused      # paused Plex is fair game
        return r.state == UIState.WATCHING    # live TV

    def _housekeeping_loop(self):
        while not self._quit:
            now = time.monotonic()
            if self._sleep_deadline and now >= self._sleep_deadline:
                self._sleep_deadline = None
                self._sleep_fire()
            ss = self.renderer.screensaver
            if ss.active:
                ss.step()
                self.renderer.update()
                time.sleep(0.05)              # ~20fps while bouncing
                continue
            if (not self._actively_playing()
                    and now - self._last_input >= self._screensaver_delay):
                ss.reset()
                ss.active = True
                self.renderer.update()
            time.sleep(0.5)

    def _sleep_fire(self):
        """Sleep timer elapsed — pause whatever's playing."""
        if self.renderer.plex_playing:
            if not self._plex_paused:
                self._plex_toggle_pause()
        else:
            self.player.set_pause(True)
        self.renderer.show_notification("Sleep timer — paused", 4.0)

    SLEEP_OPTIONS = [("Off", 0), ("15 minutes", 15), ("30 minutes", 30),
                     ("60 minutes", 60)]

    def _sleep_submenu(self):
        # Only "Off" carries a checkmark (when no timer is running); we don't
        # track which preset is active once set.
        active = self._sleep_deadline is not None
        return [MenuItem(label, checked=(mins == 0 and not active),
                         action=lambda m=mins: self._set_sleep_timer(m),
                         close_after=False)
                for label, mins in self.SLEEP_OPTIONS]

    def _set_sleep_timer(self, minutes):
        if minutes:
            self._sleep_deadline = time.monotonic() + minutes * 60
            self.renderer.show_notification(f"Sleep timer set: {minutes} min", 3.0)
        else:
            self._sleep_deadline = None
            self.renderer.show_notification("Sleep timer off", 3.0)
        self.renderer.menu.replace_page(self._sleep_submenu())
        self.renderer.mark_dirty()

    # ── Update check (GitHub Releases — notify + download, no self-overwrite) ─

    def _update_check_launch(self):
        """Quiet check on launch: only speak up if a newer version exists."""
        from . import updater, __version__
        try:
            latest = updater.check_latest()
        except updater.UpdateError:
            return
        if latest and updater.is_newer(latest["tag"], __version__):
            self.renderer.show_notification(
                f"Update {latest['tag']} available — Check for Updates in the menu", 6.0)

    def _check_updates(self):
        """Menu action: check, and if newer download the matching asset."""
        from . import updater, __version__
        self.renderer.show_notification("Checking for updates...", 3.0)

        def work():
            try:
                latest = updater.check_latest()
            except updater.UpdateError as e:
                self.renderer.show_notification(f"Update check failed: {e}", 5.0)
                return
            if not latest or not updater.is_newer(latest["tag"], __version__):
                self.renderer.show_notification(
                    f"Up to date (v{__version__})", 4.0)
                return
            asset = updater.pick_asset(latest["assets"])
            if not asset:
                self.renderer.show_notification(
                    f"{latest['tag']} available, but no build for this platform", 6.0)
                return
            self.renderer.show_notification(
                f"Downloading {latest['tag']}...", 5.0)
            updates_dir = os.path.join(self._runtime_dir, "updates")
            try:
                dest = updater.download(asset["url"], updates_dir, asset["name"])
            except updater.UpdateError as e:
                self.renderer.show_notification(f"Download failed: {e}", 5.0)
                return
            # Stage an install script that runs after Cathode exits, so the next
            # launch is the new version (never overwrites the running build).
            try:
                self._pending_apply = updater.write_apply_script(
                    dest, updater.install_dir(), updates_dir)
                self.renderer.show_notification(
                    f"Update {latest['tag']} ready — installs when you quit Cathode", 8.0)
            except Exception:
                self.renderer.show_notification(
                    f"Update downloaded — {dest}", 8.0)
        threading.Thread(target=work, daemon=True).start()

    def _sync_nav_repeat(self):
        """Toggle arrow-key repeat to match the current UI mode. Called after
        every key handler (via player.on_after_key) and at the few transitions
        that don't run through one (startup home screen, the blocking OSK)."""
        want = self._nav_context_active()
        if want == self._nav_repeat_on:
            return
        self._nav_repeat_on = want
        for key, handler in self._nav_handlers.items():
            self.player.bind_key(key, handler, repeatable=want)

    def _guard_hotkey(self, fn):
        """Wrap a hotkey so it does nothing while a dialog is selected."""
        def wrapped():
            if self._dialog_open():
                return
            fn()
        return wrapped

    def _char_typed(self, ch: str):
        """A printable key: type into the on-screen keyboard, else act normally."""
        if self.renderer.osk.open:
            self.renderer.osk.insert(ch)
            self.renderer.mark_dirty()
            return
        if (self.renderer.menu.open or self.renderer.editor.open
                or self.renderer.main_menu.open):
            return
        act = self._hotkey_actions.get(ch)
        if act:
            act()
        elif ch.isdigit():
            self._digit_press(ch)

    def _osk_paste(self):
        if not self.renderer.osk.open:
            return
        # Prefer mpv's native clipboard (works on Wayland/Windows/macOS with no
        # external tools); fall back to OS clipboard utilities (X11: xclip/xsel).
        text = self.player.get_clipboard()
        if not text:
            from . import clipboard
            text = clipboard.get_text()
        self.renderer.osk.insert((text or "").strip())
        self.renderer.mark_dirty()

    def _osk_copy(self):
        if not self.renderer.osk.open:
            return
        text = self.renderer.osk.text
        self.player.set_clipboard(text)
        from . import clipboard
        clipboard.set_text(text)   # best-effort OS clipboard too

    # ── Misc handlers ─────────────────────────────────────────────────────

    def _show_info(self):
        if self.renderer.osd_visible:
            self.renderer.hide_osd()
        else:
            self.renderer.show_osd(timeout=self.config.osd_timeout_info)
        self.renderer.update()

    def _handle_escape(self):
        """Esc never quits. It backs out: a dialog/screen first, then a menu one
        level at a time (like Backspace and the controller's Back), then the
        guide → OSD. It does not toggle fullscreen."""
        r = self.renderer
        if r.osk.open:
            r.osk.cancel()      # _osk_get's cancel cb resumes the blocked action
            r.menu.close()      # ensure the menu behind it is gone too
            r.update()
        elif r.editor.open:
            r.editor.close()    # close + revert unsaved changes
            self._editor_close()
        elif r.menu.open:
            r.menu.back()       # back out one submenu level (closes at the root)
            r.update()
        elif r.ppv.open:
            self._ppv_back()        # one level (exits PPV only at the root)
        elif r.plexinfo.open:
            self._plex_info_back()
        elif r.plex_playing:
            if r.plexosd.scrubbing or r.plexosd.adjusting:
                r.plexosd.scrubbing = False
                r.plexosd.adjusting = False
                self._plex_show_osd()
            elif r.plexosd.visible:
                r.plexosd.hide(); r.mark_dirty()   # back closes the OSD bar
            else:
                self._confirm_leave_plex()
        elif r.state == UIState.GUIDE_OPEN:
            r.close_guide()
            r.update()
        elif r.osd_visible:
            r.hide_osd()
            r.update()
        elif (self.channels and not r.main_menu.open
              and r.state == UIState.WATCHING):
            self._confirm_leave_live()
        # else: nothing — Esc is not a quit shortcut and no longer toggles
        # fullscreen.

    # ── Fullscreen / context menu / mouse ─────────────────────────────────

    def _set_fullscreen(self, on: bool):
        self._fullscreen = bool(on)
        self.player.set_fullscreen(self._fullscreen)

    def _toggle_fullscreen(self):
        self._set_fullscreen(not self._fullscreen)

    def _right_click(self):
        """Right mouse button: 'back' while in a menu/list/dialog (so the UI is
        fully mouse-driveable); the context-menu toggle only while a video is
        playing (or on the bare home/live screen)."""
        r = self.renderer
        in_nav = (r.menu.open or r.osk.open or r.editor.open or r.ppv.open
                  or r.plexinfo.open or r.main_menu.open
                  or r.state == UIState.GUIDE_OPEN)
        if in_nav:
            self._handle_escape()
        else:
            self._toggle_context_menu()

    def _toggle_context_menu(self):
        if self.renderer.osk.open:
            return   # don't open the menu over the on-screen keyboard
        m = self.renderer.menu
        if m.open:
            m.close()
        elif (self.renderer.ppv.open or self.renderer.plexinfo.open
              or self.renderer.plex_playing):
            m.open_with(self._build_plex_menu(), title="PLEX-PER-VIEW")
        else:
            m.open_with(self._build_menu(), title="CATHODE")
        self.renderer.mark_dirty()

    def _menu_click(self):
        """Left mouse button: press the hovered key / activate the hovered item,
        or click the on-screen menu button."""
        if self.renderer.osk.open:
            self.renderer.osk.press()
            self.renderer.mark_dirty()
            return
        if self.renderer.editor.open:
            x, y = self._last_mouse
            self.renderer.editor.click(x, y)
            self.renderer.mark_dirty()
            return
        if self.renderer.menu.open:
            x, y = self._last_mouse
            if self.renderer.menu.hit_test(x, y) is None:
                # Clicked outside the menu panel → dismiss, back to the video.
                self.renderer.menu.close()
                self.renderer.mark_dirty()
            else:
                # Activate exactly the item under the cursor (not a stale one).
                self.renderer.menu.set_hover(x, y)
                self.renderer.menu.activate()
                self._after_menu_action()
            return
        if self.renderer.main_menu.open:
            x, y = self._last_mouse
            self.renderer.main_menu.click(x, y)
            self.renderer.mark_dirty()
            return
        if self.renderer.ppv.open:
            x, y = self._last_mouse
            if self.renderer.ppv.hit_back(x, y):
                self._ppv_back()
                return
            if self.renderer.ppv.hit_menu(x, y):
                self._toggle_context_menu()
                return
            i = self.renderer.ppv.hit_test(x, y)
            if i is not None:
                self.renderer.ppv.sel = i
                self._ppv_select()
            return
        if self.renderer.plexinfo.open:
            x, y = self._last_mouse
            i = self.renderer.plexinfo.hit_test(x, y)
            if i is not None:
                self.renderer.plexinfo.focus = i
                self._plex_info_activate()
            return
        if self.renderer.plex_playing:
            x, y = self._last_mouse
            name = self.renderer.plexosd.hit_test(x, y)
            if self.renderer.plexosd.visible and name:
                self._plex_click(name, x)
            else:
                self._plex_show_osd()
            return
        # No dialog open: the corner button opens the menu; clicking elsewhere
        # reveals the info bar (and the button) for touch/mouse users.
        x, y = self._last_mouse
        if self.renderer.osd_visible and self.renderer.menu_button_hit(x, y):
            self._toggle_context_menu()
        else:
            self.renderer.show_osd(timeout=self.config.osd_timeout_info)
            self.renderer.update()

    def _gamepad_back(self):
        """B button: context-aware step back — delete a char / leave a sub-menu /
        close the editor / close the guide / hide the info bar."""
        r = self.renderer
        if r.osk.open:
            r.osk.backspace(); r.mark_dirty()
        elif r.editor.open:
            r.editor.close(); self._editor_close()
        elif r.menu.open:
            r.menu.back(); r.mark_dirty()
        elif r.ppv.open:
            self._ppv_back()
        elif r.plexinfo.open:
            self._plex_info_back()
        elif r.plex_playing:
            if r.plexosd.scrubbing or r.plexosd.adjusting:
                r.plexosd.scrubbing = False
                r.plexosd.adjusting = False
                self._plex_show_osd()
            elif r.plexosd.visible:
                r.plexosd.hide(); r.mark_dirty()
            else:
                self._confirm_leave_plex()
        elif r.state == UIState.GUIDE_OPEN:
            r.close_guide(); r.update()
        elif r.osd_visible:
            r.hide_osd(); r.update()
        elif (self.channels and not r.main_menu.open
              and r.state == UIState.WATCHING):
            self._confirm_leave_live()

    def _confirm_leave_plex(self):
        items = [
            MenuItem("Keep Watching", action=lambda: None),
            MenuItem("Return to Browse", action=self._plex_stop),
        ]
        self.renderer.menu.open_with(items, title="LEAVE VIDEO?")
        self.renderer.mark_dirty()

    def _confirm_leave_live(self):
        items = [
            MenuItem("Keep Watching", action=lambda: None),
            MenuItem("Return to Main Menu", action=self._open_main_menu),
        ]
        self.renderer.menu.open_with(items, title="LEAVE LIVE TV?")
        self.renderer.mark_dirty()

    # ── Native gamepad reader fallback (when mpv lacks SDL) ────────────────

    def _gamepad_action(self, name: str, is_repeat: bool = False):
        """Called from the gamepad reader thread.  Dispatch on its own thread so
        a blocking handler (e.g. the on-screen keyboard) can't freeze input."""
        self._set_input_mode("gamepad")
        if self._mark_activity():
            return            # this press only woke the screensaver
        threading.Thread(target=self._gamepad_dispatch,
                         args=(name, is_repeat), daemon=True).start()

    def _gamepad_dispatch(self, name, is_repeat):
        nav = {"up": self._guide_up, "down": self._guide_down,
               "left": self._guide_left, "right": self._guide_right}
        if name in nav:
            # Don't repeat channel / volume while watching (only nav contexts).
            if is_repeat and not self._nav_context_active():
                return
            nav[name]()
            return
        if is_repeat:
            return
        fn = self._gamepad_buttons.get(name)
        if fn:
            fn()

    def _wheel(self, delta):
        r = self.renderer
        if r.menu.open:
            r.menu.move(delta); r.mark_dirty()
        elif r.ppv.open:
            r.ppv.scroll(delta); r.mark_dirty()
        elif r.state == UIState.GUIDE_OPEN:
            for _ in range(abs(delta)):
                (r.guide.move_down if delta > 0 else r.guide.move_up)()
            r.update()
        elif r.plex_playing or r.plexinfo.open:
            pass  # ignore wheel during plex playback / info screen
        else:
            (self._channel_up if delta < 0 else self._channel_down)()

    def _wheel_up(self):
        self._wheel(-1)

    def _wheel_down(self):
        self._wheel(1)

    def _lb_action(self):
        if self.renderer.ppv.open:
            self.renderer.ppv.scroll(-10); self.renderer.mark_dirty()
        elif not self._dialog_open():
            self._channel_down()

    def _rb_action(self):
        if self.renderer.ppv.open:
            self.renderer.ppv.scroll(10); self.renderer.mark_dirty()
        elif not self._dialog_open():
            self._channel_up()

    # ── Remappable hotkeys (keyboard letters + gamepad buttons) ───────────

    # (action_id, label, default key, default gamepad button)
    INPUT_ACTIONS = [
        ("guide",        "Program Guide", "g", "x"),
        ("info",         "Info Bar",      "i", "y"),
        ("mute",         "Mute",          "m", "l3"),
        ("favorite",     "Favorite",      "f", ""),
        ("menu",         "Context Menu",  "c", "back"),
        ("fullscreen",   "Fullscreen",    "w", ""),
        ("quit",         "Quit",          "q", ""),
        ("channel_up",   "Channel Up / Scroll",   "", "rb"),
        ("channel_down", "Channel Down / Scroll", "", "lb"),
        ("vol_up",       "Volume Up",     "", "rt"),
        ("vol_down",     "Volume Down",   "", "lt"),
    ]
    KEY_CHOICES = list("abcdefghijklmnopqrstuvwxyz")
    PAD_CHOICES = ["x", "y", "start", "back", "guide", "lb", "rb", "lt", "rt", "l3", "r3"]

    def _action_callables(self):
        return {
            "guide": self._toggle_guide, "info": self._show_info,
            "mute": self._toggle_mute, "favorite": self._toggle_favorite,
            "menu": self._toggle_context_menu, "fullscreen": self._toggle_fullscreen,
            "quit": self._quit_app,
            "channel_up": self._rb_action, "channel_down": self._lb_action,
            "vol_up": self._vol_up, "vol_down": self._vol_down,
        }

    def _resolved_keys(self) -> dict:
        out = {a: dk for a, _, dk, _ in self.INPUT_ACTIONS}
        out.update({a: k for a, k in (self.config.key_bindings or {}).items()})
        return out

    def _resolved_pad(self) -> dict:
        out = {a: db for a, _, _, db in self.INPUT_ACTIONS}
        out.update({a: b for a, b in (self.config.gamepad_bindings or {}).items()})
        return out

    def _build_hotkeys(self):
        calls = self._action_callables()
        self._hotkey_actions = {}
        for action, key in self._resolved_keys().items():
            if key and action in calls:
                self._hotkey_actions[key] = calls[action]
                self._hotkey_actions[key.upper()] = calls[action]

    def _build_gamepad_buttons(self):
        g = self._guard_hotkey
        calls = self._action_callables()
        # channel up/down handle the PPV-scroll guard themselves; guard the rest.
        unguarded = {"channel_up", "channel_down"}
        self._gamepad_buttons = {"a": self._grid_select, "b": self._gamepad_back}
        for action, button in self._resolved_pad().items():
            if button and action in calls:
                fn = calls[action]
                self._gamepad_buttons[button] = fn if action in unguarded else g(fn)

    def _after_menu_action(self):
        self.renderer.mark_dirty()

    def _on_mouse_pos(self, x: int, y: int):
        # Runs on the IPC reader thread for EVERY mouse move — must stay cheap.
        # Only update hover state and request a coalesced repaint; never render
        # here (that would flood the reader and freeze input).
        self._last_mouse = (x, y)
        self._last_input = time.monotonic()
        if self.renderer.screensaver.active:
            self.renderer.screensaver.active = False
            self.renderer.mark_dirty()   # cheap; never render on the reader thread
            return
        self._set_input_mode("key")
        if self.renderer.osk.open:
            self.renderer.osk.set_hover(x, y)
            self.renderer.mark_dirty()
        elif self.renderer.editor.open:
            self.renderer.editor.set_hover(x, y)
            self.renderer.mark_dirty()
        elif self.renderer.menu.open:
            self.renderer.menu.set_hover(x, y)
            self.renderer.mark_dirty()
        elif self.renderer.main_menu.open:
            self.renderer.main_menu.set_hover(x, y)
            self.renderer.mark_dirty()
        elif self.renderer.ppv.open:
            pass  # mouse movement does NOT change the PPV highlight; use the
                  # wheel to scroll, click to activate

        elif self.renderer.plexinfo.open:
            self.renderer.plexinfo.set_hover(x, y)
            self.renderer.mark_dirty()
        elif self.renderer.plex_playing:
            self.renderer.plexosd.set_hover(x, y)
            self._plex_show_osd()
        else:
            over = self.renderer.osd_visible and self.renderer.menu_button_hit(x, y)
            if over != self.renderer._menu_btn_hover:
                self.renderer._menu_btn_hover = over
                self.renderer.mark_dirty()

    # ── On-screen keyboard (text entry) ───────────────────────────────────

    def _osk_get(self, prompt: str, initial: str = ""):
        """Show the on-screen keyboard and BLOCK until the user finishes.
        Returns the entered string, or None if cancelled. Safe to call from the
        main thread or a handler thread (input is driven by the reader thread)."""
        ev = threading.Event()
        result = {"value": None}

        def done(text):
            result["value"] = text
            ev.set()

        def cancel():
            result["value"] = None
            ev.set()

        self.renderer.osk.show(prompt, initial, on_done=done, on_cancel=cancel)
        self.renderer.update()
        self._sync_nav_repeat()      # OSK is up → enable held-key repeat
        ev.wait()
        self._sync_nav_repeat()      # OSK closed → restore prior repeat state
        self.renderer.update()
        return result["value"]

    # ── Context menu tree ─────────────────────────────────────────────────

    def _build_menu(self):
        fav = self._favorite_target()
        is_fav = fav is not None and fav.number in self._favorites
        return [
            MenuItem("Program Guide", action=self._toggle_guide, hint="G"),
            MenuItem("Remove Favorite" if is_fav else "Add Favorite",
                     action=self._toggle_favorite, hint="F", checked=is_fav),
            MenuItem("Channel Up", action=self._channel_up, hint="[^]"),
            MenuItem("Channel Down", action=self._channel_down, hint="[v]"),
            MenuItem("Volume Up", action=self._vol_up, hint="[>]", close_after=False),
            MenuItem("Volume Down", action=self._vol_down, hint="[<]", close_after=False),
            MenuItem("Mute", action=self._toggle_mute, hint="M",
                     checked=self.player.muted),
            MenuItem("Plex-Per-View", action=self._open_ppv),
            MenuItem("Playlists", submenu=self._playlists_submenu),
            MenuItem("Options", submenu=self._options_submenu),
            MenuItem("Main Menu", action=self._open_main_menu),
            MenuItem("Quit", action=self._quit_app, hint="Q"),
        ]

    def _build_plex_menu(self):
        """The context menu shown in Plex-Per-View mode (browse or playback)."""
        items = [
            MenuItem("Mute", action=self._toggle_mute, hint="M",
                     checked=self.player.muted),
        ]
        if self.renderer.plex_playing:
            items.append(MenuItem("Audio & Subtitles", submenu=self._plex_av_submenu))
        items += [
            MenuItem("Live TV", submenu=self._playlists_submenu),
            MenuItem("Options", submenu=self._options_submenu),
            MenuItem("Main Menu", action=self._open_main_menu),
            MenuItem("Quit", action=self._quit_app, hint="Q"),
        ]
        return items

    def _options_submenu(self):
        return [
            MenuItem("Themes", submenu=self._themes_submenu),
            MenuItem("Weather", submenu=self._weather_submenu),
            MenuItem("Plex", submenu=self._plex_options_submenu),
            MenuItem("Keyboard Shortcuts", submenu=self._keyboard_keys_submenu),
            MenuItem("Gamepad Buttons", submenu=self._gamepad_keys_submenu),
            MenuItem("Display", submenu=self._display_submenu),
            MenuItem("Sleep Timer", submenu=self._sleep_submenu),
            MenuItem("Check for Updates", action=self._check_updates),
        ]

    # ── Input remapping menus ─────────────────────────────────────────────

    def _keyboard_keys_submenu(self):
        keys = self._resolved_keys()
        return [MenuItem(f"{label}: {(keys.get(aid) or '').upper() or '(none)'}",
                         submenu=(lambda a=aid: self._key_choice_submenu(a)))
                for aid, label, _, _ in self.INPUT_ACTIONS]

    def _key_choice_submenu(self, action):
        cur = self._resolved_keys().get(action, "")
        items = [MenuItem("(none)", checked=(not cur), close_after=False,
                          action=lambda: self._set_key(action, ""))]
        items += [MenuItem(k.upper(), checked=(k == cur), close_after=False,
                           action=lambda key=k: self._set_key(action, key))
                  for k in self.KEY_CHOICES]
        return items

    def _set_key(self, action, key):
        binds = self._resolved_keys()
        if key:                       # free this key from any other action
            for a in list(binds):
                if binds[a] == key and a != action:
                    binds[a] = ""
        binds[action] = key
        self.config.key_bindings = binds
        self.config.save()
        self._build_hotkeys()
        self.renderer.menu.replace_page(self._key_choice_submenu(action))
        self.renderer.mark_dirty()

    def _gamepad_keys_submenu(self):
        pad = self._resolved_pad()
        return [MenuItem(f"{label}: {(pad.get(aid) or '').upper() or '(none)'}",
                         submenu=(lambda a=aid: self._pad_choice_submenu(a)))
                for aid, label, _, _ in self.INPUT_ACTIONS]

    def _pad_choice_submenu(self, action):
        cur = self._resolved_pad().get(action, "")
        items = [MenuItem("(none)", checked=(not cur), close_after=False,
                          action=lambda: self._set_pad(action, ""))]
        items += [MenuItem(b.upper(), checked=(b == cur), close_after=False,
                           action=lambda btn=b: self._set_pad(action, btn))
                  for b in self.PAD_CHOICES]
        return items

    def _set_pad(self, action, button):
        binds = self._resolved_pad()
        if button:
            for a in list(binds):
                if binds[a] == button and a != action:
                    binds[a] = ""
        binds[action] = button
        self.config.gamepad_bindings = binds
        self.config.save()
        self._build_gamepad_buttons()
        self.renderer.menu.replace_page(self._pad_choice_submenu(action))
        self.renderer.mark_dirty()

    def _plex_options_submenu(self):
        if not self.config.plex_token:
            return [MenuItem("(not signed in — open Plex-Per-View)", enabled=False)]
        user = self.config.plex_user_name or "Account"
        items = [
            MenuItem(f"Quality: {self.config.plex_quality}",
                     submenu=self._plex_quality_submenu),
            MenuItem("Libraries", submenu=self._plex_libraries_submenu),
        ]
        # Server picker only when more than one server is available.
        if len(self.config.plex_servers) > 1:
            items.append(MenuItem("Server", submenu=self._plex_servers_submenu))
        items += [
            MenuItem(f"User: {user}", action=self._plex_change_user),
            MenuItem("Unlink Plex Account", action=self._plex_unlink),
        ]
        return items

    def _plex_servers_submenu(self):
        servers = self.config.plex_servers
        if not servers:
            return [MenuItem("(open Plex-Per-View first)", enabled=False)]
        cur = self.config.plex_server_id
        return [MenuItem(s["title"] + ("" if s.get("owned") else "  (shared)"),
                         checked=(s["id"] == cur),
                         action=lambda i=s["id"]: self._plex_set_server(i),
                         close_after=False)
                for s in servers]

    def _plex_set_server(self, server_id):
        if server_id == self.config.plex_server_id:
            return
        self.config.plex_server_id = server_id
        self.config.plex_server = ""        # drop cached base URL; rediscover
        self.config.save()
        self._plex_reset()                  # rebuild client, then reconnect
        self.renderer.menu.replace_page(self._plex_servers_submenu())
        self.renderer.mark_dirty()
        # Re-enter the library from the chosen server (off the menu thread).
        self._plex_end()
        self._ppv_stack = []
        self.renderer.plexinfo.close()
        self.renderer.ppv.mode = "browse"
        self.renderer.ppv.rows = []
        self.renderer.ppv.show()
        self.renderer.ppv.set_status("CONNECTING...")
        self._ppv_return_menu = self.renderer.main_menu.open
        self.renderer.menu.close()
        self.renderer.main_menu.close()
        self._ppv_connect()

    def _plex_libraries_submenu(self):
        secs = self.config.plex_sections
        if not secs:
            return [MenuItem("(open Plex-Per-View first)", enabled=False)]
        hidden = set(self.config.plex_hidden_libraries)
        # A check means the library is shown; toggling hides/shows it.
        return [MenuItem(s["title"], checked=(s["key"] not in hidden),
                         action=lambda k=s["key"]: self._plex_toggle_library(k),
                         close_after=False)
                for s in secs]

    def _plex_toggle_library(self, key):
        hidden = list(self.config.plex_hidden_libraries)
        if key in hidden:
            hidden.remove(key)
        else:
            hidden.append(key)
        self.config.plex_hidden_libraries = hidden
        self.config.save()
        self.renderer.menu.replace_page(self._plex_libraries_submenu())
        self.renderer.mark_dirty()

    def _plex_quality_submenu(self):
        cur = self.config.plex_quality
        return [MenuItem(q, action=lambda x=q: self._plex_set_quality(x),
                         checked=(q == cur), close_after=False)
                for q in plex.QUALITY_OPTIONS]

    def _plex_set_quality(self, q):
        self.config.plex_quality = q
        self.config.save()
        self.renderer.menu.replace_page(self._plex_quality_submenu())
        self.renderer.mark_dirty()

    def _plex_change_user(self):
        r = self.renderer
        self._plex_end()
        r.plexinfo.close()
        self._ppv_return_menu = r.main_menu.open
        r.menu.close()
        r.main_menu.close()
        self._ppv_stack = []
        r.ppv.mode = "browse"
        r.ppv.rows = []
        r.ppv.show()
        r.mark_dirty()
        self._ppv_choose_user(force=True)

    def _plex_unlink(self):
        self._plex_end()
        self.config.plex_token = ""
        self.config.plex_user_token = ""
        self.config.plex_user_id = ""
        self.config.plex_user_name = ""
        self.config.save()
        self._plex_reset()      # forces the PIN sign-in again next time
        self.renderer.show_notification("Plex account unlinked", 3.0)
        self.renderer.mark_dirty()

    # ── Plex audio / subtitle settings ────────────────────────────────────

    SUB_SIZES = [("Small", 28), ("Medium", 38), ("Large", 52), ("Extra Large", 68)]
    SUB_COLORS = [("White", "#FFFFFFFF"), ("Yellow", "#FFFFFF00"),
                  ("Cyan", "#FF00FFFF"), ("Green", "#FF00FF00"),
                  ("Black", "#FF000000")]

    def _plex_av_submenu(self):
        return [
            MenuItem("Audio Track", submenu=self._plex_audio_tracks_submenu),
            MenuItem("Audio Device", submenu=self._plex_audio_devices_submenu),
            MenuItem("Subtitle Track", submenu=self._plex_sub_tracks_submenu),
            MenuItem("Subtitle Font", submenu=self._plex_sub_font_submenu),
            MenuItem("Subtitle Size", submenu=self._plex_sub_size_submenu),
            MenuItem("Subtitle Color", submenu=self._plex_sub_color_submenu),
        ]

    @staticmethod
    def _track_label(t) -> str:
        bits = [str(t["id"])]
        if t.get("lang"):
            bits.append(t["lang"])
        if t.get("title"):
            bits.append(t["title"])
        return ": ".join([bits[0], " ".join(bits[1:])]) if len(bits) > 1 else bits[0]

    def _plex_audio_tracks_submenu(self):
        tracks = self.player.get_tracks()["audio"]
        if not tracks:
            return [MenuItem("(no audio tracks)", enabled=False)]
        return [MenuItem(self._track_label(t), checked=t["selected"], close_after=False,
                         action=lambda i=t["id"]: self._plex_set_audio_track(i))
                for t in tracks]

    def _plex_set_audio_track(self, tid):
        self.player.set_audio_track(tid)
        self.renderer.menu.replace_page(self._plex_audio_tracks_submenu())
        self.renderer.mark_dirty()

    def _plex_sub_tracks_submenu(self):
        tracks = self.player.get_tracks()["sub"]
        none_sel = not any(t["selected"] for t in tracks)
        items = [MenuItem("Off", checked=none_sel, close_after=False,
                          action=lambda: self._plex_set_sub_track("no"))]
        for t in tracks:
            items.append(MenuItem(self._track_label(t), checked=t["selected"],
                         close_after=False,
                         action=lambda i=t["id"]: self._plex_set_sub_track(i)))
        return items

    def _plex_set_sub_track(self, tid):
        self.player.set_sub_track(tid)
        self.renderer.menu.replace_page(self._plex_sub_tracks_submenu())
        self.renderer.mark_dirty()

    def _plex_audio_devices_submenu(self):
        devs = self.player.get_audio_devices()
        if not devs:
            return [MenuItem("(no devices)", enabled=False)]
        cur = self.config.audio_device or "auto"
        return [MenuItem((d["desc"] or d["name"])[:38], checked=(d["name"] == cur),
                         close_after=False,
                         action=lambda n=d["name"]: self._plex_set_audio_device(n))
                for d in devs]

    def _plex_set_audio_device(self, name):
        self.player.set_audio_device(name)
        self.config.audio_device = "" if name == "auto" else name
        self.config.save()
        self.renderer.menu.replace_page(self._plex_audio_devices_submenu())
        self.renderer.mark_dirty()

    def _plex_sub_font_submenu(self):
        cur = self.config.sub_font
        items = [MenuItem("Default", checked=(not cur), close_after=False,
                          action=lambda: self._plex_set_sub_font(""))]
        for k in theme.available_fonts(include_subtitle_only=True):
            items.append(MenuItem(theme.font_label(k), checked=(k == cur),
                         close_after=False,
                         action=lambda key=k: self._plex_set_sub_font(key)))
        return items

    def _plex_set_sub_font(self, key):
        self.config.sub_font = key
        self.config.save()
        fam = theme.font_family(key) if key else "sans-serif"
        self.player.apply_sub_style(font=fam)
        self.renderer.menu.replace_page(self._plex_sub_font_submenu())
        self.renderer.mark_dirty()

    def _plex_sub_size_submenu(self):
        cur = self.config.sub_size
        return [MenuItem(name, checked=(sz == cur), close_after=False,
                         action=lambda s=sz: self._plex_set_sub_size(s))
                for name, sz in self.SUB_SIZES]

    def _plex_set_sub_size(self, sz):
        self.config.sub_size = sz
        self.config.save()
        self.player.apply_sub_style(size=sz)
        self.renderer.menu.replace_page(self._plex_sub_size_submenu())
        self.renderer.mark_dirty()

    def _plex_sub_color_submenu(self):
        cur = self.config.sub_color
        return [MenuItem(name, checked=(hexc == cur), close_after=False,
                         action=lambda c=hexc: self._plex_set_sub_color(c))
                for name, hexc in self.SUB_COLORS]

    def _plex_set_sub_color(self, hexc):
        self.config.sub_color = hexc
        self.config.save()
        self.player.apply_sub_style(color=hexc)
        self.renderer.menu.replace_page(self._plex_sub_color_submenu())
        self.renderer.mark_dirty()

    def _apply_plex_av(self):
        """Apply the persisted subtitle style + audio device to the new stream."""
        if self.config.audio_device:
            self.player.set_audio_device(self.config.audio_device)
        fam = theme.font_family(self.config.sub_font) if self.config.sub_font else None
        self.player.apply_sub_style(font=fam, size=self.config.sub_size,
                                    color=self.config.sub_color)

    def _themes_submenu(self):
        return [
            MenuItem("Color Theme", submenu=self._theme_submenu),
            MenuItem("Font", submenu=self._font_submenu),
            MenuItem("Profiles", submenu=self._profiles_submenu),
        ]

    def _weather_submenu(self):
        z = self.config.weather_zip or "(not set)"
        # close_after=False keeps us in the Weather submenu; the handlers refresh
        # the page so the new zip/units/country label shows immediately.
        return [
            MenuItem(f"Zip Code: {z}", action=self._set_weather_zip,
                     close_after=False),
            MenuItem(f"Country: {weather.country_name(self.config.weather_country)}",
                     submenu=self._country_submenu),
            MenuItem(f"Units: °{self.config.weather_units}",
                     action=self._toggle_weather_units, close_after=False),
        ]

    def _country_submenu(self):
        cur = (self.config.weather_country or "").upper()
        return [MenuItem(name, action=lambda c=code: self._set_weather_country(c),
                         checked=(code == cur), close_after=False)
                for code, name in weather.COUNTRIES]

    def _set_weather_zip(self):
        z = self._osk_get("Weather zip / postal code", self.config.weather_zip)
        if z is None:                      # cancelled
            return
        self.config.weather_zip = z.strip()
        self._apply_weather_config()

    def _toggle_weather_units(self):
        self.config.weather_units = \
            "C" if self.config.weather_units.upper().startswith("F") else "F"
        self._apply_weather_config()

    def _set_weather_country(self, code):
        self.config.weather_country = code
        self.config.save()
        if self.renderer.weather:
            self.renderer.weather.configure(self.config.weather_zip,
                                            self.config.weather_units, code)
        # Return to the Weather submenu, rebuilt so its "Country:" label updates.
        self.renderer.menu.back_and_replace(self._weather_submenu())
        self.renderer.mark_dirty()

    def _apply_weather_config(self):
        self.config.save()
        if self.renderer.weather:
            self.renderer.weather.configure(self.config.weather_zip,
                                            self.config.weather_units,
                                            self.config.weather_country)
        self.renderer.menu.replace_page(self._weather_submenu())  # refresh labels
        self.renderer.mark_dirty()

    def _display_submenu(self):
        items = [MenuItem("Fullscreen", action=self._toggle_fullscreen, hint="W",
                          checked=self._fullscreen, close_after=False)]
        for i, name in enumerate(self.player.get_displays()):
            # close_after=False so picking a display keeps the menu open.
            items.append(MenuItem(name or f"Display {i}",
                         action=lambda idx=i: self._switch_display(idx),
                         close_after=False))
        return items

    def _switch_display(self, index: int):
        """Move the window to monitor `index`, preserving the current windowed /
        fullscreen state.  mpv emits new osd dimensions, which the resize handler
        uses to rescale the aspect ratio + OSD."""
        print(f"[cathode] Switching to display {index}")
        self.player.set_display(index)
        if self._fullscreen:
            # Re-assert fullscreen so it relocates to the new screen.
            self.player.set_fullscreen(False)
            self.player.set_fullscreen(True)
        else:
            # mpv won't relocate an already-open windowed window from `screen`
            # alone, so nudge it onto the target screen.
            self.player.move_window_to_screen(index)

    # ── Playlist / network profiles ───────────────────────────────────────

    def _playlists_submenu(self):
        active = self.config.playlist_url
        items = []
        for pl in self.config.playlists:
            items.append(MenuItem(
                pl.get("name", "(unnamed)"),
                action=lambda p=pl: self._switch_playlist(p),
                checked=(pl.get("playlist_url") == active)))
        items.append(MenuItem("-" * 16, enabled=False))
        items.append(MenuItem("Add playlist...", action=self._add_playlist_dialog))
        items.append(MenuItem("Delete playlist...",
                              submenu=self._delete_playlist_submenu))
        return items

    def _delete_playlist_submenu(self):
        items = [MenuItem(p.get("name", "?"),
                          action=lambda pl=p: self._delete_playlist(pl))
                 for p in self.config.playlists]
        if not items:
            items.append(MenuItem("(no saved playlists)", enabled=False))
        return items

    def _add_playlist_dialog(self):
        """OSK-prompt for a new playlist; returns the saved dict (or None)."""
        name = self._osk_get("Playlist name", "")
        if not name:
            return None
        m3u_url = self._osk_get(f"M3U URL for '{name}'", "")
        if not m3u_url:
            return None
        epg_url = self._osk_get("XMLTV EPG URL (optional)", "")
        pl = {"name": name, "playlist_url": m3u_url, "epg_url": epg_url or ""}
        self.config.playlists.append(pl)
        self.config.save()
        print(f"[cathode] Added playlist: {name}")
        return pl

    def _delete_playlist(self, pl):
        if pl in self.config.playlists:
            self.config.playlists.remove(pl)
            self.config.save()
            print(f"[cathode] Deleted playlist: {pl.get('name')}")

    def _switch_playlist(self, pl):
        """Switch to a saved playlist: reload channels + EPG and retune."""
        self.config.playlist_url = pl.get("playlist_url", "")
        self.config.epg_url = pl.get("epg_url", "")
        self.config.save()
        self.channels = []
        self.epg = None
        self.renderer.epg = None
        print(f"[cathode] Switching to playlist: {pl.get('name')}")
        self._load_playlist_interactive()      # may OSK-prompt on failure
        self.renderer.channels = self.channels
        self._rebuild_categories()
        if self.config.epg_url:
            threading.Thread(target=self._load_epg, daemon=True).start()
        self._ch_idx = 0
        self._tune(0, initial=False)

    # ── Main menu / home screen ───────────────────────────────────────────

    def _open_main_menu(self):
        """Return to the home screen (from the context menu / leave prompt)."""
        self._plex_end()
        self.player.stop()       # stop live TV too — home screen is not playback
        self.renderer.plexinfo.close()
        self.renderer.ppv.close()
        self.renderer.menu.close()
        self.renderer.main_menu.show(self._main_menu_select)
        self.renderer.update()

    def _main_menu_select(self, key: str):
        if key == "new":
            self._main_new_playlist()
        elif key == "load":
            self._main_load_playlist()
        elif key == "plex":
            self._open_ppv()
        elif key == "options":
            self._main_options()
        elif key == "exit":
            self._quit_app()

    def _main_new_playlist(self):
        pl = self._add_playlist_dialog()      # OSK prompts (over the home screen)
        if pl:
            self._start_from_playlist(pl)

    def _main_load_playlist(self):
        """List saved playlists to choose from (context menu over the home
        screen). Falls back to New if none are saved."""
        choices = list(self.config.playlists)
        # Include the configured-but-unsaved playlist as a "Current" option.
        active = self.config.playlist_url
        if active and not any(p.get("playlist_url") == active for p in choices):
            choices.insert(0, {"name": "Current", "playlist_url": active,
                               "epg_url": self.config.epg_url})
        if not choices:
            self._main_new_playlist()
            return
        items = [MenuItem(p.get("name", "(unnamed)"),
                          action=lambda pl=p: self._start_from_playlist(pl),
                          close_after=True)
                 for p in choices]
        self.renderer.menu.open_with(items, title="LOAD PLAYLIST")
        self.renderer.mark_dirty()

    def _main_options(self):
        items = self._options_submenu() + [
            MenuItem("Playlists", submenu=self._playlists_submenu),
            MenuItem("Quit", action=self._quit_app, hint="Q"),
        ]
        self.renderer.menu.open_with(items, title="OPTIONS")
        self.renderer.mark_dirty()

    # ── Plex-Per-View ─────────────────────────────────────────────────────

    def _ppv_client(self):
        # Locked so a token change (_plex_reset from sign-in / unlink) can't race
        # an in-flight worker into building two clients or seeing a torn state.
        with self._plex_lock:
            if self._plex is None:
                if not self.config.plex_client_id:
                    self.config.plex_client_id = plex.new_client_id()
                    self.config.save()
                from . import __version__
                self._plex = plex.PlexClient(
                    self.config.plex_client_id,
                    token=self.config.plex_user_token or self.config.plex_token,
                    admin_token=self.config.plex_token, version=__version__)
            return self._plex

    def _plex_reset(self):
        """Drop the cached client so the next _ppv_client() rebuilds it with the
        current token (after sign-in, user switch, or unlink)."""
        with self._plex_lock:
            self._plex = None

    def _open_ppv(self):
        """Enter Plex-Per-View (from the home screen or context menu)."""
        r = self.renderer
        self._plex_end()                 # opening the library ends any stream
        r.plexinfo.close()
        self._ppv_return_menu = r.main_menu.open   # came from the home screen?
        r.menu.close()
        r.main_menu.close()
        self._ppv_stack = []
        r.ppv.mode = "browse"
        r.ppv.rows = []
        r.ppv.show()
        r.ppv.set_status("CONNECTING...")
        r.mark_dirty()
        if self._ppv_client().token:
            self._ppv_connect()
        else:
            self._ppv_begin_auth()

    def _ppv_connect(self):
        """Discover the server and list libraries (background)."""
        def work():
            try:
                client = self._ppv_client()
                client.discover_server(prefer=self.config.plex_server_id)
                sections = client.sections()
            except Exception as e:
                self._ppv_error(str(e) or "Couldn't reach Plex.")
                return
            # Cache the library list (show/hide menu) + the server list (server
            # picker) so both menus work without another round-trip.
            self.config.plex_sections = [{"key": s["key"], "title": s["title"]}
                                         for s in sections]
            try:
                self.config.plex_servers = client.list_servers()
            except Exception:
                pass
            self.config.save()
            hidden = set(self.config.plex_hidden_libraries)
            rows = [
                {"type": "search", "title": "SEARCH...", "meta": "",
                 "playable": False},
                {"type": "ondeck", "title": "CONTINUE WATCHING", "meta": "",
                 "playable": False},
                {"type": "watchlist", "title": "MY WATCHLIST", "meta": "",
                 "playable": False},
            ]
            rows += [{"type": "section", "rating_key": s["key"],
                      "title": s["title"].upper(), "meta": "", "playable": False,
                      "section_type": s["type"], "agent": s.get("agent", "")}
                     for s in sections if s["key"] not in hidden]
            self._ppv_push("CHOOSE A LIBRARY", rows, "Plex-Per-View")
        threading.Thread(target=work, daemon=True).start()

    def _ppv_begin_auth(self):
        def work():
            try:
                pin = self._ppv_client().request_pin()
            except Exception:
                self._ppv_error("Couldn't start Plex sign-in.")
                return
            self._ppv_pin_id = pin["id"]
            self.renderer.ppv.set_auth(pin["code"], pin["link"])
            self.renderer.mark_dirty()
            self._ppv_poll_auth()
        threading.Thread(target=work, daemon=True).start()

    def _ppv_poll_auth(self):
        import time
        deadline = time.monotonic() + 300
        r = self.renderer
        while (r.ppv.open and r.ppv.mode == "auth"
               and time.monotonic() < deadline):
            try:
                token = self._ppv_client().poll_pin(self._ppv_pin_id)
            except Exception:
                token = None
            if token:
                self.config.plex_token = token
                self.config.plex_user_token = ""   # account level until a user is picked
                self.config.save()
                self._plex_reset()                 # rebuild with the new token
                r.ppv.set_status("CONNECTING...")
                r.mark_dirty()
                self._ppv_choose_user()
                return
            time.sleep(2.0)

    def _ppv_choose_user(self, force: bool = False):
        """After linking (or via Change User), show the Plex Home users. Falls
        through to the library when there's only one user or none are found."""
        r = self.renderer
        r.ppv.show()
        r.ppv.set_status("LOADING USERS...")
        r.mark_dirty()
        def work():
            try:
                users = self._ppv_client().home_users()
            except Exception:
                users = []
            if len(users) <= 1:
                self._ppv_connect()        # single user / not a Home — just go
                return
            rows = [{"type": "user", "rating_key": u["uuid"],
                     "title": u["title"], "meta": "PIN" if u["protected"] else "",
                     "protected": u["protected"],
                     "playable": False} for u in users]
            self._ppv_stack = []
            self._ppv_push("WHO'S WATCHING?", rows, "Plex-Per-View")
        threading.Thread(target=work, daemon=True).start()

    def _ppv_pick_user(self, uuid, name, protected=False):
        r = self.renderer

        def work():
            token = ""
            while True:
                pin = ""
                if protected:
                    pin = self._osk_get(f"Enter PIN for {name}", "")
                    if not pin:
                        # Cancelled — don't switch; return to the user list.
                        self._ppv_choose_user(force=True)
                        return
                r.ppv.set_status("SWITCHING...")
                r.mark_dirty()
                try:
                    token = self._ppv_client().switch_user(uuid, pin)
                except Exception:
                    token = ""
                if token or not protected:
                    break                       # success, or non-protected failure
                r.show_notification("Wrong PIN — try again", 2.5)
            if token:
                self.config.plex_user_token = token
                self.config.plex_user_id = uuid
                self.config.plex_user_name = name
            else:
                # Non-protected switch failed — stay on the account.
                self.config.plex_user_token = ""
                self.config.plex_user_id = ""
                self.config.plex_user_name = ""
            self.config.save()
            self._ppv_stack = []
            self._ppv_connect()
        threading.Thread(target=work, daemon=True).start()

    SORT_OPTIONS = [
        ("Title (A-Z)", "titleSort:asc"), ("Title (Z-A)", "titleSort:desc"),
        ("Date Added (Newest)", "addedAt:desc"), ("Date Added (Oldest)", "addedAt:asc"),
        ("Year (Newest)", "year:desc"), ("Year (Oldest)", "year:asc"),
        ("Rating (Highest)", "rating:desc"), ("Rating (Lowest)", "rating:asc"),
    ]

    def _ppv_select(self):
        r = self.renderer
        if self._ppv_stack:
            self._ppv_stack[-1]["sel"] = r.ppv.sel
        row = r.ppv.current()
        if not row:
            return
        t = row.get("type")
        title = row.get("title", "")
        rk = row.get("rating_key")
        if t == "user":
            self._ppv_pick_user(rk, title, row.get("protected", False))
            return
        if t == "watchlist":
            self._ppv_open_watchlist()
            return
        if t == "ondeck":
            self._ppv_open_ondeck()
            return
        if t == "search":
            self._ppv_search()
            return
        if t == "sort":
            self.renderer.menu.open_with(self._sort_submenu(), title="SORT BY")
            self.renderer.mark_dirty()
            return
        if row.get("watchlist"):             # an item from the watchlist
            self._ppv_watchlist_open(row)
            return
        if row.get("playable"):
            self._ppv_show_info(row)         # open the info screen first
            return
        if t == "section":
            stype = row.get("section_type")
            if self._ppv_client().is_other_videos({"agent": row.get("agent", "")}):
                self._ppv_other_videos(rk, title)
            elif stype in ("movie", "show"):
                self._ppv_categories(rk, title, stype)
            else:
                self._ppv_open(
                    lambda s, k=rk: self._ppv_client().section_filter(k, sort=s), title)
        elif t in ("all", "allvideos"):
            self._ppv_open(
                lambda s, k=rk: self._ppv_client().section_filter(k, sort=s), title)
        elif t == "genre":
            gid = row.get("genre_id")
            self._ppv_open(
                lambda s, k=rk, g=gid: self._ppv_client().section_filter(
                    k, genre_id=g, sort=s), title)
        elif t == "folderview":
            self._ppv_load_folder(f"/library/sections/{rk}/folder", "FOLDERS", rk)
        elif t == "folder":
            self._ppv_load_folder(row.get("folder"), title, row.get("section", ""))
        elif t == "show":
            self._ppv_show_info(row)         # series info screen (Play All/etc.)
        else:
            self._ppv_open(
                lambda s, k=rk: self._ppv_client().children(k, sort=s), title)

    def _ppv_load_folder(self, path, title, section=""):
        r = self.renderer
        r.ppv.set_status("LOADING...")
        r.mark_dirty()
        crumb = " / ".join(l["title"] for l in self._ppv_stack) or "Plex-Per-View"
        def work():
            try:
                rows = self._ppv_client().folder_items(path, section)
            except Exception as e:
                self._ppv_error(str(e) or "Couldn't load that folder.")
                return
            self._ppv_push(title, rows, crumb)
        threading.Thread(target=work, daemon=True).start()

    def _ppv_other_videos(self, key, title):
        crumb = " / ".join(l["title"] for l in self._ppv_stack) or "Plex-Per-View"
        rows = [
            {"type": "allvideos", "rating_key": key, "title": "ALL VIDEOS",
             "meta": "", "playable": False},
            {"type": "folderview", "rating_key": key, "title": "BY FOLDER",
             "meta": "", "playable": False},
        ]
        self._ppv_push(title, rows, crumb)

    def _ppv_open(self, loader, title, sort="", volatile=False, sortable=True):
        """Load an item list. `loader(sort)` returns rows; the level remembers
        the loader. sortable=True pins a Sort row (library lists); set False for
        lists with no meaningful sort (onDeck, search). volatile=True reloads the
        level every time it's returned to (watchlist, onDeck, search)."""
        r = self.renderer
        r.ppv.set_status("LOADING...")
        r.mark_dirty()
        crumb = " / ".join(l["title"] for l in self._ppv_stack) or "Plex-Per-View"
        def work():
            try:
                rows = loader(sort)
            except Exception as e:
                self._ppv_error(str(e) or "Couldn't load that.")
                return
            self._ppv_push(title, rows, crumb, loader=loader, sort=sort,
                           volatile=volatile, sortable=sortable)
        threading.Thread(target=work, daemon=True).start()

    def _ppv_open_watchlist(self):
        self._ppv_open(lambda s: self._ppv_client().watchlist(sort=s),
                       "MY WATCHLIST", volatile=True)

    def _ppv_open_ondeck(self):
        # volatile so it reloads (and drops finished items) each time it's opened.
        self._ppv_open(lambda s: self._ppv_client().on_deck(),
                       "CONTINUE WATCHING", volatile=True, sortable=False)

    def _ppv_search(self):
        query = self._osk_get("Search Plex", "")
        if not query or not query.strip():
            return
        self._ppv_open(lambda s, q=query: self._ppv_client().search(q),
                       f"SEARCH: {query.upper()}", volatile=True, sortable=False)

    def _ppv_watchlist_open(self, row):
        guid = row.get("guid")
        typ = row.get("type")
        title = row.get("title", "")
        r = self.renderer
        r.ppv.set_status("FINDING...")
        r.mark_dirty()
        def work():
            rk = self._ppv_client().find_on_server(guid)
            if not rk:
                self._ppv_error("Not in your library.")
                return
            if typ in ("movie", "episode", "show"):
                self._ppv_show_info({"rating_key": rk})
            else:
                self._ppv_open(
                    lambda s, k=rk: self._ppv_client().children(k, sort=s), title)
        threading.Thread(target=work, daemon=True).start()

    def _ppv_set_sort(self, sort):
        if not self._ppv_stack or not self._ppv_stack[-1].get("loader"):
            return
        lvl = self._ppv_stack.pop()
        self._ppv_open(lvl["loader"], lvl["title"], sort=sort)

    def _sort_submenu(self):
        cur = self._ppv_stack[-1].get("sort", "") if self._ppv_stack else ""
        return [MenuItem(name, checked=(val == cur),
                         action=lambda v=val: self._ppv_set_sort(v))
                for name, val in self.SORT_OPTIONS]

    def _ppv_categories(self, section_key, title, stype):
        r = self.renderer
        r.ppv.set_status("LOADING...")
        r.mark_dirty()
        crumb = " / ".join(l["title"] for l in self._ppv_stack) or "Plex-Per-View"
        all_label = "ALL MOVIES" if stype == "movie" else "ALL SHOWS"
        def work():
            try:
                genres = self._ppv_client().genres(section_key)
            except Exception:
                genres = []
            rows = [{"type": "all", "rating_key": section_key, "title": all_label,
                     "meta": "", "playable": False}]
            for g in genres:
                rows.append({"type": "genre", "rating_key": section_key,
                             "genre_id": g["id"], "title": g["title"].upper(),
                             "meta": "", "playable": False})
            self._ppv_push(title, rows, crumb)
        threading.Thread(target=work, daemon=True).start()

    def _ppv_show_info(self, row):
        rk = row.get("rating_key")
        r = self.renderer
        r.ppv.set_status("LOADING...")
        r.mark_dirty()
        def work():
            try:
                detail = self._ppv_client().item_detail(rk)
            except Exception as e:
                self._ppv_error(str(e) or "Couldn't load info.")
                return
            self._plex_info_data = detail
            kind = detail.get("type", "")
            kind = kind if kind in ("show", "episode") else "default"
            on_wl = self._plex_watchlist_has(detail.get("guid", "")) \
                if kind != "episode" else False
            r.ppv.close()
            r.plexinfo.show(detail, watchlisted=on_wl, kind=kind)
            r.update()
        threading.Thread(target=work, daemon=True).start()

    def _plex_info_activate(self):
        fid = self.renderer.plexinfo.focused_id()
        if fid == "play":
            self._plex_info_play()
        elif fid == "playall":
            self._plex_show_playall(shuffle=False)
        elif fid == "shuffle":
            self._plex_show_playall(shuffle=True)
        elif fid == "seasons":
            self._plex_show_seasons()
        elif fid == "watchlist":
            self._plex_info_watchlist()
        elif fid == "back":
            self._plex_info_back()

    def _plex_show_seasons(self):
        d = self._plex_info_data or {}
        rk = d.get("rating_key")
        title = d.get("title", "")
        self.renderer.plexinfo.close()
        self.renderer.ppv.show()     # bring PPV back so LOADING/list is visible
        self._ppv_open(
            lambda s, k=rk: self._ppv_client().children(k, sort=s), title)

    def _plex_show_playall(self, shuffle=False):
        d = self._plex_info_data or {}
        rk = d.get("rating_key")
        self.renderer.mark_dirty()
        def work():
            try:
                eps = self._ppv_client().all_episodes(rk)
            except Exception as e:
                self._ppv_error(str(e) or "Couldn't load episodes.")
                return
            if not eps:
                self._ppv_error("No episodes to play.")
                return
            if shuffle:
                import random
                random.shuffle(eps)
            self._plex_queue = eps
            self._plex_queue_pos = 0
            self._ppv_play(eps[0], d.get("title", ""), resume=False,
                           keep_queue=True)
        threading.Thread(target=work, daemon=True).start()

    def _plex_info_play(self):
        d = self._plex_info_data or {}
        if d.get("offset", 0) > 5:
            self._ppv_resume_prompt(d)
        else:
            self._ppv_play(d.get("rating_key"), d.get("title", ""),
                           d.get("subtitle", ""), resume=False)

    def _plex_watchlist_has(self, guid):
        """Best-effort check whether `guid` is on the user's watchlist. Matches
        on the full guid or its trailing metadata id (server vs Discover guids
        share the id)."""
        if not guid:
            return False
        try:
            wl = self._ppv_client().watchlist()
        except Exception:
            return False
        gid = guid.rstrip("/").split("/")[-1]
        for r in wl:
            wg = r.get("guid", "")
            if wg == guid or (gid and wg.rstrip("/").split("/")[-1] == gid):
                return True
        return False

    def _plex_info_watchlist(self):
        d = self._plex_info_data or {}
        guid = d.get("guid", "")
        info = self.renderer.plexinfo
        add = not info.watchlisted
        def work():
            if self._ppv_client().watchlist_set(guid, add):
                info.watchlisted = add
            self.renderer.mark_dirty()
        threading.Thread(target=work, daemon=True).start()

    def _plex_info_back(self):
        self.renderer.plexinfo.close()
        if self._ppv_stack:
            self._ppv_show_top()   # reloads watchlist so removed items disappear
        self.renderer.update()

    def _ppv_resume_prompt(self, row):
        rk = row.get("rating_key")
        title = row.get("title", "")
        sub = row.get("subtitle") or row.get("meta", "")
        ts = self._fmt_time(row.get("offset", 0))
        items = [
            MenuItem(f"Resume from {ts}",
                     action=lambda: self._ppv_play(rk, title, sub, resume=True)),
            MenuItem("Start from Beginning",
                     action=lambda: self._ppv_play(rk, title, sub, resume=False)),
        ]
        self.renderer.menu.open_with(items, title="RESUME?")
        self.renderer.mark_dirty()

    @staticmethod
    def _fmt_time(s) -> str:
        s = max(0, int(s or 0))
        h, m, sec = s // 3600, (s % 3600) // 60, s % 60
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"

    def _ppv_play(self, rating_key, title, subtitle="", resume=True,
                  keep_queue=False):
        if not keep_queue:
            self._plex_queue = []    # a one-off play cancels any episode queue
            self._plex_queue_pos = 0
        r = self.renderer
        r.menu.close()               # in case the resume prompt opened it
        r.plexinfo.close()
        r.ppv.set_status("STARTING...")
        r.mark_dirty()
        def work():
            try:
                info = self._ppv_client().play_info(rating_key, self.config.plex_quality)
            except Exception as e:
                self._ppv_error(str(e) or "Couldn't play that.")
                return
            r.ppv.close()
            r.state = UIState.WATCHING
            r.plex_playing = True
            self._plex_paused = False
            self._plex_duration = None
            self._plex_pos = 0.0
            self._plex_now_rk = rating_key
            self._plex_markers = info.get("markers") or []
            r.plexosd.skip_label = ""
            r.plexosd.set_info(info.get("title") or title,
                               info.get("subtitle") or subtitle)
            r.plexosd.paused = False
            r.plexosd.adjusting = False
            r.plexosd.focus = 0          # default highlight on the timeline
            r.plexosd.volume = self.config.volume
            r.plexosd.muted = self.config.muted
            start = info.get("offset", 0) if resume else 0
            self.player.play(info["url"], start=start,
                             headers=info.get("headers"))
            self._apply_plex_av()        # subtitle style + audio device
            self._plex_show_osd()
            self._start_plex_monitor()
            r.update()
        threading.Thread(target=work, daemon=True).start()

    # ── Plex playback controls ────────────────────────────────────────────

    def _space_key(self):
        if self.renderer.plex_playing:
            self._plex_toggle_pause()
        else:
            self._char_typed(" ")

    def _plex_show_osd(self):
        import time
        self.renderer.plexosd.show()
        self._plex_osd_until = time.monotonic() + 5.0
        self.renderer.mark_dirty()

    def _start_plex_monitor(self):
        if self._plex_monitor:
            return
        self._plex_monitor = True
        threading.Thread(target=self._plex_monitor_loop, daemon=True).start()

    def _plex_monitor_loop(self):
        import time
        r = self.renderer
        while self._plex_monitor and r.plex_playing:
            pos = self.player.get_property("time-pos")
            if pos is not None:
                self._plex_pos = pos
            if self._plex_duration is None:
                self._plex_duration = self.player.get_property("duration")
            r.plexosd.set_progress(pos or 0, self._plex_duration or 0, self._plex_paused)
            # Skip Intro/Credits: show the button only while pos is inside a marker.
            self._update_skip_button(pos or 0)
            if r.plexosd.visible:
                if time.monotonic() > self._plex_osd_until:
                    r.plexosd.hide()
                r.mark_dirty()
            # Heartbeat: tell the server our position every ~10s so Now-Playing
            # and cross-device "Continue Watching" stay current mid-stream.
            now = time.monotonic()
            if pos is not None and now - self._plex_last_report >= 10:
                self._plex_last_report = now
                self._plex_report("paused" if self._plex_paused else "playing")
            time.sleep(0.5)
        self._plex_monitor = False

    def _update_skip_button(self, pos):
        """Show the SKIP button on the OSD only while playback is inside an
        intro/credits marker; hide it otherwise."""
        label, end = "", 0.0
        for mk in self._plex_markers:
            if mk["start"] <= pos < mk["end"]:
                label = "SKIP INTRO" if mk["type"] == "intro" else "SKIP CREDITS"
                end = mk["end"]
                break
        osd = self.renderer.plexosd
        osd.skip_to = end
        if label != osd.skip_label:
            osd.skip_label = label      # entered or left a marker — redraw the bar
            self.renderer.mark_dirty()

    def _plex_skip_marker(self):
        """Press SKIP: jump to the end of the active marker. For a credits
        marker this lands at ~EOF and the normal finish/next-episode flow runs."""
        osd = self.renderer.plexosd
        if osd.skip_to:
            self.player.seek(osd.skip_to, "absolute")
            osd.skip_label = ""         # hide now; the monitor re-evaluates next tick
            self._plex_show_osd()

    def _plex_focus(self, delta):
        osd = self.renderer.plexosd
        if osd.adjusting:
            return   # volume is selected for adjustment — Up/Down is locked
        osd.scrubbing = False    # moving the highlight ends scrub mode
        osd.focus_next() if delta > 0 else osd.focus_prev()
        self._plex_show_osd()

    def _plex_dpad(self, direction):
        """Left/Right: adjust volume (when selected), scrub the timeline (when
        selected), else move the highlight."""
        osd = self.renderer.plexosd
        if osd.adjusting:
            self._plex_vol(direction > 0)
        elif osd.scrubbing:
            self._plex_seek(10 * direction)
        else:
            self._plex_focus(direction)   # Left/Right also move the highlight

    def _plex_vol(self, up):
        self._unmute_if_muted()
        vol = self.player.volume_up(5) if up else self.player.volume_down(5)
        self.config.volume = vol
        self.renderer.volume = vol
        self.renderer.plexosd.volume = vol
        self.renderer.plexosd.muted = False
        self._plex_show_osd()

    def _plex_seek(self, delta):
        self.player.seek(delta, "relative")
        self._plex_show_osd()

    def _plex_skip(self, delta):
        """Skip to the next/previous episode (in a Play All / Shuffle queue) or,
        for anything else (a movie), the next/previous chapter."""
        q = self._plex_queue
        if q:
            pos = self._plex_queue_pos + delta
            if 0 <= pos < len(q):
                self._plex_report("stopped")   # save outgoing episode position
                self._plex_queue_pos = pos
                self._ppv_play(q[pos], "", resume=False, keep_queue=True)
            return
        self.player.chapter_skip(delta)
        self._plex_show_osd()

    def _plex_toggle_pause(self):
        self._plex_paused = not self._plex_paused
        self.player.set_pause(self._plex_paused)
        self.renderer.plexosd.paused = self._plex_paused
        self._plex_show_osd()

    def _plex_activate(self):
        osd = self.renderer.plexosd
        fid = osd.focused_id()
        if fid == "volume":
            osd.adjusting = not osd.adjusting   # enter/exit volume adjust mode
            self._plex_show_osd()
            return
        if fid == "skip":
            self._plex_skip_marker()
            return
        if fid == "timeline":
            osd.scrubbing = not osd.scrubbing   # select/deselect to scrub
            self._plex_show_osd()
            return
        if fid == "back10":
            self._plex_seek(-10)
        elif fid == "fwd10":
            self._plex_seek(10)
        elif fid == "prev":
            self._plex_skip(-1)
        elif fid == "next":
            self._plex_skip(1)
        elif fid == "playpause":
            self._plex_toggle_pause()
        elif fid == "stop":
            self._plex_stop()
        elif fid == "menu":
            self._toggle_context_menu()

    def _plex_click(self, name, x):
        osd = self.renderer.plexosd
        if name == "timeline":
            frac = osd.seek_fraction(x)
            if frac is not None and self._plex_duration:
                self.player.seek(frac * self._plex_duration, "absolute")
        elif name == "volume":
            frac = osd.volume_fraction(x)
            if frac is not None:
                vol = self.player.set_volume(int(frac * 100))
                self.config.volume = vol
                self.renderer.volume = vol
                osd.volume = vol
                osd.muted = False
        else:
            osd.focus_to(name)
            self._plex_activate()
        self._plex_show_osd()

    def _plex_report(self, state: str, finished: bool = False):
        """Best-effort timeline report for the item playing now. `finished`
        reports the full duration so Plex marks it watched and clears resume."""
        rk = self._plex_now_rk
        if not rk:
            return
        dur = self._plex_duration or 0
        t = dur if (finished and dur) else self._plex_pos
        threading.Thread(
            target=lambda: self._ppv_client().report_timeline(rk, t, dur, state=state),
            daemon=True).start()

    def _cache_offset(self, rk: str, offset: int):
        """Reflect a new resume point in the cached browse rows so re-selecting
        the item offers to resume (or starts over once watched)."""
        if rk and self._ppv_stack:
            for row in self._ppv_stack[-1]["rows"]:
                if row.get("rating_key") == rk and row.get("playable"):
                    row["offset"] = offset

    def _plex_teardown(self):
        """Tear down playback state + stop mpv (no server report, no nav)."""
        self._plex_monitor = False
        self.renderer.plex_playing = False
        self.renderer.plexosd.hide()
        self.renderer.plexosd.adjusting = False
        self.renderer.plexosd.scrubbing = False
        self.renderer.plexosd.skip_label = ""
        self._plex_markers = []
        self._plex_paused = False
        self._plex_now_rk = ""
        self.player.stop()

    def _plex_end(self):
        """Stop Plex playback and tear down (no navigation)."""
        if not self.renderer.plex_playing:
            return
        # Save the resume point on the server (Plex clears it if we finished).
        rk, pos, dur = self._plex_now_rk, self._plex_pos, self._plex_duration or 0
        if rk and pos > 1:
            self._plex_report("stopped")
            self._cache_offset(rk, 0 if (dur > 0 and pos > dur - 30) else int(pos))
        self._plex_teardown()

    def _plex_finished(self):
        """Current item reached its end: report it watched, clear the resume
        point, and return to the item's info screen (or the browse list)."""
        if not self.renderer.plex_playing:
            return
        rk = self._plex_now_rk
        self._plex_report("stopped", finished=True)
        self._cache_offset(rk, 0)
        self._plex_teardown()
        if self._plex_info_data:
            self._plex_info_data["offset"] = 0
            self.renderer.plexinfo.show(
                self._plex_info_data,
                watchlisted=self.renderer.plexinfo.watchlisted)
            self.renderer.update()
        elif self._ppv_stack:
            lvl = self._ppv_stack[-1]
            self.renderer.ppv.set_browse(lvl["title"], lvl["rows"],
                                         lvl["crumb"], lvl["sel"])
            self.renderer.ppv.show()
            self.renderer.update()
        else:
            self._ppv_exit()

    def _plex_stop(self):
        """Stop button / Esc: end playback and return to the item's info screen."""
        was_playing = self.renderer.plex_playing
        pos, dur = self._plex_pos, self._plex_duration or 0
        self._plex_end()
        if not was_playing:
            return
        if self._plex_info_data:
            self._plex_info_data["offset"] = 0 if (dur and pos > dur - 30) else int(pos)
            self.renderer.plexinfo.show(self._plex_info_data,
                                        watchlisted=self.renderer.plexinfo.watchlisted)
            self.renderer.update()
        elif self._ppv_stack:
            lvl = self._ppv_stack[-1]
            self.renderer.ppv.set_browse(lvl["title"], lvl["rows"],
                                         lvl["crumb"], lvl["sel"])
            self.renderer.ppv.show()
            self.renderer.update()
        else:
            self._ppv_exit()

    def _ppv_push(self, title, rows, crumb, loader=None, sort="", volatile=False,
                  sortable=True):
        # Sortable item lists get a "Sort by..." row pinned at the top so the
        # user can re-order without the context menu.
        has_sort = bool(loader and sortable and rows
                        and rows[0].get("type") != "sort")
        if has_sort:
            label = self._sort_label(sort) or "Default"
            rows = [{"type": "sort", "title": f"Sort by: {label}",
                     "meta": "", "playable": False}] + rows
        sel0 = 1 if has_sort else 0
        self._ppv_stack.append({"title": title, "rows": rows,
                                "sel": sel0,
                                "crumb": crumb, "loader": loader, "sort": sort,
                                "volatile": volatile, "sortable": sortable})
        self.renderer.ppv.set_browse(title, rows, crumb, sel=sel0)
        self.renderer.ppv.show()     # ensure visible (e.g. opened from info screen)
        self.renderer.mark_dirty()

    def _sort_label(self, val):
        for name, v in self.SORT_OPTIONS:
            if v == val:
                return name
        return "" if val else "Default"

    def _ppv_back(self):
        if len(self._ppv_stack) <= 1:
            self._ppv_exit()
            return
        self._ppv_stack.pop()
        self._ppv_show_top()

    def _ppv_show_top(self):
        """Re-show the top browse level. Volatile levels (watchlist) reload from
        the server so changes made deeper (e.g. removed from watchlist) appear."""
        if not self._ppv_stack:
            return
        lvl = self._ppv_stack[-1]
        if lvl.get("volatile") and lvl.get("loader"):
            self._ppv_stack.pop()
            self._ppv_open(lvl["loader"], lvl["title"],
                           sort=lvl.get("sort", ""), volatile=True,
                           sortable=lvl.get("sortable", True))
            return
        self.renderer.ppv.set_browse(lvl["title"], lvl["rows"], lvl["crumb"], lvl["sel"])
        self.renderer.ppv.show()
        self.renderer.mark_dirty()

    def _ppv_exit(self):
        self.renderer.ppv.close()
        self.renderer.plexinfo.close()
        self._ppv_stack = []
        if getattr(self, "_ppv_return_menu", False) or not self.channels:
            self.renderer.main_menu.show(self._main_menu_select)
        self.renderer.update()

    def _ppv_error(self, msg):
        self.renderer.ppv.set_status(msg)
        self.renderer.mark_dirty()

    def _start_from_playlist(self, pl):
        """Leave the home screen, load the chosen playlist + EPG, and tune in."""
        self._plex_end()
        self.renderer.plexinfo.close()
        self.renderer.menu.close()
        self.config.playlist_url = pl.get("playlist_url", "")
        self.config.epg_url = pl.get("epg_url", "")
        self.config.save()
        self.channels = []
        self.epg = None
        self.renderer.epg = None
        print(f"[cathode] Loading playlist: {pl.get('name')}")
        ok = self._load_playlist_interactive(allow_cancel=True)
        if not ok or not self.channels:
            # Backed out or nothing loaded — stay on the home screen.
            self.renderer.main_menu.show(self._main_menu_select)
            self.renderer.update()
            return
        self.renderer.channels = self.channels
        self._rebuild_categories()
        if self.config.epg_url:
            threading.Thread(target=self._load_epg, daemon=True).start()
        self.renderer.main_menu.close()
        self._tune(self._initial_channel_idx(), initial=True)

    def _theme_submenu(self):
        items = []
        labels = self._builtin_theme_labels()
        for label in labels:
            items.append(MenuItem(label,
                         action=lambda i=label: self._select_theme(i),
                         checked=(self._active_theme == label), close_after=False))
        # User-created themes go below the built-ins (overrides of a built-in
        # name are already shown in place above).
        for name in self.config.custom_themes:
            if name in labels:
                continue
            items.append(MenuItem(name,
                         action=lambda i=name: self._select_theme(i),
                         checked=(self._active_theme == name), close_after=False))
        # "Custom Theme..." (the editor) always stays at the very bottom.
        items.append(MenuItem("Custom Theme...", action=self._open_theme_editor))
        return items

    def _font_submenu(self):
        return [MenuItem(theme.font_label(k),
                         action=lambda key=k: self._apply_font_key(key),
                         checked=(theme.current_font() == k), close_after=False)
                for k in theme.available_fonts()]

    def _profiles_submenu(self):
        items = []
        for name in list(self.BUILTIN_PROFILES) + list(self.config.profiles):
            items.append(MenuItem(name,
                         action=lambda n=name: self._apply_profile(n),
                         back_after=True))
        items.append(MenuItem("-" * 16, enabled=False))
        items.append(MenuItem("Save current as...", action=self._save_profile_dialog,
                              back_after=True))
        items.append(MenuItem("Delete profile...", submenu=self._delete_submenu))
        return items

    def _delete_submenu(self):
        items = [MenuItem(n, action=lambda name=n: self._delete_profile(name),
                          back_after=True)
                 for n in list(self.config.profiles)]
        if not items:
            items.append(MenuItem("(no saved profiles)", enabled=False))
        return items

    # ── Appearance actions (used by menu) ─────────────────────────────────

    # ── Color themes (built-in + user custom) ─────────────────────────────

    def _builtin_theme_labels(self):
        return [theme.theme_label(k) for k in theme.THEME_ORDER]

    def _key_for_label(self, label):
        for k in theme.THEME_ORDER:
            if theme.theme_label(k) == label:
                return k
        return None

    def _migrate_themes(self):
        """Fold legacy config (a single custom_palette / theme key) into the
        custom_themes model."""
        cfg = self.config
        cp = cfg.custom_palette
        if (cfg.theme == "custom" and cp
                and all(k in cp for k in ("bg", "accent", "accent2", "text"))):
            cfg.custom_themes.setdefault("Custom", {
                "bg": list(cp["bg"]), "accent": list(cp["accent"]),
                "accent2": list(cp["accent2"]), "text": list(cp["text"]),
                "scanline": int(cfg.scanline_alpha),
                "crt": bool(cfg.crt_enabled), "vignette": bool(cfg.vignette_enabled)})
            cfg.theme = "Custom"

    def _resolve_initial_theme(self):
        t = self.config.theme
        if t in self.config.custom_themes or t in self._builtin_theme_labels():
            return t
        if t in theme.THEME_ORDER:          # legacy key → label
            return theme.theme_label(t)
        return theme.theme_label("blue")

    def _apply_theme_colors(self, ident):
        """Apply just the palette for `ident` (no config writes / rebuild)."""
        ct = self.config.custom_themes.get(ident)
        if ct:
            theme.set_custom_palette(ct["bg"], ct["accent"], ct["accent2"], ct["text"],
                                     chnum=ct.get("chnum", [40, 255, 90]))
        else:
            theme.apply_theme(self._key_for_label(ident) or "blue")

    def _apply_custom_theme_values(self, t):
        """Apply a custom theme's colors AND its CRT/vignette/scanline effects."""
        theme.set_custom_palette(t["bg"], t["accent"], t["accent2"], t["text"],
                                 chnum=t.get("chnum", [40, 255, 90]))
        self.config.scanline_alpha = int(t.get("scanline", self.config.scanline_alpha))
        self.config.crt_enabled = bool(t.get("crt", self.config.crt_enabled))
        self.config.vignette_enabled = bool(t.get("vignette", self.config.vignette_enabled))
        self.renderer._scanline_alpha = self.config.scanline_alpha
        self.renderer.crt_on = self.config.crt_enabled
        self.renderer.vignette_on = self.config.vignette_enabled
        self.renderer.set_scanline_alpha(self.config.scanline_alpha)

    def _select_theme(self, ident):
        ct = self.config.custom_themes.get(ident)
        if ct:
            self._apply_custom_theme_values(ct)
        else:
            theme.apply_theme(self._key_for_label(ident) or "blue")
        self.config.theme = ident
        self._active_theme = ident
        self.config.save()
        self.renderer.rebuild()
        self.renderer.menu.replace_page(self._theme_submenu())
        self.renderer.update()
        print(f"[cathode] Theme -> {ident}")

    def _theme_from_state(self, state):
        c = state["colors"]
        return {"bg": list(c["bg"]), "accent": list(c["accent"]),
                "accent2": list(c["accent2"]), "text": list(c["text"]),
                "chnum": list(c.get("chnum", [40, 255, 90])),
                "scanline": int(state["scanline"]),
                "crt": bool(state["crt"]), "vignette": bool(state["vignette"])}

    def _apply_font_key(self, key: str):
        if theme.set_font(key):
            self.config.font = key
            self.config.save()
            self.renderer.rebuild()
            self.renderer.menu.replace_page(self._font_submenu())
            self.renderer.update()

    def _apply_profile(self, name: str):
        prof = self.config.profiles.get(name) or self.BUILTIN_PROFILES.get(name)
        if not prof:
            return
        ptheme = prof.get("theme", "blue")
        cp = prof.get("custom_palette")
        if ptheme == "custom" and cp:
            theme.set_custom_palette(cp["bg"], cp["accent"], cp["accent2"], cp["text"])
            self.config.custom_palette = {k: list(v) for k, v in cp.items()}
        else:
            theme.apply_theme(ptheme)
        theme.set_font(prof.get("font", "vcr"))
        sa = int(prof.get("scanline_alpha", self.config.scanline_alpha))
        self._active_theme = (theme.theme_label(ptheme)
                              if ptheme in theme.THEME_ORDER else ptheme)
        self.config.theme = self._active_theme
        self.config.font = prof.get("font", self.config.font)
        self.config.scanline_alpha = sa
        self.renderer._scanline_alpha = sa
        # CRT / vignette toggles (older profiles may not have them — keep current)
        self.config.crt_enabled = bool(prof.get("crt", self.config.crt_enabled))
        self.config.vignette_enabled = bool(prof.get("vignette", self.config.vignette_enabled))
        self.renderer.crt_on = self.config.crt_enabled
        self.renderer.vignette_on = self.config.vignette_enabled
        # Remember a user profile as "active" so the editor's Save can update it.
        self._active_profile = name if name in self.config.profiles else None
        self.config.save()
        self.renderer.rebuild()
        self.renderer.update()
        print(f"[cathode] Applied profile: {name}")

    def _save_profile_dialog(self):
        name = self._osk_get("Profile name", "")
        if not name:
            return
        self.config.profiles[name] = {
            "theme": theme.current_theme(),
            "font": theme.current_font(),
            "scanline_alpha": int(self.config.scanline_alpha),
        }
        self.config.save()
        print(f"[cathode] Saved profile: {name}")

    def _delete_profile(self, name: str):
        if name in self.config.profiles:
            del self.config.profiles[name]
            self.config.save()
            print(f"[cathode] Deleted profile: {name}")

    # ── Custom theme editor ───────────────────────────────────────────────

    def _editor_state_from_current(self):
        """Seed the editor from the active theme's colors + effect settings."""
        ident = self._active_theme
        ct = self.config.custom_themes.get(ident)
        if ct:
            colors = {k: list(ct.get(k, [40, 255, 90]))
                      for k in ("bg", "accent", "accent2", "text", "chnum")}
        else:
            pal = theme.PALETTES.get(theme.current_theme(), theme.PALETTES["blue"])
            colors = {
                "bg":      list(pal["OSD_BG"][:3]),
                "accent":  list(pal["CYAN"][:3]),
                "accent2": list(pal["YELLOW"][:3]),
                "text":    list(pal["WHITE"][:3]),
                "chnum":   list(pal["CHANNEL_GREEN"][:3]),
            }
        return {"colors": colors,
                "scanline": int(self.config.scanline_alpha),
                "crt": bool(self.config.crt_enabled),
                "vignette": bool(self.config.vignette_enabled)}

    def _visual_snapshot(self):
        """Capture the full look state so the editor can revert on cancel."""
        import copy
        return {
            "active": self._active_theme,
            "theme": self.config.theme,
            "custom_themes": copy.deepcopy(self.config.custom_themes),
            "scanline": int(self.config.scanline_alpha),
            "crt": bool(self.config.crt_enabled),
            "vignette": bool(self.config.vignette_enabled),
        }

    def _apply_visual_state(self, s):
        """Re-apply a captured look snapshot to theme + renderer + config."""
        import copy
        self._active_theme = s["active"]
        self.config.theme = s["theme"]
        self.config.custom_themes = copy.deepcopy(s["custom_themes"])
        self.config.scanline_alpha = int(s["scanline"])
        self.config.crt_enabled = bool(s["crt"])
        self.config.vignette_enabled = bool(s["vignette"])
        ct = self.config.custom_themes.get(self._active_theme)
        if ct:
            theme.set_custom_palette(ct["bg"], ct["accent"], ct["accent2"], ct["text"],
                                     chnum=ct.get("chnum", [40, 255, 90]))
        else:
            theme.apply_theme(self._key_for_label(self._active_theme) or "blue")
        self.renderer.crt_on = self.config.crt_enabled
        self.renderer.vignette_on = self.config.vignette_enabled
        self.renderer.set_scanline_alpha(self.config.scanline_alpha)
        self.renderer.rebuild()
        self.renderer.mark_dirty()

    def _open_theme_editor(self):
        self.renderer.menu.close()
        # Snapshot so an un-saved exit reverts to exactly the current look.
        self._editor_revert = self._visual_snapshot()
        self._editor_saved = False
        self.renderer.editor.show(
            self._editor_state_from_current(),
            on_change=self._editor_changed,
            on_action=self._editor_action,
            on_close=self._editor_close,
        )
        self.renderer.update()

    def _editor_changed(self, state):
        """Live preview — rebind colors and flip effect flags without a heavy
        layer rebuild (this runs on an input handler thread)."""
        c = state["colors"]
        theme.set_custom_palette(c["bg"], c["accent"], c["accent2"], c["text"],
                                 chnum=c.get("chnum", [40, 255, 90]))
        self.renderer.crt_on = bool(state["crt"])
        self.renderer.vignette_on = bool(state["vignette"])
        new_alpha = max(0, min(255, int(state["scanline"])))
        if new_alpha != self.renderer._scanline_alpha:
            self.renderer.set_scanline_alpha(new_alpha)
        self.renderer.mark_dirty()

    def _editor_action(self, key: str):
        if key == "save_current":
            self._editor_save_current()
        elif key == "save_new":
            self._editor_save_new()

    def _reopen_theme_menu(self):
        """Close the editor and return to the Color Theme menu."""
        self.renderer.editor.close()
        self.renderer.rebuild()
        self.renderer.menu.open_with(self._theme_submenu(), title="Color Theme")
        self.renderer.update()

    def _editor_save_current(self):
        """Overwrite the currently selected theme's values, keeping its name,
        then return to the Color Theme menu."""
        state = self.renderer.editor.state()
        name = self._active_theme
        self.config.custom_themes[name] = self._theme_from_state(state)
        self.config.theme = name
        self._apply_custom_theme_values(self.config.custom_themes[name])
        self.config.save()
        self._editor_saved = True
        print(f"[cathode] Saved theme '{name}'")
        self._reopen_theme_menu()

    def _editor_save_new(self):
        """Prompt for a name, save a new theme into the Color Theme menu, then
        return to it."""
        state = self.renderer.editor.state()
        name = self._osk_get("New theme name", "")
        if not name:
            return
        self.config.custom_themes[name] = self._theme_from_state(state)
        self.config.theme = name
        self._active_theme = name
        self._apply_custom_theme_values(self.config.custom_themes[name])
        self.config.save()
        self._editor_saved = True
        print(f"[cathode] Saved new theme '{name}'")
        self._reopen_theme_menu()

    def _editor_close(self):
        """Editor dismissed (Close row, X button, Esc, or gamepad back). Revert
        to the pre-editor look unless the user saved."""
        if not getattr(self, "_editor_saved", True):
            self._apply_visual_state(self._editor_revert)
        self.renderer.update()

    def _quit_app(self):
        if self.channels and 0 <= self._ch_idx < len(self.channels):
            self.config.last_channel = self.channels[self._ch_idx].number
        self.config.save()
        self._shutdown()

    def _on_eof(self, reason: str = "eof"):
        """Called by mpv (on the IPC reader thread) when a stream ends. `reason`
        is "eof" (played to the end) or "error" (stream broke). Work is offloaded
        to a thread so the reader is never blocked (which would freeze input)."""
        if self._quit:
            return
        if self.renderer.plex_playing:
            # A stream error mid-playback is NOT a finish: save the resume point
            # and return to the info screen — don't mark the item watched or
            # advance the queue.
            if reason != "eof":
                threading.Thread(target=self._plex_stop, daemon=True).start()
                return
            # Episode queue (Play All / Shuffle): mark the finished episode
            # watched and advance to the next.
            if self._plex_queue and self._plex_queue_pos + 1 < len(self._plex_queue):
                self._plex_report("stopped", finished=True)
                self._cache_offset(self._plex_now_rk, 0)
                self._plex_queue_pos += 1
                nxt = self._plex_queue[self._plex_queue_pos]
                threading.Thread(
                    target=lambda: self._ppv_play(nxt, "", resume=False,
                                                  keep_queue=True),
                    daemon=True).start()
                return
            self._plex_queue = []        # queue exhausted (or single item)
            # Reached the end: mark watched and return to the info screen instead
            # of pausing on a black frame.
            threading.Thread(target=self._plex_finished, daemon=True).start()
            return
        print("[cathode] Stream ended; retrying…")
        if self.channels:
            threading.Thread(target=self._retry_current, daemon=True).start()

    def _retry_current(self):
        time.sleep(2)
        if not self._quit and self.channels:
            self.player.play(self.channels[self._ch_idx].url)

    def _on_osd_resize(self, w: int, h: int):
        """mpv reported its real window size — re-render the UI to match."""
        if self._quit:
            return
        if w == self.renderer.width and h == self.renderer.height:
            return
        print(f"[cathode] Render resolution -> {w}x{h}")
        self.width, self.height = w, h
        self.renderer.resize(w, h)
        self.renderer.update()

    # ── Appearance: live font / theme cycling ─────────────────────────────

    def _shutdown(self):
        self._quit = True
        if self._digit_timer:
            self._digit_timer.cancel()
        if getattr(self, "_gamepad_reader", None):
            self._gamepad_reader.stop()
        self.renderer.stop()
        self.player.terminate()
        # A downloaded update installs now (after we exit), so the next launch
        # runs the new version.
        if self._pending_apply:
            try:
                from . import updater
                updater.spawn_apply(self._pending_apply)
            except Exception:
                pass

    # ── Playlist loading (with first-run / retry prompt) ──────────────────

    def _load_playlist_interactive(self, allow_cancel: bool = False) -> bool:
        """Load the playlist, prompting (via the on-screen keyboard) for a URL
        when none is set, and re-prompting if a URL fails to load.  Returns True
        when channels are loaded.  With allow_cancel, a cancelled prompt returns
        False (so the caller can fall back to the home screen) instead of
        exiting the app."""
        while not self.channels:
            url = self.config.playlist_url
            err = ""
            if url:
                print("[cathode] Loading playlist…")
                try:
                    chans = m3u.load(url, user_agent=self.config.user_agent)
                    if chans:
                        self.channels = chans
                        break
                    err = "playlist has no channels"
                except Exception as e:
                    err = str(e)[:60]
                print(f"[cathode] Could not load playlist: {err}")
            prompt = "Enter M3U playlist URL" + (f"  -  ({err})" if err else "")
            m3u_url = self._osk_get(prompt, url)
            if not m3u_url:
                if allow_cancel:
                    print("[cathode] Playlist entry cancelled.")
                    return False
                print("[cathode] No playlist provided — exiting.")
                sys.exit(1)
            epg_url = self._osk_get(
                "Enter XMLTV EPG URL (optional - press DONE to skip)",
                self.config.epg_url)
            self.config.playlist_url = m3u_url
            if epg_url:
                self.config.epg_url = epg_url
            self.config.save()
        self._ensure_playlist_registered()
        print(f"[cathode] Loaded {len(self.channels)} channels.")
        return True

    def _ensure_playlist_registered(self):
        """Make the active playlist appear in the Playlists menu."""
        url = self.config.playlist_url
        if not url or any(p.get("playlist_url") == url
                          for p in self.config.playlists):
            return
        n = len(self.config.playlists) + 1
        self.config.playlists.append({
            "name": f"Playlist {n}", "playlist_url": url,
            "epg_url": self.config.epg_url or "",
        })
        self.config.save()

    # ── EPG background loader ─────────────────────────────────────────────

    def _load_epg(self):
        print("[cathode] Loading EPG…")
        try:
            epg = EPG()
            epg.load(self.config.epg_url, user_agent=self.config.user_agent)
            self.epg = epg
            self.renderer.epg = epg
            print(f"[cathode] EPG loaded ({len(epg.channel_ids)} channels).")
            self._rebuild_categories()   # refine categories with EPG genres
            self.renderer.update()
        except Exception as e:
            print(f"[cathode] EPG load failed: {e}")
