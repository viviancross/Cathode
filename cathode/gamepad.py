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
import sys
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
        # Re-enter the platform loop if it ever exits or throws (e.g. a pad
        # disconnect breaks a read). Without this the reader would die on the
        # first hiccup and never pick a reconnected controller back up.
        while self._running:
            try:
                if os.name == "nt":
                    self._run_xinput()
                elif sys.platform == "darwin":
                    self._run_macos()
                else:
                    self._run_linux_js()
            except Exception:
                pass
            if self._running:
                time.sleep(0.5)

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
        # Microsoft explicitly warns: polling XInputGetState on disconnected user
        # indices is expensive and can prevent re-detection. Only re-scan empty
        # slots once per second; the connected slot keeps polling at _POLL.
        connected = -1
        next_scan = 0.0
        while self._running:
            now = time.monotonic()
            try:
                indices = ([connected] if connected >= 0 else []) + (
                    [i for i in range(4) if i != connected]
                    if now >= next_scan else [])
                if not indices:
                    time.sleep(_POLL); continue
                found = False
                for i in indices:
                    if xinput.XInputGetState(i, ctypes.byref(st)) == 0:
                        connected = i
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
                    if connected >= 0:               # the controller just dropped
                        connected = -1
                        state["buttons"].clear(); state["held"].clear()
                    next_scan = now + 1.0            # throttle re-detect scans
            except Exception:
                # Never let a transient ctypes hiccup kill the reader.
                connected = -1
                state["buttons"].clear(); state["held"].clear()
                next_scan = now + 1.0
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
            disconnected = False
            try:
                while True:
                    data = os.read(fd, JS_SIZE)
                    if not data:           # 0-byte read = EOF = device gone
                        disconnected = True
                        break
                    if len(data) < JS_SIZE:
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
                disconnected = True
            if disconnected:
                try:
                    os.close(fd)
                except OSError:
                    pass
                fd = None
                state["buttons"].clear(); state["held"].clear()
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

    # ── macOS: IOKit HID (polling, no run loop) ───────────────────────────

    def _run_macos(self):
        import ctypes
        from ctypes import (c_void_p, c_int, c_int32, c_uint32, c_long,
                            c_char_p, c_bool, byref, POINTER)
        try:
            cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/"
                             "CoreFoundation")
            io = ctypes.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")
        except OSError:
            return

        # CoreFoundation — every ref-returning fn MUST be c_void_p (else a 64-bit
        # pointer gets truncated to 32 bits and the next call segfaults).
        cf.CFStringCreateWithCString.restype = c_void_p
        cf.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_uint32]
        cf.CFRetain.restype = c_void_p
        cf.CFRetain.argtypes = [c_void_p]
        cf.CFRelease.argtypes = [c_void_p]
        cf.CFSetGetCount.restype = c_long
        cf.CFSetGetCount.argtypes = [c_void_p]
        cf.CFSetGetValues.argtypes = [c_void_p, POINTER(c_void_p)]
        cf.CFArrayGetCount.restype = c_long
        cf.CFArrayGetCount.argtypes = [c_void_p]
        cf.CFArrayGetValueAtIndex.restype = c_void_p
        cf.CFArrayGetValueAtIndex.argtypes = [c_void_p, c_long]
        cf.CFNumberGetValue.restype = c_bool
        cf.CFNumberGetValue.argtypes = [c_void_p, c_int, c_void_p]
        for fn, args, ret in (
            ("IOHIDManagerCreate", [c_void_p, c_uint32], c_void_p),
            ("IOHIDManagerSetDeviceMatching", [c_void_p, c_void_p], None),
            ("IOHIDManagerOpen", [c_void_p, c_uint32], c_int),
            ("IOHIDManagerCopyDevices", [c_void_p], c_void_p),
            ("IOHIDDeviceGetProperty", [c_void_p, c_void_p], c_void_p),
            ("IOHIDDeviceCopyMatchingElements", [c_void_p, c_void_p, c_uint32], c_void_p),
            ("IOHIDElementGetUsagePage", [c_void_p], c_uint32),
            ("IOHIDElementGetUsage", [c_void_p], c_uint32),
            ("IOHIDElementGetLogicalMin", [c_void_p], c_long),
            ("IOHIDElementGetLogicalMax", [c_void_p], c_long),
            ("IOHIDDeviceGetValue", [c_void_p, c_void_p, POINTER(c_void_p)], c_int),
            ("IOHIDValueGetIntegerValue", [c_void_p], c_long),
        ):
            f = getattr(io, fn)
            f.argtypes = args
            f.restype = ret

        UTF8 = 0x08000100
        SINT32 = 3

        def cfstr(s):
            return cf.CFStringCreateWithCString(None, s.encode(), UTF8)

        k_usage = cfstr("PrimaryUsage")
        k_usagepage = cfstr("PrimaryUsagePage")

        def dev_int(dev, key):
            ref = io.IOHIDDeviceGetProperty(dev, key)
            if not ref:
                return None
            out = c_int32(0)
            return out.value if cf.CFNumberGetValue(ref, SINT32, byref(out)) else None

        def read(dev, elem):
            val = c_void_p()
            if io.IOHIDDeviceGetValue(dev, elem, byref(val)) != 0 or not val:
                return None
            return io.IOHIDValueGetIntegerValue(val)

        mgr = io.IOHIDManagerCreate(None, 0)
        if not mgr:
            return
        io.IOHIDManagerSetDeviceMatching(mgr, None)   # match all; we filter below
        io.IOHIDManagerOpen(mgr, 0)

        # Best-effort Xbox HID button-usage → action map (numbering varies a bit
        # by controller; tweak if buttons land wrong).
        BTN = {1: "a", 2: "b", 3: "x", 4: "y", 5: "lb", 6: "rb",
               7: "back", 8: "start", 9: "l3", 10: "r3", 11: "guide"}
        HAT = {0: {"up"}, 1: {"up", "right"}, 2: {"right"}, 3: {"down", "right"},
               4: {"down"}, 5: {"down", "left"}, 6: {"left"}, 7: {"up", "left"}}
        state = {"buttons": set(), "held": {}}
        dev = btn_el = axis_el = hat = els_arr = None
        rescan = 0.0

        def reset():
            nonlocal dev, els_arr
            if els_arr:
                cf.CFRelease(els_arr)
            if dev:
                cf.CFRelease(dev)
            dev = els_arr = None

        while self._running:
            now = time.monotonic()
            if dev is None and now >= rescan:
                rescan = now + 2.0
                devices = io.IOHIDManagerCopyDevices(mgr)
                if devices:
                    cnt = cf.CFSetGetCount(devices)
                    if cnt > 0:
                        arr = (c_void_p * cnt)()
                        cf.CFSetGetValues(devices, arr)
                        for i in range(cnt):
                            d = arr[i]
                            if (dev_int(d, k_usagepage) == 1
                                    and dev_int(d, k_usage) in (4, 5, 8)):
                                dev = cf.CFRetain(d)   # keep it past the set release
                                els_arr = io.IOHIDDeviceCopyMatchingElements(d, None, 0)
                                btn_el, axis_el, hat = {}, {}, None
                                en = cf.CFArrayGetCount(els_arr) if els_arr else 0
                                for j in range(en):
                                    e = cf.CFArrayGetValueAtIndex(els_arr, j)
                                    ep = io.IOHIDElementGetUsagePage(e)
                                    eu = io.IOHIDElementGetUsage(e)
                                    if ep == 0x09:
                                        btn_el[eu] = e
                                    elif ep == 0x01 and eu == 0x39:
                                        hat = (e, io.IOHIDElementGetLogicalMin(e),
                                               io.IOHIDElementGetLogicalMax(e))
                                    elif ep == 0x01 and eu in (0x30, 0x31, 0x32, 0x35):
                                        axis_el[eu] = (e, io.IOHIDElementGetLogicalMin(e),
                                                       io.IOHIDElementGetLogicalMax(e))
                                break
                    cf.CFRelease(devices)
                if dev is None:
                    time.sleep(0.5)
                    continue

            dirs, buttons, alive = set(), set(), False

            def axis(usage):     # normalized -1..1, 0 if absent
                t = axis_el.get(usage)
                if not t:
                    return 0.0
                e, lo, hi = t
                v = read(dev, e)
                if v is None or hi == lo:
                    return 0.0
                nonlocal alive
                alive = True
                return (v - lo) / (hi - lo) * 2.0 - 1.0

            for usage, e in btn_el.items():
                v = read(dev, e)
                if v is not None:
                    alive = True
                    if v and usage in BTN:
                        buttons.add(BTN[usage])
            lx, ly = axis(0x30), axis(0x31)
            if ly < -0.5: dirs.add("up")
            if ly > 0.5: dirs.add("down")
            if lx < -0.5: dirs.add("left")
            if lx > 0.5: dirs.add("right")
            if axis(0x32) > 0.0: buttons.add("lt")
            if axis(0x35) > 0.0: buttons.add("rt")
            if hat:
                e, lo, hi = hat
                hv = read(dev, e)
                if hv is not None:
                    alive = True
                    if lo <= hv <= hi and (hi - lo + 1) >= 8:
                        dirs |= HAT.get(hv - lo, set())

            if not alive and (btn_el or axis_el):   # device went away
                reset()
                state["buttons"].clear(); state["held"].clear()
            else:
                self._process(dirs, buttons, state)
            time.sleep(_POLL)
        reset()
