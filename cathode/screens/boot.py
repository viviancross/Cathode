"""The boot sequence: what a satellite box shows while it finds its signal
and fetches its guide. Each skin names its box's scenes (the HR20's blue
"hello" screens and Step 1 / Step 2; the ViP's "Starting up..." and its
Acquiring Signal dialog; the Dish SD box's ATTENTION 015) and how long each
holds; the real loading gates the last one, and any button skips to live
TV (loading carries on underneath). A box that had no boot screen (the
DSS: standby, instant on) names no scenes and never shows this."""

import time

from ..app import Screen

# The scenes every skin shares, before its own: the skin's list is a
# sequence of (name, min_seconds). The loading gate applies to the LAST
# scene: it holds until the channels (and, for a while, the guide) are in.
DEFAULT_SCENES = [("starting", 0.6), ("signal", 1.0), ("guide", 0.0)]


class Boot(Screen):
    name = "boot"
    opaque = True
    MIN = 1.2                   # seconds: never just a flash
    GUIDE_WAIT = 8.0            # don't hold the picture hostage to a slow guide

    def __init__(self, app):
        super().__init__(app)
        self.start = time.monotonic()
        self._channels_at = None
        self.scenes = list(getattr(getattr(app, "skin", None), "boot_scenes", None) or DEFAULT_SCENES)
        self._timer = app.after(0.25, self._check)

    # ── Where we are ──────────────────────────────────────────────────────

    def elapsed(self) -> float:
        return time.monotonic() - self.start

    def loaded(self) -> bool:
        """The real loading the last scene waits on: channels in, and the
        guide in or given up on."""
        app = self.app
        now = time.monotonic()
        if not app.channels:
            # Still loading, or failed: a failure's message is for live TV to show.
            return not app.live.message.startswith("Loading")
        if self._channels_at is None:
            self._channels_at = now
        guide_due = bool(app.config.epg_url) and not app.epg.channel_ids and \
            getattr(app, "guide_progress", -1) is not None
        return not (guide_due and now - self._channels_at < self.GUIDE_WAIT)

    def scene(self) -> str:
        """The scene to draw now: each holds its minimum, the last holds
        until loaded; 'done' after that."""
        t = self.elapsed()
        for i, (name, hold) in enumerate(self.scenes):
            last = i == len(self.scenes) - 1
            if t < hold or (last and not self.loaded()):
                return name
            t -= hold
        return "done"

    def scene_age(self) -> float:
        """Seconds into the current scene."""
        t = self.elapsed()
        for i, (name, hold) in enumerate(self.scenes):
            last = i == len(self.scenes) - 1
            if t < hold or (last and not self.loaded()):
                return t
            t -= hold
        return t

    def stage(self) -> str:
        """The shared stages the older skins draw by: starting | signal |
        guide | done (the HR20 and ViP scenes map onto them)."""
        s = self.scene()
        return {"hello": "starting", "almost": "starting", "step1": "signal", "step2": "signal",
                "acquiring": "guide", "logo": "starting", "attention": "signal"}.get(s, s)

    def _check(self):
        if self not in self.app.screens:
            return
        if self.scene() == "done" and self.elapsed() >= self.MIN:
            self.app.pop(self)
        else:
            self._timer = self.app.after(0.25, self._check)

    # Over the picture, or hiding it: a skin names the scenes its box drew
    # over live video (the HR20's Acquiring Guide Data box).
    def video_box(self):
        over = getattr(getattr(self.app, "skin", None), "boot_over_video", ())
        return "full" if self.scene() in over else "hidden"

    def animating(self) -> bool:
        return True                     # the progress sweep

    def handle(self, a: str) -> bool:
        self.app.cancel(self._timer)
        self.app.pop(self)              # any button: straight to TV
        return True
