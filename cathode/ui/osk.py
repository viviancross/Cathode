"""On-screen keyboard overlay — in-app text entry (replaces tkinter dialogs).

Driven by the same inputs as the rest of the UI: arrow keys / Enter / Esc, the
Steam Deck controller (mapped to those), and mouse hover + click.  Used for the
M3U / XMLTV URLs and for naming profiles.  All glyphs are ASCII (pixel fonts).
"""

from __future__ import annotations

from typing import Callable, Optional

from PIL import Image, ImageDraw

from .theme import (
    get_font, OSD_BG, OSD_BORDER, WHITE, WHITE_DIM, YELLOW, INK_MUTED,
    BLACK, CHANNEL_GREEN, GUIDE_SELECTED, SEL_TEXT, SCREEN_BG,
)

_SPECIAL = {"SHIFT", "SPACE", "DEL", "CLR", "CANCEL", "DONE"}

_ROWS = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl"),
    list("zxcvbnm"),
    list("./:-_?=&%@~#+,"),
    ["SHIFT", "SPACE", "DEL", "CLR", "CANCEL", "DONE"],
]


class OnScreenKeyboard:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.open = False
        self.text = ""
        self.cursor = 0           # caret index into self.text
        self.prompt = ""
        self._shift = False
        self._sel = [0, 0]
        self._field_box = None    # (x0,y0,x1,y1) of the text field, last render
        self.min_row_h = 0        # physical floor for touch hosts (px)
        # Called when the field is tapped while the on-screen keys are hidden:
        # the host's own keyboard is driving the field and may have been
        # dismissed, and there is otherwise no way to ask for it back.
        self.on_reopen = None
        self._field_start = 0     # first visible char index, last render
        self._on_done: Optional[Callable] = None
        self._on_cancel: Optional[Callable] = None
        self.input_mode = "key"   # "key" or "gamepad" — picks the caret hint
        # Draw the key grid, or just the prompt and field. A platform with its
        # own keyboard (Android) turns the grid off and lets the system IME do
        # the typing; the field stays so what you type is still shown in-world.
        self.keys_visible = True
        self._build_fonts()

    def _build_fonts(self):
        self.font = get_font(max(16, int(self.height * 0.034)))
        self.font_small = get_font(max(13, int(self.height * 0.026)))

    def resize(self, width, height):
        self.width, self.height = width, height
        self._build_fonts()

    def refresh_fonts(self):
        self._build_fonts()

    # ── open / finish ─────────────────────────────────────────────────────

    def show(self, prompt: str, initial: str = "",
             on_done: Optional[Callable] = None,
             on_cancel: Optional[Callable] = None):
        self.prompt = prompt
        self.text = initial or ""
        self.cursor = len(self.text)
        self._shift = False
        self._sel = [0, 0]
        self._on_done = on_done
        self._on_cancel = on_cancel
        self.open = True

    def _finish(self, result: Optional[str]):
        self.open = False
        done, cancel = self._on_done, self._on_cancel
        self._on_done = self._on_cancel = None
        if result is not None and done:
            done(result)
        elif result is None and cancel:
            cancel()

    # ── navigation / input ────────────────────────────────────────────────

    def move(self, dr: int, dc: int):
        r, c = self._sel
        if dr:
            r = (r + dr) % len(_ROWS)          # wrap top/bottom
            c = min(c, len(_ROWS[r]) - 1)
        if dc:
            c = (c + dc) % len(_ROWS[r])        # wrap left/right
        self._sel = [r, c]

    def move_up(self):    self.move(-1, 0)
    def move_down(self):  self.move(1, 0)
    def move_left(self):  self.move(0, -1)
    def move_right(self): self.move(0, 1)

    # text caret (bumpers / click) — distinct from the key-grid selection above
    def cursor_left(self):
        self.cursor = max(0, self.cursor - 1)

    def cursor_right(self):
        self.cursor = min(len(self.text), self.cursor + 1)

    def press(self):
        """Activate the highlighted on-screen key (the 'Select' action)."""
        cell = _ROWS[self._sel[0]][self._sel[1]]
        self._activate(cell)

    def confirm(self):
        """Submit the entered text (what Enter does)."""
        self._finish(self.text)

    def _activate(self, cell: str):
        if cell == "SHIFT":
            self._shift = not self._shift
        elif cell == "SPACE":
            self._insert_at(" ")
        elif cell == "DEL":
            self.backspace()
        elif cell == "CLR":
            self.text = ""
            self.cursor = 0
        elif cell == "CANCEL":
            self._finish(None)
        elif cell == "DONE":
            self._finish(self.text)
        else:
            self._insert_at(cell.upper() if (self._shift and cell.isalpha()) else cell)

    def cancel(self):
        self._finish(None)

    def _insert_at(self, s: str):
        self.text = self.text[:self.cursor] + s + self.text[self.cursor:]
        self.cursor += len(s)

    def backspace(self):
        """Delete the char before the caret."""
        if self.cursor > 0:
            self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
            self.cursor -= 1

    def insert(self, text: str):
        """Insert typed or pasted text at the caret (newlines stripped)."""
        if not text:
            return
        self._insert_at(text.replace("\r", "").replace("\n", ""))

    # ── geometry / hit-test / render ──────────────────────────────────────

    def _hint(self) -> str:
        if not self.keys_visible:
            # True whether or not that keyboard is currently up — and it tells
            # you how to get it back once it isn't.
            return "tap the field to type"
        if self.input_mode == "gamepad":
            return "[LB/RB] move cursor"
        return "type or Ctrl+V to paste"

    def _head(self):
        """(height, stacked) of the prompt row.

        The prompt sits left and the hint right. In a narrow panel the two run
        straight through each other, so they stack instead and the row grows to
        hold both.
        """
        d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        lh = d.textbbox((0, 0), "Ag", font=self.font_small)[3]
        avail = int(self.width * 0.82) - 2 * 16 - 20
        w = (d.textlength(self.prompt, font=self.font_small)
             + d.textlength(self._hint(), font=self.font_small))
        stacked = w > avail
        base = int(self.height * 0.06)
        return (max(base, 2 * lh + 24) if stacked else base), stacked

    def _geom(self):
        pw = int(self.width * 0.82)
        px = (self.width - pw) // 2
        key_h = max(30, int(self.height * 0.072))
        gap = max(4, int(self.width * 0.006))
        field_h = key_h + 10
        head_h = self._head()[0]
        ph = head_h + field_h + 24
        if self.keys_visible:
            ph += len(_ROWS) * (key_h + gap)
        else:
            # Field (+ an action row where one is reachable): the panel sits
            # high so a system keyboard sliding up from the bottom cannot cover
            # what is being typed.
            if self._has_actions():
                ph += self._action_h() + 12
            return px, int(self.height * 0.10), pw, ph, key_h, gap, field_h
        py = (self.height - ph) // 2
        return px, py, pw, ph, key_h, gap, field_h

    def _action_h(self) -> int:
        return max(36, self.min_row_h)

    def _has_actions(self) -> bool:
        """Does this host need our own confirm/cancel buttons?

        Only where a finger can reach them. Our drawn keyboard has CANCEL and
        DONE keys of its own, and on a television the keys are hidden in favour
        of the system's remote-driven keyboard — which the d-pad can reach and
        these buttons, sitting outside any focus ring, could not.
        """
        return not self.keys_visible and bool(self.min_row_h)

    def _action_rects(self):
        """(cancel, ok) button rects.

        With the host's keyboard driving the field there is nothing of ours on
        screen to confirm or cancel with, and dismissing that keyboard used to
        leave the prompt with no way out at all.
        """
        if not self._has_actions():
            return None
        px, py, pw, ph, _key_h, gap, _field_h = self._geom()
        bh = self._action_h()
        pad = 16
        by = py + ph - bh - 12
        bw = (pw - 2 * pad - gap) // 2
        return ((px + pad, by, px + pad + bw, by + bh),
                (px + pw - pad - bw, by, px + pw - pad, by + bh))

    def _key_rects(self):
        if not self.keys_visible:
            return []
        px, py, pw, ph, key_h, gap, field_h = self._geom()
        top = py + self._head()[0] + field_h + 8
        rects = []
        for r, row in enumerate(_ROWS):
            n = len(row)
            kw = (pw - gap * (n + 1)) / n
            ry = top + r * (key_h + gap)
            for c in range(n):
                kx = px + gap + c * (kw + gap)
                rects.append((r, c, int(kx), int(ry), int(kx + kw), int(ry + key_h)))
        return rects

    def hit_test(self, x, y):
        for (r, c, x0, y0, x1, y1) in self._key_rects():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return r, c
        return None

    def set_hover(self, x, y):
        hit = self.hit_test(x, y)
        if hit:
            self._sel = [hit[0], hit[1]]

    def click(self, x, y):
        acts = self._action_rects()
        if acts:
            for rect, fn in zip(acts, (self.cancel, self.confirm)):
                if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                    fn()
                    return True
        if self._place_caret(x, y):
            if not self.keys_visible and self.on_reopen:
                # The field was tapped and our keys aren't the ones filling it.
                self.on_reopen()
            return True
        hit = self.hit_test(x, y)
        if hit:
            self._sel = [hit[0], hit[1]]
            self.press()
            return True
        return False

    def _place_caret(self, x, y) -> bool:
        """Click inside the text field -> move the caret to the nearest gap."""
        box = self._field_box
        if not box or not (box[0] <= x <= box[2] and box[1] <= y <= box[3]):
            return False
        d = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        fx = box[0] + 8                       # matches the text draw origin
        start = self._field_start
        best, best_dx = self.cursor, None
        for i in range(start, len(self.text) + 1):
            cx = fx + d.textlength(self.text[start:i], font=self.font)
            dx = abs(cx - x)
            if best_dx is None or dx < best_dx:
                best, best_dx = i, dx
        self.cursor = best
        return True

    def render(self) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        if not self.open:
            return img
        d = ImageDraw.Draw(img)
        px, py, pw, ph, key_h, gap, field_h = self._geom()
        # Fully opaque dialog — no video shows through anywhere while typing.
        # (ImageDraw fills REPLACE pixels incl. alpha, so every fill is alpha 255.)
        panel_bg = (OSD_BG[0], OSD_BG[1], OSD_BG[2], 255)
        key_bg = (min(255, OSD_BG[0] + 26), min(255, OSD_BG[1] + 26),
                  min(255, OSD_BG[2] + 30), 255)
        sel_bg = (GUIDE_SELECTED[0], GUIDE_SELECTED[1], GUIDE_SELECTED[2], 255)
        d.rectangle([0, 0, self.width, self.height], fill=SCREEN_BG)
        d.rectangle([px, py, px + pw, py + ph], fill=panel_bg)
        d.rectangle([px, py, px + pw, py + ph], outline=OSD_BORDER, width=2)

        pad = 16
        # Prompt + a caret/entry hint matched to the active device (LB/RB moving
        # the caret is invisible otherwise on a controller-only setup).
        d.text((px + pad, py + 10), self.prompt, font=self.font_small, fill=YELLOW)
        head_h, stacked = self._head()
        hint = self._hint()
        hb = d.textbbox((0, 0), hint, font=self.font_small)
        if stacked:
            d.text((px + pad, py + 10 + hb[3] + 4), hint,
                   font=self.font_small, fill=INK_MUTED)
        else:
            d.text((px + pw - pad - (hb[2] - hb[0]), py + 10),
                   hint, font=self.font_small, fill=INK_MUTED)
        # Text field
        fy = py + head_h
        fy1 = fy + field_h - 6
        d.rectangle([px + pad, fy, px + pw - pad, fy1], fill=BLACK)
        d.rectangle([px + pad, fy, px + pw - pad, fy1], outline=OSD_BORDER, width=1)
        self._field_box = (px + pad, fy, px + pw - pad, fy1)
        fx = px + pad + 8
        avail = pw - 2 * pad - 16
        # Horizontal scroll: pick a visible window that keeps the caret in view.
        start = 0
        while d.textlength(self.text[start:self.cursor], font=self.font) > avail:
            start += 1
        end = len(self.text)
        while end > start and d.textlength(self.text[start:end], font=self.font) > avail:
            end -= 1
        self._field_start = start
        d.text((fx, fy + 6), self.text[start:end], font=self.font, fill=CHANNEL_GREEN)
        # Caret
        cx = fx + d.textlength(self.text[start:self.cursor], font=self.font)
        d.line([cx, fy + 5, cx, fy1 - 5], fill=WHITE, width=2)

        # Action row — the only on-screen way to finish when the host's own
        # keyboard is filling the field (and the only one at all once that
        # keyboard has been dismissed).
        acts = self._action_rects()
        if acts:
            for rect, label, color in zip(acts, ("CANCEL", "OK"),
                                          (WHITE_DIM, CHANNEL_GREEN)):
                ax0, ay0, ax1, ay1 = rect
                d.rounded_rectangle([ax0, ay0, ax1, ay1], radius=6, fill=key_bg,
                                    outline=color, width=2)
                lb = d.textbbox((0, 0), label, font=self.font_small)
                d.text((ax0 + (ax1 - ax0 - (lb[2] - lb[0])) // 2 - lb[0],
                        ay0 + (ay1 - ay0 - (lb[3] - lb[1])) // 2 - lb[1]),
                       label, font=self.font_small, fill=color)

        # Keys
        for (r, c, x0, y0, x1, y1) in self._key_rects():
            cell = _ROWS[r][c]
            selected = [r, c] == self._sel
            d.rectangle([x0, y0, x1, y1], fill=(sel_bg if selected else key_bg))
            d.rectangle([x0, y0, x1, y1], outline=OSD_BORDER, width=1)
            label = cell
            if cell == "SPACE":
                label = "SPACE"
            elif cell == "SHIFT":
                label = "SHIFT*" if self._shift else "SHIFT"
            elif len(cell) == 1 and self._shift and cell.isalpha():
                label = cell.upper()
            color = WHITE
            if selected:
                color = SEL_TEXT           # readable on the highlight fill
            elif cell == "DONE":
                color = CHANNEL_GREEN
            elif cell == "CANCEL":
                color = WHITE_DIM
            bb = d.textbbox((0, 0), label, font=self.font_small)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            d.text((x0 + ((x1 - x0) - tw) // 2, y0 + ((y1 - y0) - th) // 2 - bb[1]),
                   label, font=self.font_small, fill=color)
        return img
