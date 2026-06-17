"""XMLTV EPG parser."""

import xml.etree.ElementTree as ET
import urllib.request
import gzip
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import re


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


def _text(el: Optional[ET.Element], tag: str, default: str = "") -> str:
    child = el.find(tag) if el is not None else None
    if child is not None and child.text:
        return child.text.strip()
    return default


class EPG:
    """Holds EPG data indexed by channel ID."""

    def __init__(self):
        # channel_id -> list of Program, sorted by start
        self._programs: Dict[str, List[Program]] = {}
        # display-name -> channel_id mapping from XMLTV <channel> elements
        self._display_names: Dict[str, str] = {}
        # channel_id -> logo URL from <channel><icon src="..."/>
        self._icons: Dict[str, str] = {}

    def load(self, source: str, user_agent: str = "Cathode/1.0"):
        if source.startswith(("http://", "https://")):
            data = _fetch(source, user_agent)
        else:
            with open(source, "rb") as f:
                data = f.read()

        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)

        root = ET.fromstring(data)
        self._parse(root)

    def _parse(self, root: ET.Element):
        # Parse channel display names + logo icons
        for ch_el in root.findall("channel"):
            ch_id = ch_el.get("id", "")
            for dn_el in ch_el.findall("display-name"):
                if dn_el.text:
                    self._display_names[dn_el.text.strip().lower()] = ch_id
            icon_el = ch_el.find("icon")
            if icon_el is not None:
                src = icon_el.get("src", "").strip()
                if src and ch_id:
                    self._icons[ch_id] = src

        # Parse programmes
        for prog_el in root.findall("programme"):
            ch_id = prog_el.get("channel", "")
            start_str = prog_el.get("start", "")
            stop_str = prog_el.get("stop", "")
            if not (ch_id and start_str and stop_str):
                continue
            try:
                start = _parse_xmltv_dt(start_str)
                stop = _parse_xmltv_dt(stop_str)
            except ValueError:
                continue

            title = _text(prog_el, "title")
            desc = _text(prog_el, "desc")
            category = _text(prog_el, "category")

            # Episode number
            ep_nums = prog_el.findall("episode-num")
            episode = ""
            for ep in ep_nums:
                if ep.get("system") == "onscreen":
                    episode = ep.text.strip() if ep.text else ""
                    break
            if not episode and ep_nums:
                episode = ep_nums[0].text.strip() if ep_nums[0].text else ""

            rating = ""
            rating_el = prog_el.find("rating/value")
            if rating_el is not None and rating_el.text:
                rating = rating_el.text.strip()

            prog = Program(
                channel_id=ch_id,
                title=title,
                start=start,
                stop=stop,
                description=desc,
                category=category,
                episode=episode,
                rating=rating,
            )
            self._programs.setdefault(ch_id, []).append(prog)

        # Sort each channel's programs by start time
        for progs in self._programs.values():
            progs.sort(key=lambda p: p.start)

    def add_programs(self, channel_id: str, programs: List[Program]):
        """Inject programs for a channel (used by demo mode)."""
        bucket = self._programs.setdefault(channel_id, [])
        bucket.extend(programs)
        bucket.sort(key=lambda p: p.start)

    def resolve_channel_id(self, epg_id: str, channel_name: str) -> Optional[str]:
        """Return the XMLTV channel ID for a given M3U channel."""
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


def _fetch(url: str, user_agent: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()
