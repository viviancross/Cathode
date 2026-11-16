"""Jellyfin and Emby servers as library sources, beside Plex.

They speak nearly the same API. A server is signed into once with a user
name and password (the token kept, the password not); its libraries then
come into the index (library.py) the way Plex's do: this client answers
library_sections() and section_page() with rows shaped like Plex's, so the
index, channels and breaks need nothing of their own for it. A title's key
is "J<server>:<item id>" and its stream the server's file, sent as it is."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from typing import List, Optional

from .plex import PlexError

TIMEOUT = 20
KINDS = {"movies": "movie", "tvshows": "show", "music": "music", "homevideos": "clip", "musicvideos": "clip"}
TYPES = {1: "Movie", 2: "Series", 4: "Episode", 8: "MusicArtist", 10: "Audio"}
FIELDS = "Genres,Studios,OfficialRating,Overview,DateCreated,PremiereDate,ProductionYear,MediaSources"


def _auth_header(device_id: str) -> str:
    return f'MediaBrowser Client="Cathode", Device="Cathode", DeviceId="{device_id}", Version="5.0"'


def sign_in(url: str, user: str, password: str, device_id: str = "") -> dict:
    """{"url", "user", "user_id", "token", "name", "kind"} for a server, from
    its user name and password (which go no further)."""
    url = url.rstrip("/")
    device_id = device_id or uuid.uuid4().hex
    req = urllib.request.Request(f"{url}/Users/AuthenticateByName", method="POST",
                                 data=json.dumps({"Username": user, "Pw": password}).encode(),
                                 headers={"Content-Type": "application/json",
                                          "X-Emby-Authorization": _auth_header(device_id)})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        d = json.loads(r.read())
    info = {}
    try:
        with urllib.request.urlopen(f"{url}/System/Info/Public", timeout=TIMEOUT) as r:
            info = json.loads(r.read())
    except Exception:
        pass
    return {"url": url, "user": user, "user_id": d["User"]["Id"], "token": d["AccessToken"], "device": device_id,
            "name": info.get("ServerName") or url, "kind": "Emby" if "emby" in (info.get("ProductName") or "").lower()
            else "Jellyfin"}


class Client:
    """One Jellyfin or Emby server, its number n among them."""

    def __init__(self, n: int, server: dict):
        self.n, self.s = n, server
        self.url = server["url"].rstrip("/")

    def _get(self, path: str, **q):
        url = f"{self.url}{path}" + ("?" + urllib.parse.urlencode(q) if q else "")
        req = urllib.request.Request(url, headers={"X-Emby-Token": self.s["token"], "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read() or b"{}")

    def prefix(self) -> str:
        return f"j{self.n}_"

    def library_sections(self) -> List[dict]:
        out = []
        for v in self._get(f"/Users/{self.s['user_id']}/Views").get("Items") or []:
            kind = KINDS.get((v.get("CollectionType") or "").lower())
            if not kind:
                continue
            count = self._get(f"/Users/{self.s['user_id']}/Items", ParentId=v["Id"], Recursive="true",
                              Limit=0).get("TotalRecordCount", 0)
            out.append({"key": self.prefix() + v["Id"], "title": f"{v.get('Name', '?')} ({self.s.get('name', '')})",
                        "kind": kind, "stamp": str(count)})
        return out

    def section_page(self, key: str, type_: int, start: int, size: int) -> tuple:
        d = self._get(f"/Users/{self.s['user_id']}/Items", ParentId=key[len(self.prefix()):], Recursive="true",
                      IncludeItemTypes=TYPES[type_], Fields=FIELDS, StartIndex=start, Limit=size)
        return [self._row(i) for i in d.get("Items") or []], int(d.get("TotalRecordCount") or 0)

    def _key(self, item_id: str) -> str:
        return f"J{self.n}:{item_id}"

    def _row(self, i: dict) -> dict:
        """An item as Plex would have sent it."""
        t = i.get("Type")
        added = i.get("DateCreated") or ""
        try:
            added = int(datetime.fromisoformat(added[:19]).timestamp())
        except ValueError:
            added = 0
        row = {"ratingKey": self._key(i["Id"]), "title": i.get("Name") or "?", "year": i.get("ProductionYear") or 0,
               "Genre": [{"tag": g} for g in i.get("Genres") or []],
               "studio": ((i.get("Studios") or [{}])[0] or {}).get("Name", ""), "contentRating": i.get("OfficialRating") or "",
               "summary": i.get("Overview") or "", "addedAt": added,
               "thumb": f"{self.url}/Items/{i['Id']}/Images/Primary?maxHeight=450",
               "duration": int((i.get("RunTimeTicks") or 0) / 10000)}
        if t == "Episode":
            row.update(type="episode", grandparentRatingKey=self._key(i.get("SeriesId") or ""),
                       grandparentTitle=i.get("SeriesName") or "", parentIndex=i.get("ParentIndexNumber") or 0,
                       index=i.get("IndexNumber") or 0, originallyAvailableAt=(i.get("PremiereDate") or "")[:10])
        elif t == "Audio":
            artist = (i.get("AlbumArtists") or i.get("ArtistItems") or [{}])[0]
            row.update(type="track", grandparentRatingKey=self._key(artist.get("Id") or ""),
                       grandparentTitle=artist.get("Name") or i.get("AlbumArtist") or "", parentTitle=i.get("Album") or "",
                       index=i.get("IndexNumber") or 0, parentYear=i.get("ProductionYear") or 0,
                       parentThumb=f"{self.url}/Items/{i.get('AlbumId') or i['Id']}/Images/Primary?maxHeight=450")
        else:
            row["type"] = "movie"
        return row

    def stream_at(self, key: str, quality: str = "Original", at: float = 0.0) -> dict:
        """The file as it is (the player seeks to `at`)."""
        item_id = key.split(":", 1)[1]
        i = self._get(f"/Users/{self.s['user_id']}/Items/{item_id}", Fields="MediaSources")
        if not i.get("MediaSources") and i.get("Type") not in ("Audio",):
            raise PlexError("No playable file for this item.")
        kind = "Audio" if i.get("Type") == "Audio" else "Videos"
        return {"video": f"{self.url}/{kind}/{item_id}/stream?static=true", "headers": {"X-Emby-Token": self.s["token"]},
                "base": 0.0}


def clients(config) -> List[Client]:
    return [Client(n + 1, s) for n, s in enumerate(getattr(config, "media_servers", None) or []) if s.get("token")]


def for_key(app, key: str) -> Optional[Client]:
    n = int(key[1:].split(":", 1)[0] or 0)
    return next((c for c in clients(app.config) if c.n == n), None)
