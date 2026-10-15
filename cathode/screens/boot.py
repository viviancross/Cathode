"""The boot sequence: what a satellite box shows while it finds its signal
and fetches its guide. The stages follow the real loading; any button skips
to live TV (loading carries on underneath)."""

import time

from ..app import Screen


class Boot(Screen):
    name = "boot"
    opaque = True
    MIN = 1.2                   # seconds: never just a flash
    GUIDE_WAIT = 8.0            # don't hold the picture hostage to a slow guide

    def __init__(self, app):
        super().__init__(app)
        self.start = time.monotonic()
        self._channels_at = None
        self._timer = app.after(0.25, self._check)

    def stage(self) -> str:
        """starting | signal | guide | done"""
        now = time.monotonic()
        if now - self.start < 0.6:
            return "starting"
        if not self.app.channels:
            # Still loading, or failed: a failure's message is for live TV to show.
            return "signal" if self.app.live.message.startswith("Loading") else "done"
        if self._channels_at is None:
            self._channels_at = now
        # The guide is due while its load runs; a load that failed is said
        # (a notice) and doesn't hold the picture.
        guide_due = bool(self.app.config.epg_url) and not self.app.epg.channel_ids and             getattr(self.app, "guide_progress", -1) is not None
        if guide_due and now - self._channels_at < self.GUIDE_WAIT:
            return "guide"
        return "done"

    def _check(self):
        if self not in self.app.screens:
            return
        if self.stage() == "done" and time.monotonic() - self.start >= self.MIN:
            self.app.pop(self)
        else:
            self._timer = self.app.after(0.25, self._check)

    def animating(self) -> bool:
        return True                     # the progress sweep

    def handle(self, a: str) -> bool:
        self.app.cancel(self._timer)
        self.app.pop(self)              # any button: straight to TV
        return True
