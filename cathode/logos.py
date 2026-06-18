"""Channel logo fetching and caching.

Logos come from XMLTV <icon> URLs (or the M3U tvg-logo). They're fetched lazily
on a background thread, cached on disk and in memory, and resized to fit on
request; the first request for an uncached logo returns None and starts a fetch,
calling on_loaded when it's ready.

Animated logos (GIF / APNG) are decoded frame by frame, and get() returns the
frame for the current time so a repeated render plays the animation.
"""

from __future__ import annotations

import bisect
import hashlib
import os
import threading
import time
from io import BytesIO
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageSequence

# An animation: parallel lists of RGBA frames and their cumulative end-times (s),
# plus the total loop length (s).
Anim = Tuple[List[Image.Image], List[float], float]


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
        self._anim: Dict[str, Anim] = {}                    # url -> animated frames
        self._resized: Dict[Tuple, Optional[Image.Image]] = {}
        self._inflight = set()
        self._has_anim = False
        self._lock = threading.Lock()

    def has_animation(self) -> bool:
        """True once any loaded logo is animated (so the renderer keeps ticking)."""
        return self._has_anim

    def get(self, url: str, max_w: int, max_h: int) -> Optional[Image.Image]:
        """A logo resized to fit (max_w, max_h), or None if unavailable / still
        loading.  For animated logos, returns the frame for the current time.
        Triggers a background fetch on first request."""
        if not url or max_w < 2 or max_h < 2:
            return None
        w, h = int(max_w), int(max_h)
        with self._lock:
            fetched = url in self._orig or url in self._anim
            anim = self._anim.get(url)
            orig = self._orig.get(url)
            cached = self._resized.get((url, w, h))
        if not fetched:
            self._ensure_fetch(url)
            return None
        if anim is not None:
            return self._anim_frame(url, anim, w, h)
        if cached is not None:
            return cached
        if orig is None:
            return None
        fitted = self._fit(orig, w, h)
        with self._lock:
            self._resized[(url, w, h)] = fitted
        return fitted

    def _anim_frame(self, url: str, anim: Anim, w: int, h: int) -> Image.Image:
        frames, cum, total = anim
        t = time.monotonic() % total if total > 0 else 0.0
        idx = min(bisect.bisect_right(cum, t), len(frames) - 1)
        key = (url, w, h, idx)
        with self._lock:
            f = self._resized.get(key)
            if f is not None:
                return f
        fitted = self._fit(frames[idx], w, h)
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
            if url in self._inflight or url in self._orig or url in self._anim:
                return
            self._inflight.add(url)
        threading.Thread(target=self._fetch, args=(url,), daemon=True).start()

    def _disk_path(self, url: str) -> str:
        return os.path.join(self.cache_dir, hashlib.sha1(url.encode()).hexdigest())

    @staticmethod
    def _decode(src: Image.Image) -> Tuple[Optional[Image.Image], Optional[Anim]]:
        """Returns (static_rgba, None) for a single-frame image, or
        (first_frame, anim) when the source has multiple frames."""
        if getattr(src, "n_frames", 1) <= 1:
            return src.convert("RGBA"), None
        frames: List[Image.Image] = []
        cum: List[float] = []
        t = 0.0
        for fr in ImageSequence.Iterator(src):
            frames.append(fr.convert("RGBA"))
            try:
                dur = float(fr.info.get("duration", 100))
            except (TypeError, ValueError):
                dur = 100.0
            t += max(20.0, dur) / 1000.0      # seconds; floor each frame at 20ms
            cum.append(t)
        if len(frames) <= 1:
            return (frames[0] if frames else src.convert("RGBA")), None
        return frames[0], (frames, cum, t)

    def _fetch(self, url: str):
        src = None
        try:
            path = self._disk_path(url)
            if os.path.exists(path):
                src = Image.open(path)
            elif url.startswith(("http://", "https://")):
                import urllib.request
                req = urllib.request.Request(url, headers={"User-Agent": self._ua})
                data = urllib.request.urlopen(req, timeout=15).read()
                src = Image.open(BytesIO(data))
                try:                            # cache raw bytes (keeps animation)
                    with open(path, "wb") as f:
                        f.write(data)
                except OSError:
                    pass
            elif os.path.exists(url):           # local file path
                src = Image.open(url)
        except Exception:
            src = None

        static_img: Optional[Image.Image] = None
        anim: Optional[Anim] = None
        if src is not None:
            try:
                static_img, anim = self._decode(src)
            except Exception:
                static_img, anim = None, None

        with self._lock:
            if anim is not None:
                self._anim[url] = anim
                self._has_anim = True
            else:
                self._orig[url] = static_img    # RGBA image, or None on failure
            self._inflight.discard(url)
        if (static_img is not None or anim is not None) and self._on_loaded:
            try:
                self._on_loaded()
            except Exception:
                pass
