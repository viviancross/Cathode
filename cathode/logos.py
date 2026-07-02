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


class LogoStore:
    _ORIG_MAX = 256      # full-size images kept in RAM (posters add up fast)
    _RESIZED_MAX = 1024  # fitted variants; cleared wholesale when exceeded
    _DISK_MAX = 400      # on-disk cache files; pruned oldest-first at startup

    def __init__(self, cache_dir: str, on_loaded: Optional[Callable] = None,
                 user_agent: str = "Cathode/1.0"):
        self.cache_dir = cache_dir
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except OSError:
            pass
        self._on_loaded = on_loaded
        self._ua = user_agent
        self._orig: Dict[str, Optional[Image.Image]] = {}   # url -> RGBA (None = failed)
        self._resized: Dict[Tuple[str, int, int], Optional[Image.Image]] = {}
        self._inflight = set()
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
    def _fit(im: Image.Image, max_w: int, max_h: int) -> Image.Image:
        w, h = im.size
        scale = min(max_w / w, max_h / h)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        return im.resize((nw, nh), Image.LANCZOS)

    def _ensure_fetch(self, url: str):
        with self._lock:
            if url in self._inflight or url in self._orig:
                return
            self._inflight.add(url)
        threading.Thread(target=self._fetch, args=(url,), daemon=True).start()

    def _disk_path(self, url: str) -> str:
        return os.path.join(self.cache_dir, hashlib.sha1(url.encode()).hexdigest())

    def _fetch(self, url: str):
        img = None
        try:
            path = self._disk_path(url)
            if os.path.exists(path):
                img = Image.open(path).convert("RGBA")
            elif url.startswith(("http://", "https://")):
                import urllib.request
                hdrs = {"User-Agent": self._ua}
                with self._lock:
                    hdrs.update(self._auth.get(url) or {})
                req = urllib.request.Request(url, headers=hdrs)
                data = urllib.request.urlopen(req, timeout=15).read()
                img = Image.open(BytesIO(data)).convert("RGBA")
                try:
                    with open(path, "wb") as f:
                        f.write(data)
                except OSError:
                    pass
            elif os.path.exists(url):                 # local file path
                img = Image.open(url).convert("RGBA")
        except Exception:
            img = None
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
