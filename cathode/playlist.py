"""M3U playlist parser."""

import html
import re
import unicodedata
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

from .net import SSL as _SSL, as_seen_from


@dataclass
class Channel:
    number: int
    name: str
    url: str
    group: str = ""
    logo: str = ""
    epg_id: str = ""
    language: str = ""

    def __str__(self):
        return f"[{self.number}] {self.name}"


_EXTINF_RE = re.compile(r'#EXTINF:\s*-?[\d.]+\s*(?P<rest>.*)')
_ATTR_RE = re.compile(r'(\S+?)="([^"]*)"')


def _parse_attrs(attr_str: str) -> dict:
    return dict(_ATTR_RE.findall(attr_str))


def _split_attrs_name(rest: str):
    """Split the EXTINF remainder into (attrs, name) at the first comma that
    sits OUTSIDE double quotes — attr values may themselves contain commas
    (e.g. group-title="News, Local")."""
    in_quotes = False
    for i, c in enumerate(rest):
        if c == '"':
            in_quotes = not in_quotes
        elif c == "," and not in_quotes:
            return rest[:i], rest[i + 1:].strip()
    return rest, ""


def load(source: str, user_agent: str = "Cathode/1.0") -> List[Channel]:
    """Load an M3U playlist from a file path or URL."""
    if source.startswith(("http://", "https://", "rtsp://")):
        content = _fetch_url(source, user_agent)
    else:
        with open(source, "rb") as f:
            content = _decode(f.read())
    channels = _parse(content)
    for ch in channels:
        ch.logo = as_seen_from(ch.logo, source)
    return channels


def _decode(raw: bytes) -> str:
    """UTF-8 (a BOM is fine), else Windows-1252, the other encoding
    playlists turn up in."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _clean_name(name: str) -> str:
    """A channel name as written for people: entities decoded, control
    characters dropped, a runaway name cut."""
    name = html.unescape(name)
    name = "".join(" " if ch.isspace() else ch for ch in name if ch.isspace() or unicodedata.category(ch)[0] != "C")
    return " ".join(name.split())[:120]


def _fetch_url(url: str, user_agent: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=30, context=_SSL) as resp:
        return _decode(resp.read())


def _parse(content: str) -> List[Channel]:
    channels: List[Channel] = []
    lines = content.lstrip("\ufeff").splitlines()

    if not lines or not lines[0].strip().startswith("#EXTM3U"):
        # Try to parse even without proper header
        pass

    pending_meta: Optional[dict] = None
    auto_number = 1

    for line in lines:
        line = line.strip()
        if not line or line == "#EXTM3U":
            continue

        if line.startswith("#EXTINF:"):
            m = _EXTINF_RE.match(line)
            if m:
                attr_str, name = _split_attrs_name(m.group("rest"))
                name = _clean_name(name)
                if name:
                    pending_meta = {
                        "name": name,
                        "attrs": _parse_attrs(attr_str),
                    }
            continue

        if line.startswith("#"):
            continue

        # This is a URL/file line
        url = line
        if pending_meta:
            attrs = pending_meta["attrs"]
            name = pending_meta["name"]

            # Try to get explicit channel number
            try:
                number = int(attrs.get("tvg-chno", auto_number))
            except (ValueError, TypeError):
                number = auto_number

            ch = Channel(
                number=number,
                name=name,
                url=url,
                group=attrs.get("group-title", ""),
                logo=attrs.get("tvg-logo", ""),
                epg_id=attrs.get("tvg-id", ""),
                language=attrs.get("tvg-language", ""),
            )
            channels.append(ch)
            auto_number = max(auto_number, number) + 1
            pending_meta = None
        else:
            # Bare URL with no metadata
            ch = Channel(
                number=auto_number,
                name=f"Channel {auto_number}",
                url=url,
            )
            channels.append(ch)
            auto_number += 1

    # Sort by channel number, renumber sequentially if numbers are sparse
    channels.sort(key=lambda c: c.number)
    # Assign stable sequential indices (keep original numbers as display numbers)
    return channels
