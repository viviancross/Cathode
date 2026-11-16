"""Configuration management."""

import json
import os
import threading
from dataclasses import dataclass, field


def _fits(default, v) -> bool:
    """A saved value of the kind the setting holds (bool is not an int)."""
    if default is None:
        return True
    if isinstance(default, bool):
        return isinstance(v, bool)
    if isinstance(default, (int, float)):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and \
            (isinstance(default, float) or float(v).is_integer())
    return isinstance(v, type(default))


def _video_prefill():
    from .videochannels import prefill
    return prefill()


@dataclass
class Config:
    _path: str = field(default="", repr=False)

    playlist_url: str = ""
    epg_url: str = ""
    last_channel: int = 1

    # Volume (0-100)
    volume: int = 80
    muted: bool = False
    picture_format: str = "original"   # the FORMAT key: original | zoom | stretch | 4:3

    # OSD settings
    osd_timeout: float = 4.0      # seconds OSD stays visible after channel change
    osd_timeout_info: float = 6.0 # seconds OSD stays visible when manually shown

    # Channel-change static
    reveal_duration: float = 0.3   # seconds to fade static out once stream is up
    tune_timeout: float = 12.0     # max seconds to hold static if stream stalls

    # Scanline intensity (0.0 = off, 1.0 = heavy)
    scanline_alpha: int = 40       # 0-255 alpha for scanline overlay

    # Widest shape the interface itself is drawn in, as w/h; 0 fills the display.
    # The UI is laid out for a television, so on anything much wider than 16:9
    # (a phone in landscape, an ultrawide monitor) filling the screen drags the
    # menus away from the video. Set 16/9 to keep it TV-shaped and centred.
    ui_max_aspect: float = 0.0
    # Narrowest shape the interface is drawn in, as w/h; 0 lets it fill. Guards
    # the other end from ui_max_aspect: a phone held upright is about 1:2.4, and
    # a 16:9 box there is a band using a quarter of the screen.
    ui_min_aspect: float = 0.0
    # A 4:3 skin (Cathode DSS, Cathode Plate) on a wider screen: False pillarboxes
    # it, as the box looked on a widescreen set in 4:3 mode; True stretches it
    # to fill, as the set's Full/Stretch mode did.
    stretch_43: bool = False

    # CRT effect toggles (driven by the theme editor)
    video_aspect: str = "Original" # Original | Stretch | 4:3 | 16:9 | 16:10
    crt_enabled: bool = True       # CRT scanline overlay on/off
    vignette_enabled: bool = True  # corner vignette on/off
    # Animated transitions. Off resolves each one instantly to its end
    # state — the same courtesy prefers-reduced-motion buys on the web.
    motion_enabled: bool = True
    # The idle screensaver (bouncing wordmark after five minutes on the home
    # screen or guide). It paints whole frames on its own clock, so if it ever
    # misbehaves this is the switch.
    screensaver: bool = True

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
    plex_sorts: dict = field(default_factory=dict)   # list key -> "field:dir";
    # each library reopens with the sort it was last left on
    # How a library is presented: "list" or "wall" (a grid of posters). List is
    # the default because it is the better of the two for episodes, where the
    # titles carry the information and the art is one repeated frame.
    ppv_view: str = "list"
    # Where the DVR keeps downloaded files. Blank picks a sensible place for the
    # platform (see downloads.default_dir). Point it at a bigger disk if the
    # default one is small.
    download_dir: str = ""
    # Subtitle styling (independent of the main UI font) + audio output.
    subtitles: bool = False        # subtitles / captions on for every channel and title
    sub_font: str = ""             # font key (blank = mpv default sans-serif)
    sub_size: int = 38             # mpv sub-font-size
    sub_color: str = "#FFFFFFFF"   # mpv sub-color (#AARRGGBB)
    sub_back: str = ""             # mpv sub-back-color (#AARRGGBB; blank = no box)
    sub_search_lang: str = "en"    # Find subtitles' language (ISO 639-1)
    sub_auto_sync: bool = True     # Plex's auto-sync, where the server can do it
    audio_device: str = ""         # mpv audio-device (blank = auto)

    # Appearance
    skin: str = "classic"          # classic | plate | plate_hd | indirect | indirect_hd | igrid | passage
    # Each box skin's own look choices (Classic uses font/theme/custom_palette):
    skin_fonts: dict = field(default_factory=dict)    # skin -> font key
    skin_themes: dict = field(default_factory=dict)   # skin -> theme ("native", a theme, "custom")
    skin_custom: dict = field(default_factory=dict)   # skin -> edited base colours
    font: str = "vcr"              # vcr | ibm | vt220 | pixelop | vt323 | jersey
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
    spelunkr_shipped: bool = False  # Spelunkr added to the playlists once (spelunkr.ship)

    # Window
    start_fullscreen: bool = True  # -w on the command line overrides it
    boot_sequence: bool = True     # the "acquiring signal" start-up screen
    sound_effects: str = "medium"  # the box's key sounds, on the skins whose box had them: off|low|medium|high
    display: int = 0               # which monitor (0 = the first)

    # Startup
    main_menu_on_launch: bool = True  # show the home screen on launch; when
    # false, boot straight into the configured playlist (the menu is still
    # reachable from the context menu). First run always shows the menu.
    setup_done: bool = False       # the first-run setup wizard already ran once
    key_tip_shown: bool = False    # the one-time "which keys do what" toast
    look_chosen: bool = False      # the first-run look wizard (box, colours) is done
    # (it stays reachable from Options > Setup Wizard)

    # Input
    gamepad: bool = True           # enable the native gamepad reader (XInput on
    # Windows, /dev/input/js* on Linux)
    # Held-key auto-repeat (menu/guide/OSK scrolling). Capped so it's followable.
    nav_repeat_delay: int = 300    # ms before a held key starts repeating
    nav_repeat_rate: int = 8       # repeats per second while held

    # Favorite channels (channel numbers). Persisted; shown as a guide category.
    favorites: list = field(default_factory=list)
    # Cathode's own channels (ownchannels.KINDS): where each sits in the
    # lineup. "auto" = after the lineup's last number, "off", or a number.
    own_channels: dict = field(default_factory=lambda: {"tvguide": "auto", "weather": "auto"})
    own_music: bool = True          # their background music
    # Video channels (videochannels): YouTube playlists and channels mixed
    # on a timeline, each a channel after Cathode's own. See new_channel()
    # for an entry's fields. 4.34's music_playlists migrate into them.
    video_channels: list = field(default_factory=_video_prefill)
    video_quality: int = 1080       # a video channel's tallest picture (1080/720/480/360): lower buffers less
    # Library channels (libchannels.py): channels made from the Plex library,
    # after the lineup. See libchannels.new_channel() for an entry's fields.
    library_channels: list = field(default_factory=list)
    library_starter_done: bool = False      # the starter lineup was made once
    guide_days: int = 2             # days of listings the guide holds for timeline channels (2, 7, 14, 30)
    content_groups: list = field(default_factory=list)  # named sets of library sources a channel can name
    channel_edits: dict = field(default_factory=dict)   # channel address -> {"hide", "name", "number", "kids"} (lineup.py)
    profiles: list = field(default_factory=list)        # [{"id", "name", "kids", "fields"}] (profiles.py)
    profile: str = ""               # the profile on ("": the main one)
    main_fields: dict = field(default_factory=dict)     # the main profile's look, kept while another is on
    parent_pin: str = ""            # asked of a kids' profile for Settings and for switching away
    media_servers: list = field(default_factory=list)   # Jellyfin/Emby: [{"url", "user", "user_id", "token", "name", "kind"}]
    local_folders: list = field(default_factory=list)   # [{"path", "name", "kind": movie|show|clip}] (folders.py)
    packs: list = field(default_factory=list)           # [{"name", "keys": [channel addresses]}]: guide tabs
    # Sync (sync.py): every Cathode on the network with the same channels.
    lan_sync: bool = True
    web_remote: bool = True         # the web page: a phone remote, the channels, the lineup (web.py)
    share_channels: bool = True     # the library channels for other apps: M3U, XMLTV, HDHomeRun (web.py)
    sync_id: str = ""               # this Cathode's id among the others
    channels_edited: float = 0.0    # when the channel lists were last edited, here or by another Cathode
    channels_editor: str = ""       # which Cathode edited them
    music_playlists: list = field(default_factory=list)
    retired_music: bool = False     # the old decade music channels taken out once (videochannels.migrate)
    ytdl_checked: float = 0.0       # when yt-dlp was last checked for a newer release

    # Remappable hotkeys (action -> key / gamepad button). Empty = defaults.
    key_bindings: dict = field(default_factory=dict)
    gamepad_bindings: dict = field(default_factory=dict)
    remote: str = ""               # a remote in remote.REMOTES: hints use its button names
    flirc_util: str = ""           # path to flirc_util when it isn't where Cathode looks

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

    # Verbose mpv logging to mpv.log. Off by default — verbose logs grow
    # unbounded over long sessions; turn on when diagnosing video problems.
    mpv_verbose_log: bool = False

    def __post_init__(self):
        # Serialises save() — many Plex background threads call config.save().
        self._save_lock = threading.Lock()
        self._load_error = ""       # why the file couldn't be read (shown once at start)
        # Field defaults above are the single source of truth; load only
        # overrides them from disk when a config file already exists.
        if self._path and os.path.exists(self._path):
            self._load()

    def data_dir(self) -> str:
        """The directory this config lives in — where Cathode keeps user data it
        must not lose. Empty when running without a config file."""
        return os.path.dirname(self._path) if self._path else ""

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("not a settings object")
        except Exception as e:
            # Set the damaged file aside: the first save would otherwise
            # overwrite every playlist and setting it still holds.
            kept = f"{self._path}.damaged"
            try:
                os.replace(self._path, kept)
            except OSError:
                kept = ""
            self._load_error = os.path.basename(kept) if kept else "the old file"
            print(f"[config] Warning: could not load config from {self._path}: {e} (kept as {kept or '-'})")
            return
        for k, v in data.items():
            if k.startswith("_") or not hasattr(self, k):
                continue
            if _fits(getattr(self, k), v):
                cur = getattr(self, k)
                setattr(self, k, int(v) if isinstance(cur, int) and not isinstance(cur, bool) else v)
            else:               # one bad value costs that setting, not the file
                print(f"[config] ignoring {k}={v!r}: expected {type(getattr(self, k)).__name__}")

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
                if os.name != "nt":
                    try:
                        # The config holds Plex tokens — keep it owner-only.
                        os.chmod(self._path, 0o600)
                    except OSError:
                        pass
            except Exception as e:
                print(f"[config] Warning: could not save config: {e}")
                try:
                    os.remove(tmp)
                except OSError:
                    pass
