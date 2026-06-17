#!/usr/bin/env python3
"""Cathode — retro IPTV player for Steam Deck."""

import argparse
import sys
import os

# Ensure this file's directory (the project root, which contains the `cathode`
# package) is importable no matter how the script is launched or what the
# current working directory is.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cathode.app import App
from cathode.config import Config


def main():
    parser = argparse.ArgumentParser(
        description="Cathode — retro 80s/90s cable TV IPTV player"
    )
    parser.add_argument(
        "--playlist", "-p",
        metavar="URL_OR_FILE",
        help="M3U playlist URL or file path",
    )
    parser.add_argument(
        "--epg", "-e",
        metavar="URL_OR_FILE",
        help="XMLTV EPG URL or file path",
    )
    parser.add_argument(
        "--config", "-c",
        metavar="FILE",
        default=os.path.expanduser("~/.config/cathode/config.json"),
        help="Config file path (default: ~/.config/cathode/config.json)",
    )
    parser.add_argument(
        "--width", type=int, default=None,
        help="Display width (default: 1920 fullscreen, 1280 windowed)",
    )
    parser.add_argument(
        "--height", type=int, default=None,
        help="Display height (default: 1080 fullscreen, 720 windowed)",
    )
    parser.add_argument(
        "--fullscreen", "-f", action="store_true", default=None,
        help="Run fullscreen (the default unless --windowed)",
    )
    parser.add_argument(
        "--windowed", "-w", action="store_true",
        help="Run in a window instead of fullscreen (good for testing the UI)",
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="Demo mode: built-in test-pattern channels + fake EPG, "
             "no playlist or network needed (implies --windowed)",
    )
    parser.add_argument(
        "--mpv", choices=["auto", "flatpak", "system"], default="auto",
        help="Which mpv to drive (default: auto — Flatpak on Steam Deck, "
             "else a system mpv binary)",
    )
    parser.add_argument(
        "--channel", type=int, default=None,
        help="Start on this channel number",
    )
    args = parser.parse_args()

    # Resolve fullscreen vs windowed (demo defaults to windowed)
    if args.windowed:
        fullscreen = False
    elif args.fullscreen:
        fullscreen = True
    elif args.demo:
        fullscreen = False
    else:
        fullscreen = True

    # Resolve dimensions from mode if not explicitly given
    width  = args.width  or (1920 if fullscreen else 1280)
    height = args.height or (1080 if fullscreen else 720)

    config = Config(args.config)
    if args.playlist:
        config.playlist_url = args.playlist
    if args.epg:
        config.epg_url = args.epg

    # No early playlist check here: App.run() prompts for a playlist when none
    # is configured (first run) and re-prompts if one fails to load.

    app = App(
        config=config,
        width=width,
        height=height,
        fullscreen=fullscreen,
        start_channel=args.channel,
        demo=args.demo,
        mpv_backend=args.mpv,
    )
    app.run()


if __name__ == "__main__":
    main()
