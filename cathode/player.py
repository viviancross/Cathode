"""MPV player, driven entirely by mpv's JSON command protocol:

    {"command": ["loadfile", url, "replace"]}\n
    {"command": ["overlay-add", ...]}\n

This module knows that vocabulary and nothing about how mpv is reached.  A
connection object supplies the transport — see `cathode/mpvconn.py`, which
launches mpv as a subprocess (on Steam Deck / SteamOS the root filesystem is
read-only and libmpv isn't available to a system Python process, so the desktop
builds can't link libmpv in-process).  A platform that *can* embed libmpv
supplies its own connection and everything here is unchanged.

Key presses are handled by binding keys in mpv to a `script-message
cathode-key <name>` command; mpv echoes these back as `client-message` events
which we dispatch to Python callbacks.  `bind_key` keeps its own handler
registry, so a platform that delivers input itself can call those handlers
directly instead.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from typing import Callable, Dict, List, Optional


class Player:
    def __init__(
        self,
        runtime_dir: str,
        width: int = 1920,
        height: int = 1080,
        fullscreen: bool = True,
        user_agent: str = "Cathode/1.0",
        on_eof: Optional[Callable] = None,
        on_resize: Optional[Callable] = None,
        on_playback_started: Optional[Callable] = None,
        on_mouse_pos: Optional[Callable] = None,
        mpv_command: Optional[List[str]] = None,
        flatpak_app: str = "io.mpv.Mpv",
        backend: str = "auto",   # "auto" | "flatpak" | "system"
        extra_args: Optional[List[str]] = None,
        mpv_path: str = "",      # explicit path to mpv(.exe), optional
        ar_delay: int = 300,     # ms before a held key repeats
        ar_rate: int = 8,        # held-key repeats per second
        verbose_log: bool = False,   # mpv --msg-level=all=v (large log files)
        connection=None,         # how to reach mpv; see cathode/mpvconn.py
    ):
        self.width = width
        self.height = height
        self.fullscreen = fullscreen
        self.user_agent = user_agent
        self._on_eof = on_eof
        self._on_resize = on_resize
        self._on_playback_started = on_playback_started
        self._on_mouse_pos = on_mouse_pos
        self._osd_w = 0
        self._osd_h = 0
        self._extra_args = list(extra_args or [])
        self._ar_delay = int(ar_delay)
        self._ar_rate = int(ar_rate)
        self._verbose_log = bool(verbose_log)
        self._mpv_log = os.path.join(runtime_dir, "mpv.log")

        os.makedirs(runtime_dir, exist_ok=True)
        self._runtime_dir = runtime_dir

        # How mpv is reached. The default runs it as a child process; an
        # in-process libmpv connection implements the same three methods and
        # nothing below this line changes.
        if connection is None:
            from .mpvconn import SubprocessConnection
            connection = SubprocessConnection(
                runtime_dir, flatpak_app=flatpak_app, backend=backend,
                mpv_path=mpv_path or "", mpv_command=mpv_command,
                mpv_log=self._mpv_log,
            )
        self._conn = connection

        # Local cached state (avoids async IPC round-trips for the UI)
        self._volume = 80
        self._muted = False
        self._paused = False

        # Key dispatch
        self._key_handlers: Dict[str, Callable] = {}
        self.on_after_key: Optional[Callable] = None   # post-handler hook
        self._req_id = 0
        self._pending: Dict[int, list] = {}   # request_id -> [Event, data]
        self._pending_lock = threading.Lock()

        # Transport to mpv, handed over by the connection once it's up.
        self._transport = None
        self._running = False
        self._exited = threading.Event()
        self._resume_to = None          # one-shot seek (s) applied on next load
        self._unpause_on_start = False  # force play on next file load (keep-open)
        self._aspect = "Original"       # video aspect mode, reapplied per file

    # ── Launch / connect ───────────────────────────────────────────────────

    def _common_args(self) -> List[str]:
        # mpv options only — how mpv is reached (the IPC endpoint, the Flatpak
        # wrapper, the executable) belongs to the connection, not here.
        args = [
            "--no-config",
            "--idle=yes",
            "--force-window=yes",
            "--keep-open=yes",
            "--osd-level=0",
            # Keep mpv's OSC loaded but hidden ("never"); a hotkey toggles it on
            # demand without it ever auto-popping over our own UI.
            "--osc=yes",
            "--script-opts=osc-visibility=never",
            "--osd-bar=no",
            "--input-default-bindings=no",
            "--input-vo-keyboard=yes",
            # Cap held-key auto-repeat so menu / guide scrolling is followable.
            f"--input-ar-delay={self._ar_delay}",
            f"--input-ar-rate={self._ar_rate}",
            "--cursor-autohide=200",  # hide the mouse pointer quickly
            "--cursor-autohide-fs-only=no",
            "--vo=gpu",
            "--hwdec=auto-safe",
            # Deinterlace only frames flagged interlaced (480i etc.); progressive
            # content passes through untouched.
            "--vf=bwdif=deint=1",
            f"--volume={self._volume}",
            f"--user-agent={self.user_agent}",
            f"--geometry={self.width}x{self.height}",
            "--title=Cathode",
            "--cache=yes",
            "--demuxer-max-bytes=64MiB",
            # Log to a file — invaluable for diagnosing Game Mode video problems
            # where there's no terminal to read. Verbose only on request: an
            # all=v log grows unbounded over hours of playback.
            f"--log-file={self._mpv_log}",
            "--msg-level=all=v" if self._verbose_log else "--msg-level=all=info",
        ]
        args.append("--fullscreen=yes" if self.fullscreen else "--fullscreen=no")
        # Make Cathode's bundled fonts available to the subtitle renderer so the
        # subtitle-font picker can use them.
        try:
            from .ui import theme
            fdir = theme.fonts_dir()
            if fdir:
                args.append(f"--sub-fonts-dir={fdir}")
        except Exception:
            pass
        # X11 + the default GLX context can paint a black wedge over half the
        # video on some drivers; the EGL backend avoids it. Only under X11.
        if (sys.platform.startswith("linux") and os.environ.get("DISPLAY")
                and not os.environ.get("WAYLAND_DISPLAY")):
            args.append("--gpu-context=x11egl")
        # NB: mpv's own SDL gamepad input is intentionally NOT used — the app
        # has a native gamepad reader (cathode/gamepad.py) that works on every
        # mpv build (incl. the SDL-less Flatpak mpv), so we never pass
        # --input-gamepad (which is a fatal unknown option on those builds).
        # User-supplied extra args last so they can override anything above.
        args.extend(self._extra_args)
        return args

    def start(self):
        """Get mpv running and start reading from it."""
        self._transport = self._conn.connect(self._common_args())

        self._running = True
        threading.Thread(target=self._reader, daemon=True).start()

        # Observe end-of-file so we can retry streams
        self._send({"command": ["observe_property", 1, "eof-reached"]})
        # Observe the real OSD/window dimensions so the UI can render at the
        # correct resolution (handheld 1280x800 vs docked 1920x1080).
        self._send({"command": ["observe_property", 2, "osd-width"]})
        self._send({"command": ["observe_property", 3, "osd-height"]})

    # ── IPC plumbing ───────────────────────────────────────────────────────

    def _send(self, obj: dict):
        if not self._transport:
            return
        try:
            self._transport.send((json.dumps(obj) + "\n").encode("utf-8"))
        except (OSError, ValueError):
            pass

    def command(self, *args):
        """Send an arbitrary mpv command (used by the overlay renderer)."""
        self._send({"command": list(args)})

    def _set_property(self, name: str, value):
        self._send({"command": ["set_property", name, value]})

    def _reader(self):
        """Run the transport's read loop, then mark the player as exited."""
        try:
            self._transport.serve(self._on_line)
        finally:
            self._ipc_closed()

    def _on_line(self, line: bytes):
        """Handle one JSON line from mpv (called by the transport's reader)."""
        line = line.strip()
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return
        # Reply to a command we sent (e.g. get_property) — resolve the waiter.
        if "request_id" in msg and "event" not in msg:
            with self._pending_lock:
                pend = self._pending.get(msg["request_id"])
            if pend is not None:
                pend[1] = msg.get("data")
                pend[0].set()
            return
        self._handle_event(msg)

    def get_property(self, name: str, timeout: float = 0.6):
        """Synchronously read an mpv property over IPC. Returns None on
        timeout / error. Safe to call from any non-reader thread."""
        if not self._transport:
            return None
        self._req_id += 1
        rid = self._req_id
        ev = threading.Event()
        with self._pending_lock:
            self._pending[rid] = [ev, None]
        self._send({"command": ["get_property", name], "request_id": rid})
        got = ev.wait(timeout)
        with self._pending_lock:
            data = self._pending.pop(rid, [None, None])[1]
        return data if got else None

    def get_clipboard(self):
        """The system clipboard text, via mpv's native clipboard (Windows /
        Wayland / macOS). Returns None if unsupported/empty."""
        val = self.get_property("clipboard/text")
        return val if isinstance(val, str) else None

    def set_clipboard(self, text: str):
        self._set_property("clipboard/text", text)

    def get_displays(self) -> List[str]:
        """All connected monitors (not just the one the window is on).  mpv's
        `display-names` only reports the displays the window currently spans, so
        enumerate via the OS and fall back to mpv only if that fails."""
        names = self._enumerate_monitors()
        if names:
            return names
        val = self.get_property("display-names")
        return val if isinstance(val, list) else []

    def _enumerate_monitors(self) -> List[str]:
        try:
            if os.name == "nt":
                import ctypes
                n = ctypes.windll.user32.GetSystemMetrics(80)  # SM_CMONITORS
                if n and n > 0:
                    return [f"Display {i + 1}" for i in range(n)]
            else:
                import subprocess
                out = subprocess.run(["xrandr", "--listmonitors"],
                                     capture_output=True, text=True, timeout=2)
                lines = [l for l in out.stdout.splitlines() if l.strip()]
                if lines and lines[0].lower().startswith("monitors:"):
                    names = [l.split()[-1] for l in lines[1:] if l.split()]
                    if names:
                        return names
        except Exception:
            pass
        return []

    def set_display(self, index: int):
        """Target a monitor by index for both windowed and fullscreen."""
        self._set_property("fs-screen", index)
        self._set_property("screen", index)

    def move_window_to_screen(self, index: int):
        """Relocate a *windowed* window onto monitor `index`.  `screen` alone
        doesn't move an already-open window, so also set `geometry` (which is
        evaluated relative to `screen`) to re-place it centered on that screen."""
        self._set_property("screen", index)
        # Centered position on the target screen; keeps the current size.
        self._set_property("geometry", "50%:50%")

    def _ipc_closed(self):
        """Transport signalled the connection is gone (mpv exited)."""
        self._running = False
        self._exited.set()

    def _handle_event(self, msg: dict):
        event = msg.get("event")
        if event == "client-message":
            args = msg.get("args", [])
            if len(args) >= 2 and args[0] == "cathode-key":
                name = args[1]
                handler = self._key_handlers.get(name)
                if handler:
                    # Run handlers off the reader thread so a slow handler
                    # (channel change) doesn't stall IPC reads.  After each
                    # handler, fire on_after_key so the app can re-sync state
                    # (e.g. enable/disable key-repeat for the current UI mode).
                    def _run(h=handler):
                        try:
                            h()
                        finally:
                            if self.on_after_key:
                                self.on_after_key()
                    threading.Thread(target=_run, daemon=True).start()
        elif event == "playback-restart":
            # First frame of a newly-loaded file is now on screen.
            if self._resume_to is not None:
                t, self._resume_to = self._resume_to, None
                self._send({"command": ["seek", t, "absolute"]})
            if getattr(self, "_unpause_on_start", False):
                self._unpause_on_start = False
                self._paused = False
                self._set_property("pause", False)
            self._apply_aspect()       # reassert aspect on the freshly loaded file
            if self._on_playback_started:
                self._on_playback_started()
        elif event == "end-file":
            reason = msg.get("reason", "")
            if reason in ("eof", "error") and self._on_eof:
                self._on_eof(reason)
        elif event == "property-change":
            name = msg.get("name")
            if name == "eof-reached" and msg.get("data") is True:
                if self._on_eof:
                    self._on_eof("eof")
            elif name == "osd-width":
                self._osd_w = msg.get("data") or 0
                self._maybe_resize()
            elif name == "osd-height":
                self._osd_h = msg.get("data") or 0
                self._maybe_resize()
            elif name == "mouse-pos":
                data = msg.get("data") or {}
                if self._on_mouse_pos and isinstance(data, dict):
                    x, y = data.get("x"), data.get("y")
                    if x is not None and y is not None:
                        self._on_mouse_pos(int(x), int(y))

    def _maybe_resize(self):
        w, h = self._osd_w, self._osd_h
        if w and h and self._on_resize:
            self._on_resize(int(w), int(h))

    # ── Key binding ────────────────────────────────────────────────────────

    def bind_key(self, key: str, handler: Callable, name: Optional[str] = None,
                 repeatable: bool = False):
        """Bind an mpv key to a Python callback via script-message round-trip.

        With repeatable=True the binding fires repeatedly while the key is held
        (mpv's `repeatable` command prefix) — used so Backspace can chew through
        a long string when held down."""
        name = name or f"k_{key.replace('+', '_')}"
        self._key_handlers[name] = handler
        prefix = "repeatable " if repeatable else ""
        self._send({"command": ["keybind", key,
                                f"{prefix}script-message cathode-key {name}"]})

    # ── Playback ───────────────────────────────────────────────────────────

    def play(self, url: str, start: float = 0, headers: Optional[dict] = None):
        # `start` (seconds) resumes mid-file; applied once the file loads.
        self._resume_to = float(start) if start and start > 0 else None
        # A fresh load must always play: --keep-open pauses mpv at the previous
        # file's EOF, and that pause=yes would otherwise carry into this one.
        self._unpause_on_start = True
        self._paused = False
        # Per-request HTTP headers (e.g. Plex auth token) — kept out of the URL
        # so the token never lands in mpv's logs. ALWAYS set the property (empty
        # to clear) so a Plex token can't leak onto the next live-TV stream.
        self._set_property(
            "http-header-fields",
            [f"{k}: {v}" for k, v in headers.items()] if headers else [])
        self._send({"command": ["loadfile", url, "replace"]})

    def stop(self):
        self._send({"command": ["stop"]})

    def seek(self, seconds: float, mode: str = "relative"):
        self._send({"command": ["seek", seconds, mode]})

    def chapter_skip(self, delta: int):
        """Jump +/- chapters (no-op in mpv if the file has none)."""
        self._send({"command": ["add", "chapter", int(delta)]})

    # ── audio / subtitle tracks + styling ────────────────────────────────

    def get_tracks(self) -> dict:
        """Current file's audio + subtitle tracks: {'audio': [...], 'sub': [...]}."""
        tl = self.get_property("track-list") or []
        out = {"audio": [], "sub": []}
        for t in tl:
            typ = t.get("type")
            if typ in ("audio", "sub"):
                out[typ].append({
                    "id": t.get("id"),
                    "title": t.get("title") or "",
                    "lang": t.get("lang") or "",
                    "selected": bool(t.get("selected")),
                })
        return out

    def set_audio_track(self, tid):
        self._set_property("aid", tid)

    def set_sub_track(self, tid):
        self._set_property("sid", tid)

    def get_audio_devices(self) -> list:
        dl = self.get_property("audio-device-list") or []
        return [{"name": d.get("name"),
                 "desc": d.get("description") or d.get("name")} for d in dl]

    def set_audio_device(self, name):
        self._set_property("audio-device", name or "auto")

    def apply_sub_style(self, font=None, size=None, color=None, back=None):
        if font:
            self._set_property("sub-font", font)
            self._set_property("sub-ass-override", "force")   # apply to ASS subs too
        if size:
            self._set_property("sub-font-size", size)
        if color:
            self._set_property("sub-color", color)
        if back is not None:
            # back="" clears the box; a color enables it. Newer mpv needs
            # sub-border-style=background-box for sub-back-color to show; on
            # older builds the unknown property is a harmless IPC error and
            # the back-color's alpha alone draws the box.
            if back:
                self._set_property("sub-back-color", back)
                self._set_property("sub-border-style", "background-box")
            else:
                self._set_property("sub-back-color", "#00000000")
                self._set_property("sub-border-style", "outline-and-shadow")

    ASPECTS = ["Original", "Stretch", "4:3", "16:9", "16:10"]

    def set_aspect(self, mode: str):
        """Force a video aspect ratio. Stored + reapplied on each loaded file."""
        self._aspect = mode if mode in self.ASPECTS else "Original"
        self._apply_aspect()

    def _apply_aspect(self):
        mode = getattr(self, "_aspect", "Original")
        if mode == "Stretch":
            self._set_property("keepaspect", False)        # fill window, ignore AR
            self._set_property("video-aspect-override", "-1")
        else:
            self._set_property("keepaspect", True)
            ratio = {"4:3": "4:3", "16:9": "16:9", "16:10": "16:10"}.get(mode, "-1")
            self._set_property("video-aspect-override", ratio)  # -1 = use file's AR

    def set_pause(self, paused: bool):
        self._set_property("pause", bool(paused))

    def toggle_pause(self):
        self._send({"command": ["cycle", "pause"]})

    def toggle_fullscreen(self):
        self._send({"command": ["cycle", "fullscreen"]})

    def set_fullscreen(self, on: bool):
        self._set_property("fullscreen", bool(on))

    def set_mouse_tracking(self, on: bool):
        """Observe/unobserve the mouse position (used while the menu is open)."""
        if on:
            self._send({"command": ["observe_property", 7, "mouse-pos"]})
        else:
            self._send({"command": ["unobserve_property", 7]})

    def toggle_menu(self):
        """Show/hide mpv's built-in on-screen controller (the mpv 'menu')."""
        self._osc_visible = not getattr(self, "_osc_visible", False)
        mode = "always" if self._osc_visible else "never"
        self._send({"command": ["script-message", "osc-visibility", mode]})

    def set_video_box(self, left: float, right: float, top: float, bottom: float):
        """Shrink the video into a sub-rectangle of the window via margins
        (each value is a 0..1 ratio of the window).  Used to render the live
        video inside the guide's preview box."""
        for side, val in (("left", left), ("right", right),
                          ("top", top), ("bottom", bottom)):
            v = max(0.0, min(0.95, float(val)))
            self._send({"command": ["set_property",
                                    f"video-margin-ratio-{side}", v]})

    def reset_video_box(self):
        """Restore full-screen video."""
        self.set_video_box(0.0, 0.0, 0.0, 0.0)

    def pause(self):
        self._paused = not self._paused
        self._set_property("pause", self._paused)

    @property
    def paused(self) -> bool:
        return self._paused

    # ── Volume / mute (cached locally) ─────────────────────────────────────

    @property
    def volume(self) -> int:
        return self._volume

    @volume.setter
    def volume(self, val: int):
        self._volume = max(0, min(100, int(val)))
        self._set_property("volume", self._volume)

    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, val: bool):
        self._muted = bool(val)
        self._set_property("mute", self._muted)

    def volume_up(self, step: int = 5) -> int:
        self.volume = self._volume + step
        return self._volume

    def volume_down(self, step: int = 5) -> int:
        self.volume = self._volume - step
        return self._volume

    def set_volume(self, vol: int) -> int:
        self.volume = max(0, min(100, int(vol)))
        return self._volume

    def toggle_mute(self) -> bool:
        self.muted = not self._muted
        return self._muted

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def wait_for_playback(self):
        """Block until mpv exits (socket closes)."""
        self._exited.wait()

    def terminate(self):
        self._running = False
        try:
            self._send({"command": ["quit"]})
        except Exception:
            pass
        if self._transport:
            try:
                self._transport.close()
            except OSError:
                pass
        self._conn.shutdown()
        self._exited.set()
