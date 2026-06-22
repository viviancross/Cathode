"""Main UI renderer — composites all layers and writes MPV overlay buffer."""

from __future__ import annotations

import os
import time
import threading
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
from .screensaver import Screensaver
from .effects import (
    make_scanline_cache,
    make_vignette,
)
from .theme import get_font, CHANNEL_GREEN

if TYPE_CHECKING:
    from ..epg import EPG
    from ..playlist import Channel
    from ..player import Player


def _smoothstep(t: float) -> float:
    """Ease-in-out 0..1 -> 0..1 for a gentler fade than a linear ramp."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


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
        self._scanline_alpha = scanline_alpha
        self._epg_hours = epg_hours
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
        self.screensaver = Screensaver(width, height)   # idle bouncing-logo overlay
        self.plex_playing = False             # a Plex item is the current video

        # CRT scanline / vignette toggles (driven by the theme editor)
        self.crt_on = True
        self.vignette_on = True

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
        self._notif_timer = None

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

        # Background thread
        self._running = False
        self._lock = threading.Lock()

    def _build_layers(self):
        """(Re)build sub-renderers and cached effect layers for current size."""
        w, h = self.width, self.height
        self.osd        = OSD(w, h)
        self.guide      = Guide(w, h, epg_hours=self._epg_hours)
        # Re-apply guide category state so a rebuild/resize doesn't lose it.
        self.guide.set_categories(self._guide_categories)
        self.guide.favorites = self._guide_favorites
        self.guide.set_category(self._guide_category)
        self.scanlines  = make_scanline_cache(w, h, self._scanline_alpha)
        self.vignette   = make_vignette(w, h, strength=0.35)
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
            self.screensaver.refresh_fonts()

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
            self.screensaver.resize(width, height)
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

    def show_notification(self, text: str, timeout: float = 2.5):
        """Show a transient toast (works over any screen, incl. the guide). A
        one-shot timer re-renders when it expires so it clears itself."""
        self.notification = text
        self.notification_until = time.monotonic() + timeout
        if self._notif_timer is not None:
            self._notif_timer.cancel()
        self._notif_timer = threading.Timer(timeout + 0.05, self.update)
        self._notif_timer.daemon = True
        self._notif_timer.start()
        self.update()

    def _draw_notification(self, frame: Image.Image):
        """A centered pill near the top of the screen."""
        from .menu import OSD_BG, WHITE, CHANNEL_GREEN
        d = ImageDraw.Draw(frame)
        text = self.notification
        font = get_font(max(16, int(self.height * 0.030)))
        bb = d.textbbox((0, 0), text, font=font)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        padx, pady = 22, 12
        bw, bh = tw + padx * 2, th + pady * 2
        bx = (self.width - bw) // 2
        by = int(self.height * 0.10)
        d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=8,
                            fill=(OSD_BG[0], OSD_BG[1], OSD_BG[2], 235),
                            outline=CHANNEL_GREEN, width=2)
        d.text((bx + padx - bb[0], by + pady - bb[1]), text, font=font, fill=WHITE)

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

    def set_scanline_alpha(self, alpha: int):
        """Live-update CRT scanline intensity (0..255) and rebuild the layer."""
        self._scanline_alpha = max(0, min(255, int(alpha)))
        with self._lock:
            self.scanlines = make_scanline_cache(
                self.width, self.height, self._scanline_alpha)

    def set_crt(self, on: bool):
        self.crt_on = bool(on)

    def set_vignette(self, on: bool):
        self.vignette_on = bool(on)

    def _apply_video_box(self):
        """Render mpv's video inside the detail layout's preview box (else full
        screen).  Only meaningful while the guide is open."""
        box = self.guide.preview_box_px() if self.state == UIState.GUIDE_OPEN else None
        if box:
            x0, y0, x1, y1 = box
            self.player.set_video_box(
                x0 / self.width, (self.width - x1) / self.width,
                y0 / self.height, (self.height - y1) / self.height,
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
            if self.screensaver.active:
                frame = Image.alpha_composite(frame, self.screensaver.render())
        self._push_to_mpv(frame)

    def _render(self) -> Image.Image:
        # ── Main menu / home screen (opaque, covers everything) ───────────
        if self.main_menu.open:
            img = self.main_menu.render()
            if self.menu.open:
                img = Image.alpha_composite(img, self.menu.render())
            if self.editor.open:
                img = Image.alpha_composite(img, self.editor.render())
            if self.osk.open:
                img = Image.alpha_composite(img, self.osk.render())
            return img

        # ── Plex-Per-View browse screen (opaque) ──────────────────────────
        if self.ppv.open:
            img = self.ppv.render()
            if self.menu.open:
                img = Image.alpha_composite(img, self.menu.render())
            if self.osk.open:
                img = Image.alpha_composite(img, self.osk.render())
            return img

        # ── Plex item info screen (opaque) ────────────────────────────────
        if self.plexinfo.open:
            img = self.plexinfo.render()
            if self.menu.open:
                img = Image.alpha_composite(img, self.menu.render())
            return img

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
            if self.crt_on:
                guide_img = Image.alpha_composite(guide_img, self.scanlines)
            if self.menu.open:
                guide_img = Image.alpha_composite(guide_img, self.menu.render())
            if self.editor.open:
                guide_img = Image.alpha_composite(guide_img, self.editor.render())
            if self.osk.open:   # keyboard on top of everything
                guide_img = Image.alpha_composite(guide_img, self.osk.render())
            self._maybe_notify(guide_img)
            return guide_img

        # ── Plex-Per-View playback (its own control bar, not the channel OSD) ─
        if self.plex_playing:
            frame = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            if self.plexosd.visible:
                frame = Image.alpha_composite(frame, self.plexosd.render())
            if self.crt_on:
                frame = Image.alpha_composite(frame, self.scanlines)
            if self.vignette_on:
                frame = Image.alpha_composite(frame, self.vignette)
            if self.menu.open:
                frame = Image.alpha_composite(frame, self.menu.render())
            if self.osk.open:
                frame = Image.alpha_composite(frame, self.osk.render())
            self._maybe_notify(frame)
            return frame

        # ── Base: fully transparent (video shows through) ─────────────────
        # (The channel-change static + reveal fade are handled entirely by the
        # fast paths in update(); _render only draws the watching UI.)
        frame = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

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

        # ── Scanlines (CRT toggle) ────────────────────────────────────────
        if self.crt_on:
            frame = Image.alpha_composite(frame, self.scanlines)

        # ── Vignette (toggle) ─────────────────────────────────────────────
        if self.vignette_on:
            frame = Image.alpha_composite(frame, self.vignette)

        # ── On-screen menu button (shown with the info bar) ───────────────
        if (self.osd_visible and not self.menu.open and not self.osk.open
                and not self.editor.open):
            self._draw_menu_button(frame)

        # ── Context menu / theme editor / keyboard (on top of everything) ─
        if self.menu.open:
            frame = Image.alpha_composite(frame, self.menu.render())
        if self.editor.open:
            frame = Image.alpha_composite(frame, self.editor.render())
        if self.osk.open:   # keyboard renders above the editor when naming
            frame = Image.alpha_composite(frame, self.osk.render())

        self._maybe_notify(frame)
        return frame

    def _maybe_notify(self, img: Image.Image):
        """Draw the toast if active; clear it once expired."""
        if not self.notification:
            return
        if time.monotonic() >= self.notification_until:
            self.notification = ""
            return
        self._draw_notification(img)

    def menu_button_rect(self):
        """(x0, y0, x1, y1) of the on-screen menu button (top-right)."""
        size = max(34, int(self.height * 0.06))
        pad = max(10, int(self.width * 0.02))
        x1 = self.width - pad
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
        d = ImageDraw.Draw(frame)
        text = self.digit_entry
        bb = d.textbbox((0, 0), text, font=self.font_tuning)
        tw = bb[2] - bb[0]
        pad = max(12, int(self.width * 0.03))
        x = self.width - tw - pad - bb[0]
        d.text(
            (x, pad), text,
            font=self.font_tuning, fill=CHANNEL_GREEN,
            stroke_width=max(2, int(self.height * 0.006)),
            stroke_fill=(0, 0, 0, 255),
        )

    # ── Overlay I/O ───────────────────────────────────────────────────────

    def _push_to_mpv(self, img: Image.Image):
        arr = np.asarray(img, dtype=np.uint8)   # RGBA, shape (H, W, 4)

        # mpv's "bgra" overlay format expects *premultiplied* alpha:
        # each colour channel must already be scaled by alpha/255.
        rgb   = arr[:, :, :3].astype(np.uint16)
        alpha = arr[:, :, 3:4].astype(np.uint16)
        pm    = (rgb * alpha // 255).astype(np.uint8)   # premultiply
        bgra = np.dstack([
            pm[:, :, 2],          # B
            pm[:, :, 1],          # G
            pm[:, :, 0],          # R
            arr[:, :, 3],         # A (straight)
        ])
        self._write_overlay(np.ascontiguousarray(bgra).tobytes())

    def _write_overlay(self, data: bytes):
        """Publish a BGRA buffer IN PLACE and (re)point mpv's overlay at it.

        mpv mmaps the overlay file and keeps the mapping across `overlay-add`
        calls, so the same physical file (inode) must be overwritten — an atomic
        rename would swap in a fresh inode that mpv never re-reads, which freezes
        the 60fps channel-change static after the first frame.  Writing in place
        keeps the mapping live; a partially-written frame can only tear for one
        16ms frame, which is invisible.
        """
        try:
            # r+b updates the existing inode; create it the first time.
            try:
                f = open(self._overlay_path, "r+b")
            except FileNotFoundError:
                f = open(self._overlay_path, "wb")
            with f:
                f.seek(0)
                f.write(data)
        except OSError:
            return
        try:
            self.player.command(
                "overlay-add",
                1, 0, 0,
                self._overlay_path, 0,
                "bgra",
                self.width, self.height, self.width * 4,
            )
        except Exception:
            pass  # mpv may not be ready yet

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
                    elif now >= next_clock:
                        next_clock = now + self.CLOCK_TICK
                        # Only tick the OSD clock while plainly watching.
                        if (self.state != UIState.GUIDE_OPEN
                                and not self.menu.open and not self.osk.open
                                and not self.editor.open and not self.main_menu.open):
                            self.update()
                    time.sleep(0.02)
            except Exception:
                time.sleep(0.02)

    def mark_dirty(self):
        """Request a repaint on the next render-thread tick (coalesces many
        rapid input events into a single render — keeps the IPC reader free)."""
        self._dirty = True
