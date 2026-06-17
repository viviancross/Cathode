"""On-screen display: channel info bar, volume indicator, clock."""

from __future__ import annotations
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from PIL import Image, ImageDraw

from .theme import (
    get_font, TRANSPARENT, OSD_BG, OSD_BORDER,
    CYAN, YELLOW, WHITE, WHITE_DIM, GRAY,
    CHNUM_BG, CHNUM_TEXT, GREEN, RED, ORANGE, CHANNEL_GREEN,
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

        # ── Channel number (left of name, themed color) + name ────────────
        name_y = by + int(bh * 0.12)
        name_x = info_x
        if logo is not None:
            # Logo fills the box, so show the number beside the name.
            num_str = str(channel.number)
            draw.text((info_x, name_y), num_str, font=self.font_large,
                      fill=CHANNEL_GREEN)
            name_x = info_x + _text_size(draw, num_str, self.font_large)[0] + 12
        else:
            # No logo → the number stays big in the box.
            num_str = str(channel.number)
            tw, th = _text_size(draw, num_str, self.font_huge)
            draw.text((nb_x + (nb_w - tw) // 2, nb_y + (nb_h - th) // 2),
                      num_str, font=self.font_huge, fill=CHANNEL_GREEN)
        draw.text((name_x, name_y),
                  _fit(draw, channel.name, self.font_large, info_col_w - (name_x - info_x)),
                  font=self.font_large, fill=WHITE)

        # ── Current program ───────────────────────────────────────────────
        prog_y = by + int(bh * 0.45)
        if current_prog:
            prog_str = current_prog.title
            if current_prog.episode:
                prog_str += f"  {current_prog.episode}"
            draw.text((info_x, prog_y),
                      _fit(draw, prog_str, self.font_medium, info_col_w),
                      font=self.font_medium, fill=CYAN)

            # Progress bar
            progress = current_prog.progress_at(datetime.now(timezone.utc))
            pb_x = info_x
            pb_y = by + int(bh * 0.68)
            pb_w = int(bw * 0.40)
            pb_h = 4
            draw.rectangle([pb_x, pb_y, pb_x + pb_w, pb_y + pb_h], fill=GRAY)
            draw.rectangle(
                [pb_x, pb_y, pb_x + int(pb_w * progress), pb_y + pb_h],
                fill=GREEN,
            )

            # Time range
            time_str = _prog_time_range(current_prog)
            draw.text(
                (info_x, by + int(bh * 0.78)),
                time_str, font=self.font_small, fill=WHITE_DIM,
            )

        else:
            draw.text((info_x, prog_y), "No program info", font=self.font_medium, fill=GRAY)

        # ── Next program ──────────────────────────────────────────────────
        if next_prog:
            # Clip the NEXT title so it stops before the clock on the right.
            next_col_w = (bx + bw) - next_x - int(self.width * 0.10)
            draw.text(
                (next_x, name_y),
                "NEXT",
                font=self.font_small, fill=ORANGE,
            )
            draw.text(
                (next_x, prog_y),
                _fit(draw, next_prog.title, self.font_medium, next_col_w),
                font=self.font_medium, fill=WHITE_DIM,
            )
            draw.text(
                (next_x, by + int(bh * 0.78)),
                _prog_time_range(next_prog),
                font=self.font_small, fill=GRAY,
            )

        # ── Clock (right side) ────────────────────────────────────────────
        clock_str = _time_str()
        clock_x = bx + bw - 12
        clock_y = by + int(bh * 0.12)
        tw, th = _text_size(draw, clock_str, self.font_large)
        draw.text(
            (clock_x - tw, clock_y),
            clock_str, font=self.font_large, fill=YELLOW,
        )

        # ── Group / category tag ──────────────────────────────────────────
        if channel.group:
            group_str = channel.group.upper()[:20]
            tw2, _ = _text_size(draw, group_str, self.font_small)
            draw.text(
                (clock_x - tw2, clock_y + th + 6),
                group_str, font=self.font_small, fill=CYAN,
            )

        # ── Volume indicator ──────────────────────────────────────────────
        if show_volume:
            _draw_volume(draw, bx + bw // 2, by - 50, volume, muted, self.font_medium)

        return img


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
