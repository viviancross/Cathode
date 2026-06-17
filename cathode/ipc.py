"""Platform IPC transports for mpv's JSON IPC endpoint.

Linux/macOS use an AF_UNIX stream socket.  Windows uses a named pipe driven with
non-blocking ``PeekNamedPipe`` reads under a short lock — a single *synchronous*
pipe handle shared between a blocking read and concurrent writes is the classic
Windows stall (the blocking read holds the handle and starves all writes, which
freezes overlay updates and makes input laggy).  Reading only the bytes that are
already available keeps the handle free for the 60fps overlay writes.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from typing import Callable, Optional


def make_transport(path: str) -> "Transport":
    if os.name == "nt":
        return WindowsPipeTransport(path)
    return UnixSocketTransport(path)


class Transport:
    def try_connect(self) -> bool:        # one connection attempt
        raise NotImplementedError

    def send(self, data: bytes) -> None:
        raise NotImplementedError

    def serve(self, on_line: Callable[[bytes], None]) -> None:
        """Read lines until the endpoint closes, calling on_line per line."""
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class UnixSocketTransport(Transport):
    def __init__(self, path: str):
        self.path = path
        self._sock: Optional[socket.socket] = None
        self._file = None
        self._open = False
        self._wlock = threading.Lock()

    def try_connect(self) -> bool:
        if not os.path.exists(self.path):
            return False
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(self.path)
        except OSError:
            return False
        self._sock = s
        self._file = s.makefile("rwb")
        self._open = True
        return True

    def send(self, data: bytes) -> None:
        if not self._file:
            return
        with self._wlock:
            try:
                self._file.write(data)
                self._file.flush()
            except (OSError, ValueError):
                pass

    def serve(self, on_line: Callable[[bytes], None]) -> None:
        f = self._file
        while self._open and f:
            try:
                line = f.readline()
            except (OSError, ValueError):
                break
            if not line:
                break
            on_line(line)
        self._open = False

    def close(self) -> None:
        self._open = False
        for x in (self._file, self._sock):
            try:
                if x:
                    x.close()
            except OSError:
                pass


class WindowsPipeTransport(Transport):
    def __init__(self, path: str):
        self.path = path
        self._open = False
        self._lock = threading.Lock()    # serialises peek/read/write on the handle
        self._rbuf = b""
        self._handle = None

        import ctypes
        from ctypes import wintypes
        self._ctypes = ctypes
        self._wt = wintypes
        k = ctypes.windll.kernel32
        H = wintypes.HANDLE
        k.CreateFileW.restype = H
        k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, H]
        k.ReadFile.restype = wintypes.BOOL
        k.ReadFile.argtypes = [H, wintypes.LPVOID, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        k.WriteFile.restype = wintypes.BOOL
        k.WriteFile.argtypes = [H, wintypes.LPVOID, wintypes.DWORD,
                                ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        k.PeekNamedPipe.restype = wintypes.BOOL
        k.PeekNamedPipe.argtypes = [H, wintypes.LPVOID, wintypes.DWORD,
                                    ctypes.POINTER(wintypes.DWORD),
                                    ctypes.POINTER(wintypes.DWORD),
                                    ctypes.POINTER(wintypes.DWORD)]
        k.CloseHandle.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [H]
        self._k = k
        self._INVALID = ctypes.c_void_p(-1).value

    def try_connect(self) -> bool:
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3
        h = self._k.CreateFileW(self.path, GENERIC_READ | GENERIC_WRITE,
                                0, None, OPEN_EXISTING, 0, None)
        if not h or h == self._INVALID:
            return False
        self._handle = h
        self._open = True
        return True

    def send(self, data: bytes) -> None:
        if not self._open or self._handle is None:
            return
        ctypes = self._ctypes
        buf = ctypes.create_string_buffer(data, len(data))
        written = self._wt.DWORD(0)
        with self._lock:
            try:
                self._k.WriteFile(self._handle, buf, len(data),
                                  ctypes.byref(written), None)
            except OSError:
                pass

    def _read_available(self) -> Optional[bytes]:
        """Read only the bytes already buffered in the pipe (caller holds lock).
        Returns b'' if none, None if the pipe is broken/closed."""
        ctypes = self._ctypes
        avail = self._wt.DWORD(0)
        ok = self._k.PeekNamedPipe(self._handle, None, 0, None,
                                   ctypes.byref(avail), None)
        if not ok:
            return None
        n = avail.value
        if n <= 0:
            return b""
        buf = ctypes.create_string_buffer(n)
        read = self._wt.DWORD(0)
        ok = self._k.ReadFile(self._handle, buf, n, ctypes.byref(read), None)
        if not ok:
            return None
        return buf.raw[:read.value]

    def serve(self, on_line: Callable[[bytes], None]) -> None:
        while self._open:
            with self._lock:
                chunk = self._read_available()
            if chunk is None:
                break              # pipe closed/broken
            if chunk:
                self._rbuf += chunk
                while b"\n" in self._rbuf:
                    line, self._rbuf = self._rbuf.split(b"\n", 1)
                    on_line(line + b"\n")
            else:
                time.sleep(0.004)  # idle — yield without holding the handle
        self._open = False

    def close(self) -> None:
        self._open = False
        if self._handle is not None:
            try:
                self._k.CloseHandle(self._handle)
            except OSError:
                pass
            self._handle = None
