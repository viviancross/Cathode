"""Where things live: bundled assets, libmpv, per-user cache and config."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bundle_dirs():
    """Install root candidates: next to a frozen exe and its unpack dir, else
    the source checkout."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        return [exe_dir, getattr(sys, "_MEIPASS", exe_dir)]
    return [ROOT]


def asset(*parts) -> str:
    """Path to a bundled asset; first existing candidate wins."""
    for base in _bundle_dirs():
        p = os.path.join(base, "assets", *parts)
        if os.path.exists(p):
            return p
    return os.path.join(_bundle_dirs()[0], "assets", *parts)


def libmpv_dirs() -> list:
    """Where a bundled libmpv is looked for first. A frozen build has it next
    to the executable or in PyInstaller's _internal folder; a source checkout
    in _libmpv/ (Windows; elsewhere the system's own is fine)."""
    if getattr(sys, "frozen", False):
        return _bundle_dirs()
    return [os.path.join(ROOT, "_libmpv")]


def cache_dir() -> str:
    """Logs, logo cache, update downloads. Created on first use."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "cathode")
    else:
        d = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
                         "cathode")
    os.makedirs(d, exist_ok=True)
    return d


def config_path() -> str:
    return os.path.expanduser("~/.config/cathode/config.json")
