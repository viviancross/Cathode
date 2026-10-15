"""What MENU opens: the box's menu tree. Settings apply as they change and
are saved straight away."""

from . import autostart, palette, remote as R
from .screens.menu import Item, Keyboard, Menu

SKINS = [("classic", "Cathode Classic")]
FONTS = [("vcr", "VCR OSD Mono"), ("ibm", "IBM VGA"), ("vt220", "Glass TTY VT220"),
         ("pixelop", "Pixel Operator"), ("vt323", "VT323"), ("jersey", "Jersey 10")]


def _cycle(options, current, delta):
    keys = [k for k, _ in options]
    i = keys.index(current) if current in keys else 0
    return keys[(i + delta) % len(keys)]


def _label(options, key):
    return dict(options).get(key, key)


def open_main(app):
    app.push(Menu(app, "MAIN MENU", main_items(app)))


def open_welcome(app):
    """First run: nothing to watch yet."""
    def setup():
        def added(entry):
            app.config.setup_done = True
            app.config.save()
            from .screens.boot import Boot
            app.push(Boot(app))
        add_playlist(app, on_added=added)
    app.push(Menu(app, "WELCOME TO CATHODE", [
        Item("Set up your channels", setup),
        Item("Picture & Style", submenu=lambda: style_items(app)),
        Item("Exit Cathode", app.quit, close=True),
    ]))


def main_items(app):
    from .screens.guide import Guide

    def guide(cat="All"):
        def go():
            if app.channels:
                app.push(Guide(app, category=cat))
        return go
    return [
        Item("Program Guide", guide(), close=True, enabled=bool(app.channels)),
        Item("Themes & Genres", submenu=lambda: [
            Item(c, guide(c), close=True) for c in app.categories() if c not in ("All", "Favorites")
        ] or [Item("(no genres in this lineup)", enabled=False)], enabled=bool(app.channels)),
        Item("Favorites", guide("Favorites"), close=True, enabled=bool(app.channels)),
        Item("Settings", submenu=lambda: settings_items(app)),
        Item("Exit Cathode", app.quit, close=True),
    ]


def settings_items(app):
    return [
        Item("Picture & Style", submenu=lambda: style_items(app)),
        Item("Channels", submenu=lambda: channel_items(app)),
        Item("Display", submenu=lambda: display_items(app)),
        Item("System", submenu=lambda: system_items(app)),
    ]


# ── Picture & style ───────────────────────────────────────────────────────

def style_items(app):
    cfg = app.config

    def set_and(fn):
        def run(d):
            fn(d)
            cfg.save()
            app.skin.reload()
            app.invalidate()
        return run

    themes = [(k, palette.THEME_LABELS[k]) for k in palette.THEME_ORDER]
    return [
        Item("Skin", value=lambda: _label(SKINS, cfg.skin),
             adjust=lambda d: app.set_skin(_cycle(SKINS, cfg.skin, d))),
        Item("Color theme", value=lambda: _label(themes, cfg.theme),
             adjust=set_and(lambda d: setattr(cfg, "theme", _cycle(themes, cfg.theme, d)))),
        Item("Font", value=lambda: _label(FONTS, cfg.font),
             adjust=set_and(lambda d: setattr(cfg, "font", _cycle(FONTS, cfg.font, d)))),
        Item("Scanlines", value=lambda: "Off" if not cfg.crt_enabled else f"{cfg.scanline_alpha * 100 // 115}%",
             adjust=set_and(lambda d: _scanlines(cfg, d))),
        Item("Vignette", value=lambda: "On" if cfg.vignette_enabled else "Off",
             adjust=set_and(lambda d: setattr(cfg, "vignette_enabled", not cfg.vignette_enabled))),
        Item("Motion", value=lambda: "On" if cfg.motion_enabled else "Off",
             adjust=set_and(lambda d: setattr(cfg, "motion_enabled", not cfg.motion_enabled))),
    ]


def _scanlines(cfg, d):
    """0 (off) to 115 in steps; 40 is the default."""
    level = cfg.scanline_alpha if cfg.crt_enabled else 0
    level = max(0, min(115, level + 15 * d))
    cfg.crt_enabled = level > 0
    if level:
        cfg.scanline_alpha = level


# ── Channels ──────────────────────────────────────────────────────────────

def channel_items(app):
    cfg = app.config
    items = []
    for pl in cfg.playlists:
        active = pl.get("playlist_url") == cfg.playlist_url
        items.append(Item(("> " if active else "  ") + pl.get("name", "Playlist"),
                          submenu=lambda pl=pl: playlist_items(app, pl)))
    items.append(Item("Add a playlist...", lambda: add_playlist(app)))
    if cfg.epg_url:
        items.append(Item("Reload the guide now", lambda: (app.load_epg(), app.toast("Loading the guide...")),
                          close=True))
    return items


def playlist_items(app, pl):
    def delete():
        app.config.playlists.remove(pl)
        app.config.save()
        app.toast(f"Deleted {pl.get('name', 'playlist')}")
        _reopen(app, channel_items(app))
    return [
        Item("Watch this playlist", lambda: app.switch_playlist(pl), close=True),
        Item("Delete it", delete),
    ]


def _reopen(app, items):
    """Back out of a submenu that just changed what its parent lists."""
    m = app.top()
    if isinstance(m, Menu):
        m.back()
        m.refresh(items)


def add_playlist(app, on_added=None):
    """Three prompts: a name, the M3U address, an optional guide address."""
    entry = {}

    def got_name(name):
        if name is None:
            return
        entry["name"] = name or "My Channels"
        app.push(Keyboard(app, "Playlist address (M3U URL or file)", got_url,
                          hint="Paste with Ctrl+V"))

    def got_url(url):
        if not url:
            return
        entry["playlist_url"] = url
        app.push(Keyboard(app, "Guide address (XMLTV, optional)", got_epg,
                          hint="Leave empty and press DONE to skip"))

    def got_epg(epg):
        if epg is None:
            return
        entry["epg_url"] = epg
        app.config.playlists.append(entry)
        app.config.save()
        while isinstance(app.top(), Menu):
            app.pop()
        app.switch_playlist(entry)
        if on_added:
            on_added(entry)
    app.push(Keyboard(app, "Name this playlist", got_name, initial="My Channels"))


# ── Display ───────────────────────────────────────────────────────────────

def display_items(app):
    cfg = app.config
    n = app.gfx.displays()
    items = [
        Item("Full screen", value=lambda: "On" if app.fullscreen else "Off",
             adjust=lambda d: app.toggle_fullscreen()),
        Item("Start full screen", value=lambda: "Yes" if cfg.start_fullscreen else "No",
             adjust=lambda d: (setattr(cfg, "start_fullscreen", not cfg.start_fullscreen), cfg.save())),
    ]
    if n > 1:
        items.append(Item("Screen", value=lambda: f"{cfg.display + 1} of {n}",
                          adjust=lambda d: app.move_to_display((cfg.display + d) % n)))
    if autostart.supported():
        items.append(Item("Start with the computer", value=lambda: "Yes" if autostart.enabled() else "No",
                          adjust=lambda d: _toggle_autostart(app)))
    return items


def _toggle_autostart(app):
    try:
        autostart.set_enabled(not autostart.enabled())
    except OSError as e:
        app.toast(f"Couldn't change that: {e}")


# ── System ────────────────────────────────────────────────────────────────

def system_items(app):
    from . import __version__
    from .screens.diagnostics import Diagnostics
    return [
        Item("Diagnostics", lambda: app.push(Diagnostics(app)), close=True),
        Item(f"Cathode {__version__}", enabled=False),
    ]


def handles_menu_button(app, action) -> bool:
    """MENU from anywhere that doesn't use it opens the main menu."""
    if action == R.MENU and not isinstance(app.top(), (Menu, Keyboard)):
        open_main(app)
        return True
    return False
