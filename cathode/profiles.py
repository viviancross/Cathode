"""Profiles: who's watching. Each has its own look (skin, colours, fonts,
the tube's lines) and favourites; a kids' profile sees only the channels
marked for kids (and the library channels set to kids' ratings), and
Settings ask a kids' profile for the parent PIN. Every profile watches the
same schedules: a channel shows the same programme whoever's watching.

And the watch history: each time you leave a channel you watched for a
minute or more, what it was, kept a month, for Settings > System."""

from __future__ import annotations

import json
import os
import time
import uuid

FIELDS = ("skin", "skin_fonts", "skin_themes", "font", "theme", "custom_palette", "crt_enabled", "scanline_alpha",
          "vignette_enabled", "favorites")
KEEP = 30 * 86400               # history kept this long
MIN_WATCH = 60                  # seconds on a channel before it's history


def active(config) -> dict:
    """The profile on: its dict, or the main one ({"id": "", ...})."""
    pid = getattr(config, "profile", "") or ""
    return next((p for p in config.profiles if p["id"] == pid), {"id": "", "name": "Main", "kids": False})


def is_kids(config) -> bool:
    return bool(active(config).get("kids"))


def new(config, name: str, kids: bool = False) -> dict:
    """A profile starting from the look on now, no favourites."""
    p = {"id": uuid.uuid4().hex[:8], "name": name, "kids": kids,
         "fields": {k: json.loads(json.dumps(getattr(config, k))) for k in FIELDS if hasattr(config, k)}}
    p["fields"]["favorites"] = []
    config.profiles.append(p)
    return p


def switch(app, pid: str):
    """Put the profile on now away (its look, its favourites) and the other
    on, the lineup filtered again for it."""
    cfg = app.config
    cur = active(cfg)
    mine = {k: json.loads(json.dumps(getattr(cfg, k))) for k in FIELDS if hasattr(cfg, k)}
    if cur["id"]:
        cur["fields"] = mine
    else:
        cfg.main_fields = mine
    nxt = next((p for p in cfg.profiles if p["id"] == pid), None)
    fields = nxt["fields"] if nxt else (cfg.main_fields or {})
    for k, v in fields.items():
        if k in FIELDS and hasattr(cfg, k):
            setattr(cfg, k, v)
    cfg.profile = nxt["id"] if nxt else ""
    cfg.save()
    if hasattr(app, "set_skin"):
        app.set_skin(cfg.skin)
    if hasattr(app, "relineup"):
        app.relineup()


def kid_ok(ch, config) -> bool:
    """Whether a kids' profile sees a channel: one you marked for kids, a
    library channel set to kids' ratings, or Cathode's TV Guide and Weather."""
    from . import ownchannels, videochannels as vc
    e = (getattr(config, "channel_edits", None) or {}).get(ch.url) or {}
    if "kids" in e:
        return bool(e["kids"])
    if ownchannels.is_own(ch):
        return True
    if vc.is_video(ch):
        c = vc.entry(config, vc.cid_of(ch)) or {}
        return c.get("content") == "kids"
    return False


# ── Watch history ────────────────────────────────────────────────────────

def _path() -> str:
    from . import paths
    return os.path.join(paths.cache_dir(), "history.json")


def history() -> list:
    try:
        with open(_path(), encoding="utf-8") as f:
            rows = json.load(f)
        return [r for r in rows if isinstance(r, dict) and time.time() - r.get("t", 0) < KEEP]
    except (OSError, ValueError):
        return []


def note(ch, started: float, title: str, profile: str):
    """A channel watched from `started` till now, into the history (a minute
    or more of it)."""
    secs = time.time() - started
    if ch is None or secs < MIN_WATCH:
        return
    rows = history()
    rows.append({"t": started, "s": round(secs), "num": ch.number, "ch": ch.name, "title": title or "",
                 "who": profile})
    try:
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows[-2000:], f)
        os.replace(tmp, _path())
    except OSError as e:
        print(f"[history] not written: {e!r}")


def clear():
    try:
        os.remove(_path())
    except OSError:
        pass


def most_watched(rows: list, days: int = 7) -> list:
    """[(channel, hours)] over the last `days`, most first."""
    cut = time.time() - days * 86400
    tally = {}
    for r in rows:
        if r.get("t", 0) >= cut:
            key = f"{r.get('num', 0):g}  {r.get('ch', '')}"
            tally[key] = tally.get(key, 0) + r.get("s", 0) / 3600
    return sorted(tally.items(), key=lambda kv: -kv[1])
