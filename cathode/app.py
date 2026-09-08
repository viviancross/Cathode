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
from .epg import EPG
from .playlist import Channel
from .ui.renderer import Renderer, UIState, fit_aspect
from .ui import theme
from .ui.menu import MenuItem
from .app_menus import MenusMixin
from .app_plex import PlexMixin


class App(PlexMixin, MenusMixin):
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

    def __init__(
        self,
        config: Config,
        width: int = 1920,
        height: int = 1080,
        fullscreen: bool = True,
        start_channel: Optional[int] = None,
        demo: bool = False,
        mpv_backend: str = "auto",
        connection=None,             # how to reach mpv; see cathode/mpvconn.py
        ui_max_aspect: float = 0.0,  # platform default; config overrides it
        ui_min_aspect: float = 0.0,  # ditto, guarding the portrait end
    ):
        self.config     = config
        # Config wins over the platform's suggestion, so a user who wants the
        # interface edge to edge on a wide screen can still have it.
        self._ui_aspect = float(config.ui_max_aspect or ui_max_aspect or 0.0)
        self._ui_min_aspect = float(config.ui_min_aspect or ui_min_aspect or 0.0)
        self._surface_size = (width, height)   # the whole display
        width, height, ox, oy = fit_aspect(width, height, self._ui_aspect,
                                           self._ui_min_aspect)
        self._ui_origin = (ox, oy)
        self.width      = width       # the UI's size, which may be inset
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
            verbose_log=config.mpv_verbose_log,
            connection=connection,
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
        self._plex_monitor_gen = 0      # bumping it stops any running monitor
        self._plex_osd_until = 0.0
        self._plex_pos = 0.0            # last known playback position (s)
        self._plex_time_base = 0.0      # transcode start offset (mpv clock shift)
        self._plex_now_rk = ""          # ratingKey of the item playing now
        self._plex_info_data = None     # detail dict for the info screen
        self._plex_info_kind = "default"  # button set for the info screen (show/episode/default)
        self._plex_queue = []           # [{rating_key, title, subtitle}] play queue
        self._plex_queue_pos = 0        # index of the item playing now (-1 = none)
        self._plex_queue_user = False   # built by hand, so a one-off play keeps it
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
        # The UI may be drawn into a centred box inside the display; the
        # renderer needs both to place the overlay and to convert the guide's
        # preview box into mpv's surface-relative margins.
        self.renderer.overlay_pos = self._ui_origin
        self.renderer.surface_size = self._surface_size
        self.renderer.crt_on = bool(config.crt_enabled)
        self.renderer.vignette_on = bool(config.vignette_enabled)
        self.renderer.reduce_motion = not bool(config.motion_enabled)

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

        # The DVR: Plex items copied to this device so they survive a flight.
        # Deliberately NOT under runtime_dir — that is a cache, and a cache is
        # something the system is allowed to throw away. downloads.default_dir
        # puts them with the user's other videos (Movies on macOS, the XDG
        # videos dir on Linux, Videos on Windows) rather than in the config
        # folder, which is where the Android port keeps them because app storage
        # there is private anyway.
        from .downloads import DownloadStore, default_dir
        self.downloads = DownloadStore(
            config.download_dir
            or default_dir(os.path.join(config.data_dir() or runtime_dir,
                                        "downloads")),
            on_change=self._on_download_change,
            user_agent=config.user_agent)
        # The index keeps no Plex token, so resuming a download this process
        # never started has to ask the server for a fresh URL.
        self.downloads.refresh_url = self._dvr_source
        self.renderer.ppv.logos = self.renderer.logos        # poster wall tiles
        self.renderer.ppv.view = (config.ppv_view
                                  if config.ppv_view in ("list", "wall") else "list")

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
        self._pending_apply = None           # update apply-script path, run on quit

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
        self.player.set_aspect(self.config.video_aspect)   # reapplied per file

        # Track the mouse so the on-screen menu button and dialogs are clickable.
        self.player.set_mouse_tracking(True)

        # Native gamepad input (XInput on Windows, /dev/input/js* on Linux) —
        # used on every build instead of mpv's SDL gamepad.
        # The button map translates action names to handlers, and the native
        # reader is only one thing that can emit those names. Building it only
        # alongside the reader left _gamepad_action raising AttributeError on
        # every press whenever the reader was switched off.
        self._build_gamepad_buttons()
        self._gamepad_reader = None
        if self.config.gamepad:
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
            self._show_home()
            if not self.config.playlist_url and not self.config.setup_done:
                self._setup_wizard()          # first run ever — offer setup
            self.renderer.update()
            self._sync_nav_repeat()
        else:
            self._start_from_playlist({
                "name": "Configured",
                "playlist_url": self.config.playlist_url,
                "epg_url": self.config.epg_url,
            })

        print("[cathode] Ready.")

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
        if not self.channels:
            return                       # nothing loaded — never divide by zero
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
            self.config.tune_timeout, self._finish_tune, args=(True,),
        )
        self._tune_timeout.daemon = True
        self._tune_timeout.start()

    def _on_playback_started(self):
        """mpv displayed the first frame of the newly-loaded stream."""
        # A frame arriving late (after the timeout) replaces the stand-by card.
        self.renderer.clear_standby()
        self._finish_tune()

    def _finish_tune(self, timed_out: bool = False):
        """Reveal the new channel (fade the static out)."""
        if not self._awaiting_playback:
            return
        self._awaiting_playback = False
        self._cancel_tune_timeout()
        if timed_out:
            # Dead stream: fade the static into a PLEASE STAND BY card
            # instead of dead air. Cleared when a frame finally arrives.
            self.renderer.standby = True
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
        # Guide only makes sense over live TV. "menu" is allowed because the
        # live context menu's own "Program Guide" item runs while it's open.
        if self._focus_owner() not in ("live", "guide", "menu"):
            return
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

    def _guide_up(self):    self._nav_dispatch("up")
    def _guide_down(self):  self._nav_dispatch("down")
    def _guide_left(self):  self._nav_dispatch("left")
    def _guide_right(self): self._nav_dispatch("right")

    def _nav_dispatch(self, d: str):
        """Route a directional press to the screen that owns input focus.
        ONE ladder for all four directions — see _focus_owner()."""
        r = self.renderer
        owner = self._focus_owner()
        if owner == "osk":
            {"up": r.osk.move_up, "down": r.osk.move_down,
             "left": r.osk.move_left, "right": r.osk.move_right}[d]()
            r.mark_dirty()
        elif owner == "editor":
            {"up": r.editor.move_up, "down": r.editor.move_down,
             "left": r.editor.left, "right": r.editor.right}[d]()
            r.mark_dirty()
        elif owner == "menu":
            # Arrows don't navigate the context menu horizontally.
            if d == "up":
                r.menu.move_up(); r.mark_dirty()
            elif d == "down":
                r.menu.move_down(); r.mark_dirty()
        elif owner == "main_menu":
            # Home screen has no horizontal navigation.
            if d == "up":
                r.main_menu.move_up(); r.mark_dirty()
            elif d == "down":
                r.main_menu.move_down(); r.mark_dirty()
        elif owner == "ppv":
            if d == "up":
                r.ppv.move_up()
            elif d == "down":
                r.ppv.move_down()
            else:
                r.ppv.nav_horizontal(-1 if d == "left" else 1)
            r.mark_dirty()
        elif owner == "plexinfo":
            r.plexinfo.move(-1 if d in ("up", "left") else 1)
            r.mark_dirty()
        elif owner == "plex":
            if d in ("up", "down"):
                self._plex_focus(-1 if d == "up" else 1)
            else:
                self._plex_dpad(-1 if d == "left" else 1)
        elif owner == "guide":
            {"up": r.guide.move_up, "down": r.guide.move_down,
             "left": r.guide.move_left, "right": r.guide.move_right}[d]()
            r.update()
        else:   # live
            if d == "up":
                self._channel_up()
            elif d == "down":
                self._channel_down()
            elif d == "left":
                self._vol_down()
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
        r = self.renderer
        owner = self._focus_owner()   # "osk" is handled by _grid_select
        if self._digit_buf and owner in ("live", "guide"):
            # A typed channel number is pending — Enter/A tunes it now
            # instead of waiting out the entry timeout.
            if self._digit_timer:
                self._digit_timer.cancel()
            self._commit_digits()
            return
        if owner == "editor":
            r.editor.press(); r.mark_dirty()
        elif owner == "menu":
            r.menu.activate(); self._after_menu_action()
        elif owner == "main_menu":
            r.main_menu.press()
        elif owner == "ppv":
            self._ppv_select()
        elif owner == "plexinfo":
            self._plex_info_activate()
        elif owner == "plex":
            self._plex_activate()
        elif owner == "guide":
            if r.guide.focus == "category":
                self._open_category_menu()   # scrollable dropdown of categories
                return
            ch = r.guide.selected_channel()
            if ch is None:
                return
            r.close_guide()
            self._tune(self.channels.index(ch))
        elif r.osd_visible:
            # Info bar is up → Enter opens the context menu.
            self._toggle_context_menu()
        else:
            r.show_osd(timeout=self.config.osd_timeout_info)
            r.update()

    def _open_category_menu(self):
        """Scrollable dropdown of the guide's categories (XMLTV genres + All /
        Favorites). Reuses the context menu, which now scrolls long lists."""
        g = self.renderer.guide
        cur = g.current_category()
        items = [MenuItem(c, checked=(c == cur),
                          action=lambda name=c: self._pick_category(name))
                 for c in g.categories]
        self.renderer.menu.open_with(items, title="CATEGORIES")
        self.renderer.mark_dirty()

    def _pick_category(self, name):
        self.renderer.guide.set_category(name)
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

        # Non-character hotkeys. TAB self-guards (context-aware info); the page
        # jumps are live-TV only so they can never yank Plex playback away.
        p.bind_key("TAB", self._show_info, name="hk_TAB")
        p.bind_key("PGUP", self._guard_live(
            lambda: self._tune(max(0, self._ch_idx - 10))), name="hk_PGUP")
        p.bind_key("PGDWN", self._guard_live(
            lambda: self._tune(min(len(self.channels) - 1, self._ch_idx + 10))),
            name="hk_PGDWN")

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

    # Topmost input-focus owner. ONE ordering shared by every dispatcher (nav,
    # select, back, escape, click, hover, wheel) — register new screens here,
    # and give them a branch in each dispatcher plus renderer._render.
    def _focus_owner(self) -> str:
        r = self.renderer
        if r.osk.open:
            return "osk"
        if r.editor.open:
            return "editor"
        if r.menu.open:
            return "menu"
        if r.main_menu.open:
            return "main_menu"
        if r.ppv.open:
            return "ppv"
        if r.plexinfo.open:
            return "plexinfo"
        if r.plex_playing:
            return "plex"
        if r.state == UIState.GUIDE_OPEN:
            return "guide"
        return "live"

    _DIALOG_OWNERS = frozenset(
        {"osk", "editor", "menu", "main_menu", "ppv", "plexinfo"})

    def _dialog_open(self) -> bool:
        return self._focus_owner() in self._DIALOG_OWNERS

    def _nav_context_active(self) -> bool:
        return self._focus_owner() != "live"

    def _set_input_mode(self, mode):
        """Track the active input device so the on-screen hints match it."""
        if mode == self._input_mode:
            return
        self._input_mode = mode
        self.renderer.input_mode = mode
        self.renderer.ppv.input_mode = mode
        self.renderer.osk.input_mode = mode
        self.renderer.mark_dirty()

    def _after_key(self):
        """Runs after every keyboard/mouse key handler (player.on_after_key)."""
        self._set_input_mode("key")
        self._sync_nav_repeat()

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

    def _guard_live(self, fn):
        """Wrap a hotkey so it only runs over live TV (or the guide) — never
        during Plex playback or inside another screen."""
        def wrapped():
            if self._focus_owner() in ("live", "guide"):
                fn()
        return wrapped

    def _char_typed(self, ch: str):
        """A printable key: type into the on-screen keyboard, else act normally."""
        owner = self._focus_owner()
        if owner == "osk":
            self.renderer.osk.insert(ch)
            self.renderer.mark_dirty()
            return
        if owner in ("menu", "editor", "main_menu"):
            return
        act = self._hotkey_actions.get(ch)
        if act:
            act()
        elif ch.isdigit() and owner in ("live", "guide"):
            # Direct channel entry belongs to live TV only — a digit typed over
            # Plex playback or the browse screens must never retune.
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
        owner = self._focus_owner()
        if owner == "plex":
            self._plex_show_osd()   # info during Plex playback = the Plex bar
            return
        if owner != "live":
            return
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
        owner = self._focus_owner()
        if owner == "osk":
            r.osk.cancel()      # _osk_get's cancel cb resumes the blocked action
            r.menu.close()      # ensure the menu behind it is gone too
            r.update()
        elif owner == "editor":
            r.editor.close()    # close + revert unsaved changes
            self._editor_close()
        elif owner == "menu":
            r.menu.back()       # back out one submenu level (closes at the root)
            r.update()
        elif owner == "ppv":
            self._ppv_back()        # one level (exits PPV only at the root)
        elif owner == "plexinfo":
            self._plex_info_back()
        elif owner == "plex":
            if r.plexosd.scrubbing or r.plexosd.adjusting:
                r.plexosd.scrubbing = False
                r.plexosd.adjusting = False
                self._plex_show_osd()
            elif r.plexosd.visible:
                r.plexosd.hide(); r.mark_dirty()   # back closes the OSD bar
            else:
                self._confirm_leave_plex()
        elif owner == "guide":
            r.close_guide()
            r.update()
        elif r.osd_visible:
            r.hide_osd()
            r.update()
        elif (self.channels and owner == "live"
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
        if self._focus_owner() in ("menu", "osk", "editor", "ppv",
                                   "plexinfo", "main_menu", "guide"):
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
        r = self.renderer
        x, y = self._last_mouse
        owner = self._focus_owner()
        if owner == "osk":
            r.osk.click(x, y)
            r.mark_dirty()
        elif owner == "editor":
            r.editor.click(x, y)
            r.mark_dirty()
        elif owner == "menu":
            if r.menu.hit_test(x, y) is None:
                # Clicked outside the menu panel → dismiss, back to the video.
                r.menu.close()
                r.mark_dirty()
            else:
                # Activate exactly the item under the cursor (not a stale one).
                r.menu.set_hover(x, y)
                r.menu.activate()
                self._after_menu_action()
        elif owner == "main_menu":
            if r.main_menu.hit_logo(x, y):
                r.degauss()          # CRT degauss easter egg
                return
            r.main_menu.click(x, y)
            r.mark_dirty()
        elif owner == "ppv":
            if r.ppv.hit_back(x, y):
                self._ppv_back()
                return
            if r.ppv.hit_menu(x, y):
                self._toggle_context_menu()
                return
            i = r.ppv.hit_test(x, y)
            if i is not None:
                r.ppv.bar_focus = None   # clicking a row leaves the bar
                r.ppv.sel = i
                self._ppv_select()
        elif owner == "plexinfo":
            i = r.plexinfo.hit_test(x, y)
            if i is not None:
                r.plexinfo.focus = i
                self._plex_info_activate()
        elif owner == "plex":
            name = r.plexosd.hit_test(x, y)
            if r.plexosd.visible and name:
                self._plex_click(name, x)
            else:
                self._plex_show_osd()
        elif owner == "guide":
            # Clicking the category bar opens the category dropdown.
            bx0, by0, bx1, by1 = r.guide.category_bar_px()
            if bx0 <= x <= bx1 and by0 <= y <= by1:
                r.guide.focus = "category"
                self._open_category_menu()
        # Live TV: the corner button opens the menu; clicking elsewhere reveals
        # the info bar (and the button) for touch/mouse users.
        elif r.osd_visible and r.menu_button_hit(x, y):
            self._toggle_context_menu()
        else:
            r.show_osd(timeout=self.config.osd_timeout_info)
            r.update()

    def _gamepad_back(self):
        """B button: context-aware step back — delete a char / leave a sub-menu /
        close the editor / close the guide / hide the info bar."""
        r = self.renderer
        owner = self._focus_owner()
        if owner == "osk":
            r.osk.backspace(); r.mark_dirty()
        elif owner == "editor":
            r.editor.close(); self._editor_close()
        elif owner == "menu":
            r.menu.back(); r.mark_dirty()
        elif owner == "ppv":
            self._ppv_back()
        elif owner == "plexinfo":
            self._plex_info_back()
        elif owner == "plex":
            if r.plexosd.scrubbing or r.plexosd.adjusting:
                r.plexosd.scrubbing = False
                r.plexosd.adjusting = False
                self._plex_show_osd()
            elif r.plexosd.visible:
                r.plexosd.hide(); r.mark_dirty()
            else:
                self._confirm_leave_plex()
        elif owner == "guide":
            r.close_guide(); r.update()
        elif r.osd_visible:
            r.hide_osd(); r.update()
        elif (self.channels and owner == "live"
              and r.state == UIState.WATCHING):
            self._confirm_leave_live()

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
        # Bumpers move the text caret while the on-screen keyboard is open
        # (physical LB/RB, regardless of any channel-up/down remap).
        if self.renderer.osk.open and name in ("lb", "rb"):
            (self.renderer.osk.cursor_left if name == "lb"
             else self.renderer.osk.cursor_right)()
            self.renderer.mark_dirty()
            return
        if is_repeat:
            return
        fn = self._gamepad_buttons.get(name)
        if fn:
            fn()

    def _wheel(self, delta):
        r = self.renderer
        owner = self._focus_owner()
        if owner == "menu":
            r.menu.move(delta); r.mark_dirty()
        elif owner == "main_menu":
            (r.main_menu.move_down if delta > 0 else r.main_menu.move_up)()
            r.mark_dirty()
        elif owner == "ppv":
            r.ppv.scroll(delta); r.mark_dirty()
        elif owner == "guide":
            for _ in range(abs(delta)):
                (r.guide.move_down if delta > 0 else r.guide.move_up)()
            r.update()
        elif owner == "live":
            # Channel surf — ONLY over live TV. Every other owner (OSK, editor,
            # Plex screens) ignores the wheel rather than yanking the tuner.
            (self._channel_up if delta < 0 else self._channel_down)()

    def _wheel_up(self):
        self._wheel(-1)

    def _wheel_down(self):
        self._wheel(1)

    def _lb_action(self):
        owner = self._focus_owner()
        if owner == "plex":
            self._plex_skip(-1)           # Plex playback: prev episode/chapter
        elif owner == "ppv":
            self.renderer.ppv.scroll(-10); self.renderer.mark_dirty()
        elif owner in ("live", "guide"):
            self._channel_down()
        # dialogs (menu/OSK/editor/...): bumpers do nothing

    def _rb_action(self):
        owner = self._focus_owner()
        if owner == "plex":
            self._plex_skip(1)            # Plex playback: next episode/chapter
        elif owner == "ppv":
            self.renderer.ppv.scroll(10); self.renderer.mark_dirty()
        elif owner in ("live", "guide"):
            self._channel_up()

    def _lt_action(self):
        if self.renderer.plex_playing:
            self._plex_seek(-10)          # Plex playback: jump back 10s
        else:
            self._vol_down()

    def _rt_action(self):
        if self.renderer.plex_playing:
            self._plex_seek(10)           # Plex playback: jump forward 10s
        else:
            self._vol_up()

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
        ("channel_up",   "Ch Up / Next / Scroll",   "", "rb"),
        ("channel_down", "Ch Down / Prev / Scroll", "", "lb"),
        ("vol_up",       "Vol Up / Seek +10s",   "", "rt"),
        ("vol_down",     "Vol Down / Seek -10s", "", "lt"),
        ("aspect",       "Aspect Ratio",  "", "r3"),
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
            "vol_up": self._rt_action, "vol_down": self._lt_action,
            "aspect": self._cycle_aspect,
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
        # channel up/down scroll-guard themselves; aspect is global (works in any
        # context).  Guard the rest so they no-op while a dialog is selected.
        unguarded = {"channel_up", "channel_down", "aspect"}
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
        #
        # Pointer coordinates arrive in the display's space. The UI may be drawn
        # into a centred box inside that, so shift them into the UI's space or
        # every hit test is off by the margin.
        ox, oy = self._ui_origin
        x, y = x - ox, y - oy
        self._last_mouse = (x, y)
        self._set_input_mode("key")
        r = self.renderer
        owner = self._focus_owner()
        if owner == "osk":
            r.osk.set_hover(x, y)
            r.mark_dirty()
        elif owner == "editor":
            r.editor.set_hover(x, y)
            r.mark_dirty()
        elif owner == "menu":
            r.menu.set_hover(x, y)
            r.mark_dirty()
        elif owner == "main_menu":
            r.main_menu.set_hover(x, y)
            r.mark_dirty()
        elif owner == "ppv":
            pass  # mouse movement does NOT change the PPV highlight; use the
                  # wheel to scroll, click to activate
        elif owner == "plexinfo":
            r.plexinfo.set_hover(x, y)
            r.mark_dirty()
        elif owner == "plex":
            r.plexosd.set_hover(x, y)
            self._plex_show_osd()
        else:
            over = r.osd_visible and r.menu_button_hit(x, y)
            if over != r._menu_btn_hover:
                r._menu_btn_hover = over
                r.mark_dirty()

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

    def _confirm_notice(self, title: str, message: str):
        """Show a modal notice the user must acknowledge, and BLOCK until they
        press OK.  Used so a playlist failure is seen before the entry prompts
        reappear.  Safe from a handler thread (input runs on the reader thread)."""
        ev = threading.Event()
        items = [
            MenuItem(message, enabled=False),
            MenuItem("OK", action=ev.set),
        ]
        self.renderer.menu.open_with(items, title=title)
        self.renderer.update()
        self._sync_nav_repeat()
        ev.wait()
        self.renderer.menu.close()
        self._sync_nav_repeat()
        self.renderer.update()

    def _confirm_yesno(self, title: str, message: str,
                       yes: str = "Yes", no: str = "No") -> bool:
        """Modal yes/no the user must answer; BLOCKS until they pick. Returns
        True for yes.  Safe from a handler thread (input runs on the reader)."""
        ev = threading.Event()
        res = {"v": False}

        def pick(v):
            res["v"] = v
            ev.set()

        items = [
            MenuItem(message, enabled=False),
            MenuItem(yes, action=lambda: pick(True)),
            MenuItem(no, action=lambda: pick(False)),
        ]
        self.renderer.menu.open_with(items, title=title)
        self.renderer.update()
        self._sync_nav_repeat()
        ev.wait()
        self.renderer.menu.close()
        self._sync_nav_repeat()
        self.renderer.update()
        return res["v"]

    # ── Main menu / home screen ───────────────────────────────────────────

    def _show_home(self):
        """Show the home screen; with no playlist configured it grows a
        'Demo Channels' button plus a first-run hint line."""
        self.renderer.main_menu.demo_hint = not self.config.playlist_url
        self.renderer.main_menu.show(self._main_menu_select)

    def _open_main_menu(self):
        """Return to the home screen (from the context menu / leave prompt)."""
        self._plex_end()
        self.player.stop()       # stop live TV too — home screen is not playback
        self.renderer.plexinfo.close()
        self.renderer.ppv.close()
        self.renderer.menu.close()
        self._show_home()
        self.renderer.update()

    def _main_menu_select(self, key: str):
        if key == "new":
            self._main_new_playlist()
        elif key == "load":
            self._main_load_playlist()
        elif key == "demo":
            self._start_demo()
        elif key == "plex":
            self._open_ppv()
        elif key == "options":
            self._main_options()
        elif key == "exit":
            self._quit_app()

    def _start_demo(self):
        """Load the built-in test-pattern channels from the home screen (same
        set as the --demo flag) so a fresh install has something to play."""
        from . import demo
        self.channels = demo.build_channels(self.width, self.height)
        self.epg = demo.build_epg(self.channels)
        self.renderer.channels = self.channels
        self.renderer.epg = self.epg
        self._rebuild_categories()
        self.renderer.main_menu.close()
        self._tune(self._initial_channel_idx(), initial=True)

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
        ok = self._load_playlist_interactive()
        if not ok or not self.channels:
            # Backed out or nothing loaded — stay on the home screen.
            self._show_home()
            self.renderer.update()
            return
        self.renderer.channels = self.channels
        self._rebuild_categories()
        if self.config.epg_url:
            threading.Thread(target=self._load_epg, daemon=True).start()
        self.renderer.main_menu.close()
        self._tune(self._initial_channel_idx(), initial=True)

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
                nxt = self._plex_queue_pos + 1
                threading.Thread(
                    target=lambda: self._plex_play_queue_at(nxt),
                    daemon=True).start()
                return
            self._plex_queue = []        # queue exhausted (or single item)
            self._plex_queue_user = False
            self._plex_queue_pos = 0
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
        # mpv reports the whole surface; the UI may be drawn into a narrower
        # box inside it, so fit before comparing or resizing.
        surface = (w, h)
        w, h, ox, oy = fit_aspect(w, h, self._ui_aspect, self._ui_min_aspect)
        if w == self.renderer.width and h == self.renderer.height:
            return
        print(f"[cathode] Render resolution -> {w}x{h}")
        self.width, self.height = w, h
        self._surface_size = surface
        self._ui_origin = (ox, oy)
        self.renderer.overlay_pos = (ox, oy)
        self.renderer.surface_size = surface
        self.renderer.resize(w, h)
        self.renderer.update()

    # ── Appearance: live font / theme cycling ─────────────────────────────

    def _shutdown(self):
        self._quit = True
        if self._digit_timer:
            self._digit_timer.cancel()
        if getattr(self, "_gamepad_reader", None):
            self._gamepad_reader.stop()
        # The tube goes dark before the overlay is torn down and mpv is killed —
        # after this point there is no surface left to draw the collapse on.
        self.renderer.power_off()
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

    def _load_playlist_interactive(self) -> bool:
        """Load the playlist, prompting (via the on-screen keyboard) for a URL
        when none is set, and re-prompting if a URL fails to load.  Returns True
        when channels are loaded, False if the user cancels the prompt (callers
        fall back to the home screen — never exit; sys.exit from a handler
        thread only kills that thread anyway)."""
        while not self.channels:
            url = self.config.playlist_url
            err = ""
            if url:
                print("[cathode] Loading playlist…")
                self.renderer.show_notification("Loading playlist...", 120.0)
                try:
                    chans = m3u.load(url, user_agent=self.config.user_agent)
                    if chans:
                        self.channels = chans
                        self.renderer.clear_notification()
                        break
                    err = "playlist has no channels"
                except Exception as e:
                    err = str(e)[:120]
                self.renderer.clear_notification()
                print(f"[cathode] Could not load playlist: {err}")
                # Make the user acknowledge the failure before re-prompting.
                self._confirm_notice("PLAYLIST FAILED",
                                     f"Couldn't load playlist: {err}")
            m3u_url = self._osk_get("Enter M3U playlist URL", url)
            if not m3u_url:
                print("[cathode] Playlist entry cancelled.")
                return False
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
