"""On Demand: the Plex library, the play queue, and the DVR (My Recordings).

Owns the Plex client and the download store. Everything that touches the
network runs on a worker thread; results come back through app.post, so the
screens only ever see them on the UI thread.
"""

import os
import threading
from typing import Callable, List, Optional

from . import plex
from .downloads import DownloadStore, default_dir

SORTS = [
    ("Default", ""),
    ("Title A-Z", "titleSort:asc"), ("Title Z-A", "titleSort:desc"),
    ("Newest release", "originallyAvailableAt:desc"),
    ("Oldest release", "originallyAvailableAt:asc"),
    ("Newest added", "addedAt:desc"), ("Oldest added", "addedAt:asc"),
    ("Newest year", "year:desc"), ("Oldest year", "year:asc"),
    ("Highest rated", "rating:desc"), ("Lowest rated", "rating:asc"),
]


def sort_label(val: str) -> str:
    return next((n for n, v in SORTS if v == val), "Default")


def plex_error_text(e: Exception) -> str:
    """A failed Plex request, in words for the couch (the raw error goes to
    the log)."""
    import urllib.error
    from .plex import PlexError
    if isinstance(e, PlexError):
        return str(e) or "Couldn't reach Plex."
    if isinstance(e, urllib.error.HTTPError):
        return "Plex sign-in has expired: link your account again." if e.code == 401 else             f"Plex refused that ({e.code})."
    if isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError)):
        return "Couldn't reach your Plex server."
    return "Plex sent something Cathode couldn't read."


def episode_queue(eps: list, rk) -> list:
    """Episodes from `rk` to the end of the show, or [] when `rk` isn't there
    or is the last one (nothing would follow it)."""
    keys = [str(e.get("rating_key", "")) for e in eps]
    try:
        i = keys.index(str(rk))
    except ValueError:
        return []
    return eps[i:] if i < len(eps) - 1 else []


def queue_entry(d: dict) -> dict:
    return {"rating_key": str(d.get("rating_key", "")), "title": d.get("title", "?"),
            "subtitle": d.get("subtitle") or d.get("meta", "")}


class Queue:
    """The play queue: filled automatically (Play All, keep playing this
    show) or by hand (+ QUEUE). A hand-built one is never silently dropped.
    `pos` is the entry playing now, -1 when loaded but idle."""

    def __init__(self):
        self.items: List[dict] = []
        self.pos = 0
        self.by_hand = False

    def replace(self, entries):
        self.items, self.pos, self.by_hand = list(entries), 0, False

    def add(self, entries) -> int:
        entries = [e for e in entries if e.get("rating_key")]
        self.items.extend(entries)
        if entries:
            self.by_hand = True
        return len(entries)

    def one_off(self):
        """Something is played outside the queue."""
        if self.by_hand:
            self.pos = -1          # keep it; the next skip starts it from the top
        else:
            self.items, self.pos = [], 0

    def move(self, i: int, d: int) -> int:
        j = i + d
        if not (0 <= i < len(self.items) and 0 <= j < len(self.items)):
            return i
        self.items[i], self.items[j] = self.items[j], self.items[i]
        if self.pos == i:
            self.pos = j
        elif self.pos == j:
            self.pos = i
        return j

    def remove(self, i: int):
        """Drop an entry. Removing the one playing doesn't stop it: the
        position steps back so the next advance lands on what moved up."""
        if not 0 <= i < len(self.items):
            return
        self.items.pop(i)
        if i <= self.pos:
            self.pos -= 1
        if not self.items:
            self.clear()

    def clear(self):
        self.items, self.pos, self.by_hand = [], 0, False

    def step(self, d: int) -> Optional[int]:
        """Index to play for next (+1) / previous (-1), or None off the end."""
        i = self.pos + d
        return i if 0 <= i < len(self.items) else None


class OnDemand:
    def __init__(self, app):
        self.app = app
        self._client = None
        self._lock = threading.Lock()
        self.queue = Queue()
        cfg = app.config
        # Not under the cache dir: a cache is something the system may throw
        # away. default_dir puts recordings with the user's other videos.
        from .paths import cache_dir
        root = cfg.download_dir or default_dir(os.path.join(cfg.data_dir() or cache_dir(),
                                                            "downloads"))
        self.downloads = DownloadStore(root, on_change=lambda: app.post(self._downloads_changed),
                                       user_agent=cfg.user_agent)
        self.downloads.refresh_url = self._dvr_source
        self.listeners: List[Callable] = []     # screens showing DVR state

    # ── Client ────────────────────────────────────────────────────────────

    @property
    def signed_in(self) -> bool:
        return bool(self.app.config.plex_token)

    def client(self) -> plex.PlexClient:
        """Thread-safe: built once per token, rebuilt after sign-in/out."""
        with self._lock:
            if self._client is None:
                cfg = self.app.config
                if not cfg.plex_client_id:
                    cfg.plex_client_id = plex.new_client_id()
                    cfg.save()
                from . import __version__
                self._client = plex.PlexClient(cfg.plex_client_id,
                                               token=cfg.plex_user_token or cfg.plex_token,
                                               admin_token=cfg.plex_token, version=__version__)
            self._client.version_pref = getattr(self.app.config, "plex_version", "first")
            return self._client

    def reset(self):
        with self._lock:
            self._client = None

    def run(self, work: Callable, done: Callable = None, fail: Callable = None):
        """work() on a thread; done(result) or fail(message) on the UI thread."""
        def go():
            try:
                result = work()
            except Exception as e:
                print(f"[ondemand] {e!r}")
                if fail:
                    self.app.post(fail, plex_error_text(e))
                return
            if done:
                self.app.post(done, result)
        threading.Thread(target=go, daemon=True).start()

    def unlink(self):
        cfg = self.app.config
        cfg.plex_token = cfg.plex_user_token = cfg.plex_user_id = cfg.plex_user_name = ""
        cfg.save()
        self.reset()

    def poster(self, path: str, w: int, h: int):
        """A poster as a pygame surface, fetched in the background."""
        if not path or not self.signed_in:
            return None
        c = self.client()
        if not c.server:
            return None
        return self.app.skin.logo(c.photo_url(path, w, h), w, h, headers=c.poster_headers())

    # ── The DVR ───────────────────────────────────────────────────────────

    def _downloads_changed(self):
        for fn in list(self.listeners):
            fn()
        self.app.invalidate()

    def dvr_label(self, rk) -> str:
        st = self.downloads.state(rk)
        return {"done": "RECORDED", "downloading": f"REC {self.downloads.percent(rk)}%",
                "queued": "REC WAIT", "paused": "RESUME", "error": "RETRY"}.get(st, "RECORD")

    def _dvr_source(self, rk):
        """(url, headers) for an item's original file; connects first when a
        resume arrives with no browse session behind it."""
        c = self.client()
        if not c.server:
            c.discover_server(prefer=self.app.config.plex_server_id)
        info = c.download_info(rk)
        return info["url"], info["headers"]

    def dvr_start(self, rk: str, title: str = ""):
        self.app.toast("Starting download...")

        def work():
            c = self.client()
            if not c.server:
                c.discover_server(prefer=self.app.config.plex_server_id)
            info = c.download_info(rk)
            self.downloads.add(info["detail"], info["url"], info["headers"],
                               size=info["size"], container=info["container"])
            return title or info["detail"].get("title", "")
        self.run(work, lambda name: self.app.toast(f"Recording: {name}"),
                 lambda msg: self.app.toast(msg, 5.0))

    # ── Reporting ─────────────────────────────────────────────────────────

    def report(self, rk: str, pos: float, dur: float, state: str, finished: bool = False):
        """Best-effort: tell the server where we are; scrobble a finish so it
        clears the resume point and marks the item watched."""
        if not rk or not self.signed_in:
            return

        def work():
            c = self.client()
            if not c.server:
                return
            c.report_timeline(rk, dur if finished and dur else pos, dur, state=state)
            if finished:
                c.scrobble(rk)
        threading.Thread(target=work, daemon=True).start()

    def remember_offset(self, rk: str, offset: int):
        """The DVR keeps its own resume point: offline there's no server to tell."""
        self.downloads.set_offset(rk, offset)

    # ── Playing ───────────────────────────────────────────────────────────

    def play(self, rk: str, title: str = "", subtitle: str = "", resume: bool = True,
             from_queue: bool = False):
        """Start an item: the downloaded copy if there is one, else the
        stream. Pushes the playback screen once the server answers."""
        from .screens.playback import Playback
        if not from_queue:
            self.queue.one_off()
        local = self.downloads.local_path(rk)

        def work():
            if local:
                detail = self.downloads.detail(rk) or {}
                return {"url": local, "time_base": 0, "markers": [], "headers": None,
                        "title": title or detail.get("title", ""), "subtitle": subtitle,
                        "duration": detail.get("duration", 0),
                        "offset": self.downloads.offset(rk) if resume else 0}
            return self.client().play_info(rk, self.app.config.plex_quality, resume=resume)

        def done(info):
            pb = self.app.find(Playback)
            if pb:
                pb.load(rk, info, title, subtitle)
            else:
                self.app.push(Playback(self.app, rk, info, title, subtitle))
        self.run(work, done, lambda msg: self.app.toast(msg, 5.0))

    def play_queue_at(self, i: int, resume: bool = False):
        if 0 <= i < len(self.queue.items):
            self.queue.pos = i
            e = self.queue.items[i]
            self.play(e["rating_key"], e.get("title", ""), e.get("subtitle", ""),
                      resume=resume, from_queue=True)

    def play_detail(self, detail: dict, resume: bool):
        """Play from an info page. An episode queues the rest of its show
        behind it, unless the queue was built by hand."""
        rk = detail.get("rating_key")
        title = detail.get("title", "")
        sub = detail.get("subtitle") or detail.get("meta", "")
        show = detail.get("grandparent_key")
        if detail.get("type") != "episode" or not show or self.queue.by_hand:
            self.play(rk, title, sub, resume=resume)
            return

        def work():
            try:
                return episode_queue(self.client().all_episodes(show), rk)
            except Exception:
                return []

        def done(eps):
            if eps:
                self.queue.replace([queue_entry(e) for e in eps])
                self.play_queue_at(0, resume=resume)
            else:
                self.play(rk, title, sub, resume=resume)
        self.run(work, done)

    def play_all(self, show_rk: str, shuffle: bool = False):
        def work():
            eps = self.client().all_episodes(show_rk)
            if shuffle:
                import random
                random.shuffle(eps)
            return eps

        def done(eps):
            if not eps:
                self.app.toast("No episodes to play")
                return
            self.queue.replace([queue_entry(e) for e in eps])
            self.play_queue_at(0)
        self.run(work, done, lambda msg: self.app.toast(msg, 5.0))

    def enqueue(self, detail: dict):
        """+ QUEUE: one item, or every episode of a series."""
        def added(entries):
            n = self.queue.add(entries)
            self.app.toast(f"Queued {n} episodes" if n > 1 else
                           f"Queued: {entries[0]['title']}" if n else "Nothing to queue")
        if detail.get("type") == "show":
            self.run(lambda: [queue_entry(e) for e in self.client().all_episodes(detail["rating_key"])],
                     added, lambda msg: self.app.toast(msg, 5.0))
        else:
            added([queue_entry(detail)])
