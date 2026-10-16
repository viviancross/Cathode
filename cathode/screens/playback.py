"""On Demand playback: the picture full screen, with a transport bar like a
DVR's. Remote buttons act directly (no focus-hopping): OK/PAUSE pause, LEFT
and RIGHT step back and forward, CH up/down move through the queue, OK skips
an intro or the credits while that marker is up."""

import time

from .. import remote as R
from ..app import Screen

REPORT_EVERY = 10.0         # seconds between position reports to the server


class Playback(Screen):
    name = "playback"
    opaque = True               # nothing under it is drawn; its own canvas is clear

    def __init__(self, app, rk, info, title="", subtitle=""):
        super().__init__(app)
        self.od = app.ondemand
        app.live.suspend()
        self._tick = None
        self.load(rk, info, title, subtitle)

    def load(self, rk, info, title="", subtitle=""):
        """Start an item (the first, or the next from the queue)."""
        self.rk = rk
        self.title = info.get("title") or title
        self.subtitle = info.get("subtitle") or subtitle
        self.time_base = float(info.get("time_base") or 0)
        self.markers = info.get("markers") or []
        self.subs = list(info.get("subs") or [])      # files beside the video
        self._subs_added = False
        self.pos = float(info.get("offset") or 0)
        self.dur = float(info.get("duration") or 0)     # mpv's is the fallback
        self.skip_label, self.skip_to = "", 0.0
        self._last_report = time.monotonic()
        cfg = self.app.config
        v = self.app.video
        v.play(info["url"], headers=info.get("headers"), start=info.get("offset", 0),
               sub_delay=-self.time_base)
        v.sub_style(font=cfg.sub_font or None, size=cfg.sub_size, color=cfg.sub_color,
                    back=cfg.sub_back)
        self.flash = ("PLAY >", time.monotonic() + 1.5)
        self.show_bar()
        self.app.cancel(self._tick)
        self._tick = self.app.after(0.5, self._monitor)

    def video_box(self):
        return "full"

    # ── Subtitle files ────────────────────────────────────────────────────

    def sub_url(self, s: dict) -> str:
        """A subtitle file's address; with auto-sync on and the server able
        to (Plex Pass, the title's voice analysed), the server shifts it to
        the dialogue as it hands it over."""
        url = s["url"]
        sync = self.app.config.sub_auto_sync and s.get("sync") and url.startswith("http")
        print(f"[ondemand] subtitle {s.get('title') or '?'}: auto-sync "
              f"{'requested' if sync else 'off' if s.get('sync') else 'not offered by the server'}")
        return url + ("&" if "?" in url else "?") + "autoAdjustSubtitle=1" if sync else url

    def reload_subs(self):
        """Hand mpv the subtitle files again (auto-sync was switched),
        keeping the one that was showing."""
        v = self.app.video
        files = [t for t in v.tracks("sub") if t["external"]]
        shown = next((k for k, t in enumerate(files) if t["selected"]), None)
        for t in files:
            v.remove_subtitle(t["id"])
        for k, s in enumerate(self.subs):
            v.add_subtitle(self.sub_url(s), s["title"], s["lang"], select=k == shown)

    # ── Position ──────────────────────────────────────────────────────────

    def _monitor(self):
        if self not in self.app.screens:
            return
        v = self.app.video
        raw = v.prop("time-pos")
        if raw is not None:
            # mpv's clock starts at 0 even when a transcode began mid-file.
            self.pos = float(raw) + self.time_base
        if not self.dur:
            d = v.prop("duration")
            if d:
                self.dur = float(d) + self.time_base
        label, to = "", 0.0
        for m in self.markers:
            if m["start"] <= self.pos < m["end"]:
                label, to = ("SKIP INTRO" if m["type"] == "intro" else "SKIP CREDITS"), m["end"]
                break
        if label != self.skip_label:
            self.skip_label, self.skip_to = label, to
            self.app.invalidate()
        now = time.monotonic()
        if now - self._last_report >= REPORT_EVERY:
            self._last_report = now
            self.od.report(self.rk, self.pos, self.dur, "paused" if v.paused else "playing")
        if self.bar_visible() or self.skip_label:
            self.app.invalidate()
        self._tick = self.app.after(0.5, self._monitor)

    def bar_visible(self) -> bool:
        return self.app.video.paused or time.monotonic() < self.bar_until

    def show_bar(self, seconds=5.0):
        self.bar_until = time.monotonic() + seconds
        self.app.invalidate()

    # ── Ending ────────────────────────────────────────────────────────────

    def _resume_point(self) -> int:
        return 0 if self.dur and self.pos > self.dur - 30 else int(self.pos)

    def stop(self):
        """Stop and go back to the item's page, keeping the resume point."""
        if self.pos > 1:
            self.od.report(self.rk, self.pos, self.dur, "stopped")
        self._close(self._resume_point())

    def finished(self):
        """The item ran out: mark it watched, then the next in the queue, or
        back to its page."""
        self.od.report(self.rk, self.pos, self.dur, "stopped", finished=True)
        nxt = self.od.queue.step(1)
        if nxt is not None:
            self.od.remember_offset(self.rk, 0)
            self.od.play_queue_at(nxt)
            return
        self._close(0)

    def _close(self, offset: int):
        self.app.cancel(self._tick)
        self.od.remember_offset(self.rk, offset)
        self.app.video.stop()
        self.app.pop(self)
        from .iteminfo import ItemInfo
        info = self.app.find(ItemInfo)
        if info and str(info.detail.get("rating_key")) == str(self.rk):
            info.detail["offset"] = offset

    def skip(self, d: int):
        """Next/previous in the queue; off its ends, the next/previous chapter."""
        i = self.od.queue.step(d) if self.od.queue.items else None
        if i is not None:
            self.od.report(self.rk, self.pos, self.dur, "stopped")
            self.od.play_queue_at(i)
        else:
            self.app.video.chapter(d)
            self.show_bar()

    def on_video(self, kind, **data):
        if kind == "video_started" and not self._subs_added:
            self._subs_added = True                 # (it fires again after every seek)
            for s in self.subs:
                self.app.video.add_subtitle(self.sub_url(s), s["title"], s["lang"])
        if kind == "video_ended":
            if data.get("reason") == "eof":
                self.finished()
            else:
                self.app.toast("Playback failed")
                self._close(int(self.pos))

    # ── Remote ────────────────────────────────────────────────────────────

    def seek(self, s: float):
        self.app.video.seek(s)
        self.show_bar()

    def seek_to(self, frac: float):
        """Clicked on the timeline."""
        if self.dur:
            self.app.video.seek(frac * self.dur - self.time_base, "absolute")
            self.show_bar()

    def toggle_pause(self):
        v = self.app.video
        v.paused = not v.paused
        if not v.paused:
            self.flash = ("PLAY >", time.monotonic() + 1.5)
        self.show_bar()

    def transport(self):
        """The on-screen buttons, for the mouse (the remote acts on its own
        keys): (kind, label, action), left to right."""
        paused = self.app.video.paused
        return [("prev", "|<<", lambda: self.skip(-1)), ("back", "<< 10", lambda: self.seek(-10)),
                ("play", "PLAY", self.toggle_pause) if paused else ("pause", "PAUSE", self.toggle_pause),
                ("stop", "STOP", self.stop), ("fwd", "30 >>", lambda: self.seek(30)),
                ("next", ">>|", lambda: self.skip(1))]

    def handle(self, a: str) -> bool:
        if a == R.SELECT:
            if self.skip_label:
                self.app.video.seek(self.skip_to - self.time_base, "absolute")
                self.skip_label = ""
                self.show_bar()
            else:
                self.toggle_pause()
        elif a in (R.PAUSE, R.PLAY):
            self.toggle_pause()
        elif a in (R.LEFT, R.REW):
            self.seek(-10)
        elif a in (R.RIGHT, R.FF):
            self.seek(30 if a == R.FF else 10)
        elif a == R.REPLAY:
            self.seek(-7)
        elif a == R.SKIP:
            if self.skip_label:
                self.handle(R.SELECT)
            else:
                self.skip(1)
        elif a in (R.CH_UP, R.PAGE_UP):
            self.skip(1)
        elif a in (R.CH_DOWN, R.PAGE_DOWN):
            self.skip(-1)
        elif a in (R.UP, R.DOWN, R.INFO):
            self.show_bar()
        elif a in (R.STOP, R.BACK, R.EXIT):
            self.stop()
        elif a == R.MENU:
            from ..menus import playback_menu
            playback_menu(self.app, self)
        elif a in R.DIGITS or a in (R.GUIDE, R.PREV, R.BROWSE, R.FAV, R.THEMES):
            return True                     # no channels to change during a movie
        else:
            return False                    # volume and the rest: live TV handles them
        return True
