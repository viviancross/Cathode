"""Settings saved to a file and back.

Backups: every setting to a JSON file in the settings folder's backups
(by hand, or by itself once a week, eight of those kept), and back from
one. What signs this Cathode in somewhere doesn't go into a backup (the
Plex sign-in, Jellyfin and Emby sign-ins) nor what makes it this Cathode
(its id among the others): restoring keeps the ones in hand. Playlist links
do go in, with any provider password inside them."""

from __future__ import annotations

import json
import os
import time
from typing import List, Optional


SECRET = ("plex_token", "plex_user_token", "sync_id", "channels_edited", "channels_editor")
WEEK = 7 * 86400
KEEP_AUTO = 8


def folder(config) -> str:
    d = os.path.join(config.data_dir() or os.path.expanduser("~/.config/cathode"), "backups")
    os.makedirs(d, exist_ok=True)
    return d


def snapshot(config) -> dict:
    data = {k: v for k, v in config.__dict__.items() if not k.startswith("_") and k not in SECRET}
    data["media_servers"] = [{k: v for k, v in s.items() if k != "token"} for s in data.get("media_servers") or []]
    return json.loads(json.dumps(data))


def save(config, auto: bool = False) -> str:
    """A backup now: its file's path."""
    name = time.strftime("cathode-%Y%m%d-%H%M%S") + ("-auto" if auto else "") + ".json"
    path = os.path.join(folder(config), name)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"cathode_backup": 1, "saved": time.time(), "settings": snapshot(config)}, f, indent=1)
    os.replace(path + ".tmp", path)
    if auto:
        autos = sorted(n for n in os.listdir(folder(config)) if n.endswith("-auto.json"))
        for n in autos[:-KEEP_AUTO]:
            try:
                os.remove(os.path.join(folder(config), n))
            except OSError:
                pass
    return path


def weekly(config) -> Optional[str]:
    """A backup when the newest is a week old (or there's none)."""
    try:
        newest = max((os.path.getmtime(os.path.join(folder(config), n)) for n in os.listdir(folder(config))
                      if n.endswith(".json")), default=0)
        if time.time() - newest >= WEEK:
            return save(config, auto=True)
    except OSError as e:
        print(f"[backup] {e!r}")
    return None


def backups(config) -> List[dict]:
    """[{path, saved, auto}], newest first."""
    out = []
    for n in os.listdir(folder(config)):
        if n.endswith(".json"):
            p = os.path.join(folder(config), n)
            out.append({"path": p, "saved": os.path.getmtime(p), "auto": n.endswith("-auto.json"), "name": n})
    return sorted(out, key=lambda b: -b["saved"])


def restore(config, path: str) -> int:
    """A backup's settings put back (the sign-ins and this Cathode's id kept as
    they are): how many settings it held. Saved; a restart takes them up."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if not isinstance(d, dict) or d.get("cathode_backup") != 1 or not isinstance(d.get("settings"), dict):
        raise ValueError("not a Cathode backup")
    tokens = {(s.get("url"), s.get("user")): s.get("token") for s in config.media_servers}
    n = 0
    for k, v in d["settings"].items():
        if k in SECRET or k.startswith("_") or not hasattr(config, k):
            continue
        if k == "media_servers" and isinstance(v, list):
            v = [dict(s, token=tokens.get((s.get("url"), s.get("user")), "")) for s in v if isinstance(s, dict)]
        setattr(config, k, v)
        n += 1
    config.channels_edited = time.time()        # (other Cathodes take the restored channels)
    config.save()
    return n

