"""How the app reaches mpv.

`Player` speaks mpv's JSON command vocabulary and nothing else — it never learns
whether mpv is a child process on the other end of a socket or a libmpv handle
in the same address space.  That distinction lives here, behind three methods:

    connect(args) -> Transport   apply the mpv options in `args`, get mpv
                                 running, and return a connected Transport.
                                 Raise RuntimeError with a message a user can
                                 act on if mpv can't be reached.
    alive() -> bool              is mpv still there?
    shutdown() -> None           release whatever connect() acquired.  Must be
                                 safe to call when connect() failed or never ran.

`SubprocessConnection` below is the desktop implementation: it launches mpv
(Flatpak on Steam Deck, otherwise a system or bundled binary) and drives it over
the JSON IPC endpoint.  Android's in-process libmpv connection implements the
same three methods; there is deliberately no base class, because duck typing is
all this needs and an abstract class with one real implementation is just
ceremony.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from typing import List, Optional

from .ipc import make_transport, Transport

_IS_WINDOWS = (os.name == "nt")
_IS_MACOS = (sys.platform == "darwin")


class SubprocessConnection:
    """Run mpv as a child process and talk to its JSON IPC endpoint.

    On Steam Deck / SteamOS the root filesystem is read-only and libmpv is not
    available to a system Python process, which is why the desktop builds drive
    a subprocess rather than linking libmpv in-process.
    """

    def __init__(
        self,
        runtime_dir: str,
        flatpak_app: str = "io.mpv.Mpv",
        backend: str = "auto",           # "auto" | "flatpak" | "system"
        mpv_path: str = "",              # explicit path to mpv(.exe), optional
        mpv_command: Optional[List[str]] = None,   # full argv override
        mpv_log: str = "",               # mpv's own log, named in error messages
    ):
        self._runtime_dir = runtime_dir
        self._flatpak_app = flatpak_app
        self._backend = backend
        self._mpv_path = mpv_path or ""
        self._cmd_override = mpv_command
        self._mpv_log = mpv_log
        self._resolved_backend = ""
        self._proc: Optional[subprocess.Popen] = None
        self._proc_log = os.path.join(runtime_dir, "mpv-stdout.log")
        self._proc_log_fh = None
        self._transport: Optional[Transport] = None

        if _IS_WINDOWS:
            # mpv's IPC server is a Windows named pipe, not a filesystem socket.
            self.ipc_path = r"\\.\pipe\cathode-mpv-%d" % os.getpid()
        else:
            self.ipc_path = os.path.join(runtime_dir, "mpv.sock")
            self._unlink_socket()        # a crashed run can leave a stale one

    # ── locating mpv ──────────────────────────────────────────────────────

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

    def mpv_exe(self) -> Optional[str]:
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
        if _IS_MACOS:
            for p in ("/opt/homebrew/bin/mpv", "/usr/local/bin/mpv"):
                if os.path.isfile(p):
                    return p
        return None

    def resolve_backend(self) -> str:
        if self._backend == "flatpak":
            return "flatpak"
        if self._backend == "system":
            return "system"
        # auto: prefer Flatpak mpv on Linux (Steam Deck), else a system mpv.
        # macOS uses a system mpv (Homebrew) — never Flatpak.
        if (not _IS_WINDOWS and not _IS_MACOS
                and self._flatpak_mpv_available()):
            return "flatpak"
        if self.mpv_exe():
            return "system"
        # Nothing found — fall back so the error names the right thing:
        # Flatpak on Linux, a system mpv on Windows/macOS.
        if _IS_WINDOWS or _IS_MACOS:
            return "system"
        return "flatpak"

    def build_cmd(self, args: List[str]) -> List[str]:
        """Full argv for mpv: the caller's options plus our IPC endpoint."""
        if self._cmd_override:
            return self._cmd_override
        # The IPC endpoint is this connection's business, not the caller's — an
        # in-process libmpv connection has no socket at all.
        args = [f"--input-ipc-server={self.ipc_path}", *args]
        backend = self._resolved_backend = self.resolve_backend()
        if backend == "flatpak":
            # Share the runtime dir so the IPC socket + overlay buffer reach the
            # sandboxed mpv.
            return ["flatpak", "run", f"--filesystem={self._runtime_dir}",
                    self._flatpak_app, *args]
        return [self.mpv_exe() or "mpv", *args]

    # ── the contract ──────────────────────────────────────────────────────

    def connect(self, args: List[str]) -> Transport:
        cmd = self.build_cmd(args)
        exe = cmd[0]
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
                "Note: mpv.net is a different app - you need plain mpv."
            )

        # A leftover socket from a crashed run can make the new connection hit a
        # dead endpoint; remove it so mpv recreates it cleanly.
        self._unlink_socket()

        # Capture the subprocess's own stdout/stderr (flatpak + mpv startup
        # errors) to a file so failures are visible after the fact in Game Mode.
        try:
            self._proc_log_fh = open(self._proc_log, "w")
        except OSError:
            self._proc_log_fh = None
        self._proc = subprocess.Popen(
            cmd,
            stdout=self._proc_log_fh or subprocess.DEVNULL,
            stderr=subprocess.STDOUT if self._proc_log_fh else subprocess.DEVNULL,
        )

        # Wait for the IPC endpoint to appear and connect to it.
        transport = make_transport(self.ipc_path)
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"mpv exited immediately (code {self._proc.returncode}). "
                    f"See {self._proc_log}"
                )
            if transport.try_connect():
                self._transport = transport
                return transport
            time.sleep(0.1)
        raise RuntimeError(
            "Could not connect to mpv IPC endpoint. mpv is running but never "
            f"opened its control socket at {self.ipc_path}. See "
            f"{self._mpv_log} and {self._proc_log} for the reason (e.g. an "
            "unknown option, or a build of mpv without JSON IPC support)."
        )

    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def shutdown(self) -> None:
        if self._proc:
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.terminate()
        if self._proc_log_fh:
            try:
                self._proc_log_fh.close()
            except OSError:
                pass
            self._proc_log_fh = None
        self._unlink_socket()

    # ── helpers ───────────────────────────────────────────────────────────

    def _unlink_socket(self):
        if _IS_WINDOWS:
            return          # the named pipe cleans itself up
        try:
            os.unlink(self.ipc_path)
        except OSError:
            pass
