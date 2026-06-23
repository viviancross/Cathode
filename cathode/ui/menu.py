"""In-app retro context menu overlay.

A modal popup list navigable by keyboard, the Steam Deck controller (which maps
to the arrow/enter keys), and the mouse (hover + click).  The app builds the
item tree (with callbacks); this module only handles layout, navigation, and
hit-testing.  Opened/closed with right-click.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from PIL import Image, ImageDraw

from .theme import (
    get_font, ellipsize, OSD_BG, OSD_BORDER, WHITE, WHITE_DIM, CYAN, YELLOW, GRAY,
    CHANNEL_GREEN, GUIDE_SELECTED,
)


class MenuItem:
    def __init__(self, label: str, action: Optional[Callable] = None,
                 submenu=None, hint: str = "", checked: bool = False,
                 enabled: bool = True, close_after: bool = True,
                 back_after: bool = False):
        self.label = label
        self.action = action          # called on activate
        self.submenu = submenu        # callable -> List[MenuItem]  (or a list)
        self.hint = hint              # right-aligned hint text (e.g. hotkey)
        self.checked = checked        # show a marker (active option)
        self.enabled = enabled
        self.close_after = close_after  # close the menu after the action runs
        self.back_after = back_after    # return to the previous menu after it


class ContextMenu:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.open = False
        self._stack: list = []        # [[items, selected_idx, title], ...]
        self._build_fonts()

    # ── setup / lifecycle ─────────────────────────────────────────────────

    def _build_fonts(self):
        self.font = get_font(max(14, int(self.height * 0.030)))
        self.font_title = get_font(max(16, int(self.height * 0.034)))
        # Measure real ink heights so rows fit the active font and text centers
        # exactly (any bundled or user font, no overlap).
        d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        ib = d.textbbox((0, 0), "Ag", font=self.font)
        tb = d.textbbox((0, 0), "Ag", font=self.font_title)
        self._item_ink = ib[3] - ib[1]
        self._title_ink = tb[3] - tb[1]

    @staticmethod
    def _vy(d, text, font, ry, row_h):
        """Y to draw `text` so its ink is vertically centered in [ry, ry+row_h]
        (subtracts the glyph bbox top, which plain (row_h - h)//2 ignores)."""
        bb = d.textbbox((0, 0), text or "X", font=font)
        return ry + (row_h - (bb[3] - bb[1])) // 2 - bb[1]

    def resize(self, width: int, height: int):
        self.width, self.height = width, height
        self._build_fonts()

    def refresh_fonts(self):
        self._build_fonts()

    def open_with(self, items: List[MenuItem], title: str = "CATHODE"):
        self._stack = [[items, 0, title]]
        self._select_first()
        self.open = True

    def close(self):
        self.open = False
        self._stack = []

    def snapshot(self):
        """Capture the open menu (stack + highlights) so a modal dialog can
        replace it and later return the user to exactly where they were."""
        if not self.open or not self._stack:
            return None
        return [[list(items), idx, title] for items, idx, title in self._stack]

    def restore(self, snap):
        """Reopen a snapshot taken by snapshot() (or close if it was None)."""
        if not snap:
            self.close()
            return
        self._stack = [[list(items), idx, title] for items, idx, title in snap]
        self.open = True

    # ── navigation ────────────────────────────────────────────────────────

    @property
    def _page(self):
        return self._stack[-1] if self._stack else None

    def _items(self) -> List[MenuItem]:
        return self._page[0] if self._page else []

    def _back_present(self) -> bool:
        # Submenu pages show a clickable/highlightable Back row at the bottom.
        return len(self._stack) > 1

    def _select_first(self):
        p = self._page
        if not p:
            return
        for i, it in enumerate(p[0]):
            if it.enabled:
                p[1] = i
                return

    def move(self, delta: int):
        p = self._page
        if not p:
            return
        n = len(p[0])
        total = n + (1 if self._back_present() else 0)   # back is the row at index n
        if total == 0:
            return
        i = p[1]
        if i < 0:                      # nothing highlighted yet (mouse off-menu)
            i = -1 if delta > 0 else 0  # first Down -> 0, first Up -> last
        for _ in range(total + 1):
            i = (i + delta) % total
            if i == n or p[0][i].enabled:   # the Back row (i == n) is always selectable
                break
        p[1] = i

    def move_up(self):
        self.move(-1)

    def move_down(self):
        self.move(1)

    def activate(self):
        p = self._page
        if not p or p[1] < 0:                # nothing highlighted -> no-op
            return
        if self._back_present() and p[1] == len(p[0]):   # the Back row
            self.back()
            return
        if not p[0] or p[1] >= len(p[0]):
            return
        item = p[0][p[1]]
        if not item.enabled:
            return
        if item.submenu is not None:
            sub = item.submenu() if callable(item.submenu) else item.submenu
            self._stack.append([list(sub), 0, item.label.rstrip(" >")])
            self._select_first()
        elif item.action:
            item.action()
            if item.back_after:
                self.back()         # apply + return to the previous menu
            elif item.close_after:
                self.close()

    def replace_page(self, items: List[MenuItem]):
        """Rebuild the current page's items in place, preserving the highlight.
        Used after an action changes an item's own label (e.g. a toggle), so the
        new label shows without leaving the submenu."""
        p = self._page
        if not p:
            return
        p[0] = list(items)
        p[1] = min(max(p[1], 0), len(p[0]) - 1)

    def back_and_replace(self, items: List[MenuItem]):
        """Pop one level, then rebuild the page we land on — so a child-menu
        selection that changed a parent's label shows it on return."""
        if len(self._stack) > 1:
            self._stack.pop()
        self.replace_page(items)

    def back(self):
        """Go up one level, or close if at the root."""
        if len(self._stack) > 1:
            self._stack.pop()
        else:
            self.close()

    def set_hover(self, x: int, y: int):
        """Highlight the row under the cursor, or clear the highlight entirely
        when the cursor isn't over a selectable row (so a stale selection can't
        linger while the mouse is elsewhere)."""
        p = self._page
        if not p:
            return
        idx = self.hit_test(x, y)
        if idx is not None and (idx == len(p[0]) or p[0][idx].enabled):
            p[1] = idx          # idx == len(items) is the Back row
        else:
            p[1] = -1

    # ── geometry (shared by render + hit_test) ────────────────────────────

    def _row_h(self) -> int:
        # Fit the tallest text (title or item) + padding, so no row overlaps.
        ink = max(getattr(self, "_item_ink", 0), getattr(self, "_title_ink", 0))
        return max(22, int(self.height * 0.052), ink + max(10, int(self.height * 0.020)))

    def _max_visible(self) -> int:
        """How many item rows fit, reserving the pinned title (+ Back) rows."""
        row_h = self._row_h()
        pad = max(8, int(self.height * 0.018))
        avail = int(self.height * 0.90) - pad * 2
        reserved = 1 + (1 if self._back_present() else 0)   # title (+ back)
        return max(1, avail // row_h - reserved)

    def _window(self):
        """(first_visible_index, count) of the scrolling item window, kept around
        the current selection so a long category/library list scrolls instead of
        squashing."""
        n = len(self._items())
        mv = self._max_visible()
        if n <= mv:
            return 0, n
        sel = self._page[1] if self._page else 0
        anchor = sel if 0 <= sel < n else n - 1     # Back row -> anchor last item
        first = max(0, min(anchor - mv // 2, n - mv))
        return first, mv

    def _geometry(self):
        row_h = self._row_h()
        pad = max(8, int(self.height * 0.018))
        _, count = self._window()
        rows = 1 + count + (1 if self._back_present() else 0)   # title + window (+ back)
        panel_w = max(int(self.width * 0.32), 260)
        panel_h = pad * 2 + row_h * rows
        px = int(self.width * 0.06)
        py = max(int(self.height * 0.04), (self.height - panel_h) // 2)
        return px, py, panel_w, panel_h, row_h, pad

    def _row_rects(self):
        """(global_index, x0, y0, x1, y1) for each *visible* item row."""
        px, py, pw, ph, row_h, pad = self._geometry()
        first, count = self._window()
        top = py + pad + row_h            # below the title row
        rects = []
        for vi in range(count):
            ry = top + vi * row_h
            rects.append((first + vi, px, ry, px + pw, ry + row_h))
        return rects

    def _back_rect(self):
        if not self._back_present():
            return None
        px, py, pw, ph, row_h, pad = self._geometry()
        _, count = self._window()
        ry = py + pad + row_h + count * row_h     # below the last visible row
        return (px, ry, px + pw, ry + row_h)

    def hit_test(self, x: int, y: int) -> Optional[int]:
        for (i, x0, y0, x1, y1) in self._row_rects():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return i
        br = self._back_rect()
        if br and br[0] <= x <= br[2] and br[1] <= y <= br[3]:
            return len(self._items())     # Back row sentinel
        return None

    # ── render ────────────────────────────────────────────────────────────

    def render(self) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        if not self.open or not self._page:
            return img
        d = ImageDraw.Draw(img)
        px, py, pw, ph, row_h, pad = self._geometry()

        d.rectangle([0, 0, self.width, self.height], fill=(0, 0, 0, 90))  # dim
        d.rectangle([px, py, px + pw, py + ph], fill=OSD_BG)
        d.rectangle([px, py, px + pw, py + ph], outline=OSD_BORDER, width=2)

        # Title (ink centered in its row; divider sits a few px below the row).
        title = self._page[2]
        d.text((px + pad + 6, self._vy(d, title, self.font_title, py + pad, row_h)),
               title, font=self.font_title, fill=YELLOW)
        d.line([px + pad, py + pad + row_h - 2, px + pw - pad, py + pad + row_h - 2],
               fill=OSD_BORDER, width=1)

        items = self._items()
        sel = self._page[1]
        win_first, win_count = self._window()
        # Scroll arrows when the list overflows the window.
        if win_first > 0:
            d.text((px + pw - pad - 14, self._vy(d, "^", self.font, py + pad, row_h)),
                   "^", font=self.font, fill=CYAN)
        if win_first + win_count < len(items):
            d.text((px + pw - pad - 14,
                    self._vy(d, "v", self.font, py + pad + win_count * row_h, row_h)),
                   "v", font=self.font, fill=CYAN)
        for (i, rx0, ry, rx1, ry1) in self._row_rects():
            it = items[i]
            if i == sel:
                d.rectangle([px + 4, ry, px + pw - 4, ry + row_h], fill=GUIDE_SELECTED)
            color = WHITE if it.enabled else GRAY
            mark = "* " if it.checked else "   "
            right = it.hint or (">" if it.submenu is not None else "")
            right_w = (d.textbbox((0, 0), right, font=self.font)[2]) if right else 0
            # Fit the label between the left padding and the right hint/arrow.
            label_max = pw - (pad + 6) - (right_w + pad + 10) - pad
            mark_w = int(d.textlength(mark, font=self.font))
            label = mark + ellipsize(d, it.label, self.font, label_max - mark_w)
            d.text((px + pad + 6, self._vy(d, label, self.font, ry, row_h)),
                   label, font=self.font, fill=(CHANNEL_GREEN if it.checked else color))
            if right:
                d.text((px + pw - pad - right_w, self._vy(d, right, self.font, ry, row_h)),
                       right, font=self.font,
                       fill=CYAN if it.submenu is not None else WHITE_DIM)

        # Back row (submenus only) — highlightable + clickable.
        br = self._back_rect()
        if br:
            bx0, by0, bx1, by1 = br
            if sel == len(items):
                d.rectangle([px + 4, by0, px + pw - 4, by1], fill=GUIDE_SELECTED)
            label = "< Back"
            d.text((px + pad + 6, self._vy(d, label, self.font, by0, row_h)),
                   label, font=self.font, fill=CYAN)
        return img

    @staticmethod
    def _th(d, text):
        bb = d.textbbox((0, 0), text or "X")
        return bb[3] - bb[1]
