"""Write a local test lineup: mpv test-pattern channels, one dead channel
(for the stand-by card), and a guide that covers the next day.

    python tools/devtv.py            # prints the command to run with it
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cathode import paths  # noqa: E402

CHANNELS = [
    (2, "Color Bars", "smptehdbars=size=1280x720:rate=30", "News"),
    (4, "Test Card", "testsrc2=size=1280x720:rate=30", "News"),
    (5, "Fractal TV", "mandelbrot=size=1280x720:rate=30", "Science"),
    (7, "Life Channel", "life=size=1280x720:rate=30:mold=10:ratio=0.1:death_color=#202060", "Kids"),
    (9, "RGB Network", "rgbtestsrc=size=1280x720:rate=30", "Movies"),
    (11, "Cellular", "cellauto=size=1280x720:rate=30:rule=110", "Science"),
    (13, "Dead Air", "http://127.0.0.1:9/nothing-here.ts", "Sports"),
]
SHOWS = ["Morning Report", "The Big Picture", "Signal & Noise", "Late Edition",
         "Prime Time Movie", "Weather Watch", "Rerun Theater", "Static Hour"]


def main():
    out = os.path.join(paths.cache_dir(), "dev")
    os.makedirs(out, exist_ok=True)
    m3u = os.path.join(out, "dev.m3u")
    xml = os.path.join(out, "dev.xml")
    with open(m3u, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for num, name, src, group in CHANNELS:
            url = src if src.startswith("http") else f"av://lavfi:{src}"
            f.write(f'#EXTINF:-1 tvg-id="dev{num}" tvg-chno="{num}" group-title="{group}",{name}\n{url}\n')
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    with open(xml, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')
        for num, name, _, _ in CHANNELS:
            f.write(f'  <channel id="dev{num}"><display-name>{escape(name)}</display-name></channel>\n')
        for num, name, _, group in CHANNELS:
            t = now
            i = num
            while t < now + timedelta(hours=26):
                length = timedelta(minutes=30 if i % 3 else 60)
                title = SHOWS[i % len(SHOWS)]
                fmt = "%Y%m%d%H%M%S +0000"
                f.write(f'  <programme start="{t.strftime(fmt)}" stop="{(t + length).strftime(fmt)}"'
                        f' channel="dev{num}"><title>{escape(title)}</title>'
                        f'<desc>{escape(f"{title} on {name}: a test programme with a description long enough to wrap onto more than one line of the expanded banner.")}</desc>'
                        f'<category>{group}</category></programme>\n')
                t += length
                i += 1
        f.write("</tv>\n")
    print(f'python main.py -w --playlist "{m3u}" --epg "{xml}"')


if __name__ == "__main__":
    main()
