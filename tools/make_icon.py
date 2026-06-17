#!/usr/bin/env python3
"""Generate Cathode's app icon — a retro CRT TV showing color bars.

Writes assets/cathode.png (256x256, transparent background).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw

S = 256
OUT = os.path.join(os.path.dirname(__file__), "..", "assets", "cathode.png")


def rr(draw, box, radius, **kw):
    draw.rounded_rectangle(box, radius=radius, **kw)


def main():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # ── Antennae ─────────────────────────────────────────────────────────
    d.line([(128, 70), (78, 18)], fill=(200, 200, 210, 255), width=6)
    d.line([(128, 70), (188, 22)], fill=(200, 200, 210, 255), width=6)
    for (x, y) in [(78, 18), (188, 22)]:
        d.ellipse([x - 8, y - 8, x + 8, y + 8], fill=(230, 230, 240, 255))

    # ── TV body ──────────────────────────────────────────────────────────
    rr(d, [24, 60, 232, 224], 22, fill=(46, 44, 52, 255))
    rr(d, [24, 60, 232, 224], 22, outline=(20, 18, 24, 255), width=4)

    # Screen bezel
    rr(d, [40, 76, 188, 208], 14, fill=(18, 18, 22, 255))

    # ── Screen: SMPTE-style color bars ───────────────────────────────────
    sx0, sy0, sx1, sy1 = 48, 84, 180, 200
    bars = [
        (192, 192, 192), (192, 192, 0), (0, 192, 192), (0, 192, 0),
        (192, 0, 192), (192, 0, 0), (0, 0, 192),
    ]
    bw = (sx1 - sx0) / len(bars)
    bar_bottom = sy0 + int((sy1 - sy0) * 0.74)
    for i, c in enumerate(bars):
        x0 = sx0 + int(i * bw)
        x1 = sx0 + int((i + 1) * bw)
        d.rectangle([x0, sy0, x1, bar_bottom], fill=(*c, 255))
    # Lower band (darker castellation)
    lows = [(0, 0, 116), (26, 26, 26), (54, 0, 122), (26, 26, 26),
            (0, 122, 122), (26, 26, 26), (180, 180, 180)]
    for i, c in enumerate(lows):
        x0 = sx0 + int(i * bw)
        x1 = sx0 + int((i + 1) * bw)
        d.rectangle([x0, bar_bottom, x1, sy1], fill=(*c, 255))

    # Scanlines over the screen
    for y in range(sy0, sy1, 3):
        d.line([(sx0, y), (sx1, y)], fill=(0, 0, 0, 60), width=1)
    # Screen glass highlight
    d.line([(sx0 + 6, sy0 + 6), (sx0 + 30, sy0 + 6)], fill=(255, 255, 255, 70),
           width=3)

    # ── Control panel (right side) ───────────────────────────────────────
    panel_x = 196
    d.ellipse([panel_x, 92, panel_x + 24, 116], fill=(28, 28, 34, 255),
              outline=(120, 120, 130, 255), width=2)   # dial
    d.ellipse([panel_x, 126, panel_x + 24, 150], fill=(28, 28, 34, 255),
              outline=(120, 120, 130, 255), width=2)   # dial
    d.ellipse([panel_x + 6, 168, panel_x + 14, 176], fill=(0, 230, 255, 255))  # power LED
    for gy in range(184, 202, 5):                       # speaker grille
        d.line([(panel_x, gy), (panel_x + 22, gy)], fill=(90, 90, 100, 255),
               width=2)

    # ── Feet ─────────────────────────────────────────────────────────────
    d.rectangle([52, 224, 86, 236], fill=(34, 32, 38, 255))
    d.rectangle([170, 224, 204, 236], fill=(34, 32, 38, 255))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT)
    print("wrote", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
