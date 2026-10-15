"""Process-level plumbing: one Cathode at a time, a log file, a visible
fatal error."""

import os
import sys


def hold_instance_lock(path: str):
    """Lock `path` for the life of this process and return the open file, or
    None when another Cathode already holds it. Two instances share one
    overlay file, one config and (on Linux) one mpv socket, and each scribbled
    over the other. The OS drops the lock when the process dies, crash or not,
    so a stale lock file is harmless. The update installer holds the same lock
    while it copies, so a relaunch can't start a half-installed build."""
    f = None
    try:
        f = open(path, "a+b")       # refused outright while the installer has it
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        if f:
            f.close()
        return None
    return f


class _Tee:
    """stdout/stderr to the log file, and to the console too when there is
    one (the Windows build has none: its sys.stdout is None)."""

    def __init__(self, *streams):
        self._streams = [st for st in streams if st is not None]

    def write(self, text):
        for st in self._streams:
            try:
                st.write(text)
                st.flush()
            except (OSError, ValueError):
                pass
        return len(text)

    def flush(self):
        pass


def start_log(runtime_dir: str) -> str:
    """Send everything printed, and any traceback, to cathode.log as well. The
    previous run's log is kept as cathode.log.1. Call only while holding the
    instance lock, or a second launch would rotate the first one's log away."""
    path = os.path.join(runtime_dir, "cathode.log")
    try:
        os.replace(path, path + ".1")
    except OSError:
        pass
    try:
        f = open(path, "w", encoding="utf-8", errors="replace")
    except OSError:
        return ""
    sys.stdout = _Tee(f, sys.stdout)
    sys.stderr = _Tee(f, sys.stderr)
    return path


def fatal(msg: str):
    """Report a startup failure where the user will see it, then exit. The
    Windows build has no console, so a print alone would vanish."""
    print(f"[cathode] {msg}")
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, "Cathode", 0x10)
        except Exception:
            pass
    sys.exit(1)


