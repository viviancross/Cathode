"""One file to send with a bug report: this run's log and the last, the
settings with every token blanked, and what Cathode is running on. Written
where the user can find it; nothing is sent anywhere."""

from __future__ import annotations

import json
import os
import platform
import sys
import time
import zipfile

from . import __version__, paths

# Settings that are secrets, or point at the user's account: blanked, not
# dropped, so the shape of the config still shows.
SECRET = ("plex_token", "plex_user_token")
PRIVATE = ("plex_user_name", "plex_user_id")


def scrubbed(config) -> dict:
    data = {k: v for k, v in config.__dict__.items() if not k.startswith("_")}
    for k in SECRET:
        if data.get(k):
            data[k] = "<removed>"
    for k in PRIVATE:
        if data.get(k):
            data[k] = "<removed>"
    return data


def system_text(app) -> str:
    gfx = getattr(app, "gfx", None)
    video = getattr(app, "video", None)
    lines = [
        f"Cathode {__version__}",
        f"Python {sys.version.split()[0]}  frozen={bool(getattr(sys, 'frozen', False))}",
        f"OS {platform.platform()}",
        f"Flatpak {'yes' if os.path.exists('/.flatpak-info') else 'no'}",
        f"GL {getattr(gfx, 'version', '?')} | {getattr(gfx, 'renderer', '?')}",
        f"Window {getattr(gfx, 'size', '?')}  fullscreen={getattr(app, 'fullscreen', '?')}",
        f"Skin {getattr(getattr(app, 'config', None), 'skin', '?')}",
        f"Session type {os.environ.get('XDG_SESSION_TYPE', '')}  SDL_VIDEODRIVER={os.environ.get('SDL_VIDEODRIVER', '')}",
    ]
    try:
        mpv = video.player.mpv_version if video else "?"
    except Exception:
        mpv = "?"
    lines.append(f"mpv {mpv}")
    try:
        if video:
            st = video.stats()
            lines.append("Playing now: " + json.dumps({k: v for k, v in st.items() if v is not None}, default=str))
    except Exception:
        pass
    return "\n".join(lines) + "\n"


def write(app, out_dir: str = "") -> str:
    """Write the zip; returns its path."""
    out_dir = out_dir or os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(out_dir):
        out_dir = os.path.expanduser("~")
    path = os.path.join(out_dir, f"cathode-diagnostics-{time.strftime('%Y%m%d-%H%M%S')}.zip")
    cache = paths.cache_dir()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("system.txt", system_text(app))
        z.writestr("config.json", json.dumps(scrubbed(app.config), indent=2, default=str))
        for name in ("cathode.log", "cathode.log.1", "mpv.log"):
            p = os.path.join(cache, name)
            if os.path.isfile(p):
                try:
                    sys.stdout.flush()
                except Exception:
                    pass
                z.write(p, name)
    return path
