"""Where a programme can break, for mid-show breaks at chapter marks and at
quiet moments: a title's chapter starts (asked of Plex) and its silences
(found by reading its sound once with libmpv's silencedetect, a few seconds
a title). Kept in the cache folder; a title is read once, in the background,
for the channels that break that way. A title not read yet breaks halfway.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Optional

from . import library

KINDS = ("chapters", "silences")
EDGE = 240                      # no break this near a programme's start or end (seconds)
APART = 420                     # nor this near another break
QUIET = "lavfi=[silencedetect=n=-50dB:d=0.5]"   # (-50 dB for half a second: an act break's fade, not a pause)
PER_RUN = 40                    # titles read in one go

_cache: Optional[dict] = None
_lock = threading.Lock()
_busy = False


def _path() -> str:
    return os.path.join(library._dir(), "marks.json")


def _data() -> dict:
    global _cache
    if _cache is None:
        try:
            with open(_path(), encoding="utf-8") as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = {}
        for k in KINDS:
            _cache.setdefault(k, {})
    return _cache


def get(kind: str, plex: str) -> Optional[list]:
    """A title's marks ([[seconds, weight]]), [] for none, None unread."""
    return _data().get(kind, {}).get(str(plex))


def put(kind: str, plex: str, marks: list):
    with _lock:
        _data()[kind][str(plex)] = marks
        try:
            with open(_path() + ".tmp", "w", encoding="utf-8") as f:
                json.dump(_cache, f, separators=(",", ":"))
            os.replace(_path() + ".tmp", _path())
        except OSError:
            pass


def cuts(i: dict, kind: str) -> Optional[list]:
    """Where a programme breaks: its strongest marks (the longest silences,
    or the chapters), away from its ends and from each other, in order.
    None: not read yet."""
    got = get(kind, i.get("plex", ""))
    if got is None:
        return None
    dur = i["duration"]
    out = []
    for t, _w in sorted(got, key=lambda m: -m[1]):
        if EDGE <= t <= dur - EDGE and all(abs(t - o) >= APART for o in out):
            out.append(t)
    return sorted(out)


def wanted(schedules: dict) -> list:
    """[(kind, item)] the titles channels breaking at marks will air that
    haven't been read: the next two days' long programmes."""
    from . import libchannels as lc
    out, seen = [], set()
    horizon = time.time() + 2 * 86400
    for tl in list(schedules.values()):
        kind = (getattr(tl, "brk", None) or {}).get("mid")
        if kind not in KINDS:
            continue
        for s in list(getattr(tl, "_slots", ())):
            if s[0] > horizon:
                break
            i = tl._by_id.get(s[1])
            if (i and i.get("plex") and i["duration"] >= lc.MID_FROM and str(i["plex"]).isdigit()
                    and (kind, i["plex"]) not in seen and get(kind, i["plex"]) is None):
                seen.add((kind, i["plex"]))
                out.append((kind, i))
    return out


def fill(app):
    """Reads what wanted() names, on a thread, a run at a time."""
    global _busy
    od = getattr(app, "ondemand", None)
    if _busy or od is None or not getattr(od, "signed_in", False):
        return
    from . import libchannels as lc
    from . import paths
    todo = [(k, i) for k, i in wanted(lc.SCHEDULES)[:PER_RUN]
            if not (k == "silences" and getattr(paths, "ANDROID", False))]   # (a TV box: halfway instead)
    if not todo:
        return
    _busy = True

    def work():
        global _busy
        try:
            client = od.client()
            for kind, i in todo:
                try:
                    marks = chapters(client, i["plex"]) if kind == "chapters" else silences(client, i["plex"])
                except Exception as e:
                    print(f"[marks] {i.get('title')!r}: {e!r}")
                    continue
                put(kind, i["plex"], marks)
            print(f"[marks] {len(todo)} titles read for mid-show breaks")
        finally:
            _busy = False
    threading.Thread(target=work, daemon=True).start()


def chapters(client, rk: str) -> list:
    d = client._get(f"{client.server}/library/metadata/{rk}?includeChapters=1", token=client._server_token)
    m = ((d.get("MediaContainer") or {}).get("Metadata") or [{}])[0]
    return [[int(c.get("startTimeOffset") or 0) / 1000, 1.0] for c in m.get("Chapter") or []
            if int(c.get("startTimeOffset") or 0) > 0]


def silences(client, rk: str, timeout: float = 120.0) -> list:
    """The title's silences [[middle, length]], its sound read as fast as
    the server sends it (no picture, no output)."""
    from . import video  # noqa: F401  (libmpv's place found first)
    import mpv
    s = client.stream_at(rk)
    found, done = [], threading.Event()
    start = [None]

    def log(level, prefix, text):
        if "silence_start" in text:
            start[0] = float(text.rsplit(":", 1)[1])
        elif "silence_end" in text:
            try:
                end = float(text.split("silence_end:")[1].split("|")[0])
                length = float(text.rsplit(":", 1)[1])
            except (IndexError, ValueError):
                return
            found.append([round(end - length / 2, 2), round(length, 2)])
    pl = mpv.MPV(log_handler=log, loglevel="v", vo="null", ao="null", vid="no", sid="no", untimed=True,
                 ao_null_untimed=True, af=QUIET, ytdl=False)
    try:
        pl["http-header-fields"] = [f"{k}: {v}" for k, v in (s.get("headers") or {}).items()]

        def ev(e):
            if "end-file" in str(e):
                done.set()
        pl.register_event_callback(ev)
        pl.play(s["video"])
        if not done.wait(timeout):
            raise TimeoutError("read too slowly")
    finally:
        pl.terminate()
    return found
