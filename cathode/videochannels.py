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
GRACE = 20.0                    # a video due this recently starts from its top, not its offset
SAMPLE = 500                    # videos a source contributes to a day
FLOOR = 0.05                    # automatic weighting: no source under this share of the day
DAY_STARTS = 4                  # the broadcast day turns over at 4 AM, not midnight
LONG = 600                      # videos this long (median) get their own guide listings
WEIGHTINGS = [("auto", "Auto"), ("equal", "Equal"), ("manual", "Manual")]
GUIDES = [("auto", "Auto"), ("video", "Per video"), ("blocks", "Half-hour blocks")]
ORDERS = [("listed", "As listed"), ("reversed", "Reversed"), ("title", "By title")]
MIN_SECONDS = [0, 30, 60, 120, 300, 600]
MAX_SECONDS = [0, 1800, 3600, 7200, 10800, 14400, 28800]     # 0: any length

# A fresh install's channels: the three decade playlists and bideogaymin.
PREFILL = [
    {"name": "", "sources": ["https://www.youtube.com/playlist?list=PLkqz3S84Tw-Qjyd_zHSVH_Xj6ge7yrgYI"]},  # I Want My '80s Videos!
    {"name": "", "sources": ["https://www.youtube.com/playlist?list=PL9tY0BWXOZFtv0mU4GO2j_jOB4512Qo1H"]},  # '90s Hits
    {"name": "", "sources": ["https://www.youtube.com/playlist?list=PL9tY0BWXOZFu4vlBOzIOmvT6wjYb2jNiV"]},  # 2K Pop
    {"name": "bideogaymin", "max_seconds": 14400, "sources": [
        "@ScottTheWoz", "@Caddicarus", "@LGR", "@GameGrumps", "@TheGrumps", "@BringusStudios", "@JonBringus",
        "@NitroRad", "@StopSkeletonsFromFighting", "@PlanetClue", "@Billiam", "@GamingHistorian",
        "@IronPineapple", "@brutalmoose"]},
]


def new_channel(name: str = "", sources=()) -> dict:
    """A channel's settings entry with every field at its default."""
    return {"id": uuid.uuid4().hex[:8], "name": name, "number": "auto",
            "sources": [{"url": s, "weight": 1} if isinstance(s, str) else dict(s) for s in sources],
            "weighting": "auto", "min_seconds": 60, "max_seconds": 0, "skip_shorts": True, "skip_live": True,
            "guide": "auto", "card": True}


def fix(c: dict) -> dict:
    """A channel entry with any missing field filled in (older configs)."""
    d = new_channel(c.get("name", ""), c.get("sources", []))
    d.update({k: v for k, v in c.items() if k != "sources"})
    return d


def prefill() -> list:
    out = []
    for c in PREFILL:
        d = new_channel(c["name"], c["sources"])
        d.update({k: v for k, v in c.items() if k not in ("name", "sources")})
        out.append(d)
    return out


def migrate(config):
    """4.34's music_playlists become one-source channels (with bideogaymin
    after them, as a fresh install has); older entries get new fields."""
    old = getattr(config, "music_playlists", None) or []
    before = [dict(c) for c in (config.video_channels or [])]
    if old:
        config.video_channels = [new_channel("", [u]) for u in old] + prefill()[3:]
        config.music_playlists = []
    config.video_channels = [fix(c) for c in (config.video_channels or [])]
    return bool(old) or config.video_channels != before


def is_video(ch) -> bool:
    """Played by the Player: a video channel, or a Spelunkr channel."""
    return ch.url.startswith(SCHEME)


def is_made(ch) -> bool:
    """A video channel made in the settings (placed after the lineup), not
    one of the lineup's own (a Spelunkr channel)."""
    return is_video(ch) and not cid_of(ch).startswith("spelunkr.")


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
    out = [c for c in chans if not is_made(c)]
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
        self.opts = {}              # url -> the source's settings (order, shuffle)
        self.dropped = set()
        min_s, max_s = c.get("min_seconds", 60), c.get("max_seconds", 0)
        for s in c.get("sources") or []:
            lst = listings.get(s["url"])
            if not lst:
                continue
            entries = list(lst.get("entries") or [])
            if not c.get("skip_live", True):            # the channel's streams tab, fetched beside its videos
                entries += (listings.get(s["url"] + "#live") or {}).get("entries") or []
            es = [e for e in entries if e.get("id") and e.get("duration", 0) > 0
                  and e["duration"] >= min_s and (not max_s or e["duration"] <= max_s)
                  and not (c.get("skip_shorts", True) and e.get("short"))
                  and not (c.get("skip_live", True) and e.get("live"))]
            for e in es:
                if not e.get("uploader"):        # a channel's own list names no uploader
                    e["uploader"] = clean_name(lst.get("title", ""))
            if es:
                self.sources.append((s["url"], max(0.0, float(s.get("weight", 1) or 0)), es))
                self.opts[s["url"]] = s
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
        seed = self.c.get("seed", 0)             # a refresh draws the day again
        for url, w, es in self.sources:
            es = [e for e in es if e["id"] not in self.dropped]
            rnd = random.Random(f"{self.cid}:{url}:{day}" + (f":{seed}" if seed else ""))
            if len(es) > SAMPLE:                 # a day's sample, kept in the list's order
                es = [es[i] for i in sorted(rnd.sample(range(len(es)), SAMPLE))]
            opt = self.opts.get(url, {})
            order = opt.get("order", "listed")
            if order == "reversed":
                es.reverse()
            elif order == "title":
                es.sort(key=lambda e: e.get("title", "").lower())
            if opt.get("shuffle", True):
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
    """Each video channel's listings into the guide (programmes())."""
    for eid, progs in programmes(chans, schedules, now, hours).items():
        epg.set_programs(eid, progs)


def programmes(chans: list, schedules: dict, now=None, hours: int = 48) -> dict:
    """epg id -> each video channel's listings: a programme per video for
    long-form channels, half-hour blocks naming the videos that start in
    them for the rest. Touches nothing but the schedules: safe off the UI
    thread."""
    out = {}
    now = now or datetime.now(timezone.utc)
    t0 = now.replace(minute=30 if now.minute >= 30 else 0, second=0, microsecond=0) - timedelta(hours=1)
    end = t0 + timedelta(hours=hours)
    for ch in chans:
        if not is_video(ch):
            continue
        sched = schedules.get(cid_of(ch))
        if not sched or not sched.entries:
            continue
        memo = getattr(sched, "guide_memo", None)       # a Spelunkr schedule keeps its listings
        if memo and memo[0] == (t0, hours, len(sched.dropped)):     # until the half hour turns
            out[ch.epg_id] = memo[1]
            continue
        c = sched.c
        progs = []
        if guide_style(c, sched) == "video":
            cur, n = sched.at(t0), 0
            while cur and cur["start"] < end and n < 4000:
                e = cur["entry"]
                if e.get("kind"):       # Spelunkr: its shows, each running on over the breaks after it
                    if e["kind"] == "show" or not progs:
                        progs.append(Program(channel_id=ch.epg_id, title=e["title"], start=cur["start"], stop=cur["stop"],
                                             category=c.get("category", "Video"), description=e.get("desc", "")))
                    else:
                        progs[-1].stop = cur["stop"]
                else:
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
        out[ch.epg_id] = progs
        if hasattr(sched, "guide_memo"):
            sched.guide_memo = ((t0, hours, len(sched.dropped)), progs)
    return out


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
                keys = [s["url"]]
                if not c.get("skip_live", True) and ytdl.source_url(s["url"]).endswith("/videos"):
                    keys.append(s["url"] + "#live")
                for key in keys:
                    try:
                        lst = ytdl.listing(key, max_age=0 if fresh else ytdl.LISTING_TTL)
                    except Exception as e:
                        print(f"[video] {key}: {e!r}")
                        lst = ytdl.cached_listing(key)
                    if lst:
                        app.post(_source_loaded, app, key, lst)
                        time.sleep(1.0)
        app.post(_loaded, app, done)
    threading.Thread(target=work, daemon=True).start()


THROTTLE = 5.0                  # while the lists land: a rebuild at most this often


def _source_loaded(app, url: str, lst: dict):
    app.listings[url] = lst
    if getattr(app, "after", None) is None:
        rebuild(app)
        return
    if getattr(app, "_vc_soon", False):
        return                          # one is already due: it takes this list too
    app._vc_soon = True
    wait = max(0.0, getattr(app, "_vc_last", 0.0) + THROTTLE - time.monotonic())

    def due():
        app._vc_soon = False
        rebuild(app)
    app.after(wait, due)


def _loaded(app, done):
    app.video_loading = False
    rebuild(app, report=True)
    if done:
        done()


def rebuild(app, report: bool = False):
    """Schedules from the listings in hand, channel names and the guide
    after. The working out (a day's order from a channel of 3000 videos,
    two days of listings, Spelunkr's 33 channels) runs off the UI thread:
    on it, each source landing at launch was a visible stutter. The UI
    thread only swaps the result in. One build at a time; any asked for
    while one runs make one more after it."""
    if getattr(app, "post", None) is None:          # no event loop (tests): in line
        _apply(app, *_build(list(app.config.video_channels), dict(app.listings), list(app.channels)), report)
        return
    if getattr(app, "_vc_busy", False):
        app._vc_again = True
        app._vc_report = getattr(app, "_vc_report", False) or report
        return
    app._vc_busy, app._vc_again = True, False
    app._vc_last = time.monotonic()
    args = (list(app.config.video_channels), dict(app.listings), list(app.channels))

    def work():
        try:
            built = _build(*args)
        except Exception as e:
            print(f"[video] schedules: {e!r}")
            built = None
        app.post(_built, app, built, report)
    threading.Thread(target=work, daemon=True).start()


def _build(cfg_channels: list, listings: dict, chans: list):
    from . import spelunkr
    schedules = {c["id"]: Schedule(c, listings) for c in cfg_channels}
    schedules.update(spelunkr.SCHEDULES)
    return schedules, programmes(chans, schedules), listings


def _built(app, built, report):
    app._vc_busy = False
    if built:
        _apply(app, *built, report)
    if app._vc_again:
        again = getattr(app, "_vc_report", False)
        app._vc_report = False
        rebuild(app, again)


def _apply(app, schedules: dict, progs: dict, listings: dict, report: bool = False):
    app.schedules = schedules
    app.video_programmes = progs        # (a guide reloaded later takes these again)
    for ch in app.channels:
        if is_video(ch):
            c = entry(app.config, cid_of(ch))
            if c and not c.get("name"):
                for s in c.get("sources") or []:
                    lst = listings.get(s["url"])
                    if lst and lst.get("title"):
                        ch.name = clean_name(lst["title"])
                        break
    for eid, ps in progs.items():
        app.epg.set_programs(eid, ps)
    if report:
        for cid, s in schedules.items():
            if s.sources:
                print(f"[video] {s.c.get('name') or cid}: " + ", ".join(
                    f"{clean_name(listings[u].get('title', ''))} ({len(es)})" for u, _w, es in s.sources))
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
        self._timer = self._stop_timer = None

    @property
    def sched(self) -> Optional[Schedule]:
        from . import spelunkr
        s = getattr(self.app, "schedules", {}).get(self.cid) or spelunkr.SCHEDULES.get(self.cid)
        return s if s and s.entries else None

    def start(self, cont: bool = False):
        """Play what's due now (resolving it first, off the thread). With
        `cont` the last video just ended or hit its stop: the one after it
        plays from its top, however late (a slow resolve, a stream that ran
        long) or early (one that ran short) the handover is, so a channel
        plays like a playlist; only tuning in joins a video at its offset."""
        self.gen += 1
        gen = self.gen
        app = self.app
        sched = self.sched
        if sched is None:
            if not getattr(app, "video_loading", False):
                load(app)
            app.after(2.0, lambda: gen == self.gen and self.start(cont))
            return
        now = datetime.now(timezone.utc)
        cur = sched.at(self.cur["stop"] + timedelta(seconds=1)) if cont and self.cur else None
        if cur is None or now >= cur["stop"]:      # nothing after it, or that one is over too: whatever is due
            cur = sched.at(now)
        if cur is None:
            self.live.on_video("video_ended", reason="nothing to play")
            return
        e = cur["entry"]
        print(f"[video] {self.ch.name}: {e.get('title', '')!r} due, {('at ' + format((now - cur['start']).total_seconds(), '.0f') + ' s') if not cont else 'from its top'}")

        def work():
            try:
                if e.get("url"):        # a Spelunkr file plays as it is: no yt-dlp in the way
                    s = {"video": e["url"]}
                else:
                    from . import ytdl
                    ytdl.MAX_HEIGHT = int(app.config.video_quality or 1080)
                    s = ytdl.stream(e["id"])
            except Exception as ex:
                print(f"[video] {e['id']} {e.get('title', '')!r} can't play ({ex.__class__.__name__}): skipped")
                app.post(self._skip, gen, e["id"])
                return
            app.post(self._play, gen, cur, s, cont)
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
        self.cur = None
        self.start(cont=True)

    def _play(self, gen, cur, s, cont=False):
        if gen != self.gen:
            return
        e = cur["entry"]
        offset = max(0.0, (datetime.now(timezone.utc) - cur["start"]).total_seconds())
        if (cont or offset < GRACE) and not e.get("kind"):
            offset = 0.0        # a handover, or due just now (resolving and opening took the seconds): the top, not a cut head
        self.cur = cur          # (Spelunkr keeps the network's clock: always the true offset)
        if e.get("kind") == "card":                     # a Spelunkr bumper: its music, its slides on the lower third
            if e.get("url"):
                self.app.video.play(e["url"], start=offset + e.get("in", 0))
            else:
                self.app.video.stop()
                if self.live.phase == "cover":      # nothing will start to reveal it: the card is the picture
                    self.live._reveal()
            self._slides(gen, e, offset)
        else:
            self.app.video.play(s["video"], headers=s.get("headers"), start=offset + e.get("in", 0), audio=s.get("audio"))
        artist, title = (self.ch.name, e["title"]) if e.get("kind") else parse_title(e["title"], e.get("uploader", ""))
        c = entry(self.app.config, self.cid) or {}
        if c.get("card", True) and e.get("kind", "show") == "show":
            self.live.card = {"artist": artist, "song": title, "label": "", "until": time.monotonic() + CARD_SECONDS}
            self.app.after(CARD_SECONDS + 0.05, self.app.invalidate)
        print(f"[video] {self.ch.name}: {artist} - {title} from {offset:.0f} s of {e['duration']:.0f}")
        left = (cur["stop"] - datetime.now(timezone.utc)).total_seconds()
        self.app.cancel(self._timer)
        self.app.cancel(self._stop_timer)
        if left > CARD_SECONDS + 2 and c.get("card", True) and e.get("kind", "show") == "show":
            self._timer = self.app.after(left - CARD_SECONDS, lambda: gen == self.gen and self._card_again())
        # The next is due at the stop whatever this one has left (a late start
        # ends late): its tail goes, so the lateness doesn't pile up video by video.
        self._stop_timer = self.app.after(max(0.5, left), lambda: gen == self.gen and self.start(cont=True))
        # the next video resolved ahead, so its start is only mpv's open
        sched = self.sched
        nxt = sched.at(cur["stop"] + timedelta(seconds=1)) if sched else None
        if nxt and nxt["entry"]["id"] != e["id"] and not nxt["entry"].get("url"):
            delay = max(0.5, left - AHEAD)
            self.app.after(delay, lambda: gen == self.gen and threading.Thread(
                target=lambda: _resolve_quietly(nxt["entry"]["id"]), daemon=True).start())

    def _slides(self, gen, e, offset):
        """A bumper's slides on the lower third, each for its time, from
        `offset` seconds into the break."""
        base = time.monotonic() - offset
        t = e.get("lead_ms", 0) / 1000
        for text, ms in zip(e.get("slides") or [], e.get("slide_ms") or []):
            a, b, t = t, t + ms / 1000, t + ms / 1000
            if base + b <= time.monotonic():
                continue
            card = {"artist": self.ch.name, "song": "", "label": text, "until": base + b}
            self.app.after(max(0.0, base + a - time.monotonic()), lambda card=card: gen == self.gen and self._show(card))

    def _show(self, card):
        self.live.card = card
        self.app.invalidate()
        self.app.after(max(0.05, card["until"] - time.monotonic() + 0.05), self.app.invalidate)

    def _card_again(self):
        if self.live.card:
            self.live.card["until"] = time.monotonic() + CARD_SECONDS
            self.app.invalidate()
            self.app.after(CARD_SECONDS + 0.05, self.app.invalidate)

    def ended(self, reason: str):
        """The video's stream ended: the next is due (eof), or this one
        failed and is dropped from the order. On Spelunkr the network's
        clock says what's next: a file that ends early waits for its stop,
        one that fails is tried again at its offset."""
        e = (self.cur or {}).get("entry") or {}
        if e.get("kind"):
            if (self.cur["stop"] - datetime.now(timezone.utc)).total_seconds() > 2:
                if reason == "stalled":         # archive.org slow for a moment: mpv fills its cache; a reload
                    print(f"[spelunkr] {e.get('title')!r} waiting on archive.org")    # would fetch the index again
                    return
                if reason != "eof" and e["kind"] != "card":
                    print(f"[spelunkr] {e.get('title')!r} stopped ({reason}): trying it again")
                    self.app.after(15.0, lambda gen=self.gen: gen == self.gen and self.start())
                return
            self.start(cont=True)
            return
        if self.cur and reason != "eof" and self.sched:
            left = (self.cur["stop"] - datetime.now(timezone.utc)).total_seconds()
            if left > 5:
                print(f"[video] {self.cur['entry']['id']} ended early ({reason}, {left:.0f} s left): dropped")
                self._drop(self.cur["entry"]["id"])
                self.cur = None                 # the order closed up: whatever is due now, from its top
        self.start(cont=True)

    def stop(self):
        self.gen += 1
        self.app.cancel(self._timer)
        self.app.cancel(self._stop_timer)
        self.live.card = None


def _resolve_quietly(video_id):
    from . import ytdl
    try:
        ytdl.stream(video_id)
    except Exception as e:
        print(f"[video] ahead: {video_id} {e.__class__.__name__}")
