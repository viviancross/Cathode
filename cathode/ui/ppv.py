"""Plex-Per-View browse screen — a retro 90s cable "pay-per-view" listing for a
Plex library. Full-screen and opaque; the app drives navigation and data, this
just renders the current level and a cursor. ASCII only (pixel fonts).
"""

from __future__ import annotations

from typing import List, Optional

from PIL import Image, ImageDraw

from .theme import (
    get_font, OSD_BG, OSD_BORDER, WHITE, WHITE_DIM, CYAN, YELLOW, GRAY,
    CHANNEL_GREEN, GUIDE_SELECTED,
)


class PPVScreen:
    def __init__(self, width: int, height: int):
        self.open = False
        self.width = width
        self.height = height
        self.mode = "browse"          # "browse" | "auth"
        self.title = "PLEX-PER-VIEW"
        self.rows: List[dict] = []    # {title, meta, playable}
        self.sel = 0
        self.status = ""              # centered overlay (loading / error / empty)
        self.crumb = ""               # breadcrumb shown in the footer
        self.input_mode = "key"       # "key" or "gamepad" — picks the hint glyphs
        # auth view
        self.auth_code = ""
        self.auth_link = ""
        self.auth_msg = ""
        self._build_fonts()

    def _build_fonts(self):
        h = self.height
        self.f_banner = get_font(max(28, int(h * 0.075)))
        self.f_title = get_font(max(16, int(h * 0.034)))
        self.f_row = get_font(max(14, int(h * 0.030)))
        self.f_meta = get_font(max(12, int(h * 0.024)))
        self.f_foot = get_font(max(12, int(h * 0.022)))

    def resize(self, w, h):
        self.width, self.height = w, h
        self._build_fonts()

    refresh_fonts = _build_fonts

    # ── state set by the controller ───────────────────────────────────────

    def show(self):
        self.open = True

    def close(self):
        self.open = False

    def set_browse(self, title: str, rows: List[dict], crumb: str = "", sel: int = 0):
        self.mode = "browse"
        self.title = title
        self.rows = rows
        self.crumb = crumb
        self.sel = max(0, min(sel, len(rows) - 1)) if rows else 0
        self.status = "" if rows else "NOTHING HERE"

    def set_status(self, text: str):
        self.status = text

    def set_auth(self, code: str, link: str, msg: str = ""):
        self.mode = "auth"
        self.auth_code = code
        self.auth_link = link
        self.auth_msg = msg

    # ── navigation (driven by the app) ────────────────────────────────────

    def move_up(self):
        if self.rows:
            self.sel = (self.sel - 1) % len(self.rows)

    def move_down(self):
        if self.rows:
            self.sel = (self.sel + 1) % len(self.rows)

    def scroll(self, delta):
        """Jump the selection by `delta` items (clamped, no wrap)."""
        if self.rows:
            self.sel = max(0, min(self.sel + delta, len(self.rows) - 1))

    def current(self) -> Optional[dict]:
        if self.rows and 0 <= self.sel < len(self.rows):
            return self.rows[self.sel]
        return None

    # ── geometry / mouse ──────────────────────────────────────────────────

    def _panel(self):
        m = max(16, int(self.width * 0.04))
        top = int(self.height * 0.24)
        return m, top, self.width - m, self.height - int(self.height * 0.09)

    def _row_h(self) -> int:
        return max(26, int(self.height * 0.055))

    def _visible_count(self) -> int:
        _, top, _, bottom = self._panel()
        return max(1, (bottom - top - 10) // self._row_h())

    def _first_visible(self) -> int:
        # Keep the highlight centered: the list scrolls under it (clamped at the
        # very top/bottom of the list).
        vis = self._visible_count()
        n = len(self.rows)
        if n <= vis:
            return 0
        return max(0, min(self.sel - vis // 2, n - vis))

    def _row_rects(self):
        x0, top, x1, _ = self._panel()
        rh = self._row_h()
        first = self._first_visible()
        vis = self._visible_count()
        out = []
        y = top + 6
        for i in range(first, min(first + vis, len(self.rows))):
            out.append((i, x0 + 6, y, x1 - 6, y + rh))
            y += rh
        return out

    def hit_test(self, x, y) -> Optional[int]:
        if self.mode != "browse":
            return None
        for (i, ax0, ay0, ax1, ay1) in self._row_rects():
            if ax0 <= x <= ax1 and ay0 <= y <= ay1:
                return i
        return None

    def set_hover(self, x, y):
        i = self.hit_test(x, y)
        if i is not None:
            self.sel = i

    # ── render ────────────────────────────────────────────────────────────

    def render(self) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        if not self.open:
            return img
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, self.width, self.height], fill=(6, 6, 12, 255))
        # Header — stacked with measured gaps so the lines never overlap.
        y = int(self.height * 0.03)
        self._center(d, "PLEX-PER-VIEW", self.f_banner, y, YELLOW)
        y += self._th(d, "PLEX-PER-VIEW", self.f_banner) + int(self.height * 0.022)
        self._center(d, "CATHODE ON DEMAND", self.f_meta, y, CYAN)
        y += self._th(d, "CATHODE ON DEMAND", self.f_meta) + int(self.height * 0.022)

        if self.mode == "auth":
            self._render_auth(d)
            return img

        # Breadcrumb (left), then the current level title (centered).
        if self.crumb:
            d.text((int(self.width * 0.04), y), self.crumb, font=self.f_meta, fill=GRAY)
            y += self._th(d, self.crumb, self.f_meta) + int(self.height * 0.014)
        self._center(d, self.title.upper(), self.f_title, y, WHITE)

        # List panel
        x0, top, x1, bottom = self._panel()
        d.rectangle([x0, top, x1, bottom], fill=(OSD_BG[0], OSD_BG[1], OSD_BG[2], 255),
                    outline=OSD_BORDER, width=3)

        rh = self._row_h()
        for (i, ax0, ay0, ax1, ay1) in self._row_rects():
            row = self.rows[i]
            sel = (i == self.sel)
            if sel:
                d.rectangle([ax0, ay0, ax1, ay1],
                            fill=(GUIDE_SELECTED[0], GUIDE_SELECTED[1],
                                  GUIDE_SELECTED[2], 255),
                            outline=CHANNEL_GREEN, width=2)
            ty = ay0 + (rh - self._th(d, "Ag", self.f_row)) // 2
            marker = ">" if row.get("playable") else " "
            d.text((ax0 + 12, ty), f"{marker} {row.get('title', '?')}",
                   font=self.f_row, fill=WHITE if sel else WHITE_DIM)
            meta = row.get("meta", "")
            if meta:
                mw = self._tw(d, meta, self.f_meta)
                d.text((ax1 - mw - 12, ay0 + (rh - self._th(d, meta, self.f_meta)) // 2),
                       meta, font=self.f_meta, fill=CYAN if sel else GRAY)

        if self.status:
            self._center(d, self.status, self.f_title, (top + bottom) // 2, YELLOW)

        # Footer (device-aware hints)
        cur = self.current()
        act = "ORDER" if (cur and cur.get("playable")) else "OPEN"
        if self.input_mode == "gamepad":
            foot = f"[D-PAD] BROWSE    [A] {act}    [B] BACK"
        else:
            foot = f"[UP/DN] BROWSE    [ENTER] {act}    [ESC] BACK"
        self._center(d, foot, self.f_foot, self.height - int(self.height * 0.06), WHITE_DIM)
        return img

    def _render_auth(self, d):
        cy = int(self.height * 0.30)
        self._center(d, "SIGN IN TO PLEX", self.f_title, cy, WHITE)
        self._center(d, "On your phone or PC, go to:", self.f_row,
                     cy + int(self.height * 0.09), WHITE_DIM)
        self._center(d, self.auth_link or "plex.tv/link", self.f_title,
                     cy + int(self.height * 0.15), CYAN)
        self._center(d, "and enter this code:", self.f_row,
                     cy + int(self.height * 0.24), WHITE_DIM)
        self._center(d, self.auth_code or "----", self.f_banner,
                     cy + int(self.height * 0.30), CHANNEL_GREEN)
        msg = self.auth_msg or "Waiting for you to link..."
        self._center(d, msg, self.f_meta, cy + int(self.height * 0.42), GRAY)
        cancel = "[B] CANCEL" if self.input_mode == "gamepad" else "[ESC] CANCEL"
        self._center(d, cancel, self.f_foot,
                     self.height - int(self.height * 0.06), WHITE_DIM)

    # ── text helpers ──────────────────────────────────────────────────────

    def _center(self, d, text, font, y, color):
        w = self._tw(d, text, font)
        d.text(((self.width - w) // 2, y), text, font=font, fill=color)

    @staticmethod
    def _tw(d, text, font) -> int:
        bb = d.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0]

    @staticmethod
    def _th(d, text, font) -> int:
        bb = d.textbbox((0, 0), text, font=font)
        return bb[3] - bb[1]
