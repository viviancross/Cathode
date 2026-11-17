"""An On Demand item's info page: poster, summary, and what you can do with
it. The buttons depend on the kind of item."""

from .. import remote as R
from ..app import Screen

BUTTONS = {
    "show": ["playall", "seasons", "shuffle", "queue", "watchlist", "back"],
    "episode": ["play", "dvr", "queue", "back"],
    "default": ["play", "dvr", "queue", "watchlist", "back"],
    "download": ["play", "dvr", "back"],       # what works offline, and nothing else
}
LABELS = {"play": "PLAY", "playall": "PLAY ALL", "seasons": "SEASONS", "shuffle": "SHUFFLE",
          "queue": "+ QUEUE", "back": "BACK", "trailer": "TRAILER"}
PRIMARY = {"play", "playall"}


def hms(t) -> str:
    t = int(t or 0)
    h, m, s = t // 3600, t // 60 % 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class ItemInfo(Screen):
    name = "iteminfo"
    opaque = True

    def __init__(self, app, detail: dict, kind: str = "default", on_watchlist: bool = False):
        super().__init__(app)
        self.od = app.ondemand
        self.detail, self.kind = detail, kind
        self.on_watchlist = on_watchlist
        self.focus = 0
        self.od.listeners.append(self.app.invalidate)
        self._theme()

    def _theme(self):
        """A show's theme song, quietly, while its page is up (as Plex plays
        it): fetched once into the cache, played through pygame's mixer."""
        path = self.detail.get("theme")
        if not path or not getattr(self.app.config, "theme_music", False) or self.kind == "download":
            return
        import hashlib
        import os
        from .. import paths
        f = os.path.join(paths.cache_dir(), "themes", hashlib.sha1(path.encode()).hexdigest()[:16] + ".mp3")

        def work():
            if not os.path.exists(f):
                os.makedirs(os.path.dirname(f), exist_ok=True)
                data = self.od.client().raw(path)
                with open(f, "wb") as fh:
                    fh.write(data)
            return f

        def play(fn):
            if self not in self.app.screens:
                return
            try:
                import pygame
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
                pygame.mixer.music.load(fn)
                pygame.mixer.music.set_volume(0.35 * self.app.video.volume / 100)
                pygame.mixer.music.play()
                self._playing = True
            except Exception as e:
                print(f"[ondemand] theme song: {e!r}")
        self.od.run(work, play, lambda _e: None)

    def _theme_off(self):
        if getattr(self, "_playing", False):
            self._playing = False
            try:
                import pygame
                pygame.mixer.music.fadeout(600)
            except Exception:
                pass

    def video_box(self):
        return self.app.skin.page_video_box(self)

    @property
    def rk(self) -> str:
        return str(self.detail.get("rating_key") or "")

    def buttons(self):
        bs = list(BUTTONS.get(self.kind, BUTTONS["default"]))
        if self.detail.get("trailer") and self.kind != "download":
            bs.insert(len(bs) - 1, "trailer")
        return bs

    def label(self, b: str) -> str:
        if b == "play" and self.kind != "download":
            return "WATCH"              # an offer is free to watch; a recording plays
        if b == "dvr":
            return self.od.dvr_label(self.rk)
        if b == "watchlist":
            return "- WATCHLIST" if self.on_watchlist else "+ WATCHLIST"
        return LABELS.get(b, b.upper())

    def close(self):
        self._theme_off()
        if self.app.invalidate in self.od.listeners:
            self.od.listeners.remove(self.app.invalidate)
        self.app.pop(self)
        from .ondemand import OnDemandScreen
        browse = self.app.find(OnDemandScreen)
        if browse:
            browse.show_top()          # e.g. a watchlist reload drops what was removed

    def press(self, b: str):
        from .menu import Item, Menu
        d = self.detail
        if b != "back":
            self._theme_off()
        if b == "trailer":
            self.od.play_detail({"rating_key": d["trailer"], "title": f"{d.get('title', '')}: Trailer",
                                 "type": "clip"}, False)
        elif b == "play":
            off = d.get("offset", 0)
            if off > 5:
                self.app.push(Menu(self.app, "RESUME?", [
                    Item(f"Resume from {hms(off)}", lambda: self.od.play_detail(d, True), close=True),
                    Item("Start from the beginning", lambda: self.od.play_detail(d, False), close=True),
                ]))
            else:
                self.od.play_detail(d, False)
        elif b in ("playall", "shuffle"):
            self.od.play_all(self.rk, shuffle=b == "shuffle")
        elif b == "seasons":
            from .ondemand import OnDemandScreen
            browse = self.app.find(OnDemandScreen)
            self.close()
            if browse:
                browse.open(lambda s, k=self.rk: self.od.client().children(k, sort=s),
                            d.get("title", ""))
        elif b == "queue":
            self.od.enqueue(d)
        elif b == "watchlist":
            add = not self.on_watchlist

            def done(ok):
                if ok:
                    self.on_watchlist = add
            self.od.run(lambda: self.od.client().watchlist_set(d.get("guid", ""), add), done)
        elif b == "dvr":
            self._dvr()
        elif b == "back":
            self.close()

    def _dvr(self):
        from .menu import Item, Menu
        st = self.od.downloads.state(self.rk)

        def delete():
            self.od.downloads.remove(self.rk)
            self.app.toast("Deleted from My Recordings")
            if self.kind == "download":
                self.close()           # the thing this page was about is gone
        if st == "done":
            self.app.push(Menu(self.app, "RECORDED", [
                Item("Keep it", lambda: None, close=True),
                Item("Delete it", delete, close=True)]))
        elif st in ("queued", "downloading"):
            self.app.push(Menu(self.app, f"RECORDING {self.od.downloads.percent(self.rk)}%", [
                Item("Keep recording", lambda: None, close=True),
                Item("Stop", lambda: self.od.downloads.cancel(self.rk), close=True),
                Item("Delete it", delete, close=True)]))
        else:
            self.od.dvr_start(self.rk, self.detail.get("title", ""))

    def handle(self, a: str) -> bool:
        bs = self.buttons()
        if a in (R.LEFT, R.UP):
            self.focus = (self.focus - 1) % len(bs)
        elif a in (R.RIGHT, R.DOWN):
            self.focus = (self.focus + 1) % len(bs)
        elif a == R.SELECT:
            self.press(bs[self.focus])
        elif a == R.BACK:
            self.close()
        elif a == R.EXIT:
            from .ondemand import OnDemandScreen
            self.close()
            browse = self.app.find(OnDemandScreen)
            if browse:
                browse.leave()
        elif a in (R.PLAY, R.PAUSE):
            self.press("play" if "play" in bs else "playall")
        elif a == R.MENU:
            return False
        else:
            return a not in (R.VOL_UP, R.VOL_DOWN, R.MUTE, R.FULLSCREEN, R.QUIT)
        return True
