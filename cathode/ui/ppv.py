"""Plex-Per-View browse screen — a retro 90s cable "pay-per-view" listing for a
Plex library. Full-screen and opaque; the app drives navigation and data, this
just renders the current level and a cursor. ASCII only (pixel fonts).
"""

from __future__ import annotations

from typing import List, Optional

from PIL import Image, ImageDraw

from .theme import (
    get_font, ellipsize, wrap_lines, OSD_BG, OSD_BORDER, WHITE, WHITE_DIM, CYAN,
    YELLOW, GRAY, CHANNEL_GREEN, GUIDE_SELECTED,
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
        self.bar_focus = None         # None=list, "back" or "menu"=top bar button
        self._scroll_top = 0          # first visible row (variable-height scroll)
        self._row_lines = []          # per-row title line count (1 or 2)
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
        # Measure the row font's actual line height so rows can hold 2 wrapped
        # lines without overlapping the next item.
        _d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        bb = _d.textbbox((0, 0), "Ag", font=self.f_row)
        self._row_line_h = (bb[3] - bb[1]) + 4

    def resize(self, w, h):
        self.width, self.height = w, h
        self._build_fonts()
        self._row_lines = []          # widths changed → recompute on next render

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
        self.bar_focus = None
        self._scroll_top = 0
        self._compute_row_lines()
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
        # Cycle: Back/Menu bar -> row0 -> ... -> rowN -> bar (wraps around).
        if self.bar_focus:
            self.bar_focus = None
            self.sel = len(self.rows) - 1 if self.rows else 0   # wrap to bottom
        elif not self.rows or self.sel == 0:
            self.bar_focus = "back"
        else:
            self.sel -= 1

    def move_down(self):
        if self.bar_focus:
            self.bar_focus = None
            self.sel = 0
        elif not self.rows or self.sel >= len(self.rows) - 1:
            self.bar_focus = "back"                              # wrap up to the bar
        else:
            self.sel += 1

    def nav_horizontal(self, delta):
        """Left/Right: switch between the Back and Menu buttons while the bar is
        focused, otherwise page the list."""
        if self.bar_focus:
            self.bar_focus = "menu" if delta > 0 else "back"
        else:
            self.scroll(delta * 10)

    def scroll(self, delta):
        """Jump the selection by `delta` items (clamped, no wrap)."""
        if self.bar_focus:
            return
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

    def _row_pad(self) -> int:
        return max(8, int(self.height * 0.014))

    def _title_max(self, d, row, ax0, ax1):
        """Horizontal space a row's title has (after marker + right-aligned meta)."""
        marker = ">" if row.get("playable") else ""
        mark_w = self._tw(d, marker + " ", self.f_row) if marker else 0
        meta = row.get("meta", "")
        mw = self._tw(d, meta, self.f_meta) if meta else 0
        return (ax1 - (mw + 24 if meta else 12)) - (ax0 + 12 + mark_w)

    def _compute_row_lines(self):
        """Per-row title line count (1 or 2). Short titles stay one line (compact
        spacing); only long titles get a second line. Measured once per level."""
        d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        x0, _, x1, _ = self._panel()
        ax0, ax1 = x0 + 6, x1 - 6
        self._row_lines = []
        for row in self.rows:
            n = len(wrap_lines(d, row.get("title", "?"), self.f_row,
                               self._title_max(d, row, ax0, ax1), 2))
            self._row_lines.append(min(2, max(1, n)))

    def _row_h_at(self, i) -> int:
        lines = self._row_lines[i] if i < len(self._row_lines) else 1
        return lines * self._row_line_h + self._row_pad()

    def _ensure_visible(self):
        """Scroll so the selected row is fully on screen (variable row heights)."""
        _, top, _, bottom = self._panel()
        avail = bottom - top - 12
        if self.sel < self._scroll_top:
            self._scroll_top = self.sel
        while self._scroll_top < self.sel:
            h = sum(self._row_h_at(i) for i in range(self._scroll_top, self.sel + 1))
            if h <= avail:
                break
            self._scroll_top += 1

    def _row_rects(self):
        if len(self._row_lines) != len(self.rows):
            self._compute_row_lines()     # after a resize / stale measurement
        x0, top, x1, bottom = self._panel()
        self._ensure_visible()
        out = []
        y = top + 6
        for i in range(self._scroll_top, len(self.rows)):
            h = self._row_h_at(i)
            if y + h > bottom - 6:
                break
            out.append((i, x0 + 6, y, x1 - 6, y + h))
            y += h
        return out

    def hit_test(self, x, y) -> Optional[int]:
        if self.mode != "browse":
            return None
        for (i, ax0, ay0, ax1, ay1) in self._row_rects():
            if ax0 <= x <= ax1 and ay0 <= y <= ay1:
                return i
        return None

    def _back_rect(self):
        x0 = int(self.width * 0.04)
        y0 = int(self.height * 0.155)
        w = max(86, int(self.width * 0.10))
        h = max(26, int(self.height * 0.045))
        return (x0, y0, x0 + w, y0 + h)

    def hit_back(self, x, y) -> bool:
        if self.mode != "browse":
            return False
        bx0, by0, bx1, by1 = self._back_rect()
        return bx0 <= x <= bx1 and by0 <= y <= by1

    def _menu_rect(self):
        _, by0, _, by1 = self._back_rect()
        w = max(86, int(self.width * 0.10))
        x1 = int(self.width * 0.96)
        return (x1 - w, by0, x1, by1)

    def hit_menu(self, x, y) -> bool:
        if self.mode != "browse":
            return False
        mx0, my0, mx1, my1 = self._menu_rect()
        return mx0 <= x <= mx1 and my0 <= y <= my1

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

        # Back button (clickable; also reachable by D-pad/keyboard — Up from the
        # top row focuses the bar, Left/Right switch buttons, A/Enter activates).
        bx0, by0, bx1, by1 = self._back_rect()
        d.rectangle([bx0, by0, bx1, by1], fill=(OSD_BG[0], OSD_BG[1], OSD_BG[2], 255),
                    outline=CHANNEL_GREEN if self.bar_focus == "back" else OSD_BORDER,
                    width=3 if self.bar_focus == "back" else 2)
        bl = "< BACK"
        d.text((bx0 + 10, by0 + (by1 - by0 - self._th(d, bl, self.f_foot)) // 2),
               bl, font=self.f_foot, fill=CYAN)

        # Menu button (clickable; opens the Plex context menu).
        mx0, my0, mx1, my1 = self._menu_rect()
        d.rectangle([mx0, my0, mx1, my1], fill=(OSD_BG[0], OSD_BG[1], OSD_BG[2], 255),
                    outline=CHANNEL_GREEN if self.bar_focus == "menu" else OSD_BORDER,
                    width=3 if self.bar_focus == "menu" else 2)
        ml = "MENU ="
        mw = self._tw(d, ml, self.f_foot)
        d.text((mx0 + (mx1 - mx0 - mw) // 2,
                my0 + (my1 - my0 - self._th(d, ml, self.f_foot)) // 2),
               ml, font=self.f_foot, fill=CYAN)

        # List panel
        x0, top, x1, bottom = self._panel()
        d.rectangle([x0, top, x1, bottom], fill=(OSD_BG[0], OSD_BG[1], OSD_BG[2], 255),
                    outline=OSD_BORDER, width=3)

        line_h = self._row_line_h
        for (i, ax0, ay0, ax1, ay1) in self._row_rects():
            row = self.rows[i]
            sel = (i == self.sel and not self.bar_focus)
            if sel:
                d.rectangle([ax0, ay0, ax1, ay1],
                            fill=(GUIDE_SELECTED[0], GUIDE_SELECTED[1],
                                  GUIDE_SELECTED[2], 255),
                            outline=CHANNEL_GREEN, width=2)
            marker = ">" if row.get("playable") else ""
            mark_w = self._tw(d, marker + " ", self.f_row) if marker else 0
            text_x = ax0 + 12 + mark_w
            meta = row.get("meta", "")
            mw = self._tw(d, meta, self.f_meta) if meta else 0
            # Title wraps to <=2 lines only when it doesn't fit one.
            title_max = (ax1 - (mw + 24 if meta else 12)) - text_x
            lines = wrap_lines(d, row.get("title", "?"), self.f_row, title_max, 2)
            bt = ay0 + ((ay1 - ay0) - len(lines) * line_h) // 2   # vertically center
            if marker:
                d.text((ax0 + 12, self._vy(d, marker, self.f_row, bt, line_h)),
                       marker, font=self.f_row, fill=WHITE if sel else WHITE_DIM)
            for li, ln in enumerate(lines):
                d.text((text_x, self._vy(d, ln, self.f_row, bt + li * line_h, line_h)),
                       ln, font=self.f_row, fill=WHITE if sel else WHITE_DIM)
            if meta:
                d.text((ax1 - mw - 12, self._vy(d, meta, self.f_meta, bt, line_h)),
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
        # Trademark disclaimer — Cathode is an independent Plex client.
        self._center(d, "Cathode is not affiliated with or endorsed by Plex.",
                     self.f_foot, self.height - int(self.height * 0.10), GRAY)
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

    @staticmethod
    def _vy(d, text, font, ry, h) -> int:
        """Y to draw `text` ink-centered in a slot of height `h` at `ry`."""
        bb = d.textbbox((0, 0), text or "X", font=font)
        return ry + (h - (bb[3] - bb[1])) // 2 - bb[1]
