"""Video channels: YouTube playlists and channels, mixed, as a channel of
videos on a timeline.

Each channel in the settings (name, number, sources, how they're sorted)
sits after Cathode's own channels. A source is a playlist, a YouTube
channel or an @handle; its full list of videos is fetched weekly (ytdl).
The running order is a libchannels.Timeline, as a library channel's is:
written down a day at a time with any of the sort methods (Mix, the
default, interleaves the sources by their shares of the airtime), the
rules (on-air hours, time slots, seasons, word filters) and the skipping
of a video that can't play. Tuning in lands mid-video, the guide lists
what's coming, tuning away and back finds the same video further in. A
lower-third names each video as it starts and as it ends.

The Player here plays every timeline: video channels', library
channels' and Spelunkr's."""

from __future__ import annotations


import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from .epg import Program
from .playlist import Channel

SCHEME = "cathode://video/"
MAX_SKIPS = 40                  # library titles that may fail in a row before the stand-by card
CARD_SECONDS = 8.0              # the lower-third at a video's start and before its end
AHEAD = 20.0                    # seconds before a video is due that its stream is resolved
GRACE = 20.0                    # a video due this recently starts from its top, not its offset
LONG = 600                      # videos this long (median) get their own guide listings
WEIGHTINGS = [("auto", "Auto"), ("equal", "Equal"), ("manual", "Manual")]
GUIDES = [("auto", "Auto"), ("video", "Per video"), ("blocks", "Half-hour blocks")]
ORDERS = [("listed", "As listed"), ("reversed", "Reversed"), ("title", "By title")]
AS = [("show", "One show, in order"), ("videos", "Separate videos")]
LIMITS = [0, 25, 50, 100, 250, 500, 1000]       # a source's newest this many (0: all)
MIN_SECONDS = [0, 30, 60, 120, 300, 600]
MAX_SECONDS = [0, 1800, 3600, 7200, 10800, 14400, 28800]     # 0: any length

# The decade music playlists a fresh install once had (4.34 to 4.53): taken out
# of configs that still have them untouched, at the user's word (2026-11-15).
RETIRED = ("PLkqz3S84Tw-Qjyd_zHSVH_Xj6ge7yrgYI", "PL9tY0BWXOZFtv0mU4GO2j_jOB4512Qo1H", "PL9tY0BWXOZFu4vlBOzIOmvT6wjYb2jNiV")

# A fresh install's channel: bideogaymin.
PREFILL = [
    {"name": "bideogaymin", "max_seconds": 14400, "sources": [
        "@ScottTheWoz", "@Caddicarus", "@LGR", "@GameGrumps", "@TheGrumps", "@BringusStudios", "@JonBringus",
        "@NitroRad", "@StopSkeletonsFromFighting", "@PlanetClue", "@Billiam", "@GamingHistorian",
        "@IronPineapple", "@brutalmoose"]},
]


def new_channel(name: str = "", sources=()) -> dict:
    """A channel's settings entry with every field at its default."""
    return {"id": uuid.uuid4().hex[:8], "name": name, "number": "auto",
            "sources": [{"url": s, "weight": 1} if isinstance(s, str) else dict(s) for s in sources],
            "order": "mix", "block": 0, "weighting": "auto", "min_seconds": 60, "max_seconds": 0,
            "skip_shorts": True, "skip_live": True, "guide": "auto", "card": True}


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
        config.video_channels = [new_channel("", [u]) for u in old] + prefill()
        config.music_playlists = []
    config.video_channels = [fix(c) for c in (config.video_channels or [])]
    if not getattr(config, "retired_music", False):
        config.retired_music = True
        keep = [c for c in config.video_channels
                if not (not c.get("name") and len(c.get("sources") or []) == 1
                        and any(r in c["sources"][0].get("url", "") for r in RETIRED))]
        if len(keep) != len(config.video_channels):
            config.video_channels = keep
            import time
            config.channels_edited, config.channels_editor = time.time(), getattr(config, "sync_id", "") or ""
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
    from . import libchannels
    return next((c for c in config.video_channels if c["id"] == cid), None) or libchannels.entry(config, cid)


def add_to(chans: list, config, names: Optional[dict] = None) -> list:
    """The lineup with the video channels placed: at the number each asks
    for (bumped past one that's taken), or on after the last; `names` has
    the titles resolved so far, the rest are named for their first source's
    cache, or 'Video Channel' until then."""
    from . import ytdl
    from . import libchannels
    out = [c for c in chans if not is_made(c)]
    if not out and not (config.video_channels or getattr(config, "library_channels", None)):
        return out
    taken = {c.number for c in out}
    nxt = int(max((c.number for c in out), default=0)) + 1
    for c in getattr(config, "library_channels", None) or []:     # numbers library channels ask for: kept for them
        try:
            taken.add(int(c.get("number")))
        except (TypeError, ValueError):
            pass
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
    return libchannels.add_to(out, config)


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


def guide_style(c: dict, sched) -> str:
    style = c.get("guide", "auto")
    if style == "auto":
        return "video" if sched.median() >= LONG else "blocks"
    return style


def fill_guide(epg, chans: list, schedules: dict, config=None, now=None, hours: int = 0):
    """Each video channel's listings into the guide (programmes())."""
    hours = hours or 24 * int(getattr(config, "guide_days", 2) or 2)
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
            cur, n = sched.at(t0) or sched.at(now), 0
            for _ in range(400):        # opening in a break (or a second half): from the programme it belongs to
                if not cur or not (cur["entry"].get("kind") in ("ad", "bump", "brb", "card") or cur["entry"].get("part")):
                    break
                cur = sched.at(cur["start"] - timedelta(seconds=0.5)) or cur
                if cur["start"] <= t0 - timedelta(hours=12):
                    break
            while cur and cur["start"] < end and n < 8000:
                e = cur["entry"]
                if e.get("kind") == "signoff":
                    back = cur["stop"].astimezone()
                    progs.append(Program(channel_id=ch.epg_id, title="Off the air", start=cur["start"], stop=cur["stop"],
                                         description=f"{ch.name} is off the air. Back at "
                                                     f"{back:%I:%M %p}".replace(" 0", " ").lstrip("0") + "."))
                elif e.get("kind") and not e.get("yt"):     # Spelunkr, the library: shows, each running on over the breaks after it
                    if (e["kind"] == "show" and not e.get("part")) or not progs:
                        progs.append(Program(channel_id=ch.epg_id, title=e["title"], start=cur["start"], stop=cur["stop"],
                                             category=e.get("category") or c.get("category", "Video"),
                                             description=e.get("desc", ""), episode=e.get("episode_text", ""),
                                             rating=e.get("rating", ""), icon=e.get("icon", ""), air=e.get("air", ""),
                                             quality=e.get("quality", ""), audio=e.get("audio", ""),
                                             minutes=int(e.get("minutes") or 0), score=e.get("score", ""),
                                             logo=e.get("logo", ""), art=e.get("art", ""), flag=e.get("flag", "")))
                    else:
                        progs[-1].stop = cur["stop"]
                else:
                    artist, title = parse_title(e["title"], e.get("uploader", ""))
                    progs.append(Program(channel_id=ch.epg_id, title=title, start=cur["start"], stop=cur["stop"],
                                         category="Video", description=f"From {artist or e.get('uploader', '')}.",
                                         icon=e.get("icon", ""), minutes=max(1, round(e["duration"] / 60)),
                                         episode=artist or e.get("uploader", "")))
                cur = sched.at(cur["stop"] + timedelta(seconds=0.5))
                n += 1
        else:
            slot = timedelta(minutes=30)
            for i in range(hours * 2):
                a, b = t0 + i * slot, t0 + (i + 1) * slot
                names, cur, u, off = [], sched.at(a), a, True
                while cur and u < b and len(names) < 12:
                    if cur["entry"].get("kind") != "signoff":
                        off = False
                        artist, song = parse_title(cur["entry"]["title"], cur["entry"].get("uploader", ""))
                        names.append(f"{artist}: {song}" if artist else song)
                    u = cur["stop"] + timedelta(seconds=0.5)
                    cur = sched.at(u)
                progs.append(Program(channel_id=ch.epg_id, title="Off the air" if off and cur is not None and names == []
                                     else ch.name, start=a, stop=b, category="Music",
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
        _apply(app, *_build(list(app.config.video_channels), dict(app.listings), list(app.channels),
                            dict(getattr(app, "schedules", {}) or {}),
                            24 * int(getattr(app.config, "guide_days", 2) or 2), getattr(app, "library", None)), report)
        return
    if getattr(app, "_vc_busy", False):
        app._vc_again = True
        app._vc_report = getattr(app, "_vc_report", False) or report
        return
    app._vc_busy, app._vc_again = True, False
    app._vc_last = time.monotonic()
    args = (list(app.config.video_channels), dict(app.listings), list(app.channels), dict(app.schedules),
            24 * int(getattr(app.config, "guide_days", 2) or 2), getattr(app, "library", None))

    def work():
        try:
            built = _build(*args)
        except Exception as e:
            print(f"[video] schedules: {e!r}")
            built = None
        app.post(_built, app, built, report)
    threading.Thread(target=work, daemon=True).start()


def _build(cfg_channels: list, listings: dict, chans: list, prev: Optional[dict] = None, hours: int = 48,
           index=None):
    """Each video channel's Timeline (the one in hand when neither the
    channel nor its lists changed), everyone's listings for the guide."""
    from . import libchannels as lc, spelunkr
    schedules = {}
    for c in cfg_channels:
        stamp, old = lc.yt_stamp(c, listings, index), (prev or {}).get(c["id"])
        if isinstance(old, lc.Timeline) and old.sig == lc.signature(c) and old.stamp == stamp:
            old.c, old.guide_memo = dict(c), None       # (the guide style, the card: not in the days drawn)
            schedules[c["id"]] = old
        else:
            schedules[c["id"]] = lc.Timeline(c, index, made=(lc.yt_groups(c, listings), stamp), cid=c["id"])
    schedules.update(spelunkr.SCHEDULES)
    schedules.update(lc.SCHEDULES)
    return schedules, programmes(chans, schedules, hours=hours), listings


def _built(app, built, report):
    app._vc_busy = False
    if built:
        _apply(app, *built, report)
    if app._vc_again:
        again = getattr(app, "_vc_report", False)
        app._vc_report = False
        rebuild(app, again)


def _apply(app, schedules: dict, progs: dict, listings: dict, report: bool = False):
    from . import libchannels as lc
    app.schedules = schedules
    for k in [k for k in lc.SCHEDULES if not k.startswith(lc.PREFIX)]:
        del lc.SCHEDULES[k]
    for cid, s in schedules.items():            # (the video channels' among the timelines another Cathode asks for)
        if isinstance(s, lc.Timeline) and not cid.startswith(lc.PREFIX):
            lc.SCHEDULES[cid] = s
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
        for c in app.config.video_channels:
            s = schedules.get(c["id"])
            if s is not None and s.entries:
                print(f"[video] {c.get('name') or c['id']}: {len(s.entries)} videos")
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
        self._skips, self._began = 0, 0.0       # library titles skipped in a row; when the last one started

    @property
    def sched(self):
        from . import libchannels, spelunkr
        s = (getattr(self.app, "schedules", {}).get(self.cid) or spelunkr.SCHEDULES.get(self.cid)
             or libchannels.SCHEDULES.get(self.cid))
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
        if cur is not None and cur["entry"].get("kind") in ("signoff", "brb"):
            self._sign_off(gen, cur)
            return
        self.live.signoff = None
        if cur is None and hasattr(sched, "coming"):
            # A timeline with nothing that can play just now: stand-by, and a look again in a minute.
            self.live.standby = True
            if self.live.phase == "cover":
                self.live._reveal()
            self._stop_timer = app.after(60.0, lambda: gen == self.gen and self.start())
            return
        if cur is None:
            self.live.on_video("video_ended", reason="nothing to play")
            return
        e = cur["entry"]
        print(f"[video] {self.ch.name}: {e.get('title', '')!r} due, {('at ' + format((now - cur['start']).total_seconds(), '.0f') + ' s') if not cont else 'from its top'}")

        def work():
            try:
                if e.get("url"):        # a Spelunkr file plays as it is: no yt-dlp in the way
                    s = {"video": e["url"]}
                elif e.get("plex"):     # a library title: its stream asked of the server, from where it's up to
                    from . import libchannels
                    s = libchannels.stream(app, e, max(0.0, (now - cur["start"]).total_seconds()) + e.get("in", 0))
                else:
                    from . import ytdl
                    ytdl.MAX_HEIGHT = int(app.config.video_quality or 1080)
                    s = ytdl.stream(e["id"])
            except Exception as ex:
                if e.get("plex"):
                    from . import libchannels
                    if libchannels.broken(ex):      # the file, not the server: on to the next title
                        print(f"[library] {e.get('title', '')!r} {e.get('episode_text', '')} can't play ({ex}): skipped")
                        app.post(self._skip, gen, e["id"], cur)
                    else:
                        print(f"[library] {e.get('title', '')!r}: the server didn't answer ({ex!r}): stand-by")
                        app.post(self._hold, gen, cur)
                    return
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

    def _skip(self, gen, video_id, cur=None):
        """A video that can't play leaves the order and the next starts at
        once. Library titles failing one after another without any playing
        (something wrong beyond one file) stop at the stand-by card instead
        of emptying the schedule."""
        if gen != self.gen:
            return
        if cur is not None:
            self._skips += 1
            if self._skips > MAX_SKIPS:
                self._skips = 0
                self._hold(gen, cur)
                return
        self._drop(video_id)
        self.cur = None
        self.start(cont=True)

    def _sign_off(self, gen, cur):
        """Off the air: the picture stops for the colour bars (the skin's)
        until the channel signs on again."""
        self.cur = cur
        live = self.live
        self.app.video.stop()
        kind = cur["entry"]["kind"]
        if kind == "brb" and cur["entry"]["duration"] < 5:
            kind = "gap"                    # a few seconds between clips: black, not a flash of the slate
        live.signoff = {"name": self.ch.name, "back": cur["stop"], "style": kind}
        live.standby = False
        if live.phase == "cover":
            live._reveal()
        self.app.invalidate()
        left = (cur["stop"] - datetime.now(timezone.utc)).total_seconds()
        self.app.cancel(self._stop_timer)
        self._stop_timer = self.app.after(max(0.5, left), lambda: gen == self.gen and self.start(cont=True))

    def _hold(self, gen, cur):
        """The server is away (a broken file is skipped, not held): the
        stand-by card, another try each minute while the title's slot lasts.
        The clock is the schedule's, so the next title still starts on time."""
        if gen != self.gen:
            return
        self.cur = cur
        live = self.live
        live.standby = True
        if live.phase == "cover":
            live._reveal()
        self.app.invalidate()
        left = (cur["stop"] - datetime.now(timezone.utc)).total_seconds()
        self.app.cancel(self._stop_timer)
        self._stop_timer = self.app.after(max(1.0, min(left, 60.0)),
                                          lambda: gen == self.gen and self.start(cont=left <= 60.0))

    def _play(self, gen, cur, s, cont=False):
        if gen != self.gen:
            return
        e = cur["entry"]
        offset = max(0.0, (datetime.now(timezone.utc) - cur["start"]).total_seconds())
        if (cont or offset < GRACE) and (not e.get("kind") or e.get("yt") or e.get("kind") in ("ad", "bump")):
            offset = 0.0        # a handover, or due just now (resolving and opening took the seconds): the top, not a cut head
        self.cur = cur          # (Spelunkr keeps the network's clock: always the true offset)
        self._began = time.monotonic()
        if e.get("kind") == "card":                     # a Spelunkr bumper: its music, its slides on the lower third
            if e.get("url"):
                self.app.video.play(e["url"], start=offset + e.get("in", 0))
            else:
                self.app.video.stop()
                if self.live.phase == "cover":      # nothing will start to reveal it: the card is the picture
                    self.live._reveal()
            self._slides(gen, e, offset)
        else:
            self.app.video.play(s["video"], headers=s.get("headers"), audio=s.get("audio"),
                                start=max(0.0, offset + e.get("in", 0) - s.get("base", 0.0)))   # (a transcode starts at its base)
        self.live.radio = e.get("radio")       # a music channel's song: the card that stands in for a picture
        artist, title = (self.ch.name, e["title"]) if e.get("kind") and not e.get("yt") else \
            parse_title(e["title"], e.get("uploader", ""))
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
        if nxt and nxt["entry"]["id"] != e["id"] and nxt["entry"].get("plex"):
            # a library title: asked of the server ahead, so a broken one is out of the order before it's due
            self.app.after(max(0.5, left - AHEAD), lambda: gen == self.gen and threading.Thread(
                target=self._check_ahead, args=(gen, nxt["entry"]), daemon=True).start())
        elif nxt and nxt["entry"]["id"] != e["id"] and not nxt["entry"].get("url"):
            delay = max(0.5, left - AHEAD)
            self.app.after(delay, lambda: gen == self.gen and threading.Thread(
                target=lambda: _resolve_quietly(nxt["entry"]["id"]), daemon=True).start())

    def _check_ahead(self, gen, e):
        from . import libchannels
        try:
            libchannels.stream(self.app, e, 0.0)
        except Exception as ex:
            if libchannels.broken(ex):
                print(f"[library] ahead: {e.get('title', '')!r} {e.get('episode_text', '')} can't play ({ex}): skipped")
                self.app.post(lambda: gen == self.gen and self._drop(e["id"]))

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
        if self._began and time.monotonic() - self._began > 30:
            self._skips = 0                 # it played a while: not one of a run of failures
        if e.get("kind") in ("signoff", "brb"):
            return                          # (the picture stopped for the bars: nothing ended)
        if e.get("kind") and not e.get("yt"):
            if (self.cur["stop"] - datetime.now(timezone.utc)).total_seconds() > 2:
                if reason == "stalled":         # archive.org slow for a moment: mpv fills its cache; a reload
                    print(f"[spelunkr] {e.get('title')!r} waiting on archive.org")    # would fetch the index again
                    return
                if reason != "eof" and e.get("plex"):       # the file broke off: on to the next title
                    print(f"[library] {e.get('title')!r} stopped ({reason}): skipped")
                    self._skip(self.gen, e["id"], self.cur)
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
        self.live.signoff = None
        self.live.radio = None


def _resolve_quietly(video_id):
    from . import ytdl
    try:
        ytdl.stream(video_id)
    except Exception as e:
        print(f"[video] ahead: {video_id} {e.__class__.__name__}")
