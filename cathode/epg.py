"""XMLTV EPG parser."""

import xml.etree.ElementTree as ET
import urllib.request
import gzip
import os
import io
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import re

from .net import SSL as _SSL, as_seen_from
from .servers import parse_xtream_api, xtream_api_epg, xtream_epg_key, xtream_live_streams

# Lines whose API gave no listings at all this session: not asked again
# (a 20,000-channel line is 20,000 calls).
_API_EMPTY = set()


@dataclass
class Program:
    channel_id: str
    title: str
    start: datetime
    stop: datetime
    description: str = ""
    category: str = ""
    episode: str = ""
    rating: str = ""
    icon: str = ""           # the programme's poster, where the guide carries one (Tunarr does)
    # Cathode's own channels know more of a programme (NostalgiaTV's info line):
    air: str = ""            # first aired: "Nov 2, 2008"
    quality: str = ""        # SD, HD, 1080p, 4K
    audio: str = ""          # "AC3 Stereo"
    minutes: int = 0         # the programme's own length (not its slot)
    score: str = ""          # the audience's score, "7.4"
    logo: str = ""           # the show's title art (Plex's clear logo)
    art: str = ""            # the show's background art
    flag: str = ""           # "New", "Premiere"

    @property
    def duration_minutes(self) -> int:
        delta = self.stop - self.start
        return int(delta.total_seconds() / 60)

    def progress_at(self, now: datetime) -> float:
        """Return 0.0-1.0 how far through this program we are at `now`."""
        total = (self.stop - self.start).total_seconds()
        if total <= 0:
            return 0.0
        elapsed = (now - self.start).total_seconds()
        return max(0.0, min(1.0, elapsed / total))


# XMLTV datetime formats
_DT_FORMATS = [
    "%Y%m%d%H%M%S %z",
    "%Y%m%d%H%M%S",
    "%Y%m%d%H%M %z",
    "%Y%m%d%H%M",
]


def _parse_xmltv_dt(s: str) -> datetime:
    s = s.strip()
    for fmt in _DT_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    # Fallback: strip timezone suffix and try again
    m = re.match(r"(\d{14})\s*([+-]\d{4})?", s)
    if m:
        base, tz_str = m.group(1), m.group(2)
        dt = datetime.strptime(base, "%Y%m%d%H%M%S")
        if tz_str:
            sign = 1 if tz_str[0] == "+" else -1
            h, mn = int(tz_str[1:3]), int(tz_str[3:5])
            offset = timedelta(hours=h, minutes=mn) * sign
            dt = dt.replace(tzinfo=timezone(offset))
        else:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    raise ValueError(f"Cannot parse XMLTV datetime: {s!r}")


def _from_ns(ns: str) -> str:
    """xmltv_ns "0.29." (counted from nought) -> "S1E30"."""
    parts = (ns.split(".") + ["", ""])[:2]
    try:
        s, e = (int(p.split("/")[0]) + 1 if p.strip() else 0 for p in parts)
    except ValueError:
        return ""
    return f"S{s}E{e}" if s and e else (f"E{e}" if e else "")


def _air(s: str) -> str:
    """XMLTV's <date> ("19980903040000 +0000", "1998-09-03", "1998") ->
    "Sep 3, 1998", or the year alone."""
    digits = re.sub(r"\D", "", (s or "").split(" ")[0])
    try:
        if len(digits) >= 8:
            d = datetime.strptime(digits[:8], "%Y%m%d")
            return f"{d:%b} {d.day}, {d.year}"
    except ValueError:
        return ""
    return digits[:4] if len(digits) >= 4 else ""


def _text(el: Optional[ET.Element], tag: str, default: str = "") -> str:
    child = el.find(tag) if el is not None else None
    if child is not None and child.text:
        return child.text.strip()
    return default


# Only programmes overlapping [now - KEEP_BEHIND, now + KEEP_AHEAD] are kept:
# the guide shows a few hours ahead, and a provider's week of listings for a
# thousand channels is most of a gigabyte held for nothing. The app reloads
# well inside KEEP_AHEAD, so the guide never runs off the end.
KEEP_BEHIND = timedelta(hours=3)
KEEP_AHEAD = timedelta(hours=36)
# A ceiling on what a guide can make us hold, whatever its size on the wire:
# a gzip bomb of valid listings would otherwise decode straight into memory.
MAX_PROGRAMMES = 500_000


class _Counted(io.RawIOBase):
    """A source read through, counting bytes for a progress callback."""

    def __init__(self, raw, total, cb):
        self._raw, self._total, self._cb = raw, total, cb
        self._done, self._pct = 0, -1
        if not total:
            cb(None)

    def readable(self):
        return True

    def readinto(self, b):
        data = self._raw.read(len(b))
        n = len(data)
        b[:n] = data
        self._done += n
        if self._total:
            pct = min(100, self._done * 100 // self._total)
            if pct != self._pct:
                self._pct = pct
                self._cb(pct / 100)
        return n


class EPG:
    """Holds EPG data indexed by channel ID."""

    def __init__(self):
        # channel_id -> list of Program, sorted by start
        self._programs: Dict[str, List[Program]] = {}
        # display-name -> channel_id mapping from XMLTV <channel> elements
        self._display_names: Dict[str, str] = {}
        # channel_id -> logo URL from <channel><icon src="..."/>
        self._icons: Dict[str, str] = {}
        self._window = None     # (earliest stop, latest start) kept; None = all
        self._count = 0

    def load(self, source: str, user_agent: str = "Cathode/1.0",
             now: Optional[datetime] = None, progress=None):
        """Parse an XMLTV file or URL, gzipped or not, straight off the wire:
        neither the download nor its decompressed form is ever held whole.
        progress(fraction) hears how much of the source has been read, as
        each whole percent passes; progress(None) once when the size is
        unknown."""
        now = now or datetime.now(timezone.utc)
        self._window = (now - KEEP_BEHIND, now + KEEP_AHEAD)
        self._source = source       # icons written as the server's own "localhost" mean it
        line = parse_xtream_api(source)
        if line:
            return self._load_line(line, user_agent, progress)
        if source.startswith(("http://", "https://")):
            raw, total = self._open(source, user_agent)
        else:
            raw = open(source, "rb")
            total = os.path.getsize(source)
        self._read(raw, total, progress)

    def _load_line(self, line, user_agent, progress):
        """A provider line: its XMLTV guide when the panel serves one, else
        every channel's programmes through the API, which panels tend to
        leave open while locking xmltv.php."""
        from urllib.parse import urlencode
        base, user, pw = line
        self._source = base
        try:
            raw, total = self._open(f"{base}/xmltv.php?" + urlencode({"username": user, "password": pw}), user_agent)
            self._read(raw, total, progress)
        except (OSError, ET.ParseError) as e:
            print(f"[cathode] guide: the provider's xmltv.php didn't answer ({e!r})")
        # The channels the XMLTV left out (all of them when it didn't answer,
        # or when its ids aren't the ones the channel list carries) through
        # the API, one call each.
        streams = xtream_live_streams(base, user, pw, user_agent)
        left = [s for s in streams if not self.resolve_channel_id(xtream_epg_key(s), str(s.get("name", "")))]
        print(f"[cathode] guide: the provider's XMLTV covers {len(streams) - len(left)} of {len(streams)} channels")
        if not left or base in _API_EMPTY:
            return
        self.__dict__.pop("_resolved", None)
        rows = xtream_api_epg(base, user, pw, user_agent, progress=progress, streams=left)
        print(f"[cathode] guide: the provider's API listed {len(rows)} of the other {len(left)}")
        if not rows:
            _API_EMPTY.add(base)
        w0, w1 = self._window
        for key, progs in rows.items():
            self.add_programs(key, [
                Program(channel_id=key, title=t[:200], description=d[:1500],
                        start=datetime.fromtimestamp(a, timezone.utc), stop=datetime.fromtimestamp(b, timezone.utc))
                for a, b, t, d in progs
                if not (datetime.fromtimestamp(b, timezone.utc) <= w0 or datetime.fromtimestamp(a, timezone.utc) >= w1)])

    @staticmethod
    def _open(url, user_agent):
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        raw = urllib.request.urlopen(req, timeout=30, context=_SSL)
        return raw, int(raw.headers.get("Content-Length") or 0)

    def _read(self, raw, total, progress):
        with raw:
            f = io.BufferedReader(_Counted(raw, total, progress) if progress else raw)
            if f.peek(2)[:2] == b"\x1f\x8b":
                f = gzip.GzipFile(fileobj=f)
            self._parse_stream(f)

    def _parse_stream(self, fileobj):
        """Stream-parse XMLTV with iterparse, clearing elements as they finish,
        so a huge guide (100MB+) never balloons into a full DOM in RAM."""
        root = None
        for event, el in ET.iterparse(fileobj, events=("start", "end")):
            if event == "start":
                if root is None:
                    root = el
                continue
            if el.tag == "channel":
                self._parse_channel(el)
            elif el.tag == "programme":
                self._parse_programme(el)
                if self._count >= MAX_PROGRAMMES:
                    break       # keep what we have rather than run out of RAM
            else:
                continue        # sub-elements are freed with their parent
            el.clear()
            if root is not None:
                root.clear()    # drop finished children so the tree stays flat

        # Sort each channel's programs by start time
        for progs in self._programs.values():
            progs.sort(key=lambda p: p.start)

    def _parse_channel(self, ch_el: ET.Element):
        """Channel display names + logo icon from one <channel> element."""
        ch_id = ch_el.get("id", "")
        for dn_el in ch_el.findall("display-name"):
            if dn_el.text:
                self._display_names[dn_el.text.strip().lower()] = ch_id
        icon_el = ch_el.find("icon")
        if icon_el is not None:
            src = icon_el.get("src", "").strip()
            if src and ch_id:
                self._icons[ch_id] = as_seen_from(src, getattr(self, "_source", ""))

    def _parse_programme(self, prog_el: ET.Element):
        """One <programme> element -> a Program in the channel's bucket."""
        ch_id = prog_el.get("channel", "")
        start_str = prog_el.get("start", "")
        stop_str = prog_el.get("stop", "")
        if not (ch_id and start_str and stop_str):
            return
        try:
            start = _parse_xmltv_dt(start_str)
            stop = _parse_xmltv_dt(stop_str)
        except ValueError:
            return
        if self._window and (stop <= self._window[0] or start >= self._window[1]):
            return
        self._count += 1

        title = _text(prog_el, "title")[:200]
        desc = _text(prog_el, "desc")[:1500]
        category = _text(prog_el, "category")[:60]

        # Episode number, and its own title: "S1E30 - Thunder 30" as
        # NostalgiaTV writes it (Tunarr sends both).
        ep_nums = prog_el.findall("episode-num")
        episode = ""
        for ep in ep_nums:
            if ep.get("system") == "onscreen":
                episode = ep.text.strip() if ep.text else ""
                break
        if not episode and ep_nums:
            episode = ep_nums[0].text.strip() if ep_nums[0].text else ""
        if ep_nums and ep_nums[0].get("system") == "xmltv_ns" and episode == (ep_nums[0].text or "").strip():
            episode = _from_ns(episode)
        episode = re.sub(r"\bS0*(\d+)\s*E0*(\d+)\b", r"S\1E\2", episode, flags=re.I)
        sub = _text(prog_el, "sub-title")[:120]
        if sub and sub != title:
            episode = f"{episode} - {sub}" if episode else sub
        air = _air(_text(prog_el, "date"))
        length = prog_el.find("length")
        try:
            n = float(length.text) if length is not None and length.text else 0
        except ValueError:
            n = 0
        unit = (length.get("units") if length is not None else "") or "seconds"
        minutes = round(n * {"seconds": 1 / 60, "minutes": 1, "hours": 60}.get(unit, 0))
        quality = "HD" if _text(prog_el, "video/quality").upper().startswith("HD") else ""
        flag = "New" if prog_el.find("new") is not None else ""

        rating = ""
        rating_el = prog_el.find("rating/value")
        if rating_el is not None and rating_el.text:
            rating = rating_el.text.strip()

        icon_el = prog_el.find("icon")
        icon = (icon_el.get("src") or "").strip() if icon_el is not None else ""
        if not icon:                        # Tunarr also writes <image type="poster">
            for im in prog_el.findall("image"):
                if (im.get("type") or "poster") == "poster" and im.text:
                    icon = im.text.strip()
                    break
        if icon:
            icon = as_seen_from(icon, getattr(self, "_source", ""))

        self._programs.setdefault(ch_id, []).append(Program(
            channel_id=ch_id,
            title=title,
            start=start,
            stop=stop,
            description=desc,
            category=category,
            episode=episode,
            rating=rating,
            icon=icon,
            air=air,
            minutes=minutes,
            quality=quality,
            flag=flag,
        ))

    def add_programs(self, channel_id: str, programs: List[Program]):
        """Inject programs for a channel (used by demo mode)."""
        bucket = self._programs.setdefault(channel_id, [])
        bucket.extend(programs)
        bucket.sort(key=lambda p: p.start)
        self.__dict__.pop("_resolved", None)
        self.__dict__.pop("_last_stop", None)

    def set_programs(self, channel_id: str, programs: List[Program]):
        """A channel's programmes, replacing any it had (Cathode's own channels)."""
        self._programs[channel_id] = sorted(programs, key=lambda p: p.start)
        self.__dict__.pop("_resolved", None)
        self.__dict__.pop("_last_stop", None)

    def resolve_channel_id(self, epg_id: str, channel_name: str) -> Optional[str]:
        """Return the XMLTV channel ID for a given M3U channel. Memoised: the
        fuzzy fallback scans every display name, and the guide asks per row
        per frame (categories ask for every channel at once)."""
        key = (epg_id, channel_name)
        memo = self.__dict__.setdefault("_resolved", {})
        if key not in memo:
            memo[key] = self._resolve(epg_id, channel_name)
        return memo[key]

    def last_stop(self) -> Optional[datetime]:
        """When the last programme in the guide data ends."""
        if "_last_stop" not in self.__dict__:
            stops = [progs[-1].stop for progs in self._programs.values() if progs]
            self._last_stop = max(stops) if stops else None
        return self._last_stop

    def _resolve(self, epg_id: str, channel_name: str) -> Optional[str]:
        if epg_id and epg_id in self._programs:
            return epg_id
        if channel_name.lower() in self._display_names:
            cid = self._display_names[channel_name.lower()]
            if cid in self._programs:
                return cid
        # Fuzzy match
        name_lower = channel_name.lower()
        for dn, cid in self._display_names.items():
            if name_lower in dn or dn in name_lower:
                if cid in self._programs:
                    return cid
        return None

    def current_program(self, channel_id: str, now: Optional[datetime] = None) -> Optional[Program]:
        if now is None:
            now = datetime.now(timezone.utc)
        progs = self._programs.get(channel_id, [])
        for prog in progs:
            if prog.start <= now < prog.stop:
                return prog
        return None

    def next_program(self, channel_id: str, now: Optional[datetime] = None) -> Optional[Program]:
        if now is None:
            now = datetime.now(timezone.utc)
        progs = self._programs.get(channel_id, [])
        for prog in progs:
            if prog.start > now:
                return prog
        return None

    def programs_in_window(
        self,
        channel_id: str,
        start: datetime,
        end: datetime,
    ) -> List[Program]:
        progs = self._programs.get(channel_id, [])
        return [p for p in progs if p.stop > start and p.start < end]

    def icon_url(self, channel_id: str) -> str:
        """The XMLTV <icon> URL for a channel, or '' if none."""
        return self._icons.get(channel_id, "") if channel_id else ""

    def dominant_category(self, channel_id: str) -> str:
        """The most common programme <category> for a channel (its 'genre'),
        used to sort channels into guide categories.  '' if none."""
        from collections import Counter
        counts = Counter(p.category.strip() for p in self._programs.get(channel_id, [])
                         if p.category and p.category.strip())
        if not counts:
            return ""
        return counts.most_common(1)[0][0]

    @property
    def channel_ids(self):
        return list(self._programs.keys())

