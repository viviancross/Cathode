"""On Demand: browse the Plex library and My Recordings.

A stack of list levels (libraries -> genres -> titles -> seasons ...). Each
level remembers how it was loaded, so it can re-sort or reload. My
Recordings works with no network: it's on screen before the server is asked
anything, and stays when the server can't be reached.
"""

import time

from .. import remote as R
from ..app import Screen
from ..ondemand import SORTS, sort_label

LIBRARIES = "libraries"
RECORDINGS = "recordings"


def _row(t, title, **kw):
    return dict(type=t, title=title, meta="", playable=False, **kw)


class OnDemandScreen(Screen):
    name = "ondemand"
    opaque = True

    def __init__(self, app, start: str = LIBRARIES):
        super().__init__(app)
        self.od = app.ondemand
        self.stack = []
        self.status = ""
        self.mode = "browse"          # browse | auth
        self.side = None              # the button beside the list RIGHT moved to (skins that draw some)
        self.auth_code = self.auth_link = ""
        self._pin_id = None
        self._poll = None
        self.then = None              # the first-run setup's next step, once Plex is linked and answers
        self.od.listeners.append(self._recordings_changed)
        if start == RECORDINGS:
            self.open_recordings(root=True)
        elif self.od.signed_in:
            if self.od.downloads.items():
                self.show_libraries([self._recordings_row()], "CONNECTING...")
            else:
                self.status = "CONNECTING..."
            self.connect()
        else:
            self.begin_auth()

    def video_box(self):
        return self.app.skin.page_video_box(self)

    # ── Levels ────────────────────────────────────────────────────────────

    @property
    def level(self):
        return self.stack[-1] if self.stack else None

    @property
    def rows(self):
        return self.level["rows"] if self.level else []

    @property
    def sel(self) -> int:
        return self.level["sel"] if self.level else 0

    @sel.setter
    def sel(self, i):
        if self.level:
            n = len(self.rows)
            self.level["sel"] = max(0, min(i, n - 1)) if n else 0

    @property
    def view(self) -> str:
        """The poster wall only for levels of titles; menus of places to go
        (the library list, genres) read better as a list either way."""
        skin = self.app.skin
        if self.app.config.ppv_view != "wall" or not skin.poster_wall:
            return "list"
        if not skin.wall_episodes and all(r.get("type") in ("episode", "sort") for r in self.rows):
            return "list"
        titled = any(r.get("playable") or r.get("type") in ("show", "season", "movie")
                     for r in self.rows)
        return "wall" if titled else "list"

    @property
    def wall_offset(self) -> int:
        """1 when the level starts with its Sort row, which the wall shows as a
        bar above the posters rather than as a poster."""
        return 1 if self.rows and self.rows[0].get("type") == "sort" else 0

    def current(self):
        rows = self.rows
        return rows[self.sel] if 0 <= self.sel < len(rows) else None

    def crumb(self) -> str:
        return " / ".join(l["title"] for l in self.stack[:-1]) or "On Demand"

    def push(self, title, rows, loader=None, sort="", volatile=False, sortable=True, key=""):
        # Sortable lists carry a "Sort by" row so re-ordering needs no menu.
        if loader and sortable and rows and rows[0].get("type") != "sort":
            rows = [_row("sort", f"Sort by: {sort_label(sort)}")] + rows
        sel = 1 if rows and rows[0].get("type") == "sort" else 0
        self.stack.append(dict(title=title, rows=rows, sel=sel, loader=loader, sort=sort,
                               volatile=volatile, sortable=sortable, key=key))
        self.status = ""
        self.app.invalidate()

    def back(self):
        if len(self.stack) <= 1:
            self.leave()
            return
        self.stack.pop()
        self.show_top()

    def leave(self):
        self.app.cancel(self._poll)
        if self._recordings_changed in self.od.listeners:
            self.od.listeners.remove(self._recordings_changed)
        self.app.pop(self)
        self.app.live.resume()          # retunes if On Demand had the picture

    def show_top(self):
        """Back onto a level. Volatile ones (watchlist, continue watching,
        search) reload, but keep their rows if the reload fails."""
        lvl = self.level
        if not (lvl and lvl.get("volatile") and lvl.get("loader")):
            self.app.invalidate()
            return
        self.status = "LOADING..."

        def done(rows):
            if self.level is lvl:
                self.stack.pop()
                self.push(lvl["title"], rows, lvl["loader"], lvl["sort"], True,
                          lvl["sortable"], lvl["key"])

        def fail(_):
            self.status = ""
        self.od.run(lambda: lvl["loader"](lvl["sort"]), done, fail)

    def error(self, msg):
        self.status = msg               # a sentence; each skin fits it to its line
        self.app.invalidate()

    def open(self, loader, title, sort=None, volatile=False, sortable=True, key=""):
        """Load a list off the UI thread. `key` names it in config.plex_sorts,
        so each library reopens with the sort it was left on."""
        if sort is None:
            sort = self.app.config.plex_sorts.get(key, "") if key else ""
        self.status = "LOADING..."
        self.app.invalidate()
        self.od.run(lambda: loader(sort),
                    lambda rows: self.push(title, rows, loader, sort, volatile, sortable, key),
                    self.error)

    # ── Connecting and signing in ─────────────────────────────────────────

    @staticmethod
    def _recordings_row():
        return _row("downloads", "MY RECORDINGS")

    def show_libraries(self, rows, status=""):
        """Rows for the top level. Arrives twice on a cold start (this device,
        then the server); if the user went deeper meanwhile, the level under
        them is updated in place instead of yanking their screen."""
        if len(self.stack) > 1 and self.stack[0]["key"] == LIBRARIES:
            self.stack[0]["rows"] = rows
            return
        was = self.current().get("type") if self.current() and self.stack else ""
        self.stack = []
        self.push("ON DEMAND", rows, key=LIBRARIES)
        for i, r in enumerate(rows):
            if was and r.get("type") == was:
                self.sel = i
                break
        self.status = status

    def connect(self):
        cfg = self.app.config

        def work():
            c = self.od.client()
            c.discover_server(prefer=cfg.plex_server_id)
            sections = c.sections()
            try:
                servers = c.list_servers()
            except Exception:
                servers = None
            return sections, servers

        def done(result):
            sections, servers = result
            cfg.plex_sections = [{"key": s["key"], "title": s["title"]} for s in sections]
            if servers is not None:
                cfg.plex_servers = servers
            cfg.save()
            if self.then:                   # linked for the setup: back to it
                then, self.then = self.then, None
                self.app.pop(self)
                then()
                return
            hidden = set(cfg.plex_hidden_libraries)
            rows = [_row("search", "SEARCH..."), _row("ondeck", "CONTINUE WATCHING"),
                    _row("watchlist", "MY WATCHLIST")]
            if self.od.downloads.items():
                rows.append(self._recordings_row())
            rows += [_row("section", s["title"].upper(), rating_key=s["key"],
                          section_type=s["type"], agent=s.get("agent", ""))
                     for s in sections if s["key"] not in hidden]
            self.show_libraries(rows)

        def fail(msg):
            # No server is not the end when there are recordings: it narrows
            # On Demand to them.
            if self.od.downloads.items():
                self.show_libraries([self._recordings_row()], "OFFLINE")
            else:
                self.error(f"{msg} Press SELECT to try again, or check Settings > Servers > Plex.")
        self.od.run(work, done, fail)

    def begin_auth(self):
        self.mode, self.status = "auth", "GETTING A CODE..."

        def done(pin):
            self._pin_id = pin["id"]
            self.auth_code, self.auth_link = pin["code"], pin["link"]
            self.status = ""
            self._deadline = time.monotonic() + 300
            self._poll = self.app.after(2.0, self._check_pin)
        self.od.run(lambda: self.od.client().request_pin(), done,
                    lambda m: self.error("Couldn't start sign-in"))

    def _check_pin(self):
        if self not in self.app.screens or self.mode != "auth":
            return
        if time.monotonic() > self._deadline:
            self.error(f"The code expired. Press {self.app.skin.k('SELECT')} for a new one.")
            return

        def done(token):
            if not token:
                self._poll = self.app.after(2.0, self._check_pin)
                return
            cfg = self.app.config
            cfg.plex_token, cfg.plex_user_token = token, ""
            cfg.save()
            self.od.reset()
            self.mode = "browse"
            self.choose_user()
        self.od.run(lambda: self.od.client().poll_pin(self._pin_id), done,
                    lambda m: setattr(self, "_poll", self.app.after(2.0, self._check_pin)))

    def choose_user(self):
        """Plex Home users; straight to the library with only one."""
        self.status = "LOADING USERS..."

        def done(users):
            if len(users) <= 1:
                self.connect()
                return
            self.stack = []
            self.push("WHO'S WATCHING?", [
                _row("user", u["title"], rating_key=u["uuid"], protected=u["protected"],
                     meta="PIN" if u["protected"] else "") for u in users])
        self.od.run(lambda: self.od.client().home_users(), done, lambda m: self.connect())

    def pick_user(self, uuid, name, protected):
        from .menu import Keyboard

        def switch(pin=""):
            self.status = "SWITCHING..."

            def done(token):
                cfg = self.app.config
                if not token and protected:
                    self.app.toast("Wrong PIN - try again")
                    self.status = ""
                    return
                cfg.plex_user_token, cfg.plex_user_id, cfg.plex_user_name = \
                    (token, uuid, name) if token else ("", "", "")
                cfg.save()
                self.od.reset()
                self.stack = []
                self.connect()
            self.od.run(lambda: self.od.client().switch_user(uuid, pin), done,
                        lambda m: done(""))
        if protected:
            self.app.push(Keyboard(self.app, f"PIN for {name}",
                                   lambda pin: pin and switch(pin)))
        else:
            switch()

    # ── My Recordings ─────────────────────────────────────────────────────

    def open_recordings(self, root=False):
        rows = self.od.downloads.items()
        if not rows:
            self.app.toast("Nothing recorded yet. Choose Record on a title's info page.")
            if root:
                self.app.after(0, self.leave)
            return
        if root:
            self.stack = []
        self.push("MY RECORDINGS", rows, sortable=False, key=RECORDINGS)

    def _recordings_changed(self):
        lvl = self.level
        if lvl and lvl["key"] == RECORDINGS:
            rows = self.od.downloads.items()
            if not rows:
                self.back()
                return
            lvl["rows"] = rows
            self.sel = self.sel

    # ── Selecting ─────────────────────────────────────────────────────────

    def select(self):
        if self.mode == "auth":
            if self.status:
                self.begin_auth()
            return
        row = self.current()
        if not row:
            if self.status and self.status not in ("LOADING...", "CONNECTING..."):
                self.status = "CONNECTING..."   # the error's own "try again"
                self.app.invalidate()
                self.connect()
            return
        t, title, rk = row.get("type"), row.get("title", ""), row.get("rating_key")
        c = self.od.client
        if t == "user":
            self.pick_user(rk, title, row.get("protected", False))
        elif t == "watchlist":
            self.open(lambda s: c().watchlist(sort=s), "MY WATCHLIST", volatile=True, key="watchlist")
        elif t == "ondeck":
            self.open(lambda s: c().on_deck(), "CONTINUE WATCHING", volatile=True, sortable=False)
        elif t == "search":
            self._search()
        elif t == "downloads":
            self.open_recordings()
        elif t == "download":
            state = row.get("state")
            if state == "done":
                self.show_info(row)
            elif state in ("paused", "error"):
                self.od.dvr_start(rk, title)
            else:
                self.app.toast("Already recording")
        elif t == "sort":
            self.sort_menu()
        elif row.get("watchlist"):
            self._watchlist_item(row)
        elif row.get("playable") or t == "show":
            self.show_info(row)
        elif t == "section":
            if c().is_other_videos({"agent": row.get("agent", "")}):
                self.push(title, [_row("allvideos", "ALL VIDEOS", rating_key=rk),
                                  _row("folderview", "BY FOLDER", rating_key=rk)])
            elif row.get("section_type") in ("movie", "show"):
                self._categories(rk, title, row["section_type"])
            else:
                self.open(lambda s, k=rk: c().section_filter(k, sort=s), title, key=f"sec:{rk}")
        elif t in ("all", "allvideos"):
            self.open(lambda s, k=rk: c().section_filter(k, sort=s), title, key=f"sec:{rk}")
        elif t == "genre":
            g = row.get("genre_id")
            self.open(lambda s, k=rk, g=g: c().section_filter(k, genre_id=g, sort=s), title,
                      key=f"sec:{rk}")
        elif t == "folderview":
            self._folder(f"/library/sections/{rk}/folder", "FOLDERS", rk)
        elif t == "folder":
            self._folder(row.get("folder"), title, row.get("section", ""))
        else:
            self.open(lambda s, k=rk: c().children(k, sort=s), title)

    def _search(self):
        from .menu import Keyboard

        def got(q):
            if q and q.strip():
                self.open(lambda s, q=q: self.od.client().search(q), f"SEARCH: {q.upper()}",
                          volatile=True, sortable=False)
        self.app.push(Keyboard(self.app, "Search On Demand", got))

    def _categories(self, rk, title, stype):
        self.status = "LOADING..."

        def work():
            try:
                return self.od.client().genres(rk)
            except Exception:
                return []

        def done(genres):
            rows = [_row("all", "ALL MOVIES" if stype == "movie" else "ALL SHOWS", rating_key=rk)]
            rows += [_row("genre", g["title"].upper(), rating_key=rk, genre_id=g["id"]) for g in genres]
            self.push(title, rows)
        self.od.run(work, done)

    def _folder(self, path, title, section=""):
        self.status = "LOADING..."
        self.od.run(lambda: self.od.client().folder_items(path, section),
                    lambda rows: self.push(title, rows), self.error)

    def _watchlist_item(self, row):
        self.status = "FINDING..."

        def done(rk):
            if not rk:
                self.error("Not in your library")
            elif row.get("type") in ("movie", "episode", "show"):
                self.status = ""
                self.show_info({"rating_key": rk})
            else:
                self.open(lambda s, k=rk: self.od.client().children(k, sort=s), row.get("title", ""))
        self.od.run(lambda: self.od.client().find_on_server(row.get("guid")), done, self.error)

    def show_info(self, row):
        from .iteminfo import ItemInfo
        rk = row.get("rating_key")
        if row.get("type") == "download":
            # From disk: the one page that must work offline mustn't ask the server.
            detail = self.od.downloads.detail(rk)
            if detail is not None:
                self.app.push(ItemInfo(self.app, detail, "download"))
                return
        self.status = "LOADING..."

        def work():
            c = self.od.client()
            detail = c.item_detail(rk)
            kind = detail.get("type", "")
            kind = kind if kind in ("show", "episode") else "default"
            on_list = False
            if kind != "episode" and detail.get("guid"):
                gid = detail["guid"].rstrip("/").split("/")[-1]
                try:
                    on_list = any(w.get("guid") == detail["guid"]
                                  or w.get("guid", "").rstrip("/").split("/")[-1] == gid
                                  for w in c.watchlist())
                except Exception:
                    pass
            return detail, kind, on_list

        def done(result):
            self.status = ""
            detail, kind, on_list = result
            self.app.push(ItemInfo(self.app, detail, kind, on_list))
        self.od.run(work, done, self.error)

    # ── Sorting ───────────────────────────────────────────────────────────

    def sort_menu(self):
        from .menu import Item, Menu
        lvl = self.level
        if not (lvl and lvl.get("loader")):
            return

        def pick(val):
            if lvl.get("key"):
                self.app.config.plex_sorts[lvl["key"]] = val
                self.app.config.save()
            self.stack.pop()
            self.open(lvl["loader"], lvl["title"], sort=val, volatile=lvl["volatile"],
                      sortable=lvl["sortable"], key=lvl["key"])
        self.app.push(Menu(self.app, "SORT BY", [
            Item(("> " if v == lvl["sort"] else "  ") + n, (lambda v=v: pick(v)), close=True)
            for n, v in SORTS]))

    def _wall_move(self, a, cols):
        """Grid moves; the Sort bar above the posters is reached by UP from
        the top row and left with DOWN or RIGHT."""
        off, n = self.wall_offset, len(self.rows)
        if self.sel < off:
            if a in (R.DOWN, R.RIGHT):
                self.sel = off
            return
        i = self.sel - off
        if a == R.UP:
            self.sel = self.sel - cols if i >= cols else 0 if off else self.sel
        elif a == R.DOWN:
            self.sel = min(n - 1, self.sel + cols)
        elif a == R.LEFT:
            self.sel = max(off, self.sel - 1)
        else:
            self.sel = min(n - 1, self.sel + 1)

    # ── Remote ────────────────────────────────────────────────────────────

    def _side_keys(self, a) -> bool:
        """The buttons beside the list: RIGHT from the list (or the wall's
        right edge) moves into them, UP/DOWN along, SELECT presses, LEFT or
        BACK goes back to the list."""
        side = self.app.skin.od_side(self) if self.mode == "browse" else []
        if self.side is not None and not side:
            self.side = None
        if self.side is None:
            at_edge = self.view != "wall" or (self.sel - self.wall_offset) % self.app.skin.ondemand_cols(self) == \
                self.app.skin.ondemand_cols(self) - 1 or self.sel >= len(self.rows) - 1
            if a == R.RIGHT and side and at_edge:
                self.side = 0
                self.app.invalidate()
                return True
            return False
        if a in (R.UP, R.DOWN):
            self.side = (self.side + (1 if a == R.DOWN else -1)) % len(side)
        elif a == R.SELECT:
            fn, self.side = side[self.side][1], None
            fn()
        elif a in (R.LEFT, R.BACK):
            self.side = None
        else:
            return False
        self.app.invalidate()
        return True

    def handle(self, a: str) -> bool:
        if self._side_keys(a):
            return True
        n = len(self.rows)
        step = self.app.skin.ondemand_cols(self) if self.view == "wall" else 1
        if a in (R.EXIT, R.GUIDE):
            self.leave()
            if a == R.GUIDE:
                return False                 # and let live TV open the guide
        elif a == R.BACK:
            self.back()
        elif a == R.SELECT:
            self.select()
        elif a == R.MENU:
            from ..menus import ondemand_menu
            ondemand_menu(self.app, self)
        elif a == R.LIST:
            self.open_recordings()
        elif not n:
            return a not in _PASS_THROUGH
        elif self.view == "wall" and a in (R.UP, R.DOWN, R.LEFT, R.RIGHT):
            self._wall_move(a, step)
        elif a == R.UP:
            self.sel -= 1
        elif a == R.DOWN:
            self.sel += 1
        elif a == R.LEFT:
            self.back()
        elif a == R.RIGHT:
            self.select()
        elif a in (R.PAGE_UP, R.CH_UP):
            self.sel -= self.app.skin.ondemand_page(self)
        elif a in (R.PAGE_DOWN, R.CH_DOWN):
            self.sel += self.app.skin.ondemand_page(self)
        else:
            return a not in _PASS_THROUGH
        return True


_PASS_THROUGH = {R.VOL_UP, R.VOL_DOWN, R.MUTE, R.FULLSCREEN, R.QUIT}
