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
NAMES = {"tunarr": "Tunarr", "ersatztv": "ErsatzTV", "xtream": "IPTV provider"}


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
        if self.kind == "xtream":
            return self.playlist
        return self.base + PATHS[self.kind]["playlist"]

    @property
    def epg_url(self) -> str:
        if self.kind == "xtream":
            from urllib.parse import urlencode
            user, pw = self.creds
            return f"{self.base}/xmltv.php?{urlencode({'username': user, 'password': pw})}"
        return self.base + PATHS[self.kind]["epg"]

    def __str__(self) -> str:
        if self.kind == "xtream":
            return f"{self.name} at {urlsplit(self.base).hostname}"
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


# ── Xtream Codes providers: the "M3U Plus" link ───────────────────────────
# Most IPTV providers hand out one link in this shape:
#   http://host:port/get.php?username=U&password=P&type=m3u_plus&output=ts
# The same host serves the guide at xmltv.php with the same credentials.

def xtream(url: str) -> Optional[Server]:
    """The Xtream provider behind an M3U Plus link, or None. Its playlist
    URL is the link as given (output and type kept), its guide the host's
    xmltv.php with the same username and password."""
    from urllib.parse import parse_qs
    try:
        u = urlsplit((url or "").strip())
    except ValueError:
        return None
    if not u.hostname or not u.path.lower().endswith("/get.php"):
        return None
    q = parse_qs(u.query)
    user, pw = (q.get("username") or [""])[0], (q.get("password") or [""])[0]
    if not user or not pw:
        return None
    base = urlunsplit((u.scheme or "http", u.netloc, u.path[: -len("/get.php")], "", ""))
    s = Server("xtream", base, "")
    s.playlist = url.strip()
    s.creds = (user, pw)
    return s


def xtream_api_url(base: str, user: str, pw: str) -> str:
    """Cathode's own address for a line fetched through the panel's API
    (xtream://host:port/USER/PASS); what the playlist loader recognises."""
    u = urlsplit(base)
    return f"xtream://{u.netloc}/{user}/{pw}" + (f"?scheme={u.scheme}" if u.scheme == "https" else "")


def parse_xtream_api(url: str):
    """(base, user, pw) from an xtream:// address, or None."""
    from urllib.parse import parse_qs
    u = urlsplit(url or "")
    if u.scheme != "xtream" or not u.netloc:
        return None
    parts = u.path.strip("/").split("/")
    if len(parts) != 2 or not all(parts):
        return None
    scheme = (parse_qs(u.query).get("scheme") or ["http"])[0]
    return f"{scheme}://{u.netloc}", parts[0], parts[1]


def xtream_api_channels(base: str, user: str, pw: str, user_agent: str = "Cathode", timeout: float = 30) -> list:
    """The live channels of a line, from the panel's API (player_api.php),
    as the playlist loader's dicts: name, url, group, logo, epg_id, number.
    The API is what IPTV Smarters and TiviMate use; some panels serve it
    while refusing the M3U playlist."""
    from urllib.parse import urlencode

    def get(action: str):
        q = urlencode({"username": user, "password": pw, **({"action": action} if action else {})})
        req = urllib.request.Request(f"{base}/player_api.php?{q}",
                                     headers={"User-Agent": user_agent, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=timeout, context=SSL) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))

    info = get("")
    auth = (info or {}).get("user_info", {}) if isinstance(info, dict) else {}
    if str(auth.get("auth", "1")) == "0" or str(auth.get("status", "Active")).lower() not in ("active", ""):
        raise PermissionError(f"the provider says this line is {auth.get('status') or 'not accepted'}")
    ext = (info.get("server_info", {}) or {}).get("output_formats") if isinstance(info, dict) else None
    fmt = "ts" if not ext or "ts" in ext else ext[0]
    cats = {str(c.get("category_id")): c.get("category_name", "") for c in (get("get_live_categories") or [])
            if isinstance(c, dict)}
    out = []
    for n, s in enumerate(get("get_live_streams") or [], start=1):
        if not isinstance(s, dict) or not s.get("stream_id"):
            continue
        sid = s["stream_id"]
        out.append({"number": int(s.get("num") or n), "name": str(s.get("name", "")).strip() or f"Channel {sid}",
                    "url": f"{base}/live/{user}/{pw}/{sid}.{fmt}",
                    "group": cats.get(str(s.get("category_id")), ""), "logo": s.get("stream_icon") or "",
                    "epg_id": xtream_epg_key(s)})
    return out


def xtream_epg_key(stream: dict) -> str:
    """What a stream's programmes are filed under: the panel's EPG id, or
    the stream id when it has none, so the API guide still lines up."""
    return str(stream.get("epg_channel_id") or "") or f"xtream:{stream.get('stream_id')}"


def _xtream_get(base: str, user: str, pw: str, user_agent: str, timeout: float, action: str, **extra):
    from urllib.parse import urlencode
    q = urlencode({"username": user, "password": pw, "action": action, **extra})
    req = urllib.request.Request(f"{base}/player_api.php?{q}",
                                 headers={"User-Agent": user_agent, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def xtream_live_streams(base: str, user: str, pw: str, user_agent: str = "Cathode", timeout: float = 30) -> list:
    """The line's live streams as the panel lists them (dicts with stream_id,
    name, epg_channel_id...)."""
    rows = _xtream_get(base, user, pw, user_agent, timeout, "get_live_streams") or []
    return [s for s in rows if isinstance(s, dict) and s.get("stream_id")]


def xtream_api_epg(base: str, user: str, pw: str, user_agent: str = "Cathode", timeout: float = 30,
                   progress=None, workers: int = 12, streams=None) -> dict:
    """The programmes of a line's live channels (all of them, or `streams`)
    through the panel's API: one get_simple_data_table call per channel, a
    few at a time, for channels the panel's XMLTV leaves out or when it
    locks xmltv.php altogether. {epg key: [(start unix, stop unix, title,
    description)]}, keyed as xtream_epg_key does. A channel whose call
    fails just has no guide."""
    from base64 import b64decode
    from concurrent.futures import ThreadPoolExecutor

    def get(action: str, **extra):
        return _xtream_get(base, user, pw, user_agent, timeout, action, **extra)

    def text(v) -> str:
        s = str(v or "")
        try:                            # panels base64 their titles; some don't
            return b64decode(s, validate=True).decode("utf-8", "replace") if s else ""
        except ValueError:
            return s

    def one(s: dict):
        try:
            rows = get("get_simple_data_table", stream_id=s["stream_id"])
        except (OSError, ValueError):
            return s, []
        rows = rows.get("epg_listings") if isinstance(rows, dict) else rows
        progs = []
        for r in rows if isinstance(rows, list) else []:
            try:
                a, b = int(r["start_timestamp"]), int(r["stop_timestamp"])
            except (KeyError, TypeError, ValueError):
                continue
            if b > a:
                progs.append((a, b, text(r.get("title")), text(r.get("description"))))
        return s, progs

    if streams is None:
        streams = xtream_live_streams(base, user, pw, user_agent, timeout)
    out, done = {}, 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for s, progs in pool.map(one, streams):
            done += 1
            if progs:
                out[xtream_epg_key(s)] = progs
            if progress and (done % 25 == 0 or done == len(streams)):
                progress(done / len(streams))
    return out


def _local_ip() -> str:
    """This machine's address on the LAN (the route a packet to the outside
    would take; nothing is sent)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


def scan_lan(user_agent: str = "Cathode", connect_timeout: float = 0.25, workers: int = 128) -> list:
    """Tunarr and ErsatzTV servers on this machine's /24: a quick connect to
    each host's known ports, then the version question of whatever answers.
    [Server, ...] nearest-first by address; [] off a network."""
    import socket
    from concurrent.futures import ThreadPoolExecutor
    # Every /24 this machine sits on (a Deck on Wi-Fi, a PC with a VPN or
    # Docker adapter too), the default route's first.
    ips = [_local_ip()]
    try:
        ips += [a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        pass
    nets = []
    for ip in ips:
        if ip and not ip.startswith(("127.", "169.254.")) and ip.rsplit(".", 1)[0] not in nets:
            nets.append(ip.rsplit(".", 1)[0])
    hosts = [f"{net}.{i}" for net in nets[:4] for i in range(1, 255)]
    if not hosts:
        return []

    def listening(host):
        hits = []
        for port in PORTS:
            try:
                with socket.create_connection((host, port), connect_timeout):
                    hits.append(f"http://{host}:{port}")
            except OSError:
                pass
        return hits

    with ThreadPoolExecutor(max_workers=workers) as pool:
        candidates = [addr for hits in pool.map(listening, hosts) for addr in hits]
    # The same server shows up once per adapter it's reachable through (a
    # PC running Tunarr sees itself on its LAN, VPN, Tailscale and WSL
    # addresses): keep one per server, the plainest home address first.
    candidates.sort(key=_address_rank)
    found, seen = [], set()
    for addr in candidates:
        try:
            server = detect(addr, user_agent=user_agent, timeout=3.0)
        except Exception:
            server = None
        if server is not None and (server.kind, server.version) not in seen:
            seen.add((server.kind, server.version))
            found.append(server)
    return found


def _address_rank(addr: str) -> int:
    """Home LAN ranges first (192.168, 10.0), other private 10.x next, then
    Docker/WSL's 172.16-31 and Tailscale's 100.64-127 last."""
    host = urlsplit(addr).hostname or ""
    if host.startswith(("192.168.", "10.0.")):
        return 0
    if host.startswith("10."):
        return 1
    if host.startswith("172.") and 16 <= int(host.split(".")[1] or 0) <= 31:
        return 2
    if host.startswith("100.") and 64 <= int(host.split(".")[1] or 0) <= 127:
        return 3
    return 4


def looks_like_address(text: str) -> bool:
    """A bare host or host:port rather than a playlist file or link: worth
    asking the server what it is."""
    t = (text or "").strip()
    if not t:
        return False
    u = urlsplit(t if "://" in t else "http://" + t)
    return bool(u.hostname) and u.path in ("", "/") and not u.query
