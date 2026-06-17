"""Native gamepad reading — works even when mpv lacks SDL gamepad support
(e.g. the Flatpak io.mpv.Mpv build on the Steam Deck / Linux).

No third-party deps:
  • Windows: XInput via ctypes.
  • Linux:   the legacy /dev/input/js* joystick interface (struct-parsed).

It polls the first connected controller, diffs state to find button-press
edges, and emits normalized action names to a callback with auto-repeat for the
directional inputs (so a held d-pad/stick scrolls).  Mapping assumes a standard
Xbox-style pad.
"""

from __future__ import annotations

import glob
import os
import struct
import threading
import time
from typing import Callable

_REPEAT_DELAY = 0.30      # seconds before a held direction starts repeating
_REPEAT_INTERVAL = 1.0 / 8.0   # ~8 repeats/sec (matches the keyboard cap)
_STICK_TH = 16000        # left-stick deflection that counts as a direction
_POLL = 1.0 / 60.0

# Linux js button index → action (xpad ordering)
_JS_BUTTONS = {0: "a", 1: "b", 2: "x", 3: "y", 4: "lb", 5: "rb",
               6: "back", 7: "start", 8: "guide", 9: "l3", 10: "r3"}


class GamepadReader:
    def __init__(self, on_action: Callable):
        # on_action(name: str, is_repeat: bool)
        self.on_action = on_action
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    # ── shared edge/repeat processing ─────────────────────────────────────

    def _emit(self, name, is_repeat=False):
        try:
            self.on_action(name, is_repeat)
        except Exception:
            pass

    def _process(self, dirs, buttons, state):
        now = time.monotonic()
        # Button press edges (fire once; no repeat).
        for b in buttons - state["buttons"]:
            self._emit(b, False)
        state["buttons"] = set(buttons)
        # Directions: fire on press, then repeat while held.
        held = state["held"]
        for d in dirs:
            if d not in held:
                self._emit(d, False)
                held[d] = now + _REPEAT_DELAY
            elif now >= held[d]:
                self._emit(d, True)
                held[d] = now + _REPEAT_INTERVAL
        for d in [d for d in held if d not in dirs]:
            del held[d]

    def _run(self):
        try:
            if os.name == "nt":
                self._run_xinput()
            else:
                self._run_linux_js()
        except Exception:
            pass   # a gamepad reader failure must never take the app down

    # ── Windows: XInput ───────────────────────────────────────────────────

    def _run_xinput(self):
        import ctypes
        xinput = None
        for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try:
                xinput = getattr(ctypes.windll, dll)
                break
            except Exception:
                continue
        if xinput is None:
            return

        class _PAD(ctypes.Structure):
            _fields_ = [("wButtons", ctypes.c_ushort),
                        ("bLeftTrigger", ctypes.c_ubyte),
                        ("bRightTrigger", ctypes.c_ubyte),
                        ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
                        ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]

        class _STATE(ctypes.Structure):
            _fields_ = [("dwPacketNumber", ctypes.c_uint), ("Gamepad", _PAD)]

        BTN = {0x0010: "start", 0x0020: "back", 0x0040: "l3", 0x0080: "r3",
               0x0100: "lb", 0x0200: "rb", 0x0400: "guide",
               0x1000: "a", 0x2000: "b", 0x4000: "x", 0x8000: "y"}
        st = _STATE()
        state = {"buttons": set(), "held": {}}
        while self._running:
            found = False
            for i in range(4):
                if xinput.XInputGetState(i, ctypes.byref(st)) == 0:
                    found = True
                    g = st.Gamepad
                    wb = g.wButtons
                    dirs = set()
                    if wb & 0x0001: dirs.add("up")
                    if wb & 0x0002: dirs.add("down")
                    if wb & 0x0004: dirs.add("left")
                    if wb & 0x0008: dirs.add("right")
                    if g.sThumbLY > _STICK_TH: dirs.add("up")
                    if g.sThumbLY < -_STICK_TH: dirs.add("down")
                    if g.sThumbLX < -_STICK_TH: dirs.add("left")
                    if g.sThumbLX > _STICK_TH: dirs.add("right")
                    buttons = {name for bit, name in BTN.items() if wb & bit}
                    if g.bLeftTrigger > 30: buttons.add("lt")
                    if g.bRightTrigger > 30: buttons.add("rt")
                    self._process(dirs, buttons, state)
                    break
            if not found:
                state["buttons"].clear(); state["held"].clear()
            time.sleep(_POLL)

    # ── Linux: /dev/input/js* ─────────────────────────────────────────────

    def _run_linux_js(self):
        state = {"buttons": set(), "held": {}}
        btns, axes = {}, {}
        fd = None
        JS_SIZE = 8                       # struct js_event { u32 time; s16 val; u8 type; u8 num; }
        while self._running:
            if fd is None:
                paths = sorted(glob.glob("/dev/input/js*"))
                if paths:
                    try:
                        fd = os.open(paths[0], os.O_RDONLY | os.O_NONBLOCK)
                    except OSError:
                        fd = None
                if fd is None:
                    time.sleep(1.0)
                    continue
                btns, axes = {}, {}
            try:
                while True:
                    data = os.read(fd, JS_SIZE)
                    if not data or len(data) < JS_SIZE:
                        break
                    _t, value, typ, num = struct.unpack("IhBB", data)
                    typ &= ~0x80          # strip the "init" flag
                    if typ == 0x01:
                        btns[num] = value
                    elif typ == 0x02:
                        axes[num] = value
            except BlockingIOError:
                pass
            except OSError:               # disconnected
                try:
                    os.close(fd)
                except OSError:
                    pass
                fd = None
                continue
            self._process(*self._linux_signals(btns, axes), state)
            time.sleep(_POLL)
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

    @staticmethod
    def _linux_signals(btns, axes):
        dirs = set()
        dx, dy = axes.get(6, 0), axes.get(7, 0)        # d-pad (hat) axes
        lx, ly = axes.get(0, 0), axes.get(1, 0)        # left stick (Y inverted)
        if dx < -_STICK_TH or lx < -_STICK_TH: dirs.add("left")
        if dx > _STICK_TH or lx > _STICK_TH: dirs.add("right")
        if dy < -_STICK_TH or ly < -_STICK_TH: dirs.add("up")
        if dy > _STICK_TH or ly > _STICK_TH: dirs.add("down")
        buttons = {name for idx, name in _JS_BUTTONS.items() if btns.get(idx)}
        if axes.get(2, -32767) > 0: buttons.add("lt")   # triggers: released ≈ -32767
        if axes.get(5, -32767) > 0: buttons.add("rt")
        return dirs, buttons
