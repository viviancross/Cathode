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
        "Synthwave":      {"theme": "synth", "font": "pixelforge", "scanline_alpha": 40},
        "Commodore":      {"theme": "c64",   "font": "pixelforge", "scanline_alpha": 40},
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

        # Runtime dir shared with the (sandboxed) mpv for the IPC socket and
        # the overlay buffer.
        if os.name == "nt":
            cache_base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        else:
            cache_base = os.environ.get(
                "XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
        runtime_dir = os.path.join(cache_base, "cathode")
        os.makedirs(runtime_dir, exist_ok=True)
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
            gamepad=config.gamepad,
            ar_delay=config.nav_repeat_delay,
            ar_rate=config.nav_repeat_rate,
        )
        self._fullscreen = fullscreen   # tracked so Esc can exit fullscreen
        self._active_profile = None     # last-applied look profile (for editor "Save")
        self._last_mouse = (0, 0)       # last reported mouse position

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

        # Current channel
        self._ch_idx: int = 0

        # Channel-change sync (static cover held until stream's first frame)
        self._awaiting_playback: bool = False
        self._tune_timeout: Optional[threading.Timer] = None

        self._start_channel = start_channel
        self._quit = False

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

        # Block until mpv exits
        try:
            self.player.wait_for_playback()
        except KeyboardInterrupt:
            pass

        self._shutdown()

    # ── Channel navigation ────────────────────────────────────────────────

    def _tune(self, idx: int, initial: bool = False):
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
        self.renderer.show_volume_osd()
        self.renderer.update()

    # ── Guide ────────────────────────────────────────────────────────────

    def _toggle_guide(self):
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
            self.renderer.menu.back(); self.renderer.mark_dirty(); return
        if self.renderer.main_menu.open:
            return  # home screen has no horizontal navigation
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
            self.renderer.menu.activate(); self._after_menu_action(); return
        if self.renderer.main_menu.open:
            return  # home screen has no horizontal navigation
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

        A physical gamepad is supported two ways: (1) natively via mpv's SDL
        gamepad input (GAMEPAD_* keys, bound below — XInput on Windows), and
        (2) on the Steam Deck in Game Mode, via a Steam Input profile that maps
        controller buttons to the keyboard keys below (SDL gamepad is unreliable
        inside the Flatpak sandbox, so Steam Input is preferred there).
        """
        import string
        p = self.player

        # Letter hotkeys → action when NOT in a dialog (the char router also
        # uses this map). Both cases map to the same action.
        self._hotkey_actions = {
            "g": self._toggle_guide, "i": self._show_info, "m": self._toggle_mute,
            "f": self._toggle_favorite, "c": self._toggle_context_menu,
            "w": self._toggle_fullscreen, "q": self._quit_app,
        }
        for ch, act in list(self._hotkey_actions.items()):
            self._hotkey_actions[ch.upper()] = act

        # Navigation / dialog keys — always active.  Both Enter keys behave the
        # same: press/select the highlighted item (no separate "confirm").
        nav = {
            "UP": self._guide_up, "DOWN": self._guide_down,
            "LEFT": self._guide_left, "RIGHT": self._guide_right,
            "ENTER": self._grid_select, "KP_ENTER": self._grid_select,
            "ESC": self._handle_escape,
            "SPACE": lambda: self._char_typed(" "),
            "MBTN_RIGHT": self._toggle_context_menu, "MBTN_LEFT": self._menu_click,
            "ctrl+v": self._osk_paste, "ctrl+c": self._osk_copy,
        }
        for key, handler in nav.items():
            p.bind_key(key, handler)
        # Backspace deletes a char / backs out a menu — repeatable so holding it
        # chews through a long string in the text-entry dialogs.
        p.bind_key("BS", self._osk_backspace, repeatable=True)

        # Arrow keys are made repeatable on the fly (only while a menu / OSK /
        # editor / guide is open) so a held key cycles items or moves sliders,
        # while staying single-shot for channel / volume changes when watching.
        self._nav_handlers = {"UP": self._guide_up, "DOWN": self._guide_down,
                              "LEFT": self._guide_left, "RIGHT": self._guide_right}
        self._nav_repeat_on = False
        p.on_after_key = self._sync_nav_repeat

        # Non-character hotkeys — ignored while a dialog is open.
        hotkeys = {
            "TAB": self._show_info,
            "PGUP":  lambda: self._tune(max(0, self._ch_idx - 10)),
            "PGDWN": lambda: self._tune(min(len(self.channels) - 1, self._ch_idx + 10)),
            "MBTN_LEFT_DBL": self._toggle_fullscreen,
        }
        for key, handler in hotkeys.items():
            p.bind_key(key, self._guard_hotkey(handler), name=f"hk_{key}")

        # ── Gamepad (mpv SDL / XInput) ────────────────────────────────────
        # D-pad + left stick navigate; A selects/types; B backs out. These
        # reuse the same handlers as the arrow/Enter keys, so they respect the
        # OSK > editor > menu > guide priority automatically (always active).
        gp_nav = {
            "GAMEPAD_DPAD_UP": self._guide_up, "GAMEPAD_DPAD_DOWN": self._guide_down,
            "GAMEPAD_DPAD_LEFT": self._guide_left, "GAMEPAD_DPAD_RIGHT": self._guide_right,
            "GAMEPAD_LEFT_STICK_UP": self._guide_up,
            "GAMEPAD_LEFT_STICK_DOWN": self._guide_down,
            "GAMEPAD_LEFT_STICK_LEFT": self._guide_left,
            "GAMEPAD_LEFT_STICK_RIGHT": self._guide_right,
            "GAMEPAD_ACTION_DOWN": self._grid_select,   # A — select / type key
            "GAMEPAD_ACTION_RIGHT": self._gamepad_back,  # B — back / delete
        }
        for key, handler in gp_nav.items():
            p.bind_key(key, handler, name=f"gp_{key}")

        # Buttons that map to hotkey-style actions — inert while a dialog is up.
        gp_actions = {
            "GAMEPAD_ACTION_LEFT": self._toggle_guide,       # X — guide
            "GAMEPAD_ACTION_UP": self._show_info,            # Y — info bar
            "GAMEPAD_START": self._toggle_guide,             # Start — guide
            "GAMEPAD_BACK": self._toggle_context_menu,       # Back/View — menu
            "GAMEPAD_MENU": self._toggle_context_menu,
            "GAMEPAD_LEFT_SHOULDER": self._channel_down,     # LB — channel -
            "GAMEPAD_RIGHT_SHOULDER": self._channel_up,      # RB — channel +
            "GAMEPAD_LEFT_TRIGGER": self._vol_down,          # LT — volume -
            "GAMEPAD_RIGHT_TRIGGER": self._vol_up,           # RT — volume +
            "GAMEPAD_LEFT_STICK": self._toggle_mute,         # L3 — mute
            "GAMEPAD_RIGHT_STICK": self._toggle_fullscreen,  # R3 — fullscreen
        }
        for key, handler in gp_actions.items():
            p.bind_key(key, self._guard_hotkey(handler), name=f"gp_{key}")

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
                or self.renderer.editor.open or self.renderer.main_menu.open)

    def _nav_context_active(self) -> bool:
        r = self.renderer
        return (r.osk.open or r.menu.open or r.editor.open or r.main_menu.open
                or r.state == UIState.GUIDE_OPEN)

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
        """Esc never quits — it's the failsafe that always gets you out. It
        FULLY closes any open dialog (re-enabling the hotkeys), then dismisses
        guide → OSD → exits fullscreen, in that order.  (Backspace backs out of
        a menu one level at a time; Esc exits the whole thing.)"""
        r = self.renderer
        if r.osk.open:
            r.osk.cancel()      # _osk_get's cancel cb resumes the blocked action
            r.menu.close()      # ensure the menu behind it is gone too
            r.update()
        elif r.editor.open:
            r.editor.close()    # close + revert unsaved changes
            self._editor_close()
        elif r.menu.open:
            r.menu.close()      # exit the entire menu, not just one level
            r.update()
        elif r.state == UIState.GUIDE_OPEN:
            r.close_guide()
            r.update()
        elif r.osd_visible:
            r.hide_osd()
            r.update()
        elif self._fullscreen:
            self._set_fullscreen(False)
        # else: nothing — Esc is not a quit shortcut.

    # ── Fullscreen / context menu / mouse ─────────────────────────────────

    def _set_fullscreen(self, on: bool):
        self._fullscreen = bool(on)
        self.player.set_fullscreen(self._fullscreen)

    def _toggle_fullscreen(self):
        self._set_fullscreen(not self._fullscreen)

    def _toggle_context_menu(self):
        if self.renderer.osk.open:
            return   # don't open the menu over the on-screen keyboard
        m = self.renderer.menu
        if m.open:
            m.close()
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
        # No dialog open: the corner button opens the menu; clicking elsewhere
        # reveals the info bar (and the button) for touch/mouse users.
        x, y = self._last_mouse
        if self.renderer.osd_visible and self.renderer.menu_button_hit(x, y):
            self._toggle_context_menu()
        else:
            self.renderer.show_osd(timeout=self.config.osd_timeout_info)
            self.renderer.update()

    def _osk_backspace(self):
        """Backspace: delete a char in the keyboard, or back out of a menu."""
        if self.renderer.osk.open:
            self.renderer.osk.backspace()
            self.renderer.mark_dirty()
        elif self.renderer.menu.open:
            self.renderer.menu.back()
            self.renderer.mark_dirty()

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
        elif r.state == UIState.GUIDE_OPEN:
            r.close_guide(); r.update()
        elif r.osd_visible:
            r.hide_osd(); r.update()

    def _after_menu_action(self):
        self.renderer.mark_dirty()

    def _on_mouse_pos(self, x: int, y: int):
        # Runs on the IPC reader thread for EVERY mouse move — must stay cheap.
        # Only update hover state and request a coalesced repaint; never render
        # here (that would flood the reader and freeze input).
        self._last_mouse = (x, y)
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
            MenuItem("Info Bar", action=self._show_info, hint="I"),
            MenuItem("Mute", action=self._toggle_mute, hint="M",
                     checked=self.player.muted),
            MenuItem("Remove Favorite" if is_fav else "Add Favorite",
                     action=self._toggle_favorite, hint="F", checked=is_fav),
            MenuItem("Channel Up", action=self._channel_up, hint="[^]"),
            MenuItem("Channel Down", action=self._channel_down, hint="[v]"),
            MenuItem("Volume Up", action=self._vol_up, hint="[>]", close_after=False),
            MenuItem("Volume Down", action=self._vol_down, hint="[<]", close_after=False),
            MenuItem("Fullscreen", action=self._toggle_fullscreen, hint="W",
                     checked=self._fullscreen),
            MenuItem("Themes", submenu=self._themes_submenu),
            MenuItem("Playlists", submenu=self._playlists_submenu),
            MenuItem("Main Menu", action=self._open_main_menu),
            MenuItem("Quit", action=self._quit_app, hint="Q"),
        ]

    def _themes_submenu(self):
        return [
            MenuItem("Color Theme", submenu=self._theme_submenu),
            MenuItem("Font", submenu=self._font_submenu),
            MenuItem("Profiles", submenu=self._profiles_submenu),
            MenuItem("Display", submenu=self._display_submenu),
        ]

    def _display_submenu(self):
        displays = self.player.get_displays()
        items = []
        for i, name in enumerate(displays):
            # close_after=False so picking a display keeps the menu open.
            items.append(MenuItem(name or f"Display {i}",
                         action=lambda idx=i: self._switch_display(idx),
                         close_after=False))
        if not items:
            items.append(MenuItem("(no monitors detected)", enabled=False))
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
        """Return to the home screen (from the context menu)."""
        self.renderer.menu.close()
        self.renderer.main_menu.show(self._main_menu_select)
        self.renderer.update()

    def _main_menu_select(self, key: str):
        if key == "new":
            self._main_new_playlist()
        elif key == "load":
            self._main_load_playlist()
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
        items = [
            MenuItem("Themes", submenu=self._themes_submenu),
            MenuItem("Playlists", submenu=self._playlists_submenu),
            MenuItem("Fullscreen", action=self._toggle_fullscreen,
                     checked=self._fullscreen, close_after=False),
            MenuItem("Quit", action=self._quit_app, hint="Q"),
        ]
        self.renderer.menu.open_with(items, title="OPTIONS")
        self.renderer.mark_dirty()

    def _start_from_playlist(self, pl):
        """Leave the home screen, load the chosen playlist + EPG, and tune in."""
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
                         checked=(self._active_theme == label), back_after=True))
        # User-created themes go below the built-ins (overrides of a built-in
        # name are already shown in place above).
        for name in self.config.custom_themes:
            if name in labels:
                continue
            items.append(MenuItem(name,
                         action=lambda i=name: self._select_theme(i),
                         checked=(self._active_theme == name), back_after=True))
        # "Custom Theme..." (the editor) always stays at the very bottom.
        items.append(MenuItem("Custom Theme...", action=self._open_theme_editor))
        return items

    def _font_submenu(self):
        return [MenuItem(theme.font_label(k),
                         action=lambda key=k: self._apply_font_key(key),
                         checked=(theme.current_font() == k), back_after=True)
                for k in theme.available_fonts()]

    def _profiles_submenu(self):
        items = []
        for name in list(self.BUILTIN_PROFILES) + list(self.config.profiles):
            items.append(MenuItem(name,
                         action=lambda n=name: self._apply_profile(n),
                         back_after=True))
        items.append(MenuItem("-" * 16, enabled=False))
        items.append(MenuItem("Save current as...", action=self._save_profile_dialog))
        items.append(MenuItem("Delete profile...", submenu=self._delete_submenu))
        return items

    def _delete_submenu(self):
        items = [MenuItem(n, action=lambda name=n: self._delete_profile(name))
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

    def _on_eof(self):
        """Called by mpv (on the IPC reader thread) when a stream ends — retry
        the current channel. Done on a separate thread so the 2s wait never
        blocks the reader (which would freeze all input)."""
        print("[cathode] Stream ended; retrying…")
        if not self._quit and self.channels:
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
        self.renderer.stop()
        self.player.terminate()

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
