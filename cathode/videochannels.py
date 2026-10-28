"""Video channels: YouTube playlists and channels, mixed, as a channel of
videos on a timeline.

Each channel in the settings (name, number, sources, how they're weighed)
sits after Cathode's own channels. A source is a playlist, a YouTube
channel or an @handle; its full list of videos is fetched weekly (ytdl),
and each broadcast day (from 4 AM) draws a sample of up to 500 of them by
the date. The day's running order interleaves the sources by weight
(automatic: each source's share of the sample's running time, no source
under 5 %; equal; or set by hand), laid end to end, so tuning in lands
mid-video, the guide can list what's coming, and tuning away and back
finds the same video further in. A video that can't play is dropped from
the order. A lower-third names each video as it starts and as it ends."""

from __future__ import annotations

import random
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from .epg import Program
from .playlist import Channel

SCHEME = "cathode://video/"
CARD_SECONDS = 8.0              # the lower-third at a video's start and before its end
AHEAD = 20.0                    # seconds before a video is due that its stream is resolved
SAMPLE = 500                    # videos a source contributes to a day
FLOOR = 0.05                    # automatic weighting: no source under this share of the day
DAY_STARTS = 4                  # the broadcast day turns over at 4 AM, not midnight
LONG = 600                      # videos this long (median) get their own guide listings
WEIGHTINGS = [("auto", "Auto"), ("equal", "Equal"), ("manual", "Manual")]
GUIDES = [("auto", "Auto"), ("video", "Per video"), ("blocks", "Half-hour blocks")]
MIN_SECONDS = [0, 30, 60, 120, 300, 600]

# A fresh install's channels: the three decade playlists and bideogaymin.
PREFILL = [
    {"name": "", "sources": ["https://www.youtube.com/playlist?list=PLkqz3S84Tw-Qjyd_zHSVH_Xj6ge7yrgYI"]},  # I Want My '80s Videos!
    {"name": "", "sources": ["https://www.youtube.com/playlist?list=PL9tY0BWXOZFtv0mU4GO2j_jOB4512Qo1H"]},  # '90s Hits
    {"name": "", "sources": ["https://www.youtube.com/playlist?list=PL9tY0BWXOZFu4vlBOzIOmvT6wjYb2jNiV"]},  # 2K Pop
    {"name": "bideogaymin", "sources": [
        "@ScottTheWoz", "@Caddicarus", "@LGR", "@GameGrumps", "@TheGrumps", "@BringusStudios", "@JonBringus",
        "@NitroRad", "@StopSkeletonsFromFighting", "@PlanetClue", "@Billiam", "@GamingHistorian",
        "@IronPineapple", "@brutalmoose"]},
]


def new_channel(name: str = "", sources=()) -> dict:
    """A channel's settings entry with every field at its default."""
    return {"id": uuid.uuid4().hex[:8], "name": name, "number": "auto",
            "sources": [{"url": s, "weight": 1} if isinstance(s, str) else dict(s) for s in sources],
            "weighting": "auto", "min_seconds": 60, "skip_shorts": True, "skip_live": True, "guide": "auto",
            "card": True}


def fix(c: dict) -> dict:
    """A channel entry with any missing field filled in (older configs)."""
    d = new_channel(c.get("name", ""), c.get("sources", []))
    d.update({k: v for k, v in c.items() if k != "sources"})
    return d


def prefill() -> list:
    return [new_channel(c["name"], c["sources"]) for c in PREFILL]


def migrate(config):
    """4.34's music_playlists become one-source channels (with bideogaymin
    after them, as a fresh install has); older entries get new fields."""
    old = getattr(config, "music_playlists", None) or []
    before = [dict(c) for c in (config.video_channels or [])]
    if old:
        config.video_channels = [new_channel("", [u]) for u in old] + [
            new_channel(c["name"], c["sources"]) for c in PREFILL[3:]]
        config.music_playlists = []
    config.video_channels = [fix(c) for c in (config.video_channels or [])]
    return bool(old) or config.video_channels != before


def is_video(ch) -> bool:
    return ch.url.startswith(SCHEME)


def cid_of(ch) -> str:
    return ch.url[len(SCHEME):]


def epg_id(cid: str) -> str:
    return f"cathode.video.{cid}"


def entry(config, cid: str) -> Optional[dict]:
    return next((c for c in config.video_channels if c["id"] == cid), None)


def add_to(chans: list, config, names: Optional[dict] = None) -> list:
    """The lineup with the video channels placed: at the number each asks
    for (bumped past one that's taken), or on after the last; `names` has
    the titles resolved so far, the rest are named for their first source's
    cache, or 'Video Channel' until then."""
    from . import ytdl
    out = [c for c in chans if not is_video(c)]
    if not out:
        return out
    taken = {c.number for c in out}
    nxt = int(max(c.number for c in out)) + 1
    for c in config.video_channels or []:
        want = c.get("number", "auto")
        try:
            num = nxt if want == "auto" else int(want)
        except (TypeError, ValueError):
            num = nxt
        while num in taken:
            num += 1
        taken.add(num)
        nxt = max(nxt, num + 1)
        name = c.get("name") or (names or {}).get(c["id"]) or _cached_name(ytdl, c) or "Video Channel"
        ch = Channel(number=num, name=name, url=SCHEME + c["id"], epg_id=epg_id(c["id"]), group="Video")
        at = next((i for i, o in enumerate(out) if o.number > num), len(out))
        out.insert(at, ch)
    return out


def _cached_name(ytdl, c) -> str:
    for s in c.get("sources") or []:
        got = ytdl.cached_listing(s["url"])
        if got and got.get("title"):
            return clean_name(got["title"])
    return ""


def clean_name(title: str) -> str:
    """'I Want My '80s Videos! | Vevo Playlist' -> "I Want My '80s Videos!";
    'Scott The Woz - Videos' -> 'Scott The Woz'."""
    t = re.split(r"\s*[|•·]\s*", title or "")[0].strip()
    return re.sub(r"\s+-\s+(Videos|Shorts|Live)$", "", t).strip() or "Video Channel"


# ── The timeline ─────────────────────────────────────────────────────────

class Schedule:
    """A channel's running order for a broadcast day: each source's sample
    for the date, shuffled, interleaved by weight, end to end, repeating."""

    def __init__(self, c: dict, listings: dict):
        """c: the channel's settings; listings: source url -> its listing
        ({"title", "entries"}), the ones fetched so far."""
        self.c = c
        self.cid = c["id"]
        self.sources = []           # [(url, weight, [entries])]
        self.dropped = set()
        min_s = c.get("min_seconds", 60)
        for s in c.get("sources") or []:
            lst = listings.get(s["url"])
            if not lst:
                continue
            es = [e for e in lst.get("entries") or [] if e.get("id") and e.get("duration", 0) > 0
                  and e["duration"] >= min_s and not (c.get("skip_shorts", True) and e.get("short"))
                  and not (c.get("skip_live", True) and e.get("live"))]
            for e in es:
                if not e.get("uploader"):        # a channel's own list names no uploader
                    e["uploader"] = clean_name(lst.get("title", ""))
            if es:
                self.sources.append((s["url"], max(0.0, float(s.get("weight", 1) or 0)), es))
        self._day = None
        self._order: list = []
        self._starts: list = []
        self.total = 0.0

    @property
    def entries(self) -> list:
        return [e for _u, _w, es in self.sources for e in es if e["id"] not in self.dropped]

    def median(self) -> float:
        d = sorted(e["duration"] for e in self.entries)
        return d[len(d) // 2] if d else 0.0

    def _for(self, day):
        if self._day == day:
            return self._order, self._starts
        samples, weights = [], []
        for url, w, es in self.sources:
            es = [e for e in es if e["id"] not in self.dropped]
            rnd = random.Random(f"{self.cid}:{url}:{day}")
            if len(es) > SAMPLE:
                es = rnd.sample(es, SAMPLE)
            rnd.shuffle(es)
            if es:
                samples.append(es)
                weights.append((w, sum(e["duration"] for e in es)))
        mode = self.c.get("weighting", "auto")
        if mode == "equal":
            shares = [1.0] * len(samples)
        elif mode == "manual":
            shares = [w for w, _rt in weights]
            if not any(shares):
                shares = [1.0] * len(samples)
        else:
            total = sum(rt for _w, rt in weights) or 1.0
            shares = [max(rt / total, FLOOR) for _w, rt in weights]
        order, starts, t = [], [], 0.0
        played = [0.0] * len(samples)
        pos = [0] * len(samples)
        want = sum(len(s) for s in samples)
        while samples and len(order) < want:
            # the source furthest behind its share of the airtime so far
            total_share = sum(shares) or 1.0
            i = max(range(len(samples)), key=lambda k: shares[k] / total_share * (t + 1) - played[k])
            e = samples[i][pos[i] % len(samples[i])]
            pos[i] += 1
            order.append(e)
            starts.append(t)
            t += e["duration"]
            played[i] += e["duration"]
        self._day, self._order, self._starts, self.total = day, order, starts, t
        return order, starts

    @staticmethod
    def day_of(local: datetime):
        """The broadcast day a local moment belongs to, and its start."""
        start = local.replace(hour=DAY_STARTS, minute=0, second=0, microsecond=0)
        if local < start:
            start -= timedelta(days=1)
        return start.date(), start

    def at(self, now: datetime) -> Optional[dict]:
        """{"entry", "offset", "start", "stop"} playing at `now` (UTC), the
        times UTC; None with nothing to play."""
        local = now.astimezone()
        day, day_start = self.day_of(local)
        order, starts = self._for(day)
        if not order:
            return None
        secs = (local - day_start).total_seconds()
        base = secs - secs % self.total
        pos = secs - base
        i = max(0, _bisect(starts, pos) - 1)
        e = order[i]
        start = day_start + timedelta(seconds=base + starts[i])
        return {"entry": e, "offset": pos - starts[i], "start": start.astimezone(timezone.utc),
                "stop": (start + timedelta(seconds=e["duration"])).astimezone(timezone.utc)}

    def drop(self, video_id: str):
        """A video that can't play leaves the order (the rest close up)."""
        self.dropped.add(video_id)
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


def guide_style(c: dict, sched: Schedule) -> str:
    style = c.get("guide", "auto")
    if style == "auto":
        return "video" if sched.median() >= LONG else "blocks"
    return style


def fill_guide(epg, chans: list, schedules: dict, config=None, now=None, hours: int = 48):
    """Each video channel's listings: a programme per video for long-form
    channels, half-hour blocks naming the videos that start in them for
    the rest."""
    now = now or datetime.now(timezone.utc)
    t0 = now.replace(minute=30 if now.minute >= 30 else 0, second=0, microsecond=0) - timedelta(hours=1)
    end = t0 + timedelta(hours=hours)
    for ch in chans:
        if not is_video(ch):
            continue
        sched = schedules.get(cid_of(ch))
        if not sched or not sched.entries:
            continue
        c = sched.c
        progs = []
        if guide_style(c, sched) == "video":
            cur, n = sched.at(t0), 0
            while cur and cur["start"] < end and n < 4000:
                e = cur["entry"]
                artist, title = parse_title(e["title"], e.get("uploader", ""))
                progs.append(Program(channel_id=ch.epg_id, title=title, start=cur["start"], stop=cur["stop"],
                                     category="Video", description=f"From {artist or e.get('uploader', '')}, "
                                     f"{max(1, round(e['duration'] / 60))} min."))
                cur = sched.at(cur["stop"] + timedelta(seconds=0.5))
                n += 1
        else:
            slot = timedelta(minutes=30)
            for i in range(hours * 2):
                a, b = t0 + i * slot, t0 + (i + 1) * slot
                names, cur, u = [], sched.at(a), a
                while cur and u < b and len(names) < 12:
                    artist, song = parse_title(cur["entry"]["title"], cur["entry"].get("uploader", ""))
                    names.append(f"{artist}: {song}" if artist else song)
                    u = cur["stop"] + timedelta(seconds=0.5)
                    cur = sched.at(u)
                progs.append(Program(channel_id=ch.epg_id, title=ch.name, start=a, stop=b, category="Music",
                                     description=("Videos. " + "  ".join(names)) if names else "Videos."))
        epg.set_programs(ch.epg_id, progs)


# ── Titles ───────────────────────────────────────────────────────────────

_NOISE = re.compile(r"\s*[\(\[][^\)\]]*(official|video|hd\b|4k|remaster|lyric|audio|visuali[sz]er|"
                    r"version|explicit|clean|music|live\b|hq\b|stereo|mono|re-?upload)[^\)\]]*[\)\]]", re.I)


def parse_title(title: str, uploader: str = "") -> tuple:
    """('Artist', 'Song') out of a music video's title: 'A-ha - Take On Me
    (Official Video) [4K]' -> ('A-ha', 'Take On Me'); a title with no dash
    is the video's, and the uploader (its VEVO suffix dropped) is the name
    on the top line."""
    t = _NOISE.sub("", title or "").strip()
    t = re.sub(r"\s*\|.*$", "", t)
    parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", t, maxsplit=1)]
    who = re.sub(r"(?i)\s*(vevo|official|music|tv)$", "", uploader or "").strip()
    if len(parts) == 2:
        same = lambda a, b: a.lower().replace(" ", "") == b.lower().replace(" ", "")
        if who and same(parts[1], who):            # 'Game Boy Camera - Scott The Woz'
            return who, parts[0]
        if who and same(parts[0], who):
            return who, parts[1]
        if len(parts[0]) < 40:
            return parts[0], parts[1]
    return who, t or title


# ── Loading ──────────────────────────────────────────────────────────────

def load(app, done=None, cid: Optional[str] = None, fresh: bool = False):
    """Fetch every source's listing (from the cache while it's fresh), a
    second apart so YouTube isn't hammered; the schedules are rebuilt as
    each source lands, so a channel plays from the first one in."""
    from . import ytdl
    chans = [c for c in app.config.video_channels if cid is None or c["id"] == cid]
    app.video_loading = True

    def work():
        for c in chans:
            for s in c.get("sources") or []:
                try:
                    lst = ytdl.listing(s["url"], max_age=0 if fresh else ytdl.LISTING_TTL)
                except Exception as e:
                    print(f"[video] {s['url']}: {e!r}")
                    lst = ytdl.cached_listing(s["url"])
                if lst:
                    app.post(_source_loaded, app, s["url"], lst)
                    time.sleep(1.0)
        app.post(_loaded, app, done)
    threading.Thread(target=work, daemon=True).start()


def _source_loaded(app, url: str, lst: dict):
    app.listings[url] = lst
    rebuild(app)


def _loaded(app, done):
    app.video_loading = False
    rebuild(app)
    for cid, s in app.schedules.items():
        c = s.c
        print(f"[video] {c.get('name') or cid}: " + ", ".join(
            f"{clean_name(app.listings[u].get('title', ''))} ({len(es)})" for u, _w, es in s.sources))
    if done:
        done()


def rebuild(app):
    """Schedules from the listings in hand; channel names and the guide after."""
    app.schedules = {c["id"]: Schedule(c, app.listings) for c in app.config.video_channels}
    for ch in app.channels:
        if is_video(ch):
            c = entry(app.config, cid_of(ch))
            if c and not c.get("name"):
                for s in c.get("sources") or []:
                    lst = app.listings.get(s["url"])
                    if lst and lst.get("title"):
                        ch.name = clean_name(lst["title"])
                        break
    fill_guide(app.epg, app.channels, app.schedules, app.config)
    app.invalidate()


def source_report(app, c: dict) -> list:
    """[(source url, title or '', videos, fetched-ago text)] for the maker."""
    from . import ytdl
    out = []
    for s in c.get("sources") or []:
        lst = app.listings.get(s["url"]) or ytdl.cached_listing(s["url"])
        if not lst:
            out.append((s["url"], "", 0, "not fetched yet"))
            continue
        ago = time.time() - lst.get("fetched", 0)
        when = "just now" if ago < 120 else f"{int(ago // 3600)} h ago" if ago < 86400 else f"{int(ago // 86400)} d ago"
        out.append((s["url"], clean_name(lst.get("title", "")), len(lst.get("entries") or []), when))
    return out


# ── Playing ──────────────────────────────────────────────────────────────

class Player:
    """What the live screen holds while a video channel is tuned: the video
    due now resolved and played from its offset, the next resolved ahead,
    the card timed to each."""

    def __init__(self, live, ch):
        self.live, self.app, self.ch = live, live.app, ch
        self.cid = cid_of(ch)
        self.cur = None             # the schedule entry playing
        self.gen = 0
        self._timer = None

    @property
    def sched(self) -> Optional[Schedule]:
        s = getattr(self.app, "schedules", {}).get(self.cid)
        return s if s and s.entries else None

    def start(self):
        """Play what's due now (resolving it first, off the thread)."""
        from . import ytdl
        self.gen += 1
        gen = self.gen
        app = self.app
        sched = self.sched
        if sched is None:
            if not getattr(app, "video_loading", False):
                load(app)
            app.after(2.0, lambda: gen == self.gen and self.start())
            return
        cur = sched.at(datetime.now(timezone.utc))
        if cur is None:
            self.live.on_video("video_ended", reason="nothing to play")
            return
        e = cur["entry"]

        def work():
            try:
                s = ytdl.stream(e["id"])
            except Exception as ex:
                print(f"[video] {e['id']} {e.get('title', '')!r} can't play ({ex.__class__.__name__}): skipped")
                app.post(self._skip, gen, e["id"])
                return
            app.post(self._play, gen, cur, s)
        threading.Thread(target=work, daemon=True).start()

    def _drop(self, video_id):
        """A video out of the day's order: the rest close up, so the guide
        for this channel is written again."""
        sched = self.sched
        if sched:
            sched.drop(video_id)
            fill_guide(self.app.epg, [self.ch], {self.cid: sched}, self.app.config)

    def _skip(self, gen, video_id):
        if gen != self.gen:
            return
        self._drop(video_id)
        self.start()

    def _play(self, gen, cur, s):
        if gen != self.gen:
            return
        e = cur["entry"]
        offset = max(0.0, (datetime.now(timezone.utc) - cur["start"]).total_seconds())
        self.cur = cur
        self.app.video.play(s["video"], headers=s.get("headers"), start=offset, audio=s.get("audio"))
        artist, title = parse_title(e["title"], e.get("uploader", ""))
        c = entry(self.app.config, self.cid) or {}
        if c.get("card", True):
            self.live.card = {"artist": artist, "song": title, "label": "", "until": time.monotonic() + CARD_SECONDS}
            self.app.after(CARD_SECONDS + 0.05, self.app.invalidate)
        print(f"[video] {self.ch.name}: {artist} - {title} from {offset:.0f} s of {e['duration']:.0f}")
        left = (cur["stop"] - datetime.now(timezone.utc)).total_seconds()
        self.app.cancel(self._timer)
        if left > CARD_SECONDS + 2 and c.get("card", True):
            self._timer = self.app.after(left - CARD_SECONDS, lambda: gen == self.gen and self._card_again())
        # the next video resolved ahead, so its start is only mpv's open
        sched = self.sched
        nxt = sched.at(cur["stop"] + timedelta(seconds=1)) if sched else None
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
        """The video's stream ended: the next is due (eof), or this one
        failed and is dropped from the order."""
        if self.cur and reason != "eof" and self.sched:
            left = (self.cur["stop"] - datetime.now(timezone.utc)).total_seconds()
            if left > 5:
                print(f"[video] {self.cur['entry']['id']} ended early ({reason}, {left:.0f} s left): dropped")
                self._drop(self.cur["entry"]["id"])
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
        print(f"[video] ahead: {video_id} {e.__class__.__name__}")
