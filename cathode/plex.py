"""Minimal Plex client for Plex-Per-View.

Talks to plex.tv (sign-in + server discovery) and a Plex Media Server (library
browsing + direct-play URLs) over plain HTTP with JSON responses. No SDK, no
third-party deps — just urllib + json.

Sign-in uses the PIN/link flow: request a code, the user enters it at
plex.tv/link, then we poll until a token comes back. The token is reused on later
launches. Playback hands mpv the server's direct file URL with the token in the
query string, plus the saved resume offset.
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import List, Optional

PLEX_TV = "https://plex.tv"
LINK_URL = "https://plex.tv/link"
_TIMEOUT = 15


def _ssl_context() -> ssl.SSLContext:
    # macOS Python often ships without a usable CA bundle, so HTTPS to plex.tv
    # fails verification. Use certifi's bundle when present.
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


_SSL = _ssl_context()

# Transcode quality presets shown in Plex Options. "Original" = direct play (no
# transcode, max quality); the rest cap the video bitrate (kbps).
QUALITY_OPTIONS = ["Original", "1080p (20 Mbps)", "720p (4 Mbps)", "480p (2 Mbps)"]
_QUALITY = {"1080p (20 Mbps)": 20000, "720p (4 Mbps)": 4000, "480p (2 Mbps)": 2000}


def new_client_id() -> str:
    return uuid.uuid4().hex


class PlexError(Exception):
    pass


class PlexClient:
    def __init__(self, client_id: str, token: str = "", admin_token: str = "",
                 product: str = "Cathode", version: str = "1.0"):
        self.client_id = client_id or new_client_id()
        self.token = token or ""           # effective token (selected home user)
        self.admin_token = admin_token or token or ""   # account token (home mgmt)
        self.product = product
        self.version = version
        self.server = ""          # chosen server base URL
        self._server_token = ""   # token to use against that server

    # ── HTTP ──────────────────────────────────────────────────────────────

    def _headers(self, token: Optional[str] = None) -> dict:
        h = {
            "Accept": "application/json",
            "X-Plex-Product": self.product,
            "X-Plex-Version": self.version,
            "X-Plex-Client-Identifier": self.client_id,
            "X-Plex-Device": "Cathode",
            "X-Plex-Device-Name": "Cathode",
            "X-Plex-Platform": "Cathode",
        }
        tok = token if token is not None else self.token
        if tok:
            h["X-Plex-Token"] = tok
        return h

    def _get(self, url: str, token: Optional[str] = None,
             timeout: float = _TIMEOUT) -> dict:
        req = urllib.request.Request(url, headers=self._headers(token))
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
            return json.loads(r.read() or b"{}")

    def _post(self, url: str) -> dict:
        req = urllib.request.Request(url, data=b"", method="POST",
                                     headers=self._headers())
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_SSL) as r:
            return json.loads(r.read() or b"{}")

    # ── PIN sign-in ───────────────────────────────────────────────────────

    def request_pin(self) -> dict:
        """Start the link flow. Returns {id, code, link} — show the code and
        link to the user, then call poll_pin(id) until it returns a token.
        The default (non-strong) pin is the short 4-character plex.tv/link code."""
        data = self._post(f"{PLEX_TV}/api/v2/pins")
        return {"id": data.get("id"), "code": data.get("code", ""),
                "link": LINK_URL}

    def poll_pin(self, pin_id) -> Optional[str]:
        """Return the auth token once the user has entered the code, else None."""
        data = self._get(f"{PLEX_TV}/api/v2/pins/{pin_id}")
        token = data.get("authToken")
        if token:
            self.token = token
        return token

    # ── server discovery ──────────────────────────────────────────────────

    def discover_server(self) -> str:
        """Find a reachable Plex Media Server and remember it. Returns its base
        URL, or raises PlexError. Prefers a local connection, then remote.

        Candidates are probed in parallel with a short timeout so a dead remote
        / relay address can't stall the whole connect for 15s each in series."""
        url = (f"{PLEX_TV}/api/v2/resources"
               "?includeHttps=1&includeRelay=1")
        data = self._get(url)
        resources = data if isinstance(data, list) else data.get("resources", [])
        servers = [r for r in resources
                   if "server" in (r.get("provides") or "")]
        if not servers:
            raise PlexError("No Plex Media Server is linked to this account.")
        # Build a preference-ordered candidate list: owned servers first, and
        # within each, local connections before remote before relay.
        servers.sort(key=lambda r: 0 if r.get("owned") else 1)
        candidates = []   # (uri, token) in descending preference
        for r in servers:
            conns = sorted(r.get("connections") or [],
                           key=lambda c: 0 if c.get("local") else
                           (2 if c.get("relay") else 1))
            tok = r.get("accessToken") or self.token
            for c in conns:
                if c.get("uri"):
                    candidates.append((c["uri"], tok))
        hit = self._first_reachable(candidates)
        if hit:
            self.server, self._server_token = hit
            return hit[0]
        raise PlexError("Couldn't connect to your Plex server.")

    def _first_reachable(self, candidates, timeout: float = 5):
        """Probe candidates concurrently; return the most-preferred (earliest in
        the list) that responds, not merely the fastest. (uri, token) or None."""
        if not candidates:
            return None
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(8, len(candidates))) as ex:
            futs = [ex.submit(self._reachable, uri, tok, timeout)
                    for uri, tok in candidates]
            for (uri, tok), f in zip(candidates, futs):
                try:
                    if f.result():
                        return (uri, tok)
                except Exception:
                    pass
        return None

    def _reachable(self, uri: str, token: str, timeout: float = _TIMEOUT) -> bool:
        try:
            self._get(f"{uri}/identity", token=token, timeout=timeout)
            return True
        except Exception:
            return False

    # ── library browsing ──────────────────────────────────────────────────

    def sections(self) -> List[dict]:
        data = self._get(f"{self.server}/library/sections",
                         token=self._server_token)
        out = []
        for d in _container(data, "Directory"):
            # Include movie / show / homevideo (other videos). Music + photos
            # are out of scope for Plex-Per-View.
            if d.get("type") in ("movie", "show", "homevideo"):
                out.append({"key": d.get("key"), "title": d.get("title", "?"),
                            "type": d.get("type"), "agent": d.get("agent", "")})
        return out

    @staticmethod
    def _join(path: str, sort: str = "") -> str:
        if not sort:
            return path
        return f"{path}{'&' if '?' in path else '?'}sort={sort}"

    def section_items(self, key: str, sort: str = "") -> List[dict]:
        data = self._get(self._join(
            f"{self.server}/library/sections/{key}/all", sort),
            token=self._server_token)
        return [_meta_row(m) for m in _container(data, "Metadata")]

    def is_other_videos(self, section: dict) -> bool:
        """Home-video / 'Other Videos' libraries support folder browsing."""
        return "none" in (section.get("agent") or "")

    def folder_items(self, path: str, section: str = "") -> List[dict]:
        """A folder's contents in an Other Videos library: nested folders +
        videos.

        Plex returns subfolders as Directory entries and video files as Metadata
        carrying a Media/Part. Some servers also return folder-like Metadata with
        no playable part — treat anything non-playable as a folder so selecting
        it descends via the folder endpoint, NOT /library/metadata/{id}/children
        (which 404s for a folder and surfaced as "HTTP Error 404: Not Found").
        `section` is the library section key, used to rebuild a folder URL when
        Plex hands back a relative or bare key."""
        url = self._abs_url(path)
        try:
            data = self._get(url, token=self._server_token)
        except urllib.error.HTTPError as e:
            raise PlexError(f"Folder unavailable ({e.code}).")
        rows = []
        for d in _container(data, "Directory"):
            rows.append({"type": "folder", "folder": self._folder_url(section, d),
                         "section": section,
                         "title": d.get("title") or d.get("name", "?"),
                         "meta": "", "playable": False})
        for m in _container(data, "Metadata"):
            row = _meta_row(m)
            if row["playable"]:
                rows.append(row)
            else:
                rows.append({"type": "folder",
                             "folder": self._folder_url(section, m),
                             "section": section,
                             "title": row["title"], "meta": "", "playable": False})
        return rows

    def _folder_url(self, section: str, node: dict) -> str:
        """URL that lists a folder node's contents. Use an absolute key Plex
        already gave us; otherwise rebuild from the section + the node's id as
        /library/sections/{section}/folder?parent={id}."""
        k = node.get("key") or ""
        if k.startswith("http") or k.startswith("/"):
            return k
        if "parent=" in k:                       # relative 'folder?parent=123'
            return f"/library/sections/{section}/folder?{k.split('?', 1)[-1]}"
        rid = (k.rstrip("/").split("/")[-1] if k else "") \
            or str(node.get("ratingKey") or node.get("id") or "")
        return f"/library/sections/{section}/folder?parent={rid}"

    def _abs_url(self, path: str) -> str:
        """Resolve a Plex `key`/path to an absolute URL against the server."""
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.server}{path}"

    def watchlist(self, sort: str = "") -> List[dict]:
        """The account watchlist (Plex Discover). Items carry a guid to resolve
        against the server when played. Tries the discover host first, then
        falls back to metadata."""
        extra = f"&sort={sort}" if sort else ""
        urls = [
            "https://discover.provider.plex.tv/library/sections/watchlist/all"
            "?includeCollections=1&includeExternalMedia=1" + extra,
            "https://metadata.provider.plex.tv/library/sections/watchlist/all"
            "?includeCollections=1&includeExternalMedia=1" + extra,
        ]
        # Use the ACCOUNT token (self.admin_token), not the per-server token.
        last = None
        for url in urls:
            try:
                data = self._get(url, token=self.admin_token or self.token)
                break
            except Exception as e:
                last = e
                data = None
        if data is None:
            raise PlexError(str(last) if last else "Couldn't load watchlist.")
        rows = []
        for m in _container(data, "Metadata"):
            row = _meta_row(m)
            row["watchlist"] = True
            row["guid"] = m.get("guid", "")
            rows.append(row)
        return rows

    def find_on_server(self, guid: str) -> Optional[str]:
        """Resolve a Discover guid to a ratingKey on the connected server.

        Uses the cross-library `/library/all?guid=` match (one request for the
        whole server) instead of querying every section in turn. Tries the full
        guid first, then its trailing metadata id, since server vs Discover
        guids share the id but not always the full string."""
        if not guid:
            return None
        gid = guid.rstrip("/").split("/")[-1]
        for q in (guid, gid):
            if not q:
                continue
            try:
                url = (f"{self.server}/library/all?"
                       + urllib.parse.urlencode({"guid": q}))
                items = _container(self._get(url, token=self._server_token),
                                   "Metadata")
                if items:
                    return str(items[0].get("ratingKey"))
            except Exception:
                pass
        return None

    def children(self, rating_key: str, sort: str = "") -> List[dict]:
        url = f"{self.server}/library/metadata/{rating_key}/children"
        if sort:
            url += f"?sort={sort}"
        data = self._get(url, token=self._server_token)
        return [_meta_row(m) for m in _container(data, "Metadata")]

    def genres(self, section_key: str) -> List[dict]:
        """Genres for a Movies/TV library: [{id, title}]. The genre `id` is the
        filter value to pass back as `?genre=<id>` on the library's /all."""
        data = self._get(f"{self.server}/library/sections/{section_key}/genre",
                         token=self._server_token)
        out = []
        for d in _container(data, "Directory"):
            # key may be a bare id ("9"), a path (".../genre/9"), or carry a
            # query (".../all?genre=9") — pull the trailing id out of any form.
            gid = d.get("key", "").rstrip("/").split("/")[-1].split("=")[-1]
            if gid:
                out.append({"id": gid, "title": d.get("title", "?")})
        return out

    def section_filter(self, section_key: str, genre_id: str = "",
                       sort: str = "") -> List[dict]:
        """Library /all filtered by genre (and optionally sorted)."""
        # Plex wants `sort=year:desc` literally; urlencode would mangle the ':'.
        parts = []
        if genre_id:
            parts.append(f"genre={urllib.parse.quote(genre_id)}")
        if sort:
            parts.append(f"sort={sort}")
        q = ("?" + "&".join(parts)) if parts else ""
        data = self._get(f"{self.server}/library/sections/{section_key}/all{q}",
                         token=self._server_token)
        return [_meta_row(m) for m in _container(data, "Metadata")]

    def item_detail(self, rating_key: str) -> dict:
        """Full metadata for the info screen."""
        data = self._get(f"{self.server}/library/metadata/{rating_key}",
                         token=self._server_token)
        items = _container(data, "Metadata")
        if not items:
            raise PlexError("This item is no longer available.")
        m = items[0]
        title, subtitle = _display_title(m)
        thumb = (m.get("thumb") or m.get("grandparentThumb")
                 or m.get("parentThumb") or "")
        # Clean URL; the token rides in a header (poster_headers) so it stays out
        # of the URL string and the image cache key.
        poster = f"{self.server}{thumb}" if thumb else ""
        return {
            "rating_key": rating_key, "title": title, "subtitle": subtitle,
            "summary": m.get("summary", ""), "duration": int(m.get("duration", 0)) // 1000,
            "offset": int(m.get("viewOffset", 0)) // 1000, "poster": poster,
            "poster_headers": {"X-Plex-Token": self._server_token} if poster else {},
            "guid": m.get("guid", ""), "type": m.get("type", ""),
        }

    def all_episodes(self, show_rating_key: str) -> List[str]:
        """Ordered rating_keys for every episode in a show (flattened seasons)."""
        url = f"{self.server}/library/metadata/{show_rating_key}/allLeaves"
        data = self._get(url, token=self._server_token)
        return [str(m.get("ratingKey")) for m in _container(data, "Metadata")
                if m.get("ratingKey") is not None]

    def watchlist_set(self, guid: str, add: bool = True) -> bool:
        """Add/remove an item (by its plex:// guid) from the account watchlist.
        The actions live on the Discover provider; fall back to metadata host."""
        rk = guid.rstrip("/").split("/")[-1] if guid else ""
        if not rk:
            return False
        action = "addToWatchlist" if add else "removeFromWatchlist"
        tok = self.admin_token or self.token
        for host in ("https://discover.provider.plex.tv",
                     "https://metadata.provider.plex.tv"):
            url = f"{host}/actions/{action}?ratingKey={rk}&X-Plex-Token={tok}"
            try:
                req = urllib.request.Request(url, method="PUT",
                                             headers=self._headers(token=tok))
                urllib.request.urlopen(req, timeout=_TIMEOUT, context=_SSL)
                return True
            except Exception:
                continue
        return False

    # ── home users (Plex Home) ────────────────────────────────────────────

    def home_users(self) -> List[dict]:
        """The Plex Home users on this account (empty if not a Home / on error)."""
        data = self._get(f"{PLEX_TV}/api/v2/home/users", token=self.admin_token)
        users = data if isinstance(data, list) else data.get("users", [])
        out = []
        for u in users:
            out.append({"uuid": str(u.get("uuid") or u.get("id") or ""),
                        "title": u.get("title") or u.get("username") or "User",
                        "protected": bool(u.get("protected") or u.get("hasPassword"))})
        return [u for u in out if u["uuid"]]

    def switch_user(self, uuid: str) -> str:
        """Switch to a Home user; returns that user's auth token (or '')."""
        data = self._post(
            f"{PLEX_TV}/api/v2/home/users/{uuid}/switch", token=self.admin_token)
        token = data.get("authToken") or data.get("authentication_token") or ""
        if token:
            self.token = token
        return token

    # ── playback ──────────────────────────────────────────────────────────

    def play_info(self, rating_key: str, quality: str = "Original") -> dict:
        """Fresh metadata for one item: {url, offset, title, subtitle}.
        Direct play unless a transcode `quality` preset is given."""
        data = self._get(f"{self.server}/library/metadata/{rating_key}",
                         token=self._server_token)
        items = _container(data, "Metadata")
        if not items:
            raise PlexError("This item is no longer available.")
        m = items[0]
        part = _first_part(m)
        if not part:
            raise PlexError("No playable file for this item.")
        offset = int(m.get("viewOffset", 0)) // 1000   # ms -> s
        title, subtitle = _display_title(m)
        kbps = _QUALITY.get(quality)
        if kbps:
            url = self._transcode_url(rating_key, kbps, offset)
            offset = 0          # the transcoder already starts at the offset
        else:
            url = f"{self.server}{part}"
        # Auth travels in a header, not the URL query, so the token never lands
        # in mpv's log file. The caller passes these to the player.
        return {"url": url, "offset": offset, "title": title,
                "subtitle": subtitle,
                "headers": {"X-Plex-Token": self._server_token}}

    def report_timeline(self, rating_key: str, time_s: float, duration_s: float,
                        state: str = "stopped"):
        """Tell the server the current playback position so it saves (or clears,
        when finished) the resume point. Best-effort."""
        try:
            q = urllib.parse.urlencode({
                "ratingKey": rating_key,
                "key": f"/library/metadata/{rating_key}",
                "state": state,
                "time": int(max(0, time_s) * 1000),
                "duration": int(max(0, duration_s) * 1000),
                "X-Plex-Token": self._server_token,
                "X-Plex-Client-Identifier": self.client_id,
            })
            self._get(f"{self.server}/:/timeline?{q}", token=self._server_token)
        except Exception:
            pass

    def _transcode_url(self, rating_key: str, kbps: int, offset: int) -> str:
        # Token is sent as a header (see play_info), not in the query string.
        q = urllib.parse.urlencode({
            "path": f"/library/metadata/{rating_key}",
            "protocol": "hls", "fastSeek": "1",
            "directPlay": "0", "directStream": "1",
            "maxVideoBitrate": str(kbps), "videoQuality": "100",
            "offset": str(offset),
            "mediaIndex": "0", "partIndex": "0",
            "X-Plex-Client-Identifier": self.client_id,
            "X-Plex-Session-Identifier": self.client_id,
        })
        return f"{self.server}/video/:/transcode/universal/start.m3u8?{q}"


# ── JSON helpers ──────────────────────────────────────────────────────────

def _container(data: dict, key: str) -> list:
    mc = data.get("MediaContainer", {}) if isinstance(data, dict) else {}
    val = mc.get(key, [])
    return val if isinstance(val, list) else []


def _first_part(meta: dict) -> Optional[str]:
    for media in meta.get("Media", []) or []:
        for part in media.get("Part", []) or []:
            if part.get("key"):
                return part["key"]
    return None


def _display_title(m: dict) -> tuple:
    """(title, subtitle) for the playback bar — show name for episodes."""
    if m.get("type") == "episode":
        show = m.get("grandparentTitle") or m.get("title", "?")
        s, e = m.get("parentIndex"), m.get("index")
        tag = f"S{int(s):d}E{int(e):d}" if s is not None and e is not None else ""
        return show, f"{tag}  {m.get('title', '')}".strip()
    bits = []
    if m.get("year"):
        bits.append(str(m["year"]))
    if m.get("contentRating"):
        bits.append(str(m["contentRating"]))
    if m.get("rating"):
        bits.append(f"{float(m['rating']):.1f}")
    return m.get("title", "?"), "   ".join(bits)


def _meta_row(m: dict) -> dict:
    """Normalize a Metadata entry into a browse row."""
    typ = m.get("type", "")
    title = m.get("title", "?")
    if typ == "episode":
        s, e = m.get("parentIndex"), m.get("index")
        if s is not None and e is not None:
            title = f"S{int(s):d}E{int(e):d}  {title}"
    elif typ == "season":
        title = m.get("title") or f"Season {m.get('index', '?')}"
    bits = []
    if m.get("year"):
        bits.append(str(m["year"]))
    if m.get("contentRating"):
        bits.append(str(m["contentRating"]))
    if m.get("rating"):
        bits.append(f"{float(m['rating']):.1f}")
    if m.get("leafCount"):
        bits.append(f"{m['leafCount']} eps")
    # Anything carrying a Media/Part is a playable file — covers Other Videos
    # whose items are type "clip"/"" rather than movie/episode. (Selecting a
    # non-playable item routes to /children, which 404s for a leaf file.)
    playable = typ in ("movie", "episode", "clip") or bool(m.get("Media"))
    return {"type": typ, "rating_key": str(m.get("ratingKey", "")),
            "title": title, "meta": "   ".join(bits),
            "playable": playable,
            "offset": int(m.get("viewOffset", 0)) // 1000}   # resume point (s)
