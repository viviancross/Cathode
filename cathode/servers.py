"""The channel servers Cathode is built for: Tunarr and ErsatzTV. Given one
address, which it is, its version, and where its playlist and guide are, so
setup asks for one thing and the box "finds its signal" from there.

Detection is one request: GET {base}/api/version. Tunarr answers
{"tunarr": "2026.10.1", ...}; ErsatzTV {"appVersion": "v26.11.3", ...}.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from .net import SSL

# Default ports, tried when the address names none: Tunarr's, then ErsatzTV's.
PORTS = (8000, 8409)

PATHS = {
    "tunarr": {"playlist": "/api/channels.m3u", "epg": "/api/xmltv.xml"},
    # ErsatzTV: the segmenter mode is the one its Next engine serves; the
    # legacy modes are rewritten to it since 26.11.
    "ersatztv": {"playlist": "/iptv/channels.m3u?mode=segmenter", "epg": "/iptv/xmltv.xml"},
}
NAMES = {"tunarr": "Tunarr", "ersatztv": "ErsatzTV"}


@dataclass
class Server:
    kind: str           # "tunarr" | "ersatztv"
    base: str           # "http://10.0.0.215:8000", no trailing slash
    version: str

    @property
    def name(self) -> str:
        return NAMES[self.kind]

    @property
    def playlist_url(self) -> str:
        return self.base + PATHS[self.kind]["playlist"]

    @property
    def epg_url(self) -> str:
        return self.base + PATHS[self.kind]["epg"]

    def __str__(self) -> str:
        return f"{self.name} {self.version}".strip()


def normalise(address: str) -> str:
    """What someone types ('10.0.0.215:8000', 'tunarr.local', a full URL)
    as a base: a scheme, no path, no trailing slash."""
    a = (address or "").strip().rstrip("/")
    if not a:
        return ""
    if "://" not in a:
        a = "http://" + a
    u = urlsplit(a)
    return urlunsplit((u.scheme, u.netloc, "", "", ""))


def candidates(address: str) -> list:
    """The bases to try for an address: as typed, then with each default
    port when none was given."""
    base = normalise(address)
    if not base:
        return []
    out = [base]
    if not urlsplit(base).port:
        u = urlsplit(base)
        out += [urlunsplit((u.scheme, f"{u.hostname}:{p}", "", "", "")) for p in PORTS]
    return out


def identify(data) -> Optional[tuple]:
    """(kind, version) from an /api/version body, or None if it's neither."""
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("tunarr"), str):
        return "tunarr", data["tunarr"]
    if isinstance(data.get("appVersion"), str):
        return "ersatztv", data["appVersion"].lstrip("v")
    return None


def _version(base: str, user_agent: str, timeout: float):
    req = urllib.request.Request(base + "/api/version", headers={"User-Agent": user_agent, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL) as resp:
        return json.loads(resp.read(65536).decode("utf-8", "replace"))


def detect(address: str, user_agent: str = "Cathode", timeout: float = 4.0) -> Optional[Server]:
    """The server at an address, or None when nothing there answers like
    one (a plain M3U host, a typo, nothing listening)."""
    for base in candidates(address):
        try:
            found = identify(_version(base, user_agent, timeout))
        except (urllib.error.URLError, OSError, ValueError):
            continue
        if found:
            return Server(found[0], base, found[1])
    return None


def looks_like_address(text: str) -> bool:
    """A bare host or host:port rather than a playlist file or link: worth
    asking the server what it is."""
    t = (text or "").strip()
    if not t:
        return False
    u = urlsplit(t if "://" in t else "http://" + t)
    return bool(u.hostname) and u.path in ("", "/") and not u.query
