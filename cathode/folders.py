"""Folders on this computer as library sources: movies, shows, or clips
(bumpers and commercials). Each video's length is read from its own header
(MP4, Matroska/WebM, AVI), so no player has to open it; a file whose length
can't be read is left out. A show's episodes are found by their SxxEyy, the
show named for its folder. A title's key is "L" and its path.

Folders are this computer's own: another Cathode that takes a channel made
from them won't have the files, and skips them."""

from __future__ import annotations

import hashlib
import os
import re
import struct
from typing import List, Optional

EXTS = {".mkv", ".mp4", ".m4v", ".mov", ".avi", ".webm"}
KINDS = [("movie", "Movies"), ("show", "Shows"), ("clip", "Clips: bumpers, commercials")]
_SE = re.compile(r"[Ss](\d{1,2})[ ._-]*[Ee](\d{1,3})")
_YEAR = re.compile(r"[\(\[ ._](19\d\d|20\d\d)[\)\] ._]?")


# ── How long a file runs, from its header ────────────────────────────────

def duration(path: str) -> float:
    """Seconds, or 0 when the header doesn't say."""
    try:
        with open(path, "rb") as f:
            head = f.read(12)
            f.seek(0)
            if head[4:8] in (b"ftyp", b"moov", b"free", b"mdat", b"wide", b"skip"):
                return _mp4(f)
            if head[:4] == b"\x1a\x45\xdf\xa3":
                return _mkv(f)
            if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
                return _avi(f)
    except (OSError, struct.error, ValueError):
        pass
    return 0.0


def _mp4(f) -> float:
    def atoms(end):
        while f.tell() + 8 <= end:
            at = f.tell()
            size, kind = struct.unpack(">I4s", f.read(8))
            if size == 1:
                size = struct.unpack(">Q", f.read(8))[0]
            elif size == 0:
                size = end - at
            if size < 8:
                return
            yield kind, at, size
            f.seek(at + size)
    end = os.fstat(f.fileno()).st_size
    for kind, at, size in atoms(end):
        if kind == b"moov":
            f.seek(at + 8)
            for k2, at2, _s2 in atoms(at + size):
                if k2 == b"mvhd":
                    f.seek(at2 + 8)
                    version = f.read(1)[0]
                    f.read(3)
                    if version == 1:
                        f.read(16)
                        scale, dur = struct.unpack(">IQ", f.read(12))
                    else:
                        f.read(8)
                        scale, dur = struct.unpack(">II", f.read(8))
                    return dur / scale if scale else 0.0
    return 0.0


def _vint(data: bytes, i: int, keep_marker: bool):
    first = data[i]
    n = 1
    while n <= 8 and not first & (0x80 >> (n - 1)):
        n += 1
    if n > 8:
        raise ValueError("bad EBML")
    v = first if keep_marker else first & (0xFF >> n)
    for b in data[i + 1:i + n]:
        v = (v << 8) | b
    return v, i + n


def _mkv(f) -> float:
    data = f.read(1 << 20)
    i, scale, dur = 0, 1000000, None
    containers = {0x18538067, 0x1549A966}       # Segment, Info: look inside
    while i < len(data) - 2:
        eid, i = _vint(data, i, True)
        size, i = _vint(data, i, False)
        if eid in containers:
            continue
        if eid == 0x2AD7B1:                       # TimecodeScale
            scale = int.from_bytes(data[i:i + size], "big")
        elif eid == 0x4489:                       # Duration
            dur = struct.unpack(">f" if size == 4 else ">d", data[i:i + size])[0]
        if eid == 0x1654AE6B or eid == 0x1F43B675:    # Tracks or a Cluster: Info is behind us
            break
        i += size
    return dur * scale / 1e9 if dur else 0.0


def _avi(f) -> float:
    data = f.read(4096)
    k = data.find(b"avih")
    if k < 0:
        return 0.0
    us_per_frame, = struct.unpack("<I", data[k + 8:k + 12])
    frames, = struct.unpack("<I", data[k + 24:k + 28])
    return us_per_frame * frames / 1e6


# ── A folder as a library ────────────────────────────────────────────────

def _key(path: str) -> str:
    return "l" + hashlib.sha1(os.path.abspath(path).lower().encode()).hexdigest()[:10]


def _files(root: str):
    for d, _dirs, names in os.walk(root):
        for n in sorted(names):
            if os.path.splitext(n)[1].lower() in EXTS:
                yield os.path.join(d, n)


def _title(name: str) -> tuple:
    """('Some Film', 1999) out of 'Some.Film.(1999).1080p.mkv'."""
    base = os.path.splitext(name)[0]
    m = _YEAR.search(base)
    year = int(m.group(1)) if m else 0
    if m:
        base = base[:m.start()]
    return re.sub(r"[._]+", " ", base).strip(" -") or name, year


def _show_of(path: str) -> str:
    """A file's show: its folder, or the folder above a Season one."""
    d = os.path.basename(os.path.dirname(path))
    if re.match(r"(?i)^(season|series|s)\s*\d+", d):
        d = os.path.basename(os.path.dirname(os.path.dirname(path)))
    return _title(d)[0]


class Folders:
    """The folders in the settings, as library_sections() and a fetch."""

    def __init__(self, folders: list):
        self.folders = [f for f in folders or [] if f.get("path")]

    def library_sections(self) -> List[dict]:
        out = []
        for f in self.folders:
            if not os.path.isdir(f["path"]):
                continue
            stat = [(p, os.stat(p)) for p in _files(f["path"])]
            stamp = hashlib.sha1(repr(sorted((p, s.st_size, int(s.st_mtime)) for p, s in stat)).encode()).hexdigest()[:12]
            out.append({"key": _key(f["path"]), "title": f.get("name") or os.path.basename(f["path"].rstrip("/\\")),
                        "kind": f.get("kind", "movie"), "stamp": stamp, "path": f["path"]})
        return out

    def fetch_section(self, meta: dict, old=None):
        """The folder read: each file's length from its header (or the last
        reading of it, when the file hasn't changed)."""
        from .library import Section
        sec = Section(meta["key"], meta["title"], meta["kind"], meta["stamp"])
        known = {i["plex"]: i["duration"] for i in (old.items if old else [])}
        shows = {}
        for p in _files(meta["path"]):
            rk = "L" + p
            secs = known.get(rk) or duration(p)
            if secs <= 0:
                continue
            title, year = _title(os.path.basename(p))
            m = _SE.search(os.path.basename(p))
            if meta["kind"] == "show" and m:
                show = _show_of(p)
                sk = "L" + hashlib.sha1(show.lower().encode()).hexdigest()[:10]
                if sk not in shows:
                    shows[sk] = True
                    sec.add_show({"ratingKey": sk, "title": show, "year": year})
                name = re.sub(r"[._]+", " ", os.path.splitext(os.path.basename(p))[0][m.end():]).strip(" -")
                sec.add_item({"type": "episode", "ratingKey": rk, "grandparentRatingKey": sk, "grandparentTitle": show,
                              "parentIndex": int(m.group(1)), "index": int(m.group(2)), "title": name,
                              "duration": int(secs * 1000)})
            else:
                sec.add_item({"type": "movie", "ratingKey": rk, "title": title, "year": year,
                              "duration": int(secs * 1000)})
        import time
        sec.fetched = time.time()
        return sec


def stream(key: str) -> dict:
    from .plex import PlexError
    path = key[1:]
    if not os.path.isfile(path):
        raise PlexError("The file isn't there any more.")
    return {"video": path, "headers": {}, "base": 0.0}


def find(config) -> Optional[Folders]:
    fs = getattr(config, "local_folders", None) or []
    return Folders(fs) if fs else None
