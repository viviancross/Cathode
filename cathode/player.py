"""MPV player controlled over a JSON IPC socket.

On Steam Deck / SteamOS the root filesystem is read-only and libmpv is not
available to a system Python process, so we do NOT use python-mpv (which links
libmpv in-process).  Instead we launch mpv as a subprocess (typically the
Flatpak `io.mpv.Mpv`) with `--input-ipc-server=<socket>` and drive it entirely
over the JSON IPC protocol:

    {"command": ["loadfile", url, "replace"]}\n
    {"command": ["overlay-add", ...]}\n

Key presses are handled by binding keys in mpv to a `script-message
cathode-key <name>` command; mpv echoes these back as `client-message` events
which we dispatch to Python callbacks.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, Dict, List, Optional

from .ipc import make_transport


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
        self._flatpak_app = flatpak_app
        self._backend = backend
        self._mpv_path = mpv_path or ""
        self._cmd_override = mpv_command
        self._resolved_backend = ""
        self._extra_args = list(extra_args or [])
        self._ar_delay = int(ar_delay)
        self._ar_rate = int(ar_rate)
        self._mpv_log = os.path.join(runtime_dir, "mpv.log")
        self._proc_log = os.path.join(runtime_dir, "mpv-stdout.log")

        os.makedirs(runtime_dir, exist_ok=True)
        self._runtime_dir = runtime_dir
        self._is_windows = (os.name == "nt")
        self._is_macos = (sys.platform == "darwin")
        if self._is_windows:
            # mpv's IPC server is a Windows named pipe, not a filesystem socket.
            self._sock_path = r"\\.\pipe\cathode-mpv-%d" % os.getpid()
        else:
            self._sock_path = os.path.join(runtime_dir, "mpv.sock")
            try:
                os.unlink(self._sock_path)   # remove any stale socket
            except OSError:
                pass

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

        # IPC connection (platform-specific transport: unix socket / named pipe)
        self._transport = None
        self._running = False
        self._exited = threading.Event()
        self._cmd: List[str] = []
        self._proc: Optional[subprocess.Popen] = None

    # ── Backend detection ──────────────────────────────────────────────────

    def _flatpak_mpv_available(self) -> bool:
        if not shutil.which("flatpak"):
            return False
        try:
            r = subprocess.run(
                ["flatpak", "info", self._flatpak_app],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=10,
            )
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _bundled_mpv(self) -> Optional[str]:
        """Locate an mpv shipped alongside a frozen (PyInstaller) build."""
        bases = []
        if getattr(sys, "frozen", False):
            bases.append(os.path.dirname(sys.executable))
            mei = getattr(sys, "_MEIPASS", None)
            if mei:
                bases.append(mei)
        for base in bases:
            for rel in ("mpv.exe", os.path.join("mpv", "mpv.exe"),
                        "mpv", os.path.join("mpv", "mpv")):
                p = os.path.join(base, rel)
                if os.path.isfile(p):
                    return p
        return None

    def _mpv_exe(self) -> Optional[str]:
        """Resolve the mpv executable (config path, then bundled, then PATH)."""
        if self._mpv_path:
            if os.path.isfile(self._mpv_path):
                return self._mpv_path
            found = shutil.which(self._mpv_path)
            if found:
                return found
        bundled = self._bundled_mpv()
        if bundled:
            return bundled
        for name in ("mpv", "mpv.exe", "mpv.com"):
            found = shutil.which(name)
            if found:
                return found
        # A GUI-launched macOS .app doesn't inherit the shell PATH, so probe the
        # standard Homebrew locations directly.
        if self._is_macos:
            for p in ("/opt/homebrew/bin/mpv", "/usr/local/bin/mpv"):
                if os.path.isfile(p):
                    return p
        return None

    def _resolve_backend(self) -> str:
        if self._backend == "flatpak":
            return "flatpak"
        if self._backend == "system":
            return "system"
        # auto: prefer Flatpak mpv on Linux (Steam Deck), else a system mpv.
        # macOS uses a system mpv (Homebrew) — never Flatpak.
        if (not self._is_windows and not self._is_macos
                and self._flatpak_mpv_available()):
            return "flatpak"
        if self._mpv_exe():
            return "system"
        # Nothing found — fall back so the error names the right thing:
        # Flatpak on Linux, a system mpv on Windows/macOS.
        if self._is_windows or self._is_macos:
            return "system"
        return "flatpak"

    # ── Launch / connect ───────────────────────────────────────────────────

    def _common_args(self) -> List[str]:
        args = [
            f"--input-ipc-server={self._sock_path}",
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
            f"--volume={self._volume}",
            f"--user-agent={self.user_agent}",
            f"--geometry={self.width}x{self.height}",
            "--title=Cathode",
            "--cache=yes",
            "--demuxer-max-bytes=64MiB",
            # Verbose log to a file — invaluable for diagnosing Game Mode video
            # problems where there's no terminal to read.
            f"--log-file={self._mpv_log}",
            "--msg-level=all=v",
        ]
        args.append("--fullscreen=yes" if self.fullscreen else "--fullscreen=no")
        # NB: mpv's own SDL gamepad input is intentionally NOT used — the app
        # has a native gamepad reader (cathode/gamepad.py) that works on every
        # mpv build (incl. the SDL-less Flatpak mpv), so we never pass
        # --input-gamepad (which is a fatal unknown option on those builds).
        # User-supplied extra args last so they can override anything above.
        args.extend(self._extra_args)
        return args

    def _build_cmd(self) -> List[str]:
        if self._cmd_override:
            return self._cmd_override
        backend = self._resolve_backend()
        self._resolved_backend = backend
        if backend == "flatpak":
            # Share the runtime dir so the IPC socket + overlay buffer reach the
            # sandboxed mpv.
            return [
                "flatpak", "run",
                f"--filesystem={self._runtime_dir}",
                self._flatpak_app,
                *self._common_args(),
            ]
        return [self._mpv_exe() or "mpv", *self._common_args()]

    def start(self):
        """Launch mpv and connect the IPC socket."""
        self._cmd = self._build_cmd()
        exe = self._cmd[0]
        if not (shutil.which(exe) or os.path.isfile(exe)):
            if self._resolved_backend == "flatpak":
                raise RuntimeError(
                    f"'flatpak' not found. Install mpv via Flatpak "
                    f"(flatpak install flathub {self._flatpak_app})."
                )
            raise RuntimeError(
                "mpv not found. Install mpv and make sure 'mpv' runs from a "
                "terminal (add it to PATH), or set \"mpv_path\" in "
                "config.json to the full path of mpv.exe. "
                "Note: mpv.net is a different app — you need plain mpv."
            )

        # A leftover socket from a crashed run can make the new connection hit a
        # dead endpoint; remove it so mpv recreates it cleanly.
        if not self._is_windows:
            try:
                if os.path.exists(self._sock_path):
                    os.unlink(self._sock_path)
            except OSError:
                pass

        # Capture the subprocess's own stdout/stderr (flatpak + mpv startup
        # errors) to a file so failures are visible after the fact in Game Mode.
        try:
            self._proc_log_fh = open(self._proc_log, "w")
        except OSError:
            self._proc_log_fh = None
        self._proc = subprocess.Popen(
            self._cmd,
            stdout=self._proc_log_fh or subprocess.DEVNULL,
            stderr=subprocess.STDOUT if self._proc_log_fh else subprocess.DEVNULL,
        )

        # Wait for the IPC endpoint to appear and connect to it.
        self._transport = make_transport(self._sock_path)
        deadline = time.monotonic() + 15.0
        connected = False
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"mpv exited immediately (code {self._proc.returncode}). "
                    f"See {self._proc_log}"
                )
            if self._transport.try_connect():
                connected = True
                break
            time.sleep(0.1)
        if not connected:
            raise RuntimeError(
                "Could not connect to mpv IPC endpoint. mpv is running but never "
                f"opened its control socket at {self._sock_path}. See "
                f"{self._mpv_log} and {self._proc_log} for the reason (e.g. an "
                "unknown option, or a build of mpv without JSON IPC support)."
            )

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
            if self._is_windows:
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
            if self._on_playback_started:
                self._on_playback_started()
        elif event == "end-file":
            reason = msg.get("reason", "")
            if reason in ("eof", "error") and self._on_eof:
                self._on_eof()
        elif event == "property-change":
            name = msg.get("name")
            if name == "eof-reached" and msg.get("data") is True:
                if self._on_eof:
                    self._on_eof()
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

    def play(self, url: str):
        self._send({"command": ["loadfile", url, "replace"]})

    def stop(self):
        self._send({"command": ["stop"]})

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
        if self._proc:
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.terminate()
        if getattr(self, "_proc_log_fh", None):
            try:
                self._proc_log_fh.close()
            except OSError:
                pass
        if not self._is_windows:   # the named pipe cleans itself up
            try:
                os.unlink(self._sock_path)
            except OSError:
                pass
        self._exited.set()
