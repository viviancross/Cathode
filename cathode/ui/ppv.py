"""Plex-Per-View browse screen — a retro 90s cable "pay-per-view" listing for a
Plex library. Full-screen and opaque; the app drives navigation and data, this
just renders the current level and a cursor. ASCII only (pixel fonts).
"""

from __future__ import annotations

from typing import List, Optional

from PIL import Image, ImageDraw

from .effects import draw_smpte_bars
from .theme import (
    get_font, ellipsize, wrap_lines, OSD_BG, OSD_BORDER, WHITE, WHITE_DIM, CYAN,
    YELLOW, INK_MUTED, CHANNEL_GREEN, GUIDE_SELECTED, SEL_TEXT, SCREEN_BG,
)


class PPVScreen:
    def __init__(self, width: int, height: int):
        self.open = False
        self.width = width
        self.height = height
        self.mode = "browse"          # "browse" | "auth"
        self.view = "list"            # "list" | "wall" — set from config by App
        self.min_row_h = 0            # physical floor for touch hosts (px); also
        # the signal that there IS a touch host, which changes what the footer
        # can usefully say
        self.title = "PLEX-PER-VIEW"
        self.rows: List[dict] = []    # {title, meta, playable, thumb, duration}
        self.sel = 0
        self.bar_focus = None         # None=list, "back" or "menu"=top bar button
        self._scroll_top = 0          # first visible row (variable-height scroll)
        self._wall_top = 0            # first visible tile ROW (poster wall)
        # Artwork, wired by App: `art_url(path, w, h)` builds a sized transcode
        # URL, `art_headers` carries the token so it stays out of that URL and
        # out of the image cache key. `logos` is the shared LogoStore.
        self.logos = None
        self.art_url = None
        self.art_headers = {}
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
        _d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        # The wordmark is sized off the height, so in a narrow box it runs off
        # both edges. Shrink it to the width it actually has.
        bpx = max(28, int(h * 0.075))
        self.f_banner = get_font(bpx)
        avail = self.width - 2 * max(16, int(self.width * 0.04))
        bw = _d.textlength("PLEX-PER-VIEW", font=self.f_banner)
        if bw > avail > 0:
            self.f_banner = get_font(max(16, int(bpx * avail / bw)))
        self.f_title = get_font(max(16, int(h * 0.034)))
        # Requested sizes are kept, not just the fonts: get_font takes a target
        # ink height and returns a face whose nominal size is something else
        # entirely, so anything that needs to scale a font has to scale the
        # request rather than the face.
        self._row_px = max(14, int(h * 0.030))
        self._foot_px = max(12, int(h * 0.022))
        self.f_row = get_font(self._row_px)
        self.f_meta = get_font(max(12, int(h * 0.024)))
        self.f_foot = get_font(self._foot_px)
        # Measure the row font's actual line height so rows can hold 2 wrapped
        # lines without overlapping the next item.
        _d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        bb = _d.textbbox((0, 0), "Ag", font=self.f_row)
        self._row_line_h = (bb[3] - bb[1]) + 4
        bb = _d.textbbox((0, 0), "Ag", font=self.f_meta)
        self._meta_line_h = (bb[3] - bb[1]) + 4

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
        self._wall_top = 0
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

    def _step(self) -> int:
        """How far one vertical move travels: a row in the list, a whole row of
        tiles on the wall."""
        return self._wall_metrics()[0] if self.view == "wall" else 1

    def move_up(self):
        # Cycle: Back/Menu bar -> row0 -> ... -> rowN -> bar (wraps around).
        step = self._step()
        if self.bar_focus:
            self.bar_focus = None
            self.sel = len(self.rows) - 1 if self.rows else 0   # wrap to bottom
        elif not self.rows or self.sel < step:
            self.bar_focus = "back"           # already on the top row
        else:
            self.sel -= step

    def move_down(self):
        step = self._step()
        if self.bar_focus:
            self.bar_focus = None
            self.sel = 0
        elif not self.rows or self.sel >= len(self.rows) - 1:
            self.bar_focus = "back"                              # wrap up to the bar
        elif self.sel + step >= len(self.rows):
            # A short final row still catches the cursor. Refusing to move
            # because sel+cols is past the end would strand it mid-grid.
            self.sel = len(self.rows) - 1
        else:
            self.sel += step

    def nav_horizontal(self, delta):
        """Left/Right: switch between the Back and Menu buttons while the bar is
        focused; otherwise page the list, or step one tile along the wall."""
        if self.bar_focus:
            self.bar_focus = "menu" if delta > 0 else "back"
        elif self.view == "wall":
            self.scroll(delta)
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

    def _metrics(self):
        """Header flow: (title_row_y, row_h, bar_h, panel_top).

        Measured rather than fixed fractions of the height: the banner, the
        subtitle, the title row and the breadcrumb stack, and at phone
        proportions the fixed fractions put the Back button through the title
        and the breadcrumb through the top of the list.
        """
        d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        h = self.height
        gap = int(h * 0.022)
        y = int(h * 0.03)
        y += self._th(d, "PLEX-PER-VIEW", self.f_banner) + gap
        y += self._th(d, "CATHODE ON DEMAND", self.f_meta) + gap
        bar_h = max(26, self.min_row_h, int(h * 0.045))
        row_h = max(self._th(d, "Ag", self.f_title), bar_h)
        panel_top = (y + row_h + self._th(d, "Ag", self.f_meta)
                     + max(4, int(h * 0.010)) + max(6, int(h * 0.012)))
        return y, row_h, bar_h, panel_top

    def _bar_btn_w(self, label: str) -> int:
        d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        return max(86, int(self.width * 0.10),
                   int(d.textlength(label, font=self.f_foot)) + 24)

    def _panel(self):
        m = max(16, int(self.width * 0.04))
        _, _, _, top = self._metrics()
        # The footer is keyboard/controller hints; a touch host has the Back and
        # Menu buttons on screen instead, so the list takes that space back.
        foot = 0.03 if self.min_row_h else 0.09
        return m, top, self.width - m, self.height - int(self.height * foot)

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
        """Drop the per-row title measurements; they are recomputed on demand.

        Measuring every row up front cost half a second on a 5000-title library
        — and a Plex library that size is ordinary. Only the rows actually on
        screen need measuring, so the list is sized here and filled lazily by
        _row_h_at.
        """
        self._row_lines = [None] * len(self.rows)

    def _row_h_at(self, i) -> int:
        if not (0 <= i < len(self._row_lines)):
            return max(self._row_line_h + self._row_pad(), self.min_row_h)
        lines = self._row_lines[i]
        if lines is None:
            d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
            x0, _, x1, _ = self._panel()
            row = self.rows[i]
            n = len(wrap_lines(d, row.get("title", "?"), self.f_row,
                               self._title_max(d, row, x0 + 6, x1 - 6), 2))
            lines = self._row_lines[i] = min(2, max(1, n))
        return max(lines * self._row_line_h + self._row_pad(), self.min_row_h)

    def _ensure_visible(self):
        """Scroll so the selected row is fully on screen (variable row heights).

        Walks back from the selection rather than forward from the top: the old
        version re-summed the whole range on every step, so jumping to the end
        of a 5000-row library was quadratic and took nearly seven seconds —
        which is exactly what returning from an item near the bottom of a large
        library did. This is bounded by the number of rows that fit on screen.
        """
        _, top, _, bottom = self._panel()
        avail = bottom - top - 12
        if self.sel < self._scroll_top:
            self._scroll_top = self.sel
            return
        used, first = 0, self.sel
        for i in range(self.sel, -1, -1):
            h = self._row_h_at(i)
            if used + h > avail:
                break
            used += h
            first = i
        if self._scroll_top < first:
            self._scroll_top = first

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

    # ── poster wall geometry ──────────────────────────────────────────────

    def _wall_label_px(self, tw: int):
        """Label sizes for a tile `tw` wide, as (title_px, meta_px).

        Sized off the TILE, not off the screen height like every other font
        here. The list's row font in a 118px tile ellipsised every title down to
        three characters — the wall is denser than the list, so its text has to
        be measured against the box it actually lands in.
        """
        tpx = max(9, min(self._row_px, int(tw * 0.16)))
        # The metadata line is a good deal smaller than the title, not merely a
        # little: it carries three fields ("1982 R 8.2") where the title needs
        # only to be recognisable, and at 0.8 the rating and score fell off it.
        return tpx, max(8, int(tpx * 0.70))

    def _wall_label_h(self, tw: int) -> int:
        tpx, mpx = self._wall_label_px(tw)
        return int(tpx * 1.35) + int(mpx * 1.35) + 6

    def _wall_metrics(self):
        """Tile grid for the current panel: (cols, tile_w, poster_h, gap).

        The column count is derived, never fixed: the app runs 1280x800 in the
        hand and 1920x1080 docked, and a count tuned for one is wrong for the
        other. The rule is the largest tile that still shows two WHOLE rows —
        a clipped second row reads as a rendering fault, not as "more below".

        Deriving it here also keeps the cursor honest: move_up/move_down step by
        whatever this returns, so the grid and the cursor cannot drift apart.
        """
        x0, top, x1, bottom = self._panel()
        avail_w = (x1 - x0) - 12
        avail_h = (bottom - top) - 12
        gap = max(8, int(self.width * 0.010))
        last = (3, avail_w, 0, gap)
        for cols in range(3, 13):
            tw = (avail_w - gap * (cols - 1)) // cols
            if tw <= 0:
                break
            ph = int(tw * 1.5)                       # posters are 2:3
            last = (cols, tw, ph, gap)
            if 2 * (ph + self._wall_label_h(tw)) + gap <= avail_h:
                return last
        return last                                  # nothing fits two rows

    def _wall_tile_h(self) -> int:
        _, tw, ph, _ = self._wall_metrics()
        return ph + self._wall_label_h(tw)

    def _wall_visible_rows(self) -> int:
        _, top, _, bottom = self._panel()
        _, _, _, gap = self._wall_metrics()
        th = self._wall_tile_h() + gap
        return max(1, ((bottom - top - 12) + gap) // th)

    def _ensure_visible_wall(self, cols):
        row = self.sel // cols
        vis = self._wall_visible_rows()
        self._wall_top = min(self._wall_top, row)
        self._wall_top = max(self._wall_top, row - vis + 1)
        self._wall_top = max(0, self._wall_top)

    def _wall_rects(self):
        """(index, x0, y0, x1, y1) for each tile on screen. Only these indices
        may have artwork requested for them — see _render_wall."""
        cols, tw, ph, gap = self._wall_metrics()
        x0, top, x1, bottom = self._panel()
        self._ensure_visible_wall(cols)
        tile_h = self._wall_tile_h()
        out = []
        first = self._wall_top * cols
        y = top + 6
        i = first
        while i < len(self.rows):
            if y + tile_h > bottom - 6:
                break
            for c in range(cols):
                if i + c >= len(self.rows):
                    break
                tx = x0 + 6 + c * (tw + gap)
                out.append((i + c, tx, y, tx + tw, y + tile_h))
            i += cols
            y += tile_h + gap
        return out

    def hit_test(self, x, y) -> Optional[int]:
        if self.mode != "browse":
            return None
        rects = self._wall_rects() if self.view == "wall" else self._row_rects()
        for (i, ax0, ay0, ax1, ay1) in rects:
            if ax0 <= x <= ax1 and ay0 <= y <= ay1:
                return i
        return None

    def _back_rect(self):
        x0 = int(self.width * 0.04)
        row_y, row_h, bar_h, _ = self._metrics()
        w = self._bar_btn_w("< BACK")
        y0 = row_y + (row_h - bar_h) // 2
        return (x0, y0, x0 + w, y0 + bar_h)

    def _back_in_auth(self) -> bool:
        """Sign-in has a way out on screen wherever there isn't a key for it."""
        return bool(self.min_row_h)

    def hit_back(self, x, y) -> bool:
        if self.mode != "browse" and not (self.mode == "auth"
                                          and self._back_in_auth()):
            return False
        bx0, by0, bx1, by1 = self._back_rect()
        return bx0 <= x <= bx1 and by0 <= y <= by1

    def _menu_rect(self):
        _, by0, _, by1 = self._back_rect()
        w = self._bar_btn_w("MENU =")
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
        d.rectangle([0, 0, self.width, self.height], fill=SCREEN_BG)
        # Header — stacked with measured gaps so the lines never overlap.
        y = int(self.height * 0.03)
        self._center(d, "PLEX-PER-VIEW", self.f_banner, y, YELLOW)
        y += self._th(d, "PLEX-PER-VIEW", self.f_banner) + int(self.height * 0.022)
        self._center(d, "CATHODE ON DEMAND", self.f_meta, y, CYAN)
        y += self._th(d, "CATHODE ON DEMAND", self.f_meta) + int(self.height * 0.022)

        if self.mode == "auth":
            self._render_auth(d)
            if self._back_in_auth():
                self._draw_bar_button(d, self._back_rect(), "< BACK",
                                      self.bar_focus == "back")
            return img

        # Current level title (centered), with the breadcrumb/path right under
        # it — clipped to the middle half of the screen so it clears the Back
        # and Menu buttons on either side.
        row_y, row_h, _bar_h, _ = self._metrics()
        title_h = self._th(d, "Ag", self.f_title)
        # Clipped to the gap between the two buttons — on a narrow box that gap
        # is a good deal less than the middle half of the screen.
        bx1 = self._back_rect()[2]
        mx0 = self._menu_rect()[0]
        ttxt = ellipsize(d, self.title.upper(), self.f_title,
                         max(40, mx0 - bx1 - 24))
        self._center(d, ttxt, self.f_title, row_y + (row_h - title_h) // 2, WHITE)
        if self.crumb:
            cy = row_y + row_h + max(4, int(self.height * 0.010))
            ctxt = ellipsize(d, self.crumb, self.f_meta,
                             self.width - 2 * max(16, int(self.width * 0.04)))
            self._center(d, ctxt, self.f_meta, cy, WHITE_DIM)

        # Back button (clickable; also reachable by D-pad/keyboard — Up from the
        # top row focuses the bar, Left/Right switch buttons, A/Enter activates).
        self._draw_bar_button(d, self._back_rect(), "< BACK",
                              self.bar_focus == "back")
        # Menu button (clickable; opens the Plex context menu).
        self._draw_bar_button(d, self._menu_rect(), "MENU =",
                              self.bar_focus == "menu")

        # List panel
        x0, top, x1, bottom = self._panel()
        d.rectangle([x0, top, x1, bottom], fill=(OSD_BG[0], OSD_BG[1], OSD_BG[2], 255),
                    outline=OSD_BORDER, width=3)

        # Two presentations of the same rows and the same cursor. The wall is
        # browse-only: a status screen has nothing to tile.
        if self.view == "wall" and not self.status:
            self._render_wall(d, img)
        else:
            self._render_list(d)

        if self.status:
            sy = (top + bottom) // 2
            # Off-air motif: a small test-bar strip above the status.
            bw = int(self.width * 0.20)
            bh = max(10, int(self.height * 0.028))
            draw_smpte_bars(d, (self.width - bw) // 2, sy - bh - 14,
                            (self.width + bw) // 2, sy - 14)
            self._center(d, self.status, self.f_title, sy, YELLOW)
            # A status (empty level / error) is a dead end without a way out —
            # point at the exit in the active device's vocabulary.
            if self.min_row_h:
                back = "TAP BACK, ABOVE"
            else:
                back = "[B] BACK" if self.input_mode == "gamepad" else "[ESC] BACK"
            self._center(d, back, self.f_meta,
                         sy + self._th(d, self.status, self.f_title)
                         + max(6, int(self.height * 0.02)), WHITE_DIM)

        # Footer (device-aware hints). A touch host has no keys to name and the
        # controls it does have are already on screen and labelled, so the hints
        # are dropped rather than translated into instructions for tapping the
        # thing you are looking at.
        if not self.min_row_h:
            cur = self.current()
            act = "ORDER" if (cur and cur.get("playable")) else "OPEN"
            if self.input_mode == "gamepad":
                foot = f"[D-PAD] BROWSE    [A] {act}    [B] BACK"
            else:
                foot = f"[UP/DN] BROWSE    [ENTER] {act}    [ESC] BACK"
            foot_y = self.height - int(self.height * 0.06)
            self._center(d, foot, self.f_foot, foot_y, WHITE_DIM)
        return img

    def _render_list(self, d):
        """One row per item: title, an ORDER marker, right-aligned metadata."""
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
                       marker, font=self.f_row, fill=SEL_TEXT if sel else WHITE_DIM)
            for li, ln in enumerate(lines):
                # Titles at full strength, metadata at the muted step. The two
                # used to sit one alpha apart (185 vs a flat gray), which at ten
                # feet made a library read as one undifferentiated block; the
                # title is what you scan for, so it gets the whole ink.
                d.text((text_x, self._vy(d, ln, self.f_row, bt + li * line_h, line_h)),
                       ln, font=self.f_row, fill=SEL_TEXT if sel else WHITE)
            if meta:
                d.text((ax1 - mw - 12, self._vy(d, meta, self.f_meta, bt, line_h)),
                       meta, font=self.f_meta, fill=SEL_TEXT if sel else INK_MUTED)

    def _render_wall(self, d, img):
        """A grid of posters. `img` as well as `d` because compositing artwork
        needs alpha_composite, which ImageDraw cannot do."""
        _, tw_m, ph, _ = self._wall_metrics()
        tpx, mpx = self._wall_label_px(tw_m)
        f_tile = get_font(tpx)
        f_tile_meta = get_font(mpx)
        title_lh = int(tpx * 1.35)
        rects = self._wall_rects()
        for (i, tx0, ty0, tx1, ty1) in rects:
            row = self.rows[i]
            sel = (i == self.sel and not self.bar_focus)
            py1 = ty0 + ph
            art = self._tile_art(row, tx1 - tx0, ph)
            d.rectangle([tx0, ty0, tx1, py1],
                        fill=(OSD_BG[0], OSD_BG[1], OSD_BG[2], 255),
                        outline=CHANNEL_GREEN if sel else OSD_BORDER,
                        width=3 if sel else 1)
            if art is not None:
                # _fit preserves aspect, so non-2:3 art leaves bars; centre it
                # on the filled tile rather than cropping heads off portraits.
                img.alpha_composite(art, (tx0 + (tx1 - tx0 - art.width) // 2,
                                          ty0 + (ph - art.height) // 2))
            elif row.get("thumb"):
                # Artwork was expected. None also means "still downloading", so
                # this doubles as the loading state and resolves itself when
                # on_loaded re-renders.
                self._center_in(d, "NO ART", f_tile_meta, tx0, ty0, tx1, py1, INK_MUTED)
            else:
                # Nothing to draw and nothing coming: a folder, a genre, or the
                # pinned "Sort by:" row. Carry the title into the plate — as a
                # NO ART box under a name clipped to "Sort..." it reads as a
                # broken film rather than as the control it is.
                self._plate_text(d, row.get("title", "?"), f_tile,
                                 tx0, ty0, tx1, py1)
            # Resume bar along the bottom of the poster.
            off, dur = row.get("offset", 0), row.get("duration", 0)
            if off > 5 and dur:
                bar_h = max(3, int(ph * 0.02))
                pct = min(1.0, off / dur)
                d.rectangle([tx0 + 2, py1 - bar_h, tx0 + 2 + int((tx1 - tx0 - 4) * pct),
                             py1 - 1], fill=CHANNEL_GREEN)
            # Label under the tile: title on one line, metadata dimmer below.
            ly = py1 + 3
            meta = " ".join(row.get("meta", "").split())
            # An artless row put its title in the plate, so its strip may have
            # nothing to show — highlighting an empty bar just looks broken.
            if sel and (row.get("thumb") or meta):
                d.rectangle([tx0, ly - 2, tx1, ty1],
                            fill=(GUIDE_SELECTED[0], GUIDE_SELECTED[1],
                                  GUIDE_SELECTED[2], 255))
            # A plate already carries the whole title; repeating it clipped
            # underneath adds nothing.
            if row.get("thumb"):
                # ellipsize() is the ASCII one from theme — the pixel fonts have
                # no U+2026 and would draw tofu.
                title = ellipsize(d, row.get("title", "?"), f_tile, tx1 - tx0 - 6)
                d.text((tx0 + 3, ly), title, font=f_tile,
                       fill=SEL_TEXT if sel else WHITE)
            # `meta` was normalised above: the list separates its fields with a
            # double space to hold them apart across a wide row, which in a tile
            # wastes the width the fields themselves need and ellipsises
            # "1982  R  8.2" down to the year plus a marooned "...".
            if meta:
                d.text((tx0 + 3, ly + title_lh),
                       ellipsize(d, meta, f_tile_meta, tx1 - tx0 - 6),
                       font=f_tile_meta, fill=SEL_TEXT if sel else INK_MUTED)

    def _tile_art(self, row, w, h):
        """Poster for one tile, or None when there is none (or it is still
        downloading). Only ever called for tiles being drawn: LogoStore starts a
        thread per URL, so asking for every row of a 500-title library would be
        500 threads and 500 downloads to fill twenty boxes."""
        thumb = row.get("thumb", "")
        if not thumb or self.logos is None or self.art_url is None:
            return None
        url = self.art_url(thumb, w, h)
        if not url:
            return None
        return self.logos.get(url, w, h, headers=self.art_headers)

    def _plate_text(self, d, text, font, x0, y0, x1, y1):
        """A title wrapped and centred inside an artless tile, so a folder or the
        Sort row reads as itself rather than as a film whose poster failed."""
        lines = wrap_lines(d, text, font, (x1 - x0) - 10, 4)
        if not lines:
            return
        lh = self._th(d, "Ag", font) + 4
        y = y0 + ((y1 - y0) - len(lines) * lh) // 2
        for ln in lines:
            w = self._tw(d, ln, font)
            d.text((x0 + ((x1 - x0) - w) // 2, y), ln, font=font, fill=WHITE_DIM)
            y += lh

    def _center_in(self, d, text, font, x0, y0, x1, y1, color):
        bb = d.textbbox((0, 0), text, font=font)
        d.text((x0 + (x1 - x0 - (bb[2] - bb[0])) // 2 - bb[0],
                y0 + (y1 - y0 - (bb[3] - bb[1])) // 2 - bb[1]),
               text, font=font, fill=color)

    def _render_auth(self, d):
        cy = int(self.height * 0.30)
        self._center(d, "SIGN IN TO PLEX", self.f_title, cy, WHITE)
        # "your phone" is wrong advice when the phone is what you're holding.
        m = max(16, int(self.width * 0.04))
        where = ("On another device, go to:" if self.min_row_h
                 else "On your phone or PC, go to:")
        self._center_fitted(d, where, self._row_px, cy + int(self.height * 0.09),
                            self.width - 2 * m, WHITE_DIM)
        self._center(d, self.auth_link or "plex.tv/link", self.f_title,
                     cy + int(self.height * 0.15), CYAN)
        self._center(d, "and enter this code:", self.f_row,
                     cy + int(self.height * 0.24), WHITE_DIM)
        self._center(d, self.auth_code or "----", self.f_banner,
                     cy + int(self.height * 0.30), CHANNEL_GREEN)
        msg = self.auth_msg or "Waiting for you to link..."
        self._center(d, msg, self.f_meta, cy + int(self.height * 0.42), INK_MUTED)
        # Trademark disclaimer — Cathode is an independent Plex client. This one
        # is not allowed to be clipped, so it is fitted to the box rather than
        # trusted to a font sized off the height.
        self._center_fitted(d, "Cathode is not affiliated with or endorsed by Plex.",
                            self._foot_px, self.height - int(self.height * 0.10),
                            self.width - 2 * m, INK_MUTED)
        # A touch host gets the Back button the browse view already has, drawn
        # by render() — naming a key it hasn't got is worse than nothing.
        if not self.min_row_h:
            cancel = "[B] CANCEL" if self.input_mode == "gamepad" else "[ESC] CANCEL"
            self._center(d, cancel, self.f_foot,
                         self.height - int(self.height * 0.06), WHITE_DIM)

    # ── text helpers ──────────────────────────────────────────────────────

    def _center(self, d, text, font, y, color):
        w = self._tw(d, text, font)
        d.text(((self.width - w) // 2, y), text, font=font, fill=color)

    def _center_fitted(self, d, text, base_px, y, max_w, color):
        """Centred, at whatever size keeps the whole line inside `max_w`.

        For copy that must not be clipped or ellipsised — a line that has to be
        read in full, not merely be present.
        """
        px = max(9, int(base_px))
        while px > 9 and self._tw(d, text, get_font(px)) > max_w:
            px -= 1
        font = get_font(px)
        w = self._tw(d, text, font)
        d.text(((self.width - w) // 2, y), text, font=font, fill=color)

    def _draw_bar_button(self, d, rect, label, focused):
        x0, y0, x1, y1 = rect
        d.rectangle([x0, y0, x1, y1],
                    fill=(OSD_BG[0], OSD_BG[1], OSD_BG[2], 255),
                    outline=CHANNEL_GREEN if focused else OSD_BORDER,
                    width=3 if focused else 2)
        self._btn_label(d, label, self.f_foot, x0, y0, x1, y1, CYAN)

    def _btn_label(self, d, text, font, x0, y0, x1, y1, color):
        """Center `text` in the button box on BOTH axes, subtracting the glyph
        bbox offset so it's truly centered for any font (tall pixel fonts carry
        big left/top bearing and would otherwise sit low and off-center)."""
        bb = d.textbbox((0, 0), text, font=font)
        lx = x0 + (x1 - x0 - (bb[2] - bb[0])) // 2 - bb[0]
        ly = y0 + (y1 - y0 - (bb[3] - bb[1])) // 2 - bb[1]
        d.text((lx, ly), text, font=font, fill=color)

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
