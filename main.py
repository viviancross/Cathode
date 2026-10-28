#!/usr/bin/env python3
"""Cathode: a satellite-box-style IPTV player."""

import argparse
import os
import sys

# The project root (which holds the `cathode` package) importable however
# this is launched.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cathode import paths  # noqa: E402
from cathode.config import Config  # noqa: E402
from cathode.instance import fatal, hold_instance_lock, start_log  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Cathode: a satellite-box-style IPTV player")
    ap.add_argument("--playlist", "-p", metavar="URL_OR_FILE", help="M3U playlist")
    ap.add_argument("--epg", "-e", metavar="URL_OR_FILE", help="XMLTV guide")
    ap.add_argument("--config", "-c", metavar="FILE", default=paths.config_path())
    ap.add_argument("--windowed", "-w", action="store_true", help="start in a window")
    ap.add_argument("--channel", type=int, help="start on this channel number")
    ap.add_argument("--skin", help="classic | plate | plate_hd | indirect | indirect_hd | igrid | passage | wayfinder | y1")
    ap.add_argument("--shot", metavar="PNG", help="save a frame after --seconds and exit")
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--press", default="", metavar="T:BUTTON,...",
                    help="press remote buttons at these times, e.g. 1:INFO,2.5:DIGIT1")
    args = ap.parse_args()

    config = Config(args.config)
    if args.playlist:
        config.playlist_url, config.epg_url = args.playlist, args.epg or ""
    if args.skin:
        config.skin = args.skin

    from cathode.updater import LOCK_FILE      # the update installer holds it too
    runtime = paths.cache_dir()
    lock = hold_instance_lock(os.path.join(runtime, LOCK_FILE))
    if not lock:
        fatal("Cathode is already running, or finishing an update.")
    start_log(runtime)

    from cathode.app import App
    full = config.start_fullscreen and not args.windowed and not args.shot
    app = App(config, fullscreen=full, start_channel=args.channel)
    if args.shot:
        app.shot = (args.shot, args.seconds)
    app.script = [(float(t), b) for t, _, b in (p.partition(":") for p in args.press.split(",") if p)]
    app.run()


if __name__ == "__main__":
    main()
