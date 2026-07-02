"""Plex-Per-View controller — browse stack, info screen, playback (queue,
monitor, OSD controls), and the Plex settings menus. Mixed into App
(cathode.app); every method runs on the shared App instance and uses its
renderer / player / config state."""

from __future__ import annotations

import threading
import time

from . import plex
from .ui import theme
from .ui.menu import MenuItem
from .ui.renderer import UIState


class PlexMixin:
    def _confirm_leave_plex(self):
        items = [
            MenuItem("Keep Watching", action=lambda: None),
            MenuItem("Return to Browse", action=self._plex_stop),
        ]
        self.renderer.menu.open_with(items, title="LEAVE VIDEO?")
        self.renderer.mark_dirty()

    def _build_plex_menu(self):
        """The context menu shown in Plex-Per-View mode (browse or playback)."""
        items = [
            MenuItem("Mute", action=self._toggle_mute, hint="M",
                     checked=self.player.muted),
        ]
        if self.renderer.plex_playing:
            items.append(MenuItem("Audio & Subtitles", submenu=self._plex_av_submenu))
        items += [
            MenuItem("Live TV", submenu=self._playlists_submenu),
            MenuItem("Options", submenu=self._options_submenu),
            MenuItem("Main Menu", action=self._open_main_menu),
            MenuItem("Quit", action=self._quit_app, hint="Q"),
        ]
        return items

    def _plex_options_submenu(self):
        if not self.config.plex_token:
            return [MenuItem("(not signed in — open Plex-Per-View)", enabled=False)]
        user = self.config.plex_user_name or "Account"
        items = [
            MenuItem(f"Quality: {self.config.plex_quality}",
                     submenu=self._plex_quality_submenu),
            MenuItem("Libraries", submenu=self._plex_libraries_submenu),
        ]
        # Server picker only when more than one server is available.
        if len(self.config.plex_servers) > 1:
            items.append(MenuItem("Server", submenu=self._plex_servers_submenu))
        items += [
            MenuItem(f"User: {user}", action=self._plex_change_user),
            MenuItem("Unlink Plex Account", action=self._plex_unlink),
        ]
        return items

    def _plex_servers_submenu(self):
        servers = self.config.plex_servers
        if not servers:
            return [MenuItem("(open Plex-Per-View first)", enabled=False)]
        cur = self.config.plex_server_id
        return [MenuItem(s["title"] + ("" if s.get("owned") else "  (shared)"),
                         checked=(s["id"] == cur),
                         action=lambda i=s["id"]: self._plex_set_server(i),
                         close_after=False)
                for s in servers]

    def _plex_set_server(self, server_id):
        if server_id == self.config.plex_server_id:
            return
        self.config.plex_server_id = server_id
        self.config.plex_server = ""        # drop cached base URL; rediscover
        self.config.save()
        self._plex_reset()                  # rebuild client, then reconnect
        self.renderer.menu.replace_page(self._plex_servers_submenu())
        self.renderer.mark_dirty()
        # Re-enter the library from the chosen server (off the menu thread).
        self._plex_end()
        self._ppv_stack = []
        self.renderer.plexinfo.close()
        self.renderer.ppv.mode = "browse"
        self.renderer.ppv.rows = []
        self.renderer.ppv.show()
        self.renderer.ppv.set_status("CONNECTING...")
        self._ppv_return_menu = self.renderer.main_menu.open
        self.renderer.menu.close()
        self.renderer.main_menu.close()
        self._ppv_connect()

    def _plex_libraries_submenu(self):
        secs = self.config.plex_sections
        if not secs:
            return [MenuItem("(open Plex-Per-View first)", enabled=False)]
        hidden = set(self.config.plex_hidden_libraries)
        # A check means the library is shown; toggling hides/shows it.
        return [MenuItem(s["title"], checked=(s["key"] not in hidden),
                         action=lambda k=s["key"]: self._plex_toggle_library(k),
                         close_after=False)
                for s in secs]

    def _plex_toggle_library(self, key):
        hidden = list(self.config.plex_hidden_libraries)
        if key in hidden:
            hidden.remove(key)
        else:
            hidden.append(key)
        self.config.plex_hidden_libraries = hidden
        self.config.save()
        self.renderer.menu.replace_page(self._plex_libraries_submenu())
        self.renderer.mark_dirty()

    def _plex_quality_submenu(self):
        cur = self.config.plex_quality
        return [MenuItem(q, action=lambda x=q: self._plex_set_quality(x),
                         checked=(q == cur), close_after=False)
                for q in plex.QUALITY_OPTIONS]

    def _plex_set_quality(self, q):
        self.config.plex_quality = q
        self.config.save()
        self.renderer.menu.replace_page(self._plex_quality_submenu())
        self.renderer.mark_dirty()

    def _plex_change_user(self):
        r = self.renderer
        self._plex_end()
        r.plexinfo.close()
        self._ppv_return_menu = r.main_menu.open
        r.menu.close()
        r.main_menu.close()
        self._ppv_stack = []
        r.ppv.mode = "browse"
        r.ppv.rows = []
        r.ppv.show()
        r.mark_dirty()
        self._ppv_choose_user(force=True)

    def _plex_unlink(self):
        self._plex_end()
        self.config.plex_token = ""
        self.config.plex_user_token = ""
        self.config.plex_user_id = ""
        self.config.plex_user_name = ""
        self.config.save()
        self._plex_reset()      # forces the PIN sign-in again next time
        self.renderer.show_notification("Plex account unlinked", 3.0)
        self.renderer.mark_dirty()

    # ── Plex audio / subtitle settings ────────────────────────────────────

    SUB_SIZES = [("Small", 28), ("Medium", 38), ("Large", 52), ("Extra Large", 68)]
    SUB_COLORS = [("White", "#FFFFFFFF"), ("Yellow", "#FFFFFF00"),
                  ("Cyan", "#FF00FFFF"), ("Green", "#FF00FF00"),
                  ("Black", "#FF000000")]
    SUB_BACKS = [("None", ""), ("Shaded", "#96000000"), ("Black", "#FF000000")]

    def _plex_av_submenu(self):
        return [
            MenuItem("Audio Track", submenu=self._plex_audio_tracks_submenu),
            MenuItem("Subtitle Track", submenu=self._plex_sub_tracks_submenu),
            MenuItem("Subtitle Font", submenu=self._plex_sub_font_submenu),
            MenuItem("Subtitle Size", submenu=self._plex_sub_size_submenu),
            MenuItem("Subtitle Color", submenu=self._plex_sub_color_submenu),
            MenuItem("Subtitle Background", submenu=self._plex_sub_back_submenu),
        ]

    @staticmethod
    def _track_label(t) -> str:
        bits = [str(t["id"])]
        if t.get("lang"):
            bits.append(t["lang"])
        if t.get("title"):
            bits.append(t["title"])
        return ": ".join([bits[0], " ".join(bits[1:])]) if len(bits) > 1 else bits[0]

    def _plex_audio_tracks_submenu(self):
        tracks = self.player.get_tracks()["audio"]
        if not tracks:
            return [MenuItem("(no audio tracks)", enabled=False)]
        return [MenuItem(self._track_label(t), checked=t["selected"], close_after=False,
                         action=lambda i=t["id"]: self._plex_set_audio_track(i))
                for t in tracks]

    def _plex_set_audio_track(self, tid):
        self.player.set_audio_track(tid)
        self.renderer.menu.replace_page(self._plex_audio_tracks_submenu())
        self.renderer.mark_dirty()

    def _plex_sub_tracks_submenu(self):
        tracks = self.player.get_tracks()["sub"]
        none_sel = not any(t["selected"] for t in tracks)
        items = [MenuItem("Off", checked=none_sel, close_after=False,
                          action=lambda: self._plex_set_sub_track("no"))]
        for t in tracks:
            items.append(MenuItem(self._track_label(t), checked=t["selected"],
                         close_after=False,
                         action=lambda i=t["id"]: self._plex_set_sub_track(i)))
        return items

    def _plex_set_sub_track(self, tid):
        self.player.set_sub_track(tid)
        self.renderer.menu.replace_page(self._plex_sub_tracks_submenu())
        self.renderer.mark_dirty()

    def _plex_audio_devices_submenu(self):
        devs = self.player.get_audio_devices()
        if not devs:
            return [MenuItem("(no devices)", enabled=False)]
        cur = self.config.audio_device or "auto"
        return [MenuItem((d["desc"] or d["name"])[:38], checked=(d["name"] == cur),
                         close_after=False,
                         action=lambda n=d["name"]: self._plex_set_audio_device(n))
                for d in devs]

    def _plex_set_audio_device(self, name):
        self.player.set_audio_device(name)
        self.config.audio_device = "" if name == "auto" else name
        self.config.save()
        self.renderer.menu.replace_page(self._plex_audio_devices_submenu())
        self.renderer.mark_dirty()

    def _plex_sub_font_submenu(self):
        cur = self.config.sub_font
        items = [MenuItem("Default", checked=(not cur), close_after=False,
                          action=lambda: self._plex_set_sub_font(""))]
        for k in theme.available_fonts(include_subtitle_only=True):
            items.append(MenuItem(theme.font_label(k), checked=(k == cur),
                         close_after=False,
                         action=lambda key=k: self._plex_set_sub_font(key)))
        return items

    def _plex_set_sub_font(self, key):
        self.config.sub_font = key
        self.config.save()
        fam = theme.font_family(key) if key else "sans-serif"
        self.player.apply_sub_style(font=fam)
        self.renderer.menu.replace_page(self._plex_sub_font_submenu())
        self.renderer.mark_dirty()

    def _plex_sub_size_submenu(self):
        cur = self.config.sub_size
        return [MenuItem(name, checked=(sz == cur), close_after=False,
                         action=lambda s=sz: self._plex_set_sub_size(s))
                for name, sz in self.SUB_SIZES]

    def _plex_set_sub_size(self, sz):
        self.config.sub_size = sz
        self.config.save()
        self.player.apply_sub_style(size=sz)
        self.renderer.menu.replace_page(self._plex_sub_size_submenu())
        self.renderer.mark_dirty()

    def _plex_sub_color_submenu(self):
        cur = self.config.sub_color
        return [MenuItem(name, checked=(hexc == cur), close_after=False,
                         action=lambda c=hexc: self._plex_set_sub_color(c))
                for name, hexc in self.SUB_COLORS]

    def _plex_set_sub_color(self, hexc):
        self.config.sub_color = hexc
        self.config.save()
        self.player.apply_sub_style(color=hexc)
        self.renderer.menu.replace_page(self._plex_sub_color_submenu())
        self.renderer.mark_dirty()

    def _plex_sub_back_submenu(self):
        cur = self.config.sub_back
        return [MenuItem(name, checked=(hexc == cur), close_after=False,
                         action=lambda c=hexc: self._plex_set_sub_back(c))
                for name, hexc in self.SUB_BACKS]

    def _plex_set_sub_back(self, hexc):
        self.config.sub_back = hexc
        self.config.save()
        self.player.apply_sub_style(back=hexc)
        self.renderer.menu.replace_page(self._plex_sub_back_submenu())
        self.renderer.mark_dirty()

    def _apply_plex_av(self):
        """Apply the persisted subtitle style + audio device to the new stream."""
        if self.config.audio_device:
            self.player.set_audio_device(self.config.audio_device)
        fam = theme.font_family(self.config.sub_font) if self.config.sub_font else None
        self.player.apply_sub_style(font=fam, size=self.config.sub_size,
                                    color=self.config.sub_color,
                                    back=self.config.sub_back)

    # ── Plex-Per-View ─────────────────────────────────────────────────────

    def _ppv_client(self):
        # Locked so a token change (_plex_reset from sign-in / unlink) can't race
        # an in-flight worker into building two clients or seeing a torn state.
        with self._plex_lock:
            if self._plex is None:
                if not self.config.plex_client_id:
                    self.config.plex_client_id = plex.new_client_id()
                    self.config.save()
                from . import __version__
                self._plex = plex.PlexClient(
                    self.config.plex_client_id,
                    token=self.config.plex_user_token or self.config.plex_token,
                    admin_token=self.config.plex_token, version=__version__)
            return self._plex

    def _plex_reset(self):
        """Drop the cached client so the next _ppv_client() rebuilds it with the
        current token (after sign-in, user switch, or unlink)."""
        with self._plex_lock:
            self._plex = None

    def _open_ppv(self):
        """Enter Plex-Per-View (from the home screen or context menu)."""
        r = self.renderer
        self._plex_end()                 # opening the library ends any stream
        r.plexinfo.close()
        self._ppv_return_menu = r.main_menu.open   # came from the home screen?
        r.menu.close()
        r.main_menu.close()
        self._ppv_stack = []
        r.ppv.mode = "browse"
        r.ppv.rows = []
        r.ppv.show()
        r.ppv.set_status("CONNECTING...")
        r.mark_dirty()
        if self._ppv_client().token:
            self._ppv_connect()
        else:
            self._ppv_begin_auth()

    def _ppv_connect(self):
        """Discover the server and list libraries (background)."""
        def work():
            try:
                client = self._ppv_client()
                client.discover_server(prefer=self.config.plex_server_id)
                sections = client.sections()
            except Exception as e:
                self._ppv_error(str(e) or "Couldn't reach Plex.")
                return
            # Cache the library list (show/hide menu) + the server list (server
            # picker) so both menus work without another round-trip.
            self.config.plex_sections = [{"key": s["key"], "title": s["title"]}
                                         for s in sections]
            try:
                self.config.plex_servers = client.list_servers()
            except Exception:
                pass
            self.config.save()
            hidden = set(self.config.plex_hidden_libraries)
            rows = [
                {"type": "search", "title": "SEARCH...", "meta": "",
                 "playable": False},
                {"type": "ondeck", "title": "CONTINUE WATCHING", "meta": "",
                 "playable": False},
                {"type": "watchlist", "title": "MY WATCHLIST", "meta": "",
                 "playable": False},
            ]
            rows += [{"type": "section", "rating_key": s["key"],
                      "title": s["title"].upper(), "meta": "", "playable": False,
                      "section_type": s["type"], "agent": s.get("agent", "")}
                     for s in sections if s["key"] not in hidden]
            self._ppv_push("CHOOSE A LIBRARY", rows, "Plex-Per-View")
        threading.Thread(target=work, daemon=True).start()

    def _ppv_begin_auth(self):
        def work():
            try:
                pin = self._ppv_client().request_pin()
            except Exception:
                self._ppv_error("Couldn't start Plex sign-in.")
                return
            self._ppv_pin_id = pin["id"]
            self.renderer.ppv.set_auth(pin["code"], pin["link"])
            self.renderer.mark_dirty()
            self._ppv_poll_auth()
        threading.Thread(target=work, daemon=True).start()

    def _ppv_poll_auth(self):
        deadline = time.monotonic() + 300
        r = self.renderer
        while (r.ppv.open and r.ppv.mode == "auth"
               and time.monotonic() < deadline):
            try:
                token = self._ppv_client().poll_pin(self._ppv_pin_id)
            except Exception:
                token = None
            if token:
                self.config.plex_token = token
                self.config.plex_user_token = ""   # account level until a user is picked
                self.config.save()
                self._plex_reset()                 # rebuild with the new token
                r.ppv.set_status("CONNECTING...")
                r.mark_dirty()
                self._ppv_choose_user()
                return
            time.sleep(2.0)

    def _ppv_choose_user(self, force: bool = False):
        """After linking (or via Change User), show the Plex Home users. Falls
        through to the library when there's only one user or none are found."""
        r = self.renderer
        r.ppv.show()
        r.ppv.set_status("LOADING USERS...")
        r.mark_dirty()
        def work():
            try:
                users = self._ppv_client().home_users()
            except Exception:
                users = []
            if len(users) <= 1:
                self._ppv_connect()        # single user / not a Home — just go
                return
            rows = [{"type": "user", "rating_key": u["uuid"],
                     "title": u["title"], "meta": "PIN" if u["protected"] else "",
                     "protected": u["protected"],
                     "playable": False} for u in users]
            self._ppv_stack = []
            self._ppv_push("WHO'S WATCHING?", rows, "Plex-Per-View")
        threading.Thread(target=work, daemon=True).start()

    def _ppv_pick_user(self, uuid, name, protected=False):
        r = self.renderer

        def work():
            token = ""
            while True:
                pin = ""
                if protected:
                    pin = self._osk_get(f"Enter PIN for {name}", "")
                    if not pin:
                        # Cancelled — don't switch; return to the user list.
                        self._ppv_choose_user(force=True)
                        return
                r.ppv.set_status("SWITCHING...")
                r.mark_dirty()
                try:
                    token = self._ppv_client().switch_user(uuid, pin)
                except Exception:
                    token = ""
                if token or not protected:
                    break                       # success, or non-protected failure
                r.show_notification("Wrong PIN — try again", 2.5)
            if token:
                self.config.plex_user_token = token
                self.config.plex_user_id = uuid
                self.config.plex_user_name = name
            else:
                # Non-protected switch failed — stay on the account.
                self.config.plex_user_token = ""
                self.config.plex_user_id = ""
                self.config.plex_user_name = ""
            self.config.save()
            self._ppv_stack = []
            self._ppv_connect()
        threading.Thread(target=work, daemon=True).start()

    SORT_OPTIONS = [
        ("Title (A-Z)", "titleSort:asc"), ("Title (Z-A)", "titleSort:desc"),
        ("Date Added (Newest)", "addedAt:desc"), ("Date Added (Oldest)", "addedAt:asc"),
        ("Year (Newest)", "year:desc"), ("Year (Oldest)", "year:asc"),
        ("Rating (Highest)", "rating:desc"), ("Rating (Lowest)", "rating:asc"),
    ]

    def _ppv_select(self):
        r = self.renderer
        # Top bar (Back / Menu) is focusable by D-pad/keyboard.
        if r.ppv.bar_focus == "back":
            self._ppv_back(); return
        if r.ppv.bar_focus == "menu":
            self._toggle_context_menu(); return
        if self._ppv_stack:
            self._ppv_stack[-1]["sel"] = r.ppv.sel
        row = r.ppv.current()
        if not row:
            return
        t = row.get("type")
        title = row.get("title", "")
        rk = row.get("rating_key")
        if t == "user":
            self._ppv_pick_user(rk, title, row.get("protected", False))
            return
        if t == "watchlist":
            self._ppv_open_watchlist()
            return
        if t == "ondeck":
            self._ppv_open_ondeck()
            return
        if t == "search":
            self._ppv_search()
            return
        if t == "sort":
            self.renderer.menu.open_with(self._sort_submenu(), title="SORT BY")
            self.renderer.mark_dirty()
            return
        if row.get("watchlist"):             # an item from the watchlist
            self._ppv_watchlist_open(row)
            return
        if row.get("playable"):
            self._ppv_show_info(row)         # open the info screen first
            return
        if t == "section":
            stype = row.get("section_type")
            if self._ppv_client().is_other_videos({"agent": row.get("agent", "")}):
                self._ppv_other_videos(rk, title)
            elif stype in ("movie", "show"):
                self._ppv_categories(rk, title, stype)
            else:
                self._ppv_open(
                    lambda s, k=rk: self._ppv_client().section_filter(k, sort=s), title)
        elif t in ("all", "allvideos"):
            self._ppv_open(
                lambda s, k=rk: self._ppv_client().section_filter(k, sort=s), title)
        elif t == "genre":
            gid = row.get("genre_id")
            self._ppv_open(
                lambda s, k=rk, g=gid: self._ppv_client().section_filter(
                    k, genre_id=g, sort=s), title)
        elif t == "folderview":
            self._ppv_load_folder(f"/library/sections/{rk}/folder", "FOLDERS", rk)
        elif t == "folder":
            self._ppv_load_folder(row.get("folder"), title, row.get("section", ""))
        elif t == "show":
            self._ppv_show_info(row)         # series info screen (Play All/etc.)
        else:
            self._ppv_open(
                lambda s, k=rk: self._ppv_client().children(k, sort=s), title)

    def _ppv_load_folder(self, path, title, section=""):
        r = self.renderer
        r.ppv.set_status("LOADING...")
        r.mark_dirty()
        crumb = " / ".join(l["title"] for l in self._ppv_stack) or "Plex-Per-View"
        def work():
            try:
                rows = self._ppv_client().folder_items(path, section)
            except Exception as e:
                self._ppv_error(str(e) or "Couldn't load that folder.")
                return
            self._ppv_push(title, rows, crumb)
        threading.Thread(target=work, daemon=True).start()

    def _ppv_other_videos(self, key, title):
        crumb = " / ".join(l["title"] for l in self._ppv_stack) or "Plex-Per-View"
        rows = [
            {"type": "allvideos", "rating_key": key, "title": "ALL VIDEOS",
             "meta": "", "playable": False},
            {"type": "folderview", "rating_key": key, "title": "BY FOLDER",
             "meta": "", "playable": False},
        ]
        self._ppv_push(title, rows, crumb)

    def _ppv_open(self, loader, title, sort="", volatile=False, sortable=True):
        """Load an item list. `loader(sort)` returns rows; the level remembers
        the loader. sortable=True pins a Sort row (library lists); set False for
        lists with no meaningful sort (onDeck, search). volatile=True reloads the
        level every time it's returned to (watchlist, onDeck, search)."""
        r = self.renderer
        r.ppv.set_status("LOADING...")
        r.mark_dirty()
        crumb = " / ".join(l["title"] for l in self._ppv_stack) or "Plex-Per-View"
        def work():
            try:
                rows = loader(sort)
            except Exception as e:
                self._ppv_error(str(e) or "Couldn't load that.")
                return
            self._ppv_push(title, rows, crumb, loader=loader, sort=sort,
                           volatile=volatile, sortable=sortable)
        threading.Thread(target=work, daemon=True).start()

    def _ppv_open_watchlist(self):
        self._ppv_open(lambda s: self._ppv_client().watchlist(sort=s),
                       "MY WATCHLIST", volatile=True)

    def _ppv_open_ondeck(self):
        # volatile so it reloads (and drops finished items) each time it's opened.
        self._ppv_open(lambda s: self._ppv_client().on_deck(),
                       "CONTINUE WATCHING", volatile=True, sortable=False)

    def _ppv_search(self):
        query = self._osk_get("Search Plex", "")
        if not query or not query.strip():
            return
        self._ppv_open(lambda s, q=query: self._ppv_client().search(q),
                       f"SEARCH: {query.upper()}", volatile=True, sortable=False)

    def _ppv_watchlist_open(self, row):
        guid = row.get("guid")
        typ = row.get("type")
        title = row.get("title", "")
        r = self.renderer
        r.ppv.set_status("FINDING...")
        r.mark_dirty()
        def work():
            rk = self._ppv_client().find_on_server(guid)
            if not rk:
                self._ppv_error("Not in your library.")
                return
            if typ in ("movie", "episode", "show"):
                self._ppv_show_info({"rating_key": rk})
            else:
                self._ppv_open(
                    lambda s, k=rk: self._ppv_client().children(k, sort=s), title)
        threading.Thread(target=work, daemon=True).start()

    def _ppv_set_sort(self, sort):
        if not self._ppv_stack or not self._ppv_stack[-1].get("loader"):
            return
        lvl = self._ppv_stack.pop()
        self._ppv_open(lvl["loader"], lvl["title"], sort=sort)

    def _sort_submenu(self):
        cur = self._ppv_stack[-1].get("sort", "") if self._ppv_stack else ""
        return [MenuItem(name, checked=(val == cur),
                         action=lambda v=val: self._ppv_set_sort(v))
                for name, val in self.SORT_OPTIONS]

    def _ppv_categories(self, section_key, title, stype):
        r = self.renderer
        r.ppv.set_status("LOADING...")
        r.mark_dirty()
        crumb = " / ".join(l["title"] for l in self._ppv_stack) or "Plex-Per-View"
        all_label = "ALL MOVIES" if stype == "movie" else "ALL SHOWS"
        def work():
            try:
                genres = self._ppv_client().genres(section_key)
            except Exception:
                genres = []
            rows = [{"type": "all", "rating_key": section_key, "title": all_label,
                     "meta": "", "playable": False}]
            for g in genres:
                rows.append({"type": "genre", "rating_key": section_key,
                             "genre_id": g["id"], "title": g["title"].upper(),
                             "meta": "", "playable": False})
            self._ppv_push(title, rows, crumb)
        threading.Thread(target=work, daemon=True).start()

    def _ppv_show_info(self, row):
        rk = row.get("rating_key")
        r = self.renderer
        r.ppv.set_status("LOADING...")
        r.mark_dirty()
        def work():
            try:
                detail = self._ppv_client().item_detail(rk)
            except Exception as e:
                self._ppv_error(str(e) or "Couldn't load info.")
                return
            self._plex_info_data = detail
            kind = detail.get("type", "")
            kind = kind if kind in ("show", "episode") else "default"
            self._plex_info_kind = kind          # remembered for return-to-info
            on_wl = self._plex_watchlist_has(detail.get("guid", "")) \
                if kind != "episode" else False
            r.ppv.close()
            r.plexinfo.show(detail, watchlisted=on_wl, kind=kind)
            r.update()
        threading.Thread(target=work, daemon=True).start()

    def _plex_info_activate(self):
        fid = self.renderer.plexinfo.focused_id()
        if fid == "play":
            self._plex_info_play()
        elif fid == "playall":
            self._plex_show_playall(shuffle=False)
        elif fid == "shuffle":
            self._plex_show_playall(shuffle=True)
        elif fid == "seasons":
            self._plex_show_seasons()
        elif fid == "watchlist":
            self._plex_info_watchlist()
        elif fid == "back":
            self._plex_info_back()

    def _plex_show_seasons(self):
        d = self._plex_info_data or {}
        rk = d.get("rating_key")
        title = d.get("title", "")
        self.renderer.plexinfo.close()
        self.renderer.ppv.show()     # bring PPV back so LOADING/list is visible
        self._ppv_open(
            lambda s, k=rk: self._ppv_client().children(k, sort=s), title)

    def _plex_show_playall(self, shuffle=False):
        d = self._plex_info_data or {}
        rk = d.get("rating_key")
        self.renderer.mark_dirty()
        def work():
            try:
                eps = self._ppv_client().all_episodes(rk)
            except Exception as e:
                self._ppv_error(str(e) or "Couldn't load episodes.")
                return
            if not eps:
                self._ppv_error("No episodes to play.")
                return
            if shuffle:
                import random
                random.shuffle(eps)
            self._plex_queue = eps
            self._plex_queue_pos = 0
            self._ppv_play(eps[0], d.get("title", ""), resume=False,
                           keep_queue=True)
        threading.Thread(target=work, daemon=True).start()

    def _plex_info_play(self):
        d = self._plex_info_data or {}
        if d.get("offset", 0) > 5:
            self._ppv_resume_prompt(d)
        else:
            self._plex_begin_play(d, resume=False)

    def _plex_begin_play(self, detail, resume):
        """Play `detail`. For a TV episode, queue the rest of the show from this
        episode on, so playback continues in sequence after it finishes (works
        whether the episode was picked from the show page or Continue Watching).
        Movies / clips / a final episode just play on their own."""
        rk = detail.get("rating_key")
        title = detail.get("title", "")
        sub = detail.get("subtitle") or detail.get("meta", "")
        show_key = detail.get("grandparent_key")
        if detail.get("type") != "episode" or not show_key:
            self._ppv_play(rk, title, sub, resume=resume)
            return
        self.renderer.ppv.set_status("STARTING...")
        self.renderer.mark_dirty()
        def work():
            try:
                eps = self._ppv_client().all_episodes(show_key)
            except Exception:
                eps = []
            queue = self._episode_queue(eps, str(rk))
            if queue:
                self._plex_queue = queue
                self._plex_queue_pos = 0
                self._ppv_play(queue[0], title, sub, resume=resume,
                               keep_queue=True)
            else:
                self._ppv_play(rk, title, sub, resume=resume)
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _episode_queue(eps, rk):
        """Episode rating_keys from `rk` to the end of the show, or [] if `rk`
        isn't found or is already the last episode (nothing to queue after it)."""
        try:
            idx = eps.index(rk)
        except ValueError:
            return []
        return eps[idx:] if idx < len(eps) - 1 else []

    def _plex_watchlist_has(self, guid):
        """Best-effort check whether `guid` is on the user's watchlist. Matches
        on the full guid or its trailing metadata id (server vs Discover guids
        share the id)."""
        if not guid:
            return False
        try:
            wl = self._ppv_client().watchlist()
        except Exception:
            return False
        gid = guid.rstrip("/").split("/")[-1]
        for r in wl:
            wg = r.get("guid", "")
            if wg == guid or (gid and wg.rstrip("/").split("/")[-1] == gid):
                return True
        return False

    def _plex_info_watchlist(self):
        d = self._plex_info_data or {}
        guid = d.get("guid", "")
        info = self.renderer.plexinfo
        add = not info.watchlisted
        def work():
            if self._ppv_client().watchlist_set(guid, add):
                info.watchlisted = add
            self.renderer.mark_dirty()
        threading.Thread(target=work, daemon=True).start()

    def _plex_info_back(self):
        self.renderer.plexinfo.close()
        if self._ppv_stack:
            self._ppv_show_top()   # reloads watchlist so removed items disappear
        self.renderer.update()

    def _ppv_resume_prompt(self, row):
        ts = theme.fmt_hms(row.get("offset", 0))
        items = [
            MenuItem(f"Resume from {ts}",
                     action=lambda: self._plex_begin_play(row, resume=True)),
            MenuItem("Start from Beginning",
                     action=lambda: self._plex_begin_play(row, resume=False)),
        ]
        self.renderer.menu.open_with(items, title="RESUME?")
        self.renderer.mark_dirty()

    def _ppv_play(self, rating_key, title, subtitle="", resume=True,
                  keep_queue=False):
        if not keep_queue:
            self._plex_queue = []    # a one-off play cancels any episode queue
            self._plex_queue_pos = 0
        r = self.renderer
        r.menu.close()               # in case the resume prompt opened it
        r.plexinfo.close()
        r.ppv.set_status("STARTING...")
        r.mark_dirty()
        def work():
            try:
                info = self._ppv_client().play_info(
                    rating_key, self.config.plex_quality, resume=resume)
            except Exception as e:
                self._ppv_error(str(e) or "Couldn't play that.")
                return
            r.ppv.close()
            r.state = UIState.WATCHING
            r.plex_playing = True
            self._plex_paused = False
            self._plex_duration = None
            self._plex_pos = 0.0
            self._plex_now_rk = rating_key
            self._plex_time_base = float(info.get("time_base") or 0)
            self._plex_markers = info.get("markers") or []
            r.plexosd.skip_label = ""
            r.plexosd.set_info(info.get("title") or title,
                               info.get("subtitle") or subtitle)
            r.plexosd.paused = False
            r.plexosd.adjusting = False
            r.plexosd.focus = 0          # default highlight on the timeline
            r.plexosd.volume = self.config.volume
            r.plexosd.muted = self.config.muted
            # play_info already zeroed the offset when resume=False (and when
            # the transcoder starts at the offset itself).
            self.player.play(info["url"], start=info.get("offset", 0),
                             headers=info.get("headers"))
            self._apply_plex_av()        # subtitle style + audio device
            self._plex_show_osd()
            self._start_plex_monitor()
            r.update()
        threading.Thread(target=work, daemon=True).start()

    # ── Plex playback controls ────────────────────────────────────────────

    def _space_key(self):
        if self.renderer.plex_playing:
            self._plex_toggle_pause()
        else:
            self._char_typed(" ")

    def _plex_show_osd(self):
        self.renderer.plexosd.show()
        self._plex_osd_until = time.monotonic() + 5.0
        self.renderer.mark_dirty()

    def _start_plex_monitor(self):
        # Generation counter, not a boolean: bumping it kills any older loop,
        # and a stale loop's exit can never knock out the new one.
        self._plex_monitor_gen += 1
        threading.Thread(target=self._plex_monitor_loop,
                         args=(self._plex_monitor_gen,), daemon=True).start()

    def _stop_plex_monitor(self):
        self._plex_monitor_gen += 1

    def _plex_monitor_loop(self, gen: int):
        r = self.renderer
        while gen == self._plex_monitor_gen and r.plex_playing:
            # mpv's clock starts at 0 even when a transcode began mid-file, so
            # every position is shifted by the transcode's start offset.
            base = self._plex_time_base
            raw = self.player.get_property("time-pos")
            pos = (raw + base) if raw is not None else None
            if pos is not None:
                self._plex_pos = pos
            if self._plex_duration is None:
                d = self.player.get_property("duration")
                if d:
                    self._plex_duration = d + base
            r.plexosd.set_progress(pos or 0, self._plex_duration or 0, self._plex_paused)
            # Skip Intro/Credits: show the button only while pos is inside a marker.
            self._update_skip_button(pos or 0)
            if r.plexosd.visible:
                if time.monotonic() > self._plex_osd_until:
                    r.plexosd.hide()
                r.mark_dirty()
            # Heartbeat: tell the server our position every ~10s so Now-Playing
            # and cross-device "Continue Watching" stay current mid-stream.
            now = time.monotonic()
            if pos is not None and now - self._plex_last_report >= 10:
                self._plex_last_report = now
                self._plex_report("paused" if self._plex_paused else "playing")
            time.sleep(0.5)

    def _update_skip_button(self, pos):
        """Show the SKIP button on the OSD only while playback is inside an
        intro/credits marker; hide it otherwise."""
        label, end = "", 0.0
        for mk in self._plex_markers:
            if mk["start"] <= pos < mk["end"]:
                label = "SKIP INTRO" if mk["type"] == "intro" else "SKIP CREDITS"
                end = mk["end"]
                break
        osd = self.renderer.plexosd
        osd.skip_to = end
        if label != osd.skip_label:
            osd.skip_label = label      # entered or left a marker — redraw the bar
            self.renderer.mark_dirty()

    def _plex_skip_marker(self):
        """Press SKIP: jump to the end of the active marker. For a credits
        marker this lands at ~EOF and the normal finish/next-episode flow runs."""
        osd = self.renderer.plexosd
        if osd.skip_to:
            # Markers are absolute; mpv's clock starts at the transcode offset.
            self.player.seek(osd.skip_to - self._plex_time_base, "absolute")
            osd.skip_label = ""         # hide now; the monitor re-evaluates next tick
            self._plex_show_osd()

    def _plex_focus(self, delta):
        osd = self.renderer.plexosd
        if osd.adjusting:
            return   # volume is selected for adjustment — Up/Down is locked
        osd.scrubbing = False    # moving the highlight ends scrub mode
        osd.focus_next() if delta > 0 else osd.focus_prev()
        self._plex_show_osd()

    def _plex_dpad(self, direction):
        """Left/Right: adjust volume (when selected), scrub the timeline (when
        selected), else move the highlight."""
        osd = self.renderer.plexosd
        if osd.adjusting:
            self._plex_vol(direction > 0)
        elif osd.scrubbing:
            self._plex_seek(10 * direction)
        else:
            self._plex_focus(direction)   # Left/Right also move the highlight

    def _plex_vol(self, up):
        self._unmute_if_muted()
        vol = self.player.volume_up(5) if up else self.player.volume_down(5)
        self.config.volume = vol
        self.renderer.volume = vol
        self.renderer.plexosd.volume = vol
        self.renderer.plexosd.muted = False
        self._plex_show_osd()

    def _plex_seek(self, delta):
        self.player.seek(delta, "relative")
        self._plex_show_osd()

    def _plex_skip(self, delta):
        """Skip to the next/previous episode (in a Play All / Shuffle queue) or,
        for anything else (a movie), the next/previous chapter. Off the queue's
        edge (prev on the first item, next on the last) it falls through to a
        chapter skip so the button always does something."""
        q = self._plex_queue
        if q:
            pos = self._plex_queue_pos + delta
            if 0 <= pos < len(q):
                self._plex_report("stopped")   # save outgoing episode position
                self._plex_queue_pos = pos
                self._ppv_play(q[pos], "", resume=False, keep_queue=True)
                return
        self.player.chapter_skip(delta)
        self._plex_show_osd()

    def _plex_toggle_pause(self):
        self._plex_paused = not self._plex_paused
        self.player.set_pause(self._plex_paused)
        self.renderer.plexosd.paused = self._plex_paused
        self._plex_show_osd()

    def _plex_activate(self):
        osd = self.renderer.plexosd
        fid = osd.focused_id()
        if fid == "volume":
            osd.adjusting = not osd.adjusting   # enter/exit volume adjust mode
            self._plex_show_osd()
            return
        if fid == "skip":
            self._plex_skip_marker()
            return
        if fid == "timeline":
            osd.scrubbing = not osd.scrubbing   # select/deselect to scrub
            self._plex_show_osd()
            return
        if fid == "back10":
            self._plex_seek(-10)
        elif fid == "fwd10":
            self._plex_seek(10)
        elif fid == "prev":
            self._plex_skip(-1)
        elif fid == "next":
            self._plex_skip(1)
        elif fid == "playpause":
            self._plex_toggle_pause()
        elif fid == "stop":
            self._plex_stop()
        elif fid == "menu":
            self._toggle_context_menu()

    def _plex_click(self, name, x):
        osd = self.renderer.plexosd
        if name == "timeline":
            frac = osd.seek_fraction(x)
            if frac is not None and self._plex_duration:
                # The click targets an absolute position; shift into mpv's
                # (transcode-relative) clock.
                self.player.seek(frac * self._plex_duration - self._plex_time_base,
                                 "absolute")
        elif name == "volume":
            frac = osd.volume_fraction(x)
            if frac is not None:
                self._unmute_if_muted()   # dragging the bar means "I want sound"
                vol = self.player.set_volume(int(frac * 100))
                self.config.volume = vol
                self.renderer.volume = vol
                osd.volume = vol
                osd.muted = False
        else:
            osd.focus_to(name)
            self._plex_activate()
        self._plex_show_osd()

    def _plex_report(self, state: str, finished: bool = False):
        """Best-effort timeline report for the item playing now. `finished`
        also scrobbles, the canonical mark-watched call, so Plex reliably
        clears the resume point and flags the item watched."""
        rk = self._plex_now_rk
        if not rk:
            return
        dur = self._plex_duration or 0
        t = dur if (finished and dur) else self._plex_pos

        def work():
            client = self._ppv_client()
            client.report_timeline(rk, t, dur, state=state)
            if finished:
                client.scrobble(rk)
        threading.Thread(target=work, daemon=True).start()

    def _cache_offset(self, rk: str, offset: int):
        """Reflect a new resume point in the cached browse rows so re-selecting
        the item offers to resume (or starts over once watched)."""
        if rk and self._ppv_stack:
            for row in self._ppv_stack[-1]["rows"]:
                if row.get("rating_key") == rk and row.get("playable"):
                    row["offset"] = offset

    def _plex_teardown(self):
        """Tear down playback state + stop mpv (no server report, no nav)."""
        self._stop_plex_monitor()
        self.renderer.plex_playing = False
        self.renderer.plexosd.hide()
        self.renderer.plexosd.adjusting = False
        self.renderer.plexosd.scrubbing = False
        self.renderer.plexosd.skip_label = ""
        self._plex_markers = []
        self._plex_paused = False
        self._plex_now_rk = ""
        self._plex_time_base = 0.0
        self.player.stop()

    def _plex_end(self):
        """Stop Plex playback and tear down (no navigation)."""
        if not self.renderer.plex_playing:
            return
        # Save the resume point on the server (Plex clears it if we finished).
        rk, pos, dur = self._plex_now_rk, self._plex_pos, self._plex_duration or 0
        if rk and pos > 1:
            self._plex_report("stopped")
            self._cache_offset(rk, 0 if (dur > 0 and pos > dur - 30) else int(pos))
        self._plex_teardown()

    def _plex_after_stop(self, offset: int):
        """Playback ended — return to the item's info screen (with the new
        resume offset), else the browse list, else out of PPV entirely."""
        if self._plex_info_data:
            self._plex_info_data["offset"] = offset
            self.renderer.plexinfo.show(
                self._plex_info_data,
                watchlisted=self.renderer.plexinfo.watchlisted,
                kind=self._plex_info_kind)
            self.renderer.update()
        elif self._ppv_stack:
            lvl = self._ppv_stack[-1]
            self.renderer.ppv.set_browse(lvl["title"], lvl["rows"],
                                         lvl["crumb"], lvl["sel"])
            self.renderer.ppv.show()
            self.renderer.update()
        else:
            self._ppv_exit()

    def _plex_finished(self):
        """Current item reached its end: report it watched, clear the resume
        point, and return to the item's info screen (or the browse list)."""
        if not self.renderer.plex_playing:
            return
        rk = self._plex_now_rk
        self._plex_report("stopped", finished=True)
        self._cache_offset(rk, 0)
        self._plex_teardown()
        self._plex_after_stop(0)

    def _plex_stop(self):
        """Stop button / Esc: end playback and return to the item's info screen."""
        was_playing = self.renderer.plex_playing
        pos, dur = self._plex_pos, self._plex_duration or 0
        self._plex_end()
        if not was_playing:
            return
        self._plex_after_stop(0 if (dur and pos > dur - 30) else int(pos))

    def _ppv_push(self, title, rows, crumb, loader=None, sort="", volatile=False,
                  sortable=True):
        # Sortable item lists get a "Sort by..." row pinned at the top so the
        # user can re-order without the context menu.
        has_sort = bool(loader and sortable and rows
                        and rows[0].get("type") != "sort")
        if has_sort:
            label = self._sort_label(sort) or "Default"
            rows = [{"type": "sort", "title": f"Sort by: {label}",
                     "meta": "", "playable": False}] + rows
        sel0 = 1 if has_sort else 0
        self._ppv_stack.append({"title": title, "rows": rows,
                                "sel": sel0,
                                "crumb": crumb, "loader": loader, "sort": sort,
                                "volatile": volatile, "sortable": sortable})
        self.renderer.ppv.set_browse(title, rows, crumb, sel=sel0)
        self.renderer.ppv.show()     # ensure visible (e.g. opened from info screen)
        self.renderer.mark_dirty()

    def _sort_label(self, val):
        for name, v in self.SORT_OPTIONS:
            if v == val:
                return name
        return "" if val else "Default"

    def _ppv_back(self):
        if len(self._ppv_stack) <= 1:
            self._ppv_exit()
            return
        self._ppv_stack.pop()
        self._ppv_show_top()

    def _ppv_show_top(self):
        """Re-show the top browse level. Volatile levels (watchlist) reload from
        the server so changes made deeper (e.g. removed from watchlist) appear.
        The old level stays on the stack until the reload SUCCEEDS — a failed
        refresh falls back to the cached rows instead of eating a level."""
        if not self._ppv_stack:
            return
        lvl = self._ppv_stack[-1]
        if lvl.get("volatile") and lvl.get("loader"):
            r = self.renderer
            r.ppv.set_status("LOADING...")
            r.ppv.show()
            r.mark_dirty()

            def work():
                try:
                    rows = lvl["loader"](lvl.get("sort", ""))
                except Exception:
                    rows = None
                if rows is not None:
                    if self._ppv_stack and self._ppv_stack[-1] is lvl:
                        self._ppv_stack.pop()
                    self._ppv_push(lvl["title"], rows, lvl["crumb"],
                                   loader=lvl["loader"], sort=lvl.get("sort", ""),
                                   volatile=True,
                                   sortable=lvl.get("sortable", True))
                else:
                    r.ppv.set_browse(lvl["title"], lvl["rows"], lvl["crumb"],
                                     lvl["sel"])
                    r.ppv.show()
                    r.mark_dirty()
            threading.Thread(target=work, daemon=True).start()
            return
        self.renderer.ppv.set_browse(lvl["title"], lvl["rows"], lvl["crumb"], lvl["sel"])
        self.renderer.ppv.show()
        self.renderer.mark_dirty()

    def _ppv_exit(self):
        self.renderer.ppv.close()
        self.renderer.plexinfo.close()
        self._ppv_stack = []
        if getattr(self, "_ppv_return_menu", False) or not self.channels:
            self.renderer.main_menu.show(self._main_menu_select)
        self.renderer.update()

    def _ppv_error(self, msg):
        self.renderer.ppv.set_status(msg)
        self.renderer.mark_dirty()

