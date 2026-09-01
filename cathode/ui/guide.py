"""Program guide overlay — 80s-style cable TV grid."""

from __future__ import annotations
import math
from datetime import datetime, timezone, timedelta
from typing import List, Optional, TYPE_CHECKING

from PIL import Image, ImageDraw

from . import theme
from .effects import draw_smpte_bars
from .theme import (
    get_font, measure, text_wh,
    GUIDE_BG, GUIDE_HEADER_BG, GUIDE_ROW_ODD, GUIDE_ROW_EVEN,
    GUIDE_CURRENT, GUIDE_SELECTED, GUIDE_ONAIR, GUIDE_TIME_BG, GUIDE_BORDER,
    WHITE, WHITE_DIM, CYAN, YELLOW, RED, INK_MUTED,
    ORANGE, OSD_BORDER, OSD_BG,
    SEL_TEXT, SEL_TEXT_DIM, ONAIR_TEXT,
)

if TYPE_CHECKING:
    from ..epg import EPG, Program
    from ..playlist import Channel


_GUIDE_TITLE = "  CABLE GUIDE  "


def _fmt(dt: datetime, fmt: str) -> str:
    """strftime without glibc-only %-I / %-d codes (portable to Windows)."""
    return dt.strftime(fmt)


def _time_label(dt: datetime) -> str:
    local = dt.astimezone()
    return local.strftime("%I:%M %p").lstrip("0")


def _prog_range(prog: "Program") -> str:
    return f"{_time_label(prog.start)} - {_time_label(prog.stop)}"


def _is_night() -> bool:
    h = datetime.now().astimezone().hour
    return h >= 20 or h < 6


def _moon_phase(now: Optional[datetime] = None) -> float:
    """0..1 through the synodic month (0 = new, 0.5 = full)."""
    now = now or datetime.now(timezone.utc)
    ref = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)   # a known new moon
    days = (now - ref).total_seconds() / 86400.0
    return (days % 29.530588853) / 29.530588853


def _wrap_text(draw, text: str, font, max_w: int, max_lines: int) -> list:
    """Word-wrap `text` to fit `max_w` px, up to `max_lines` lines."""
    if not text or max_lines <= 0:
        return []
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if measure(draw, trial, font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    # Mark truncation if text didn't fully fit
    if len(lines) == max_lines:
        joined = " ".join(lines)
        if len(joined) < len(text):
            lines[-1] = _truncate(lines[-1] + " ...", draw, font, max_w)
    return lines


def _text_size(draw: ImageDraw.Draw, text: str, font) -> tuple:
    return text_wh(draw, text, font)


def _truncate(text: str, draw: ImageDraw.Draw, font, max_w: int) -> str:
    return theme.ellipsize(draw, text, font, max_w)


class Guide:
    """Renders a full-screen retro program guide grid."""

    # Layout constants (as fractions of width/height)
    PADDING          = 0.02
    HEADER_H_FRAC    = 0.07
    TIME_ROW_H_FRAC  = 0.045
    ROW_H_FRAC       = 0.075
    CH_COL_W_FRAC    = 0.14
    DETAIL_PANEL_FRAC = 0.36   # height of the info panel in the "detail" layout
                               # (tall enough for the synopsis to wrap a few lines)

    def __init__(self, width: int, height: int, epg_hours: int = 3,
                 min_row_h: int = 0):
        self.width = width
        self.height = height
        # What the user asked for; the window actually drawn is narrowed to fit
        # (see _compute_geometry), and a resize back to a wide box restores it.
        self._epg_hours_req = epg_hours
        self.epg_hours = epg_hours
        # Physical floor for touch hosts (px). A constructor argument, not
        # an attribute set afterwards: the geometry is computed during init.
        self.min_row_h = min_row_h

        # State (defined before geometry so a resize can clamp against it)
        self.scroll_offset = 0   # index of first visible channel (within category)
        self.selected_row  = 0   # selected row index (0..visible_rows-1)
        self.time_offset_min = 0 # minutes from "now" window starts

        # Categories: a selector above the grid filters channels by genre.
        self.categories = ["All", "Favorites"]
        self.category_idx = 0
        self.focus = "grid"      # "grid" | "category" — what arrows act on
        self.favorites = set()   # channel numbers
        self._channels = []      # last full channel list (kept for nav/filter)

        self._compute_geometry()

    def _compute_geometry(self):
        """Compute layout metrics.  A top info panel (with the live-video preview
        window) pushes the channel grid down and shrinks it."""
        width, height = self.width, self.height
        # The grid is laid out for a television. Held upright the same fractions
        # spend the box the wrong way round: a third of the height on the info
        # panel, a seventh of the width on channel names that then truncate.
        self.portrait = width < height
        self.pad      = int(width * self.PADDING)
        nominal_header = int(height * (0.052 if self.portrait else self.HEADER_H_FRAC))
        # The header carries the only close button, so on a touch host it has to
        # be at least a thumb tall — but the title keeps its nominal size, or it
        # would grow with the button.
        self.header_h = max(nominal_header,
                            (self.min_row_h + 8) if self.min_row_h else 0)
        self.time_row_h = int(height * (0.034 if self.portrait
                                        else self.TIME_ROW_H_FRAC))
        self.ch_col_w = int(width * (0.24 if self.portrait else self.CH_COL_W_FRAC))
        self.panel_h = int(height * (0.21 if self.portrait
                                     else self.DETAIL_PANEL_FRAC))
        self.cat_bar_h = max(26, int(height * 0.045))   # category selector strip
        self.time_ruler_y = self.header_h + self.panel_h
        # Three hours across a phone held upright is a half-hour cell about ten
        # characters wide, and every programme in it renders as "S...". Fewer
        # hours of real titles beats more hours of ellipses; what's on now is
        # what the guide is opened for anyway.
        self.epg_hours = (min(self._epg_hours_req, 2) if self.portrait
                          else self._epg_hours_req)

        # A touch host raises the floor: fewer channels on screen, but every one
        # of them big enough to hit. Proportional rows are ~4mm on a phone.
        nominal_row = max(1, int(height * self.ROW_H_FRAC),
                          getattr(self, "min_row_h", 0))
        # A third of the height on the info panel is still eight or nine rows of
        # grid on a television. On a short box — a cover screen, a small window,
        # anything with a touch floor — the same third leaves four, and a guide
        # showing four channels is a list. The panel gives the rows back.
        chrome = self.header_h + self.time_row_h + 2 * self.pad
        if height - chrome - self.panel_h < 6 * nominal_row:
            self.panel_h = max(int(height * 0.20),
                               height - chrome - 6 * nominal_row)
            self.time_ruler_y = self.header_h + self.panel_h

        # Fit as many rows as the (remaining) space allows, then stretch row
        # height so the grid fills to the bottom.
        inner_h = height - self.header_h - self.panel_h - self.time_row_h - 2 * self.pad
        self.visible_rows = max(1, inner_h // nominal_row)
        self.row_h = inner_h // self.visible_rows

        self.grid_x = self.pad + self.ch_col_w
        self.grid_w = width - self.pad - self.grid_x
        self.grid_y = self.time_ruler_y + self.time_row_h

        # Fonts
        self.font_title  = get_font(int(nominal_header * 0.45))
        self.font_time   = get_font(int(self.time_row_h * 0.55))
        self.font_ch     = get_font(int(self.row_h * 0.30))
        self.font_prog   = get_font(int(self.row_h * 0.28))
        self._small_px   = int(self.row_h * 0.22)
        self.font_small  = get_font(self._small_px)
        # The panel's text is sized against the panel, not the display: upright
        # the panel is a third of the height it has on a television, and a font
        # picked from the display would print two lines into it.
        if self.portrait:
            self.font_panel_title = get_font(max(14, int(self.panel_h * 0.11)))
            self.font_panel_text  = get_font(max(11, int(self.panel_h * 0.08)))
        else:
            self.font_panel_title = get_font(max(14, int(height * 0.045)))
            self.font_panel_text  = get_font(max(11, int(height * 0.028)))

        # The close button is sized to its label so it can't clip, and to a
        # thumb where one is expected.
        _d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        self.close_w = max(96, int(width * 0.085),
                           int(_d.textlength("X CLOSE", font=self.font_time)) + 24)
        self.close_h = min(self.header_h - 6,
                           max(26, self.min_row_h, int(self.header_h * 0.52)))

        # Keep the cursor on a visible row after a geometry change
        if self.selected_row > self.visible_rows - 1:
            self.selected_row = self.visible_rows - 1

    def preview_box_px(self):
        """Pixel rect (x0, y0, x1, y1) of the live-video preview window — the
        full-height left column of the info panel."""
        pad = self.pad
        top = self.header_h + pad
        bottom = self.header_h + self.panel_h - pad
        lx = pad
        # Shape the window like the video that goes in it. A fixed share of the
        # width is a 16:9 window only on a panel of one particular height; on a
        # short one it stretches into a letterbox slot, and upright it becomes a
        # column that pillarboxes the preview down to a sliver.
        lw = min(int(self.width * (0.46 if self.portrait else 0.30)),
                 int((bottom - top) * 16 / 9))
        return (lx, top, lx + lw, bottom)

    def close_rect_px(self):
        """Pixel rect of the guide's close button, at the right of the header.

        The guide is closed by B / Escape / the guide key, none of which exist on
        a phone -- and the system back gesture is a step up, not something the
        screen advertises. So the way out is drawn where it can be seen.
        """
        pad = self.pad
        w, h = self.close_w, self.close_h
        x1 = self.width - pad
        y0 = (self.header_h - h) // 2
        return (x1 - w, y0, x1, y0 + h)

    def hit_row(self, x, y):
        """Visible grid row under (x, y), or None.

        Covers the channel column and the programme cells alike: on a
        touchscreen the whole row is the target, because aiming at a particular
        programme cell to select its channel is a distinction without a
        difference.
        """
        if y < self.grid_y or x < self.pad:
            return None
        row = int((y - self.grid_y) // self.row_h)
        if row < 0 or row >= self.visible_rows:
            return None
        if self.scroll_offset + row >= len(self.filtered()):
            return None          # empty space below the last channel
        return row

    def hit_close(self, x, y) -> bool:
        x0, y0, x1, y1 = self.close_rect_px()
        return x0 <= x <= x1 and y0 <= y <= y1

    def category_bar_px(self):
        """Pixel rect of the highlightable category selector (◄ cat ►), a bar
        across the top of the panel's right region (beside the preview window)."""
        pad = self.pad
        _bx0, _by0, bx1, _by1 = self.preview_box_px()
        x0 = bx1 + pad
        x1 = self.width - pad
        y0 = self.header_h + pad
        y1 = y0 + self.cat_bar_h
        return (x0, y0, x1, y1)

    # ── Categories ────────────────────────────────────────────────────────

    def set_categories(self, names):
        """Replace the category list, keeping the current selection by name."""
        cur = self.current_category()
        self.categories = list(names) if names else ["All"]
        self.set_category(cur)

    def set_category(self, name: str):
        if name in self.categories:
            self.category_idx = self.categories.index(name)
        else:
            self.category_idx = 0
        self._clamp_position()

    def current_category(self) -> str:
        if 0 <= self.category_idx < len(self.categories):
            return self.categories[self.category_idx]
        return "All"

    def _cycle_category(self, delta: int):
        if not self.categories:
            return
        self.category_idx = (self.category_idx + delta) % len(self.categories)
        self.scroll_offset = 0
        self.selected_row = 0

    def filtered(self):
        """Channels visible under the current category."""
        cat = self.current_category()
        chans = self._channels
        if cat == "All":
            return chans
        if cat == "Favorites":
            return [c for c in chans if c.number in self.favorites]
        return [c for c in chans if getattr(c, "category", "") == cat]

    def _clamp_position(self):
        total = len(self.filtered())
        max_first = max(0, total - self.visible_rows)
        self.scroll_offset = max(0, min(self.scroll_offset, max_first))
        self.selected_row = max(0, min(self.selected_row,
                                       max(0, min(self.visible_rows, total) - 1)))

    # ── Public interface ─────────────────────────────────────────────────────

    def move_up(self):
        if self.focus == "category":
            vis = self.filtered()                 # wrap up into the grid's bottom
            if vis:
                self.focus = "grid"
                self._set_index(len(vis) - 1, len(vis))
            return
        if self.selected_row > 0:
            self.selected_row -= 1
        elif self.scroll_offset > 0:
            self.scroll_offset -= 1
        else:
            self.focus = "category"               # past the top → category selector

    def move_down(self):
        total = len(self.filtered())
        if self.focus == "category":
            self.focus = "grid"
            self._set_index(0, total)
            return
        if total == 0 or self.scroll_offset + self.selected_row >= total - 1:
            self.focus = "category"               # past the bottom → category selector
            return
        max_row = min(self.visible_rows - 1, total - self.scroll_offset - 1)
        if self.selected_row < max_row:
            self.selected_row += 1
        elif self.scroll_offset + self.visible_rows < total:
            self.scroll_offset += 1

    def _set_index(self, idx: int, total_channels: int):
        """Position the selection on filtered-list index `idx`, adjusting scroll
        to keep it visible."""
        if total_channels <= 0:
            self.scroll_offset = self.selected_row = 0
            return
        vis = max(1, self.visible_rows)
        idx = max(0, min(idx, total_channels - 1))
        self.scroll_offset = max(0, min(idx - vis + 1, total_channels - vis)) if idx >= vis else 0
        self.scroll_offset = max(0, self.scroll_offset)
        self.selected_row = idx - self.scroll_offset

    def move_left(self):
        if self.focus == "category":
            self._cycle_category(-1)
        else:
            self.time_offset_min = max(0, self.time_offset_min - 30)

    def move_right(self):
        if self.focus == "category":
            self._cycle_category(1)
        else:
            self.time_offset_min = min(self.epg_hours * 60 - 30, self.time_offset_min + 30)

    def selected_channel(self):
        """The highlighted Channel in the current category, or None."""
        if self.focus != "grid":
            return None
        vis = self.filtered()
        i = self.scroll_offset + self.selected_row
        return vis[i] if 0 <= i < len(vis) else None

    def jump_to_channel(self, channels: list, idx: int):
        """Open positioned on channel `idx` (full-list index) if it's in the
        current category; otherwise on the top of the category."""
        self._channels = channels
        self.focus = "grid"
        vis = self.filtered()
        target = channels[idx] if 0 <= idx < len(channels) else None
        pos = vis.index(target) if target in vis else 0
        self._set_index(pos, len(vis))

    def render(
        self,
        channels: List["Channel"],
        epg: Optional["EPG"],
        current_channel_idx: int,
        logos=None,
        weather=None,
    ) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        self._logos = logos
        self._img = img    # for pasting logos in channel rows
        # Cached weather summary (None until first fetch / when no zip set).
        self._weather = weather.current() if weather is not None else None

        now = datetime.now(timezone.utc)
        window_start = now + timedelta(minutes=self.time_offset_min)
        window_end   = window_start + timedelta(hours=self.epg_hours)

        # ── Full-screen background ────────────────────────────────────────
        draw.rectangle([0, 0, self.width, self.height], fill=GUIDE_BG)

        # ── Header bar ────────────────────────────────────────────────────
        self._draw_header(draw, now)

        self._channels = channels
        vis = self.filtered()
        cur_ch = (channels[current_channel_idx]
                  if 0 <= current_channel_idx < len(channels) else None)

        # ── Info panel (with the live-video preview window) ───────────────
        self._draw_detail_panel(draw, channels, epg, current_channel_idx, now, vis)

        # ── Category selector ─────────────────────────────────────────────
        self._draw_category_bar(draw)

        # ── Time ruler ────────────────────────────────────────────────────
        self._draw_time_ruler(draw, window_start, window_end, now)

        # ── Channel rows (filtered by category) ───────────────────────────
        visible = vis[self.scroll_offset : self.scroll_offset + self.visible_rows]
        for i, ch in enumerate(visible):
            row_y = self.grid_y + i * self.row_h
            is_selected = (self.focus == "grid" and i == self.selected_row)
            is_current  = (cur_ch is not None and ch is cur_ch)

            self._draw_channel_row(
                draw, ch, i, row_y,
                window_start, window_end, now,
                epg, is_selected, is_current,
            )
        if not vis:
            # Off-air motif: a small test-bar strip above the message.
            bar_h = max(14, int(self.row_h * 0.5))
            draw_smpte_bars(draw, self.grid_x + 8, self.grid_y + 8,
                            self.grid_x + 8 + int(self.grid_w * 0.32),
                            self.grid_y + 8 + bar_h)
            line_h = _text_size(draw, "Ag", self.font_small)[1] + 8
            ty = self.grid_y + 8 + bar_h + 10
            self._text((self.grid_x + 8, ty),
                       "No channels in this category",
                       self.font_small, INK_MUTED)
            self._text((self.grid_x + 8, ty + line_h),
                       "Pick another category above with < >",
                       self.font_small, WHITE_DIM)

        # ── Scroll indicators ─────────────────────────────────────────────
        if self.scroll_offset > 0:
            self._draw_scroll_arrow(draw, up=True)
        if self.scroll_offset + self.visible_rows < len(vis):
            self._draw_scroll_arrow(draw, up=False)

        # ── Border ────────────────────────────────────────────────────────
        draw.rectangle(
            [0, 0, self.width - 1, self.height - 1],
            outline=GUIDE_BORDER, width=2,
        )

        return img

    # ── Private render helpers ────────────────────────────────────────────────

    def _text(self, xy, text, font, fill, stroke_width=0, stroke_fill=None):
        """Draw cached text onto the current frame (self._img). Heavy pixel fonts
        only rasterize each string once; repeats are a cheap alpha-paste."""
        theme.draw_text(self._img, xy, text, font, fill,
                        stroke_width=stroke_width, stroke_fill=stroke_fill)

    def _draw_header(self, draw: ImageDraw.Draw, now: datetime):
        draw.rectangle([0, 0, self.width, self.header_h], fill=GUIDE_HEADER_BG)
        draw.rectangle(
            [0, self.header_h - 2, self.width, self.header_h],
            fill=OSD_BORDER,
        )

        # The title, the clock and the close button share one row, and which of
        # them has to give way depends on how wide that row is — not on which
        # way round the box happens to be. Both concessions are made by
        # measurement, so a phone upright, a cover screen and a television all
        # get a header that fits.
        tw, th = _text_size(draw, _GUIDE_TITLE, self.font_title)
        # The close button owns the right edge; the clock sits inside it.
        cx0, cy0, cx1, cy1 = self.close_rect_px()
        local = now.astimezone()
        time_str = (
            local.strftime("%I:%M:%S %p").lstrip("0")
            + local.strftime("  %a %b ")
            + str(local.day)
        )
        tw2, _ = _text_size(draw, time_str, self.font_time)
        centred = (self.width - tw) // 2
        # First concession: seconds and the date, the least useful of what's
        # here, in exchange for a centred title.
        if centred + tw > cx0 - 2 * self.pad - tw2:
            time_str = local.strftime("%I:%M %p").lstrip("0")
            tw2, _ = _text_size(draw, time_str, self.font_time)
        clock_x = cx0 - self.pad - tw2
        # Second: the title stops being centred and takes the left edge, so the
        # row reads left to right — what this is, the weather, the time, the way
        # out — instead of printing itself over the clock.
        title_left = centred if centred + tw <= clock_x - self.pad else self.pad
        self._text(
            (title_left, (self.header_h - th) // 2),
            _GUIDE_TITLE, self.font_title, YELLOW,
        )
        self._text(
            (clock_x, (self.header_h - th) // 2),
            time_str, self.font_time, CYAN,
        )

        # Close button (far right).
        draw.rectangle([cx0, cy0, cx1, cy1],
                       fill=(OSD_BG[0], OSD_BG[1], OSD_BG[2], 255),
                       outline=OSD_BORDER, width=2)
        lw, lh = _text_size(draw, "X CLOSE", self.font_time)
        self._text((cx0 + (cx1 - cx0 - lw) // 2,
                    cy0 + (cy1 - cy0 - lh) // 2 - 2),
                   "X CLOSE", self.font_time, CYAN)

        # Weather on the LEFT (roomy, so it never truncates).  The keybind hint
        # that used to live here is now covered by the context menu.
        # Weather takes whatever side of the title is free: the space left of a
        # centred one, the space right of a left-aligned one.
        if self._weather:
            if title_left > self.pad:
                left, limit = self.pad, title_left - self.pad
            else:
                left, limit = title_left + tw + self.pad, clock_x - self.pad
            self._draw_weather(draw, left=left, right_limit=limit)

    def _draw_weather(self, draw, left, right_limit):
        """Two-line weather summary + condition icon, left-aligned from `left`
        without crossing `right_limit` (the start of the centred title)."""
        w = self._weather
        f = self.font_small
        icon_sz = int(self.header_h * 0.5)
        gap = 8
        line1 = f"{w.get('temp', '')}°{w.get('units', 'F')}  {w.get('conditions', '')}"
        parts = []
        if w.get("city"):
            parts.append(w["city"])
        if w.get("humidity"):
            parts.append(f"{w['humidity']}% RH")
        if w.get("rain"):                       # only when there's a real chance
            parts.append(f"{w['rain']}% rain")
        line2 = "   ".join(parts)

        avail = right_limit - left - icon_sz - gap
        if avail < 50:
            return
        line1 = _truncate(line1, draw, f, avail)
        line2 = _truncate(line2, draw, f, avail)
        self._draw_weather_icon(draw, left, (self.header_h - icon_sz) // 2, icon_sz,
                                w.get("category", "cloudy"))
        lh = _text_size(draw, "Ag", f)[1] + 3
        ty = (self.header_h - (lh * 2 - 3)) // 2
        tx = left + icon_sz + gap
        self._text((tx, ty), line1, f, WHITE)
        self._text((tx, ty + lh), line2, f, WHITE_DIM)

    def _draw_weather_icon(self, draw, x, y, s, cat):
        """Small vector glyph for the current condition (drawn, not an asset)."""
        def cloud(bx, by, bw, bh, color):
            r = bh * 0.5
            draw.ellipse([bx, by + bh - 2 * r, bx + 2 * r, by + bh], fill=color)
            draw.ellipse([bx + bw - 2 * r, by + bh - 2 * r, bx + bw, by + bh], fill=color)
            draw.ellipse([bx + bw * 0.28, by, bx + bw * 0.72, by + bh * 0.95], fill=color)
            draw.rectangle([bx + r, by + bh - r, bx + bw - r, by + bh], fill=color)

        def sun(scx, scy, r, rays=True):
            draw.ellipse([scx - r, scy - r, scx + r, scy + r], fill=YELLOW)
            if rays:
                for i in range(8):
                    a = i * math.pi / 4
                    draw.line([scx + math.cos(a) * (r + 2), scy + math.sin(a) * (r + 2),
                               scx + math.cos(a) * (r + 5), scy + math.sin(a) * (r + 5)],
                              fill=YELLOW, width=max(1, s // 18))

        def moon(mx, my, r):
            # Two-circle crescent at the real current phase; the shadow circle
            # is filled with the header background so it reads as a bite.
            draw.ellipse([mx - r, my - r, mx + r, my + r], fill=(228, 228, 214, 255))
            p = _moon_phase()
            off = (-4 * r * p) if p < 0.5 else (4 * r * (1 - p))
            if abs(off) < 2 * r - 1:          # not full — carve the shadow
                draw.ellipse([mx - r + off, my - r, mx + r + off, my + r],
                             fill=GUIDE_HEADER_BG)

        cx = x + s / 2
        night = _is_night()
        if cat == "clear":
            if night:
                moon(cx, y + s / 2, s * 0.28)
            else:
                sun(cx, y + s / 2, s * 0.28)
            return
        if cat == "partly":
            if night:
                moon(x + s * 0.32, y + s * 0.34, s * 0.2)
            else:
                sun(x + s * 0.32, y + s * 0.34, s * 0.2)
            cloud(x + s * 0.28, y + s * 0.42, s * 0.66, s * 0.4, WHITE_DIM)
            return
        cloud(x + s * 0.08, y + s * 0.18, s * 0.84, s * 0.5, INK_MUTED if cat == "fog" else WHITE_DIM)
        base = y + s * 0.72
        if cat == "rain":
            for i in range(3):
                dx = x + s * (0.3 + i * 0.2)
                draw.line([dx, base, dx - s * 0.08, base + s * 0.2], fill=CYAN, width=max(1, s // 16))
        elif cat == "snow":
            for i in range(3):
                dx = x + s * (0.3 + i * 0.2)
                draw.ellipse([dx - 1, base + s * 0.06, dx + 2, base + s * 0.06 + 3], fill=WHITE)
        elif cat == "storm":
            draw.polygon([(cx, base), (cx - s * 0.12, base + s * 0.16),
                          (cx, base + s * 0.16), (cx - s * 0.06, base + s * 0.3)], fill=YELLOW)
        elif cat == "fog":
            for i in range(2):
                ly = base + s * 0.04 + i * s * 0.12
                draw.line([x + s * 0.15, ly, x + s * 0.85, ly], fill=INK_MUTED, width=max(1, s // 16))

    def _draw_category_bar(self, draw):
        """The ◄ Category ► selector, highlighted when it has focus."""
        x0, y0, x1, y1 = self.category_bar_px()
        focused = (self.focus == "category")
        bg = GUIDE_SELECTED if focused else GUIDE_TIME_BG
        draw.rectangle([x0, y0, x1, y1], fill=bg, outline=OSD_BORDER, width=1)
        cat = self.current_category()
        # Arrows on both sides
        self._text((x0 + 6, y0 + (y1 - y0 - 14) // 2), "<",
                   self.font_small, SEL_TEXT if focused else CYAN)
        self._text((x1 - 14, y0 + (y1 - y0 - 14) // 2), ">",
                   self.font_small, SEL_TEXT if focused else CYAN)
        label = _truncate(cat, draw, self.font_small, (x1 - x0) - 36)
        lb = draw.textbbox((0, 0), label, font=self.font_small)
        lx = x0 + ((x1 - x0) - (lb[2] - lb[0])) // 2
        self._text((lx, y0 + (y1 - y0 - (lb[3] - lb[1])) // 2 - lb[1]),
                   label, self.font_small, SEL_TEXT if focused else WHITE_DIM)

    def _draw_detail_panel(self, draw, channels, epg, current_channel_idx, now, vis):
        """Top info panel: currently-playing channel (left) + metadata for the
        selected channel's current program (right)."""
        pad = self.pad
        bottom = self.header_h + self.panel_h - pad
        # Divider under the whole panel
        draw.rectangle([0, self.header_h + self.panel_h - 2,
                        self.width, self.header_h + self.panel_h], fill=OSD_BORDER)

        # ── Left: live video preview window ───────────────────────────────
        # Punch a transparent hole through the opaque guide background so mpv's
        # (margin-shrunk) video shows through here; only a border + a caption
        # are drawn on top.
        bx0, by0, bx1, by1 = self.preview_box_px()
        draw.rectangle([bx0, by0, bx1, by1], fill=(0, 0, 0, 0))
        draw.rectangle([bx0, by0, bx1, by1], outline=OSD_BORDER, width=2)
        if channels:
            # "NOW PLAYING" chip, top-left over the video
            lbl = "NOW PLAYING"
            lb = draw.textbbox((0, 0), lbl, font=self.font_small)
            draw.rectangle([bx0 + 2, by0 + 2, bx0 + (lb[2] - lb[0]) + 16,
                            by0 + (lb[3] - lb[1]) + 12], fill=OSD_BG)
            self._text((bx0 + 8, by0 + 6), lbl, self.font_small, ORANGE)

        # ── Right: category selector (top) + metadata for the SELECTED program
        cx0, cy0, cx1, cy1 = self.category_bar_px()
        rx = bx1 + pad
        rw = self.width - pad - rx
        r_top = cy1 + pad                 # metadata sits below the category bar
        h2 = bottom - r_top
        sel_idx = self.scroll_offset + self.selected_row
        if vis and 0 <= sel_idx < len(vis):
            sel = vis[sel_idx]
            scid = epg.resolve_channel_id(sel.epg_id, sel.name) if epg else None
            sprog = epg.current_program(scid, now) if (epg and scid) else None
            # Stack rows by MEASURED line height + a uniform gap, so spacing is
            # even and nothing overlaps for any font. Title/meta wrap (never
            # truncate), and the description fills whatever panel height is left.
            def _lh(font):
                return text_wh(draw, "Ag", font)[1]
            gap = max(4, int(self.height * 0.012))
            y = r_top

            def _put(lines, font, color):
                """Draw as many of `lines` as the panel still has room for.

                The panel is a fixed box and the copy in it isn't: a long title
                that wraps to two lines used to push the times and synopsis
                straight through the divider and into the grid. Whatever doesn't
                fit is dropped, top-down, so the most important line survives.
                """
                nonlocal y
                lh = _lh(font)
                for ln in lines:
                    if y + lh > bottom:
                        return False
                    self._text((rx, y), ln, font, color)
                    y += lh
                return True

            _put([_truncate(f"{sel.number}  {sel.name}", draw,
                            self.font_small, rw)], self.font_small, YELLOW)
            y += gap
            if sprog:
                _put(_wrap_text(draw, sprog.title, self.font_panel_title, rw, 2),
                     self.font_panel_title, WHITE)
                y += gap
                meta = _prog_range(sprog)
                if sprog.episode:
                    meta += "   " + sprog.episode
                if sprog.category:
                    meta += "   " + sprog.category
                _put(_wrap_text(draw, meta, self.font_panel_text, rw,
                                1 if self.portrait else 2),
                     self.font_panel_text, CYAN)
                y += gap
                dlh = _lh(self.font_panel_text) + max(2, gap // 2)
                max_lines = max(0, (bottom - y) // dlh)
                if max_lines:
                    for ln in _wrap_text(draw, sprog.description or "",
                                         self.font_panel_text, rw, max_lines):
                        self._text((rx, y), ln, self.font_panel_text, WHITE_DIM)
                        y += dlh
            else:
                self._text((rx, y), "No program information",
                           self.font_panel_text, INK_MUTED)

    def _draw_time_ruler(
        self,
        draw: ImageDraw.Draw,
        window_start: datetime,
        window_end: datetime,
        now: datetime,
    ):
        ry = self.time_ruler_y
        rh = self.time_row_h

        # Channel column header
        draw.rectangle(
            [self.pad, ry, self.pad + self.ch_col_w, ry + rh],
            fill=GUIDE_TIME_BG,
        )
        self._text(
            (self.pad + 6, ry + 4),
            "CHANNEL", self.font_small, CYAN,
        )

        # Time slots at 30-min intervals
        total_min = self.epg_hours * 60
        slot_min = 30
        slots = total_min // slot_min
        slot_w = self.grid_w / slots

        draw.rectangle(
            [self.grid_x, ry, self.grid_x + self.grid_w, ry + rh],
            fill=GUIDE_TIME_BG,
        )

        # Every half hour gets a gridline; a label only when there's room since
        # the last one. In a narrow box the half-hour labels run into each other
        # and the ruler reads "1:39 PM2:09 PM" — the rhythm of the grid survives
        # the thinning, the overprinting doesn't.
        next_label_x = self.grid_x
        for i in range(slots):
            t = window_start + timedelta(minutes=i * slot_min)
            label = t.astimezone().strftime("%I:%M %p").lstrip("0")
            x = self.grid_x + int(i * slot_w)
            draw.line([x, ry, x, ry + rh], fill=GUIDE_BORDER, width=1)
            if x >= next_label_x:
                self._text((x + 4, ry + 4), label, self.font_small, WHITE)
                next_label_x = x + 4 + measure(draw, label, self.font_small) + 12

        # "Now" line
        now_offset = (now - window_start).total_seconds() / 60
        if 0 <= now_offset <= total_min:
            now_x = self.grid_x + int(now_offset / total_min * self.grid_w)
            draw.line(
                [now_x, ry, now_x, ry + rh + self.row_h * self.visible_rows],
                fill=(RED[0], RED[1], RED[2], 180), width=2,
            )

    def _draw_channel_row(
        self,
        draw: ImageDraw.Draw,
        ch: "Channel",
        row_i: int,
        row_y: int,
        window_start: datetime,
        window_end: datetime,
        now: datetime,
        epg: Optional["EPG"],
        is_selected: bool,
        is_current: bool,
    ):
        row_h = self.row_h
        bg = GUIDE_ROW_ODD if row_i % 2 == 0 else GUIDE_ROW_EVEN
        if is_selected:
            bg = GUIDE_SELECTED
        if is_current and not is_selected:
            bg = GUIDE_CURRENT

        # Channel column
        col_x0 = self.pad
        draw.rectangle(
            [col_x0, row_y, col_x0 + self.ch_col_w, row_y + row_h],
            fill=GUIDE_TIME_BG,
        )
        # Favorite badge — top-right corner of the channel column (state was
        # otherwise only visible via the Favorites category).
        if ch.number in self.favorites:
            self._text((col_x0 + self.ch_col_w - 14, row_y + 3), "*",
                       self.font_small, YELLOW)

        # Logo (above the number + name), pulled from XMLTV <icon> (or M3U logo)
        logo = None
        if getattr(self, "_logos", None) is not None:
            url = ""
            if epg is not None:
                url = epg.icon_url(epg.resolve_channel_id(ch.epg_id, ch.name))
            url = url or getattr(ch, "logo", "")
            if url:
                logo = self._logos.get(url, self.ch_col_w - 12, int(row_h * 0.50))

        num_str = str(ch.number)
        tw, th = _text_size(draw, num_str, self.font_ch)
        if logo is not None:
            lw, lh = logo.size
            self._img.alpha_composite(
                logo, (col_x0 + (self.ch_col_w - lw) // 2,
                       row_y + (int(row_h * 0.55) - lh) // 2 + 1))
            text_y = row_y + int(row_h * 0.55) + (int(row_h * 0.45) - th) // 2
        else:
            text_y = row_y + (row_h - th) // 2

        # [number] [name] — centered horizontally under the logo
        gap = 6
        avail = self.ch_col_w - 12
        # Side by side on a television. Upright the column is narrow and the
        # rows are tall, so the name takes its own line under the number — at
        # whatever size it fits at, because "HD Colo..." identifies nothing.
        if self.portrait and logo is None:
            f_name = self._fit_name_font(draw, ch.name, avail)
            name_str = _truncate(ch.name, draw, f_name, avail)
            # Stacked lines are placed by their measured ink, not the text
            # origin: the two fonts carry different top bearings, and stacking
            # by nominal position leaves the number resting on the name's
            # ascenders.
            nb = draw.textbbox((0, 0), num_str, font=self.font_ch)
            mb = draw.textbbox((0, 0), name_str or "Ag", font=f_name)
            nw, nh = mb[2] - mb[0], mb[3] - mb[1]
            g2 = max(4, nh // 4)
            ny = row_y + (row_h - (th + g2 + nh)) // 2
            self._text((col_x0 + (self.ch_col_w - tw) // 2 - nb[0], ny - nb[1]),
                       num_str, self.font_ch, YELLOW if is_current else WHITE)
            if name_str:
                self._text((col_x0 + (self.ch_col_w - nw) // 2 - mb[0],
                            ny + th + g2 - mb[1]),
                           name_str, f_name,
                           CYAN if is_current else WHITE_DIM)
        else:
            name_str = _truncate(ch.name, draw, self.font_small,
                                 avail - tw - gap)
            nw, nh = _text_size(draw, name_str, self.font_small)
            total_w = tw + (gap + nw if name_str else 0)
            start_x = col_x0 + max(4, (self.ch_col_w - total_w) // 2)
            self._text((start_x, text_y), num_str, self.font_ch,
                       YELLOW if is_current else WHITE)
            if name_str:
                self._text((start_x + tw + gap, text_y + (th - nh) // 2),
                           name_str, self.font_small,
                           CYAN if is_current else WHITE_DIM)

        # Program grid area background
        draw.rectangle(
            [self.grid_x, row_y, self.grid_x + self.grid_w, row_y + row_h],
            fill=bg,
        )

        # Row border
        draw.line(
            [self.pad, row_y + row_h - 1, self.grid_x + self.grid_w, row_y + row_h - 1],
            fill=GUIDE_BORDER, width=1,
        )

        # EPG programs
        if epg is None:
            self._text(
                (self.grid_x + 8, row_y + (row_h - 16) // 2),
                "No EPG data", self.font_small, INK_MUTED,
            )
            return

        channel_epg_id = epg.resolve_channel_id(ch.epg_id, ch.name)
        if not channel_epg_id:
            self._text(
                (self.grid_x + 8, row_y + (row_h - 16) // 2),
                ch.name, self.font_small, INK_MUTED,
            )
            return

        progs = epg.programs_in_window(channel_epg_id, window_start, window_end)
        total_min = self.epg_hours * 60

        for prog in progs:
            start_off = max(0, (prog.start - window_start).total_seconds() / 60)
            end_off   = min(total_min, (prog.stop - window_start).total_seconds() / 60)
            if end_off <= start_off:
                continue

            px = self.grid_x + int(start_off / total_min * self.grid_w)
            pw = int((end_off - start_off) / total_min * self.grid_w)

            is_on_air = prog.start <= now < prog.stop
            cell_fill = GUIDE_ONAIR if is_on_air else bg
            if is_on_air:
                cell_text = ONAIR_TEXT
            elif is_selected:
                cell_text = SEL_TEXT_DIM   # readable on the accent-mixed fill
            else:
                cell_text = WHITE_DIM

            draw.rectangle(
                [px + 1, row_y + 2, px + pw - 1, row_y + row_h - 2],
                fill=cell_fill,
            )
            draw.line(
                [px, row_y, px, row_y + row_h],
                fill=GUIDE_BORDER, width=1,
            )

            # Program title in cell. A block only wide enough for the ellipsis
            # renders as a bare "..." that says less than the empty block does —
            # a 20px floor was low enough to let those through at phone font
            # sizes, so the floor is measured against the font instead.
            if pw >= 8 + measure(draw, "MMMMM", self.font_prog):
                title = _truncate(prog.title, draw, self.font_prog, pw - 8)
                if title:
                    _tw2, th2 = _text_size(draw, title, self.font_prog)
                    self._text(
                        (px + 4, row_y + (row_h - th2) // 2),
                        title, self.font_prog, cell_text,
                    )

    def _fit_name_font(self, draw, name: str, max_w: int):
        """Channel-name font shrunk (to a floor) so the whole name fits `max_w`.

        Scaled in one step from the measured overflow rather than stepped down a
        size at a time: this runs per row, per frame.
        """
        w = measure(draw, name, self.font_small)
        if w <= max_w or w <= 0:
            return self.font_small
        return get_font(max(11, int(self._small_px * max_w / w)))

    def _draw_scroll_arrow(self, draw: ImageDraw.Draw, up: bool):
        cx = self.width // 2
        if up:
            y  = self.grid_y - 12
            pts = [(cx - 12, y + 10), (cx + 12, y + 10), (cx, y)]
        else:
            y   = self.grid_y + self.row_h * self.visible_rows + 12
            pts = [(cx - 12, y - 10), (cx + 12, y - 10), (cx, y)]
        draw.polygon(pts, fill=CYAN)
