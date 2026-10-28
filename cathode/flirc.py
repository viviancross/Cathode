"""A FLIRC USB receiver, driven through flirc_util: the dongle learns a
remote's buttons and types keys, and Cathode reads the keys like a keyboard.
Buttons are recorded by HID usage (record_api), so no key-name spelling of
flirc_util's needs guessing."""

import os
import shutil
import subprocess
import sys
import threading
from typing import Callable, Optional

# USB HID keyboard usages (page 7) by pygame key name.
HID = {"return": 40, "escape": 41, "backspace": 42, "tab": 43, "space": 44, "-": 45, "=": 46,
       "[": 47, "]": 48, "\\": 49, ";": 51, "'": 52, "`": 53, ",": 54, ".": 55, "/": 56,
       "insert": 73, "home": 74, "page up": 75, "delete": 76, "end": 77, "page down": 78,
       "right": 79, "left": 80, "down": 81, "up": 82, "enter": 88}
for _i, _ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
    HID[_ch] = 4 + _i
for _i in range(1, 10):
    HID[str(_i)] = 29 + _i
HID["0"] = 39
for _i in range(1, 13):
    HID[f"f{_i}"] = 57 + _i

_WINDOWS = [r"C:\Program Files (x86)\Flirc\flirc_util.exe", r"C:\Program Files\Flirc\flirc_util.exe"]
_MAC = ["/Applications/Flirc.app/Contents/Resources/flirc_util", "/Applications/Flirc.app/Contents/MacOS/flirc_util",
        "/usr/local/bin/flirc_util"]


def key_for(keys: dict, action: str) -> Optional[str]:
    """The pygame key name a FLIRC should type for `action`, from the live
    key map (code -> action): a letter or digit first, else any key with a
    HID usage; None when the action has no typeable key."""
    import pygame
    names = [pygame.key.name(c) for c, a in keys.items() if a == action]
    names = [n for n in names if n in HID]
    return min(names, key=lambda n: (not n.isalnum(), n)) if names else None


def find(override: str = "") -> Optional[list]:
    """The command that runs flirc_util here, or None. In a Flatpak it's the
    host's, through flatpak-spawn."""
    if override:
        return [override]
    if os.environ.get("FLATPAK_ID"):
        return ["flatpak-spawn", "--host", "flirc_util"]
    found = shutil.which("flirc_util")
    if found:
        return [found]
    for p in (_WINDOWS if os.name == "nt" else _MAC if sys.platform == "darwin" else []):
        if os.path.exists(p):
            return [p]
    return None


NOT_FOUND = "flirc_util not found. Install the Flirc software from flirc.tv (or set flirc_util in config.json)."


def last_line(out: str, code: int) -> str:
    """What to show for a run: its last line that says something (not the
    prompt, not a debug line)."""
    lines = [ln.strip() for ln in out.splitlines()
             if ln.strip() and not ln.strip().startswith(("[D]", "Press any button"))]
    if lines:
        return lines[-1]
    return "Done" if code == 0 else f"flirc_util exited {code}"


class Flirc:
    """Runs flirc_util off the UI thread; results come back on it. A
    recording waits for a remote button, so it can be cancelled."""

    def __init__(self, app):
        self.app = app
        self.proc = None
        self.seq = 0

    def run(self, args: list, done: Callable[[bool, str], None]):
        """done(ok, last line of output) on the UI thread, unless cancelled
        first."""
        cmd = find(self.app.config.flirc_util)
        if not cmd:
            done(False, NOT_FOUND)
            return
        self.cancel()
        self.seq += 1
        seq = self.seq
        exe = cmd[-1] if cmd[0] != "flatpak-spawn" else ""
        kw = {"cwd": os.path.dirname(exe) or None}       # Windows: its DLLs sit beside it
        if os.name == "nt":
            kw["creationflags"] = 0x08000000             # no console window

        def work():
            try:
                p = subprocess.Popen(cmd + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kw)
            except OSError as e:
                self.app.post(self._done, seq, done, False, str(e))
                return
            self.proc = p
            out = p.communicate()[0] or ""
            self.app.post(self._done, seq, done, p.returncode == 0, last_line(out, p.returncode))
        threading.Thread(target=work, daemon=True).start()

    def _done(self, seq, done, ok, text):
        if seq == self.seq:
            done(ok, text)

    def cancel(self):
        self.seq += 1               # a result still on its way is stale
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.kill()
            except OSError:
                pass
