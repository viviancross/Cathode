"""'Press the key you want': grabs the next raw key or controller button for
remapping. Esc (or the controller's B... once remapped, whatever is BACK)
cancels via the key itself: Esc is never bindable."""

from typing import Callable, Optional

import pygame

from .. import remote as R
from ..app import Screen


class Capture(Screen):
    name = "capture"
    wants_raw = True

    def __init__(self, app, prompt: str, kind: str, on_done: Callable[[Optional[str]], None]):
        super().__init__(app)
        self.prompt, self.kind, self.on_done = prompt, kind, on_done

    def raw(self, e) -> bool:
        """Raw events while open. True when used."""
        got = None
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self._finish(None)
                return True
            if self.kind == "key":
                got = pygame.key.name(e.key)
        elif e.type == pygame.CONTROLLERBUTTONDOWN and self.kind == "pad":
            got = R.pad_button_name(e.button)
        if got:
            self._finish(got)
            return True
        return e.type in (pygame.KEYDOWN, pygame.CONTROLLERBUTTONDOWN, pygame.TEXTINPUT)

    def _finish(self, value):
        self.app.pop(self)
        self.on_done(value)

    def handle(self, a: str) -> bool:
        return True
