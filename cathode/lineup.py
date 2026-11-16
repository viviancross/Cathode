"""The lineup as you've edited it: channels hidden, renamed, renumbered
(decimals allowed: 10.5), and packs, named sets of channels that are tabs
in the guide's category pop-up. Edits are kept by each channel's address,
so they hold when the playlist is fetched again; a channel's own name and
number come back when its edit is cleared."""

from __future__ import annotations

NONE = "cathode://none"         # the playlist that's no playlist: Cathode's own channels only


def apply(chans: list, config) -> list:
    """The channels to show, edited, in number order (ties as they came)."""
    edits = getattr(config, "channel_edits", None) or {}
    out = []
    for ch in chans:
        if not hasattr(ch, "orig"):
            ch.orig = (ch.name, ch.number)
        e = edits.get(ch.url) or {}
        ch.name = e.get("name") or ch.orig[0]
        ch.number = e["number"] if isinstance(e.get("number"), (int, float)) else ch.orig[1]
        if not e.get("hide"):
            out.append(ch)
    out.sort(key=lambda c: c.number)
    return out


def number(text: str):
    """'10.5' -> 10.5, '12' -> 12, anything else -> None."""
    try:
        v = float(text.strip())
    except (ValueError, AttributeError):
        return None
    if v <= 0 or v > 99999:
        return None
    return int(v) if v.is_integer() else round(v, 2)


def edit(config, ch, **change):
    """Set (or, with a None, clear) a channel's name, number or hide."""
    e = dict((config.channel_edits or {}).get(ch.url) or {})
    for k, v in change.items():
        if v is None or v is False or v == "":
            e.pop(k, None)
        else:
            e[k] = v
    if e:
        config.channel_edits[ch.url] = e
    else:
        config.channel_edits.pop(ch.url, None)


def packs(config) -> list:
    return [p for p in getattr(config, "packs", None) or [] if p.get("name")]


def in_pack(config, name: str, chans: list) -> list:
    p = next((p for p in packs(config) if p["name"] == name), None)
    keys = set((p or {}).get("keys") or [])
    return [c for c in chans if c.url in keys]
