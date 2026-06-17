"""M3U playlist parser."""

import re
import urllib.request
from dataclasses import dataclass
from typing import List, Optional


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


_EXTINF_RE = re.compile(
    r'#EXTINF:\s*-?\d+\s*'
    r'(?P<attrs>[^,]*)'
    r',\s*(?P<name>.+)'
)
_ATTR_RE = re.compile(r'(\S+?)="([^"]*)"')


def _parse_attrs(attr_str: str) -> dict:
    return dict(_ATTR_RE.findall(attr_str))


def load(source: str, user_agent: str = "Cathode/1.0") -> List[Channel]:
    """Load an M3U playlist from a file path or URL."""
    if source.startswith(("http://", "https://", "rtsp://")):
        content = _fetch_url(source, user_agent)
    else:
        with open(source, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    return _parse(content)


def _fetch_url(url: str, user_agent: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse(content: str) -> List[Channel]:
    channels: List[Channel] = []
    lines = content.splitlines()

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
                attrs = _parse_attrs(m.group("attrs"))
                name = m.group("name").strip()
                pending_meta = {
                    "name": name,
                    "attrs": attrs,
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
