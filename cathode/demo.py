"""Built-in demo mode — fake channels + synthetic EPG for testing the UI.

Uses mpv's ffmpeg `lavfi` test sources (color bars, test patterns, fractals)
so the UI can be exercised with no playlist, no network and no real IPTV
source.  Perfect for sanity-checking the OSD, guide and retro effects.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List, Tuple

from .playlist import Channel
from .epg import EPG, Program


# (display name, lavfi source, epg id) — all sources accept size=WxH:rate=N
_DEMO_SPECS: List[Tuple[str, str, str]] = [
    ("Color Bars",     "smptebars",   "bars"),
    ("HD Color Bars",  "smptehdbars", "hdbars"),
    ("Test Pattern",   "testsrc2",    "test"),
    ("EBU Bars",       "pal100bars",  "ebu"),
    ("RGB Test",       "rgbtestsrc",  "rgb"),
    ("YUV Test",       "yuvtestsrc",  "yuv"),
    ("Fractal TV",     "mandelbrot",  "fractal"),
    ("Grid Channel",   "testsrc",     "grid"),
]

# Retro show titles to scatter across the schedule
_SHOWS = [
    ("The Midnight Movie",   "Classic cinema after dark.",            "Movie"),
    ("Cyber Cops",           "Future police drama.",                  "Series"),
    ("Galaxy Rangers",       "Animated space adventure.",             "Kids"),
    ("Aerobics Power Hour",  "Get fit with the stars!",               "Fitness"),
    ("News at Nine",         "Tonight's top stories.",                "News"),
    ("Saturday Cartoons",    "A morning block of toons.",             "Kids"),
    ("Infomercial Zone",     "Amazing products, low prices!",         "Shopping"),
    ("Music Television",     "Back-to-back music videos.",            "Music"),
    ("Late Night Talk",      "Celebrity guests and laughs.",          "Talk"),
    ("Cooking with Fire",    "Bold flavors, big personality.",        "Cooking"),
    ("Game Show Mania",      "Spin the wheel and win!",               "Game"),
    ("Sci-Fi Theater",       "Tales from beyond the stars.",          "Movie"),
    ("Weather Now",          "Your forecast, updated hourly.",        "Weather"),
    ("Retro Replay",         "Sports classics from the archives.",    "Sports"),
    ("Soap Opera Digest",    "Love, drama and betrayal.",             "Drama"),
    ("Nature's Wonders",     "Documentary wildlife footage.",         "Documentary"),
]


def build_channels(width: int, height: int, rate: int = 30) -> List[Channel]:
    channels: List[Channel] = []
    for i, (name, src, eid) in enumerate(_DEMO_SPECS, start=2):
        url = f"av://lavfi:{src}=size={width}x{height}:rate={rate}"
        channels.append(
            Channel(
                number=i,
                name=name,
                url=url,
                group="DEMO",
                epg_id=eid,
            )
        )
    return channels


def build_epg(channels: List[Channel]) -> EPG:
    """Synthesize a believable schedule around 'now' for each demo channel."""
    epg = EPG()
    now = datetime.now(timezone.utc)
    # Start two hours before now, aligned to the half hour
    base = now.replace(minute=0 if now.minute < 30 else 30,
                       second=0, microsecond=0) - timedelta(hours=2)

    show_i = 0
    for ch in channels:
        t = base
        end = now + timedelta(hours=5)
        slot = 0
        while t < end:
            # Alternate 30 / 60 minute slots for variety
            dur = 60 if (slot % 3 == 0) else 30
            stop = t + timedelta(minutes=dur)
            title, desc, cat = _SHOWS[show_i % len(_SHOWS)]
            show_i += 1
            slot += 1
            epg.add_programs(ch.epg_id, [
                Program(
                    channel_id=ch.epg_id,
                    title=title,
                    start=t,
                    stop=stop,
                    description=desc,
                    category=cat,
                    episode=f"S{(slot % 5) + 1}E{(slot % 12) + 1}",
                )
            ])
            t = stop
    return epg
