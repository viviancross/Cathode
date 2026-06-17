"""Program guide overlay — 80s-style cable TV grid."""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import List, Optional, TYPE_CHECKING

from PIL import Image, ImageDraw

from .theme import (
    get_font,
    GUIDE_BG, GUIDE_HEADER_BG, GUIDE_ROW_ODD, GUIDE_ROW_EVEN,
    GUIDE_CURRENT, GUIDE_SELECTED, GUIDE_ONAIR, GUIDE_TIME_BG, GUIDE_BORDER,
    WHITE, WHITE_DIM, CYAN, YELLOW, GRAY, GRAY_DARK, BLACK,
    ORANGE, GREEN, OSD_BORDER, OSD_BG, CHANNEL_GREEN,
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


def _wrap_text(draw, text: str, font, max_w: int, max_lines: int) -> list:
    """Word-wrap `text` to fit `max_w` px, up to `max_lines` lines."""
    if not text or max_lines <= 0:
        return []
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
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
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]


def _truncate(text: str, draw: ImageDraw.Draw, font, max_w: int) -> str:
    if not text:
        return ""
    tw, _ = _text_size(draw, text, font)
    if tw <= max_w:
        return text
    while text and tw > max_w:
        text = text[:-1]
        tw, _ = _text_size(draw, text + "...", font)
    return text + "..."


class Guide:
    """Renders a full-screen retro program guide grid."""

    # Layout constants (as fractions of width/height)
    PADDING          = 0.02
    HEADER_H_FRAC    = 0.07
    TIME_ROW_H_FRAC  = 0.045
    ROW_H_FRAC       = 0.075
    CH_COL_W_FRAC    = 0.14
    DETAIL_PANEL_FRAC = 0.30   # height of the info panel in the "detail" layout

    def __init__(self, width: int, height: int, epg_hours: int = 3):
        self.width = width
        self.height = height
        self.epg_hours = epg_hours

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
        self.pad      = int(width * self.PADDING)
        self.header_h = int(height * self.HEADER_H_FRAC)
        self.time_row_h = int(height * self.TIME_ROW_H_FRAC)
        self.ch_col_w = int(width * self.CH_COL_W_FRAC)
        self.panel_h = int(height * self.DETAIL_PANEL_FRAC)
        self.cat_bar_h = max(26, int(height * 0.045))   # category selector strip
        self.time_ruler_y = self.header_h + self.panel_h

        # Fit as many rows as the (remaining) space allows, then stretch row
        # height so the grid fills to the bottom.
        inner_h = height - self.header_h - self.panel_h - self.time_row_h - 2 * self.pad
        nominal_row = max(1, int(height * self.ROW_H_FRAC))
        self.visible_rows = max(1, inner_h // nominal_row)
        self.row_h = inner_h // self.visible_rows

        self.grid_x = self.pad + self.ch_col_w
        self.grid_w = width - self.pad - self.grid_x
        self.grid_y = self.time_ruler_y + self.time_row_h

        # Fonts
        self.font_title  = get_font(int(self.header_h * 0.45))
        self.font_time   = get_font(int(self.time_row_h * 0.55))
        self.font_ch     = get_font(int(self.row_h * 0.30))
        self.font_prog   = get_font(int(self.row_h * 0.28))
        self.font_small  = get_font(int(self.row_h * 0.22))
        self.font_panel_title = get_font(max(14, int(height * 0.045)))
        self.font_panel_text  = get_font(max(11, int(height * 0.028)))

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
        lw = int(self.width * 0.30)
        return (lx, top, lx + lw, bottom)

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
    ) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        self._logos = logos
        self._img = img    # for pasting logos in channel rows

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
            draw.text((self.grid_x + 8, self.grid_y + 8),
                      "No channels in this category",
                      font=self.font_small, fill=GRAY)

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

    def _draw_header(self, draw: ImageDraw.Draw, now: datetime):
        draw.rectangle([0, 0, self.width, self.header_h], fill=GUIDE_HEADER_BG)
        draw.rectangle(
            [0, self.header_h - 2, self.width, self.header_h],
            fill=OSD_BORDER,
        )

        # Title
        tw, th = _text_size(draw, _GUIDE_TITLE, self.font_title)
        draw.text(
            ((self.width - tw) // 2, (self.header_h - th) // 2),
            _GUIDE_TITLE, font=self.font_title, fill=YELLOW,
        )

        # Current time (right)
        local = now.astimezone()
        time_str = (
            local.strftime("%I:%M:%S %p").lstrip("0")
            + local.strftime("  %a %b ")
            + str(local.day)
        )
        tw2, _ = _text_size(draw, time_str, self.font_time)
        draw.text(
            (self.width - tw2 - self.pad, (self.header_h - th) // 2),
            time_str, font=self.font_time, fill=CYAN,
        )

        # Keybind hint (left)
        # ASCII only (pixel fonts lack arrow glyphs), compact so it never runs
        # into the centred title even with wide fonts.
        hint = "Ch:Up/Dn  Time:L/R  F:Fav  G:Close"
        draw.text(
            (self.pad, (self.header_h - th) // 2),
            hint, font=self.font_small, fill=GRAY,
        )

    def _draw_category_bar(self, draw):
        """The ◄ Category ► selector, highlighted when it has focus."""
        x0, y0, x1, y1 = self.category_bar_px()
        focused = (self.focus == "category")
        bg = GUIDE_SELECTED if focused else GUIDE_TIME_BG
        draw.rectangle([x0, y0, x1, y1], fill=bg, outline=OSD_BORDER, width=1)
        cat = self.current_category()
        # Arrows on both sides
        ay = y0 + (y1 - y0) // 2
        draw.text((x0 + 6, y0 + (y1 - y0 - 14) // 2), "<",
                  font=self.font_small, fill=YELLOW if focused else CYAN)
        draw.text((x1 - 14, y0 + (y1 - y0 - 14) // 2), ">",
                  font=self.font_small, fill=YELLOW if focused else CYAN)
        label = _truncate(cat, draw, self.font_small, (x1 - x0) - 36)
        lb = draw.textbbox((0, 0), label, font=self.font_small)
        lx = x0 + ((x1 - x0) - (lb[2] - lb[0])) // 2
        draw.text((lx, y0 + (y1 - y0 - (lb[3] - lb[1])) // 2 - lb[1]),
                  label, font=self.font_small, fill=WHITE if focused else WHITE_DIM)

    def _draw_detail_panel(self, draw, channels, epg, current_channel_idx, now, vis):
        """Top info panel: currently-playing channel (left) + metadata for the
        selected channel's current program (right)."""
        pad = self.pad
        top = self.header_h + pad
        bottom = self.header_h + self.panel_h - pad
        h = bottom - top
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
            draw.text((bx0 + 8, by0 + 6), lbl, font=self.font_small, fill=ORANGE)

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
            draw.text((rx, r_top), _truncate(f"{sel.number}  {sel.name}", draw,
                      self.font_small, rw), font=self.font_small, fill=YELLOW)
            y = r_top + int(h2 * 0.16)
            if sprog:
                draw.text((rx, y), _truncate(sprog.title, draw,
                          self.font_panel_title, rw),
                          font=self.font_panel_title, fill=WHITE)
                y += int(h2 * 0.26)
                meta = _prog_range(sprog)
                if sprog.episode:
                    meta += "   " + sprog.episode
                if sprog.category:
                    meta += "   " + sprog.category
                draw.text((rx, y), _truncate(meta, draw, self.font_panel_text, rw),
                          font=self.font_panel_text, fill=CYAN)
                y += int(h2 * 0.20)
                lh = int(self.height * 0.028 * 1.35) + 2
                max_lines = max(1, (bottom - y) // lh)
                for ln in _wrap_text(draw, sprog.description or "",
                                     self.font_panel_text, rw, max_lines):
                    draw.text((rx, y), ln, font=self.font_panel_text, fill=WHITE_DIM)
                    y += lh
            else:
                draw.text((rx, y), "No program information",
                          font=self.font_panel_text, fill=GRAY)

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
        draw.text(
            (self.pad + 6, ry + 4),
            "CHANNEL", font=self.font_small, fill=CYAN,
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

        for i in range(slots):
            t = window_start + timedelta(minutes=i * slot_min)
            label = t.astimezone().strftime("%I:%M %p").lstrip("0")
            x = self.grid_x + int(i * slot_w)
            draw.line([x, ry, x, ry + rh], fill=GUIDE_BORDER, width=1)
            draw.text((x + 4, ry + 4), label, font=self.font_small, fill=WHITE)

        # "Now" line
        now_offset = (now - window_start).total_seconds() / 60
        if 0 <= now_offset <= total_min:
            now_x = self.grid_x + int(now_offset / total_min * self.grid_w)
            draw.line(
                [now_x, ry, now_x, ry + rh + self.row_h * self.visible_rows],
                fill=(255, 80, 80, 180), width=2,
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
        name_str = _truncate(ch.name, draw, self.font_small,
                             self.ch_col_w - tw - gap - 12)
        nw, nh = _text_size(draw, name_str, self.font_small)
        total_w = tw + (gap + nw if name_str else 0)
        start_x = col_x0 + max(4, (self.ch_col_w - total_w) // 2)
        draw.text((start_x, text_y), num_str, font=self.font_ch,
                  fill=YELLOW if is_current else WHITE)
        if name_str:
            draw.text((start_x + tw + gap, text_y + (th - nh) // 2), name_str,
                      font=self.font_small, fill=CYAN if is_current else WHITE_DIM)

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
            draw.text(
                (self.grid_x + 8, row_y + (row_h - 16) // 2),
                "No EPG data", font=self.font_small, fill=GRAY,
            )
            return

        channel_epg_id = epg.resolve_channel_id(ch.epg_id, ch.name)
        if not channel_epg_id:
            draw.text(
                (self.grid_x + 8, row_y + (row_h - 16) // 2),
                ch.name, font=self.font_small, fill=GRAY,
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
            cell_text = WHITE if is_on_air else WHITE_DIM

            draw.rectangle(
                [px + 1, row_y + 2, px + pw - 1, row_y + row_h - 2],
                fill=cell_fill,
            )
            draw.line(
                [px, row_y, px, row_y + row_h],
                fill=GUIDE_BORDER, width=1,
            )

            # Program title in cell
            title = _truncate(prog.title, draw, self.font_prog, pw - 8)
            tw2, th2 = _text_size(draw, title, self.font_prog)
            if pw > 20 and title:
                draw.text(
                    (px + 4, row_y + (row_h - th2) // 2),
                    title, font=self.font_prog, fill=cell_text,
                )

    def _draw_scroll_arrow(self, draw: ImageDraw.Draw, up: bool):
        cx = self.width // 2
        if up:
            y  = self.grid_y - 12
            pts = [(cx - 12, y + 10), (cx + 12, y + 10), (cx, y)]
        else:
            y   = self.grid_y + self.row_h * self.visible_rows + 12
            pts = [(cx - 12, y - 10), (cx + 12, y - 10), (cx, y)]
        draw.polygon(pts, fill=CYAN)
