"""Spelunkr (spelunkr.tv): 24/7 channels of forgotten Internet Archive video,
shipped as a saved playlist ("spelunkr://").

The network publishes its lineup (data.spelunkr.tv/lineup.json) and, per
channel, versioned manifests: the Internet Archive files it airs (each with
its running time and where to start in the file), the text bumpers that run
between shows with their music, the commercial reels (slices of archive
tapes) its ad breaks are cut from, and, for marathon channels, the Up Next
cards between episodes. Every client works out what is on from the same
data and the same seeded arithmetic, so everyone sees the same moment;
_engine below is that arithmetic (the site's engine 5), so a channel here
airs what the site airs, breaks and all. A manifest for a newer engine
falls back to the shows end to end (and says so in the log).

The lineup is fetched again every five minutes, as the site does: a new
channel joins the dial and a new version of a channel takes over at its
moment. The video channels' player plays it all: shows and commercials
straight from archive.org, a bumper as its slides over its music."""

from __future__ import annotations

import json
import os
import re
import struct
import threading
import time
import urllib.parse
import urllib.request
from bisect import bisect_left, bisect_right
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import paths
from .net import SSL
from .playlist import Channel
from .videochannels import SCHEME, epg_id

URL = "spelunkr://"
NAME = "Spelunkr"
PREFIX = "spelunkr."                # a Spelunkr channel's id among the video channels'
DATA = "https://data.spelunkr.tv/"
AUDIO = "https://audio.spelunkr.tv/bumps/"
LOGO = "https://spelunkr.tv/brand/pixel/png/{}-64.png"
FILES = "https://archive.org/download/{}/{}"
ENGINE = 5                          # the engine _engine follows
REFRESH = 5 * 60                    # the lineup, fetched again this often (the site's own poll)
# A tune's patience: archive.org hands over a file's index before its first
# frame, up to 40 MB on the channels of taped broadcasts (1.6 MB typical),
# which on a slower line outlasts the usual tune timeout.
TUNE_WAIT = 45.0
SCHEDULES: dict = {}                # channel id -> Schedule, from the last lineup loaded


def ship(config) -> bool:
    """Spelunkr in the saved playlists, once: a fresh install and an old one
    both get it; one deleted stays deleted. True when the config changed."""
    if config.spelunkr_shipped:
        return False
    if not any(p.get("playlist_url") == URL for p in config.playlists):
        config.playlists.append({"name": NAME, "playlist_url": URL, "epg_url": ""})
    config.spelunkr_shipped = True
    return True


def is_shipped(pl: dict) -> bool:
    return pl.get("playlist_url") == URL


def is_spelunkr(ch) -> bool:
    return ch.url.startswith(SCHEME + PREFIX)


# ── Fetching ─────────────────────────────────────────────────────────────

def _cache(path: str) -> str:
    return os.path.join(paths.cache_dir(), "spelunkr", path.replace("/", "_"))


def _get(path: str, fresh: bool = False):
    """A JSON file of the network's: from the cache unless `fresh` (manifests
    and platform files are versioned, so a cached one never goes stale), the
    cached copy again when the network can't be reached."""
    f = _cache(path)
    if not fresh and os.path.exists(f):
        with open(f, encoding="utf-8") as fh:
            return json.load(fh)
    try:
        req = urllib.request.Request(DATA + path, headers={"User-Agent": "Cathode"})
        with urllib.request.urlopen(req, context=SSL, timeout=20) as r:
            raw = r.read()
        data = json.loads(raw)
    except Exception:
        if os.path.exists(f):
            with open(f, encoding="utf-8") as fh:
                return json.load(fh)
        raise
    os.makedirs(os.path.dirname(f), exist_ok=True)
    tmp = f"{f}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "wb") as fh:          # whole or not at all: the loaders share the platform files
        fh.write(raw)
    os.replace(tmp, f)
    return data


def _version(cid: str, ptr: dict, base_audio: str):
    """A version pointer's Timeline: its manifest, its platform file (the
    network's own bumpers), its details (each show's description)."""
    man = _get(ptr["manifest"])
    plat = _get(man["platform"]) if man.get("platform") else None
    try:
        notes = _get(ptr["details"]).get("items") or [] if ptr.get("details") else []
    except Exception:
        notes = []
    return Timeline(cid, ptr, man, plat, notes, base_audio)


def channels() -> list:
    """The dial: one channel per Spelunkr channel on the air with a dial
    number, its schedule kept in SCHEDULES. Raises when the lineup can't be
    had (fetched or cached)."""
    lineup = _get("lineup.json", fresh=True)
    base_audio = lineup.get("audioBase") or AUDIO
    now_ms = time.time() * 1000
    picks = []
    for c in lineup.get("channels") or []:
        if not isinstance(c.get("dial"), int) or c.get("debugOnly") or c.get("comingSoon") or not c.get("versions"):
            continue
        # the version on the air now and any after it (the site's own choice)
        live = [v for v in c["versions"] if v.get("effectiveAtMs", v.get("epochMs", 0)) <= now_ms]
        cur = max(live, key=lambda v: v["v"]) if live else None
        for v in c["versions"]:
            if cur is None or v["v"] >= cur["v"]:
                picks.append((c, v))

    have = {(tl.cid, tl.v): tl for s in SCHEDULES.values() for tl in s.timelines}

    def load(pick):
        old = have.get((PREFIX + pick[0]["id"], pick[1]["v"]))
        if old is not None:             # a version already in hand keeps its built cycles
            return old
        try:
            return _version(PREFIX + pick[0]["id"], pick[1], base_audio)
        except Exception as e:
            print(f"[spelunkr] {pick[0].get('id')} v{pick[1].get('v')}: {e!r}")
            return None
    with ThreadPoolExecutor(8) as ex:
        loaded = list(ex.map(load, picks))
    by = {}
    for (c, _v), tl in zip(picks, loaded):
        if tl is not None:
            by.setdefault(c["id"], (c, []))[1].append(tl)
    out, scheds = [], {}
    for c, tls in by.values():
        cid = PREFIX + c["id"]
        family = (c.get("family") or "").replace("-", " ").title().replace("Tv ", "TV ") or NAME
        scheds[cid] = Schedule(cid, c.get("name") or c["id"], tls, family)
        out.append(Channel(number=c["dial"], name=c.get("name") or c["id"], url=SCHEME + cid,
                           epg_id=epg_id(cid), group=family, logo=LOGO.format(c["id"])))
    now = datetime.now(timezone.utc)
    for s in scheds.values():           # the cycles on now, built here off the UI thread
        try:
            s.at(now)
        except Exception as e:
            print(f"[spelunkr] {s.cid}: {e!r}")
    SCHEDULES.clear()
    SCHEDULES.update(scheds)
    print(f"[spelunkr] {len(out)} channels, lineup of {lineup.get('generatedAt', '?')}")
    return sorted(out, key=lambda ch: ch.number)


# ── The engine: the site's arithmetic, ported (engine 5) ─────────────────
# Constants and names follow the site's code; the comments say what each is.

CARD_FLOOR, CARD_BASE, CARD_PER_CHAR = 2500, 1500, 55       # a bumper slide's time on screen
TITLE_MS, GAP_MS, HOLD_MS, BETWEEN_MS = 3500, 1000, 1000, 300
AD_GAP = 20 * 60000                 # an ad break at most this often
ROUND = 336 * 3600000               # two weeks: the commercials' rotation
LT = 1_000_000                      # the rotation's places
SLOT = 20000                        # a break's allowance in the ad rates
DAY = 24 * 3600000
HOUR = 3600000
TOLS = (3, 6)                       # years either side a commercial may come from


def _u16(s: str) -> list:
    """UTF-16 code units: what the site's string lengths and hashes count."""
    b = (s or "").encode("utf-16-le")
    return struct.unpack(f"<{len(b) // 2}H", b)


def _slide_ms(text: str) -> int:
    return max(CARD_FLOOR, CARD_BASE + len(_u16(text)) * CARD_PER_CHAR)


def _slides_ms(bump) -> int:
    return sum(_slide_ms(s.get("text", "")) for s in (bump.get("slides") or []))


def _break_ms(w, z) -> int:
    return TITLE_MS + _slides_ms(w) + GAP_MS + HOLD_MS + BETWEEN_MS + _slides_ms(z) + GAP_MS + HOLD_MS


def _hash(s: str) -> int:
    t = 0
    for c in _u16(s):
        t = (t * 31 + c) & 0xFFFFFFFF
    return t


def _rng(seed: int):
    """The site's seeded random numbers (mulberry32)."""
    t = seed & 0xFFFFFFFF

    def nxt():
        nonlocal t
        t = (t + 0x6D2B79F5) & 0xFFFFFFFF
        n = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
        n ^= (n + ((n ^ (n >> 7)) * (61 | n))) & 0xFFFFFFFF
        return ((n ^ (n >> 14)) & 0xFFFFFFFF) / 4294967296
    return nxt


def _falsy(x) -> bool:              # JS truthiness: an empty list is truthy there
    return x is None or x is False or x == "" or (isinstance(x, (int, float)) and not isinstance(x, bool) and x == 0)


def _day_ms(day: str, end: bool) -> float:
    try:
        d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000
    except ValueError:
        return float("nan")
    return d + DAY - 1 if end else d


def _in_season(rng, t: float) -> bool:
    a, b = rng[0], rng[1]
    if re.match(r"^\d{4}-", a):
        return _day_ms(a, False) <= t <= _day_ms(b, True)
    md = lambda u: (lambda p: p[0] * 100 + p[1])([int(x) for x in u.split("-")[:2]])
    d = datetime.fromtimestamp(t / 1000, timezone.utc)
    o, c, e = d.month * 100 + d.day, md(a), md(b)
    return c <= o <= e if c <= e else (o >= c or o <= e)


def _eligible(bumps, t):
    live = [b for b in bumps if b.get("active") is not False]
    year_round = [b for b in live if _falsy(b.get("date_range"))]
    seasonal = [b for b in live if not _falsy(b.get("date_range"))]
    if any(_in_season(b["date_range"], t) for b in seasonal):
        return [b for b in live if _falsy(b.get("date_range")) or _in_season(b["date_range"], t)]
    return year_round


def _pick(bumps, idx, name, seed, t):
    if not bumps:
        return None
    pool = _eligible(bumps, t)
    if not pool:
        return None
    return pool[int(_rng(_hash(f"{name}-break-{idx}-{seed}"))() * len(pool))]


def _shuffle(pool, recent, seed):
    """A deck of bumpers, shuffled, the last few played kept off its top."""
    r = _rng(seed)
    s = list(pool)
    for i in range(len(s) - 1, 0, -1):
        j = int(r() * (i + 1))
        s[i], s[j] = s[j], s[i]
    half = len(s) // 2
    rank = {}
    for i in range(min(half, len(recent)), 0, -1):
        rank[id(recent[-i])] = half + 1 - i
    if not rank:
        return s
    c = lambda b: rank.get(id(b), 0)
    for i in range(1, min(half, len(recent)) + 1):
        u = recent[-i]
        h = next((k for k, b in enumerate(s) if b is u), -1)
        if h < 0 or h >= c(u):
            continue
        f = [p for p in range(c(u), len(s)) if c(s[p]) <= h]
        pick = r()                  # drawn even when there's nothing to swap with, as the site draws it
        if not f:
            continue
        d = f[int(pick * len(f))]
        s[h], s[d] = s[d], s[h]
    return s


def _deck_copy(st):
    return ({"order": st["order"], "pos": st["pos"], "key": st["key"], "recent": list(st["recent"]), "rounds": 0}
            if st else {"order": [], "pos": 0, "key": None, "recent": [], "rounds": 0})


def _deal(st, bumps, name, seed, t):
    if not bumps:
        return None
    pool = _eligible(bumps, t)
    if not pool:
        return None
    seasonal = [b for b in bumps if b.get("active") is not False and not _falsy(b.get("date_range"))]
    key = "|".join(str(b.get("id")) for b in seasonal if _in_season(b["date_range"], t)) if seasonal else ""
    if st["key"] != key or st["pos"] >= len(st["order"]):
        st["order"] = _shuffle(pool, st["recent"], _hash(f"{name}-deck-{seed}-{st['rounds']}"))
        st["rounds"] += 1
        st["pos"], st["key"] = 0, key
    b = st["order"][st["pos"]]
    st["pos"] += 1
    st["recent"].append(b)
    if len(st["recent"]) > len(st["order"]):
        st["recent"].pop(0)
    return b


def _music(pool, bump_id, idx, seed):
    """A bumper's track: drawn from the pool, a start up to a minute in."""
    if not pool:
        return None
    r = _rng(_hash(f"{bump_id}-audio-{idx}-{seed}"))
    k = int(r() * len(pool))
    return dict(pool[k], startOffset=int(r() * 60))


def _sting(stings, idx, name, seed):
    if not stings:
        return None
    return stings[int(_rng(_hash(f"{name}-card-{idx}-{seed}"))() * len(stings))]


def _year(x):
    m = re.match(r"\s*([+-]?\d+)", str((x or {}).get("year") or ""))
    return int(m.group(1)) if m else None


def _phase(slice_):
    return int(_rng(_hash(f"ad-{slice_['id']}"))() * LT)


def _phases(slices):
    t = [_phase(s) for s in slices]
    order = sorted(range(len(slices)), key=lambda i: (t[i], slices[i]["id"], i))
    out = [0] * len(slices)
    for rank, i in enumerate(order):
        out[i] = rank * LT // len(slices)
    return out


def _ad_start(start, name):
    s = start if isinstance(start, int) and not isinstance(start, bool) and 0 <= start < 1000 else _hash(f"ads-{name}") % 1000
    return s * (LT / 1000)


def _rates(items, block, gap, slice_ms):
    s = i = o = c = 0.0
    by_year = {}
    for h, u in enumerate(items):
        f = u["duration"] * 1000
        s += f
        i += f
        o += f
        if block and h < len(items) - 1 and o < block["lengthMs"]:
            s += block["cardMs"]
            i += block["cardMs"]
            o += block["cardMs"]
            continue
        o = 0
        d = items[(h + 1) % len(items)]
        if u.get("offAir") is not True and d.get("offAir") is not True and i >= gap:
            c += 1
            by_year[_year(u)] = by_year.get(_year(u), 0) + 1
            s += SLOT + slice_ms
            i = SLOT / 2
        else:
            s += SLOT
            i += SLOT
    return {"cycleMs": s, "total": c, "byYear": by_year}


class _AdPlan:
    """Which commercial a break gets: every slice has a place in a two-week
    rotation; a break takes the next one due from its show's years (widening
    to any year when those run thin), none twice in a row's memory."""

    def __init__(self, slices, lineup, block, gap, name, start, decades):
        self.slices = slices
        self.phases = _phases(slices)
        avg = sum(s["lengthMs"] for s in slices) / len(slices)
        self.rates = _rates(lineup, block, gap, avg)
        self.years = [_year(s) for s in slices]
        self.start = _ad_start(start, name)
        self.dec = f"d{decades}" if isinstance(decades, int) and not isinstance(decades, bool) and decades >= 1 else None
        self._tiers, self._memo = {}, {}

    def _tier(self, g, v):
        key = (g, v)
        if key in self._memo:
            return self._memo[key]
        dec = int(v[1:]) if isinstance(v, str) else None
        inf = v == float("inf")

        def fits(n):
            if inf:
                return True
            if n is None or g is None:
                return False
            return abs(n // 10 - g // 10) <= dec if dec is not None else abs(n - g) <= v
        lst = sorted((n for n in range(len(self.slices)) if self.slices[n].get("anywhere") is True or fits(self.years[n])),
                     key=lambda n: (self.phases[n], self.slices[n]["id"], n))
        c = sum(cnt for yr, cnt in self.rates["byYear"].items() if fits(yr))
        need = c * ROUND / self.rates["cycleMs"] if self.rates["cycleMs"] > 0 else 0
        healthy = len(lst) > 0 and len(lst) >= need
        round_ms = ROUND if healthy or not lst else max(HOUR, int(len(lst) * self.rates["cycleMs"] // c))
        k = {"tol": v, "list": lst, "places": [self.phases[n] for n in lst], "roundMs": round_ms, "healthy": healthy}
        self._memo[key] = k
        return k

    def tiers(self, g):
        if g in self._tiers:
            return self._tiers[g]
        if g is None:
            v = [self._tier(None, float("inf"))]
        else:
            v = [self._tier(g, t) for t in (*TOLS, *([self.dec] if self.dec else []), float("inf"))]
        first = next(i for i, t in enumerate(v) if t["healthy"] or t["tol"] == float("inf"))
        self._tiers[g] = v[first:]
        return self._tiers[g]


def _place(t, round_ms, start):
    r = ((t % round_ms) + round_ms) % round_ms
    return (int(r * LT // round_ms) + start) % LT


def _choose_ad(plan, used, year, now, since=None):
    since = now if since is None else since
    if len(used) >= len(plan.phases):
        used.clear()
    tiers = [t for t in plan.tiers(year) if t["list"]]
    firsts = []
    for tier in tiers:
        lst, n = tier["list"], len(tier["list"])
        h = _place(since, tier["roundMs"], plan.start)
        f = _place(now, tier["roundMs"], plan.start)
        d = 0 if now <= since else LT if now - since >= tier["roundMs"] else (f - h + LT) % LT
        p = int(min(DAY, tier["roundMs"]) * LT // tier["roundMs"])
        m = bisect_left(tier["places"], h + 1)
        firsts.append(m)
        for g in range(n):
            v = (m + g) % n
            if (((tier["places"][v] - h + LT) % LT) or LT) > d:
                break
            if lst[v] not in used:
                used.add(lst[v])
                return lst[v]
        for g in range(1, n + 1):
            v = (m - g + n * 2) % n
            if (h - tier["places"][v] + LT) % LT >= p:
                break
            if lst[v] not in used:
                used.add(lst[v])
                return lst[v]
    for k, tier in enumerate(tiers):
        n = len(tier["list"])
        for f in range(1, n + 1):
            d = tier["list"][(firsts[k] - f + n * 2) % n]
            if d not in used:
                used.add(d)
                return d
    return -1


class Timeline:
    """One version of a channel: its cycles (the shows round once, with their
    breaks) laid end to end from the version's epoch."""

    def __init__(self, cid, ptr, man, plat, notes, base_audio):
        self.cid, self.name = cid, cid[len(PREFIX):]
        self.v = ptr["v"]
        self.epoch = int(ptr.get("epochMs", 0))
        self.effective = int(ptr.get("effectiveAtMs", self.epoch))
        self.engine = man.get("engine") or 0
        self.items = [dict(it, _note=(notes[k] if k < len(notes) and isinstance(notes[k], dict) else {}).get("description", ""))
                      for k, it in enumerate(man.get("items") or [])]
        self.first = int(ptr.get("startIndex") or 0)
        if not 0 <= self.first < len(self.items):
            self.first = 0
        cb, pb = man.get("bumps") or [], (plat or {}).get("bumps") or []
        self.base_audio = base_audio
        self.bumps = None
        if cb and pb and self.engine <= ENGINE:
            pools = man.get("audioPools") or {}
            self.bumps = {"channel": cb, "platform": pb,
                          "channel_audio": [a for v in pools.values() for a in v] if man.get("audioOverlay") else man.get("audio") or [],
                          "platform_audio": (plat or {}).get("audio") or []}
        if self.engine > ENGINE:
            print(f"[spelunkr] {self.name} v{self.v}: engine {self.engine} is newer than Cathode's ({ENGINE}); shows only")
        self.block = man.get("block") or None
        ads = man.get("ads") or None
        self.ads = ads if ads and ads.get("slices") else None
        self.plan = None
        if self.ads and self.bumps:
            gap = self.ads["gapMs"] if isinstance(self.ads.get("gapMs"), int) else AD_GAP
            self.plan = _AdPlan(self.ads["slices"], self.items, self.block, gap, self.cid[len(PREFIX):],
                                self.ads.get("start"), self.ads.get("decades"))
        self.ad_carry, self.deck_carry = {}, {}
        self.fwd, self.back, self.built = [], [], {}
        # The guide's listings are worked out off the UI thread while the
        # player asks what's on: the lazily built cycles take turns.
        self._lock = threading.RLock()

    # one cycle's entries, as the site's Ba/R0 build them
    def _cycle(self, k, cycle_start=None, season_at=None):
        first = self.first if k == 0 else 0
        items = self.items[first:] if first else self.items
        if not self.bumps:
            return [{"type": "video", "item": it, "durMs": it["duration"] * 1000} for it in items]
        name, seed = self.name, f"{self.v}.{k}"
        block, ads = self.block, self.ads
        slices = ads["slices"] if ads else None
        carry = (self.ad_carry.get(k) if k >= 1 else None) if slices else None
        used = {i for i, _ in (carry or {}).get("recent", []) if isinstance(i, int) and 0 <= i < len(slices or [])}
        since = carry.get("fromMs") if carry and isinstance(carry.get("fromMs"), int) else None
        took = []
        gap = ads["gapMs"] if ads and isinstance(ads.get("gapMs"), int) else AD_GAP
        deck = _deck_copy(self.deck_carry.get(k) if k >= 1 else None) if self.engine >= 5 else None
        f = cycle_start or 0
        d = since_ad = 0
        last_ad_end = None
        out = []
        for K, it in enumerate(items):
            U = first + K
            ms = it["duration"] * 1000
            out.append({"type": "video", "item": it, "durMs": ms})
            f += ms
            d += ms
            since_ad += ms
            if block and K < len(items) - 1 and d < block["lengthMs"]:
                st = _sting(block.get("stings") or [], U, name, seed)
                te = st["lengthMs"] if st else block["cardMs"]
                out.append({"type": "up-next", "sting": st, "durMs": te, "next": items[K + 1]})
                f += te
                d += te
                since_ad += te
                continue
            d = 0
            x = season_at if season_at is not None else f
            W = _deal(deck, self.bumps["channel"], name, seed, x) if deck else _pick(self.bumps["channel"], U, name, seed, x)
            Z = _pick(self.bumps["platform"], U, "spelunkr", seed, x)
            if not (W and Z):
                continue
            wa = _music(self.bumps["channel_audio"], W.get("id"), U, seed)
            nxt = items[K + 1] if K < len(items) - 1 else self.items[0]
            if slices and it.get("offAir") is not True and nxt.get("offAir") is not True and since_ad >= gap:
                ve = _choose_ad(self.plan, used, _year(it), f, since if since is not None else f - since_ad)
                since = None
                took.append([ve, f])
                ee = slices[ve]
                z = TITLE_MS + _slides_ms(W) + GAP_MS + HOLD_MS
                q = _slides_ms(Z) + GAP_MS + HOLD_MS
                out.append({"type": "bump", "half": "open", "bump": W, "audio": wa, "durMs": z})
                out.append({"type": "ad", "slice": ee, "durMs": ee["lengthMs"]})
                out.append({"type": "bump", "half": "close", "bump": Z,
                            "audio": _music(self.bumps["platform_audio"], Z.get("id"), U, seed), "durMs": q})
                f += z + ee["lengthMs"] + q
                since_ad = q
                last_ad_end = f
                continue
            we = _break_ms(W, Z)
            out.append({"type": "bump", "bump": W, "close": Z, "audio": wa, "durMs": we})
            f += we
            since_ad += we
        if slices and k >= 0 and (k + 1) not in self.ad_carry:
            # what the next cycle carries: where the last commercial break
            # ended (else where this one counted from), the day's commercials
            frm = last_ad_end if took else (since if since is not None else (cycle_start or 0))
            self.ad_carry[k + 1] = {"fromMs": frm,
                                    "recent": [r for r in (carry or {}).get("recent", []) + took if r[1] >= f - DAY]}
        if deck is not None and k >= 0 and (k + 1) not in self.deck_carry:
            self.deck_carry[k + 1] = {"order": deck["order"], "pos": deck["pos"], "key": deck["key"], "recent": deck["recent"]}
        return out

    def _span(self, k):
        """Cycle k's (start ms, length ms), cycles built in order."""
        if k >= 0:
            while len(self.fwd) <= k:
                s = self.fwd[-1][0] + self.fwd[-1][1] if self.fwd else self.epoch
                self.fwd.append((s, sum(e["durMs"] for e in self._cycle(len(self.fwd), cycle_start=s))))
            return self.fwd[k]
        while len(self.back) <= -k - 1:
            s = self.back[-1][0] if self.back else self.epoch
            n = sum(e["durMs"] for e in self._cycle(-(len(self.back) + 1), season_at=self.epoch))
            self.back.append((s - n, n))
        return self.back[-k - 1]

    def _index(self, t):
        if t >= self.epoch:
            if self.fwd and t < self.fwd[-1][0] + self.fwd[-1][1]:
                return bisect_right([s for s, _ in self.fwd], t) - 1
            i = len(self.fwd) - 1 if self.fwd else 0
            while True:
                s, n = self._span(i)
                if t < s + n:
                    return i
                i += 1
        k = -1
        while self._span(k)[0] > t:
            k -= 1
        return k

    def cycle(self, k):
        if k in self.built:
            return self.built[k]
        s, n = self._span(k)
        es = self._cycle(k, cycle_start=s) if k >= 0 else self._cycle(k, season_at=self.epoch)
        offs, o = [], 0
        for e in es:
            offs.append(o)
            o += e["durMs"]
        self.built[k] = (s, offs, es)
        if len(self.built) > 8:
            self.built.pop(next(iter(self.built)))
        return self.built[k]

    def at(self, t):
        """(entry, start ms, k, i) on at t ms."""
        with self._lock:
            k = self._index(t)
            s, offs, es = self.cycle(k)
            i = max(0, bisect_right(offs, t - s) - 1)
            return es[i], s + offs[i], k, i


class Schedule:
    """A Spelunkr channel's schedule over its versions, the face of
    videochannels.Schedule: the video channels' player, guide and stop
    timer drive it. Entries are shows, commercials and bumpers."""

    def __init__(self, cid: str, name: str, timelines: list, category: str):
        self.cid = cid
        self.c = {"id": cid, "name": name, "guide": "video", "card": True, "category": category}
        self.sources = []           # (the video channels' log line lists their sources)
        self.timelines = sorted(timelines, key=lambda tl: tl.v)
        self.dropped = set()

    @property
    def entries(self) -> list:
        return [it for tl in self.timelines for it in tl.items]

    def median(self) -> float:
        d = sorted(it["duration"] for it in self.entries)
        return d[len(d) // 2] if d else 0.0

    def _version(self, t):
        live = [tl for tl in self.timelines if tl.effective <= t]
        if live:
            return live[-1]
        return min(self.timelines, key=lambda tl: (tl.effective, -tl.v)) if self.timelines else None

    def at(self, now: datetime):
        """{"entry", "offset", "start", "stop"} on at `now` (UTC)."""
        t = now.timestamp() * 1000
        tl = self._version(t)
        if tl is None or not tl.items:
            return None
        e, start, k, i = tl.at(t)
        stop = start + e["durMs"]
        later = [x.effective for x in self.timelines if x.v > tl.v and x.effective > t]
        if later and min(later) < stop:          # a newer version takes over mid-way
            stop = min(later)
        entry = _entry(tl, e, k, i)
        return {"entry": entry, "offset": (t - start) / 1000,
                "start": datetime.fromtimestamp(start / 1000, timezone.utc),
                "stop": datetime.fromtimestamp(stop / 1000, timezone.utc)}

    def drop(self, video_id: str):
        """A file that won't play: noted, nothing moves (the timeline is the
        network's; the next due follows at its time)."""
        self.dropped.add(video_id)


def _entry(tl, e, k, i) -> dict:
    """A schedule entry as the player and guide take it."""
    key = f"{tl.v}:{k}:{i}"
    if e["type"] == "video":
        it = e["item"]
        name = it.get("file") or it.get("mp4") or ""
        return {"id": f"{it['id']}/{name}", "kind": "show", "url": FILES.format(it["id"], urllib.parse.quote(name)),
                "in": it.get("inS") or 0, "duration": e["durMs"] / 1000, "title": it.get("title") or name,
                "desc": it.get("_note", ""), "year": str(it.get("year") or "")}
    if e["type"] == "ad":
        sl = e["slice"]
        return {"id": f"ad:{key}", "kind": "ad", "url": FILES.format(sl["tape"], urllib.parse.quote(sl["file"])),
                "in": sl.get("inMs", 0) / 1000, "duration": e["durMs"] / 1000, "title": "Commercial break"}
    if e["type"] == "up-next":
        st = e.get("sting")
        nxt = e["next"]
        return {"id": f"next:{key}", "kind": "card", "duration": e["durMs"] / 1000, "title": "Up next",
                "url": tl.base_audio + urllib.parse.quote(st["track"]) if st else "", "in": (st or {}).get("startMs", 0) / 1000,
                "slides": [f"Up next: {nxt.get('title') or ''}"], "slide_ms": [e["durMs"]]}
    w, z = e["bump"], e.get("close")
    texts = [s.get("text", "") for s in w.get("slides") or []] + [s.get("text", "") for s in (z or {}).get("slides") or []]
    times = [_slide_ms(x) for x in texts]
    lead = TITLE_MS if e.get("half") != "close" else 0
    a = e.get("audio")
    return {"id": f"bump:{key}", "kind": "card", "duration": e["durMs"] / 1000, "title": "Spelunkr",
            "url": tl.base_audio + urllib.parse.quote(a["filename"]) if a and a.get("filename") else "",
            "in": (a or {}).get("startOffset", 0), "slides": texts, "slide_ms": times, "lead_ms": lead}


if __name__ == "__main__":         # ponytail: the one check; a live fetch, run by hand
    chans = channels()
    now = datetime.now(timezone.utc)
    for ch in chans[:5]:
        cur = SCHEDULES[ch.url[len(SCHEME):]].at(now)
        assert cur and cur["start"] <= now < cur["stop"], ch
        print(ch.number, ch.name, "|", cur["entry"]["kind"], cur["entry"]["title"], f"+{cur['offset']:.0f}s of {cur['entry']['duration']:.0f}")
