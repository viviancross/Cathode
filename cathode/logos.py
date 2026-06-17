"""Channel logo fetching + caching.

Logos come from XMLTV <icon> URLs (or M3U tvg-logo as a fallback).  They're
fetched lazily on a background thread, cached on disk and in memory, and resized
to fit on request.  The first request for an uncached logo returns None and
kicks off a fetch; when it completes, `on_loaded` is called so the UI repaints.
"""

from __future__ import annotations

import hashlib
import os
import threading
from io import BytesIO
from typing import Callable, Dict, Optional, Tuple

from PIL import Image


class LogoStore:
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
        self._lock = threading.Lock()

    def get(self, url: str, max_w: int, max_h: int) -> Optional[Image.Image]:
        """A logo resized to fit (max_w, max_h), or None if unavailable / still
        loading.  Triggers a background fetch on first request."""
        if not url or max_w < 2 or max_h < 2:
            return None
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
                req = urllib.request.Request(url, headers={"User-Agent": self._ua})
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
            self._inflight.discard(url)
        if img is not None and self._on_loaded:
            try:
                self._on_loaded()
            except Exception:
                pass
