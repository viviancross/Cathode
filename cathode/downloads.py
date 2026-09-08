"""The DVR — local copies of Plex items, for when the server isn't there.

Plex-Per-View streams from a server that is unreachable on a plane, on a train,
or on hotel wifi that has decided today is not the day. A download is the same
original file, fetched once over HTTP and written next to the config, plus an
index entry holding the metadata the info screen needs — so a downloaded title
looks and plays exactly the same with the network off.

One worker, one file at a time: a phone does better with a single full-speed
transfer than six competing for the same pipe, and a part-file resumes with a
Range request rather than starting a four-gigabyte movie over.

The index deliberately holds no Plex token. Resuming a download after a restart
asks the server for a fresh URL, which costs one request and keeps the account's
credentials in exactly one file instead of two.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import urllib.request
from typing import Callable, Dict, List, Optional

from .net import SSL as _SSL

# States an entry can be in. "paused" is what an interrupted download becomes on
# the next launch: the bytes are still on disk, and selecting it resumes.
DONE, DOWNLOADING, QUEUED, PAUSED, ERROR = (
    "done", "downloading", "queued", "paused", "error")


def _xdg_videos() -> str:
    """The user's Videos directory as XDG records it, or "" if it doesn't.

    Reading `user-dirs.dirs` matters on a localised desktop, where the folder is
    named in the user's own language and guessing "Videos" produces a second,
    English-named one beside it.
    """
    path = os.path.join(
        os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
        "user-dirs.dirs")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("XDG_VIDEOS_DIR="):
                    val = line.split("=", 1)[1].strip().strip('"')
                    return os.path.expanduser(val.replace("$HOME", "~"))
    except OSError:
        pass
    return ""


def default_dir(fallback: str = "") -> str:
    """Where downloads go when the user hasn't named a directory.

    Videos belong with the user's other videos, not inside a config folder.
    Android keeps app data private so the config dir is right there, but on a
    desktop a multi-gigabyte film under ~/.config is somewhere nobody thinks to
    look and nobody thinks to clean up. Each platform has an established answer
    and this uses it: Movies on macOS, the XDG videos directory on Linux (which
    is localised, hence reading it rather than assuming), Videos on Windows.

    Falls back to `fallback` if that directory's parent doesn't exist, so a
    stripped-down system still gets somewhere to write.
    """
    import sys
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        base = os.path.join(home, "Movies")
    elif os.name == "nt":
        base = os.path.join(os.environ.get("USERPROFILE", home), "Videos")
    else:
        base = _xdg_videos() or os.path.join(home, "Videos")
    if os.path.isdir(os.path.dirname(base)):
        return os.path.join(base, "Cathode")
    return fallback or os.path.join(home, "Cathode")


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))[:64] or "item"


class _Interrupted(Exception):
    """The transfer stopped early and every byte of it is still good."""


class _Fatal(Exception):
    """Retrying will not help: no file to fetch, or nowhere to put it."""


class DownloadStore:
    CHUNK = 256 * 1024
    # Never fill the last of the disk; a phone with no free space stops being a
    # phone. Checked against the size the server reports before the first byte.
    HEADROOM = 200 * 1024 * 1024
    # Seconds to wait before each retry of an interrupted transfer, and how many
    # there are. Short enough to ride out a lift or a station platform, finite
    # so a download that is simply not coming back stops asking.
    RETRY_BACKOFF = (5, 20, 60)

    def __init__(self, root: str, on_change: Optional[Callable] = None,
                 user_agent: str = "Cathode/1.0"):
        self.root = root
        self._on_change = on_change
        self._ua = user_agent
        self._lock = threading.RLock()
        self._items: Dict[str, dict] = {}      # rating_key -> entry
        self._order: List[str] = []            # rating_keys, newest first
        self._queue: List[str] = []
        self._auth: Dict[str, dict] = {}       # rating_key -> request headers
        self._urls: Dict[str, str] = {}        # rating_key -> source URL
        self._poster_src: Dict[str, tuple] = {}   # rating_key -> (url, headers)
        self._cancel = set()
        self._interrupted = set()   # paused by the network, not by the user
        self._retries = {}          # rating_key -> retries already spent
        self._worker = None
        self._active = False
        # Set by the host. on_active(True/False) brackets a run of downloads, so
        # a platform that would otherwise freeze or evict a backgrounded process
        # can be told to hold it open. refresh_url(rk) -> (url, headers) re-derives
        # a source for an entry this process has no URL for.
        self.on_active = None
        self.refresh_url = None
        try:
            os.makedirs(root, exist_ok=True)
        except OSError:
            pass
        self._load()

    # ── index ─────────────────────────────────────────────────────────────

    @property
    def _index_path(self) -> str:
        return os.path.join(self.root, "index.json")

    def _load(self):
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        for e in data.get("items", []):
            rk = str(e.get("rating_key") or "")
            if not rk:
                continue
            # Anything that was mid-flight when the app closed is paused, not
            # resumed: a download that restarts itself over cellular the moment
            # the app opens is a bill, not a feature.
            if e.get("state") in (DOWNLOADING, QUEUED):
                e["state"] = PAUSED
            if e.get("state") == DONE:
                p = os.path.join(self.root, e.get("file", ""))
                if not os.path.exists(p):
                    continue                  # file deleted behind our back
                size = int(e.get("size") or 0)
                if size and os.path.getsize(p) != size:
                    # Finished on paper, short on disk — a crash between the
                    # rename and the save. Better found here than halfway
                    # through the film.
                    e["state"] = PAUSED
                    try:
                        os.replace(p, p + ".part")
                    except OSError:
                        pass
            self._items[rk] = e
            self._order.append(rk)

    def _save(self):
        with self._lock:
            items = [self._items[rk] for rk in self._order if rk in self._items]
        tmp = f"{self._index_path}.{os.getpid()}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"items": items}, f, indent=2)
            os.replace(tmp, self._index_path)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def _changed(self):
        if self._on_change:
            try:
                self._on_change()
            except Exception:
                pass

    # ── queries ───────────────────────────────────────────────────────────

    def state(self, rk) -> str:
        e = self._items.get(str(rk))
        return e.get("state", "") if e else ""

    def percent(self, rk) -> int:
        return self._pct(self._items.get(str(rk)) or {})

    @staticmethod
    def _pct(e: dict) -> int:
        total = int(e.get("size") or 0)
        if total <= 0:
            return 0
        return max(0, min(100, int(int(e.get("got") or 0) * 100 / total)))

    def local_path(self, rk) -> str:
        """The playable file for `rk`, or "" if it isn't downloaded."""
        e = self._items.get(str(rk))
        if not e or e.get("state") != DONE:
            return ""
        p = os.path.join(self.root, e.get("file", ""))
        return p if os.path.exists(p) else ""

    def offset(self, rk) -> int:
        e = self._items.get(str(rk))
        return int(e.get("offset") or 0) if e else 0

    def set_offset(self, rk, offset: int):
        """Remember a resume point locally. Offline there is no server to tell."""
        e = self._items.get(str(rk))
        if e is None:
            return
        e["offset"] = max(0, int(offset))
        self._save()

    def items(self) -> List[dict]:
        """Browse rows for the DOWNLOADS list, newest first."""
        with self._lock:
            return [self._row(self._items[rk])
                    for rk in self._order if rk in self._items]

    def _row(self, e: dict) -> dict:
        st = e.get("state", "")
        meta = e.get("meta", "")
        if st == DOWNLOADING:
            meta = f"{self._pct(e)}%"
        elif st == QUEUED:
            meta = "QUEUED"
        elif st == PAUSED:
            meta = f"PAUSED {self._pct(e)}%"
        elif st == ERROR:
            meta = "FAILED"
        return {"type": "download", "rating_key": e["rating_key"],
                "title": e.get("title", "?"), "meta": meta,
                "playable": st == DONE, "state": st,
                "offset": int(e.get("offset") or 0)}

    def detail(self, rk) -> Optional[dict]:
        """An info-screen detail dict built from the index — no server needed.

        Shaped like PlexClient.item_detail so the info screen can't tell the
        difference. The poster is a local file path, which LogoStore loads the
        same way it loads a URL.
        """
        e = self._items.get(str(rk))
        if e is None:
            return None
        poster = os.path.join(self.root, e["poster"]) if e.get("poster") else ""
        return {
            "rating_key": str(rk), "title": e.get("title", "?"),
            "subtitle": e.get("subtitle", ""), "summary": e.get("summary", ""),
            "duration": int(e.get("duration") or 0),
            "offset": int(e.get("offset") or 0),
            "poster": poster if poster and os.path.exists(poster) else "",
            "poster_headers": {}, "guid": "", "type": e.get("type", ""),
            "grandparent_key": "",
        }

    # ── writes ────────────────────────────────────────────────────────────

    def add(self, detail: dict, url: str, headers: Optional[dict] = None,
            size: int = 0, container: str = ""):
        """Queue `detail` for download from `url`. Re-adding a paused or failed
        entry resumes it: the part-file on disk is what a Range request asks the
        server to continue from."""
        rk = str(detail.get("rating_key") or "")
        if not rk or not url:
            return
        with self._lock:
            e = self._items.get(rk)
            if e is not None and e.get("state") in (DONE, DOWNLOADING, QUEUED):
                return                        # already here, or already coming
            if e is None:
                ext = container or os.path.splitext(
                    url.split("?")[0])[1].lstrip(".") or "mkv"
                e = {
                    "rating_key": rk,
                    "title": detail.get("title", "?"),
                    "subtitle": detail.get("subtitle", ""),
                    "summary": detail.get("summary", ""),
                    "duration": int(detail.get("duration") or 0),
                    "type": detail.get("type", ""),
                    "meta": detail.get("meta", ""),
                    "file": f"{_safe_name(rk)}.{_safe_name(ext)}",
                    "poster": "", "size": int(size or 0), "got": 0,
                    "offset": int(detail.get("offset") or 0),
                    "state": QUEUED, "added": time.time(),
                }
                self._items[rk] = e
                self._order.insert(0, rk)
            else:
                e["state"] = QUEUED
                e.pop("error", None)
                if size:
                    e["size"] = int(size)
            self._cancel.discard(rk)
            self._urls[rk] = url
            self._auth[rk] = dict(headers or {})
            if detail.get("poster"):
                self._poster_src[rk] = (detail["poster"],
                                        dict(detail.get("poster_headers") or {}))
            if rk not in self._queue:
                self._queue.append(rk)
            self._start_worker()
        self._save()
        self._changed()

    def cancel(self, rk):
        """Stop a download in flight, keeping what has already been fetched."""
        rk = str(rk)
        with self._lock:
            self._cancel.add(rk)
            # Stopped on purpose, so resume() must leave it alone — that call
            # exists to undo what the network did, not what the user did.
            self._interrupted.discard(rk)
            self._retries.pop(rk, None)
            if rk in self._queue:
                self._queue.remove(rk)
            e = self._items.get(rk)
            if e is not None and e.get("state") in (QUEUED, DOWNLOADING):
                e["state"] = PAUSED
        self._save()
        self._changed()

    def remove(self, rk):
        """Delete a download and everything on disk that belongs to it."""
        rk = str(rk)
        self.cancel(rk)
        with self._lock:
            e = self._items.pop(rk, None)
            if rk in self._order:
                self._order.remove(rk)
            self._urls.pop(rk, None)
            self._auth.pop(rk, None)
        if e is not None:
            for name in (e.get("file", ""), e.get("file", "") + ".part",
                         e.get("poster", "")):
                if not name:
                    continue
                try:
                    os.remove(os.path.join(self.root, name))
                except OSError:
                    pass
        self._save()
        self._changed()

    def bytes_used(self) -> int:
        total = 0
        try:
            for f in os.listdir(self.root):
                p = os.path.join(self.root, f)
                if os.path.isfile(p):
                    total += os.path.getsize(p)
        except OSError:
            pass
        return total

    # ── the worker ────────────────────────────────────────────────────────

    def _start_worker(self):
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._pump, daemon=True,
                                            name="cathode-dvr")
            self._worker.start()

    def _pump(self):
        self._set_active(True)
        try:
            while True:
                with self._lock:
                    if not self._queue:
                        self._worker = None
                        return
                    rk = self._queue.pop(0)
                    e = self._items.get(rk)
                    if e is None or rk in self._cancel:
                        continue
                    e["state"] = DOWNLOADING
                self._changed()
                try:
                    self._fetch_poster(rk)
                    self._fetch(rk)
                except _Fatal as ex:
                    self._mark(rk, ERROR, ex)
                except Exception as ex:
                    # Everything else is the network or the host getting in the
                    # way, and the bytes already on disk are still good. Pause
                    # rather than fail: a failed download needs the user to come
                    # back and clean up after it, and none of this was their
                    # doing.
                    self._interrupt(rk, ex)
                    return
        finally:
            self._set_active(False)

    def _mark(self, rk, state, ex=None):
        with self._lock:
            e = self._items.get(rk)
            if e is not None and e.get("state") == DOWNLOADING:
                e["state"] = state
                if ex is not None:
                    e["error"] = str(ex)[:120]
        self._save()
        self._changed()

    def _interrupt(self, rk, ex):
        """Stop the whole run, keeping every byte already fetched.

        The rest of the queue is going to meet the same dead network, and
        marking three more items FAILED in the two seconds after the first one
        died is just noise the user has to clear up. They stay paused, and
        resume() puts them back — either on a timer, or when the app next comes
        to the foreground, whichever happens first.
        """
        with self._lock:
            for other in ([rk] + list(self._queue)):
                e = self._items.get(other)
                if e is not None and e.get("state") in (DOWNLOADING, QUEUED):
                    e["state"] = PAUSED
                    if other == rk and ex is not None:
                        e["error"] = str(ex)[:120]
                    self._interrupted.add(other)
            self._queue.clear()
            self._worker = None
            # A phone walking into a lift should not need the user to come back
            # and press anything. Give up after the last delay: past that it is
            # not a blip, and retrying every minute all night is a battery bill.
            n = self._retries.get(rk, 0)
            if n < len(self.RETRY_BACKOFF):
                self._retries[rk] = n + 1
                t = threading.Timer(self.RETRY_BACKOFF[n], self.resume)
                t.daemon = True
                t.start()
        self._save()
        self._changed()

    def _set_active(self, on: bool):
        if self._active == on:
            return
        self._active = on
        if self.on_active:
            try:
                self.on_active(on)
            except Exception:
                pass

    def resume(self):
        """Re-queue everything that stopped on its own.

        Only what was interrupted: a download the user pressed Stop on stays
        stopped, and one paused since a previous launch waits to be asked. Safe
        to call as often as you like — the app calls it every time it comes
        back to the foreground, which is the moment a host that froze the
        process has just unfrozen it.
        """
        with self._lock:
            back = [rk for rk in self._order
                    if rk in self._interrupted
                    and self._items.get(rk, {}).get("state") == PAUSED]
            for rk in back:
                self._items[rk]["state"] = QUEUED
                self._items[rk].pop("error", None)
                self._cancel.discard(rk)
                if rk not in self._queue:
                    self._queue.append(rk)
            if back:
                self._start_worker()
        if back:
            self._save()
            self._changed()
        return len(back)

    def _fetch_poster(self, rk: str):
        src = self._poster_src.get(rk)
        e = self._items.get(rk)
        if not src or e is None or e.get("poster"):
            return
        url, headers = src
        name = f"{_safe_name(rk)}.poster"
        try:
            hdrs = {"User-Agent": self._ua}
            hdrs.update(headers or {})
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=20, context=_SSL) as r:
                data = r.read()
            with open(os.path.join(self.root, name), "wb") as f:
                f.write(data)
            e["poster"] = name
            self._save()
        except Exception:
            pass          # art is a nicety; the file is the point

    def _source(self, rk: str):
        """(url, headers) for `rk`, asking the app for a fresh one if this
        process has none. The index holds no token, so a download resumed after
        a restart has to be re-derived from the server rather than replayed."""
        url = self._urls.get(rk, "")
        if url:
            return url, dict(self._auth.get(rk) or {})
        if self.refresh_url:
            try:
                url, headers = self.refresh_url(rk)
            except Exception as ex:
                raise _Interrupted(f"Couldn't reach the server ({ex})") from ex
            if url:
                with self._lock:
                    self._urls[rk] = url
                    self._auth[rk] = dict(headers or {})
                return url, dict(headers or {})
        raise _Fatal("No source for this download.")

    def _fetch(self, rk: str):
        e = self._items[rk]
        url, auth = self._source(rk)
        dest = os.path.join(self.root, e["file"])
        part = dest + ".part"
        got = os.path.getsize(part) if os.path.exists(part) else 0
        hdrs = {"User-Agent": self._ua}
        hdrs.update(auth)
        if got:
            hdrs["Range"] = f"bytes={got}-"
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=30, context=_SSL) as r:
            code = getattr(r, "status", None) or r.getcode()
            if got and code != 206:
                got = 0                       # server ignored the range
            length = int(r.headers.get("Content-Length") or 0)
            total = length + got if length else int(e.get("size") or 0)
            if total:
                e["size"] = total
                free = shutil.disk_usage(self.root).free
                if total - got > free - self.HEADROOM:
                    raise _Fatal("Not enough free space.")
            e["got"] = got
            last = -1
            with open(part, "ab" if got else "wb") as f:
                while True:
                    if rk in self._cancel:
                        self._changed()
                        return
                    buf = r.read(self.CHUNK)
                    if not buf:
                        break
                    f.write(buf)
                    got += len(buf)
                    e["got"] = got
                    pct = self._pct(e)
                    if pct != last:           # a repaint per percent, not per chunk
                        last = pct
                        self._changed()
        # read() returning b"" is what a finished download looks like AND what a
        # connection dropped mid-transfer looks like — the socket just ends. The
        # byte count is the only thing that tells them apart, so a short file is
        # never promoted out of .part. Getting this wrong is how an interrupted
        # download came to sit in the list saying ON DVR while being half a film.
        expected = int(e.get("size") or 0)
        if expected and got < expected:
            raise _Interrupted(f"stopped at {got:,} of {expected:,} bytes")
        os.replace(part, dest)
        e["state"] = DONE
        e["got"] = os.path.getsize(dest)
        if not expected:
            e["size"] = e["got"]        # no size was ever advertised
        e.pop("error", None)
        self._interrupted.discard(rk)
        self._retries.pop(rk, None)
        self._save()
        self._changed()
