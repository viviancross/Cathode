"""On-screen display: channel info bar, volume indicator, clock."""

from __future__ import annotations
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from PIL import Image, ImageDraw

from . import theme
from .theme import (
    get_font, OSD_BG, OSD_BORDER,
    CYAN, YELLOW, WHITE, WHITE_DIM, GRAY,
    CHNUM_BG, GREEN, RED, ORANGE, CHANNEL_GREEN,
)

if TYPE_CHECKING:
    from ..epg import Program, EPG
    from ..playlist import Channel


def _time_str() -> str:
    return datetime.now().strftime("%I:%M %p").lstrip("0")


def _prog_time_range(prog: "Program") -> str:
    local_start = prog.start.astimezone().strftime("%I:%M").lstrip("0")
    local_stop  = prog.stop.astimezone().strftime("%I:%M %p").lstrip("0")
    return f"{local_start} - {local_stop}"   # ASCII hyphen (all fonts have it)


def _fit(draw, text: str, font, max_w: int) -> str:
    """Trim text with an ellipsis so it fits within max_w pixels."""
    if not text:
        return ""
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "...", font=font) > max_w:
        text = text[:-1]
    return (text + "...") if text else ""


class OSD:
    """Renders the OSD bar at the bottom of the screen."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height

        # Bar dimensions
        self.bar_h = int(height * 0.155)
        self.bar_y = height - self.bar_h - int(height * 0.025)

        # Channel number box (upper-left of bar)
        self.num_box_w = int(self.bar_h * 1.1)

        # Fonts
        self.font_huge   = get_font(int(self.bar_h * 0.55))
        self.font_large  = get_font(int(self.bar_h * 0.32))
        self.font_medium = get_font(int(self.bar_h * 0.24))
        self.font_small  = get_font(int(self.bar_h * 0.18))

    def render(
        self,
        channel: Optional["Channel"],
        current_prog: Optional["Program"],
        next_prog: Optional["Program"],
        volume: int,
        muted: bool,
        show_volume: bool = False,
        epg: Optional["EPG"] = None,
        logos=None,
    ) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        if channel is None:
            return img
        draw = ImageDraw.Draw(img)

        bar_x = int(self.width * 0.02)
        bar_w = int(self.width * 0.96)
        bx, by, bh = bar_x, self.bar_y, self.bar_h
        bw = bar_w

        # ── Main bar background ──────────────────────────────────────────
        _rounded_rect(draw, bx, by, bx + bw, by + bh, radius=8, fill=OSD_BG)
        draw.rectangle([bx, by, bx + bw, by + 2], fill=OSD_BORDER)  # top border

        # ── Logo box (upper-left) — channel logo, or the number as fallback ─
        nb_x = bx + 8
        nb_y = by + 8
        nb_w = self.num_box_w
        nb_h = bh - 16
        _rounded_rect(draw, nb_x, nb_y, nb_x + nb_w, nb_y + nb_h, radius=6, fill=CHNUM_BG)
        draw.rectangle([nb_x, nb_y, nb_x + nb_w, nb_y + 2], fill=OSD_BORDER)

        logo = None
        if logos is not None:
            url = ""
            if epg is not None:
                url = epg.icon_url(epg.resolve_channel_id(channel.epg_id, channel.name))
            url = url or getattr(channel, "logo", "")
            logo = logos.get(url, nb_w - 10, nb_h - 10)

        if logo is not None:
            lw, lh = logo.size
            img.alpha_composite(logo, (nb_x + (nb_w - lw) // 2,
                                       nb_y + (nb_h - lh) // 2))

        # ── Column geometry ──────────────────────────────────────────────
        info_x = nb_x + nb_w + 20
        next_x = int(self.width * 0.45)
        info_col_w = next_x - info_x - 16   # width before the NEXT column

        # ── Vertical row stack ────────────────────────────────────────────
        # Rows are placed by MEASURED ink height (not fixed bar-fractions), and
        # each line is drawn with its ink top on the row line. The progress bar
        # sits just below the title's real ink, so nothing strikes through the
        # text for ANY font (compact or tall pixel fonts), now or future.
        def _rh(font):
            return _text_size(draw, "Ag", font)[1]
        gap = max(2, int(bh * 0.05))
        y_name = by + int(bh * 0.10)
        y_prog = y_name + _rh(self.font_large) + gap
        pb_h   = 4
        pb_y   = y_prog + _rh(self.font_medium) + max(2, gap // 2)
        y_time = pb_y + pb_h + max(2, gap // 2)

        # ── Channel number (left of name, themed color) + name ────────────
        name_x = info_x
        num_str = str(channel.number)
        if logo is not None:
            # Logo fills the box, so show the number beside the name.
            self._t(img, draw, info_x, y_name, num_str, self.font_large, CHANNEL_GREEN)
            name_x = info_x + _text_size(draw, num_str, self.font_large)[0] + 12
        else:
            # No logo → the number stays big in the box.
            tw, th = _text_size(draw, num_str, self.font_huge)
            self._t(img, draw, nb_x + (nb_w - tw) // 2, nb_y + (nb_h - th) // 2,
                    num_str, self.font_huge, CHANNEL_GREEN)
        self._t(img, draw, name_x, y_name,
                _fit(draw, channel.name, self.font_large, info_col_w - (name_x - info_x)),
                self.font_large, WHITE)

        # ── Current program ───────────────────────────────────────────────
        if current_prog:
            prog_str = current_prog.title
            if current_prog.episode:
                prog_str += f"  {current_prog.episode}"
            self._t(img, draw, info_x, y_prog,
                    _fit(draw, prog_str, self.font_medium, info_col_w),
                    self.font_medium, CYAN)

            # Progress bar (below the title ink)
            progress = current_prog.progress_at(datetime.now(timezone.utc))
            pb_w = int(bw * 0.40)
            draw.rectangle([info_x, pb_y, info_x + pb_w, pb_y + pb_h], fill=GRAY)
            draw.rectangle(
                [info_x, pb_y, info_x + int(pb_w * progress), pb_y + pb_h],
                fill=GREEN,
            )

            # Time range
            self._t(img, draw, info_x, y_time,
                    _prog_time_range(current_prog), self.font_small, WHITE_DIM)
        else:
            self._t(img, draw, info_x, y_prog, "No program info",
                    self.font_medium, GRAY)

        # ── Next program ──────────────────────────────────────────────────
        if next_prog:
            # Clip the NEXT title so it stops before the clock on the right.
            next_col_w = (bx + bw) - next_x - int(self.width * 0.10)
            self._t(img, draw, next_x, y_name, "NEXT", self.font_small, ORANGE)
            self._t(img, draw, next_x, y_prog,
                    _fit(draw, next_prog.title, self.font_medium, next_col_w),
                    self.font_medium, WHITE_DIM)
            self._t(img, draw, next_x, y_time,
                    _prog_time_range(next_prog), self.font_small, GRAY)

        # ── Clock (right side) ────────────────────────────────────────────
        clock_str = _time_str()
        clock_x = bx + bw - 12
        tw, th = _text_size(draw, clock_str, self.font_large)
        self._t(img, draw, clock_x - tw, y_name, clock_str, self.font_large, YELLOW)

        # ── Group / category tag (below the clock) ────────────────────────
        if channel.group:
            group_str = channel.group.upper()[:20]
            tw2, _ = _text_size(draw, group_str, self.font_small)
            self._t(img, draw, clock_x - tw2, y_prog, group_str, self.font_small, CYAN)

        # ── Volume indicator ──────────────────────────────────────────────
        if show_volume:
            _draw_volume(draw, bx + bw // 2, by - 50, volume, muted, self.font_medium)

        return img

    def _t(self, img, draw, x, y, text, font, fill):
        """Draw cached text with its visible ink top at `y` — subtracts the glyph
        top bearing so every font lands on the row line (tall pixel fonts carry
        big top bearing and would otherwise sit low and collide)."""
        if not text:
            return
        bb = draw.textbbox((0, 0), text, font=font)
        theme.draw_text(img, (int(x), int(y - bb[1])), text, font, fill)


def _draw_volume(
    draw: ImageDraw.Draw,
    cx: int, cy: int,
    volume: int, muted: bool,
    font,
):
    """Small volume HUD above the OSD bar."""
    label = "MUTE" if muted else f"VOL  {volume:3d}"
    w, h = _text_size(draw, label, font)
    x = cx - w // 2 - 8
    y = cy - h // 2 - 6
    draw.rectangle([x, y, x + w + 16, y + h + 12], fill=OSD_BG)
    draw.rectangle([x, y, x + w + 16, y + 2], fill=OSD_BORDER)
    color = RED if muted else CYAN
    draw.text((x + 8, y + 6), label, font=font, fill=color)

    if not muted:
        # Bar graph
        bar_x = cx - 60
        bar_y = cy + h // 2 + 8
        bar_total = 120
        draw.rectangle([bar_x, bar_y, bar_x + bar_total, bar_y + 6], fill=GRAY)
        fill_w = int(bar_total * volume / 100)
        fill_color = GREEN if volume < 80 else YELLOW if volume < 95 else RED
        draw.rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + 6], fill=fill_color)


class ChannelFlash:
    """Big centered channel-number overlay shown briefly on switch."""

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.font = get_font(int(height * 0.20))
        self.font_name = get_font(int(height * 0.05))

    def render(self, channel: Optional["Channel"], alpha: int = 230) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        if channel is None:
            return img
        draw = ImageDraw.Draw(img)

        num_str = str(channel.number)
        tw, th = _text_size(draw, num_str, self.font)

        box_w = tw + 60
        box_h = th + 30
        bx = (self.width - box_w) // 2
        by = (self.height - box_h) // 2

        _rounded_rect(
            draw, bx, by, bx + box_w, by + box_h,
            radius=10,
            fill=(*OSD_BG[:3], alpha),   # themed bg with fade alpha
        )
        draw.rectangle([bx, by, bx + box_w, by + 3], fill=OSD_BORDER)
        draw.rectangle([bx, by + box_h - 3, bx + box_w, by + box_h], fill=OSD_BORDER)

        draw.text(
            (bx + (box_w - tw) // 2, by + (box_h - th) // 2),
            num_str, font=self.font, fill=YELLOW,
        )
        return img


# ── Helpers ──────────────────────────────────────────────────────────────────

def _text_size(draw: ImageDraw.Draw, text: str, font) -> tuple:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]


def _rounded_rect(
    draw: ImageDraw.Draw,
    x0: int, y0: int, x1: int, y1: int,
    radius: int = 8,
    fill=None,
    outline=None,
):
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=outline)
