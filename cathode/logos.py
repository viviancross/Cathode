"""Channel logo fetching and caching.

Logos come from XMLTV <icon> URLs (or the M3U tvg-logo). They're fetched lazily
on a background thread, cached on disk and in memory, and resized to fit on
request; the first request for an uncached logo returns None and starts a fetch,
calling on_loaded when it's ready.
"""

from __future__ import annotations

import hashlib
import os
import threading
from io import BytesIO
from typing import Callable, Dict, Optional, Tuple

from PIL import Image

from .net import SSL


def _read_capped(resp, limit: int) -> Optional[bytes]:
    """Read at most `limit` bytes; None if the response is bigger than that.

    A timeout bounds how long a fetch can stall, not how much it can send. Logo
    URLs are third-party data — they arrive in XMLTV <icon src> and M3U
    tvg-logo attributes, from playlists people download from IPTV providers —
    so one entry pointing at a huge file would otherwise be read whole into
    memory, on a thread per URL, and then written to the disk cache.
    """
    chunks, total = [], 0
    while True:
        chunk = resp.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


class Animation:
    """An animated logo: its frames (RGBA) and how long each shows, in
    seconds, played at the file's own rate. A delay of 10 ms or less reads
    as 100 ms, as browsers play it (such files are made for that)."""

    def __init__(self, frames, durations):
        self.frames = frames
        self.durations = [d if d > 0.01 else 0.1 for d in durations]
        self.total = sum(self.durations)

    @property
    def size(self):
        return self.frames[0].size

    def at(self, t: float) -> Tuple[int, float]:
        """(the frame showing at time t, seconds until the next one)."""
        t %= self.total
        for i, d in enumerate(self.durations):
            if t < d:
                return i, d - t
            t -= d
        return 0, self.durations[0]


class LogoStore:
    _ORIG_MAX = 256      # full-size images kept in RAM (posters add up fast)
    _RESIZED_MAX = 1024  # fitted variants; cleared wholesale when exceeded
    _DISK_MAX = 400      # on-disk cache files; pruned oldest-first at startup
    # A channel logo or a poster is tens of kilobytes; 8 MB is already absurd
    # for one, and is the point at which we stop rather than find out.
    _MAX_BYTES = 8 * 1024 * 1024
    # Decoded size, which is the number that actually costs memory: a small
    # file can decode to an enormous bitmap (a "decompression bomb"), and
    # Pillow's own default only warns. 50 MP is ~200 MB as RGBA: real channel
    # art gets close (a Tunarr upload measured 8098x5430), so anything over
    # _BIG decodes one at a time, and what's kept is cut to _KEEP a side
    # (nothing is drawn bigger).
    _MAX_PIXELS = 50_000_000
    _BIG = 16_000_000
    _KEEP = 1024
    _big = threading.Lock()
    _MAX_FRAMES = 1000       # an animated logo's frames kept (the pixel budget usually binds first)

    def __init__(self, cache_dir: str, on_loaded: Optional[Callable] = None,
                 user_agent: str = "Cathode/1.0"):
        self.cache_dir = cache_dir
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except OSError:
            pass
        self._on_loaded = on_loaded
        self._ua = user_agent
        self._orig: Dict[str, Optional[Image.Image]] = {}   # url -> RGBA or Animation (None = failed)
        self._resized: Dict[Tuple[str, int, int], Optional[Image.Image]] = {}
        self._inflight = set()
        self._later: Dict[str, float] = {}  # url -> when to ask again (the server said not now)
        self._auth: Dict[str, dict] = {}    # url -> extra request headers (e.g. Plex token)
        self._lock = threading.Lock()
        threading.Thread(target=self._prune_disk, daemon=True).start()

    def _prune_disk(self):
        """Trim the on-disk cache to _DISK_MAX files, oldest (mtime) first, so
        years of channel logos + Plex posters can't grow it without bound."""
        try:
            files = [os.path.join(self.cache_dir, f)
                     for f in os.listdir(self.cache_dir)]
            files = [f for f in files if os.path.isfile(f)]
            if len(files) <= self._DISK_MAX:
                return
            files.sort(key=os.path.getmtime)
            for p in files[:len(files) - self._DISK_MAX]:
                try:
                    os.remove(p)
                except OSError:
                    pass
        except OSError:
            pass

    def get(self, url: str, max_w: int, max_h: int,
            headers: Optional[dict] = None) -> Optional[Image.Image]:
        """A logo resized to fit (max_w, max_h), or None if unavailable / still
        loading. Triggers a background fetch on first request. `headers` (e.g. a
        Plex auth token) are sent with the fetch but kept OUT of the URL / cache
        key, so the token never lands in the URL or the on-disk cache name."""
        if not url or max_w < 2 or max_h < 2:
            return None
        if headers:
            with self._lock:
                self._auth[url] = headers
        key = (url, int(max_w), int(max_h))
        with self._lock:
            if key in self._resized:
                return self._resized[key]
            orig = self._orig.get(url, "?")
        if orig == "?":
            self._ensure_fetch(url)
            return None
        if orig is None:
            return None
        fitted = self._fit(orig, max_w, max_h)
        with self._lock:
            if len(self._resized) >= self._RESIZED_MAX:
                self._resized.clear()   # ponytail: crude cap; re-fits are cheap
            self._resized[key] = fitted
        return fitted

    @staticmethod
    def _fit(im, max_w: int, max_h: int):
        if isinstance(im, Animation):
            return Animation([LogoStore._fit(f, max_w, max_h) for f in im.frames], im.durations)
        w, h = im.size
        scale = min(max_w / w, max_h / h)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        return im.resize((nw, nh), Image.LANCZOS)

    def _ensure_fetch(self, url: str):
        import time
        with self._lock:
            if url in self._inflight or url in self._orig or self._later.get(url, 0) > time.monotonic():
                return
            self._inflight.add(url)
        threading.Thread(target=self._fetch, args=(url,), daemon=True).start()

    def _disk_path(self, url: str) -> str:
        return os.path.join(self.cache_dir, hashlib.sha1(url.encode()).hexdigest())

    def _decode(self, im) -> Optional[Image.Image]:
        """Decode to RGBA, refusing anything absurdly large.

        `Image.open` is lazy — it reads the header and nothing else — so the
        dimensions can be checked BEFORE any pixels are allocated, which is the
        only point at which refusing is still cheap.
        """
        w, h = im.size
        if w <= 0 or h <= 0 or w * h > self._MAX_PIXELS:
            return None
        if w * h > self._BIG:
            with self._big:
                return self._decode_now(im, w, h)
        return self._decode_now(im, w, h)

    def _decode_now(self, im, w, h):
        n = getattr(im, "n_frames", 1)
        if n > 1:
            # Animated: every frame, within the frame cap and the same pixel
            # budget a still image gets (frames x size).
            n = min(n, self._MAX_FRAMES, max(1, self._MAX_PIXELS // (w * h)))
            frames, durations = [], []
            for i in range(n):
                im.seek(i)
                frames.append(im.convert("RGBA"))
                durations.append((im.info.get("duration") or 100) / 1000)
            return Animation(frames, durations) if len(frames) > 1 else frames[0]
        out = im.convert("RGBA")
        if max(w, h) > self._KEEP:
            out.thumbnail((self._KEEP, self._KEEP), Image.LANCZOS)
        return out

    def _fetch(self, url: str):
        img = None
        try:
            path = self._disk_path(url)
            if os.path.exists(path):
                img = self._decode(Image.open(path))
            elif url.startswith(("http://", "https://")):
                import urllib.request
                hdrs = {"User-Agent": self._ua}
                with self._lock:
                    hdrs.update(self._auth.get(url) or {})
                req = urllib.request.Request(url, headers=hdrs)
                with urllib.request.urlopen(req, timeout=15, context=SSL) as resp:
                    data = _read_capped(resp, self._MAX_BYTES)
                if data is None:
                    raise ValueError("logo exceeds the size cap")
                img = self._decode(Image.open(BytesIO(data)))
                # Only cache what actually decoded: caching first would fill
                # the disk with whatever a bad URL happened to return.
                if img is not None:
                    try:
                        with open(path, "wb") as f:
                            f.write(data)
                    except OSError:
                        pass
            elif os.path.exists(url):                 # local file path
                img = self._decode(Image.open(url))
        except Exception as e:
            print(f"[logos] couldn't load {url.split('?')[0]}: {e!r}")
            img = None
            import time
            import urllib.error
            code = getattr(e, "code", None)
            if code in (429, 500, 502, 503, 504) or (code is None and isinstance(e, (urllib.error.URLError, OSError))):
                with self._lock:                # (too many asks, or the network: again in a minute)
                    self._later[url] = time.monotonic() + 60
                    self._inflight.discard(url)
                return
        with self._lock:
            self._orig[url] = img
            while len(self._orig) > self._ORIG_MAX:
                # dicts iterate in insertion order — evict the oldest; an
                # evicted image reloads from the disk cache on next request.
                self._orig.pop(next(iter(self._orig)))
            self._inflight.discard(url)
        if img is not None and self._on_loaded:
            try:
                self._on_loaded()
            except Exception:
                pass


# ── Whose logo a channel wears ───────────────────────────────────────────
# Yours first: a file in the settings folder's logos folder named for the
# channel (its name or number: "Nickelodeon.gif", "107.png"; "<name> bug.png"
# for its screen bug), or the one picked on its edit page. Then the guide's,
# then the channel's own (the playlist's; a starter network's real logo; a
# 24/7's title art from Plex).

EXTS = (".png", ".apng", ".gif", ".webp", ".jpg", ".jpeg")
_listing = {"dir": None, "at": 0.0, "files": {}}


def _key(s: str) -> str:
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().casefold().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "", s)


def folder(config) -> str:
    """The settings folder's logos folder ("" with no settings folder: never
    the cache's, which is pruned)."""
    d = config.data_dir()
    return os.path.join(d, "logos") if d else ""


def files(config) -> dict:
    """The logos folder's pictures by their names' letters and digits (a
    look at the folder every few seconds at most: a file dropped in shows
    up without a restart)."""
    import time
    d = folder(config)
    if _listing["dir"] == d and time.monotonic() - _listing["at"] < 3.0:
        return _listing["files"]
    out = {}
    try:
        if not d:
            raise OSError("no settings folder")
        for fn in os.listdir(d):
            stem, ext = os.path.splitext(fn)
            if ext.lower() in EXTS and os.path.isfile(os.path.join(d, fn)):
                out[_key(stem)] = os.path.join(d, fn)
    except OSError:
        pass
    _listing.update(dir=d, at=time.monotonic(), files=out)
    return out


def custom(config, ch, kind: str = "logo") -> str:
    """Your picture for a channel's logo (kind "logo") or screen bug ("bug"):
    the one picked on its edit page ("off": no bug), else one in the logos
    folder named for it; "" when there isn't one."""
    pick = ((getattr(config, "channel_edits", None) or {}).get(ch.url) or {}).get(kind) or ""
    if pick:
        return pick if pick == "off" or "/" in pick or "\\" in pick else os.path.join(folder(config), pick)
    fs = files(config)
    tail = " bug" if kind == "bug" else ""
    for name in dict.fromkeys((ch.name, getattr(ch, "orig", (ch.name,))[0], f"{ch.number:g}")):
        p = fs.get(_key(name + tail))
        if p:
            return p
    return ""


def url_for(app, ch, kind: str = "logo") -> str:
    """Where a channel's logo (or its screen bug) comes from; "" for none."""
    if ch is None:
        return ""
    cfg = app.config
    mine = custom(cfg, ch, kind)
    if kind == "bug":
        return "" if mine == "off" else mine or url_for(app, ch)
    if mine:
        return mine
    epg = getattr(app, "epg", None)
    url = (epg.icon_url(epg.resolve_channel_id(ch.epg_id, ch.name)) if epg else "") or ch.logo or ""
    if url.startswith("asset:"):            # one that comes with Cathode (the starter lineup's)
        from .paths import asset
        return asset(*url[6:].split("/"))
    if url.startswith("/library/"):         # a show's title art on the Plex server
        od = getattr(app, "ondemand", None)
        c = od.client() if od is not None and getattr(od, "signed_in", False) else None
        url = c.photo_url(url, 600, 300) if c is not None and c.server else ""
    return url
