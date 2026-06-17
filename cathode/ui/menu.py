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
    get_font, OSD_BG, OSD_BORDER, WHITE, WHITE_DIM, CYAN, YELLOW, GRAY,
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

    # ── navigation ────────────────────────────────────────────────────────

    @property
    def _page(self):
        return self._stack[-1] if self._stack else None

    def _items(self) -> List[MenuItem]:
        return self._page[0] if self._page else []

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
        if not p or not p[0]:
            return
        n = len(p[0])
        i = p[1]
        if i < 0:                      # nothing highlighted yet (mouse off-menu)
            i = -1 if delta > 0 else 0  # first Down -> 0, first Up -> last
        for _ in range(n + 1):
            i = (i + delta) % n
            if p[0][i].enabled:
                break
        p[1] = i

    def move_up(self):
        self.move(-1)

    def move_down(self):
        self.move(1)

    def activate(self):
        p = self._page
        if not p or not p[0] or p[1] < 0:   # nothing highlighted -> no-op
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
        if idx is not None and p[0][idx].enabled:
            p[1] = idx
        else:
            p[1] = -1

    # ── geometry (shared by render + hit_test) ────────────────────────────

    def _geometry(self):
        items = self._items()
        rows = len(items) + 1  # + title row
        avail_h = int(self.height * 0.90)
        row_h = max(22, min(int(self.height * 0.052), avail_h // max(rows, 1)))
        pad = max(8, int(self.height * 0.018))
        panel_w = max(int(self.width * 0.32), 260)
        panel_h = pad * 2 + row_h * rows
        px = int(self.width * 0.06)
        py = max(int(self.height * 0.04), (self.height - panel_h) // 2)
        return px, py, panel_w, panel_h, row_h, pad

    def _row_rects(self):
        """List of (index, x0, y0, x1, y1) for each item row."""
        px, py, pw, ph, row_h, pad = self._geometry()
        first = py + pad + row_h          # below the title row
        rects = []
        for i in range(len(self._items())):
            ry = first + i * row_h
            rects.append((i, px, ry, px + pw, ry + row_h))
        return rects

    def hit_test(self, x: int, y: int) -> Optional[int]:
        for (i, x0, y0, x1, y1) in self._row_rects():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return i
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

        # Title
        title = self._page[2]
        d.text((px + pad + 6, py + pad + (row_h - self._th(d, title)) // 2),
               title, font=self.font_title, fill=YELLOW)
        d.line([px + pad, py + pad + row_h - 3, px + pw - pad, py + pad + row_h - 3],
               fill=OSD_BORDER, width=1)

        items = self._items()
        sel = self._page[1]
        first = py + pad + row_h
        for i, it in enumerate(items):
            ry = first + i * row_h
            if i == sel:
                d.rectangle([px + 4, ry, px + pw - 4, ry + row_h], fill=GUIDE_SELECTED)
            color = WHITE if it.enabled else GRAY
            mark = "* " if it.checked else "   "
            label = mark + it.label
            d.text((px + pad + 6, ry + (row_h - self._th(d, label)) // 2),
                   label, font=self.font, fill=(CHANNEL_GREEN if it.checked else color))
            right = it.hint or (">" if it.submenu is not None else "")
            if right:
                rb = d.textbbox((0, 0), right, font=self.font)
                d.text((px + pw - pad - (rb[2] - rb[0]),
                        ry + (row_h - self._th(d, right)) // 2),
                       right, font=self.font,
                       fill=CYAN if it.submenu is not None else WHITE_DIM)
        return img

    @staticmethod
    def _th(d, text):
        bb = d.textbbox((0, 0), text or "X")
        return bb[3] - bb[1]
