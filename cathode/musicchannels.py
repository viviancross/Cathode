"""Music channels: a YouTube playlist as a channel of videos on a timeline.

Each playlist in the settings is a channel after Cathode's own ones, named
from the playlist. A day's running order is the playlist shuffled by the
date, laid end to end from local midnight, so tuning in lands mid-song, the
guide can say what's coming, and tuning away and back finds the same song
further in. The stream is resolved through ytdl when a song is due, the
next one a little ahead; a song that can't play is dropped from the order.
A lower-third card names the song as it starts and again as it ends."""

from __future__ import annotations

import random
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from .epg import Program
from .playlist import Channel

SCHEME = "cathode://music/"
PREFILL = [                     # official decade playlists, so the channels exist before any setup
    "https://www.youtube.com/playlist?list=PLkqz3S84Tw-Qjyd_zHSVH_Xj6ge7yrgYI",   # I Want My '80s Videos! (Vevo)
    "https://www.youtube.com/playlist?list=PL9tY0BWXOZFtv0mU4GO2j_jOB4512Qo1H",   # '90s Hits (Vevo)
    "https://www.youtube.com/playlist?list=PL9tY0BWXOZFu4vlBOzIOmvT6wjYb2jNiV",   # 2K Pop (Vevo)
]
CARD_SECONDS = 8.0              # the lower-third at a song's start and before its end
AHEAD = 20.0                    # seconds before a song is due that its stream is resolved


def is_music(ch) -> bool:
    return ch.url.startswith(SCHEME)


def plid(ch) -> str:
    return ch.url[len(SCHEME):]


def epg_id(pid: str) -> str:
    return f"cathode.music.{pid}"


def add_to(chans: list, config, names: Optional[dict] = None) -> list:
    """The lineup with the music channels after everything else, numbered
    on from the last; `names` (playlist id -> title) names the ones already
    resolved, the rest are "Music Videos" until they are."""
    from . import ytdl
    out = [c for c in chans if not is_music(c)]
    if not out:
        return out
    nxt = int(max(c.number for c in out)) + 1
    for url in getattr(config, "music_playlists", None) or []:
        pid = ytdl.playlist_id(url)
        name = (names or {}).get(pid) or ((ytdl.cached_playlist(url) or {}).get("title")) or "Music Videos"
        out.append(Channel(number=nxt, name=clean_name(name), url=SCHEME + pid, epg_id=epg_id(pid), group="Music"))
        nxt += 1
    return out


def clean_name(title: str) -> str:
    """'I Want My '80s Videos! | Vevo Playlist' -> "I Want My '80s Videos!"."""
    return re.split(r"\s*[|•·]\s*", title or "")[0].strip() or "Music Videos"


# ── The timeline ─────────────────────────────────────────────────────────

class Schedule:
    """A playlist's running order for a day, from local midnight: the
    entries shuffled by the date, end to end, repeating."""

    def __init__(self, pid: str, entries: list):
        self.pid = pid
        self.entries = [e for e in entries if e.get("duration", 0) > 0 and e.get("id")]
        self._day = None
        self._order: list = []
        self._starts: list = []
        self.total = 0.0

    def _for(self, day):
        if self._day != day:
            order = list(self.entries)
            random.Random(f"{self.pid}:{day}").shuffle(order)
            starts, t = [], 0.0
            for e in order:
                starts.append(t)
                t += e["duration"]
            self._day, self._order, self._starts, self.total = day, order, starts, t
        return self._order, self._starts

    def at(self, now: datetime) -> Optional[dict]:
        """{"entry", "offset", "start", "stop"} playing at `now` (UTC), the
        times UTC; None with nothing to play."""
        local = now.astimezone()
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
        order, starts = self._for(local.date())
        if not order:
            return None
        secs = (local - midnight).total_seconds()
        base = secs - secs % self.total
        pos = secs - base
        i = max(0, _bisect(starts, pos) - 1)
        e = order[i]
        start = midnight + timedelta(seconds=base + starts[i])
        return {"entry": e, "offset": pos - starts[i], "start": start.astimezone(timezone.utc),
                "stop": (start + timedelta(seconds=e["duration"])).astimezone(timezone.utc)}

    def drop(self, video_id: str):
        """A video that can't play leaves the order (the rest close up)."""
        self.entries = [e for e in self.entries if e["id"] != video_id]
        self._day = None


def _bisect(a, x):
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] <= x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def fill_guide(epg, chans: list, schedules: dict, now=None, hours: int = 48):
    """Half-hour blocks for each music channel that has its playlist, each
    describing the songs that start in it."""
    now = now or datetime.now(timezone.utc)
    t = now.replace(minute=30 if now.minute >= 30 else 0, second=0, microsecond=0) - timedelta(hours=1)
    slot = timedelta(minutes=30)
    for ch in chans:
        if not is_music(ch):
            continue
        sched = schedules.get(plid(ch))
        if not sched or not sched.entries:
            continue
        progs = []
        for i in range(hours * 2):
            a, b = t + i * slot, t + (i + 1) * slot
            names, cur, u = [], sched.at(a), a
            while cur and u < b and len(names) < 12:
                artist, song = parse_title(cur["entry"]["title"], cur["entry"].get("uploader", ""))
                names.append(f"{artist}: {song}" if artist else song)
                u = cur["stop"] + timedelta(seconds=0.5)
                cur = sched.at(u)
            progs.append(Program(channel_id=ch.epg_id, title=ch.name, start=a, stop=b, category="Music",
                                 description=("Music videos. " + "  ".join(names)) if names else "Music videos."))
        epg.set_programs(ch.epg_id, progs)


# ── Titles ───────────────────────────────────────────────────────────────

_NOISE = re.compile(r"\s*[\(\[][^\)\]]*(official|video|hd\b|4k|remaster|lyric|audio|visuali[sz]er|"
                    r"version|explicit|clean|music|live\b|hq\b|stereo|mono|re-?upload)[^\)\]]*[\)\]]", re.I)


def parse_title(title: str, uploader: str = "") -> tuple:
    """('Artist', 'Song') out of a YouTube title: 'A-ha - Take On Me
    (Official Video) [4K]' -> ('A-ha', 'Take On Me'); without the dash, the
    uploader (its VEVO suffix dropped) stands as the artist."""
    t = _NOISE.sub("", title or "").strip()
    t = re.sub(r"\s*\|.*$", "", t)
    parts = re.split(r"\s+[-–—]\s+", t, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    artist = re.sub(r"(?i)\s*(vevo|official|music|tv)$", "", uploader or "").strip()
    return artist, t


# ── Playing ──────────────────────────────────────────────────────────────

def load(app, done=None):
    """Resolve every playlist in the settings (cached a day), then put the
    schedules on the app, name the channels and fill their guide."""
    from . import ytdl
    urls = list(app.config.music_playlists or [])
    app.music_loading = True

    def work():
        got = {}
        for url in urls:
            try:
                pl = ytdl.playlist(url)
                got[pl["id"]] = pl
            except Exception as e:
                print(f"[music] playlist {ytdl.playlist_id(url)}: {e!r}")
                old = ytdl.cached_playlist(url)
                if old:
                    got[old["id"]] = old
        app.post(_loaded, app, got, done)
    threading.Thread(target=work, daemon=True).start()


def _loaded(app, got: dict, done):
    app.music_loading = False
    app.music = {pid: Schedule(pid, pl["entries"]) for pid, pl in got.items()}
    names = {pid: clean_name(pl.get("title", "")) for pid, pl in got.items()}
    for ch in app.channels:
        if is_music(ch) and plid(ch) in names:
            ch.name = names[plid(ch)]
    fill_guide(app.epg, app.channels, app.music)
    print(f"[music] {len(got)} playlists, " + ", ".join(f"{names[p]} ({len(pl['entries'])})" for p, pl in got.items()))
    app.invalidate()
    if done:
        done()


class Player:
    """What the live screen holds while a music channel is tuned: the song
    due now resolved and played from its offset, the next resolved ahead,
    the card timed to each."""

    def __init__(self, live, ch):
        self.live, self.app, self.ch = live, live.app, ch
        self.sched = getattr(live.app, "music", {}).get(plid(ch))
        self.cur = None             # the schedule entry playing
        self.gen = 0
        self._timer = None

    def start(self):
        """Play what's due now (resolving it first, off the thread)."""
        from . import ytdl
        self.gen += 1
        gen = self.gen
        app = self.app
        if self.sched is None:
            if not getattr(app, "music_loading", False):
                load(app)
            app.after(2.0, lambda: gen == self.gen and self._retry())
            return
        cur = self.sched.at(datetime.now(timezone.utc))
        if cur is None:
            self.live.on_video("video_ended", reason="nothing to play")
            return
        e = cur["entry"]

        def work():
            try:
                s = ytdl.stream(e["id"])
            except Exception as ex:
                print(f"[music] {e['id']} {e.get('title', '')!r} can't play ({ex.__class__.__name__}): skipped")
                app.post(self._skip, gen, e["id"])
                return
            app.post(self._play, gen, cur, s)
        threading.Thread(target=work, daemon=True).start()

    def _retry(self):
        self.sched = getattr(self.app, "music", {}).get(plid(self.ch))
        self.start()

    def _skip(self, gen, video_id):
        if gen != self.gen:
            return
        self.sched.drop(video_id)
        self.start()

    def _play(self, gen, cur, s):
        if gen != self.gen:
            return
        from . import ytdl
        e = cur["entry"]
        offset = max(0.0, (datetime.now(timezone.utc) - cur["start"]).total_seconds())
        self.cur = cur
        self.app.video.play(s["video"], headers=s.get("headers"), start=offset, audio=s.get("audio"))
        artist, song = parse_title(e["title"], e.get("uploader", ""))
        label = re.sub(r"(?i)\s*(vevo|official|music|tv)$", "", e.get("uploader", "")).strip()
        if label.lower().replace(" ", "") == artist.lower().replace(" ", ""):
            label = ""                  # the uploader is the artist: nothing new to say
        self.live.card = {"artist": artist, "song": song, "label": label,
                          "until": time.monotonic() + CARD_SECONDS}
        self.app.after(CARD_SECONDS + 0.05, self.app.invalidate)
        print(f"[music] {self.ch.name}: {artist} - {song} from {offset:.0f} s of {e['duration']:.0f}")
        left = (cur["stop"] - datetime.now(timezone.utc)).total_seconds()
        self.app.cancel(self._timer)
        if left > CARD_SECONDS + 2:
            self._timer = self.app.after(left - CARD_SECONDS, lambda: gen == self.gen and self._card_again())
        # the next song resolved ahead, so its start is only mpv's open
        nxt = self.sched.at(cur["stop"] + timedelta(seconds=1))
        if nxt and nxt["entry"]["id"] != e["id"]:
            delay = max(0.5, left - AHEAD)
            self.app.after(delay, lambda: gen == self.gen and threading.Thread(
                target=lambda: _resolve_quietly(nxt["entry"]["id"]), daemon=True).start())

    def _card_again(self):
        if self.live.card:
            self.live.card["until"] = time.monotonic() + CARD_SECONDS
            self.app.invalidate()
            self.app.after(CARD_SECONDS + 0.05, self.app.invalidate)

    def ended(self, reason: str):
        """The song's stream ended: the next is due (eof), or this one failed
        and is dropped from the order."""
        if self.cur and reason != "eof":
            left = (self.cur["stop"] - datetime.now(timezone.utc)).total_seconds()
            if left > 5:
                self.sched.drop(self.cur["entry"]["id"])
        self.start()

    def stop(self):
        self.gen += 1
        self.app.cancel(self._timer)
        self.live.card = None


def _resolve_quietly(video_id):
    from . import ytdl
    try:
        ytdl.stream(video_id)
    except Exception as e:
        print(f"[music] ahead: {video_id} {e.__class__.__name__}")
