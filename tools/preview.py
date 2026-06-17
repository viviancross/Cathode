#!/usr/bin/env python3
"""Render Cathode UI frames to PNG without mpv — for visual sanity checks.

Renders the OSD bar and the program guide across font + theme combinations at
the Steam Deck's native 1280x800, compositing over a fake 'video' background so
transparency is visible.  Writes PNGs to tools/preview_out/.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from PIL import Image
import numpy as np

from cathode import demo
from cathode.ui import theme

W, H = 1280, 800
OUT = os.path.join(os.path.dirname(__file__), "preview_out")
os.makedirs(OUT, exist_ok=True)


def fake_video_bg(w, h):
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        arr[y, :, 2] = int(40 + 60 * y / h)
    arr[80:300, 100:500] = (90, 40, 30)
    arr[200:560, 720:1180] = (30, 70, 50)
    return Image.fromarray(arr, "RGB").convert("RGBA")


def composite(bg, overlay):
    return Image.alpha_composite(bg, overlay).convert("RGB")


def render_osd(channels, epg, now):
    from cathode.ui.osd import OSD
    from cathode.ui import effects
    osd = OSD(W, H)
    ch = channels[0]
    cid = epg.resolve_channel_id(ch.epg_id, ch.name)
    cur = epg.current_program(cid, now)
    nxt = epg.next_program(cid, now)
    img = osd.render(ch, cur, nxt, volume=80, muted=False, show_volume=False)
    frame = composite(fake_video_bg(W, H), img)
    frame = composite(frame.convert("RGBA"),
                      effects.make_scanline_cache(W, H, 40))
    return frame.convert("RGB")


def render_guide(channels, epg):
    from cathode.ui.guide import Guide
    from cathode.ui import effects
    g = Guide(W, H, epg_hours=3)
    g.jump_to_channel(channels, 2)
    img = g.render(channels, epg, current_channel_idx=2)
    img = Image.alpha_composite(img, effects.make_scanline_cache(W, H, 30))
    return img.convert("RGB")


def main():
    channels = demo.build_channels(W, H)
    epg = demo.build_epg(channels)
    now = datetime.now(timezone.utc)

    avail = theme.available_fonts()
    print("Available fonts:", avail)

    fonts  = [f for f in ("vcr", "ibm", "dejavu") if f in avail] or avail[:1]
    themes = ["blue", "amber", "green", "vhs", "mono"]

    # OSD: one per font, all in blue
    theme.apply_theme("blue")
    for fk in fonts:
        theme.set_font(fk)
        render_osd(channels, epg, now).save(
            os.path.join(OUT, f"osd_{fk}.png"))
        print(f"wrote osd_{fk}.png")

    # Guide: font x theme matrix (keep it small)
    for fk in fonts:
        theme.set_font(fk)
        for th in themes:
            theme.apply_theme(th)
            render_guide(channels, epg).save(
                os.path.join(OUT, f"guide_{fk}_{th}.png"))
            print(f"wrote guide_{fk}_{th}.png")

    print("\nDone ->", OUT)


if __name__ == "__main__":
    main()
