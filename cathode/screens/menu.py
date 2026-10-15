"""Menus and the on-screen keyboard."""

from typing import Callable, List, Optional

import pygame

from .. import remote as R
from ..app import Screen


class Item:
    """A menu row. Exactly one of `action` (run it) or `submenu` (a function
    returning the next page's items) is usual; `value` shows a setting on the
    right, and `adjust(delta)` lets LEFT/RIGHT change it in place."""

    def __init__(self, label: str, action: Optional[Callable] = None,
                 submenu: Optional[Callable[[], List["Item"]]] = None,
                 value: Optional[Callable[[], str]] = None,
                 adjust: Optional[Callable[[int], None]] = None,
                 enabled: bool = True, close: bool = False,
                 preview: Optional[Callable[[], None]] = None):
        self.label, self.action, self.submenu = label, action, submenu
        self.value, self.adjust, self.enabled = value, adjust, enabled
        self.close = close          # close the whole menu after the action
        self.preview = preview      # run when the cursor lands here (live previews)


class Menu(Screen):
    name = "menu"

    def __init__(self, app, title: str, items: List[Item]):
        super().__init__(app)
        self.pages = [[title, items, self._first(items)]]

    @staticmethod
    def _first(items):
        return next((i for i, it in enumerate(items) if it.enabled), 0)

    # The page on top.
    @property
    def title(self):
        return self.pages[-1][0]

    @property
    def items(self) -> List[Item]:
        return self.pages[-1][1]

    @property
    def cursor(self) -> int:
        return self.pages[-1][2]

    @cursor.setter
    def cursor(self, i):
        self.pages[-1][2] = i

    def open(self, title: str, items: List[Item]):
        self.pages.append([title, items, self._first(items)])

    def video_box(self):
        return self.app.skin.menu_video_box(self)

    def refresh(self, items: List[Item]):
        """Replace the current page's items, keeping the cursor."""
        self.pages[-1][1] = items
        self.cursor = min(self.cursor, len(items) - 1)

    def back(self):
        if len(self.pages) > 1:
            self.pages.pop()
        else:
            self.app.pop(self)

    def close(self):
        self.app.pop(self)

    def move(self, d: int):
        n = len(self.items)
        for _ in range(n):              # skip disabled rows, wrapping
            self.cursor = (self.cursor + d) % n
            if self.items[self.cursor].enabled:
                break
        self._landed()

    def _landed(self):
        it = self.items[self.cursor]
        if it.preview:
            it.preview()

    def activate(self, i: Optional[int] = None):
        if i is not None:
            if not (0 <= i < len(self.items)) or not self.items[i].enabled:
                return
            self.cursor = i
        it = self.items[self.cursor]
        if it.submenu:
            self.open(it.label, it.submenu())
        elif it.action:
            if it.close:
                self.close()
            it.action()
        elif it.adjust:
            it.adjust(1)

    def handle(self, a: str) -> bool:
        if not self.items:
            if a in (R.BACK, R.EXIT, R.MENU):
                self.close()
            return True
        it = self.items[self.cursor]
        cols = self.app.skin.menu_cols(self) if getattr(self.app, "skin", None) else 1
        if cols > 1 and a in (R.UP, R.DOWN, R.LEFT, R.RIGHT):
            # A grid of tiles (Plate Network's Main Menu): across, and down by a row.
            step = {R.LEFT: -1, R.RIGHT: 1, R.UP: -cols, R.DOWN: cols}[a]
            j = self.cursor + step
            if 0 <= j < len(self.items) and self.items[j].enabled:
                self.cursor = j
                self._landed()
        elif a == R.UP:
            self.move(-1)
        elif a == R.DOWN:
            self.move(1)
        elif a == R.SELECT:
            self.activate()
        elif a in (R.LEFT, R.RIGHT) and it.adjust:
            it.adjust(1 if a == R.RIGHT else -1)
        elif a == R.RIGHT and it.submenu:
            self.activate()
        elif a in (R.BACK, R.LEFT):
            self.back()
        elif a in (R.EXIT, R.MENU):
            self.close()
        elif a in R.DIGITS:
            # Numbered menus, as on the boxes: 1 picks the first row, 0 the tenth.
            n = int(a[-1]) or 10
            self.activate(n - 1)
        else:
            return a not in (R.VOL_UP, R.VOL_DOWN, R.MUTE, R.FULLSCREEN, R.QUIT)
        return True


class Keyboard(Screen):
    """Text entry for remote, controller, mouse, or a real keyboard (typing
    and paste go straight in). Calls on_done(text) on DONE, on_done(None) on
    CANCEL; never blocks anything while it's open."""
    name = "keyboard"
    opaque = True
    wants_text = True

    LAYERS = {
        "abc": ["1234567890", "qwertyuiop", "asdfghjkl:", "zxcvbnm./-"],
        "ABC": ["1234567890", "QWERTYUIOP", "ASDFGHJKL:", "ZXCVBNM./-"],
        "sym": ["!@#$%^&*()", "_+=?~'\"|\\;", "[]{}<>,`  ", "          "],
    }
    ACTIONS = ["SHIFT", "SYM", "SPACE", "DEL", "CLEAR", "CANCEL", "DONE"]

    def __init__(self, app, prompt: str, on_done: Callable[[Optional[str]], None],
                 initial: str = "", hint: str = ""):
        super().__init__(app)
        self.prompt, self.hint, self.on_done = prompt, hint, on_done
        self.value = initial
        self.caret = len(initial)
        self.layer = getattr(getattr(app, "skin", None), "keyboard_layer", "abc")
        # Start on the first letter: past the digits, never on an action.
        self.row, self.col = next(((r, c) for r, row in enumerate(self.grid()) for c, k in enumerate(row)
                                   if len(k) == 1 and k.isalpha()), (0, 0))
        pygame.key.start_text_input()

    def video_box(self):
        return self.app.skin.page_video_box(self)

    # Grid: key rows, then the action row(s). A skin may lay the keys out as
    # its box did; the actions keep their names (SHIFT, SPACE, DONE...).
    def grid(self) -> List[List[str]]:
        skin = getattr(self.app, "skin", None)
        rows = skin.keyboard_rows(self.layer) if skin else None
        if rows:
            return [list(r) for r in rows]
        return [list(r) for r in self.LAYERS[self.layer]] + [self.ACTIONS]

    def _press(self, cell: str):
        if cell == "SHIFT":
            self.layer = "ABC" if self.layer == "abc" else "abc"
        elif cell == "SYM":
            self.layer = "sym" if self.layer != "sym" else "abc"
        elif cell == "SPACE":
            self.insert(" ")
        elif cell == "DEL":
            self.backspace()
        elif cell == "CLEAR":
            self.value, self.caret = "", 0
        elif cell == "CANCEL":
            self._finish(None)
        elif cell == "DONE":
            self._finish(self.value.strip())
        elif cell.strip():
            self.insert(cell)

    def _finish(self, result):
        pygame.key.stop_text_input()
        self.app.pop(self)
        self.on_done(result)

    MAX = 4096         # long enough for any address with a token; a runaway paste stops here

    def insert(self, s: str):
        s = s[:max(0, self.MAX - len(self.value))]
        self.value = self.value[:self.caret] + s + self.value[self.caret:]
        self.caret += len(s)
        self.app.invalidate()

    def backspace(self):
        if self.caret > 0:
            self.value = self.value[:self.caret - 1] + self.value[self.caret:]
            self.caret -= 1

    def text(self, s: str):
        """Typed on a real keyboard."""
        self.insert("".join(ch for ch in s if ch.isprintable()))

    def paste(self):
        try:
            got = pygame.scrap.get_text() if hasattr(pygame.scrap, "get_text") else ""
        except pygame.error:
            got = ""
        if got:
            self.insert(got.strip().replace("\n", ""))

    def move(self, dr: int, dc: int):
        g = self.grid()
        self.row = (self.row + dr) % len(g)
        self.col = min(self.col, len(g[self.row]) - 1) if dr else (self.col + dc) % len(g[self.row])

    def handle(self, a: str) -> bool:
        if a == R.UP:
            self.move(-1, 0)
        elif a == R.DOWN:
            self.move(1, 0)
        elif a == R.LEFT:
            self.move(0, -1)
        elif a == R.RIGHT:
            self.move(0, 1)
        elif a == R.SELECT:
            self._press(self.grid()[self.row][self.col])
        elif a == R.BACK:
            self.backspace()
        elif a == R.EXIT:
            self._finish(None)
        elif a == R.CH_DOWN:            # bumpers move the caret
            self.caret = max(0, self.caret - 1)
        elif a == R.CH_UP:
            self.caret = min(len(self.value), self.caret + 1)
        elif a in R.DIGITS:
            self.insert(a[-1])
        return True                     # nothing typed here reaches the screens below
