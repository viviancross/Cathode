"""A library channel as one continuous stream for other apps (Plex's and
Jellyfin's live TV, VLC, Channels DVR): /live/<channel>.ts on the web page's
address, programmes and their breaks back to back, as MPEG-TS.

Each piece of the schedule (a programme or its part, a commercial, a
bumper) is asked of Plex's transcoder as HLS from where it's up to; its
eight-second segments (MPEG-TS) are passed on one after another, the next
piece's after the last. The client reads at its own pace, which keeps the
stream on the schedule's clock. Slates (off the air, the "we'll be right
back" card) have no picture of their own: the stream goes on to what's on
after them."""

from __future__ import annotations

import bisect
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

QUALITY = 8000                  # kbps asked of the transcoder


def _session(client, rk: str, at: float, sid: str) -> tuple:
    """A Plex HLS transcode of a title from `at` seconds; returns its
    segments' base address and each segment's start in the file (Plex's
    segments run eight seconds, or one, as the file has it)."""
    from .net import SSL
    # (Plex's own transcode address, as Plex Web asks: an unknown platform gets 400)
    # (directStream off: H.264 every time, as any player takes; an HEVC file copied came through empty)
    url = client._transcode_url(rk, QUALITY, int(at)).replace("directStream=1", "directStream=0") + "&" + urllib.parse.urlencode(
        {"X-Plex-Platform": "Chrome", "X-Plex-Product": "Plex Web", "session": sid})
    req = urllib.request.Request(url, headers=_headers(client))
    with urllib.request.urlopen(req, timeout=30, context=SSL) as r:
        r.read()
    base = f"{client.server}/video/:/transcode/universal/session/{sid}/base/"
    req = urllib.request.Request(base + "index.m3u8", headers=_headers(client))     # (this starts the transcoder)
    with urllib.request.urlopen(req, timeout=30, context=SSL) as r:
        index = r.read().decode("utf-8", "replace")
    starts, t = [], 0.0
    for line in index.splitlines():
        if line.startswith("#EXTINF:"):
            starts.append(t)
            t += float(line[8:].split(",")[0])
    return base, starts


def _headers(client) -> dict:
    h = {k: v for k, v in client._headers(client._server_token).items() if k != "Accept"}
    h.update({"X-Plex-Platform": "Chrome", "X-Plex-Product": "Plex Web", "X-Plex-Device": "Windows"})
    return h


def _stop(client, sid: str):
    from .net import SSL
    try:
        req = urllib.request.Request(f"{client.server}/video/:/transcode/universal/stop?session={sid}",
                                     headers=_headers(client))
        urllib.request.urlopen(req, timeout=5, context=SSL).read()
    except Exception:
        pass


def _segment(client, base: str, k: int, wait: float = 25.0) -> bytes:
    """Segment k (waits while the transcoder catches up to it)."""
    from .net import SSL
    t0 = time.monotonic()
    while True:
        try:
            req = urllib.request.Request(f"{base}{k:05d}.ts", headers=_headers(client))
            with urllib.request.urlopen(req, timeout=30, context=SSL) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 404 or time.monotonic() - t0 > wait:
                raise
            time.sleep(0.5)


def pieces(tl, start: datetime):
    """The schedule's pieces from a moment: (start, stop, entry), the one on
    then first (from where it's up to), each after the last."""
    cur = tl.at(start)
    while cur is not None:
        yield cur
        cur = tl.at(cur["stop"] + timedelta(seconds=0.5))


def stream(app, tl, out, client, stop_at: float = 0.0) -> int:
    """Writes the channel to `out` until the client goes (or `stop_at`,
    monotonic, for tests). Returns the bytes sent."""
    sent, n = 0, 0
    now = datetime.now(timezone.utc)
    first = True
    for cur in pieces(tl, now):
        if stop_at and time.monotonic() > stop_at:
            break
        e = cur["entry"]
        if datetime.now(timezone.utc) > cur["stop"] + timedelta(minutes=2):
            return sent + stream(app, tl, out, client, stop_at)     # fell behind (a long slate): on to what's on now
        rk = str(e.get("plex") or "")
        if not rk.isdigit():
            continue                                    # a slate, or not Plex's: nothing to send
        dur = (cur["stop"] - cur["start"]).total_seconds()
        into = cur["offset"] if first else 0.0
        first = False
        f0 = float(e.get("in", 0)) + into               # the file's time the piece is sent from
        f1 = float(e.get("in", 0)) + dur
        n += 1
        sid = f"cathode{abs(hash((tl.cid, cur['start'].timestamp()))) % 10 ** 10}"
        try:
            base, starts = _session(client, rk, f0, sid)
            k0 = max(0, bisect.bisect_right(starts, f0) - 1)
            k1 = max(k0 + 1, bisect.bisect_left(starts, f1))
            for k in range(k0, k1):
                if stop_at and time.monotonic() > stop_at:
                    break
                data = _segment(client, base, k)
                out.write(data)
                sent += len(data)
        except (BrokenPipeError, ConnectionError, OSError) as ex:
            if isinstance(ex, urllib.error.URLError) and not isinstance(ex, urllib.error.HTTPError):
                print(f"[broadcast] {e.get('title')!r}: {ex!r}")
                continue
            if isinstance(ex, urllib.error.HTTPError):
                print(f"[broadcast] {e.get('title')!r}: Plex said {ex.code}; on to the next")
                continue
            _stop(client, sid)
            return sent                                 # the client went
        finally:
            _stop(client, sid)
    return sent
