"""Minimal cross-platform clipboard access (no third-party deps).

Windows uses the Win32 clipboard via ctypes; Linux shells out to wl-paste /
xclip / xsel (whichever is present).  All failures degrade to "" / False.
"""

from __future__ import annotations

import os
import subprocess


def get_text() -> str:
    try:
        if os.name == "nt":
            return _win_get()
        return _nix_get()
    except Exception:
        return ""


def set_text(s: str) -> bool:
    try:
        if os.name == "nt":
            return _win_set(s)
        return _nix_set(s)
    except Exception:
        return False


# ── Linux ─────────────────────────────────────────────────────────────────

def _nix_get() -> str:
    for cmd in (["wl-paste", "-n"],
                ["xclip", "-selection", "clipboard", "-o"],
                ["xsel", "-b", "-o"]):
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, timeout=2)
            if r.returncode == 0:
                return r.stdout.decode("utf-8", "replace")
        except (OSError, subprocess.SubprocessError):
            continue
    return ""


def _nix_set(s: str) -> bool:
    for cmd in (["wl-copy"],
                ["xclip", "-selection", "clipboard"],
                ["xsel", "-b", "-i"]):
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            p.communicate(s.encode("utf-8"), timeout=2)
            if p.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


# ── Windows ────────────────────────────────────────────────────────────────

def _win_get() -> str:
    import ctypes
    from ctypes import wintypes
    CF_UNICODETEXT = 13
    u = ctypes.windll.user32
    k = ctypes.windll.kernel32
    u.GetClipboardData.restype = wintypes.HANDLE
    u.GetClipboardData.argtypes = [wintypes.UINT]
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalLock.argtypes = [wintypes.HANDLE]
    k.GlobalUnlock.argtypes = [wintypes.HANDLE]
    if not u.OpenClipboard(None):
        return ""
    try:
        h = u.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        ptr = k.GlobalLock(h)
        if not ptr:
            return ""
        try:
            return ctypes.c_wchar_p(ptr).value or ""
        finally:
            k.GlobalUnlock(h)
    finally:
        u.CloseClipboard()


def _win_set(s: str) -> bool:
    import ctypes
    from ctypes import wintypes
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    u = ctypes.windll.user32
    k = ctypes.windll.kernel32
    k.GlobalAlloc.restype = wintypes.HANDLE
    k.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalLock.argtypes = [wintypes.HANDLE]
    k.GlobalUnlock.argtypes = [wintypes.HANDLE]
    u.SetClipboardData.restype = wintypes.HANDLE
    u.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    data = s.encode("utf-16-le") + b"\x00\x00"
    h = k.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not h:
        return False
    ptr = k.GlobalLock(h)
    if not ptr:
        return False
    ctypes.memmove(ptr, data, len(data))
    k.GlobalUnlock(h)
    if not u.OpenClipboard(None):
        return False
    try:
        u.EmptyClipboard()
        u.SetClipboardData(CF_UNICODETEXT, h)
        return True
    finally:
        u.CloseClipboard()
