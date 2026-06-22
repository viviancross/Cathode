"""Configuration management."""

import json
import os
import threading
from dataclasses import dataclass, field


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
    reveal_duration: float = 0.3   # seconds to fade static out once stream is up
    tune_timeout: float = 12.0     # max seconds to hold static if stream stalls

    # Scanline intensity (0.0 = off, 1.0 = heavy)
    scanline_alpha: int = 40       # 0-255 alpha for scanline overlay

    # CRT effect toggles (driven by the theme editor)
    crt_enabled: bool = True       # CRT scanline overlay on/off
    vignette_enabled: bool = True  # corner vignette on/off

    # Guide settings
    guide_hours: int = 3           # hours of EPG to show in guide

    # Weather (shown in the guide header). Empty zip = feature off.
    weather_zip: str = ""          # e.g. "90210" — your area's postal/zip code
    weather_units: str = "F"       # "F" or "C"
    weather_country: str = "US"    # ISO country code — pins the zip lookup to one
    # country (a bare zip is ambiguous, e.g. 90210 can resolve to Spain)

    # Plex-Per-View (browse + watch a Plex library on demand). Empty token = signed out.
    plex_token: str = ""           # plex.tv account token (set via the PIN sign-in)
    plex_client_id: str = ""       # stable X-Plex-Client-Identifier (auto-generated)
    plex_server: str = ""          # cached base URL of the chosen server
    plex_server_id: str = ""       # chosen server's clientIdentifier (blank = auto)
    plex_servers: list = field(default_factory=list)   # cached [{id,title,owned}]
    plex_user_token: str = ""      # selected Plex Home user's token (blank = account)
    plex_user_id: str = ""         # selected Home user uuid
    plex_user_name: str = ""       # selected Home user display name
    plex_quality: str = "Original" # "Original" = direct play, else a transcode preset
    plex_hidden_libraries: list = field(default_factory=list)   # section keys to hide
    plex_sections: list = field(default_factory=list)           # cached [{key,title}]
    # Subtitle styling (independent of the main UI font) + audio output.
    sub_font: str = ""             # font key (blank = mpv default sans-serif)
    sub_size: int = 38             # mpv sub-font-size
    sub_color: str = "#FFFFFFFF"   # mpv sub-color (#AARRGGBB)
    audio_device: str = ""         # mpv audio-device (blank = auto)

    # Appearance
    font: str = "vcr"              # vcr | ibm | vt220 | handjet | dotgothic
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

    # Remappable hotkeys (action -> key / gamepad button). Empty = defaults.
    key_bindings: dict = field(default_factory=dict)
    gamepad_bindings: dict = field(default_factory=dict)

    # Network
    user_agent: str = "Cathode/1.0 IPTV"
    stream_timeout: int = 10

    # Extra raw mpv arguments (advanced / troubleshooting), e.g.
    # ["--gpu-context=wayland"] or ["--hwdec=no"] for Game Mode display issues.
    mpv_extra_args: list = field(default_factory=list)

    # Check GitHub Releases for a newer version on launch (notify only).
    update_check: bool = True

    # Explicit path to the mpv executable (e.g. "C:/mpv/mpv.exe") for when it
    # isn't on PATH. Empty = auto-detect.
    mpv_path: str = ""

    def __post_init__(self):
        # Serialises save() — many Plex background threads call config.save().
        self._save_lock = threading.Lock()
        # Field defaults above are the single source of truth; load only
        # overrides them from disk when a config file already exists.
        if self._path and os.path.exists(self._path):
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
        # Lock + write-to-temp + atomic replace so concurrent saves from Plex
        # background threads can't interleave and corrupt the file.
        lock = getattr(self, "_save_lock", None) or threading.Lock()
        with lock:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            data = {k: v for k, v in self.__dict__.items()
                    if not k.startswith("_")}
            tmp = f"{self._path}.{os.getpid()}.tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self._path)
            except Exception as e:
                print(f"[config] Warning: could not save config: {e}")
                try:
                    os.remove(tmp)
                except OSError:
                    pass
