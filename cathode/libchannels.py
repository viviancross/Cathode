"""Library channels: channels made from the Plex library, on a timeline.
(Video channels, made from YouTube lists, run on the same timeline: their
titles come from yt_groups() instead of the library.)

Each channel in the settings (name, number, sources, sort method) sits
after the lineup. A source is a slice of the library index (library.py):
a whole library, a genre, a decade, a studio, a rating band, one show or
picked titles.
The titles it matches fall into groups, a show's episodes in order being
one group and each movie its own.

The running order is written down a broadcast day at a time (4 AM to
4 AM) in the cache folder, with the rotation's state as the day began.
The next day carries on from where the last ended, so a show's episodes
keep their order across days and restarts, and the guide can list the days
ahead. Editing a channel rewrites today onward; a changed library rewrites
tomorrow onward.

The timelines here are played by videochannels.Player (as Spelunkr's are):
an entry carries `plex`, its rating key, and its stream is asked of the
server as it comes due. A title that can't play (a damaged file, one that
left the library) is skipped: what follows moves up to start at once, the
guide with it, and the title stays off the air for a week. Only the server
itself being away leaves the stand-by card up."""

from __future__ import annotations

import collections
import hashlib
import json
import os
import random
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import library, sync as _sync
from .playlist import Channel

PREFIX = "lib."                 # a library channel's id among the video channels'
VERSION = 1                     # of the written-down schedule
DAY_STARTS = 4                  # the broadcast day turns over at 4 AM
MIN_SECONDS = 60                # shorter titles stay out of a programme channel
KEEP_DAYS = 1                   # days behind today kept on disk
OFF_AIR = 7 * 86400             # a title that couldn't play is left out of the days drawn up this long
REFRESH = 6 * 3600              # the server asked again for what changed, this often
SCHEDULES: dict = {}            # channel id (with its prefix) -> Timeline

ORDERS = [("mix", "Mix"), ("random", "Random"), ("cyclic_shuffle", "Cyclic Shuffle"), ("block_shuffle", "Block Shuffle"),
          ("block_cyclic", "Block Cyclic"), ("marathon_shuffle", "Marathon Shuffle"),
          ("marathon_cyclic", "Marathon Cyclic"), ("round_robin_shuffle", "Round Robin Shuffle"),
          ("round_robin_cyclic", "Round Robin Cyclic"), ("playlist", "Playlist Order")]
BLOCKS = {"block_shuffle": 2, "block_cyclic": 2, "marathon_shuffle": 12, "marathon_cyclic": 12}
KINDS = [("all", "Everything"), ("genre", "Genre"), ("decade", "Decade"), ("studio", "Studio"),
         ("rating", "Rating"), ("show", "Show"), ("title", "Title"), ("season", "Season"),
         ("collection", "Collection"), ("playlist", "Playlist")]
ITEM_KINDS = ("title", "season", "playlist")    # kinds that pick episodes, not whole shows
WATCHED = [("all", "Everything"), ("unwatched", "Unwatched only"), ("watched", "Watched only")]
EPISODE_START = [("first", "First episode"), ("random", "A random episode")]
KIDS = ["TV-Y", "TV-Y7", "TV-Y7-FV", "TV-G", "G"]
MATURE = ["TV-MA", "R", "NC-17"]
OFF = "-off-"                   # an off-the-air stretch among the days drawn up
BRB = "-brb-"                   # a "we'll be right back" slate: a break's time nothing fits
NEXT = "-next-"                 # the "coming up next" card before a programme
SLATES = (OFF, BRB, NEXT)       # what stands in a day for no title
NEXT_SECONDS = 8
PADS = [(0, "No"), (5, "5 minutes"), (10, "10 minutes"), (15, "Quarter hours"), (30, "Half hours"), (60, "Hours")]
MIDS = [("off", "Off"), ("halfway", "Halfway"), ("every10", "Every 10 minutes"), ("every15", "Every 15 minutes"),
        ("every20", "Every 20 minutes"), ("every30", "Every 30 minutes"), ("chapters", "At chapter marks"),
        ("silences", "At quiet moments")]
COUNTS = [(0, "Fill the time")] + [(n, f"{n} each") for n in (1, 2, 3, 4, 5, 6, 8)]
BREAK_LENGTHS = [60, 90, 120, 180, 240]
MID_FROM = 15 * 60              # a programme this long gets breaks in it
SHORT, NEAR = 600, 360          # titles under ten minutes break only within six of the quarter/half hour
CLIP_MAX = 600                  # break material: clips up to ten minutes
FLOOR = 0.05                    # Mix, automatic weighting: no source under this share of the airtime
# What a channel's days are drawn from: a change to any of them redraws today onward.
SIG_KEYS = ("sources", "order", "block", "seed", "hours", "content", "words_out", "words_in", "weighting",
            "min_seconds", "max_seconds", "skip_shorts", "skip_live", "premieres", "breaks", "specials", "watched",
            "max_movies", "mature_from", "marathons", "episode_start", "reset", "pins", "title_weights", "balance",
            "premiere_times", "premiere_days", "premiere_count", "premiere_preroll", "seasonal")
# Holidays (the seasonal cycler): words in an episode's or a movie's title, and when they're in season
# (from month/day to month/day). A title with one airs only then, and more often then.
HOLIDAYS = [
    ("Halloween", re.compile(r"halloween|treehouse of horror|trick.or.treat", re.I), (10, 1), (10, 31)),
    ("Thanksgiving", re.compile(r"thanksgiving", re.I), (11, 1), (11, 30)),
    ("Christmas", re.compile(r"christmas|x-?mas\b|santa\b|grinch|hanukkah|chanukah|kwanzaa|nutcracker", re.I),
     (11, 25), (12, 31)),
    ("New Year", re.compile(r"new year'?s", re.I), (12, 26), (1, 2)),
    ("Valentine's Day", re.compile(r"valentine", re.I), (2, 1), (2, 14)),
    ("St. Patrick's Day", re.compile(r"st\.? patrick|leprechaun", re.I), (3, 10), (3, 17)),
    ("Easter", re.compile(r"easter\b", re.I), (3, 20), (4, 25)),
    ("Fourth of July", re.compile(r"fourth of july|4th of july", re.I), (6, 28), (7, 4)),
]


def holiday(i: dict) -> str:
    """The holiday a title is for ("" for none), by its words."""
    text = f"{i.get('name') or ''} {i['title'] if i.get('type') != 'episode' else ''}"
    return next((h for h, rx, _a, _b in HOLIDAYS if rx.search(text)), "")


def in_season(h: str, lt: datetime) -> bool:
    _n, _rx, a, b = next(x for x in HOLIDAYS if x[0] == h)
    md = (lt.month, lt.day)
    return a <= md <= b if a <= b else (md >= a or md <= b)
NEW_DAYS = 14                   # a title added this recently is new (the guide says so; premieres pick from them)
PREMIERE_HOUR = 20              # premieres air at the first programme from 8 PM
PREMIERES = [("off", "Off"), ("prime", "8 PM, the newest arrival")]
WEIGHTINGS = [("auto", "Auto"), ("equal", "Equal"), ("manual", "Manual")]
CONTENT = [("any", "Adults"), ("family", "Everyone"), ("kids", "Kids")]     # NostalgiaTV's Audience
# When a channel is on the air: [sign on, sign off] hours, or None for always.
HOURS = [(None, "Always"), ([6, 2], "6 AM to 2 AM"), ([6, 0], "6 AM to midnight"), ([5, 1], "5 AM to 1 AM"),
         ([7, 23], "7 AM to 11 PM"), ([6, 18], "Daytime, 6 AM to 6 PM"), ([18, 6], "Nights, 6 PM to 6 AM"),
         ([22, 6], "Late, 10 PM to 6 AM")]
# When a source airs (a time slot). Monday is day 0; a slot past midnight belongs to the night it began.
AIRS = [(None, "Any time"), ({"from": 6, "to": 12}, "Mornings"), ({"from": 12, "to": 17}, "Afternoons"),
        ({"from": 17, "to": 20}, "Early evening"), ({"from": 20, "to": 23}, "Prime time"),
        ({"from": 23, "to": 6}, "Late night"), ({"days": [5], "from": 7, "to": 12}, "Saturday mornings"),
        ({"days": [0, 1, 2, 3, 4], "from": 15, "to": 18}, "After school"), ({"days": [5, 6]}, "Weekends"),
        ({"days": [0, 1, 2, 3, 4]}, "Weekdays"), ({"days": [4, 5], "from": 20, "to": 2}, "Friday and Saturday nights"),
        ({"days": [0, 1, 2, 3, 4], "from": 20, "to": 23}, "Weeknight prime time"),
        ({"days": [5], "from": 12, "to": 18}, "Saturday afternoons"), ({"days": [6], "from": 12, "to": 18}, "Sunday afternoons")]
# (A source of one show in a slot is a marathon: the slot is all that show, in order.)
SEASONS = [(None, "All year"), ([10], "October"), ([11], "November"), ([12], "December"),
           ([10, 11, 12], "October to December"), ([6, 7, 8], "Summer"), ([1, 2], "January and February")]

_TAIL = re.compile(r"\s+(Television Animation|Animation Studios?|Animation|Productions?|Cartoons|Studios?|"
                   r"Networks?|Television|Media|Company|Entertainment|Pictures)$", re.I)


def brand(studio: str) -> str:
    """'Nickelodeon Animation Studio' and 'Nickelodeon Productions' are both
    Nickelodeon: a studio's name without its trade."""
    s = (studio or "").strip()
    return _TAIL.sub("", s) or s


# ── Channels in the settings ─────────────────────────────────────────────

def new_channel(name: str = "", sources=(), order: str = "cyclic_shuffle", **more) -> dict:
    d = {"id": uuid.uuid4().hex[:8], "name": name, "number": "auto", "sources": [dict(s) for s in sources],
         "order": order, "block": 0, "card": False, "starter": False}
    d.update(more)
    return d


def entry(config, cid: str) -> Optional[dict]:
    if not cid.startswith(PREFIX):
        return None
    return next((c for c in getattr(config, "library_channels", None) or [] if c["id"] == cid[len(PREFIX):]), None)


def is_library(ch) -> bool:
    from . import videochannels as vc
    return vc.is_video(ch) and vc.cid_of(ch).startswith(PREFIX)


def add_to(chans: list, config) -> list:
    """The lineup with the library channels placed: at the number each asks
    for (bumped past one that's taken), or in a block of their own from the
    next hundred up (a lineup ending at 69 puts them from 101)."""
    from . import videochannels as vc
    out = [c for c in chans if not is_library(c)]
    made = getattr(config, "library_channels", None) or []
    if not made:
        return out
    taken = {c.number for c in out}
    nxt = (int(max(c.number for c in out)) // 100 + 1) * 100 + 1 if out else 1
    for c in made:
        want = c.get("number", "auto")
        try:
            num = nxt if want == "auto" else int(want)
        except (TypeError, ValueError):
            num = nxt
        while num in taken:
            num += 1
        taken.add(num)
        if want == "auto":
            nxt = num + 1
        ch = Channel(number=num, name=c.get("name") or "Library Channel", url=vc.SCHEME + PREFIX + c["id"],
                     logo=c.get("logo", ""), epg_id=vc.epg_id(PREFIX + c["id"]), group=c.get("group") or "Library")
        at = next((i for i, o in enumerate(out) if o.number > num), len(out))
        out.insert(at, ch)
    return out


# ── Rules: when a channel and its sources are on ─────────────────────────

def on_air(c: dict, t: float) -> bool:
    """Whether the channel is on the air at a moment (its hours, local time)."""
    hrs = c.get("hours")
    if not hrs or hrs[0] == hrs[1]:
        return True
    a, b = hrs
    lt = datetime.fromtimestamp(t)
    h = lt.hour + lt.minute / 60 + lt.second / 3600
    return a <= h < b if a < b else (h >= a or h < b)


def next_on(c: dict, t: float) -> float:
    """When the channel next signs on after a moment it's off the air."""
    lt = datetime.fromtimestamp(t)
    on = lt.replace(hour=c["hours"][0], minute=0, second=0, microsecond=0)
    if on <= lt:
        on += timedelta(days=1)
    return on.timestamp()


def active(src: dict, lt: datetime) -> bool:
    """Whether a source airs at a local moment: its season, its slot."""
    months = src.get("season")
    if months and lt.month not in months:
        return False
    a = src.get("airs") or {}
    day = lt.weekday()
    f, to = a.get("from"), a.get("to")
    if f is not None and to is not None:
        h = lt.hour + lt.minute / 60
        if f < to:
            if not f <= h < to:
                return False
        elif h >= f:
            pass
        elif h < to:
            day = (day - 1) % 7         # after midnight: the night before's slot
        else:
            return False
    return not a.get("days") or day in a["days"]


def _next_hour(t: float) -> float:
    lt = datetime.fromtimestamp(t)
    return (lt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).timestamp()


def _words(c: dict, text: str) -> bool:
    """Whether a title gets past the channel's word filters."""
    t = (text or "").lower()
    out = [w.strip().lower() for w in c.get("words_out") or [] if w.strip()]
    need = [w.strip().lower() for w in c.get("words_in") or [] if w.strip()]
    return not any(w in t for w in out) and (not need or any(w in t for w in need))


def _rated(c: dict, rating: str) -> bool:
    mode = c.get("content", "any")
    if mode == "kids":
        return rating in KIDS
    if mode == "family":
        return rating not in MATURE
    return True


def expand(c: dict, config) -> dict:
    """The channel with each content group it names replaced by the
    group's own sources (taking the naming source's slot, season, weight,
    leave-out and shuffle)."""
    groups_ = {g["id"]: g for g in getattr(config, "content_groups", None) or []}
    if not any(s.get("kind") == "group" for s in c.get("sources") or []):
        return c
    out = []
    for s in c.get("sources") or []:
        if s.get("kind") != "group":
            out.append(s)
            continue
        over = {k: s[k] for k in ("airs", "season", "weight", "exclude", "shuffle") if k in s}
        out += [dict(sub, **over) for sub in (groups_.get(s.get("value")) or {}).get("sources") or []
                if sub.get("kind") != "group"]
    return dict(c, sources=out)


def signature(c: dict) -> str:
    return hashlib.sha1(json.dumps([VERSION] + [c.get(k) for k in SIG_KEYS], sort_keys=True)
                        .encode()).hexdigest()[:12]


# ── What a channel draws from ────────────────────────────────────────────

def _match(src: dict, obj: dict) -> bool:
    """obj: a show's row or a movie's."""
    kind, val = src.get("kind", "all"), src.get("value")
    if kind == "genre":
        return val in obj["genres"]
    if kind == "decade":
        return bool(obj["year"]) and obj["year"] // 10 * 10 == int(val)
    if kind == "studio":
        return brand(obj["studio"]) == val
    if kind == "rating":
        return obj["rating"] in (val or [])
    if kind == "show":
        return obj.get("key") == val
    if kind == "title":                 # picked titles (a movie, a clip, an episode) by rating key
        return obj.get("plex") in (val if isinstance(val, list) else [val])
    if kind == "season":                # "show key:season number"
        key, _, n = str(val).partition(":")
        return obj.get("show_key") == key and str(obj.get("season")) == n
    if kind in ("collection", "playlist"):
        return (obj.get("key") or obj.get("plex")) in src.get("_keys", ())
    return True


def _matching(src: dict, index):
    """The library's titles a source matches (long enough for a programme)."""
    only = src.get("only")
    if src.get("kind") in ("collection", "playlist"):
        src = dict(src, _keys=set(((getattr(index, src["kind"] + "s", None) or {}).get(src.get("value")) or {})
                                  .get("keys") or ()))
    for sec in index.sections.values():
        if (src.get("section") and sec.key != src["section"]) or (
                not src.get("section") and (sec.breaks or sec.hidden or (sec.kind == "music" and only != "music"))):
            continue
        if only and sec.kind != only:
            continue
        if sec.kind in ("show", "music") and src.get("kind") in ITEM_KINDS:
            yield from (i for i in sec.items if i["duration"] >= MIN_SECONDS and _match(src, i))
        elif sec.kind in ("show", "music"):
            keys = {k for k, sh in sec.shows.items() if _match(src, sh)}
            yield from (i for i in sec.items if i["show_key"] in keys and i["duration"] >= MIN_SECONDS)
        elif src.get("kind") != "show":
            yield from (i for i in sec.items if i["duration"] >= MIN_SECONDS and _match(src, i))


def clips(sources, index) -> list:
    """Break material: the clips some library sources hold (any length up
    to ten minutes, the libraries hidden from On Demand included)."""
    out, seen = [], set()
    for src in sources or []:
        for sec in index.sections.values():
            if src.get("section") and sec.key != src["section"]:
                continue
            for i in sec.items:
                if src.get("specials") and i["season"] != 0:
                    continue                    # (a show's shorts, filed as specials: not its episodes)
                if 0 < i["duration"] <= CLIP_MAX and i["id"] not in seen and _match(src, i if sec.kind != "show" else
                                                                                       sec.shows.get(i["show_key"], {})):
                    seen.add(i["id"])
                    out.append(i)
    return out


def long_clips(sources, index) -> list:
    """Commercial material from long videos (a TV show of old ads, a
    compilation): the titles of the sources marked to be cut into pieces."""
    out = []
    for src in sources or []:
        if src.get("chunks"):
            out += [i for i in _matching(dict(src, only=None), index) if i["duration"] > CLIP_MAX]
    return out


def _brands(c: dict) -> list:
    """Words a channel's bumpers' libraries would carry: its studios'
    first words (four letters of a long one) and initials."""
    out = []
    for s in c.get("sources") or []:
        if s.get("kind") == "studio" and s.get("value"):
            words = str(s["value"]).lower().split()
            out.append(words[0][:4] if len(words[0]) > 4 else words[0])
            if len(words) > 1:
                out.append("".join(w[0] for w in words))
    return out


def default_breaks(c: dict, index) -> dict:
    """Breaks for a channel from what the library holds: commercials from
    every commercials library, bumpers from the libraries named for the
    channel's studio (CN Bumps for a Cartoon Network channel), lined up
    with the half hours, none during programmes."""
    import re
    ads, bumps = [], []
    for sec in index.sections.values():
        if not sec.breaks:
            continue
        t = sec.title.lower()
        if re.search(r"commercial|\bads?\b|promo", t):
            ads.append({"section": sec.key, "kind": "all"})
        elif any(re.search(rf"(^|\W){re.escape(b)}", t) for b in _brands(c)):
            bumps.append({"section": sec.key, "kind": "all"})
    return {"ads": ads, "bumps": bumps, "pad": 30, "mid": "off", "length": 120}


def breaks_of(c: dict, index) -> dict:
    """A channel's breaks as they are: its own, or (never set, as every
    channel starts) the defaults: between programmes, not during them. Set
    off ({}) they're off."""
    if "breaks" in c:
        return c["breaks"] or {}
    return default_breaks(c, index) if index is not None else {}


def groups(c: dict, index) -> list:
    """The titles a channel's sources match, as groups in title order: a
    show's episodes in their order (its specials after them, its shorts left to be bumpers),
    each movie on its own. A title two sources match is in once; one a
    source set to leave out matches isn't in at all, nor one the channel's
    word filters or ratings rule out. A group knows its sources (`src`,
    the first `k`) and weight `w`, for time slots and Mix."""
    srcs = c.get("sources") or []
    banned = {i["id"] for s in srcs if s.get("exclude") for i in _matching(s, index)}
    seen_ = getattr(index, "watched", None) or set()
    want = c.get("watched", "all")
    if want != "all" and seen_:
        banned |= {i["id"] for s in srcs if not s.get("exclude") for i in _matching(s, index)
                   if (i["plex"] in seen_) != (want == "watched")}
    no_specials = c.get("specials", True) is False
    out, seen = {}, set()
    for k, src in enumerate(srcs):
        if src.get("exclude"):
            continue
        w = max(0.0, float(src.get("weight", 1) or 0))
        for i in _matching(src, index):
            if i["id"] in banned or not _rated(c, i["rating"]) or not _words(c, f"{i['title']} {i['name']}") or (
                    no_specials and i["type"] == "episode" and not i["season"]):
                continue
            gid = "s" + i["show_key"] if i["type"] in ("episode", "track") else "m" + i["plex"]
            g = out.get(gid)
            if g is None:
                g = out[gid] = {"id": gid, "title": i["title"], "items": [], "src": set(), "k": k, "w": w}
            g["src"].add(k)
            g["w"] = max(g["w"], w)
            if i["id"] not in seen:
                seen.add(i["id"])
                g["items"].append(i)
    tws = c.get("title_weights") or {}
    for g in out.values():
        if g["id"] in tws:
            g["tw"] = max(0.0, float(tws[g["id"]] or 0))
        if len(g["items"]) > 1:
            # specials after the seasons; a show's shorts among them are its network's bumpers, not episodes
            g["items"].sort(key=lambda i: (i["season"] == 0, i["season"], i.get("album", ""), i["episode"], i["air"]))
            if any(i["season"] for i in g["items"]):
                g["items"] = [i for i in g["items"] if i["season"] or i["duration"] > CLIP_MAX] or g["items"]
    return sorted((g for g in out.values() if g["items"]), key=lambda g: (g["title"].lower(), g["id"]))


def yt_groups(c: dict, listings: dict) -> list:
    """A video channel's titles from its sources' YouTube lists: each list
    filtered (lengths, Shorts, streams, words), cut to its newest, put in
    its order; a channel or @handle is one show in that order, a playlist
    separate videos (unless the source says otherwise)."""
    from . import ytdl
    from .videochannels import clean_name
    out, seen = [], set()
    lo, hi = c.get("min_seconds", 60), c.get("max_seconds", 0)
    for k, s in enumerate(c.get("sources") or []):
        lst = listings.get(s["url"])
        if not lst:
            continue
        es = list(lst.get("entries") or [])
        if not c.get("skip_live", True):
            es += (listings.get(s["url"] + "#live") or {}).get("entries") or []
        if int(s.get("limit") or 0):
            es = es[:int(s["limit"])]
        if s.get("order") == "reversed":
            es.reverse()
        elif s.get("order") == "title":
            es.sort(key=lambda e: (e.get("title") or "").lower())
        name = clean_name(lst.get("title", ""))
        items = []
        for e in es:
            d = float(e.get("duration") or 0)
            if (not e.get("id") or e["id"] in seen or d <= 0 or d < lo or (hi and d > hi)
                    or (c.get("skip_shorts", True) and e.get("short")) or (c.get("skip_live", True) and e.get("live"))
                    or not _words(c, e.get("title", ""))):
                continue
            seen.add(e["id"])
            items.append({"id": e["id"], "type": "video", "title": e.get("title") or "", "name": "", "duration": d,
                          "uploader": e.get("uploader") or name, "year": 0, "genres": [], "studio": "", "rating": "",
                          "summary": "", "thumb": f"https://i.ytimg.com/vi/{e['id']}/mqdefault.jpg", "added": 0})
        if not items:
            continue
        w = max(0.0, float(s.get("weight", 1) or 0))
        as_ = s.get("as") or default_as(s["url"])
        if as_ == "show":
            out.append({"id": "y" + ytdl.source_key(s["url"]), "title": name or s["url"], "items": items,
                        "src": {k}, "k": k, "w": w})
        else:
            out += [{"id": "v" + i["id"], "title": i["title"], "items": [i], "src": {k}, "k": k, "w": w} for i in items]
    return out


def default_as(url: str) -> str:
    """A playlist is separate videos (songs, say); a creator's channel or
    @handle is one show, its videos in order."""
    from . import ytdl
    return "videos" if "list=" in ytdl.source_url(url) else "show"


def yt_stamp(c: dict, listings: dict, index=None) -> str:
    """Changes when any of the channel's lists is fetched again (or the
    library its breaks come from changes)."""
    return (index.stamp() + "#" if index is not None else "") + "|".join(f"{(listings.get(u) or {}).get('fetched', 0):.0f}"
                    for s in c.get("sources") or [] for u in (s["url"], s["url"] + "#live"))


class Rotor:
    """Draws a channel's next title by its sort method. Its state is a small
    dict that goes to disk with the schedule, so the rotation carries on."""

    def __init__(self, cid: str, order: str, block: int, groups_: list, state: dict, skip=(),
                 weighting: str = "auto", sources=(), start: str = "first", balance: str = "duration"):
        self.cid, self.order, self.all, self.state = cid, order, groups_, state
        self.start, self.balance = start, balance
        self.skip = skip            # titles off the air (they couldn't play)
        self.block = max(1, int(block or BLOCKS.get(order, 1)))
        self.weighting = weighting
        self.shuffles = [s.get("shuffle", True) for s in sources]
        self._ipos: dict = {}
        self._memos: dict = {}      # (pool, what, n) -> the shuffle for it
        self._pools: dict = {}
        self._key = None
        self._use(None)

    def _use(self, eligible):
        """The groups to draw from: all, or those a time slot allows. Each
        slot's rotation (its cycle, its turn) is kept apart in the state;
        where a show is up to is one for all of them."""
        key = "" if eligible is None else hashlib.sha1(",".join(sorted(eligible)).encode()).hexdigest()[:8]
        if key == self._key:
            return
        self._key = key
        p = self._pools.get(key)
        if p is None:
            gs = self.all if eligible is None else [g for g in self.all if g["id"] in eligible]
            mix = {}
            for g in gs:
                mix.setdefault(g.get("k", 0), []).extend(g["items"])
            items = [i for g in gs if g.get("tw", 1.0) > 0 for i in g["items"] * max(1, round(g.get("tw", 1.0)))]
            p = self._pools[key] = (gs, items or [i for g in gs for i in g["items"]], {g["id"]: n for n, g in enumerate(gs)},
                                    [len(g["items"]) ** 0.5 * g.get("w", 1.0) * g.get("tw", 1.0) for g in gs], mix)
        self.groups, self.items, self._gpos, self._weights, self._mix_pools = p
        if not any(self._weights):
            self._weights = None
        self.st = self.state if not key else self.state.setdefault("slots", {}).setdefault(key, {})

    def _rng(self, *what):
        return random.Random(f"{self.cid}:" + ":".join(str(w) for w in what))

    def _shuffled(self, what: str, n: int, of: list) -> list:
        k = (self._key, what, n)
        if k not in self._memos:
            lst = list(of)
            self._rng(self._key, what, n).shuffle(lst) if self._key else self._rng(what, n).shuffle(lst)
            self._memos[k] = lst
        return self._memos[k]

    def _cycle(self, n: int) -> list:
        """Every title, shuffled for cycle n; it doesn't open on the title
        the cycle before closed on."""
        lst = self._shuffled("c", n, self.items)
        if n and len(lst) > 2 and lst[0] is self._shuffled("c", n - 1, self.items)[-1]:
            lst[0], lst[1] = lst[1], lst[0]
        return lst

    def next(self, eligible=None) -> Optional[dict]:
        """The next title to air, from the groups a time slot allows (all,
        by default), passing over any that are off the air."""
        self._use(eligible)
        for _ in range(len(self.items)):
            i = self._draw()
            if i["id"] not in self.skip:
                return i
        return None

    def _draw(self) -> dict:
        o, st = self.order, self.st
        if o == "mix":
            return self._mix()
        if o == "random":
            st["n"] = st.get("n", 0) + 1
            rnd = self._rng("r", st["n"])
            recent = st.setdefault("recent", [])
            keep = min(200, len(self.items) // 5)
            for _ in range(20):
                i = self.items[rnd.randrange(len(self.items))]
                if i["id"] not in recent:
                    break
            recent.append(i["id"])
            del recent[:max(0, len(recent) - keep)]
            return i
        if o == "cyclic_shuffle":
            cycle, pos = st.get("cycle", 0), st.get("pos", 0)
            if pos >= len(self.items):
                cycle, pos = cycle + 1, 0
            st["cycle"], st["pos"] = cycle, pos + 1
            return self._cycle(cycle)[pos]
        g = self.groups[self._gpos[st["group"]]] if st.get("group") in self._gpos else None
        if g is None or st.get("left", 0) <= 0:
            g = self._next_group()
            st["group"] = g["id"]
            st["left"] = len(g["items"]) if o == "playlist" else self.block
        st["left"] -= 1
        return self._next_in(g)

    def _mix(self) -> dict:
        """Mix: the sources interleaved by their shares of the airtime (the
        one furthest behind goes next), each source's titles shuffled a
        round at a time, or in its own order, carrying on where it was."""
        st, pools = self.st, self._mix_pools
        ks = sorted(pools)
        if self.weighting == "equal":
            share = {k: 1.0 for k in ks}
        elif self.weighting == "manual":
            w = {g.get("k", 0): g.get("w", 1.0) for g in self.groups}
            share = {k: w.get(k, 1.0) for k in ks}
            if not any(share.values()):
                share = {k: 1.0 for k in ks}
        else:
            count = self.balance == "count"
            rt = {k: len(pools[k]) if count else sum(i["duration"] for i in pools[k]) for k in ks}
            total = sum(rt.values()) or 1.0
            share = {k: max(rt[k] / total, FLOOR) for k in ks}
        played = st.setdefault("played", {})
        k = min((k for k in ks if share[k] > 0), key=lambda k: (played.get(str(k), 0.0) / share[k], k))
        mc = st.setdefault("mc", {})
        cyc, pos = mc.get(str(k), [0, 0])
        lst = pools[k]
        if pos >= len(lst):
            cyc, pos = cyc + 1, 0
        mc[str(k)] = [cyc, pos + 1]
        shuffle = self.shuffles[k] if k < len(self.shuffles) else True
        i = (self._shuffled(f"m{k}", cyc, lst) if shuffle else lst)[pos]
        played[str(k)] = played.get(str(k), 0.0) + (1.0 if self.balance == "count" and self.weighting == "auto"
                                                     else i["duration"])
        return i

    def _next_group(self) -> dict:
        o, st, n = self.order, self.st, len(self.groups)
        if o in ("block_shuffle", "marathon_shuffle"):
            # at random, the bigger shows more often, never the one just on
            st["n"] = st.get("n", 0) + 1
            rnd = self._rng("b", st["n"])
            for _ in range(10):
                g = rnd.choices(self.groups, weights=self._weights)[0]
                if n == 1 or g["id"] != st.get("group"):
                    break
            return g
        if o == "round_robin_shuffle":
            rnd, pos = st.get("round", 0), st.get("rpos", 0)
            if pos >= n:
                rnd, pos = rnd + 1, 0
            st["round"], st["rpos"] = rnd, pos + 1
            return self._shuffled("g", rnd, self.groups)[pos]
        # in turn: the one after the last (by name, so a show added to the library doesn't shift the turn)
        at = self._gpos.get(st.get("group"))
        return self.groups[0 if at is None else (at + 1) % n]

    def _next_in(self, g: dict) -> dict:
        """The group's title after the last it aired, round to the first."""
        ptr = self.state.setdefault("ptr", {})
        pos = self._ipos.get(g["id"])
        if pos is None:
            pos = self._ipos[g["id"]] = {i["id"]: n for n, i in enumerate(g["items"])}
        at = pos.get(ptr.get(g["id"]))
        if at is None and self.start == "random":
            i = g["items"][self._rng("start", g["id"]).randrange(len(g["items"]))]
        else:
            i = g["items"][0 if at is None else (at + 1) % len(g["items"])]
        ptr[g["id"]] = i["id"]
        return i


# ── The timeline ─────────────────────────────────────────────────────────

def day_of(t: float) -> tuple:
    """(the broadcast day's name, its start as a timestamp) for a moment."""
    local = datetime.fromtimestamp(t)
    start = local.replace(hour=DAY_STARTS, minute=0, second=0, microsecond=0)
    if local < start:
        start -= timedelta(days=1)
    return start.strftime("%Y-%m-%d"), start.timestamp()


def _next_day(start: float) -> float:
    return (datetime.fromtimestamp(start) + timedelta(days=1)).timestamp()      # (a 23 or 25 hour day at the clocks' change)


def _utc(t: float) -> datetime:
    return datetime.fromtimestamp(t, timezone.utc)


def _date(s: str) -> str:
    """'2008-11-02' -> 'Nov 2, 2008'."""
    try:
        d = datetime.strptime((s or "")[:10], "%Y-%m-%d")
    except ValueError:
        return ""
    return f"{d:%b} {d.day}, {d.year}"


def describe(i: dict) -> dict:
    """A title as the Player and the guide take it: what NostalgiaTV's info
    line has (episode, air date, rating, quality, audio, length, score)."""
    e = dict(i)
    e["kind"] = "show"
    e["minutes"] = max(1, round(i["duration"] / 60))
    e["quality"], e["audio"] = i.get("q", ""), i.get("au", "")
    if i["type"] == "video":            # (a video channel's: the guide and the card read its title)
        e["yt"] = True
        e["icon"] = i["thumb"]
        return e
    new = i.get("added", 0) >= time.time() - NEW_DAYS * 86400
    e["flag"] = "New" if new else ""
    if i["type"] == "track":            # music: the radio card says what's playing
        e["category"] = "Music"
        e["desc"] = f'"{i["name"]}"' + (f" from {i['album']}" if i.get("album") else "")
        e["radio"] = {"artist": i["title"], "song": i["name"], "album": i.get("album", ""), "art": ""}
        return e
    if i["type"] == "episode":
        code = f"S{i['season']}E{i['episode']}" if i["season"] else ""
        name = "" if re.fullmatch(r"(season \d+,? )?episode \d+", i["name"] or "", re.I) else i["name"]  # Plex's stand-in
        e["episode_text"] = " - ".join(x for x in (code, name) if x) or i["name"]  # "S13E4 - Lost in MySpace"
        e["desc"] = i["summary"]
        e["air"] = _date(i.get("air", ""))
        e["category"] = (i["genres"] or ["Series"])[0]
    else:
        if i["type"] == "movie" and i["year"]:
            e["title"] = f"{i['title']} ({i['year']})"                          # "Barbarian (2022)"
        e["desc"] = i["summary"]
        e["air"] = _date(i.get("air", ""))
        e["category"] = "Movie" if i["type"] == "movie" else (i["genres"] or ["Video"])[0]
    return e


class Timeline:
    """A library channel's written-down running order, a day at a time. To
    the Player and the guide it answers as a video channel's Schedule does."""

    sources = ()                # (nothing for the video channels' source report)

    def __init__(self, c: dict, index=None, poster=None, store: bool = True, made=None, cid=None):
        """A library channel's from the index; a video channel's from `made`:
        (its groups, its lists' stamp), with its own `cid`."""
        self.c = dict(c) if made else dict(c, guide="video")
        self.cid = cid or PREFIX + c["id"]
        self.poster = poster
        self.store = store
        self.dropped: dict = {}     # a title that couldn't play -> when
        self.guide_memo = None
        self.lock = threading.RLock()
        self.groups, self.stamp = made if made else (groups(c, index), index.stamp())
        self._by_id = {i["id"]: i for g in self.groups for i in g["items"]}
        self.entries = list(self._by_id.values())
        self.brk = brk = breaks_of(c, index)
        self.ads = clips(brk.get("ads"), index) if index is not None and brk else []
        self.idents = clips(brk.get("idents"), index) if index is not None and brk else []
        self.chunks = long_clips(brk.get("ads"), index) if index is not None and brk else []
        for i in self.idents + self.chunks:
            self._by_id.setdefault(i["id"], i)
        pr = c.get("premiere_preroll")
        self._prerolls = clips([{"section": pr, "kind": "all"}], index) if pr and index is not None else []
        self.bumps = clips(brk.get("bumps"), index) if index is not None and brk else []
        for i in self.ads + self.bumps:
            self._by_id.setdefault(i["id"], i)
        by_len = lambda pool: (sorted(pool, key=lambda i: i["duration"]), sorted(i["duration"] for i in pool))  # noqa: E731
        self._ads, self._bumps, self._idents = by_len(self.ads), by_len(self.bumps), by_len(self.idents)
        self.sig = signature(c)
        self._then = _parts(self.groups)            # part one -> (part two, its group)
        self._by_len = sorted(self.entries, key=lambda i: i["duration"])
        self._lens = [i["duration"] for i in self._by_len]
        self._hol = {i["id"]: h for i in self.entries for h in (holiday(i),) if h}
        if len(self._hol) * 2 > len(self.entries) or not c.get("seasonal", True):
            self._hol = {}                          # (a holiday channel: all year)
        self._gids = frozenset(g["id"] for g in self.groups)
        self._movies = frozenset(g["id"] for g in self.groups if g["items"][0]["type"] == "movie")
        self._mature = frozenset(g["id"] for g in self.groups if g["items"][0]["rating"] in MATURE)
        self._slotted = any(s.get("airs") or s.get("season") for s in c.get("sources") or [] if not s.get("exclude"))
        self.days: list = []        # [{"day", "start", "state": as it began, "slots": [[start, id, seconds]]}]
        self.state: dict = {}       # as the last day ended
        # Its line (first drawn up where, when) and how worked on: what other Cathodes compare (sync.py).
        self.lineage, self.born, self.rev, self.by = uuid.uuid4().hex[:12], time.time(), 0, _sync.ME
        self._starts: list = []
        self._slots: list = []
        self._made: dict = {}
        self._dirty = False
        if store:
            self._load()

    def median(self) -> float:
        d = sorted(i["duration"] for i in self.entries)
        return d[len(d) // 2] if d else 0.0

    def unknown(self) -> bool:
        """Whether the days name titles this Cathode hasn't read (another's
        days, taken before this one's lists or library caught up)."""
        return any(s[1] not in SLATES and s[1] not in self._by_id for s in self._slots)

    # ── Breaks ────────────────────────────────────────────────────────────

    def _place(self, i: dict, t: float, slots: list, state: dict, extra: Optional[dict] = None) -> float:
        """A programme into the day: in parts with breaks between them when
        it's long and the channel breaks during programmes, then the break
        after it (to the next quarter or half hour, or of its length)."""
        brk = self.brk
        on = bool(self.ads or self.bumps or self.chunks)
        cuts, mid, dur = [], brk.get("mid", "off"), i["duration"]
        if on and dur >= MID_FROM and mid != "off":
            if mid in ("chapters", "silences"):
                from . import marks
                cuts = marks.cuts(i, mid)
                if cuts is None:
                    mid = "halfway"             # not read yet: halfway till it is
            if mid == "halfway":
                cuts = [dur / 2]
            elif mid.startswith("every"):
                step = int(mid[5:]) * 60.0
                cuts = [k * step for k in range(1, int(dur // step) + 1) if dur - k * step >= step / 2]
        edges = [0.0] + cuts + [dur]
        for k in range(len(edges) - 1):
            x = dict(extra or {})
            if k:
                x.update({"in": edges[k], "part": k})
            slots.append([t, i["id"], edges[k + 1] - edges[k]] + ([x] if x else []))
            t += edges[k + 1] - edges[k]
            if on and k < len(edges) - 2:
                t = self._break(t, slots, state, t + float(brk.get("length", 120)))
        if on:
            pad = int(brk.get("pad", 30) or 0)
            card = NEXT_SECONDS if brk.get("next_card") else 0
            if brk.get("count"):
                until = t + 3600.0                  # (the break is its commercials, however long)
            elif not pad:
                until = t + float(brk.get("length", 120))
            else:
                until = self._boundary(t, pad)
                if i["duration"] < SHORT and until - t > NEAR:
                    return t            # short titles (songs, clips) run on: a break only near the clock's mark
            t = self._break(t, slots, state, until - card, top=True)
            if card:
                end = t + card if brk.get("count") else max(until, t + 1)
                slots.append([t, NEXT, end - t, {"brk": "next"}])
                t = end
        return t

    @staticmethod
    def _boundary(t: float, pad: int) -> float:
        """The next quarter, half or whole hour after a moment (local)."""
        lt = datetime.fromtimestamp(t)
        top = lt.replace(minute=0, second=0, microsecond=0)
        mins = (t - top.timestamp()) / 60
        nxt = (int(mins // pad) + 1) * pad
        return (top + timedelta(minutes=nxt)).timestamp()

    def _break(self, t: float, slots: list, state: dict, until: float, top: bool = False) -> float:
        """A break from t to `until`: the channel's ident (between
        programmes), a bumper in, commercials (or as many as it's set to
        run), a bumper out; what no clip fits, the "we'll be right back"
        slate. Too short a gap (under ten seconds) is no break."""
        if until - t < 10:
            return t
        count = int(self.brk.get("count") or 0)
        state["bn"] = state.get("bn", 0) + 1
        rnd = random.Random(f"{self.cid}:brk:{state['bn']}")
        recent = state.setdefault("ads_recent", [])
        seen = set(recent)

        def pick(pool, room, avoid=()):
            """A clip that fits the room: a few random tries among those short
            enough (the pool kept by length), one not aired lately if it can."""
            items, lengths = pool
            k = _bisect(lengths, room)
            if not k:
                return None
            spare = None
            for _ in range(12):
                i = items[rnd.randrange(k)]
                if i["id"] in self.dropped or i["id"] in avoid:
                    continue
                if i["id"] not in seen:
                    return i
                spare = spare or i
            return spare or next((i for i in items[:k] if i["id"] not in self.dropped and i["id"] not in avoid), None)
        def in_order(room):
            """The commercials in their running order, carrying on where the
            last break left off (one that doesn't fit waits its turn)."""
            items = self.ads
            pos = state.get("adpos", 0)
            for k in range(len(items)):
                a = items[(pos + k) % len(items)]
                if a["duration"] <= room and a["id"] not in self.dropped:
                    state["adpos"] = (pos + k + 1) % len(items)
                    return a
            return None

        def piece(room):
            """A commercial-length piece of a long video: 30 to 90 seconds
            from somewhere in it."""
            if room < 20 or not self.chunks:
                return None
            v = self.chunks[rnd.randrange(len(self.chunks))]
            if v["id"] in self.dropped:
                return None
            n = min(room, rnd.uniform(30, 90))
            return v, rnd.uniform(0, max(0.0, v["duration"] - n)), n
        if top and self.idents:
            idt = pick(self._idents, (until - t) / 3 if not count else CLIP_MAX)
            if idt:
                slots.append([t, idt["id"], idt["duration"], {"brk": "bump"}])
                t += idt["duration"]
        cap = CLIP_MAX if count else None
        b_in = pick(self._bumps, (until - t) / 3 if cap is None else 60)
        b_out = pick(self._bumps, (until - t) / 3 if cap is None else 60, {b_in["id"]} if b_in else ())
        end_ads = until - (b_out["duration"] if b_out else 0)
        if b_in:
            slots.append([t, b_in["id"], b_in["duration"], {"brk": "bump"}])
            t += b_in["duration"]
        n = 0
        ordered = self.brk.get("ad_order") == "in_order"
        while (self.ads or self.chunks) and (not count or n < count):
            room = cap if cap is not None else end_ads - t
            a = None
            if self.ads and not (self.chunks and rnd.random() < len(self.chunks) / (len(self.chunks) + len(self.ads))):
                a = in_order(room) if ordered else pick(self._ads, room)
            if a is None:
                got = piece(room)
                if got is None:
                    if self.ads and self.chunks:
                        a = in_order(room) if ordered else pick(self._ads, room)
                    if a is None:
                        break
                else:
                    v, at, length = got
                    slots.append([t, v["id"], length, {"brk": "ad", "in": round(at, 2)}])
                    t += length
                    n += 1
                    continue
            slots.append([t, a["id"], a["duration"], {"brk": "ad"}])
            t += a["duration"]
            n += 1
            recent.append(a["id"])
            seen.add(a["id"])
            del recent[:max(0, len(recent) - 60)]
        if count:
            end_ads = t
        if end_ads - t > 0.01:
            slots.append([t, BRB, end_ads - t, {"brk": "brb"}])
            t = end_ads
        if b_out:
            slots.append([t, b_out["id"], b_out["duration"], {"brk": "bump"}])
            t += b_out["duration"]
        return t

    def _premiere(self, t: float, state: dict, elig) -> list:
        """At the first programme from each premiere hour (8 PM unless set)
        on the premiere nights (every night unless set): the newest arrivals
        the channel hasn't premiered yet, one or a few back to back."""
        if self.c.get("premieres", "off") == "off":
            return []
        lt = datetime.fromtimestamp(t)
        day = lt.strftime("%Y-%m-%d")
        nights = self.c.get("premiere_days")
        if nights and lt.weekday() not in nights:
            return []
        hours = [h for h in self.c.get("premiere_times") or [PREMIERE_HOUR] if lt.hour >= h]
        if not hours:
            return []
        key = f"{day}@{max(hours)}"
        if state.get("prem_day") and state["prem_day"] in (key, day if max(hours) == PREMIERE_HOUR else key):
            return []                           # (a plain day: as 5.2 wrote it down)
        state["prem_day"] = key
        done = state.setdefault("premiered", [])
        fresh = time.time() - NEW_DAYS * 86400
        new = sorted((i for g in self.groups if elig is None or g["id"] in elig for i in g["items"]
                      if i.get("added", 0) >= fresh and i["id"] not in done and i["id"] not in self.dropped),
                     key=lambda i: (-i["added"], i["id"]))[:max(1, int(self.c.get("premiere_count") or 1))]
        for i in new:
            done.append(i["id"])
        del done[:max(0, len(done) - 500)]
        return new

    def _preroll(self, t: float, slots: list, state: dict) -> float:
        """A premiere's pre-roll: a clip from the library picked for it."""
        pool = getattr(self, "_prerolls", None)
        if not pool:
            return t
        state["pr"] = state.get("pr", 0) + 1
        i = pool[random.Random(f"{self.cid}:pr:{state['pr']}").randrange(len(pool))]
        slots.append([t, i["id"], i["duration"], {"brk": "bump"}])
        return t + i["duration"]

    def _pins(self, start: float, end: float) -> list:
        """[(when, pin, key)] the pinned titles due in a broadcast day."""
        out = []
        base = datetime.fromtimestamp(start)
        for n, p in enumerate(self.c.get("pins") or []):
            try:
                hh, mm = (int(x) for x in str(p.get("at", "")).split(":"))
            except ValueError:
                continue
            at = base.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if at.timestamp() < start:
                at += timedelta(days=1)
            if p.get("days") and at.weekday() not in p["days"]:
                continue
            if start <= at.timestamp() < end:
                out.append((at.timestamp(), p, f"{base:%Y-%m-%d}#{n}"))
        return sorted(out, key=lambda x: x[0])

    def _pinned(self, p: dict, rotor) -> Optional[dict]:
        """A pin's title: a show's next episode, or the movie."""
        src = p.get("src") or {}
        if src.get("kind") == "show":
            g = next((g for g in self.groups if g["id"] == "s" + str(src.get("value"))), None)
            return rotor._next_in(g) if g else None
        keys = src.get("value") if isinstance(src.get("value"), list) else [src.get("value")]
        return next((i for i in self.entries if i.get("plex") in keys and i["id"] not in self.dropped), None)

    def _fill(self, t: float, until: float, slots: list, state: dict) -> float:
        """The time before a pinned title filled: titles that fit (the
        longest that does, each time), then a break to the minute."""
        rnd = random.Random(f"{self.cid}:fill:{int(t)}")
        while until - t > 90:
            k = _bisect(self._lens, until - t - 30)
            if not k:
                break
            i = self._by_len[max(0, k - 1 - rnd.randrange(min(k, 8)))]
            if i["id"] in self.dropped:
                break
            slots.append([t, i["id"], i["duration"]])
            t += i["duration"]
        if until - t > 1:
            if self.ads or self.bumps:
                t = self._break(t, slots, state, until)
            if until - t > 0.01:
                slots.append([t, BRB, until - t, {"brk": "brb"}])
        return until

    def _seasonal(self, t: float, state: dict, rotor, elig) -> Optional[dict]:
        """The seasonal cycler: in a holiday's season, about one programme
        in four is one of its titles (the next not yet aired)."""
        if not self._hol:
            return None
        lt = datetime.fromtimestamp(t)
        live = [i for i in self.entries if self._hol.get(i["id"]) and in_season(self._hol[i["id"]], lt)
                and i["id"] not in self.dropped]
        if not live:
            return None
        state["hn"] = state.get("hn", 0) + 1
        if random.Random(f"{self.cid}:hol:{state['hn']}").random() > 0.25:
            return None
        aired = state.setdefault("hol_aired", [])
        i = next((i for i in live if i["id"] not in aired), None) or live[0]
        if i["id"] in aired:
            aired.clear()
        aired.append(i["id"])
        return i

    def _limit(self, elig, t: float, state: dict):
        """A time slot's groups less the movies once the day has had its
        most, and the grown-ups' titles before their hour."""
        cut = set()
        most = int(self.c.get("max_movies") or 0)
        if most and state.get("movies", 0) >= most:
            cut |= self._movies
        late = self.c.get("mature_from")
        if late is not None and on_air({"hours": [int(late), 6]}, t) is False:
            cut |= self._mature
        if not cut:
            return elig
        return frozenset((self._gids if elig is None else elig) - cut)

    def _marathon(self, t: float, name: str, state: dict, rotor, elig) -> Optional[dict]:
        """Random marathons: on about one day in three, from an hour picked at
        random, four to eight episodes of one show back to back."""
        m = state.get("mara")
        if m and m.get("left", 0) > 0:
            g = next((g for g in self.groups if g["id"] == m["g"]), None)
            if g is not None and (elig is None or g["id"] in elig):
                m["left"] -= 1
                return rotor._next_in(g)
            state.pop("mara", None)
        if not self.c.get("marathons") or state.get("mara_day") == name:
            return None
        rnd = random.Random(f"{self.cid}:mara:{name}")
        if rnd.random() > 0.35 or datetime.fromtimestamp(t).hour < rnd.randint(10, 19):
            return None
        state["mara_day"] = name
        shows = [g for g in self.groups if len(g["items"]) >= 6 and (elig is None or g["id"] in elig)
                 and g["items"][0]["type"] == "episode"]
        if not shows:
            return None
        g = rnd.choice(shows)
        state["mara"] = {"g": g["id"], "left": rnd.randint(4, 8) - 1}
        return rotor._next_in(g)

    def _eligible(self, t: float):
        """The groups that may air at a moment: those of the sources whose
        time slot it is, if any's is; else those of the sources without a
        slot (a seasonal source joins them in its months). None: all."""
        if not self._slotted:
            return None
        lt = datetime.fromtimestamp(t)
        srcs = self.c.get("sources") or []
        act = [k for k, s in enumerate(srcs) if not s.get("exclude") and active(s, lt)]
        slot = {k for k in act if srcs[k].get("airs")}
        use = slot or {k for k in act if not srcs[k].get("airs")}
        return frozenset(g["id"] for g in self.groups if g["src"] & use)

    # ── On disk ───────────────────────────────────────────────────────────

    def _path(self) -> str:
        return os.path.join(library._dir(), f"sched-{self.c['id']}.json")

    def _load(self):
        try:
            with open(self._path(), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        if d.get("v") != VERSION:
            return
        days, state = d.get("days") or [], d.get("state") or {}
        self.dropped = {k: v for k, v in (d.get("dropped") or {}).items() if time.time() - v < OFF_AIR}
        self.lineage = d.get("lineage") or self.lineage
        self.born = float(d.get("born") or (days[0]["start"] if days else self.born))
        self.rev, self.by = int(d.get("rev") or 0), d.get("by") or self.by
        today = day_of(time.time())[0]
        cut = None                                  # the first day that has to be drawn up again
        for n, day in enumerate(days):
            if any(s[1] not in SLATES and s[1] not in self._by_id for s in day["slots"]):
                cut = n                             # a title left the library
                break
            if d.get("sig") != self.sig and day["day"] >= today:
                cut = n                             # the channel was edited: today onward
                break
            if d.get("stamp") != self.stamp and day["day"] > today:
                cut = n                             # the library changed: tomorrow onward
                break
        if cut is not None:
            state = days[cut]["state"]
            days = days[:cut]
        self.days, self.state = days, state
        self._dirty = cut is not None or d.get("sig") != self.sig or d.get("stamp") != self.stamp
        self._index()

    def _save(self):
        if not self.store or not self._dirty:
            return
        self._dirty = False
        tmp = self._path() + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._doc(), f, separators=(",", ":"))
            os.replace(tmp, self._path())
        except OSError as e:
            print(f"[library] schedule not written: {e!r}")

    # ── Drawing up days ───────────────────────────────────────────────────

    def _index(self):
        self._slots = [s for d in self.days for s in d["slots"]]
        self._starts = [s[0] for s in self._slots]
        self.guide_memo = None

    def _generate(self, name: str, start: float):
        """One more day: from where the last ended (a programme running
        over 4 AM, or short of it where a title was skipped) to the first
        programme ending after the next 4 AM."""
        before = json.loads(json.dumps(self.state))
        state = self.state
        end = _next_day(start)
        t = state.get("t") or start
        if not start - 86400 <= t < end:
            t = start                   # a gap in the days (the box was off): from the day's top
        seed = self.c.get("seed", 0)                # (a refresh's: the days drawn differently)
        if state.get("reset", 0) != self.c.get("reset", 0):
            for k in ("ptr", "cycle", "pos", "slots", "mc", "played", "group", "left"):
                state.pop(k, None)              # every show from its start again
            state["reset"] = self.c.get("reset", 0)
        if state.get("mday") != name:
            state["mday"], state["movies"] = name, 0
        lt0 = datetime.fromtimestamp(start + 43200)
        skip = set(self.dropped) | {k for k, h in self._hol.items() if not in_season(h, lt0)}
        rotor = Rotor(f"{self.cid}:{seed}" if seed else self.cid, self.c.get("order", "cyclic_shuffle"),
                      self.c.get("block", 0), self.groups, state, skip, self.c.get("weighting", "auto"),
                      self.c.get("sources") or [], self.c.get("episode_start", "first"),
                      self.c.get("balance", "duration"))
        pins = [p for p in self._pins(start, end) if p[2] not in (state.get("pins_done") or [])]
        slots = []

        def off(a, b):                  # off the air from a to b (one stretch with any just before)
            if slots and slots[-1][1] == OFF and abs(slots[-1][0] + slots[-1][2] - a) < 0.01:
                slots[-1][2] += b - a
            else:
                slots.append([a, OFF, b - a])
        while t < end:
            if not on_air(self.c, t):
                b = next_on(self.c, t)
                off(t, b)
                t = b
                continue
            while pins and pins[0][0] < t - 1800:
                pins.pop(0)                     # (one long passed: the box was off)
            if pins and t >= pins[0][0] - 5:
                at, p, key = pins.pop(0)
                done = state.setdefault("pins_done", [])
                done.append(key)
                del done[:max(0, len(done) - 100)]
                i = self._pinned(p, rotor)
                if i is not None:
                    t = self._place(i, t, slots, state)
                    t = self._then_parts(i, t, slots, state)
                continue
            elig = self._limit(self._eligible(t), t, state)
            prem = self._premiere(t, state, elig)
            if prem:
                t = self._preroll(t, slots, state)
                for i in prem:
                    t = self._place(i, t, slots, state, {"premiere": 1})
                    t = self._then_parts(i, t, slots, state)
                continue
            hol = self._seasonal(t, state, rotor, elig)
            if hol is not None:
                t = self._place(hol, t, slots, state)
                continue
            mara = self._marathon(t, name, state, rotor, elig)
            if mara is not None:
                t = self._place(mara, t, slots, state, {"flag": "Marathon"})
                continue
            i = rotor.next(elig) if elig is None or elig else None
            if i is not None and pins and t + i["duration"] > pins[0][0]:
                t = self._fill(t, pins[0][0], slots, state)      # (the pinned title starts on the minute)
                continue
            if i is None:
                if elig is None:
                    break               # nothing can play at all
                b = _next_hour(t)       # nothing in this slot can: off the air till the hour
                off(t, b)
                t = b
                continue
            t = self._place(i, t, slots, state)
            t = self._then_parts(i, t, slots, state)
        state["t"] = t
        self.days.append({"day": name, "start": start, "state": before, "slots": slots})
        self._dirty = True
        self.rev, self.by = self.rev + 1, _sync.ME

    def _then_parts(self, i: dict, t: float, slots: list, state: dict) -> float:
        """Part two (and three...) straight after part one."""
        if i["type"] == "movie":
            state["movies"] = state.get("movies", 0) + 1
        while i["id"] in self._then and on_air(self.c, t):
            i, gid = self._then[i["id"]]
            if i["id"] in self.dropped:
                break
            state.setdefault("ptr", {})[gid] = i["id"]
            t = self._place(i, t, slots, state)
        return t

    def _cover(self, t: float):
        """Days drawn up until they reach past `t`; old ones let go."""
        if not self.entries or (self.days and self.state.get("t", 0) > t):
            return
        if self.days and day_of(t)[1] - self.days[-1]["start"] > 3 * 86400:
            self.days = []              # the box was off for days: no drawing up every day between
        for _ in range(40):
            if not self.days:           # from today (or the day asked for, if that's before it)
                self._generate(*min(day_of(time.time()), day_of(t)))
            else:
                self._generate(*day_of(_next_day(self.days[-1]["start"]) + 3600))
            if self.state.get("t", 0) > t or not self.days[-1]["slots"]:
                break                   # (nothing left that can play: no days of nothing)
        keep = day_of(time.time() - KEEP_DAYS * 86400)[0]
        self.days = [d for d in self.days if d["day"] >= keep] or self.days[-1:]
        self._index()
        self._save()

    # ── What the Player and the guide ask ─────────────────────────────────

    def at(self, now: datetime, _depth: int = 0) -> Optional[dict]:
        """{"entry", "offset", "start", "stop"} on the air at `now` (UTC).
        In a redirect's hours, the channel it carries then."""
        t = now.timestamp()
        r = self.c.get("redirect") or {}
        if r.get("to") and r["to"] != self.cid and _depth < 3 and r.get("from", 0) != r.get("until", 0) and on_air({"hours": [r.get("from", 0), r.get("until", 0)]}, t):
            other = SCHEDULES.get(r["to"])
            got = other.at(now, _depth + 1) if other is not None else None
            if got:
                return dict(got, redirect=r["to"])
        with self.lock:
            self._cover(t)
            n = _bisect(self._starts, t) - 1
            if n < 0:
                return None
            slot = self._slots[n]
            start, item_id, dur = slot[0], slot[1], slot[2]
            extra = slot[3] if len(slot) > 3 else None
            if t >= start + dur:
                return None
            if item_id in SLATES:
                kind, title = ("signoff", "Off the air") if item_id == OFF else ("brb", "We'll be right back")
                e = {"id": item_id, "kind": kind, "title": title, "duration": dur}
                if item_id == NEXT:
                    e.update(title="Coming up next", style="next", next=self._next_title(n))
                return {"entry": e, "offset": t - start, "start": _utc(start), "stop": _utc(start + dur)}
            e = self._made.get(item_id)
            if e is None:
                i = self._by_id.get(item_id)
                if i is None:
                    return None
                e = self._made[item_id] = describe(i)
                if self.poster and i["thumb"] and i["type"] != "video":
                    e["icon"] = self.poster(i["thumb"])
                if self.poster and i.get("logo"):
                    e["logo"] = self.poster(i["logo"], 480, 180)
                if self.poster and i.get("art"):
                    e["art"] = self.poster(i["art"], 640, 360)
                if e.get("radio"):
                    e["radio"] = dict(e["radio"], art=e.get("icon", ""))
            if extra:
                e = dict(e, **extra)
                if extra.get("brk"):
                    e["kind"] = extra["brk"]            # ("ad", "bump": a break's piece, not a programme)
                if extra.get("premiere"):
                    e["flag"] = "Premiere"
            return {"entry": e, "offset": t - start, "start": _utc(start), "stop": _utc(start + dur)}

    def _next_title(self, n: int) -> dict:
        """The programme after slot n: its title and episode."""
        for s in self._slots[n + 1:n + 40]:
            if s[1] in SLATES or (len(s) > 3 and s[3].get("brk")):
                continue
            i = self._by_id.get(s[1])
            if i:
                d = describe(i)
                return {"title": d["title"], "episode": d.get("episode_text", ""), "at": s[0]}
            break
        return {}

    def drop(self, item_id: str, now: Optional[datetime] = None):
        """A title that can't play leaves the air: what's left of it now, and
        every airing of it drawn up ahead, is taken out and what follows
        moves up to fill the time. It stays out of the days drawn up from
        here on, for a week."""
        if item_id in SLATES:
            return
        t = (now or datetime.now(timezone.utc)).timestamp()
        with self.lock:
            self.dropped[item_id] = time.time()
            shift = 0.0
            for d in self.days:
                if shift and d["state"].get("t", 0) > t:
                    d["state"]["t"] -= shift            # (the day began that much sooner)
                keep = []
                for n, s in enumerate(d["slots"]):
                    if s[1] == item_id and len(s) > 3 and s[3].get("brk") and s[0] + s[2] > t:
                        d["slots"][n] = [s[0] - shift, BRB, s[2], {"brk": "brb"}]   # a dud commercial: the slate
                        keep.append(d["slots"][n])
                        continue
                    if shift and s[0] > t and len(s) > 3 and s[3].get("brk"):
                        keep.append([s[0] - shift, BRB, shift, {"brk": "brb"}])  # the next break takes the time up
                        shift = 0.0
                        keep.append(s)
                        continue
                    if s[1] == OFF and shift and s[0] > t:  # a sign-off takes the time up: sign-on stays put
                        s[0] -= shift
                        s[2] += shift
                        shift = 0.0
                        keep.append(s)
                        continue
                    if s[1] == item_id and s[0] + s[2] > t:
                        if s[0] < t:                    # on the air now: it ends here (no hole behind it)
                            shift += s[0] + s[2] - t
                            s[2] = t - s[0]
                            keep.append(s)
                        else:
                            shift += s[2]
                        continue
                    if shift:
                        s[0] -= shift
                    keep.append(s)
                d["slots"] = keep
            if shift:
                self.state["t"] = self.state.get("t", 0) - shift
            self._dirty = True
            self.rev, self.by = self.rev + 1, _sync.ME
            self._index()
            self._save()

    def restore(self, item_id: str):
        """A skipped title back in the days drawn up from here on."""
        with self.lock:
            if self.dropped.pop(item_id, None) is not None:
                self._dirty = True
                self.rev, self.by = self.rev + 1, _sync.ME
                self._save()

    def coming(self, n: int = 24, now: Optional[datetime] = None) -> list:
        """[(start, entry)] for what's on now and the next n-1 after it."""
        out, cur = [], self.at(now or datetime.now(timezone.utc))
        while cur and len(out) < n:
            out.append((cur["start"], cur["entry"]))
            cur = self.at(cur["stop"] + timedelta(seconds=0.5))
        return out

    def title_of(self, item_id: str) -> str:
        i = self._by_id.get(item_id)
        if not i:
            return item_id
        return f"{i['title']}: {i['name']}" if i.get("name") else i["title"]

    # ── Other Cathodes (sync.py) ──────────────────────────────────────────

    def version(self) -> dict:
        return {"sig": self.sig, "lineage": self.lineage, "born": self.born, "rev": self.rev, "by": self.by}

    def _doc(self) -> dict:
        return {"v": VERSION, **self.version(), "stamp": self.stamp, "days": self.days, "state": self.state,
                "dropped": self.dropped}

    def doc(self) -> dict:
        """The written-down days, as another Cathode asks for them."""
        with self.lock:
            return json.loads(json.dumps(self._doc()))

    def adopt(self, doc) -> bool:
        """Another Cathode's days taken in place of these, when they win
        (beats()). A title skipped here and not there is skipped again, so
        it's out on both."""
        if not is_doc(doc):
            return False
        with self.lock:
            if not beats(doc, self.version()):
                return False
            mine = dict(self.dropped)
            self.days, self.state = doc["days"], doc["state"]
            self.dropped = {k: float(v) for k, v in doc["dropped"].items() if time.time() - float(v) < OFF_AIR}
            self.lineage, self.born, self.rev, self.by = doc["lineage"], float(doc["born"]), int(doc["rev"]), doc["by"]
            self.guide_memo = None
            self._dirty = True
            self._index()
            self._save()
            for k in mine:
                if k not in self.dropped:
                    self.drop(k)
        return True


_PART = re.compile(r"^(.*?)[\s,:;-]*(?:\(\s*(?:part\s*)?(\d+|one|two|three|four|i{1,3}|iv)\s*\)|\bpart\s+(\d+|one|two|three|four|i{1,3}|iv))"
                   r"\s*$", re.I)
_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "i": 1, "ii": 2, "iii": 3, "iv": 4}


def _part(name: str):
    """'The Best of Both Worlds, Part II' -> ('the best of both worlds', 2)."""
    m = _PART.match(name or "")
    if not m:
        return None
    n = (m.group(2) or m.group(3)).lower()
    return m.group(1).strip().lower(), int(n) if n.isdigit() else _NUMS[n]


def _parts(groups_: list) -> dict:
    """Each multi-part episode's part one (two...) -> (the next part, its
    group): neighbours in the show's order with one name and parts n, n+1."""
    out = {}
    for g in groups_:
        its = g["items"]
        for a, b in zip(its, its[1:]):
            if a["type"] != "episode":
                break
            pa, pb = _part(a["name"]), _part(b["name"])
            if pa and pb and pa[0] == pb[0] and pb[1] == pa[1] + 1:
                out[a["id"]] = (b, g["id"])
    return out


def beats(theirs: dict, mine: dict) -> bool:
    """Whether another Cathode's schedule for a channel wins over this
    one's: the same channel as edited, then the older line, then the more
    worked on (ties to the higher id)."""
    try:
        if theirs.get("sig") != mine.get("sig"):
            return False
        if theirs.get("lineage") != mine.get("lineage"):
            return (float(theirs["born"]), str(theirs["lineage"])) < (float(mine["born"]), str(mine["lineage"]))
        return (int(theirs["rev"]), str(theirs["by"])) > (int(mine["rev"]), str(mine["by"]))
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def is_doc(d) -> bool:
    """A schedule as another Cathode sends it, its shape checked."""
    try:
        if not (isinstance(d, dict) and d.get("v") == VERSION and isinstance(d["days"], list)
                and isinstance(d["state"], dict) and isinstance(d["dropped"], dict)
                and isinstance(d["lineage"], str) and isinstance(d["by"], str) and isinstance(d["rev"], int)
                and isinstance(d["born"], (int, float)) and isinstance(d["state"].get("t", 0), (int, float))):
            return False
        for day in d["days"]:
            if not (isinstance(day, dict) and isinstance(day["day"], str) and isinstance(day["start"], (int, float))
                    and isinstance(day["state"], dict) and isinstance(day["slots"], list)):
                return False
            for s in day["slots"]:
                if not (isinstance(s, list) and len(s) in (3, 4) and isinstance(s[0], (int, float))
                        and isinstance(s[1], str) and isinstance(s[2], (int, float))
                        and (len(s) == 3 or isinstance(s[3], dict))):
                    return False
        return all(isinstance(v, (int, float)) for v in d["dropped"].values())
    except (KeyError, TypeError, AttributeError):
        return False


def _bisect(a, x):
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] <= x:
            lo = mid + 1
        else:
            hi = mid
    return lo


# ── The starter lineup ───────────────────────────────────────────────────
# Your channels as your Tunarr had them (assets/channels/lineup.json: each
# with its number, the shows and movies it plays by title, the libraries it
# takes whole, its bumpers, its logo and screen bug), with the dayparts
# Cathode adds and a few channels of Cathode's own. Then every show and
# movie no channel has goes where it belongs (place_titles()): at first, and as
# the library grows.

STARTER_MAKE = 5                # 5: your Tunarr lineup, every title placed; 4: real logos; 3: every title placed;
#                                 2: network replicas; 1: genres...
SLOT_SHOWS = 3                  # a daypart with fewer of its shows in the library isn't kept
ADS = ["Classic Commercials"]   # the commercials, unless the table names others


def lineup() -> dict:
    """The starter lineup's table."""
    from .paths import asset
    with open(asset("channels", "lineup.json"), encoding="utf-8") as f:
        return json.load(f)


def _tkey(title: str) -> str:
    """A title as the table and the library both have it: letters and
    digits only, '&' read as 'and', a year at the end left off ('Archer
    (2009)' is 'archer')."""
    import unicodedata
    t = re.sub(r"\s*\((19|20)\d\d\)\s*$", "", title or "")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().casefold().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "", t)


def _movie_key(name: str) -> tuple:
    """'Good Burger (1997)' as (its title's key, 1997)."""
    m = re.fullmatch(r"(.*) \((\d{4})\)", name or "")
    return (_tkey(m.group(1)), int(m.group(2))) if m else (_tkey(name), 0)


def starter(index, table=None) -> list:
    """The starter lineup's channels: each with the shows the table names
    (by title), its movies, the libraries it takes whole, its dayparts, its
    bumpers (and its shows' shorts) and the commercials. A channel nothing
    in the library is for isn't made."""
    table = table or lineup()
    libs = {s.title.lower(): s for s in index.sections.values()}
    shows, movies = {}, {}
    for sec in index.sections.values():
        if sec.hidden or sec.breaks:
            continue
        if sec.kind == "show":
            have = {i["show_key"] for i in sec.items}
            for k, sh in sec.shows.items():
                if k in have:
                    shows.setdefault(_tkey(sh["title"]), []).append((sec.key, k))
        elif sec.kind == "movie":
            for i in sec.items:
                movies.setdefault((_tkey(i["title"]), i["year"]), []).append((sec.key, i["plex"]))
    shorts = {(s.key, i["show_key"]) for s in index.sections.values() if s.kind == "show" for i in s.items
              if i["season"] == 0 and 0 < i["duration"] <= CLIP_MAX and any(j["season"] for j in s.items
                                                                             if j["show_key"] == i["show_key"])}

    def found(titles) -> list:
        return [h for t in dict.fromkeys(_tkey(t) for t in titles or () if t) for h in shows.get(t, ())]

    def lib(name):
        return libs.get((name or "").lower())

    ads = [{"section": s.key, "kind": "all"} for s in map(lib, table.get("ads", ADS)) if s]
    out = []
    for e in table["channels"]:
        slots = []
        for sl in e.get("slots", ()):
            f, ls = found(sl.get("shows")), [s for s in map(lib, sl.get("libs", ())) if s]
            if len(f) >= SLOT_SHOWS or ls:
                slots.append((sl["airs"], f, ls))
        in_slot = {h for _a, f, _l in slots for h in f} | {s.key for _a, _f, ls in slots for s in ls}
        day = [h for h in found(e.get("shows")) if h not in in_slot]
        sources = [{"section": s, "kind": "show", "value": k} for s, k in day]
        picked = {}
        for m in e.get("movies", ()):
            for s, key in movies.get(_movie_key(m), ())[:1]:
                picked.setdefault(s, []).append(key)
        sources += [{"section": s, "kind": "title", "value": v} for s, v in picked.items()]
        sources += [{"section": s.key, "kind": "all"} for s in map(lib, e.get("libs", ())) if s and s.key not in in_slot]
        sources += [dict({k: v for k, v in src.items() if k != "lib"}, section=lib(src["lib"]).key)
                    for src in e.get("sources", ()) if lib(src.get("lib"))]
        for airs, f, ls in slots:         # (a daypart's shows and libraries air in it only)
            sources += [{"section": s, "kind": "show", "value": k, "airs": airs} for s, k in f]
            sources += [{"section": s.key, "kind": "all", "airs": airs} for s in ls]
        if not sources:
            continue
        bumps = [{"section": s.key, "kind": "all"} for s in map(lib, e.get("bumps", ())) if s]
        bumps += [{"section": lib(n).key, "kind": "title", "value": v}
                  for n, v in (e.get("bump_titles") or {}).items() if lib(n)]
        bumps += [{"section": s, "kind": "show", "value": k, "specials": True}
                  for s, k in day + [h for _a, f, _l in slots for h in f] if (s, k) in shorts]   # its shows' shorts
        brk = {"ads": ads if e.get("ads", True) else [], "bumps": bumps, "pad": 30, "mid": "off", "length": 120}
        more = {k: e[k] for k in ("block", "bug", "closed") if k in e}
        logo = e.get("logo", "")
        if logo == "show":              # a 24/7's: the show's title art (a Plex path: the app asks its server)
            logo = next((index.sections[s].shows[k].get("logo", "") for s, k in day), "")
        if logo:
            more["logo"] = logo
        # the same id from the same library on any Cathode: two never edited air the same days
        cid = hashlib.sha1(json.dumps([e["name"], sources], sort_keys=True).encode()).hexdigest()[:8]
        out.append(new_channel(e["name"], sources, e.get("order", "cyclic_shuffle"), starter=True, id=cid,
                               number=e.get("number", "auto"), group=e.get("group") or "Library",
                               breaks=brk if brk["ads"] or brk["bumps"] else {}, **more))
    return out


def _rows(c: dict, index) -> tuple:
    """What a channel's sources take: its shows ({(section, key): row}) and
    its movies ({(section, rating key): item})."""
    shows, movies = {}, {}
    for src in c.get("sources") or []:
        if src.get("exclude") or src.get("kind") == "group":
            continue
        for sec in index.sections.values():
            if (src.get("section") and sec.key != src["section"]) or (
                    not src.get("section") and (sec.breaks or sec.hidden)):
                continue
            if sec.kind == "show":
                if src.get("kind") == "show":
                    if src.get("value") in sec.shows:
                        shows[(sec.key, src["value"])] = sec.shows[src["value"]]
                else:
                    shows.update(((sec.key, k), sh) for k, sh in sec.shows.items() if _match(src, sh))
            elif sec.kind == "movie" and src.get("kind") != "show":
                movies.update(((sec.key, i["plex"]), i) for i in sec.items if _match(src, i))
    return shows, movies


def _kidness(rating: str) -> float:
    """How much a rating is for children: 1 for G and TV-Y, 0 for R and TV-MA."""
    return {"TV-PG": 0.75, "PG": 0.75, "TV-14": 0.4, "PG-13": 0.4}.get(
        rating, 1.0 if rating in KIDS else 0.0 if rating in MATURE else 0.5)


def _name(title: str) -> tuple:
    """A title's words, as keys ('Hunter x Hunter: Phantom Rouge' starts
    with 'Hunter x Hunter')."""
    return tuple(w for w in (_tkey(x) for x in (title or "").split()) if w)


def _profile(rows) -> dict:
    """What a channel's shows (or movies) are like: their libraries, studios,
    genres, how much they're for kids, their names. rows: (section, row)."""
    rows = list(rows)
    return {"sections": {s for s, _r in rows},
            "studios": collections.Counter(b for b in (brand(r.get("studio") or "") for _s, r in rows) if b),
            "genres": collections.Counter(g for _s, r in rows for g in r.get("genres") or ()),
            "n": len(rows), "kids": sum(_kidness(r.get("rating")) for _s, r in rows) / len(rows),
            "names": {_name(r["title"]) for _s, r in rows if len(_tkey(r["title"])) >= 6}}


def _like(row: dict, section: str, profiles: list, shows: list) -> Optional[dict]:
    """The channel a show (or movie) belongs on, by the ones already there:
    a spin-off or a show's movie with that show; else the channel most like
    it (its library, a studio mostly on that channel, its genres, how much
    it's for kids). Never a grown-ups' title on a kids' channel."""
    words = _name(row.get("title"))
    kin = [(len(n), c) for c, p in shows for n in p["names"] if words[:len(n)] == n]
    if kin:
        return max(kin, key=lambda t: t[0])[1]
    if row.get("rating") in MATURE:
        profiles = [p for p in profiles if p[0].get("content", "any") == "any" and p[1]["kids"] < 0.75] or profiles
    if not profiles:
        return None
    b, gs, k = brand(row.get("studio") or ""), row.get("genres") or [], _kidness(row.get("rating"))
    total = sum(p["studios"][b] for _c, p in profiles) if b else 0

    def score(cp):
        p = cp[1]
        g = sum(p["genres"][x] for x in gs) / ((p["n"] + 5) * len(gs)) if gs else 0.0     # (a few movies prove little)
        mostly = b and p["studios"][b] >= 2 and 2 * p["studios"][b] >= total               # (Hanna-Barbera's: Boomerang)
        return g + 0.25 * (1 - abs(k - p["kids"])) + 0.5 * (section in p["sections"]) + (1.0 if mostly else 0.0)
    return max(profiles, key=score)[0]


def newest(index) -> float:
    """When the library last took in a show or movie."""
    return max((i.get("added") or 0 for s in index.sections.values() if s.kind in ("show", "movie")
                and not s.breaks and not s.hidden for i in s.items), default=0)


def place_titles(chans: list, index, since: float = 0.0, config=None, table=None) -> list:
    """Each show and movie no channel has, put on the channel it belongs on
    (with `since`, only those the library took in after that moment): the
    one the starter's table names it for (in its daypart, if that's where
    it ran), else the one whose shows (movies) it's most like. A channel of
    one show (a 24/7) takes nothing; the table's leave-outs stay out.
    [(title, channel name)] placed."""
    table = table or lineup()
    leave = {_tkey(t) for t in table.get("leave_out", ())}
    homes = {}
    for e in table["channels"]:
        for t in e.get("shows", ()):
            homes.setdefault(_tkey(t), (e["name"], None))
    for e in table["channels"]:
        for sl in e.get("slots", ()):
            for t in sl.get("shows", ()):
                homes.setdefault(_tkey(t), (e["name"], sl["airs"]))
    for e in table["channels"]:
        for t in e.get("more", ()):
            homes.setdefault(_tkey(t), (e["name"], None))
    takes = {c["name"]: c for c in chans if not c.get("closed")}
    have_s, have_m, like_s, like_m = set(), set(), [], []
    for c in chans:
        s, m = _rows(expand(c, config) if config is not None else c, index)
        have_s |= s.keys()
        have_m |= {p for _s, p in m}
        if not c.get("closed"):
            like_s += [(c, _profile((k[0], r) for k, r in s.items()))] if s else []
            like_m += [(c, _profile((k[0], r) for k, r in m.items()))] if m else []
    placed = []
    for sec in index.sections.values():
        if sec.hidden or sec.breaks or sec.kind not in ("show", "movie"):
            continue
        if sec.kind == "show":
            first = {}
            for i in sec.items:
                first[i["show_key"]] = min(first.get(i["show_key"], i.get("added") or 0), i.get("added") or 0)
            for k, sh in sorted(sec.shows.items(), key=lambda kv: kv[1]["title"].lower()):
                t = _tkey(sh["title"])
                if (sec.key, k) in have_s or k not in first or (since and first[k] <= since) or t in leave:
                    continue
                name, airs = homes.get(t, (None, None))
                c = takes.get(name)
                if c is None:
                    c, airs = _like(sh, sec.key, like_s, like_s), None
                if c is None:
                    continue
                c.setdefault("sources", []).append(dict({"section": sec.key, "kind": "show", "value": k},
                                                        **({"airs": airs} if airs else {})))
                have_s.add((sec.key, k))
                placed.append((sh["title"], c["name"]))
            continue
        for i in sec.items:
            if i["plex"] in have_m or (since and (i.get("added") or 0) <= since) or i["duration"] < MIN_SECONDS \
                    or _tkey(i["title"]) in leave:
                continue
            c = _like(i, sec.key, like_m, like_s)
            if c is None:
                continue
            src = next((s for s in c.get("sources") or [] if s.get("kind") == "title" and s.get("section") == sec.key
                        and not s.get("exclude") and not s.get("airs")), None)
            if src is None:
                src = {"section": sec.key, "kind": "title", "value": []}
                c.setdefault("sources", []).append(src)
            elif not isinstance(src.get("value"), list):
                src["value"] = [src["value"]]
            src["value"].append(i["plex"])
            have_m.add(i["plex"])
            placed.append((i["title"], c["name"]))
    return placed


def add_starter(config, index) -> int:
    """The starter lineup's channels not already there (by name) added, and
    every show and movie no channel has put on one."""
    have = {c.get("name") for c in config.library_channels}
    new = [c for c in starter(index) if c["name"] not in have]
    config.library_channels.extend(new)
    place_titles(config.library_channels, index, config=config)
    config.library_starter_make = STARTER_MAKE
    config.library_placed_to = newest(index)
    return len(new)


def renew_starter(config, index) -> int:
    """An older make of the starter lineup replaced by this one: its channels
    you never edited taken out, the new ones added (yours stay as they are)."""
    config.library_channels[:] = [c for c in config.library_channels if not c.get("starter")]
    return add_starter(config, index)


# ── In the app ───────────────────────────────────────────────────────────

def start(app, fresh: bool = False, done=None):
    """The library read (its files, or the server where they're stale), the
    starter lineup made the first time, the channels placed and drawn up."""
    app._lib_gen = gen = getattr(app, "_lib_gen", 0) + 1

    def loaded(index, err):
        if getattr(app, "after", None):         # and again later: new arrivals join tomorrow's days
            app.after(REFRESH, lambda: gen == app._lib_gen and start(app))
        index = index or getattr(app, "library", None)
        if index is not None:
            cfg = app.config
            if not cfg.library_starter_done and not cfg.library_channels:
                n = add_starter(cfg, index)
                cfg.library_starter_done = True
                cfg.save()
                _sync.quiet(app)                # Cathode's doing, not an edit: another Cathode's lists still win
                if n:
                    app.toast(f"{n} channels made from your Plex library. Settings > Channels "
                              "to change them.", 10.0)
            elif cfg.library_starter_make < STARTER_MAKE:
                # an older make of the starter lineup: its channels nobody edited become this one's
                old = any(c.get("starter") for c in cfg.library_channels)
                n = renew_starter(cfg, index) if old else 0
                cfg.library_starter_make = STARTER_MAKE
                cfg.save()
                _sync.quiet(app)
                if n:
                    app.toast(f"The starter lineup is now your Tunarr channels: {n} channels. Channels you "
                              "changed are as they were.", 10.0)
            got = place_titles(cfg.library_channels, index, since=cfg.library_placed_to, config=cfg) \
                if cfg.library_placed_to else []
            top = newest(index)
            if got or top > cfg.library_placed_to:
                cfg.library_placed_to = max(top, cfg.library_placed_to)
                cfg.save()
                _sync.quiet(app)
            if got:                         # what the library took in, on its channels
                said = ", ".join(f"{t} on {c}" for t, c in got[:3]) + (f" and {len(got) - 3} more" if len(got) > 3
                                                                        else "")
                app.toast(f"New in your library: {said}.", 10.0)
            place(app)
        if done:
            done(index, err)
    library.load(app, loaded, fresh=fresh)


def place(app):
    """The channels put in the lineup (after a change to them) and their
    timelines built."""
    app.place_own_channels()            # (the lineup again, ours included: videochannels.add_to)
    rebuild(app)


def rebuild(app, done=None):
    """A Timeline per channel, built off the UI thread (a genre channel's
    groups are tens of thousands of episodes), then the guide."""
    index = getattr(app, "library", None)
    if index is None:
        return
    chans = [expand(dict(c), app.config) for c in app.config.library_channels]
    od = getattr(app, "ondemand", None)
    client = od.client() if od is not None and hasattr(od, "client") else None

    def poster(path, w=300, h=450):
        if path.startswith("http"):                     # (Jellyfin and Emby: the image's own address)
            return path
        return client.photo_url(path, w, h) if client and client.server and path.startswith("/") else ""

    def work():
        built = {}
        for c in chans:
            try:
                built[PREFIX + c["id"]] = Timeline(c, index, poster)
            except Exception as e:
                print(f"[library] {c.get('name')}: {e!r}")
        app.post(_built, app, built, done)
    if getattr(app, "post", None) is None:      # no event loop (tests): in line
        _built(app, {PREFIX + c["id"]: Timeline(c, index, poster) for c in chans}, done)
        return
    threading.Thread(target=work, daemon=True).start()


def _built(app, built: dict, done):
    from . import videochannels as vc
    for k in [k for k in SCHEDULES if k.startswith(PREFIX)]:
        del SCHEDULES[k]                # (the video channels' stay)
    SCHEDULES.update(built)
    from . import marks
    app.after(20.0, lambda: marks.fill(app))      # (mid-show breaks at marks: the titles coming up, read)
    print(f"[library] {len(built)} channels on the air.")
    vc.rebuild(app)
    if done:
        done()


def broken(ex: Exception) -> bool:
    """Whether a stream failed because of the title (its file is damaged or
    it left the library) and not the server being away: the one is skipped,
    the other waited out."""
    import urllib.error
    from .plex import PlexError
    return isinstance(ex, PlexError) or (isinstance(ex, urllib.error.HTTPError) and ex.code == 404)


def stream(app, e: dict, at: float) -> dict:
    """The stream for a title from `at` seconds in, asked of its place
    (Plex, Jellyfin or Emby, a folder) on the Player's thread."""
    key = e["plex"]
    if key.startswith("L"):
        from . import folders
        return folders.stream(key)
    if key.startswith("J"):
        from . import jellyfin
        from .plex import PlexError
        c = jellyfin.for_key(app, key)
        if c is None:
            raise PlexError("Its server isn't in the settings any more.")
        return c.stream_at(key, app.config.plex_quality or "Original", at)
    c = app.ondemand.client()
    if not c.server:
        c.discover_server(prefer=app.config.plex_server_id)
    return c.stream_at(e["plex"], app.config.plex_quality or "Original", at)


def options(index, section: str, kind: str) -> list:
    """[(value, label, count)] a source of this kind could take, for the
    maker: genres and studios by how much they hold, decades and shows in
    order."""
    n, names = {}, {}
    if kind in ("collection", "playlist"):
        got = getattr(index, kind + "s", None) or {}
        return sorted(((k, d["title"], len(d.get("keys") or [])) for k, d in got.items()
                       if not section or d.get("section", section) == section), key=lambda r: r[1].lower())
    for sec in index.sections.values():
        if (section and sec.key != section) or (not section and (sec.breaks or sec.hidden or sec.kind == "music")):
            continue
        if kind == "season":
            for i in sec.items if sec.kind == "show" else ():
                v = f"{i['show_key']}:{i['season']}"
                n[v] = n.get(v, 0) + 1
                names[v] = f"{i['title']}: " + (f"Season {i['season']}" if i["season"] else "Specials")
            continue
        rows = sec.shows.values() if sec.kind in ("show", "music") else sec.items
        for r in rows:
            if kind == "genre":
                vals = r["genres"]
            elif kind == "decade":
                vals = [r["year"] // 10 * 10] if r["year"] else []
            elif kind == "studio":
                vals = [brand(r["studio"])] if r["studio"] else []
            elif kind == "show":
                vals = [r["key"]] if sec.kind in ("show", "music") else []
                names[r.get("key")] = r["title"]
            elif kind == "title":
                vals = [] if sec.kind in ("show", "music") else [r["plex"]]
                names[r.get("plex")] = f"{r['title']} ({r['year']})" if r.get("year") else r["title"]

            else:
                vals = []
            for v in vals:
                n[v] = n.get(v, 0) + 1
    if kind == "decade":
        return [(v, f"{v}s", k) for v, k in sorted(n.items())]
    if kind == "season":
        return sorted(((v, names[v], k) for v, k in n.items()),
                      key=lambda r: (r[1].rsplit(":", 1)[0].lower(), int(r[0].rsplit(":", 1)[1]) or 999))
    if kind in ("show", "title"):
        return sorted(((v, names[v], k) for v, k in n.items()), key=lambda r: r[1].lower())
    return [(v, str(v), k) for v, k in sorted(n.items(), key=lambda kv: (-kv[1], str(kv[0])))]


def source_label(index, src: dict) -> str:
    """'TV Shows: Comedy', 'Everything: 1990s', 'The Simpsons'."""
    if src.get("kind") == "group":
        return f"Group: {src.get('label') or 'a content group'}"
    sec = index.sections.get(src.get("section") or "") if index else None
    where = sec.title if sec else "Everything"
    kind, val = src.get("kind", "all"), src.get("value")
    if kind == "all":
        return where
    if kind == "show":
        return (sec.shows.get(val) or {}).get("title", "A show") if sec else "A show"
    if kind == "title":
        vals = val if isinstance(val, list) else [val]
        if len(vals) == 1 and sec:
            i = next((i for i in sec.items if i["plex"] == vals[0]), None)
            return (f"{i['title']}: {i['name']}" if i.get("name") else i["title"]) if i else "A title"
        return f"{where}: {len(vals)} titles"
    if kind == "season":
        key, _, s = str(val).partition(":")
        show = ((sec.shows.get(key) or {}).get("title") if sec else None) or "A show"
        return f"{show}: " + (f"Season {s}" if s != "0" else "Specials")
    if kind in ("collection", "playlist"):
        d = (getattr(index, kind + "s", None) or {}).get(val) if index else None
        return f"{kind.title()}: {(d or {}).get('title') or 'gone'}"
    if kind == "decade":
        return f"{where}: {val}s"
    if kind == "rating":
        return f"{where}: rated {', '.join(val or [])}"
    return f"{where}: {val}"
