"""The library index: everything the Plex server holds, compact, on disk.

Library channels (libchannels.py) are made from it: which titles are a
comedy, from the '90s, from one studio; each show's episodes in order. One
file per Plex library in the cache folder, fetched 2000 rows at a time off
the UI thread and again only when the server says that library changed.

A title is a dict the channels play as it is: id, plex (its rating key),
type (movie, episode, clip), title (a show's name for an episode), name (the
episode's own), duration in seconds, year, genres, studio, rating, summary,
thumb, added, and for an episode show_key, season, episode, air. Episodes
take their genres, studio and rating from their show."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Optional

from . import paths

VERSION = 2                     # 2: quality, audio, score, air dates, title art
PAGE = 2000
SUMMARY = 160 if getattr(paths, "LOW_POWER", False) else 400     # characters of a summary kept (a TV box's memory: fewer)
QUALITY = {"4K": 4, "1080p": 3, "HD": 2, "SD": 1}
BREAK_MEDIAN = 150          # an Other Videos library of clips shorter than this (median) is break material


AUDIO = {"aac": "AAC", "ac3": "AC3", "eac3": "EAC3", "mp3": "MP3", "dca": "DTS", "dts": "DTS", "truehd": "TrueHD",
         "flac": "FLAC", "opus": "Opus", "vorbis": "Vorbis", "mp2": "MP2", "pcm": "PCM"}
CHANNELS = {1: "Mono", 2: "Stereo", 6: "5.1", 8: "7.1"}


def _media(m: dict) -> tuple:
    """(quality, audio) of an item's first file: ("HD", "AC3 Stereo")."""
    md = (m.get("Media") or [{}])[0] or {}
    res = str(md.get("videoResolution") or "").lower()
    q = {"720": "HD", "1080": "1080p", "4k": "4K", "2160": "4K"}.get(res, "SD" if res else "")
    codec = AUDIO.get(str(md.get("audioCodec") or "").lower(), str(md.get("audioCodec") or "").upper())
    ch = CHANNELS.get(int(md.get("audioChannels") or 0), "")
    return q, " ".join(x for x in (codec, ch) if x)


def _image(m: dict, kind: str) -> str:
    return next((i.get("url", "") for i in m.get("Image") or [] if i.get("type") == kind), "")


def _score(m: dict) -> str:
    try:
        v = float(m.get("audienceRating") or m.get("rating") or 0)
    except (TypeError, ValueError):
        return ""
    return f"{v:.1f}" if v else ""


def _dir() -> str:
    d = os.path.join(paths.cache_dir(), "library")
    os.makedirs(d, exist_ok=True)
    return d


class Section:
    """One Plex library: its titles, and its shows by rating key."""

    def __init__(self, key, title: str, kind: str, stamp: str = ""):
        self.key, self.title, self.kind, self.stamp = str(key), title, kind, stamp
        self.items: list = []
        self.shows: dict = {}
        self.fetched = 0.0
        self.hidden = False         # hidden from On Demand in the settings: no channel takes it unasked

    @property
    def breaks(self) -> bool:
        """Bumpers and commercials, not programmes: an Other Videos library
        whose clips are short."""
        if self.kind != "clip" or not self.items:
            return False
        d = sorted(i["duration"] for i in self.items)
        return d[len(d) // 2] < BREAK_MEDIAN

    # ── Rows, as the server sends them ────────────────────────────────────

    def add_show(self, m: dict):
        self.shows[str(m.get("ratingKey"))] = {
            "key": str(m.get("ratingKey")), "title": m.get("title", "?"), "year": int(m.get("year") or 0),
            "genres": [g.get("tag", "") for g in m.get("Genre", []) or []], "studio": m.get("studio") or "",
            "rating": m.get("contentRating") or "", "thumb": m.get("thumb") or "",
            "summary": (m.get("summary") or "")[:SUMMARY], "logo": _image(m, "clearLogo"),
            "art": m.get("art") or _image(m, "background")}

    def add_item(self, m: dict):
        dur = int(m.get("duration") or 0) / 1000
        if dur <= 0:
            return
        rk = str(m.get("ratingKey"))
        if m.get("type") == "track":        # a music library's: its artist is its "show"
            artist = self.shows.get(str(m.get("grandparentRatingKey"))) or {}
            self.items.append({
                "id": "p" + rk, "plex": rk, "type": "track", "title": m.get("grandparentTitle") or artist.get("title", "?"),
                "name": m.get("title") or "", "album": m.get("parentTitle") or "", "duration": dur,
                "year": int(m.get("parentYear") or m.get("year") or 0), "genres": artist.get("genres", []), "studio": "",
                "rating": "", "summary": "", "thumb": m.get("parentThumb") or artist.get("thumb", ""),
                "added": int(m.get("addedAt") or 0), "show_key": str(m.get("grandparentRatingKey")), "season": 0,
                "episode": int(m.get("index") or 0), "air": ""})
            return
        q, au = _media(m)
        if m.get("type") == "episode":
            show = self.shows.get(str(m.get("grandparentRatingKey"))) or {}
            self.items.append({
                "q": q, "au": au, "score": _score(m), "logo": show.get("logo", ""), "art": show.get("art", ""),
                "id": "p" + rk, "plex": rk, "type": "episode", "title": m.get("grandparentTitle") or show.get("title", "?"),
                "name": m.get("title") or "", "duration": dur, "year": int(m.get("year") or show.get("year") or 0),
                "genres": show.get("genres", []), "studio": show.get("studio", ""),
                "rating": m.get("contentRating") or show.get("rating", ""),
                "summary": (m.get("summary") or "")[:SUMMARY], "thumb": show.get("thumb") or m.get("grandparentThumb") or "",
                "added": int(m.get("addedAt") or 0), "show_key": str(m.get("grandparentRatingKey")),
                "season": int(m.get("parentIndex") or 0), "episode": int(m.get("index") or 0),
                "air": m.get("originallyAvailableAt") or ""})
        else:
            self.items.append({
                "q": q, "au": au, "score": _score(m), "air": m.get("originallyAvailableAt") or "",
                "logo": _image(m, "clearLogo"), "art": m.get("art") or "",
                "id": "p" + rk, "plex": rk, "type": "clip" if self.kind == "clip" else "movie",
                "title": m.get("title", "?"), "name": "", "duration": dur, "year": int(m.get("year") or 0),
                "genres": [g.get("tag", "") for g in m.get("Genre", []) or []], "studio": m.get("studio") or "",
                "rating": m.get("contentRating") or "", "summary": (m.get("summary") or "")[:SUMMARY],
                "thumb": m.get("thumb") or "", "added": int(m.get("addedAt") or 0)})

    # ── On disk ───────────────────────────────────────────────────────────

    def path(self) -> str:
        return os.path.join(_dir(), f"section-{self.key}.json")

    def save(self):
        """Episodes leave what their show carries to the show's row."""
        rows = []
        for i in self.items:
            if i["type"] == "track":
                rows.append([i["plex"], i["show_key"], i["episode"], i["name"], i["album"], i["duration"], i["year"],
                             i["thumb"], i["added"], i["title"]])
            elif i["type"] == "episode":
                rows.append([i["plex"], i["show_key"], i["season"], i["episode"], i["name"], i["duration"], i["air"],
                             i["summary"], i["added"], i["title"], i["rating"], i.get("q", ""), i.get("au", ""),
                             i.get("score", "")])
            else:
                rows.append([i["plex"], i["title"], i["duration"], i["year"], i["genres"], i["studio"], i["rating"],
                             i["summary"], i["thumb"], i["added"], i.get("q", ""), i.get("au", ""), i.get("score", ""),
                             i.get("air", ""), i.get("logo", ""), i.get("art", "")])
        data = {"v": VERSION, "key": self.key, "title": self.title, "kind": self.kind, "stamp": self.stamp,
                "fetched": self.fetched, "shows": list(self.shows.values()), "rows": rows}
        tmp = self.path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp, self.path())

    @classmethod
    def load(cls, key) -> Optional["Section"]:
        try:
            with open(os.path.join(_dir(), f"section-{key}.json"), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return None
        if d.get("v") != VERSION:
            return None
        s = cls(d["key"], d["title"], d["kind"], d.get("stamp", ""))
        s.fetched = d.get("fetched", 0.0)
        s.shows = {sh["key"]: sh for sh in d.get("shows", [])}
        for r in d.get("rows", []):
            if s.kind == "music":
                artist = s.shows.get(r[1]) or {}
                s.items.append({"id": "p" + r[0], "plex": r[0], "type": "track", "title": r[9], "name": r[3],
                                "album": r[4], "duration": r[5], "year": r[6], "genres": artist.get("genres", []),
                                "studio": "", "rating": "", "summary": "", "thumb": r[7], "added": r[8], "show_key": r[1],
                                "season": 0, "episode": r[2], "air": ""})
            elif s.kind == "show":
                show = s.shows.get(r[1]) or {}
                s.items.append({"id": "p" + r[0], "plex": r[0], "type": "episode", "title": r[9], "name": r[4],
                                "duration": r[5], "year": show.get("year", 0), "genres": show.get("genres", []),
                                "studio": show.get("studio", ""), "rating": r[10], "summary": r[7],
                                "thumb": show.get("thumb", ""), "added": r[8], "show_key": r[1], "season": r[2],
                                "episode": r[3], "air": r[6], "q": r[11], "au": r[12], "score": r[13],
                                "logo": show.get("logo", ""), "art": show.get("art", "")})
            else:
                s.items.append({"id": "p" + r[0], "plex": r[0], "type": "clip" if s.kind == "clip" else "movie",
                                "title": r[1], "name": "", "duration": r[2], "year": r[3], "genres": r[4],
                                "studio": r[5], "rating": r[6], "summary": r[7], "thumb": r[8], "added": r[9],
                                "q": r[10], "au": r[11], "score": r[12], "air": r[13], "logo": r[14], "art": r[15]})
        return s


class Index:
    """Every library in hand, by section key."""

    def __init__(self, sections=()):
        self.sections = {s.key: s for s in sections}
        self._by_id = None
        self.collections: dict = {}     # Plex's: key -> {title, section, keys}
        self.playlists: dict = {}       # Plex's video playlists: key -> {title, keys}
        self.watched: set = set()       # rating keys of what's been watched

    def programme_sections(self) -> list:
        """The libraries channels are made from unasked: not the bumpers and
        commercials, not the ones hidden in the settings."""
        return [s for s in self.sections.values() if not s.breaks and not s.hidden]

    def item(self, item_id: str) -> Optional[dict]:
        if self._by_id is None:
            self._by_id = {i["id"]: i for s in self.sections.values() for i in s.items}
        return self._by_id.get(item_id)

    def stamp(self, keys=None) -> str:
        """Changes when any of these libraries (all of them, by default) does."""
        return "|".join(f"{k}={s.stamp}" for k, s in sorted(self.sections.items()) if keys is None or k in keys)

    def count(self) -> int:
        return sum(len(s.items) for s in self.sections.values())

    def dedupe(self, prefer: str = "plex"):
        """A film or episode in two places is kept once: from the first place
        (Plex, then Jellyfin and Emby, then folders), or with prefer
        "quality" the better picture (4K, 1080p, HD, SD), the first place on
        a tie. Clips are never folded together."""
        def rank(sec):
            return 0 if sec.key[:1].isdigit() else 1 if sec.key.startswith("j") else 2

        def key(i):
            if i["type"] == "episode":
                return ("e", i["title"].lower(), i["season"], i["episode"])
            if i["type"] == "movie":
                return ("m", i["title"].lower(), i["year"])
            return None
        best = {}
        for sec in sorted(self.sections.values(), key=lambda s: (rank(s), s.key)):
            for n, i in enumerate(sec.items):
                k = key(i)
                if k is None:
                    continue
                score = (-QUALITY.get(i.get("q", ""), 0) if prefer == "quality" else 0, rank(sec))
                if k not in best or score < best[k][0]:
                    best[k] = (score, i["id"])
        for sec in self.sections.values():
            sec.items = [i for i in sec.items if key(i) is None or best[key(i)][1] == i["id"]]
        self._by_id = None


def fetch(client, meta: dict, progress=None) -> Section:
    """A library read off the server, page by page. progress(done, total)."""
    sec = Section(meta["key"], meta["title"], meta["kind"], meta.get("stamp", ""))

    def pages(type_):
        start = 0
        while True:
            rows, total = client.section_page(sec.key, type_, start, PAGE)
            yield from rows
            start += len(rows)
            if progress:
                progress(start, total)
            if not rows or start >= total:
                return
    if sec.kind in ("show", "music"):
        for m in pages(2 if sec.kind == "show" else 8):     # shows, or artists
            sec.add_show(m)
        for m in pages(4 if sec.kind == "show" else 10):    # their episodes, or tracks
            sec.add_item(m)
    else:
        for m in pages(1):
            sec.add_item(m)
    sec.fetched = time.time()
    return sec


def build(clients, hidden=(), fresh: bool = False, progress=None, prefer: str = "plex") -> Index:
    """The index: each library from its file when its place's stamp matches
    it, fetched (and written) when it doesn't. `clients`: Plex, Jellyfin or
    Emby servers, folders (one, or a list). Libraries hidden in the
    settings are read too (a channel can ask for one; the bumpers among
    them are break material), marked so nothing takes them unasked. A place
    that doesn't answer keeps what was read of it last. The same title from
    two places is kept once (dedupe)."""
    out = []
    for client in clients if isinstance(clients, (list, tuple)) else [clients]:
        try:
            metas = client.library_sections()
        except Exception as e:
            print(f"[library] {type(client).__name__}: {e!r}: what was read of it last")
            out += [s for s in (cached() or Index()).sections.values() if _owned(client, s.key)]
            continue
        for meta in metas:
            sec = None if fresh else Section.load(meta["key"])
            if sec is None or sec.stamp != meta["stamp"] or sec.kind != meta["kind"]:
                t0 = time.time()
                if hasattr(client, "fetch_section"):
                    sec = client.fetch_section(meta, sec or Section.load(meta["key"]))
                else:
                    sec = fetch(client, meta, (lambda d, t, m=meta: progress(m["title"], d, t)) if progress else None)
                sec.save()
                print(f"[library] {sec.title}: {len(sec.items)} titles read in {time.time() - t0:.1f} s")
            sec.title, sec.hidden = meta["title"], meta["key"] in hidden
            out.append(sec)
    idx = Index(out)
    idx.dedupe(prefer)
    _extras(idx, clients if isinstance(clients, (list, tuple)) else [clients])
    return idx


def _extras(idx, clients):
    """Plex's collections, playlists and watched titles on the index: asked
    of the server, else as they were last read."""
    got = None
    for client in clients:
        if hasattr(client, "extras"):
            try:
                got = client.extras([{"key": s.key, "kind": s.kind} for s in idx.sections.values()
                                     if _owned(client, s.key)])
            except Exception as e:
                print(f"[library] collections and playlists not read: {e!r}")
    path = os.path.join(_dir(), "extras.json")
    if got is not None:
        try:
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(got, f, separators=(",", ":"))
            os.replace(path + ".tmp", path)
        except OSError:
            pass
    else:
        try:
            with open(path, encoding="utf-8") as f:
                got = json.load(f)
        except (OSError, ValueError):
            got = {}
    idx.collections = got.get("collections") or {}
    idx.playlists = got.get("playlists") or {}
    idx.watched = set(got.get("watched") or [])


def _owned(client, key: str) -> bool:
    """Whether a library (by its key) is this place's."""
    from . import folders, jellyfin
    if isinstance(client, jellyfin.Client):
        return key.startswith(client.prefix())
    if isinstance(client, folders.Folders):
        return key.startswith("l")
    return key[:1].isdigit()


def cached(hidden=()) -> Optional[Index]:
    """The index as it was last written, without asking the server: what a
    start has in hand before the server answers (or when it never does)."""
    out = []
    try:
        names = os.listdir(_dir())
    except OSError:
        return None
    for n in names:
        if n.startswith("section-") and n.endswith(".json"):
            sec = Section.load(n[len("section-"):-len(".json")])
            if sec:
                sec.hidden = sec.key in hidden
                out.append(sec)
    if not out:
        return None
    idx = Index(out)
    _extras(idx, [])
    return idx


def load(app, done=None, fresh: bool = False):
    """The index built on a thread; app.library set and done(index) called on
    the UI thread. One build at a time."""
    from . import folders, jellyfin
    od = getattr(app, "ondemand", None)
    plex = od is not None and od.signed_in
    places = jellyfin.clients(app.config) + ([folders.find(app.config)] if folders.find(app.config) else [])
    if (not plex and not places) or getattr(app, "library_loading", False):
        return
    app.library_loading = True

    def progress(title, d, t):
        app.library_progress = (title, d, t)

    def work():
        idx, err = None, ""
        try:
            clients = list(places)
            if plex:
                c = od.client()
                try:
                    if not c.server:
                        c.discover_server(prefer=app.config.plex_server_id)
                    clients.insert(0, c)
                except Exception as e:
                    print(f"[library] Plex didn't answer ({e!r}): what was read of it last")
                    clients.insert(0, _Gone())
            idx = build(clients, hidden=set(app.config.plex_hidden_libraries or []), fresh=fresh, progress=progress,
                        prefer=getattr(app.config, "dedupe_prefer", "plex"))
        except Exception as e:
            err = repr(e)
            print(f"[library] couldn't read the library ({e!r}): using what was read last")
            idx = cached(set(app.config.plex_hidden_libraries or []))
        app.post(_loaded, app, idx, err, done)
    threading.Thread(target=work, daemon=True).start()


class _Gone:
    """A Plex server that didn't answer: its libraries from their files."""
    def library_sections(self):
        raise OSError("Plex away")


def _loaded(app, idx, err, done):
    app.library_loading = False
    app.library_progress = None
    if idx is not None:
        app.library = idx
        print(f"[library] {idx.count()} titles in {len(idx.sections)} libraries.")
    if done:
        done(idx, err)
