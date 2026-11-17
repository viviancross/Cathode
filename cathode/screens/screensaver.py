"""The screensaver: a bouncing wordmark after a long idle on a page that never
changes (the guide, a menu). Never over live TV, which is its own motion.
Any button wakes it and is used up doing so."""

import time

from ..app import Screen


class Screensaver(Screen):
    name = "screensaver"
    opaque = True
    SPEED = (110.0, 80.0)       # canvas pixels per second

    def __init__(self, app):
        super().__init__(app)
        self.start = time.monotonic()

    def position(self, box_w, box_h, area_w, area_h):
        """Top-left of a box bouncing off the edges of the area."""
        t = time.monotonic() - self.start

        def bounce(span, v):
            if span <= 0:
                return 0
            d = (t * v) % (2 * span)
            return d if d <= span else 2 * span - d
        return int(bounce(area_w - box_w, self.SPEED[0])), int(bounce(area_h - box_h, self.SPEED[1]))

    def animating(self) -> bool:
        return True

    def handle(self, a: str) -> bool:
        self.app.pop(self)
        live = getattr(self.app, "live", None)
        if live is not None and hasattr(live, "wake"):
            live.wake()
        return True
