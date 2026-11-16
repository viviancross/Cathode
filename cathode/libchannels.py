"""Library channels: channels made from the Plex library, on a timeline.

Each channel in the settings (name, number, sources, sort method) sits
after the lineup. A source is a slice of the library index (library.py):
a whole library, a genre, a decade, a studio, a rating band or one show.
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

from . import library
from .playlist import Channel

PREFIX = "lib."                 # a library channel's id among the video channels'
VERSION = 1                     # of the written-down schedule
DAY_STARTS = 4                  # the broadcast day turns over at 4 AM
MIN_SECONDS = 60                # shorter titles stay out of a programme channel
KEEP_DAYS = 1                   # days behind today kept on disk
OFF_AIR = 7 * 86400             # a title that couldn't play is left out of the days drawn up this long
REFRESH = 6 * 3600              # the server asked again for what changed, this often
SCHEDULES: dict = {}            # channel id (with its prefix) -> Timeline

ORDERS = [("random", "Random"), ("cyclic_shuffle", "Cyclic Shuffle"), ("block_shuffle", "Block Shuffle"),
          ("block_cyclic", "Block Cyclic"), ("marathon_shuffle", "Marathon Shuffle"),
          ("marathon_cyclic", "Marathon Cyclic"), ("round_robin_shuffle", "Round Robin Shuffle"),
          ("round_robin_cyclic", "Round Robin Cyclic"), ("playlist", "Playlist Order")]
BLOCKS = {"block_shuffle": 2, "block_cyclic": 2, "marathon_shuffle": 12, "marathon_cyclic": 12}
KINDS = [("all", "Everything"), ("genre", "Genre"), ("decade", "Decade"), ("studio", "Studio"),
         ("rating", "Rating"), ("show", "Show")]
KIDS = ["TV-Y", "TV-Y7", "TV-Y7-FV", "TV-G", "G"]
MATURE = ["TV-MA", "R", "NC-17"]

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
    if not out or not made:
        return out
    taken = {c.number for c in out}
    nxt = (int(max(c.number for c in out)) // 100 + 1) * 100 + 1
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
                     epg_id=vc.epg_id(PREFIX + c["id"]), group=c.get("group") or "Library")
        at = next((i for i, o in enumerate(out) if o.number > num), len(out))
        out.insert(at, ch)
    return out


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
    return True


def groups(c: dict, index) -> list:
    """The titles a channel's sources match, as groups in title order: a
    show's episodes in their order (specials left out when it has seasons),
    each movie on its own. A title two sources match is in once."""
    out, seen = {}, set()
    for src in c.get("sources") or []:
        only = src.get("only")
        for sec in index.sections.values():
            if (src.get("section") and sec.key != src["section"]) or (
                    not src.get("section") and (sec.breaks or sec.hidden)):
                continue
            if only and sec.kind != only:
                continue
            if sec.kind == "show":
                keys = {k for k, sh in sec.shows.items() if _match(src, sh)}
                for i in sec.items:
                    if i["show_key"] in keys and i["duration"] >= MIN_SECONDS and i["id"] not in seen:
                        seen.add(i["id"])
                        out.setdefault("s" + i["show_key"], {"id": "s" + i["show_key"], "title": i["title"],
                                                             "items": []})["items"].append(i)
            elif src.get("kind") != "show":
                for i in sec.items:
                    if i["duration"] >= MIN_SECONDS and i["id"] not in seen and _match(src, i):
                        seen.add(i["id"])
                        out["m" + i["plex"]] = {"id": "m" + i["plex"], "title": i["title"], "items": [i]}
    for g in out.values():
        if len(g["items"]) > 1:
            g["items"].sort(key=lambda i: (i["season"], i["episode"], i["air"]))
            if any(i["season"] for i in g["items"]):
                g["items"] = [i for i in g["items"] if i["season"]] or g["items"]
    return sorted(out.values(), key=lambda g: (g["title"].lower(), g["id"]))


class Rotor:
    """Draws a channel's next title by its sort method. Its state is a small
    dict that goes to disk with the schedule, so the rotation carries on."""

    def __init__(self, cid: str, order: str, block: int, groups_: list, state: dict, skip=()):
        self.cid, self.order, self.groups, self.state = cid, order, groups_, state
        self.skip = skip            # titles off the air (they couldn't play)
        self.block = max(1, int(block or BLOCKS.get(order, 1)))
        self.items = [i for g in groups_ for i in g["items"]]
        self._gpos = {g["id"]: n for n, g in enumerate(groups_)}
        self._ipos: dict = {}
        self._memo = None           # (what, the shuffle for it)
        self._weights = [len(g["items"]) ** 0.5 for g in groups_]

    def _rng(self, *what):
        return random.Random(f"{self.cid}:" + ":".join(str(w) for w in what))

    def _shuffled(self, what: str, n: int, of: list) -> list:
        if self._memo is None or self._memo[0] != (what, n):
            lst = list(of)
            self._rng(what, n).shuffle(lst)
            self._memo = ((what, n), lst)
        return self._memo[1]

    def _cycle(self, n: int) -> list:
        """Every title, shuffled for cycle n; it doesn't open on the title
        the cycle before closed on."""
        if self._memo is None or self._memo[0] != ("c", n):
            lst = list(self.items)
            self._rng("c", n).shuffle(lst)
            if n and len(lst) > 2:
                prev = list(self.items)
                self._rng("c", n - 1).shuffle(prev)
                if lst[0] is prev[-1]:
                    lst[0], lst[1] = lst[1], lst[0]
            self._memo = (("c", n), lst)
        return self._memo[1]

    def next(self) -> Optional[dict]:
        """The next title to air, passing over any that are off the air."""
        for _ in range(len(self.items)):
            i = self._draw()
            if i["id"] not in self.skip:
                return i
        return None

    def _draw(self) -> dict:
        o, st = self.order, self.state
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

    def _next_group(self) -> dict:
        o, st, n = self.order, self.state, len(self.groups)
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


def describe(i: dict) -> dict:
    """A title as the Player and the guide take it."""
    e = dict(i)
    e["kind"] = "show"
    if i["type"] == "episode":
        e["episode_text"] = f"S{i['season']} E{i['episode']}" if i["season"] else ""
        e["desc"] = (f'"{i["name"]}"  ' if i["name"] else "") + i["summary"]
        e["category"] = (i["genres"] or ["Series"])[0]
    else:
        e["desc"] = (f"({i['year']})  " if i["year"] else "") + i["summary"]
        e["category"] = "Movie" if i["type"] == "movie" else (i["genres"] or ["Video"])[0]
    return e


class Timeline:
    """A library channel's written-down running order, a day at a time. To
    the Player and the guide it answers as a video channel's Schedule does."""

    sources = ()                # (nothing for the video channels' source report)

    def __init__(self, c: dict, index, poster=None, store: bool = True):
        self.c = dict(c, guide="video")
        self.cid = PREFIX + c["id"]
        self.index = index
        self.poster = poster
        self.store = store
        self.dropped: dict = {}     # a title that couldn't play -> when
        self.guide_memo = None
        self.lock = threading.RLock()
        self.groups = groups(c, index)
        self.entries = [i for g in self.groups for i in g["items"]]
        self.sig = hashlib.sha1(json.dumps([VERSION, c.get("sources"), c.get("order"), c.get("block"),
                                            c.get("seed", 0)], sort_keys=True).encode()).hexdigest()[:12]
        self.stamp = index.stamp()
        self.days: list = []        # [{"day", "start", "state": as it began, "slots": [[start, id, seconds]]}]
        self.state: dict = {}       # as the last day ended
        self._starts: list = []
        self._slots: list = []
        self._made: dict = {}
        self._dirty = False
        if store:
            self._load()

    def median(self) -> float:
        return 3600.0

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
        today = day_of(time.time())[0]
        cut = None                                  # the first day that has to be drawn up again
        for n, day in enumerate(days):
            if any(self.index.item(s[1]) is None for s in day["slots"]):
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
                json.dump({"v": VERSION, "sig": self.sig, "stamp": self.stamp, "days": self.days,
                           "state": self.state, "dropped": self.dropped}, f, separators=(",", ":"))
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
        rotor = Rotor(f"{self.cid}:{seed}" if seed else self.cid, self.c.get("order", "cyclic_shuffle"),
                      self.c.get("block", 0), self.groups, state, self.dropped)
        slots = []
        while t < end:
            i = rotor.next()
            if i is None:
                break
            slots.append([t, i["id"], i["duration"]])
            t += i["duration"]
        state["t"] = t
        self.days.append({"day": name, "start": start, "state": before, "slots": slots})
        self._dirty = True

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

    def at(self, now: datetime) -> Optional[dict]:
        """{"entry", "offset", "start", "stop"} on the air at `now` (UTC)."""
        t = now.timestamp()
        with self.lock:
            self._cover(t)
            n = _bisect(self._starts, t) - 1
            if n < 0:
                return None
            start, item_id, dur = self._slots[n]
            if t >= start + dur:
                return None
            e = self._made.get(item_id)
            if e is None:
                i = self.index.item(item_id)
                if i is None:
                    return None
                e = self._made[item_id] = describe(i)
                if self.poster and i["thumb"]:
                    e["icon"] = self.poster(i["thumb"])
            return {"entry": e, "offset": t - start, "start": _utc(start), "stop": _utc(start + dur)}

    def drop(self, item_id: str, now: Optional[datetime] = None):
        """A title that can't play leaves the air: what's left of it now, and
        every airing of it drawn up ahead, is taken out and what follows
        moves up to fill the time. It stays out of the days drawn up from
        here on, for a week."""
        t = (now or datetime.now(timezone.utc)).timestamp()
        with self.lock:
            self.dropped[item_id] = time.time()
            shift = 0.0
            for d in self.days:
                if shift and d["state"].get("t", 0) > t:
                    d["state"]["t"] -= shift            # (the day began that much sooner)
                keep = []
                for s in d["slots"]:
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
            self._index()
            self._save()


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

# The starter lineup's channel names: placeholders of our own, there to be renamed.
GENRE_NAMES = {"Comedy": "Laugh Track", "Animation": "Toon Tube", "Family": "Family Room", "Reality": "Unscripted",
               "Game Show": "Buzzer", "Adventure": "Quest", "Documentary": "Fact Finder", "Drama": "Primetime",
               "Action": "Overdrive", "Fantasy": "Spellbound", "Music": "Encore", "Talk Show": "Couch Talk",
               "Talk": "Couch Talk", "Romance": "Heartstrings", "Sport": "Scoreboard", "Science Fiction": "Orbit",
               "Mystery": "Whodunit", "Crime": "Case File", "Horror": "Fright Night", "Children": "Playtime",
               "News": "The Wire", "History": "Time Capsule", "Anime": "Mecha", "Thriller": "Edge of Seat",
               "Western": "High Noon", "War": "Front Line", "Food": "Hot Plate"}
STUDIO_NAMES = {"Nickelodeon": "Slimetime", "Disney": "Mouse House", "Hanna-Barbera": "Yabba Dabba",
                "Cartoon Network": "Checkerboard", "Williams Street": "Late Swim", "Warner Bros.": "Water Tower",
                "MTV": "Unplugged", "G4": "Player Two", "BBC": "The Beeb", "Comedy Central": "Comedy Capital",
                "20th Century Fox": "Fanfare", "Dickhouse": "Stunt House"}
KIDS_NAME, MATURE_NAME = "Saturday Morning", "After Dark"
MOVIE_NAMES = {"Animation": "Animated", "Science Fiction": "Sci-Fi"}
MAIN_SHOWS = 30                 # a show library this big gets genre, decade and studio channels
GENRE_SHOWS, DECADE_SHOWS, STUDIO_SHOWS = 10, 10, 6
GENRE_MOVIES, DECADE_MOVIES = 20, 20
MARATHON_EPISODES, MARATHONS = 150, 12


def starter(index) -> list:
    """A lineup made from what the library holds: a channel per genre, decade
    and studio with enough in it, the kids' and the grown-ups' shows, a
    channel for each long-running show, the movies, and each small library."""
    out = []

    def add(name, group, order, *sources):
        out.append(new_channel(name, sources, order, starter=True, group=group))

    secs = index.programme_sections()
    shows = [s for s in secs if s.kind == "show"]
    main = [s for s in shows if len(s.shows) >= MAIN_SHOWS]
    rows = [(s, sh) for s in main for sh in s.shows.values()]

    def count(values):
        n = {}
        for v in values:
            if v:
                n[v] = n.get(v, 0) + 1
        return sorted(n.items(), key=lambda kv: (-kv[1], str(kv[0])))

    for genre, n in count(g for _s, sh in rows for g in sh["genres"]):
        if n >= GENRE_SHOWS:
            add(GENRE_NAMES.get(genre, genre), "Genres", "block_shuffle", {"kind": "genre", "value": genre, "only": "show"})
    for decade, n in sorted(count(sh["year"] // 10 * 10 for _s, sh in rows)):
        if n >= DECADE_SHOWS:
            add(_decade(decade), "Decades", "round_robin_shuffle",
                {"kind": "decade", "value": decade, "only": "show"})
    for studio, n in count(brand(sh["studio"]) for _s, sh in rows):
        if n >= STUDIO_SHOWS:
            add(STUDIO_NAMES.get(studio, studio), "Studios", "block_shuffle",
                {"kind": "studio", "value": studio, "only": "show"})
    if sum(1 for _s, sh in rows if sh["rating"] in KIDS) >= GENRE_SHOWS:
        add(KIDS_NAME, "Genres", "round_robin_shuffle", {"kind": "rating", "value": KIDS, "only": "show"})
    if sum(1 for _s, sh in rows if sh["rating"] in MATURE) >= GENRE_SHOWS:
        add(MATURE_NAME, "Genres", "block_shuffle", {"kind": "rating", "value": MATURE, "only": "show"})
    eps = {}
    for s in main:
        for i in s.items:
            eps[(s.key, i["show_key"])] = eps.get((s.key, i["show_key"]), 0) + 1
    for (key, show), n in sorted(eps.items(), key=lambda kv: -kv[1])[:MARATHONS]:
        if n >= MARATHON_EPISODES:
            add(index.sections[key].shows[show]["title"], "Marathons", "playlist",
                {"section": key, "kind": "show", "value": show})
    movies = [s for s in secs if s.kind == "movie"]
    rich = max(movies, key=lambda s: len({g for i in s.items for g in i["genres"]}), default=None)
    for s in movies:
        add(s.title, "Movies", "cyclic_shuffle", {"section": s.key, "kind": "all"})
        if s is not rich:
            continue                    # the library with the most kinds of film also gets genre and decade channels
        for genre, k in count(g for i in s.items for g in i["genres"]):
            if k >= GENRE_MOVIES:
                add(f"{MOVIE_NAMES.get(genre, genre)} Movies", "Movies", "cyclic_shuffle",
                    {"section": s.key, "kind": "genre", "value": genre})
        for decade, k in sorted(count(i["year"] // 10 * 10 for i in s.items)):
            if k >= DECADE_MOVIES:
                add(f"{_decade(decade)[4:]} Movies", "Movies", "cyclic_shuffle",
                    {"section": s.key, "kind": "decade", "value": decade})
    for s in shows:
        if s not in main:
            add(s.title, "Libraries", "block_shuffle", {"section": s.key, "kind": "all"})
    for s in secs:
        if s.kind == "clip":
            add(s.title, "Libraries", "cyclic_shuffle", {"section": s.key, "kind": "all"})
    return out


def _decade(decade: int) -> str:
    return f"The {decade}s" if decade >= 2000 else f"The '{decade % 100:02d}s"


def add_starter(config, index) -> int:
    """The starter lineup's channels not already there (by name) added."""
    have = {c.get("name") for c in config.library_channels}
    new = [c for c in starter(index) if c["name"] not in have]
    config.library_channels.extend(new)
    return len(new)


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
                if n:
                    app.toast(f"{n} channels made from your Plex library. Settings > Channels > "
                              "Library Channels to change them.", 10.0)
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
    chans = [dict(c) for c in app.config.library_channels]
    od = getattr(app, "ondemand", None)
    client = od.client() if od is not None and hasattr(od, "client") else None

    def poster(path):
        return client.photo_url(path, 300, 450) if client and client.server else ""

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
    SCHEDULES.clear()
    SCHEDULES.update(built)
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
    """The stream for a title from `at` seconds in, asked of the server
    (on the Player's thread)."""
    c = app.ondemand.client()
    if not c.server:
        c.discover_server(prefer=app.config.plex_server_id)
    return c.stream_at(e["plex"], app.config.plex_quality or "Original", at)


def options(index, section: str, kind: str) -> list:
    """[(value, label, count)] a source of this kind could take, for the
    maker: genres and studios by how much they hold, decades and shows in
    order."""
    n, names = {}, {}
    for sec in index.sections.values():
        if (section and sec.key != section) or (not section and (sec.breaks or sec.hidden)):
            continue
        rows = sec.shows.values() if sec.kind == "show" else sec.items
        for r in rows:
            if kind == "genre":
                vals = r["genres"]
            elif kind == "decade":
                vals = [r["year"] // 10 * 10] if r["year"] else []
            elif kind == "studio":
                vals = [brand(r["studio"])] if r["studio"] else []
            elif kind == "show":
                vals = [r["key"]] if sec.kind == "show" else []
                names[r.get("key")] = r["title"]
            else:
                vals = []
            for v in vals:
                n[v] = n.get(v, 0) + 1
    if kind == "decade":
        return [(v, f"{v}s", k) for v, k in sorted(n.items())]
    if kind == "show":
        return sorted(((v, names[v], k) for v, k in n.items()), key=lambda r: r[1].lower())
    return [(v, str(v), k) for v, k in sorted(n.items(), key=lambda kv: (-kv[1], str(kv[0])))]


def source_label(index, src: dict) -> str:
    """'TV Shows: Comedy', 'Everything: 1990s', 'The Simpsons'."""
    sec = index.sections.get(src.get("section") or "") if index else None
    where = sec.title if sec else "Everything"
    kind, val = src.get("kind", "all"), src.get("value")
    if kind == "all":
        return where
    if kind == "show":
        return (sec.shows.get(val) or {}).get("title", "A show") if sec else "A show"
    if kind == "decade":
        return f"{where}: {val}s"
    if kind == "rating":
        return f"{where}: rated {', '.join(val or [])}"
    return f"{where}: {val}"
