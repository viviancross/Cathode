"""Main UI renderer — composites all layers and writes MPV overlay buffer."""

from __future__ import annotations

import math
import os
import threading
import time
import traceback
from typing import Optional, List, TYPE_CHECKING

import numpy as np
from PIL import Image, ImageDraw

from .osd import OSD
from .guide import Guide
from .menu import ContextMenu
from .osk import OnScreenKeyboard
from .editor import ThemeEditor
from .mainmenu import MainMenu
from .ppv import PPVScreen
from .plexosd import PlexOSD
from .plexinfo import PlexInfoScreen
from .effects import (
    make_crt_overlay,
    combine_dark_overlays,
    make_vignette,
    draw_smpte_bars,
)
from .theme import get_font, CHANNEL_GREEN, SCRIM, TRACK

if TYPE_CHECKING:
    from ..epg import EPG
    from ..playlist import Channel
    from ..player import Player


def _to_premultiplied_bgra(img: Image.Image) -> bytes:
    """Serialise an RGBA image to the premultiplied BGRA mpv's overlay wants.

    Pillow's "BGRa" raw packer does this in one C pass.  Every Pillow build we
    ship has it, but a port to a new platform may land on one that doesn't, and
    a missing packer would otherwise show up as a silently corrupt screen — so
    fall back to the (much slower) numpy equivalent instead of raising.
    """
    global _HAVE_BGRA_PACKER
    if _HAVE_BGRA_PACKER:
        try:
            return img.tobytes("raw", "BGRa")
        except (ValueError, KeyError, OSError):
            _HAVE_BGRA_PACKER = False   # probe once, then stay on the fallback
    arr = np.asarray(img, dtype=np.uint8)          # RGBA, shape (H, W, 4)
    rgb = arr[:, :, :3].astype(np.uint16)
    alpha = arr[:, :, 3:4].astype(np.uint16)
    pm = (rgb * alpha // 255).astype(np.uint8)     # premultiply
    bgra = np.dstack([pm[:, :, 2], pm[:, :, 1], pm[:, :, 0], arr[:, :, 3]])
    return np.ascontiguousarray(bgra).tobytes()


_HAVE_BGRA_PACKER = True


def fit_aspect(width: int, height: int, aspect: float, min_aspect: float = 0.0):
    """Centred box whose shape is held between `min_aspect` and `aspect` (w/h).

    Returns (w, h, x, y). An `aspect` of 0 means "use the whole thing".

    Cathode's interface is laid out for a television. On a display much wider
    than 16:9 — a phone in landscape, an ultrawide monitor — stretching it edge
    to edge pulls the menus away from the video and leaves the frame hugging the
    bezels, so the box is pillarboxed down to `aspect`.

    `min_aspect` guards the opposite end. A phone held upright is about 1:2.4;
    squeezing a TV layout into 16:9 there leaves a band using a quarter of the
    screen, and a menu that can only show two of its rows. Letterboxing to a
    gentler shape instead gives the interface room while still keeping it
    recognisably a television rather than a column.
    """
    if aspect <= 0 or width <= 0 or height <= 0:
        return width, height, 0, 0
    a = width / height
    if a > aspect:
        w, h = int(round(height * aspect)), height      # too wide: pillarbox
    elif min_aspect and a < min_aspect:
        w, h = width, int(round(width / min_aspect))    # too tall: letterbox
    else:
        w, h = width, height                            # already in range
    return w, h, (width - w) // 2, (height - h) // 2


def _smoothstep(t: float) -> float:
    """Ease-in-out 0..1 -> 0..1 for a gentler fade than a linear ramp."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _ease_out_quart(t: float) -> float:
    """Fast start, long settle. Arrivals: the thing is already most of the way
    there before the eye has finished moving to it."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 4


def _ease_in_quad(t: float) -> float:
    """Slow start, accelerating away. Departures, which read better leaving
    than the mirror of an arrival does."""
    t = max(0.0, min(1.0, t))
    return t * t


class UIState:
    WATCHING         = "watching"
    CHANNEL_CHANGING = "channel_changing"
    GUIDE_OPEN       = "guide_open"


class Renderer:
    """
    Manages the MPV overlay.  Call update() whenever UI state changes,
    and start the background clock-tick thread with start().
    """

    STATIC_FPS   = 60   # frames/sec during the channel-change static
    STATIC_BLOCK = 5    # static "particle" size in px (bigger = coarser tube TV)
    CLOCK_TICK   = 1.0  # seconds between clock-only refreshes
    ATTRACT_AFTER = 300.0  # idle seconds on home/guide before the screensaver

    def __init__(
        self,
        player: "Player",
        width: int,
        height: int,
        overlay_path: str,
        scanline_alpha: int = 40,
        epg_hours: int = 3,
    ):
        self.player = player
        self.width  = width
        self.height = height
        self._overlay_path = overlay_path
        # Where the UI sits on mpv's surface, and how big that surface is.
        # These differ from width/height when the interface is drawn into a
        # box narrower than the display (see fit_aspect). Anything handed to
        # mpv in display coordinates has to go through them.
        self.overlay_pos = (0, 0)
        self.surface_size = (width, height)
        self._scanline_alpha = scanline_alpha
        self._epg_hours = epg_hours
        # Smallest interactive row in pixels; 0 leaves it to proportion.
        # Set by touch hosts before the first layout.
        self.min_row_h = 0
        # Guide category state — survives rebuilds/resizes; resets each launch.
        self._guide_categories = ["All", "Favorites"]
        self._guide_favorites = set()
        self._guide_category = "All"

        # Context menu + on-screen keyboard + theme editor — persistent
        self.menu = ContextMenu(width, height)
        self.osk = OnScreenKeyboard(width, height)
        self.editor = ThemeEditor(width, height)
        self.main_menu = MainMenu(width, height)
        self.ppv = PPVScreen(width, height)   # Plex-Per-View browse screen
        self.plexinfo = PlexInfoScreen(width, height)   # Plex item info page
        self.plexosd = PlexOSD(width, height)  # Plex playback control bar
        self.plex_playing = False             # a Plex item is the current video

        # CRT scanline / vignette toggles (driven by the theme editor + config).
        # Private here because the cached tube layer has to be rebuilt whenever
        # either changes; the properties below own that. Set before
        # _build_layers() so the first build sees them.
        self._crt_on = True
        self._vignette_on = True

        # Sub-renderers + cached effect layers (rebuilt on resize / theme swap)
        self._build_layers()

        # State
        self.state: str = UIState.WATCHING
        self.osd_visible: bool = False
        self.osd_hide_at: float = 0.0
        self.volume_vis_until: float = 0.0

        # Direct channel entry — digits shown on screen as they're typed
        self.digit_entry: str = ""
        self.digit_entry_until: float = 0.0

        # On-screen menu button (shown with the info bar; opens the menu)
        self._menu_btn_hover: bool = False

        # Transient notification toast (e.g. "Added to Favorites")
        self.notification: str = ""
        self.notification_until: float = 0.0
        self._notif_shown_at: float = 0.0
        self._notif_timer = None

        # Motion. Off means every animated transition resolves instantly to its
        # end state — the same courtesy prefers-reduced-motion buys on the web,
        # which matters more here: this runs full-screen, ten feet away.
        self.reduce_motion: bool = False

        # "PLEASE STAND BY" card — set when a tune times out with no frame.
        self.standby: bool = False

        # VCR-style transport tag ("PLAY >") flashed during Plex playback.
        self._vcr_tag: str = ""
        self._vcr_tag_until: float = 0.0
        self._vcr_timer = None

        # Idle screensaver (bouncing logo) + degauss easter egg.
        self._last_activity: float = time.monotonic()
        self._degauss_on: bool = False

        # Active input device ("key" | "gamepad") — picks hint glyphs.
        self.input_mode: str = "key"

        # Download progress overlay (update downloads) — None when inactive.
        self._dl_active: bool = False
        self._dl_label: str = ""
        self._dl_frac: float = 0.0

        # Coalesced-repaint flag (set by input, drained by the render thread)
        self._dirty: bool = False

        # Channel-change transition (buffering cover -> reveal fade)
        self._cc_phase: str = "buffering"
        self._buffer_start: float = 0.0
        self._reveal_start: float = 0.0
        self._reveal_duration: float = 0.3
        self._pending_osd_timeout: float = 4.0

        # Current data refs (set by App)
        self.channels: List["Channel"] = []
        self.current_channel_idx: int = 0
        self.epg: Optional["EPG"] = None
        self.logos = None    # LogoStore (set by App); fetches channel logos
        self.weather = None  # Weather (set by App); guide-header weather
        self.volume: int = 80
        self.muted: bool = False

        # Overlay buffer file (lives in a Flatpak-shared runtime dir so the
        # sandboxed mpv can read what the host Python writes).
        self._overlay_size = width * height * 4  # BGRA
        # Use a temp sibling + atomic rename so mpv never reads a half-written
        # buffer.
        self._overlay_tmp = self._overlay_path + ".tmp"

        # The overlay file is held open across frames: reopening it per frame
        # costs ~8ms at 1080p (more than the compositing itself), and mpv keeps
        # its mmap of the same inode either way.
        self._overlay_fh = None
        self._overlay_lock = threading.Lock()

        # Background thread
        self._running = False
        self._render_error_logged = False
        self._lock = threading.Lock()

    def _build_layers(self):
        """(Re)build sub-renderers and cached effect layers for current size."""
        w, h = self.width, self.height
        self.osd        = OSD(w, h)
        self.guide      = Guide(w, h, epg_hours=self._epg_hours,
                                min_row_h=self.min_row_h)
        # Re-apply guide category state so a rebuild/resize doesn't lose it.
        self.guide.set_categories(self._guide_categories)
        self.guide.favorites = self._guide_favorites
        self.guide.set_category(self._guide_category)
        self.vignette   = make_vignette(w, h, strength=0.35)
        self._build_crt_layer()
        self.font_tuning = get_font(int(h * 0.10))   # channel number over static

    def rebuild(self):
        """Rebuild layers in place (after a font or theme change), keep state."""
        with self._lock:
            self._build_layers()
            self.menu.refresh_fonts()   # pick up new font; keep open state
            self.osk.refresh_fonts()
            self.editor.refresh_fonts()
            self.main_menu.refresh_fonts()
            self.ppv.refresh_fonts()
            self.plexinfo.refresh_fonts()
            self.plexosd.refresh_fonts()

    def resize(self, width: int, height: int):
        """Re-render at a new window resolution (e.g. handheld <-> docked)."""
        if width <= 0 or height <= 0:
            return
        if width == self.width and height == self.height:
            return
        with self._lock:
            self._clear_overlay()
            self.width = width
            self.height = height
            self._overlay_size = width * height * 4
            self._build_layers()
            self.menu.resize(width, height)
            self.osk.resize(width, height)
            self.editor.resize(width, height)
            self.main_menu.resize(width, height)
            self.ppv.resize(width, height)
            self.plexinfo.resize(width, height)
            self.plexosd.resize(width, height)
        # Re-fit the video preview to the new geometry if the guide is open.
        self._apply_video_box()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        t = threading.Thread(target=self._clock_thread, daemon=True)
        t.start()

    def stop(self):
        self._running = False
        self._clear_overlay()
        self._close_overlay_file()   # the file can't be unlinked while it's open
        for p in (self._overlay_path, self._overlay_tmp):
            try:
                os.unlink(p)
            except OSError:
                pass

    # ── State transitions (called from App) ───────────────────────────────

    def begin_channel_change(self, reveal_duration: float = 0.3):
        """Start covering the screen with static (the 'buffering' phase).

        The cover is held until reveal_channel() is called (when mpv reports
        the new stream's first frame), so it stays in sync with real loading.
        """
        self.state          = UIState.CHANNEL_CHANGING
        self._cc_phase      = "buffering"
        self._buffer_start  = time.monotonic()
        self._reveal_start  = 0.0
        self._reveal_duration = max(0.05, reveal_duration)
        self.osd_visible    = False
        self.standby        = False   # a new tune clears the stand-by card

    def reveal_channel(self, osd_timeout: float = 4.0):
        """New stream is on screen — fade the static out to reveal it."""
        if self.state != UIState.CHANNEL_CHANGING:
            return
        if self._cc_phase != "revealing":
            self._cc_phase     = "revealing"
            self._reveal_start = time.monotonic()
            self._pending_osd_timeout = osd_timeout

    def end_channel_change(self, osd_timeout: float = 4.0):
        self.state       = UIState.WATCHING
        self._cc_phase   = "buffering"
        self.osd_visible = True
        self.osd_hide_at = time.monotonic() + osd_timeout

    def show_standby(self):
        """Show the PLEASE STAND BY card (dead stream — no frame ever came)."""
        self.standby = True
        self.update()

    def clear_standby(self):
        if self.standby:
            self.standby = False
            self.update()

    def flash_vcr_tag(self, text: str, timeout: float = 1.2):
        """Flash a VCR-style transport tag ("PLAY >") top-left during Plex
        playback. The paused tag is persistent and driven by plexosd.paused."""
        self._vcr_tag = text
        self._vcr_tag_until = time.monotonic() + timeout
        if self._vcr_timer is not None:
            self._vcr_timer.cancel()
        self._vcr_timer = threading.Timer(timeout + 0.05, self.update)
        self._vcr_timer.daemon = True
        self._vcr_timer.start()
        self.update()

    def show_osd(self, timeout: float = 6.0):
        self.osd_visible = True
        self.osd_hide_at = time.monotonic() + timeout

    def hide_osd(self):
        self.osd_visible = False

    def show_digit_entry(self, text: str, timeout: float = 2.5):
        self.digit_entry = text
        self.digit_entry_until = time.monotonic() + timeout

    def clear_digit_entry(self):
        self.digit_entry = ""
        self.digit_entry_until = 0.0

    def show_volume_osd(self, timeout: float = 2.5):
        self.osd_visible       = True
        self.volume_vis_until  = time.monotonic() + timeout
        self.osd_hide_at       = max(self.osd_hide_at, self.volume_vis_until)

    # How long the toast takes to arrive and to leave. Both inside the product
    # range for state feedback; the exit is shorter than the entrance because a
    # departure that takes as long as an arrival reads as hesitation.
    NOTIF_IN  = 0.16
    NOTIF_OUT = 0.12

    def show_notification(self, text: str, timeout: float = 2.5):
        """Show a transient toast (works over any screen, incl. the guide). A
        one-shot timer re-renders when it expires so it clears itself."""
        self.notification = text
        self._notif_shown_at = time.monotonic()
        self.notification_until = time.monotonic() + timeout
        if self._notif_timer is not None:
            self._notif_timer.cancel()
        self._notif_timer = threading.Timer(timeout + 0.05, self.update)
        self._notif_timer.daemon = True
        self._notif_timer.start()
        self.update()

    def clear_notification(self):
        self.notification = ""
        self.notification_until = 0.0
        if self._notif_timer is not None:
            self._notif_timer.cancel()
            self._notif_timer = None
        self.update()

    def set_download_progress(self, label: str, frac: float):
        """Show/refresh the centered download progress bar (frac 0..1)."""
        self._dl_active = True
        self._dl_label = label
        self._dl_frac = max(0.0, min(1.0, frac))
        self.update()

    def clear_download_progress(self):
        self._dl_active = False
        self.update()

    def _draw_download_progress(self, frame: Image.Image):
        from .menu import OSD_BG, OSD_BORDER, WHITE, CHANNEL_GREEN
        d = ImageDraw.Draw(frame)
        w, h = self.width, self.height
        bw = int(w * 0.5)
        bh = int(h * 0.16)
        bx = (w - bw) // 2
        by = (h - bh) // 2
        d.rectangle([0, 0, w, h], fill=SCRIM)                     # dim behind
        d.rectangle([bx, by, bx + bw, by + bh],
                    fill=(OSD_BG[0], OSD_BG[1], OSD_BG[2], 245), outline=OSD_BORDER, width=2)
        font = get_font(max(15, int(h * 0.026)))
        pct = int(self._dl_frac * 100)
        label = self._dl_label or "Downloading..."
        d.text((bx + 20, by + 18), label, font=font, fill=WHITE)
        # Bar
        m = 20
        bar_x0, bar_x1 = bx + m, bx + bw - m
        bar_y0 = by + bh - 40
        bar_y1 = bar_y0 + 18
        # Track behind the fill, like every other bar in the app. This one was
        # outline-only, so at 0% it read as an empty box rather than as a bar
        # waiting to fill.
        d.rectangle([bar_x0, bar_y0, bar_x1, bar_y1], fill=TRACK,
                    outline=OSD_BORDER, width=1)
        fill_w = int((bar_x1 - bar_x0 - 2) * self._dl_frac)
        if fill_w > 0:
            d.rectangle([bar_x0 + 1, bar_y0 + 1, bar_x0 + 1 + fill_w, bar_y1 - 1],
                        fill=CHANNEL_GREEN)
        d.text((bar_x1 - 44, bar_y0 - 24), f"{pct}%", font=font, fill=CHANNEL_GREEN)

    def _notif_envelope(self):
        """(opacity 0..1, vertical offset px) for the toast right now.

        It drops in from above the top edge and lifts back out the same way,
        rather than blinking on and off. The toast is the app's only general
        feedback channel — "Queued", "Added to Favorites", "Update available" —
        and an instant swap gives the eye nothing to track, so a message that
        replaces another one is easy to miss entirely.
        """
        if self.reduce_motion:
            return 1.0, 0
        now = time.monotonic()
        travel = max(10, int(self.height * 0.05))
        since = now - self._notif_shown_at
        if since < self.NOTIF_IN:
            p = _ease_out_quart(since / self.NOTIF_IN)
            return p, int(-(1.0 - p) * travel)
        left = self.notification_until - now
        if left < self.NOTIF_OUT:
            p = _ease_in_quad(1.0 - max(0.0, left) / self.NOTIF_OUT)
            return 1.0 - p, int(-p * travel)
        return 1.0, 0

    def _notif_animating(self) -> bool:
        """True while the toast is arriving or leaving, so the render thread
        keeps painting instead of waiting for the next input or clock tick."""
        if not self.notification or self.reduce_motion:
            return False
        now = time.monotonic()
        return (now - self._notif_shown_at < self.NOTIF_IN
                or 0.0 < self.notification_until - now < self.NOTIF_OUT)

    def _draw_notification(self, frame: Image.Image):
        """A centered pill near the top of the screen."""
        from .menu import OSD_BG, WHITE, CHANNEL_GREEN
        opacity, dy = self._notif_envelope()
        if opacity <= 0.0:
            return
        # Drawn into its own patch so the whole pill fades as one object. The
        # fill has to stay opaque internally — it lands on the info screen's
        # title and see-through text under it reads as a glitch — so the fade
        # belongs to the composite, not to the colours.
        #
        # The patch is the size of the pill, not of the screen: this runs every
        # frame of the transition, and allocating and compositing a full 1080p
        # surface to move a 400px pill is most of a frame's budget spent on
        # empty pixels.
        box = self._notif_box()
        if box is None:
            return
        bx, by, bw, bh = box
        patch = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        self._paint_notification(patch)
        if opacity < 1.0:
            patch.putalpha(patch.getchannel("A").point(
                lambda v: int(v * opacity)))
        frame.alpha_composite(patch, (bx, by + dy))

    def _notif_box(self):
        """(x, y, w, h) of the toast pill at rest, or None when there's no
        toast. Geometry lives here so the patch can be cut to size."""
        text = self.notification
        if not text:
            return None
        d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        font = get_font(max(16, int(self.height * 0.030)))
        bb = d.textbbox((0, 0), text, font=font)
        padx, pady = 22, 12
        bw = (bb[2] - bb[0]) + padx * 2
        bh = (bb[3] - bb[1]) + pady * 2
        bx = (self.width - bw) // 2
        # Hug the top edge. At 0.10h the pill landed halfway down the Plex info
        # screen's title, leaving unreadable glyph bottoms poking out below it.
        by = max(6, int(self.height * 0.02))
        # The typed-channel digits own the top-right corner, and a pill wide
        # enough reaches them. While they're up it drops below rather than
        # printing across them.
        if self.digit_entry and time.monotonic() < self.digit_entry_until:
            db = d.textbbox((0, 0), self.digit_entry, font=self.font_tuning)
            by += (db[3] - db[1]) + max(8, int(self.height * 0.015))
        return bx, by, bw + 1, bh + 1

    def _paint_notification(self, patch: Image.Image):
        """Draw the pill into `patch`, which is exactly its size."""
        from .menu import OSD_BG, WHITE, CHANNEL_GREEN
        d = ImageDraw.Draw(patch)
        text = self.notification
        font = get_font(max(16, int(self.height * 0.030)))
        bb = d.textbbox((0, 0), text, font=font)
        padx, pady = 22, 12
        w, h = patch.width - 1, patch.height - 1
        # Opaque, not translucent: the pill lands on top of the info screen's
        # title block, and see-through text underneath reads as a glitch. The
        # transition's fade is applied to the finished patch instead.
        d.rounded_rectangle([0, 0, w, h], radius=8,
                            fill=(OSD_BG[0], OSD_BG[1], OSD_BG[2], 255),
                            outline=CHANNEL_GREEN, width=2)
        d.text((padx - bb[0], pady - bb[1]), text, font=font, fill=WHITE)

    def open_guide(self):
        self.state = UIState.GUIDE_OPEN
        self.osd_visible = False
        self.guide.set_category(self._guide_category)   # restore session category
        self._apply_video_box()

    def close_guide(self):
        # Remember the category for the rest of the session (not persisted).
        self._guide_category = self.guide.current_category()
        self.state = UIState.WATCHING
        self.player.reset_video_box()   # restore full-screen video

    def set_guide_categories(self, names):
        self._guide_categories = list(names)
        self.guide.set_categories(self._guide_categories)

    def set_guide_favorites(self, favorites):
        self._guide_favorites = set(favorites)
        self.guide.favorites = self._guide_favorites

    # Properties, not plain attributes: the tube is a cached layer, so a bare
    # `renderer.crt_on = False` would otherwise change the flag and leave the
    # old overlay compositing. app.py assigns both of these straight from
    # config at startup, which is exactly that case.

    @property
    def crt_on(self) -> bool:
        return self._crt_on

    @crt_on.setter
    def crt_on(self, on: bool):
        self._crt_on = bool(on)
        self._rebuild_crt_if_ready()

    @property
    def vignette_on(self) -> bool:
        return self._vignette_on

    @vignette_on.setter
    def vignette_on(self, on: bool):
        self._vignette_on = bool(on)
        self._rebuild_crt_if_ready()

    def _rebuild_crt_if_ready(self):
        # Guarded: the flags are set in __init__ before the layers exist.
        if hasattr(self, "vignette"):
            self._build_crt_layer()

    def _build_crt_layer(self):
        """Flatten whichever tube effects are enabled into ONE cached overlay.

        The frame then pays for a single composite instead of one per effect,
        which is what makes it affordable to run the CRT over every screen
        rather than only over video — the old code composited scanlines and
        vignette separately and so ran two passes on the paths that had them
        and none at all on the full-screen pages.
        """
        layers = []
        if self.crt_on:
            layers.append(make_crt_overlay(self.width, self.height,
                                           self._scanline_alpha))
        if self.vignette_on:
            layers.append(self.vignette)
        self.crt_layer = combine_dark_overlays(*layers) if layers else None

    def _apply_crt(self, frame: Image.Image) -> Image.Image:
        """Put the tube over a finished frame."""
        if self.crt_layer is None:
            return frame
        return Image.alpha_composite(frame, self.crt_layer)

    def _finish(self, frame: Image.Image) -> Image.Image:
        """Common tail for every screen: dialogs, then the toast, then the tube
        over all of it.

        The tube goes last on purpose. Scanlines used to be composited before
        the context menu and keyboard were drawn, so those stayed crisp while
        the page behind them was striped — which read as a modern panel
        floating outside the fiction rather than as part of the same screen.
        Everything the viewer can see is behind the same glass.
        """
        frame = self._overlay_dialogs(frame)
        self._maybe_notify(frame)
        return self._apply_crt(frame)

    def set_scanline_alpha(self, alpha: int):
        """Live-update CRT scanline intensity (0..255) and rebuild the layer."""
        self._scanline_alpha = max(0, min(255, int(alpha)))
        with self._lock:
            self._build_crt_layer()

    def set_crt(self, on: bool):
        with self._lock:
            self.crt_on = on          # the property rebuilds the tube layer

    def set_vignette(self, on: bool):
        with self._lock:
            self.vignette_on = on

    def _apply_video_box(self):
        """Render mpv's video inside the detail layout's preview box (else full
        screen).  Only meaningful while the guide is open."""
        box = self.guide.preview_box_px() if self.state == UIState.GUIDE_OPEN else None
        if box:
            # The box is in UI coordinates, but mpv's margins are ratios of the
            # whole surface. When the UI is inset those are not the same space,
            # and skipping the conversion puts the preview in the wrong place at
            # the wrong size.
            x0, y0, x1, y1 = box
            ox, oy = self.overlay_pos
            sw, sh = self.surface_size
            x0, x1, y0, y1 = x0 + ox, x1 + ox, y0 + oy, y1 + oy
            self.player.set_video_box(
                x0 / sw, (sw - x1) / sw,
                y0 / sh, (sh - y1) / sh,
            )
        else:
            self.player.reset_video_box()

    # ── Main render call ──────────────────────────────────────────────────

    def _num_patch(self):
        """Build (and cache) the top-left channel-number bitmap as a small BGRA
        patch + its alpha, for blending over the static.  Rebuilt only when the
        channel changes — drawn in a fixed vibrant green on every theme."""
        if not self.channels:
            return None
        num = str(self.channels[self.current_channel_idx].number)
        if getattr(self, "_num_patch_key", None) == (num, self.width, self.height):
            return self._num_patch_cache

        pad = max(12, int(self.width * 0.025))
        pw = max(1, int(self.width * 0.30))
        ph = max(1, int(self.height * 0.22))
        patch = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        d = ImageDraw.Draw(patch)
        d.text(
            (pad, pad), num,
            font=self.font_tuning, fill=CHANNEL_GREEN,
            stroke_width=max(2, int(self.height * 0.006)),
            stroke_fill=(0, 0, 0, 255),
        )
        parr = np.asarray(patch, dtype=np.uint16)
        pa = parr[:, :, 3:4]                       # straight alpha (ph,pw,1)
        pbgr = parr[:, :, [2, 1, 0]]               # patch colour as BGR
        self._num_patch_key = (num, self.width, self.height)
        self._num_patch_cache = (pbgr, pa, pw, ph)
        return self._num_patch_cache

    def _buffering_bgra(self) -> bytes:
        """Build an opaque static BGRA buffer directly (no PIL round-trip), with
        the channel number blended into the top-left.  Fast enough for 60fps.

        The noise is generated as a small BGRA buffer (1/block resolution) and
        upscaled with a single repeat — this gives the coarse tube-TV particles
        *and* keeps per-frame work low enough for 60fps at 1080p."""
        w, h = self.width, self.height
        b = max(1, self.STATIC_BLOCK)
        bh = (h + b - 1) // b
        bw = (w + b - 1) // b
        sg = np.random.randint(30, 240, size=(bh, bw), dtype=np.uint8)
        small = np.empty((bh, bw, 4), dtype=np.uint8)
        small[:, :, 0] = sg   # B
        small[:, :, 1] = sg   # G
        small[:, :, 2] = sg   # R
        small[:, :, 3] = 255  # opaque
        buf = np.repeat(np.repeat(small, b, axis=0), b, axis=1)[:h, :w]
        buf = np.ascontiguousarray(buf)

        patch = self._num_patch()
        if patch is not None:
            pbgr, pa, pw, ph = patch
            region = buf[:ph, :pw, :3].astype(np.uint16)
            blended = (pbgr * pa + region * (255 - pa)) // 255
            buf[:ph, :pw, :3] = blended.astype(np.uint8)
        return buf.tobytes()

    def _reveal_bgra(self, intensity: float) -> bytes:
        """Static at a uniform (premultiplied) alpha for the reveal fade — built
        directly so the fade runs at 60fps and dissolves smoothly into video."""
        w, h = self.width, self.height
        b = max(1, self.STATIC_BLOCK)
        a = int(max(0.0, min(1.0, intensity)) * 255)
        bh = (h + b - 1) // b
        bw = (w + b - 1) // b
        sg = np.random.randint(30, 240, size=(bh, bw), dtype=np.uint8)
        pg = (sg.astype(np.uint16) * a // 255).astype(np.uint8)   # premultiplied
        small = np.empty((bh, bw, 4), dtype=np.uint8)
        small[:, :, 0] = pg
        small[:, :, 1] = pg
        small[:, :, 2] = pg
        small[:, :, 3] = a
        buf = np.repeat(np.repeat(small, b, axis=0), b, axis=1)[:h, :w]
        return np.ascontiguousarray(buf).tobytes()

    def update(self):
        """Render current frame and push to MPV overlay."""
        with self._lock:
            if self.state == UIState.CHANNEL_CHANGING:
                if self._cc_phase == "buffering":
                    self._write_overlay(self._buffering_bgra())
                    return
                # revealing — fast 60fps eased fade from static to video
                progress = (time.monotonic() - self._reveal_start) / self._reveal_duration
                if progress < 1.0:
                    intensity = 1.0 - _smoothstep(progress)
                    self._write_overlay(self._reveal_bgra(intensity))
                    return
                self.end_channel_change(self._pending_osd_timeout)
                # fall through to render the now-WATCHING frame
            frame = self._render()
            if self._dl_active:
                self._draw_download_progress(frame)
        self._push_to_mpv(frame)

    def _overlay_dialogs(self, img: Image.Image) -> Image.Image:
        """Composite the shared modal layers (menu, editor, keyboard) on top.
        EVERY screen branch must end with this — a dialog that renders in one
        context but not another becomes an invisible input trap."""
        if self.menu.open:
            img = Image.alpha_composite(img, self.menu.render())
        if self.editor.open:
            img = Image.alpha_composite(img, self.editor.render())
        if self.osk.open:   # keyboard on top of everything
            img = Image.alpha_composite(img, self.osk.render())
        return img

    def _render(self) -> Image.Image:
        # The opaque full-screen pages below each draw the toast themselves —
        # they return early, so the shared _maybe_notify at the end never runs
        # for them, and actions like "+ QUEUE" would give no feedback at all.
        # They apply the tube themselves for the same reason: the whole app is
        # inside the CRT, not just the pages that happen to sit over video.

        # ── Main menu / home screen (opaque, covers everything) ───────────
        if self.main_menu.open:
            return self._finish(self.main_menu.render())

        # ── Plex-Per-View browse screen (opaque) ──────────────────────────
        if self.ppv.open:
            return self._finish(self.ppv.render())

        # ── Plex item info screen (opaque) ────────────────────────────────
        if self.plexinfo.open:
            return self._finish(self.plexinfo.render())

        now_mono = time.monotonic()

        # ── Auto-hide OSD ─────────────────────────────────────────────────
        if self.osd_visible and now_mono > self.osd_hide_at:
            self.osd_visible = False

        show_vol = now_mono < self.volume_vis_until

        # ── Guide ─────────────────────────────────────────────────────────
        if self.state == UIState.GUIDE_OPEN:
            guide_img = self.guide.render(
                self.channels,
                self.epg,
                self.current_channel_idx,
                logos=self.logos,
                weather=self.weather,
            )
            return self._finish(guide_img)

        # ── Plex-Per-View playback (its own control bar, not the channel OSD) ─
        if self.plex_playing:
            frame = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            if self.plexosd.visible:
                frame = Image.alpha_composite(frame, self.plexosd.render())
            # VCR transport tags: persistent "|| PAUSE" (with a drifting
            # tracking band, like a paused tape) or a brief "PLAY >" flash.
            if self.plexosd.paused:
                self._draw_tracking_band(frame)
                self._draw_vcr_tag(frame, "|| PAUSE")
            elif self._vcr_tag and now_mono < self._vcr_tag_until:
                self._draw_vcr_tag(frame, self._vcr_tag)
            return self._finish(frame)

        # ── Base: fully transparent (video shows through) ─────────────────
        # (The channel-change static + reveal fade are handled entirely by the
        # fast paths in update(); _render only draws the watching UI.)
        frame = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

        # ── Stand-by card (dead stream: no frame before the tune timeout) ──
        if self.standby:
            self._draw_standby(frame)

        # ── OSD ───────────────────────────────────────────────────────────
        if self.osd_visible and self.channels:
            ch = self.channels[self.current_channel_idx]
            epg_id = self.epg.resolve_channel_id(ch.epg_id, ch.name) if self.epg else None
            current_prog = self.epg.current_program(epg_id) if (self.epg and epg_id) else None
            next_prog    = self.epg.next_program(epg_id) if (self.epg and epg_id) else None

            osd_img = self.osd.render(
                channel=ch,
                current_prog=current_prog,
                next_prog=next_prog,
                volume=self.volume,
                muted=self.muted,
                show_volume=show_vol,
                epg=self.epg,
                logos=self.logos,
            )
            frame = Image.alpha_composite(frame, osd_img)

        # ── Direct channel entry (digits typed so far) ────────────────────
        if self.digit_entry and now_mono < self.digit_entry_until:
            self._draw_digit_entry(frame)

        # ── On-screen menu button (shown with the info bar) ───────────────
        if (self.osd_visible and not self.menu.open and not self.osk.open
                and not self.editor.open):
            self._draw_menu_button(frame)

        # Dialogs, toast, then the tube over all of it.
        return self._finish(frame)

    def _maybe_notify(self, img: Image.Image):
        """Draw the toast if active; clear it once expired."""
        if not self.notification:
            return
        if time.monotonic() >= self.notification_until:
            self.notification = ""
            return
        self._draw_notification(img)

    def menu_button_rect(self):
        """(x0, y0, x1, y1) of the on-screen menu button.

        The top-right corner is where a menu button lives at ten feet. Held
        upright the box is tall and that corner is out of thumb reach, so the
        button drops to sit just above the info bar, with the rest of the
        controls and inside the half of the screen a hand can actually get to.
        """
        size = max(34, self.min_row_h, int(self.height * 0.06))
        pad = max(10, int(self.width * 0.02))
        x1 = self.width - pad
        if self.width < self.height:
            y0 = max(pad, self.osd.bar_y - pad - size)
        else:
            y0 = pad
        return (x1 - size, y0, x1, y0 + size)

    def menu_button_hit(self, x: int, y: int) -> bool:
        x0, y0, x1, y1 = self.menu_button_rect()
        return x0 <= x <= x1 and y0 <= y <= y1

    def _draw_menu_button(self, frame: Image.Image):
        """A small hamburger button drawn with rectangles (no font glyphs)."""
        from .menu import OSD_BG, OSD_BORDER, WHITE, CHANNEL_GREEN
        x0, y0, x1, y1 = self.menu_button_rect()
        d = ImageDraw.Draw(frame)
        d.rounded_rectangle([x0, y0, x1, y1], radius=6, fill=OSD_BG)
        accent = CHANNEL_GREEN if self._menu_btn_hover else OSD_BORDER
        d.rounded_rectangle([x0, y0, x1, y1], radius=6, outline=accent, width=2)
        bar_w = (x1 - x0) - 16
        bx = x0 + 8
        bar_color = CHANNEL_GREEN if self._menu_btn_hover else WHITE
        for i in range(3):
            by = y0 + int((y1 - y0) * (0.32 + i * 0.18))
            d.rectangle([bx, by, bx + bar_w, by + 3], fill=bar_color)

    def _draw_digit_entry(self, frame: Image.Image):
        """Big vibrant-green digits in the top-right as the user types a channel
        number (no box, dark outline so it reads over any video)."""
        from .menu import WHITE_DIM
        d = ImageDraw.Draw(frame)
        text = self.digit_entry
        bb = d.textbbox((0, 0), text, font=self.font_tuning)
        tw = bb[2] - bb[0]
        pad = max(12, int(self.width * 0.03))
        right = self.width - pad
        # The on-screen menu button owns the top-right corner while the info bar
        # is up. Where the two share a row, the digits move in from it instead of
        # being drawn underneath it.
        mb_x0, mb_y0, _x1, _y1 = self.menu_button_rect()
        if mb_y0 < pad + (bb[3] - bb[1]):
            right = min(right, mb_x0 - max(10, int(self.width * 0.015)))
        x = right - tw - bb[0]
        d.text(
            (x, pad), text,
            font=self.font_tuning, fill=CHANNEL_GREEN,
            stroke_width=max(2, int(self.height * 0.006)),
            stroke_fill=(0, 0, 0, 255),
        )
        # Confirm hint under the digits (entry also commits on the timeout).
        # A touch host has no key to name and the timeout tunes it anyway, so
        # naming one there would be an instruction that can't be followed.
        if self.min_row_h:
            return
        hint = "[A] TUNE" if self.input_mode == "gamepad" else "[ENTER] TUNE"
        hf = get_font(max(13, int(self.height * 0.026)))
        hb = d.textbbox((0, 0), hint, font=hf)
        d.text((right - (hb[2] - hb[0]) - hb[0],
                pad + (bb[3] - bb[1]) + max(6, int(self.height * 0.012))),
               hint, font=hf, fill=WHITE_DIM,
               stroke_width=2, stroke_fill=(0, 0, 0, 255))

    @staticmethod
    def _fitted(d, text: str, px: int, max_w: int):
        """Largest font at or below `px` whose `text` fits inside `max_w`.

        The sizes here are fractions of the height while the space is a fraction
        of the width — a ratio that only holds while the box is TV-shaped.
        """
        px = max(10, int(px))
        while px > 10 and max_w > 0 and d.textlength(text, font=get_font(px)) > max_w:
            px -= 1
        return get_font(px)

    def _draw_standby(self, frame: Image.Image):
        """SMPTE bars over a dark band with PLEASE STAND BY — what a dead
        channel shows instead of dead air. Scanlines/vignette composite on
        top, and the OSD/menus still draw over it."""
        from .menu import WHITE, WHITE_DIM
        d = ImageDraw.Draw(frame)
        w, h = self.width, self.height
        split = int(h * 0.62)
        draw_smpte_bars(d, 0, 0, w, split)
        d.rectangle([0, split, w, h], fill=(10, 10, 10, 255))
        # Both lines are sized off the height and centred across the width, so
        # in a tall box they run off both edges. This is the card a dead channel
        # shows; it has to be readable, not merely present.
        gap = max(8, int(h * 0.02))
        room = w - 2 * max(16, int(w * 0.04))
        mb_x0, _y0, _x1, mb_y1 = self.menu_button_rect()
        if mb_y1 > split:
            # The menu button hangs into the dark band — upright it sits just
            # above the info bar rather than up in the corner. These lines are
            # centred, so they have to stop short of it on both sides or they
            # run underneath it.
            room = min(room, max(160, 2 * (mb_x0 - gap) - w))
        msg = "PLEASE STAND BY"
        f_big = self._fitted(d, msg, max(20, int(h * 0.065)), room)
        bb = d.textbbox((0, 0), msg, font=f_big)
        line = b2 = f_small = None
        if self.channels:
            ch = self.channels[self.current_channel_idx]
            line = f"CH {ch.number}  {ch.name} - NO SIGNAL"
            f_small = self._fitted(d, line, max(13, int(h * 0.028)), room)
            b2 = d.textbbox((0, 0), line, font=f_small)
        block_h = (bb[3] - bb[1]) + ((gap + b2[3] - b2[1]) if b2 else 0)
        ty = max(split + gap, split + ((h - split) - block_h) // 2)
        d.text(((w - (bb[2] - bb[0])) // 2 - bb[0], ty - bb[1]), msg,
               font=f_big, fill=WHITE)
        if b2:
            d.text(((w - (b2[2] - b2[0])) // 2 - b2[0],
                    ty + (bb[3] - bb[1]) + gap - b2[1]),
                   line, font=f_small, fill=WHITE_DIM)

    def _draw_vcr_tag(self, frame: Image.Image, text: str):
        """Top-left VCR-style transport tag, same treatment as the digits."""
        d = ImageDraw.Draw(frame)
        f = get_font(max(18, int(self.height * 0.05)))
        pad = max(14, int(self.width * 0.03))
        bb = d.textbbox((0, 0), text, font=f)
        d.text((pad - bb[0], pad - bb[1]), text, font=f, fill=CHANNEL_GREEN,
               stroke_width=max(2, int(self.height * 0.005)),
               stroke_fill=(0, 0, 0, 255))

    def _draw_tracking_band(self, frame: Image.Image):
        """A faint horizontal noise band that drifts down the screen while
        paused — the paused-VHS tracking look. Drifts on the clock tick."""
        h = self.height
        bh = max(4, int(h * 0.010))
        y = int(h * (0.15 + 0.70 * ((time.monotonic() * 0.02) % 1.0)))
        noise = np.random.randint(60, 220, size=(bh, self.width), dtype=np.uint8)
        band = np.dstack([noise, noise, noise,
                          np.full_like(noise, 110)])
        frame.alpha_composite(Image.fromarray(band, "RGBA"), (0, y))

    # ── Degauss easter egg ──────────────────────────────────────────────────

    # Length of the power-off collapse. Roughly a real tube's, and in the same
    # bracket as the degauss easter egg so the two feel like one machine.
    POWER_OFF = 0.44

    def power_off(self):
        """The tube going dark: the picture squashes into a bright horizontal
        line, the line shrinks to a dot, the dot fades.

        The app is called Cathode and every screen in it is pretending to be a
        television, so cutting instantly to black on quit was the one moment
        the fiction dropped. It runs on the way out, where a flourish costs
        nothing — the user has already decided to leave and nothing is waiting
        behind it. Honours the Motion toggle, and can never block the exit:
        any failure here is swallowed, because a decorative send-off must not
        be able to keep the process alive.
        """
        if self.reduce_motion:
            return
        try:
            self._power_off_run()
        except Exception:
            pass

    def _power_off_run(self):
        w, h = self.width, self.height
        cy = h // 2
        with self._lock:
            ui = self._render()
        # Composited over black: the overlay is transparent where video shows
        # through, and the collapse has to swallow the whole picture, not just
        # the parts Cathode happens to be drawing.
        base = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        base.alpha_composite(ui)
        white = Image.new("RGBA", (w, h), (255, 255, 255, 255))

        # Derived from POWER_OFF so the constant is the real duration rather
        # than a number three hardcoded phases happen to add up to.
        t_squash = self.POWER_OFF * 0.50
        t_pinch  = self.POWER_OFF * 0.27
        t_fade   = self.POWER_OFF * 0.23
        t0 = time.monotonic()
        # Deliberately not gated on self._running: this runs during shutdown,
        # after the render thread has been told to stop.
        while True:
            el = time.monotonic() - t0
            frame = Image.new("RGBA", (w, h), (0, 0, 0, 255))
            if el < t_squash:
                # Ease OUT, not in: the vertical deflection dies fast and then
                # settles. Easing in leaves the picture at full height for most
                # of the phase and then snaps to a line, which reads as a
                # glitch rather than as a tube losing its scan.
                p = _ease_out_quart(el / t_squash)
                band = max(2, int(h * (1.0 - p)))
                shot = base.resize((w, band), Image.BILINEAR)
                # Brighten after the resize, not before: the beam is dumping
                # the same energy into fewer lines, which is why the line goes
                # white — and blending a full-size white plate every frame to
                # then throw most of it away was most of the frame's cost.
                if p > 0:
                    shot = Image.blend(
                        shot, white.resize((w, band), Image.NEAREST),
                        min(0.75, p * 0.85))
                frame.paste(shot, (0, cy - band // 2))
            elif el < t_squash + t_pinch:
                p = _ease_in_quad((el - t_squash) / t_pinch)
                half = max(1, int(w * (1.0 - p) / 2))
                d = ImageDraw.Draw(frame)
                d.rectangle([w // 2 - half, cy - 1, w // 2 + half, cy + 1],
                            fill=(255, 255, 255, 255))
            elif el < t_squash + t_pinch + t_fade:
                p = (el - t_squash - t_pinch) / t_fade
                v = int(255 * (1.0 - p))
                r = max(1, int(3 * (1.0 - p)) + 1)
                d = ImageDraw.Draw(frame)
                d.ellipse([w // 2 - r, cy - r, w // 2 + r, cy + r],
                          fill=(v, v, v, 255))
            else:
                break
            self._push_to_mpv(frame)
            time.sleep(0.012)
        # Leave the tube dark rather than snapping back to the last frame.
        self._push_to_mpv(Image.new("RGBA", (w, h), (0, 0, 0, 255)))

    def degauss(self):
        """One-shot CRT degauss: the current screen wobbles and shimmers for
        ~half a second (main-menu logo easter egg)."""
        if self._degauss_on:
            return
        self._degauss_on = True
        threading.Thread(target=self._degauss_run, daemon=True).start()

    def _degauss_run(self):
        try:
            dur = 0.45
            t0 = time.monotonic()
            band = 12
            while True:
                p = (time.monotonic() - t0) / dur
                if p >= 1.0:
                    break
                with self._lock:
                    frame = self._render()
                arr = np.asarray(frame, dtype=np.uint8).copy()
                amp = (1.0 - p) ** 2 * self.width * 0.02
                for y0 in range(0, arr.shape[0], band):
                    k = int(amp * math.sin(p * 40 + y0 * 0.05))
                    if k:
                        arr[y0:y0 + band] = np.roll(arr[y0:y0 + band], k, axis=1)
                # Chroma fringe: red channel drifts a little further.
                k2 = max(1, int(amp * 0.4))
                arr[:, :, 0] = np.roll(arr[:, :, 0], k2, axis=1)
                self._push_to_mpv(Image.fromarray(arr, "RGBA"))
                time.sleep(0.03)
            self.update()   # settle on a clean frame
        finally:
            self._degauss_on = False

    # ── Idle attract mode (screensaver) ─────────────────────────────────────

    def _attract_due(self, now: float) -> bool:
        """Screensaver arms only on the idle-prone opaque screens (home /
        guide) with no dialog open; any input exits via mark_dirty()."""
        if now - self._last_activity < self.ATTRACT_AFTER:
            return False
        if not (self.main_menu.open or self.state == UIState.GUIDE_OPEN):
            return False
        return not (self.menu.open or self.osk.open or self.editor.open)

    def _attract_loop(self):
        """Bouncing CATHODE wordmark on black, DVD-logo style: corner hits
        change the color. Runs on the clock thread until any activity."""
        from . import theme
        start = self._last_activity
        w, h = self.width, self.height
        font = get_font(max(24, int(h * 0.09)))
        probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        bb = probe.textbbox((0, 0), "CATHODE", font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        x, y = w * 0.2, h * 0.3
        v = max(2.0, h * 0.006)
        vx, vy = v, v
        colors = [theme.CYAN, theme.YELLOW, CHANNEL_GREEN, theme.ORANGE,
                  theme.WHITE]
        ci = 0
        while (self._running and self._last_activity == start
               and self.width == w and self.height == h
               and (self.main_menu.open or self.state == UIState.GUIDE_OPEN)):
            x += vx
            y += vy
            bounced = False
            if x <= 0 or x + tw >= w:
                vx, bounced = -vx, True
                x = max(0.0, min(x, w - tw))
            if y <= 0 or y + th >= h:
                vy, bounced = -vy, True
                y = max(0.0, min(y, h - th))
            if bounced:
                ci = (ci + 1) % len(colors)
            frame = Image.new("RGBA", (w, h), (0, 0, 0, 255))
            ImageDraw.Draw(frame).text((int(x) - bb[0], int(y) - bb[1]),
                                       "CATHODE", font=font, fill=colors[ci])
            self._push_to_mpv(self._apply_crt(frame))
            time.sleep(0.05)
        self._dirty = True   # repaint the real screen on wake

    # ── Overlay I/O ───────────────────────────────────────────────────────

    def _push_to_mpv(self, img: Image.Image):
        # mpv's "bgra" overlay format expects *premultiplied* alpha: each colour
        # channel must already be scaled by alpha/255.  Pillow's "BGRa" raw
        # packer (lowercase 'a' = premultiplied) does the premultiply, the
        # channel swap and the serialise in one C pass — 8ms at 1080p against
        # ~57ms for the equivalent five numpy passes, which is the difference
        # between a smooth UI and a slideshow on a low-power CPU.
        self._write_overlay(_to_premultiplied_bgra(img))

    def _write_overlay(self, data: bytes):
        """Publish a BGRA buffer IN PLACE and (re)point mpv's overlay at it.

        mpv mmaps the overlay file and keeps the mapping across `overlay-add`
        calls, so the same physical file (inode) must be overwritten — an atomic
        rename would swap in a fresh inode that mpv never re-reads, which freezes
        the 60fps channel-change static after the first frame.  Writing in place
        keeps the mapping live; a partially-written frame can only tear for one
        16ms frame, which is invisible.

        The handle stays open between frames: reopening it costs ~8ms at 1080p,
        more than compositing the frame in the first place.
        """
        try:
            with self._overlay_lock:
                f = self._overlay_fh
                if f is None or f.closed:
                    try:
                        f = open(self._overlay_path, "r+b")
                    except FileNotFoundError:
                        f = open(self._overlay_path, "wb+")
                    self._overlay_fh = f
                f.seek(0)
                f.write(data)
                f.flush()
        except OSError:
            self._close_overlay_file()   # reopen from scratch on the next frame
            return
        try:
            ox, oy = self.overlay_pos
            self.player.command(
                "overlay-add",
                1, ox, oy,
                self._overlay_path, 0,
                "bgra",
                self.width, self.height, self.width * 4,
            )
        except Exception:
            pass  # mpv may not be ready yet

    def _close_overlay_file(self):
        with self._overlay_lock:
            try:
                if self._overlay_fh is not None:
                    self._overlay_fh.close()
            except OSError:
                pass
            self._overlay_fh = None

    def _clear_overlay(self):
        try:
            self.player.command("overlay-remove", 1)
        except Exception:
            pass

    # ── Background render thread ───────────────────────────────────────────

    def _clock_thread(self):
        """
        Drives refreshes:
          • During a channel change, render fast (STATIC_FPS) so the static
            noise actually animates.
          • Otherwise tick once per second so the OSD clock advances.
        """
        frame_budget = 1.0 / self.STATIC_FPS
        next_clock = time.monotonic()
        while self._running:
            # A render error must never kill this thread — that would freeze all
            # graphics (OSD, guide, menus, static) until the app is restarted.
            try:
                if self.state == UIState.CHANNEL_CHANGING:
                    t0 = time.monotonic()
                    self.update()
                    # Sleep only the remainder of the frame budget so the actual
                    # rate approaches STATIC_FPS instead of (render + full sleep).
                    time.sleep(max(0.0, frame_budget - (time.monotonic() - t0)))
                    next_clock = time.monotonic()  # reset slow tick
                else:
                    now = time.monotonic()
                    if self._dirty:
                        # Coalesced repaint requested by input (e.g. mouse hover,
                        # menu/keyboard interaction) — render at most every poll.
                        self._dirty = False
                        self.update()
                        next_clock = now + self.CLOCK_TICK
                    elif self._notif_animating():
                        # The toast is arriving or leaving. Outside a channel
                        # change this loop only paints on input or once a
                        # second, so a short transition needs its own reason to
                        # keep drawing; the 50Hz poll below is the frame clock.
                        self.update()
                    elif self._attract_due(now):
                        self._attract_loop()
                        next_clock = time.monotonic() + self.CLOCK_TICK
                    elif now >= next_clock:
                        next_clock = now + self.CLOCK_TICK
                        # Only tick the OSD clock while plainly watching.
                        if (self.state != UIState.GUIDE_OPEN
                                and not self.menu.open and not self.osk.open
                                and not self.editor.open and not self.main_menu.open):
                            self.update()
                    time.sleep(0.02)
            except Exception:
                # Still never fatal — a dead render thread means no graphics at
                # all until restart. But report it once: a repeating exception
                # here looks exactly like a black screen with nothing wrong,
                # which is expensive to diagnose from the outside.
                if not self._render_error_logged:
                    self._render_error_logged = True
                    traceback.print_exc()
                time.sleep(0.02)

    def mark_dirty(self):
        """Request a repaint on the next render-thread tick (coalesces many
        rapid input events into a single render — keeps the IPC reader free).
        Doubles as the activity signal that resets / exits the screensaver."""
        self._last_activity = time.monotonic()
        self._dirty = True
