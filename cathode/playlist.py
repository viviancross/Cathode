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
    number: float            # whole for most lineups; ErsatzTV numbers like 10.5 keep their part
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


# What a provider's panel answers to. Xtream panels refuse clients they
# don't know, with their own status codes (884, say), and most only answer
# to the players they expect; these are what those players send.
PLAYER_AGENTS = ["VLC/3.0.20 LibVLC/3.0.20", "TiviMate/4.7.0 (Android)", "IPTVSmarters/2.2.2", "okhttp/4.12.0"]


def _scrub(url: str) -> str:
    url = re.sub(r"^xtream://([^/]+)/[^/?]+/[^/?]+", lambda m: "xtream://" + m.group(1) + "/***/***", url)
    return re.sub(r"(username|password)=[^&]+", lambda m: m.group(1) + "=***",
                  re.sub(r"/playlist/[^/]+/[^/]+/", "/playlist/***/***/", url))


def link_variants(url: str) -> list:
    """The shapes one Xtream link can take: as given; type=m3u instead of
    m3u_plus (older panels); the /playlist/USER/PASS/m3u_plus path newer
    panels serve beside get.php. Only for a get.php link."""
    from urllib.parse import parse_qs, urlsplit, urlunsplit, urlencode
    u = urlsplit(url)
    if not u.path.lower().endswith("/get.php"):
        return [url]
    q = parse_qs(u.query)
    user, pw = (q.get("username") or [""])[0], (q.get("password") or [""])[0]
    if not user or not pw:
        return [url]
    out = [url]
    if (q.get("type") or [""])[0] != "m3u":
        q2 = {k: v[0] for k, v in q.items()}
        q2["type"] = "m3u"
        out.append(urlunsplit((u.scheme, u.netloc, u.path, urlencode(q2), "")))
    base = u.path[: -len("/get.php")]
    out.append(urlunsplit((u.scheme, u.netloc, f"{base}/playlist/{user}/{pw}/m3u_plus", "", "")))
    return out


def load_as(source: str, user_agent: str = "Cathode/1.0"):
    """load(), and the agent it took: a provider that refuses Cathode's own
    is tried with the agents real players send, and with the other shapes
    its link can take, so its playlist (and its guide and streams, with the
    same agent) still comes through. Returns (channels, user_agent, url):
    the url is the one that answered. Every attempt is logged, scrubbed."""
    import urllib.error
    if not source.startswith(("http://", "https://")):
        return load(source, user_agent), user_agent, source
    agents = [user_agent] + [a for a in PLAYER_AGENTS if a != user_agent]
    variants = link_variants(source)
    # A line's playlist refused in every shape: the panel's API, which the
    # apps providers expect use instead, often still answers (one such panel
    # answered 884 to get.php for everyone, and served Smarters by API).
    from . import servers
    prov = servers.xtream(source)
    if prov is not None:
        api = servers.xtream_api_url(prov.base, *prov.creds)
        try:
            chans = load(api, user_agent, timeout=20)
            print(f"[playlist] the panel's API answered where the playlist didn't: {_scrub(api)}")
            return chans, user_agent, api
        except Exception as e:
            print(f"[playlist] {_scrub(api)}: {e!r}"[:200])
    # The link's shapes first, with Cathode's own agent (a panel that refuses
    # get.php outright is found in three tries), then each shape as each
    # player. The search uses short timeouts: a refusal is quick, and a
    # dozen slow ones would be a long "Checking the address...".
    order = [(url, user_agent) for url in variants] + [(url, a) for a in agents[1:] for url in variants]
    last = None
    for url, agent in order:
        try:
            chans = load(url, agent, timeout=8)
            if url != source or agent != user_agent:
                print(f"[playlist] {_scrub(url)} answered to {agent!r}")
            return chans, agent, url
        except urllib.error.HTTPError as e:
            last = e
            print(f"[playlist] {_scrub(url)} as {agent!r}: HTTP {e.code}")
            if e.code == 404 and len(variants) == 1:
                raise                       # a plain link that isn't there: nothing to try
    raise last


def _chno(raw, auto: int):
    """tvg-chno as a number: whole when it is one, with its decimal part when
    the server numbers channels 10.1, 10.2 (ErsatzTV); the next free number
    when it's missing or not a number."""
    if raw is None:
        return auto
    s = str(raw).strip()
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return auto


def load(source: str, user_agent: str = "Cathode/1.0", timeout: float = 30) -> List[Channel]:
    """Load an M3U playlist from a file path or URL, or a line through a
    provider's API (an xtream:// address)."""
    if source.startswith("xtream://"):
        from . import servers
        line = servers.parse_xtream_api(source)
        if line is None:
            raise ValueError("not a line address")
        rows = servers.xtream_api_channels(*line, user_agent=user_agent, timeout=timeout)
        return [Channel(number=r["number"], name=_clean_name(r["name"]), url=r["url"], group=r["group"],
                        logo=r["logo"], epg_id=r["epg_id"]) for r in rows]
    if source.startswith(("http://", "https://", "rtsp://")):
        content = _fetch_url(source, user_agent, timeout)
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


def _fetch_url(url: str, user_agent: str, timeout: float = 30) -> str:
    # The headers a player sends with its agent: some panels look at these too.
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "*/*",
                                               "Accept-Encoding": "identity", "Connection": "keep-alive"})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as resp:
        return _decode(resp.read())


def _parse(content: str) -> List[Channel]:
    channels: List[Channel] = []
    lines = content.lstrip("\ufeff").splitlines()

    if not lines or not lines[0].strip().startswith("#EXTM3U"):
        # Try to parse even without proper header
        pass

    pending_meta: Optional[dict] = None
    auto_number = 1
    group_line = ""                     # an #EXTGRP: names the group of the entries after it

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#EXTM3U"):
            continue

        if line.startswith("#EXTINF:"):
            m = _EXTINF_RE.match(line)
            if m:
                attr_str, name = _split_attrs_name(m.group("rest"))
                attrs = _parse_attrs(attr_str)
                # A provider's list often leaves the name after the comma
                # empty and carries it in tvg-name, or puts attributes after
                # the comma; take the name where it is.
                name = _clean_name(name) or _clean_name(attrs.get("tvg-name", ""))
                if name:
                    if group_line and not attrs.get("group-title"):
                        attrs["group-title"] = group_line
                    pending_meta = {"name": name, "attrs": attrs}
            continue

        if line.startswith("#EXTGRP:"):
            group_line = line[len("#EXTGRP:"):].strip()
            continue

        if line.startswith("#"):
            continue

        # This is a URL/file line
        url = line
        if pending_meta:
            attrs = pending_meta["attrs"]
            name = pending_meta["name"]

            number = _chno(attrs.get("tvg-chno"), auto_number)

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
            auto_number = int(max(auto_number, number)) + 1
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
