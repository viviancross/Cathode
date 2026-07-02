"""Options / settings menu tree — appearance (themes, fonts, profiles, the
custom-theme editor), weather, display, input remapping, playlist management,
and the update-check flow. Mixed into App (cathode.app)."""

from __future__ import annotations

import os
import threading
import time

from . import weather
from .ui import theme
from .ui.menu import MenuItem


class MenusMixin:
    # Built-in look presets (theme + font + scanline intensity). Not deletable.
    BUILTIN_PROFILES = {
        "Classic Blue":   {"theme": "blue",  "font": "vcr",        "scanline_alpha": 40},
        "Amber Terminal": {"theme": "amber", "font": "vt220",      "scanline_alpha": 50},
        "Green Phosphor": {"theme": "green", "font": "ibm",        "scanline_alpha": 50},
        "Synthwave":      {"theme": "synth", "font": "vt323", "scanline_alpha": 40},
        "Commodore":      {"theme": "c64",   "font": "pixelop", "scanline_alpha": 40},
        "Monochrome":     {"theme": "mono",  "font": "dejavu",     "scanline_alpha": 30},
    }

    # ── Update check (GitHub Releases — notify + download, no self-overwrite) ─

    def _update_check_launch(self):
        """Quiet check on launch: only speak up if a newer version exists."""
        from . import updater, __version__
        try:
            latest = updater.check_latest()
        except updater.UpdateError:
            return
        if latest and updater.is_newer(latest["tag"], __version__):
            self.renderer.show_notification(
                f"Update {latest['tag']} available — Check for Updates in the menu", 6.0)

    def _check_updates(self):
        """Menu action: checking screen -> result -> confirm -> download with a
        progress bar -> 'restart to apply'.  Declining or finishing returns the
        user to the menu they were on."""
        from . import updater, __version__
        snap = self.renderer.menu.snapshot()   # capture the menu to return to

        def work():
            # 1. Checking screen.
            self.renderer.menu.open_with(
                [MenuItem("Contacting GitHub…", enabled=False)],
                title="CHECKING FOR UPDATES")
            self.renderer.update()
            try:
                latest = updater.check_latest()
            except updater.UpdateError as e:
                self._update_done(snap, "UPDATE CHECK FAILED", str(e))
                return
            # 2. Already current.
            if not latest or not updater.is_newer(latest["tag"], __version__):
                self._update_done(snap, "UP TO DATE",
                                  f"You're on the latest version (v{__version__}).")
                return
            tag = latest["tag"]
            asset = updater.pick_asset(latest["assets"])
            if not asset:
                self._update_done(snap, "UPDATE AVAILABLE",
                    f"{tag} is available, but there's no build for this platform.")
                return
            # 3. Confirm download/install.
            if not self._confirm_yesno("UPDATE AVAILABLE",
                    f"{tag} is available. Download and install it?",
                    yes="Download", no="Not now"):
                self.renderer.menu.restore(snap)   # No -> back to last menu
                self.renderer.update()
                return
            # 4. Download with a progress bar.
            self.renderer.menu.close()
            updates_dir = os.path.join(self._runtime_dir, "updates")
            last = [0.0]

            def prog(done, total):
                now = time.monotonic()
                if total and done < total and now - last[0] < 0.1:
                    return                       # throttle repaints
                last[0] = now
                frac = (done / total) if total else 0.0
                mb = done / 1024 / 1024
                if total:
                    lbl = f"Downloading {tag}   {mb:.1f} / {total/1024/1024:.1f} MB"
                else:
                    lbl = f"Downloading {tag}   {mb:.1f} MB"
                self.renderer.set_download_progress(lbl, frac)

            try:
                dest = updater.download(asset["url"], updates_dir, asset["name"],
                                        on_progress=prog, total=asset.get("size", 0))
            except updater.UpdateError as e:
                self.renderer.clear_download_progress()
                self._update_done(snap, "DOWNLOAD FAILED", str(e))
                return
            self.renderer.clear_download_progress()
            # 4b. Verify against the release's .sha256 sidecar when one exists
            # (skipped silently when the release doesn't publish one).
            side = updater.find_checksum_asset(latest["assets"], asset["name"])
            if side:
                try:
                    updater.verify_sha256(dest, side["url"])
                except updater.UpdateError as e:
                    try:
                        os.remove(dest)
                    except OSError:
                        pass
                    self._update_done(snap, "UPDATE FAILED", str(e))
                    return
            # 5. Stage the apply-on-quit script and tell the user to restart.
            try:
                self._pending_apply = updater.write_apply_script(
                    dest, updater.install_dir(), updates_dir)
            except Exception:
                pass
            self._update_done(snap, "UPDATE READY",
                              "Downloaded. Restart Cathode to finish installing.")

        threading.Thread(target=work, daemon=True).start()

    def _update_done(self, snap, title: str, message: str):
        """End an update flow: show a message (OK), then return the user to the
        menu they started from."""
        self._confirm_notice(title, message)
        self.renderer.menu.restore(snap)
        self.renderer.update()

    # ── Context menu tree ─────────────────────────────────────────────────

    def _build_menu(self):
        fav = self._favorite_target()
        is_fav = fav is not None and fav.number in self._favorites
        return [
            MenuItem("Program Guide", action=self._toggle_guide, hint="G"),
            MenuItem("Remove Favorite" if is_fav else "Add Favorite",
                     action=self._toggle_favorite, hint="F", checked=is_fav),
            MenuItem("Channel Up", action=self._channel_up, hint="[^]"),
            MenuItem("Channel Down", action=self._channel_down, hint="[v]"),
            MenuItem("Volume Up", action=self._vol_up, hint="[>]", close_after=False),
            MenuItem("Volume Down", action=self._vol_down, hint="[<]", close_after=False),
            MenuItem("Mute", action=self._toggle_mute, hint="M",
                     checked=self.player.muted),
            MenuItem("Plex-Per-View", action=self._open_ppv),
            MenuItem("Playlists", submenu=self._playlists_submenu),
            MenuItem("Options", submenu=self._options_submenu),
            MenuItem("Main Menu", action=self._open_main_menu),
            MenuItem("Quit", action=self._quit_app, hint="Q"),
        ]

    def _options_submenu(self):
        return [
            MenuItem("Themes", submenu=self._themes_submenu),
            MenuItem("Weather", submenu=self._weather_submenu),
            MenuItem("Plex", submenu=self._plex_options_submenu),
            MenuItem("Keyboard Shortcuts", submenu=self._keyboard_keys_submenu),
            MenuItem("Gamepad Buttons", submenu=self._gamepad_keys_submenu),
            MenuItem("Audio Device", submenu=self._plex_audio_devices_submenu),
            MenuItem("Display", submenu=self._display_submenu),
            MenuItem("Check for Updates", action=self._check_updates),
        ]

    # ── Input remapping menus ─────────────────────────────────────────────

    def _keyboard_keys_submenu(self):
        keys = self._resolved_keys()
        return [MenuItem(f"{label}: {(keys.get(aid) or '').upper() or '(none)'}",
                         submenu=(lambda a=aid: self._key_choice_submenu(a)))
                for aid, label, _, _ in self.INPUT_ACTIONS]

    def _key_choice_submenu(self, action):
        cur = self._resolved_keys().get(action, "")
        items = [MenuItem("(none)", checked=(not cur), close_after=False,
                          action=lambda: self._set_key(action, ""))]
        items += [MenuItem(k.upper(), checked=(k == cur), close_after=False,
                           action=lambda key=k: self._set_key(action, key))
                  for k in self.KEY_CHOICES]
        return items

    def _set_key(self, action, key):
        binds = self._resolved_keys()
        if key:                       # free this key from any other action
            for a in list(binds):
                if binds[a] == key and a != action:
                    binds[a] = ""
        binds[action] = key
        self.config.key_bindings = binds
        self.config.save()
        self._build_hotkeys()
        self.renderer.menu.replace_page(self._key_choice_submenu(action))
        self.renderer.mark_dirty()

    def _gamepad_keys_submenu(self):
        pad = self._resolved_pad()
        return [MenuItem(f"{label}: {(pad.get(aid) or '').upper() or '(none)'}",
                         submenu=(lambda a=aid: self._pad_choice_submenu(a)))
                for aid, label, _, _ in self.INPUT_ACTIONS]

    def _pad_choice_submenu(self, action):
        cur = self._resolved_pad().get(action, "")
        items = [MenuItem("(none)", checked=(not cur), close_after=False,
                          action=lambda: self._set_pad(action, ""))]
        items += [MenuItem(b.upper(), checked=(b == cur), close_after=False,
                           action=lambda btn=b: self._set_pad(action, btn))
                  for b in self.PAD_CHOICES]
        return items

    def _set_pad(self, action, button):
        binds = self._resolved_pad()
        if button:
            for a in list(binds):
                if binds[a] == button and a != action:
                    binds[a] = ""
        binds[action] = button
        self.config.gamepad_bindings = binds
        self.config.save()
        self._build_gamepad_buttons()
        self.renderer.menu.replace_page(self._pad_choice_submenu(action))
        self.renderer.mark_dirty()

    def _themes_submenu(self):
        return [
            MenuItem("Color Theme", submenu=self._theme_submenu),
            MenuItem("Font", submenu=self._font_submenu),
            MenuItem("Profiles", submenu=self._profiles_submenu),
        ]

    def _weather_submenu(self):
        z = self.config.weather_zip or "(not set)"
        # close_after=False keeps us in the Weather submenu; the handlers refresh
        # the page so the new zip/units/country label shows immediately.
        return [
            MenuItem(f"Zip Code: {z}", action=self._set_weather_zip,
                     close_after=False),
            MenuItem(f"Country: {weather.country_name(self.config.weather_country)}",
                     submenu=self._country_submenu),
            MenuItem(f"Units: °{self.config.weather_units}",
                     action=self._toggle_weather_units, close_after=False),
        ]

    def _country_submenu(self):
        cur = (self.config.weather_country or "").upper()
        return [MenuItem(name, action=lambda c=code: self._set_weather_country(c),
                         checked=(code == cur), close_after=False)
                for code, name in weather.COUNTRIES]

    def _set_weather_zip(self):
        z = self._osk_get("Weather zip / postal code", self.config.weather_zip)
        if z is None:                      # cancelled
            return
        self.config.weather_zip = z.strip()
        self._apply_weather_config()

    def _toggle_weather_units(self):
        self.config.weather_units = \
            "C" if self.config.weather_units.upper().startswith("F") else "F"
        self._apply_weather_config()

    def _set_weather_country(self, code):
        self.config.weather_country = code
        self.config.save()
        if self.renderer.weather:
            self.renderer.weather.configure(self.config.weather_zip,
                                            self.config.weather_units, code)
        # Return to the Weather submenu, rebuilt so its "Country:" label updates.
        self.renderer.menu.back_and_replace(self._weather_submenu())
        self.renderer.mark_dirty()

    def _apply_weather_config(self):
        self.config.save()
        if self.renderer.weather:
            self.renderer.weather.configure(self.config.weather_zip,
                                            self.config.weather_units,
                                            self.config.weather_country)
        self.renderer.menu.replace_page(self._weather_submenu())  # refresh labels
        self.renderer.mark_dirty()

    def _display_submenu(self):
        items = [MenuItem("Fullscreen", action=self._toggle_fullscreen, hint="W",
                          checked=self._fullscreen, close_after=False),
                 MenuItem("Aspect Ratio", submenu=self._aspect_submenu)]
        for i, name in enumerate(self.player.get_displays()):
            # close_after=False so picking a display keeps the menu open.
            items.append(MenuItem(name or f"Display {i}",
                         action=lambda idx=i: self._switch_display(idx),
                         close_after=False))
        return items

    def _aspect_submenu(self):
        cur = self.config.video_aspect
        return [MenuItem(m, checked=(m == cur), close_after=False,
                         action=lambda x=m: self._set_aspect(x, from_menu=True))
                for m in self.player.ASPECTS]

    def _set_aspect(self, mode, from_menu=False):
        self.config.video_aspect = mode
        self.config.save()
        self.player.set_aspect(mode)
        if from_menu:
            self.renderer.menu.replace_page(self._aspect_submenu())
            self.renderer.mark_dirty()
        else:
            self.renderer.show_notification(f"Aspect: {mode}", 2.5)

    def _cycle_aspect(self):
        """R3: step to the next aspect ratio (works globally; persists and
        applies to the current and next video)."""
        opts = self.player.ASPECTS
        cur = self.config.video_aspect
        i = (opts.index(cur) + 1) % len(opts) if cur in opts else 0
        self._set_aspect(opts[i])

    def _switch_display(self, index: int):
        """Move the window to monitor `index`, preserving the current windowed /
        fullscreen state.  mpv emits new osd dimensions, which the resize handler
        uses to rescale the aspect ratio + OSD."""
        print(f"[cathode] Switching to display {index}")
        self.player.set_display(index)
        if self._fullscreen:
            # Re-assert fullscreen so it relocates to the new screen.
            self.player.set_fullscreen(False)
            self.player.set_fullscreen(True)
        else:
            # mpv won't relocate an already-open windowed window from `screen`
            # alone, so nudge it onto the target screen.
            self.player.move_window_to_screen(index)

    # ── Playlist / network profiles ───────────────────────────────────────

    def _playlists_submenu(self):
        active = self.config.playlist_url
        items = []
        for pl in self.config.playlists:
            items.append(MenuItem(
                pl.get("name", "(unnamed)"),
                action=lambda p=pl: self._switch_playlist(p),
                checked=(pl.get("playlist_url") == active)))
        items.append(MenuItem("-" * 16, enabled=False))
        items.append(MenuItem("Add playlist...", action=self._add_playlist_dialog))
        items.append(MenuItem("Delete playlist...",
                              submenu=self._delete_playlist_submenu))
        return items

    def _delete_playlist_submenu(self):
        items = [MenuItem(p.get("name", "?"), close_after=False,
                          action=lambda pl=p: self._delete_playlist(pl))
                 for p in self.config.playlists]
        if not items:
            items.append(MenuItem("(no saved playlists)", enabled=False))
        return items

    def _add_playlist_dialog(self):
        """OSK-prompt for a new playlist; returns the saved dict (or None)."""
        name = self._osk_get("Playlist name", "")
        if not name:
            return None
        m3u_url = self._osk_get(f"M3U URL for '{name}'", "")
        if not m3u_url:
            return None
        epg_url = self._osk_get("XMLTV EPG URL (optional)", "")
        pl = {"name": name, "playlist_url": m3u_url, "epg_url": epg_url or ""}
        self.config.playlists.append(pl)
        self.config.save()
        print(f"[cathode] Added playlist: {name}")
        return pl

    def _delete_playlist(self, pl):
        if pl in self.config.playlists:
            self.config.playlists.remove(pl)
            # Clear the active URL if we just deleted the active playlist, so it
            # doesn't reappear as a synthetic "Current" entry in Load Playlist.
            if pl.get("playlist_url") == self.config.playlist_url:
                self.config.playlist_url = ""
                self.config.epg_url = ""
            self.config.save()
            print(f"[cathode] Deleted playlist: {pl.get('name')}")
        self.renderer.menu.replace_page(self._delete_playlist_submenu())
        self.renderer.mark_dirty()

    def _switch_playlist(self, pl):
        """Switch to a saved playlist: reload channels + EPG and retune."""
        self.config.playlist_url = pl.get("playlist_url", "")
        self.config.epg_url = pl.get("epg_url", "")
        self.config.save()
        self.channels = []
        self.epg = None
        self.renderer.epg = None
        print(f"[cathode] Switching to playlist: {pl.get('name')}")
        # May OSK-prompt on failure; a cancel lands on the home screen instead
        # of leaving a stale half-switched state.
        if not self._load_playlist_interactive() or not self.channels:
            self._open_main_menu()
            return
        self.renderer.channels = self.channels
        self._rebuild_categories()
        if self.config.epg_url:
            threading.Thread(target=self._load_epg, daemon=True).start()
        self._ch_idx = 0
        self._tune(0, initial=False)

    def _theme_submenu(self):
        items = []
        labels = self._builtin_theme_labels()
        for label in labels:
            items.append(MenuItem(label,
                         action=lambda i=label: self._select_theme(i),
                         checked=(self._active_theme == label), close_after=False))
        # User-created themes go below the built-ins (overrides of a built-in
        # name are already shown in place above).
        for name in self.config.custom_themes:
            if name in labels:
                continue
            items.append(MenuItem(name,
                         action=lambda i=name: self._select_theme(i),
                         checked=(self._active_theme == name), close_after=False))
        # "Custom Theme..." (the editor) always stays at the very bottom.
        items.append(MenuItem("Custom Theme...", action=self._open_theme_editor))
        return items

    def _font_submenu(self):
        return [MenuItem(theme.font_label(k),
                         action=lambda key=k: self._apply_font_key(key),
                         checked=(theme.current_font() == k), close_after=False)
                for k in theme.available_fonts()]

    def _profiles_submenu(self):
        items = []
        for name in list(self.BUILTIN_PROFILES) + list(self.config.profiles):
            items.append(MenuItem(name,
                         action=lambda n=name: self._apply_profile(n),
                         back_after=True))
        items.append(MenuItem("-" * 16, enabled=False))
        items.append(MenuItem("Save current as...", action=self._save_profile_dialog,
                              back_after=True))
        items.append(MenuItem("Delete profile...", submenu=self._delete_submenu))
        return items

    def _delete_submenu(self):
        items = [MenuItem(n, action=lambda name=n: self._delete_profile(name),
                          back_after=True)
                 for n in list(self.config.profiles)]
        if not items:
            items.append(MenuItem("(no saved profiles)", enabled=False))
        return items

    # ── Appearance actions (used by menu) ─────────────────────────────────

    # ── Color themes (built-in + user custom) ─────────────────────────────

    def _builtin_theme_labels(self):
        return [theme.theme_label(k) for k in theme.THEME_ORDER]

    def _key_for_label(self, label):
        for k in theme.THEME_ORDER:
            if theme.theme_label(k) == label:
                return k
        return None

    def _migrate_themes(self):
        """Fold legacy config (a single custom_palette / theme key) into the
        custom_themes model."""
        cfg = self.config
        cp = cfg.custom_palette
        if (cfg.theme == "custom" and cp
                and all(k in cp for k in ("bg", "accent", "accent2", "text"))):
            cfg.custom_themes.setdefault("Custom", {
                "bg": list(cp["bg"]), "accent": list(cp["accent"]),
                "accent2": list(cp["accent2"]), "text": list(cp["text"]),
                "scanline": int(cfg.scanline_alpha),
                "crt": bool(cfg.crt_enabled), "vignette": bool(cfg.vignette_enabled)})
            cfg.theme = "Custom"

    def _resolve_initial_theme(self):
        t = self.config.theme
        if t in self.config.custom_themes or t in self._builtin_theme_labels():
            return t
        if t in theme.THEME_ORDER:          # legacy key → label
            return theme.theme_label(t)
        return theme.theme_label("blue")

    def _apply_theme_colors(self, ident):
        """Apply just the palette for `ident` (no config writes / rebuild)."""
        ct = self.config.custom_themes.get(ident)
        if ct:
            theme.set_custom_palette(ct["bg"], ct["accent"], ct["accent2"], ct["text"],
                                     chnum=ct.get("chnum", [40, 255, 90]))
        else:
            theme.apply_theme(self._key_for_label(ident) or "blue")

    def _apply_custom_theme_values(self, t):
        """Apply a custom theme's colors AND its CRT/vignette/scanline effects."""
        theme.set_custom_palette(t["bg"], t["accent"], t["accent2"], t["text"],
                                 chnum=t.get("chnum", [40, 255, 90]))
        self.config.scanline_alpha = int(t.get("scanline", self.config.scanline_alpha))
        self.config.crt_enabled = bool(t.get("crt", self.config.crt_enabled))
        self.config.vignette_enabled = bool(t.get("vignette", self.config.vignette_enabled))
        self.renderer._scanline_alpha = self.config.scanline_alpha
        self.renderer.crt_on = self.config.crt_enabled
        self.renderer.vignette_on = self.config.vignette_enabled
        self.renderer.set_scanline_alpha(self.config.scanline_alpha)

    def _select_theme(self, ident):
        ct = self.config.custom_themes.get(ident)
        if ct:
            self._apply_custom_theme_values(ct)
        else:
            theme.apply_theme(self._key_for_label(ident) or "blue")
        self.config.theme = ident
        self._active_theme = ident
        self.config.save()
        self.renderer.rebuild()
        self.renderer.menu.replace_page(self._theme_submenu())
        self.renderer.update()
        print(f"[cathode] Theme -> {ident}")

    def _theme_from_state(self, state):
        c = state["colors"]
        return {"bg": list(c["bg"]), "accent": list(c["accent"]),
                "accent2": list(c["accent2"]), "text": list(c["text"]),
                "chnum": list(c.get("chnum", [40, 255, 90])),
                "scanline": int(state["scanline"]),
                "crt": bool(state["crt"]), "vignette": bool(state["vignette"])}

    def _apply_font_key(self, key: str):
        if theme.set_font(key):
            self.config.font = key
            self.config.save()
            self.renderer.rebuild()
            self.renderer.menu.replace_page(self._font_submenu())
            self.renderer.update()

    def _apply_profile(self, name: str):
        prof = self.config.profiles.get(name) or self.BUILTIN_PROFILES.get(name)
        if not prof:
            return
        ptheme = prof.get("theme", "blue")
        cp = prof.get("custom_palette")
        if ptheme == "custom" and cp:
            theme.set_custom_palette(cp["bg"], cp["accent"], cp["accent2"], cp["text"])
            self.config.custom_palette = {k: list(v) for k, v in cp.items()}
        else:
            theme.apply_theme(ptheme)
        theme.set_font(prof.get("font", "vcr"))
        sa = int(prof.get("scanline_alpha", self.config.scanline_alpha))
        self._active_theme = (theme.theme_label(ptheme)
                              if ptheme in theme.THEME_ORDER else ptheme)
        self.config.theme = self._active_theme
        self.config.font = prof.get("font", self.config.font)
        self.config.scanline_alpha = sa
        self.renderer._scanline_alpha = sa
        # CRT / vignette toggles (older profiles may not have them — keep current)
        self.config.crt_enabled = bool(prof.get("crt", self.config.crt_enabled))
        self.config.vignette_enabled = bool(prof.get("vignette", self.config.vignette_enabled))
        self.renderer.crt_on = self.config.crt_enabled
        self.renderer.vignette_on = self.config.vignette_enabled
        # Remember a user profile as "active" so the editor's Save can update it.
        self._active_profile = name if name in self.config.profiles else None
        self.config.save()
        self.renderer.rebuild()
        self.renderer.update()
        print(f"[cathode] Applied profile: {name}")

    def _save_profile_dialog(self):
        name = self._osk_get("Profile name", "")
        if not name:
            return
        self.config.profiles[name] = {
            "theme": theme.current_theme(),
            "font": theme.current_font(),
            "scanline_alpha": int(self.config.scanline_alpha),
        }
        self.config.save()
        print(f"[cathode] Saved profile: {name}")

    def _delete_profile(self, name: str):
        if name in self.config.profiles:
            del self.config.profiles[name]
            self.config.save()
            print(f"[cathode] Deleted profile: {name}")

    # ── Custom theme editor ───────────────────────────────────────────────

    def _editor_state_from_current(self):
        """Seed the editor from the active theme's colors + effect settings."""
        ident = self._active_theme
        ct = self.config.custom_themes.get(ident)
        if ct:
            colors = {k: list(ct.get(k, [40, 255, 90]))
                      for k in ("bg", "accent", "accent2", "text", "chnum")}
        else:
            pal = theme.PALETTES.get(theme.current_theme(), theme.PALETTES["blue"])
            colors = {
                "bg":      list(pal["OSD_BG"][:3]),
                "accent":  list(pal["CYAN"][:3]),
                "accent2": list(pal["YELLOW"][:3]),
                "text":    list(pal["WHITE"][:3]),
                "chnum":   list(pal["CHANNEL_GREEN"][:3]),
            }
        return {"colors": colors,
                "scanline": int(self.config.scanline_alpha),
                "crt": bool(self.config.crt_enabled),
                "vignette": bool(self.config.vignette_enabled)}

    def _visual_snapshot(self):
        """Capture the full look state so the editor can revert on cancel."""
        import copy
        return {
            "active": self._active_theme,
            "theme": self.config.theme,
            "custom_themes": copy.deepcopy(self.config.custom_themes),
            "scanline": int(self.config.scanline_alpha),
            "crt": bool(self.config.crt_enabled),
            "vignette": bool(self.config.vignette_enabled),
        }

    def _apply_visual_state(self, s):
        """Re-apply a captured look snapshot to theme + renderer + config."""
        import copy
        self._active_theme = s["active"]
        self.config.theme = s["theme"]
        self.config.custom_themes = copy.deepcopy(s["custom_themes"])
        self.config.scanline_alpha = int(s["scanline"])
        self.config.crt_enabled = bool(s["crt"])
        self.config.vignette_enabled = bool(s["vignette"])
        ct = self.config.custom_themes.get(self._active_theme)
        if ct:
            theme.set_custom_palette(ct["bg"], ct["accent"], ct["accent2"], ct["text"],
                                     chnum=ct.get("chnum", [40, 255, 90]))
        else:
            theme.apply_theme(self._key_for_label(self._active_theme) or "blue")
        self.renderer.crt_on = self.config.crt_enabled
        self.renderer.vignette_on = self.config.vignette_enabled
        self.renderer.set_scanline_alpha(self.config.scanline_alpha)
        self.renderer.rebuild()
        self.renderer.mark_dirty()

    def _open_theme_editor(self):
        self.renderer.menu.close()
        # Snapshot so an un-saved exit reverts to exactly the current look.
        self._editor_revert = self._visual_snapshot()
        self._editor_saved = False
        self.renderer.editor.show(
            self._editor_state_from_current(),
            on_change=self._editor_changed,
            on_action=self._editor_action,
            on_close=self._editor_close,
        )
        self.renderer.update()

    def _editor_changed(self, state):
        """Live preview — rebind colors and flip effect flags without a heavy
        layer rebuild (this runs on an input handler thread)."""
        c = state["colors"]
        theme.set_custom_palette(c["bg"], c["accent"], c["accent2"], c["text"],
                                 chnum=c.get("chnum", [40, 255, 90]))
        self.renderer.crt_on = bool(state["crt"])
        self.renderer.vignette_on = bool(state["vignette"])
        new_alpha = max(0, min(255, int(state["scanline"])))
        if new_alpha != self.renderer._scanline_alpha:
            self.renderer.set_scanline_alpha(new_alpha)
        self.renderer.mark_dirty()

    def _editor_action(self, key: str):
        if key == "save_current":
            self._editor_save_current()
        elif key == "save_new":
            self._editor_save_new()

    def _reopen_theme_menu(self):
        """Close the editor and return to the Color Theme menu."""
        self.renderer.editor.close()
        self.renderer.rebuild()
        self.renderer.menu.open_with(self._theme_submenu(), title="Color Theme")
        self.renderer.update()

    def _editor_save_current(self):
        """Overwrite the currently selected theme's values, keeping its name,
        then return to the Color Theme menu."""
        state = self.renderer.editor.state()
        name = self._active_theme
        self.config.custom_themes[name] = self._theme_from_state(state)
        self.config.theme = name
        self._apply_custom_theme_values(self.config.custom_themes[name])
        self.config.save()
        self._editor_saved = True
        print(f"[cathode] Saved theme '{name}'")
        self._reopen_theme_menu()

    def _editor_save_new(self):
        """Prompt for a name, save a new theme into the Color Theme menu, then
        return to it."""
        state = self.renderer.editor.state()
        name = self._osk_get("New theme name", "")
        if not name:
            return
        self.config.custom_themes[name] = self._theme_from_state(state)
        self.config.theme = name
        self._active_theme = name
        self._apply_custom_theme_values(self.config.custom_themes[name])
        self.config.save()
        self._editor_saved = True
        print(f"[cathode] Saved new theme '{name}'")
        self._reopen_theme_menu()

    def _editor_close(self):
        """Editor dismissed (Close row, X button, Esc, or gamepad back). Revert
        to the pre-editor look unless the user saved."""
        if not getattr(self, "_editor_saved", True):
            self._apply_visual_state(self._editor_revert)
        self.renderer.update()

