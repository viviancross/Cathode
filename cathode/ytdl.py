"""YouTube through yt-dlp, in-process: playlists resolved flat, a video
resolved to the stream URLs libmpv plays (video and audio apart, as YouTube
serves them), and yt-dlp itself kept fresh.

yt-dlp is pure Python, so it ships inside the bundle; YouTube changes break
it every few months, so a newer release (the zipapp GitHub publishes) can be
fetched into the cache and is imported ahead of the bundled copy at the next
start. No JavaScript runtime: without one yt-dlp uses YouTube's visionOS
client, whose streams need no challenge solving today; when that closes, a
runtime can be named in JS_RUNTIMES and the update brings the solver.

Everything here blocks on the network: callers thread it."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from typing import Optional

from . import paths
from .net import SSL as _SSL

RELEASES = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
ZIPAPP = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
JS_RUNTIMES: dict = {}          # e.g. {"quickjs": {"path": "..."}} when YouTube needs one again
PLAYLIST_TTL = 24 * 3600
FORMAT = ("bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]"
          "/bestvideo[height<=1080]+bestaudio/best")
_lock = threading.Lock()
_streams: dict = {}             # video id -> resolved stream, until it expires
_mod = None


def cache_dir() -> str:
    d = os.path.join(paths.cache_dir(), "ytdl")
    os.makedirs(d, exist_ok=True)
    return d


def _zip_path() -> str:
    return os.path.join(cache_dir(), "yt-dlp.zip")


def _load():
    """yt_dlp, the fetched zipapp ahead of the bundled package."""
    global _mod
    if _mod is None:
        z = _zip_path()
        if os.path.isfile(z) and z not in sys.path:
            sys.path.insert(0, z)
        import yt_dlp
        _mod = yt_dlp
    return _mod


def version() -> str:
    try:
        return _load().version.__version__
    except Exception as e:
        return f"missing ({e.__class__.__name__})"


def _ydl(**extra):
    y = _load()
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noprogress": True,
            "js_runtimes": dict(JS_RUNTIMES), "logger": _Quiet()}
    opts.update(extra)
    return y.YoutubeDL(opts)


class _Quiet:
    def debug(self, m): pass
    def info(self, m): pass
    def warning(self, m): pass
    def error(self, m): print(f"[ytdl] {m}")


def playlist_id(url: str) -> str:
    """The list id out of a YouTube playlist link (or the text as given)."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return (q.get("list") or [url.strip()])[0]


def playlist_url(url: str) -> str:
    u = url.strip()
    return u if "://" in u else f"https://www.youtube.com/playlist?list={u}"


def cached_playlist(url: str) -> Optional[dict]:
    """The playlist as last resolved, however old, or None."""
    p = os.path.join(cache_dir(), f"pl-{re.sub(r'[^A-Za-z0-9_-]', '_', playlist_id(url))}.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def playlist(url: str, max_age: float = PLAYLIST_TTL) -> dict:
    """{"id", "title", "fetched", "entries": [{"id", "title", "duration", "uploader"}]},
    from the cache while it's fresh, else resolved flat (one request, no
    per-video lookups) and cached."""
    pid = playlist_id(url)
    p = os.path.join(cache_dir(), f"pl-{re.sub(r'[^A-Za-z0-9_-]', '_', pid)}.json")
    old = cached_playlist(url)
    if old and time.time() - old.get("fetched", 0) < max_age:
        return old
    with _ydl(extract_flat=True) as y:
        r = y.extract_info(playlist_url(url), download=False)
    entries = [{"id": e["id"], "title": e.get("title") or "", "duration": float(e.get("duration") or 0),
                "uploader": e.get("uploader") or e.get("channel") or ""}
               for e in (r.get("entries") or []) if e.get("id")]
    out = {"id": pid, "title": r.get("title") or (old or {}).get("title", ""),
           "fetched": time.time(), "entries": entries}
    if not entries and old:
        return old                  # a bad answer keeps the last good list
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f)
    os.replace(tmp, p)
    return out


def stream(video_id: str) -> dict:
    """{"video", "audio" (or None), "headers", "expires", "title", "uploader"}
    for the video, kept until the URLs expire. Raises on a video that can't
    be played (removed, blocked, private)."""
    with _lock:
        s = _streams.get(video_id)
        if s and s["expires"] - time.time() > 120:
            return s
    with _ydl(format=FORMAT) as y:
        v = y.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    rf = v.get("requested_formats") or [v]
    expires = time.time() + 5 * 3600
    m = re.search(r"[?&]expire=(\d+)", rf[0].get("url", ""))
    if m:
        expires = min(expires, int(m.group(1)))
    s = {"video": rf[0]["url"], "audio": rf[1]["url"] if len(rf) > 1 else None,
         "headers": dict(rf[0].get("http_headers") or {}), "expires": expires,
         "title": v.get("title") or "", "uploader": v.get("uploader") or v.get("channel") or "",
         "duration": float(v.get("duration") or 0)}
    with _lock:
        if len(_streams) > 64:
            _streams.clear()
        _streams[video_id] = s
    return s


# ── Keeping yt-dlp fresh ─────────────────────────────────────────────────

def latest_version() -> str:
    """The newest yt-dlp release tag on GitHub."""
    req = urllib.request.Request(RELEASES, headers={"Accept": "application/vnd.github+json",
                                                    "User-Agent": "Cathode"})
    with urllib.request.urlopen(req, timeout=15, context=_SSL) as r:
        return json.loads(r.read()).get("tag_name", "")


def _vt(s: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", s))


def update() -> Optional[str]:
    """Fetch the newest yt-dlp zipapp into the cache when it's newer than
    what's running; the new one loads at the next start. Returns the version
    fetched, or None when already current. Raises on a failed fetch; a bad
    download never replaces a good one."""
    latest = latest_version()
    if not latest or _vt(latest) <= _vt(version()):
        return None
    req = urllib.request.Request(ZIPAPP, headers={"User-Agent": "Cathode"})
    tmp = _zip_path() + ".tmp"
    with urllib.request.urlopen(req, timeout=60, context=_SSL) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    import zipfile
    with zipfile.ZipFile(tmp) as z:          # a truncated or wrong file is thrown away
        if "yt_dlp/version.py" not in z.namelist():
            raise ValueError("not a yt-dlp release")
        got = re.search(r"__version__\s*=\s*'([^']+)'", z.read("yt_dlp/version.py").decode()).group(1)
    os.replace(tmp, _zip_path())
    return got
