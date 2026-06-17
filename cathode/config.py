"""Configuration management."""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Config:
    _path: str = field(default="", repr=False)

    playlist_url: str = ""
    epg_url: str = ""
    last_channel: int = 1

    # Volume (0-100)
    volume: int = 80
    muted: bool = False

    # OSD settings
    osd_timeout: float = 4.0      # seconds OSD stays visible after channel change
    osd_timeout_info: float = 6.0 # seconds OSD stays visible when manually shown

    # Channel-change static
    static_duration: float = 0.35  # (legacy) seconds of static noise
    reveal_duration: float = 0.3   # seconds to fade static out once stream is up
    tune_timeout: float = 12.0     # max seconds to hold static if stream stalls

    # Scanline intensity (0.0 = off, 1.0 = heavy)
    scanline_alpha: int = 40       # 0-255 alpha for scanline overlay

    # CRT effect toggles (driven by the theme editor)
    crt_enabled: bool = True       # CRT scanline overlay on/off
    vignette_enabled: bool = True  # corner vignette on/off

    # Guide settings
    guide_hours: int = 3           # hours of EPG to show in guide

    # Appearance
    font: str = "vcr"              # vcr | ibm | vt220 | pixelforge | dejavu
    theme: str = "blue"           # blue | amber | green | vhs | mono | custom | ...
    # Custom palette saved by the theme editor: {bg,accent,accent2,text -> [r,g,b]}
    custom_palette: dict = field(default_factory=dict)   # legacy (migrated)
    # User-created/overridden color themes shown in the Color Theme menu:
    # name -> {bg, accent, accent2, text, scanline, crt, vignette}
    custom_themes: dict = field(default_factory=dict)
    # User-saved look presets: name -> {theme, font, scanline_alpha, ...}
    profiles: dict = field(default_factory=dict)
    # Saved playlists/networks: [{name, playlist_url, epg_url}, ...]
    playlists: list = field(default_factory=list)

    # Startup
    main_menu_on_launch: bool = True  # show the home screen on launch; when
    # false, boot straight into the configured playlist (the menu is still
    # reachable from the context menu). First run always shows the menu.

    # Input
    gamepad: bool = True           # enable the native gamepad reader (XInput on
    # Windows, /dev/input/js* on Linux)
    # Held-key auto-repeat (menu/guide/OSK scrolling). Capped so it's followable.
    nav_repeat_delay: int = 300    # ms before a held key starts repeating
    nav_repeat_rate: int = 8       # repeats per second while held

    # Favorite channels (channel numbers). Persisted; shown as a guide category.
    favorites: list = field(default_factory=list)

    # Network
    user_agent: str = "Cathode/1.0 IPTV"
    stream_timeout: int = 10

    # Extra raw mpv arguments (advanced / troubleshooting), e.g.
    # ["--gpu-context=wayland"] or ["--hwdec=no"] for Game Mode display issues.
    mpv_extra_args: list = field(default_factory=list)

    # Explicit path to the mpv executable (e.g. "C:/mpv/mpv.exe") for when it
    # isn't on PATH. Empty = auto-detect.
    mpv_path: str = ""

    def __init__(self, path: str = ""):
        self._path = path
        # Set defaults
        self.playlist_url = ""
        self.epg_url = ""
        self.last_channel = 1
        self.volume = 80
        self.muted = False
        self.osd_timeout = 4.0
        self.osd_timeout_info = 6.0
        self.static_duration = 0.35
        self.reveal_duration = 0.3
        self.tune_timeout = 12.0
        self.scanline_alpha = 40
        self.crt_enabled = True
        self.vignette_enabled = True
        self.guide_hours = 3
        self.font = "vcr"
        self.theme = "blue"
        self.custom_palette = {}
        self.custom_themes = {}
        self.profiles = {}
        self.playlists = []
        self.main_menu_on_launch = True
        self.gamepad = True
        self.nav_repeat_delay = 300
        self.nav_repeat_rate = 8
        self.favorites = []
        self.user_agent = "Cathode/1.0 IPTV"
        self.stream_timeout = 10
        self.mpv_extra_args = []
        self.mpv_path = ""

        if path and os.path.exists(path):
            self._load()

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if hasattr(self, k) and not k.startswith("_"):
                    setattr(self, k, v)
        except Exception as e:
            print(f"[config] Warning: could not load config from {self._path}: {e}")

    def save(self):
        if not self._path:
            return
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        data = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[config] Warning: could not save config: {e}")
