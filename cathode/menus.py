"""What MENU opens: the box's menu tree. Settings apply as they change and
are saved straight away."""

from . import autostart, remote as R
from .screens.menu import DESCRIPTIONS, Item, Keyboard, Menu


def _cycle(options, current, delta):
    keys = [k for k, _ in options]
    i = keys.index(current) if current in keys else 0
    return keys[(i + delta) % len(keys)]


def _label(options, key):
    return dict(options).get(key, key)


def open_main(app):
    app.push(Menu(app, "MAIN MENU", main_items(app)))


# Beside each box's name on the wizard's first page, and what it is.
LOOK_NOTES = {"classic": "Retro CRT", "indirect": "1997, 4:3", "indirect_hd": "2007, HD",
              "plate": "2005, 4:3", "plate_hd": "2007, HD"}
LOOK_HELP = {"classic": "Cathode's own look: a retro CRT, every theme.",
             "indirect": "A 1997 satellite box: purple pages, 4:3.",
             "indirect_hd": "A 2007 HD satellite box: the blue guide.",
             "plate": "A 2005 dish box: grey pages, blue pills, 4:3.",
             "plate_hd": "A 2007 HD dish box: teal pages, gold cursor."}

DESCRIPTIONS.update({
    # Main Menu
    "Program Guide": "Show the on-screen programming schedule.",
    "Themes & Genres": "Channels grouped by what they show.",
    "Favorites": "The guide with just your favorite channels.",
    "On Demand": "Movies and shows from your Plex server.",
    "My Recordings": "What you've downloaded to watch here.",
    "Button Guide": "What every button does, on this box.",
    "Settings": "Picture, channels, subtitles, buttons and more.",
    "Exit Cathode": "Close Cathode.",
    # Settings
    "Picture & Style": "The box, its colors and lettering, screen effects.",
    "Channels": "Your playlists and their guides.",
    "Display": "Full screen, and which screen to use.",
    "Remote control": "Your remote, and which button does what.",
    "System": "Diagnostics, sound, weather, updates.",
    # Picture & Style
    "Skin": "The box Cathode looks and works like.",
    "Color theme": "Original is the box's own colors.",
    "Font": "The lettering on every screen.",
    "Scanlines": "A tube's lines over the picture and menus.",
    "Vignette": "Darker corners, like a tube TV.",
    "Picture format": "How the video fills the screen.",
    "Wide screen": "Pillarbox keeps 4:3; Stretch fills the screen.",
    "Motion": "Slides and fades. Off makes changes instant.",
    "Edit colors": "Your own version of this theme.",
    # Display
    "Full screen": "Fill the whole screen with Cathode.",
    "Start full screen": "Open in full screen next time.",
    "Screen": "Which screen Cathode shows on.",
    "Start with the computer": "Open Cathode when you sign in.",
    # Remote control
    "Remote": "Name the buttons as your remote prints them.",
    "Keyboard keys": "Change which key does what.",
    "Controller buttons": "Change which pad button does what.",
    "Reset to defaults": "Put every button back as it came.",
    # System
    "Diagnostics": "Signal, stream and picture details.",
    "Audio output": "Which speakers or HDMI the sound uses.",
    "Weather": "Local weather in the guide's header.",
    "Check for updates": "See if there's a newer Cathode.",
    "Check at start-up": "Look for a newer Cathode each time it opens.",
    "Start-up screen": "The box's start-up screen when Cathode opens.",
    "Screensaver": "A moving logo when nothing's on screen for a while.",
    # Subtitles
    "Track": "Which subtitles to show.",
    "Size": "How big subtitles are.",
    "Find subtitles": "Search for subtitles through your Plex server.",
    "Search language": "The language Find subtitles looks for.",
    "Auto-sync": "Plex lines subtitles up with the speech.",
    # On Demand
    "View": "A list, or a wall of posters.",
    "Quality": "How much Plex sends: lower if it stutters.",
    "Libraries": "Which Plex libraries On Demand shows.",
    "Who's watching": "Switch to another Plex Home user.",
    "Unlink Plex account": "Sign this Cathode out of Plex.",
    # The welcome
    "Set up your channels": "Type in the channel list link (M3U) your IPTV provider gave you.",
    "Playlist address": "Where the channels come from: your provider's M3U link, or a file.",
    "Guide address": "Where the listings come from: your provider's XMLTV link. Optional.",
    "Change the look": "Pick the box and its colors again.",
})


def open_welcome(app):
    """First run, as a wizard: 1/3 the box, 2/3 its colours, 3/3 the
    channels. The look pages redraw in whatever the cursor is on; BACK steps
    back a page. Once the look is chosen, coming back here (MENU with no
    channels yet) goes straight to the channels."""
    from .skins import skin_classes
    m = Menu(app, "", [])

    def setup():
        def added(entry):
            app.config.setup_done = True
            app.config.save()
            from .screens.boot import Boot
            app.push(Boot(app))
        add_playlist(app, on_added=added, first_run=True)

    def channels(title, extra=()):
        return [title, [Item("Set up your channels", setup), *extra,
                        Item("Exit Cathode", submenu=lambda: _confirm(app, "Exit Cathode", app.quit,
                                                                       "Keep going", close=True))], 0]

    def colours():
        skin = app.skin
        choices = [(k, label) for k, label in skin.theme_choices() if k != "custom"]

        def show(k):
            skin.set_theme_key(k)
            skin.reload()
            app.invalidate()

        def chosen(k):
            show(k)
            app.config.look_chosen = True
            app.config.save()
            m.pages.append(channels("3/3 YOUR CHANNELS"))
        keys = [k for k, _ in choices]
        m.open("2/3 CHOOSE COLORS", [Item(label, lambda k=k: chosen(k), preview=lambda k=k: show(k),
                                          help="The box's own colors, as it looked. Recommended." if k == "native"
                                          else "Cathode 3's colors, kept readable on this box.")
                                     for k, label in choices])
        m.cursor = keys.index(skin.theme_key()) if skin.theme_key() in keys else 0

    def restart():
        m.close()
        app.config.look_chosen = False
        open_welcome(app)

    if app.config.look_chosen:
        m.pages = [channels("WELCOME TO CATHODE", [Item("Change the look", restart)])]
    else:
        names = list(skin_classes())
        boxes = [Item(cls.label, lambda k=k: (app.set_skin(k), colours()), value=lambda k=k: LOOK_NOTES.get(k, ""),
                      preview=lambda k=k: app.set_skin(k), help=LOOK_HELP.get(k, ""))
                 for k, cls in skin_classes().items()]
        m.pages = [["1/3 CHOOSE YOUR BOX", boxes, names.index(app.config.skin) if app.config.skin in names else 0]]
    app.push(m)


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
        Item("On Demand", lambda: open_ondemand(app), close=True),
        Item("My Recordings", lambda: open_ondemand(app, recordings=True), close=True),
        Item("Settings", submenu=lambda: settings_items(app)),
        Item("Button Guide", submenu=lambda: button_guide_items(app)),
        Item("Exit Cathode", submenu=lambda: _confirm(app, "Exit Cathode", app.quit, "Keep watching", close=True)),
    ]


def _confirm(app, yes: str, do, keep: str = "Keep it", close: bool = False):
    """The page before something that can't be undone, as the recording
    delete has: the safe choice first, so SELECT twice doesn't do it."""
    act = do if close else (lambda: (app.top().back(), do()))
    return [Item(keep, lambda: app.top().back()), Item(yes, act, close=close)]


def settings_items(app):
    return [
        Item("Picture & Style", submenu=lambda: style_items(app)),
        Item("Channels", submenu=lambda: channel_items(app)),
        Item("Display", submenu=lambda: display_items(app)),
        Item("Subtitles", submenu=lambda: subtitle_items(app), help="Subtitle language, size and look."),
        Item("On Demand", submenu=lambda: ondemand_settings(app), help="Plex quality, libraries and your account."),
        Item("Remote control", submenu=lambda: remote_items(app)),
        Item("System", submenu=lambda: system_items(app)),
    ]


# ── On Demand ─────────────────────────────────────────────────────────────

def open_ondemand(app, recordings=False):
    from .screens.ondemand import OnDemandScreen, RECORDINGS, LIBRARIES
    app.push(OnDemandScreen(app, RECORDINGS if recordings else LIBRARIES))


def ondemand_settings(app):
    from . import plex
    cfg = app.config
    od = app.ondemand
    if not od.signed_in:
        return [Item("Not signed in: open On Demand to link your Plex account", enabled=False)]

    def toggle_library(key):
        hidden = cfg.plex_hidden_libraries
        hidden.remove(key) if key in hidden else hidden.append(key)
        cfg.save()

    def set_server(sid):
        cfg.plex_server_id, cfg.plex_server = sid, ""
        cfg.save()
        od.reset()
        app.toast("Server changed: reopen On Demand")

    def change_user():
        from .screens.ondemand import OnDemandScreen
        while app.top().name == "menu":
            app.pop()
        screen = OnDemandScreen(app)
        app.push(screen)
        screen.choose_user()

    def unlink():
        od.unlink()
        app.toast("Plex account unlinked")
    items = [
        Item("View", value=lambda: "Poster wall" if cfg.ppv_view == "wall" else "List",
             adjust=lambda d: (setattr(cfg, "ppv_view", "list" if cfg.ppv_view == "wall" else "wall"),
                               cfg.save())),
        Item("Quality", value=lambda: cfg.plex_quality,
             adjust=lambda d: (setattr(cfg, "plex_quality",
                                       _cycle([(q, q) for q in plex.QUALITY_OPTIONS], cfg.plex_quality, d)),
                               cfg.save())),
        Item("Libraries", submenu=lambda: [
            Item(s["title"], value=lambda k=s["key"]: "Hidden" if k in cfg.plex_hidden_libraries else "Shown",
                 adjust=lambda d, k=s["key"]: toggle_library(k))
            for s in cfg.plex_sections] or [Item("(open On Demand first)", enabled=False)]),
    ]
    if len(cfg.plex_servers) > 1:
        items.append(Item("Server", submenu=lambda: [
            Item(("> " if s["id"] == cfg.plex_server_id else "  ") + s["title"]
                 + ("" if s.get("owned") else " (shared)"), (lambda i=s["id"]: set_server(i)), close=True)
            for s in cfg.plex_servers]))
    items += [
        Item("Who's watching", change_user, value=lambda: cfg.plex_user_name or "Account"),
        Item("Unlink Plex account", submenu=lambda: _confirm(app, "Unlink it", unlink, "Keep it linked", close=True)),
    ]
    return items


def ondemand_menu(app, screen):
    """MENU inside On Demand."""
    lvl = screen.level
    items = []
    if lvl and lvl.get("loader") and lvl.get("sortable"):
        items.append(Item("Sort", screen.sort_menu, close=True))
    items += [
        Item("View", value=lambda: "Poster wall" if app.config.ppv_view == "wall" else "List",
             adjust=lambda d: (setattr(app.config, "ppv_view",
                                       "list" if app.config.ppv_view == "wall" else "wall"),
                               app.config.save())),
        Item(f"Play queue ({len(app.ondemand.queue.items)})", submenu=lambda: queue_items(app)),
        Item("On Demand settings", submenu=lambda: ondemand_settings(app)),
        Item("Back to TV", screen.leave, close=True),
    ]
    app.push(Menu(app, "ON DEMAND", items))


def queue_items(app):
    from .screens.playback import Playback
    q = app.ondemand.queue
    if not q.items:
        return [Item("(empty: use + QUEUE on an info page)", enabled=False)]
    playing = app.find(Playback)

    def entry(i):
        def play():
            if playing:
                playing.od.report(playing.rk, playing.pos, playing.dur, "stopped")
            app.ondemand.play_queue_at(i)

        def move(d):
            j = q.move(i, d)
            _reopen(app, queue_items(app))
            app.top().cursor = j

        def remove():
            q.remove(i)
            _reopen(app, queue_items(app))
        return [Item(f"#{i + 1} of {len(q.items)}", enabled=False),
                Item("Play now", play, close=True),
                Item("Move up", lambda: move(-1), enabled=i > 0),
                Item("Move down", lambda: move(1), enabled=i < len(q.items) - 1),
                Item("Remove", remove)]
    items = [Item(("> " if i == q.pos and playing else "  ") + e["title"],
                  submenu=lambda i=i: entry(i)) for i, e in enumerate(q.items)]

    def clear():
        q.clear()
        app.top().refresh(queue_items(app))
    items.append(Item("Clear the queue", clear))
    return items


SUB_SIZES = [(28, "Small"), (38, "Medium"), (52, "Large"), (68, "Extra large")]
SUB_COLORS = [("#FFFFFFFF", "White"), ("#FFFFFF00", "Yellow"), ("#FF00FFFF", "Cyan"),
              ("#FF00FF00", "Green")]
SUB_BACKS = [("", "None"), ("#96000000", "Shaded"), ("#FF000000", "Black")]
SUB_LANGS = [("en", "English"), ("es", "Spanish"), ("fr", "French"), ("de", "German"), ("it", "Italian"),
             ("pt", "Portuguese"), ("nl", "Dutch"), ("sv", "Swedish"), ("da", "Danish"), ("no", "Norwegian"),
             ("fi", "Finnish"), ("pl", "Polish"), ("ru", "Russian"), ("el", "Greek"), ("tr", "Turkish"),
             ("ar", "Arabic"), ("he", "Hebrew"), ("hi", "Hindi"), ("ja", "Japanese"), ("ko", "Korean"),
             ("zh", "Chinese")]


def track_items(app, kind):
    """The playing stream's audio or subtitle tracks; picking a subtitle
    track (or Off) also sets the subtitles setting."""
    v = app.video

    def pick(tid):
        v.set_track(kind, tid)
        if kind == "sub":
            app.config.subtitles = tid is not None
            app.config.save()
        app.top().refresh(track_items(app, kind))
    rows = [Item(("> " if t["selected"] else "  ") + t["name"], (lambda i=t["id"]: pick(i)))
            for t in v.tracks(kind)]
    if kind == "sub":
        if not rows:
            return [Item("(none on this stream)", enabled=False)]
        off = not any(t["selected"] for t in v.tracks("sub"))
        rows.insert(0, Item(("> " if off else "  ") + "Off", lambda: pick(None)))
    return rows or [Item("(none)", enabled=False)]


def subtitle_items(app):
    """Subtitles for live TV and On Demand alike: on or off for everything
    you watch, this stream's track, and how they look."""
    v, cfg = app.video, app.config

    def toggle(d):
        cfg.subtitles = not cfg.subtitles
        cfg.save()
        v.apply_subtitles(cfg.subtitles)

    def style(label, attr, options, apply):
        def adj(d):
            setattr(cfg, attr, _cycle(options, getattr(cfg, attr), d))
            cfg.save()
            apply(getattr(cfg, attr))
        return Item(label, value=lambda: _label(options, getattr(cfg, attr)), adjust=adj)
    fonts = [("", "Default")] + _subtitle_fonts()
    rows = [
        Item("Subtitles", value=lambda: "On" if cfg.subtitles else "Off", adjust=toggle,
             help="Show subtitles when there are any."),
        Item("Track", submenu=lambda: track_items(app, "sub")),
        style("Size", "sub_size", SUB_SIZES, lambda s: v.sub_style(size=s)),
        style("Color", "sub_color", SUB_COLORS, lambda c: v.sub_style(color=c)),
        style("Background", "sub_back", SUB_BACKS, lambda b: v.sub_style(back=b)),
        style("Font", "sub_font", fonts, lambda f: v.sub_style(font=f or "sans-serif")),
    ]
    from .screens.playback import Playback
    pb = app.find(Playback)
    if pb:                  # On Demand: the Plex server can look more up
        def sync(d):
            cfg.sub_auto_sync = not cfg.sub_auto_sync
            cfg.save()
            pb.reload_subs()
        rows[2:2] = [Item("Find subtitles", submenu=lambda: find_subtitle_items(app, pb)),
                     style("Search language", "sub_search_lang", SUB_LANGS, lambda _: None),
                     Item("Auto-sync", value=lambda: "On" if cfg.sub_auto_sync else "Off", adjust=sync)]
    return rows


def find_subtitle_items(app, pb):
    """What the Plex server can fetch for the title playing (its own
    OpenSubtitles link), in the search language. Picking one has the server
    fetch it and keep it with the title, then shows it."""
    import time
    from .plex import PlexError
    from .screens.playback import Playback
    od, cfg = app.ondemand, app.config
    lang = _label(SUB_LANGS, cfg.sub_search_lang)
    rows = [Item(f"Searching for {lang} subtitles...", enabled=False)]

    def show(items):
        m = app.top()
        if isinstance(m, Menu) and m.items is rows:
            m.refresh(items)
            app.invalidate()

    def fetch(r, rk=pb.rk):
        app.toast("Fetching subtitles...")

        def work():
            c = od.client()
            had = {s["url"] for s in c.subtitle_files(rk)}
            c.download_subtitle(rk, r["key"])
            for _ in range(30):             # the server fetches in the background
                time.sleep(1)
                new = [s for s in c.subtitle_files(rk) if s["url"] not in had]
                if new:
                    return new[0]
            raise PlexError("The server hasn't finished fetching them. Try again in a moment.")

        def done(sub):
            if app.find(Playback) is pb and pb.rk == rk:
                pb.subs.append(sub)
                app.video.add_subtitle(pb.sub_url(sub), sub["title"], sub["lang"], select=True)
                cfg.subtitles = True
                cfg.save()
            app.toast(f"Subtitles added: {sub['title'] or lang}")
        od.run(work, done, lambda msg: app.toast(f"Couldn't get subtitles. {msg}"))

    def found(results):
        show([Item(r["title"] + ("  (SDH)" if r["hi"] else ""), (lambda r=r: fetch(r)), close=True,
                   value=(lambda: "Exact") if r["exact"] else None) for r in results]
             or [Item(f"No {lang} subtitles found", enabled=False)])

    od.run(lambda: od.client().search_subtitles(pb.rk, cfg.sub_search_lang), found,
           lambda msg: show([Item(f"Couldn't search. {msg}", enabled=False)]))
    return rows


def open_options(app):
    """Live TV's Options pop-up (the OPTIONS key): the favourite, the picture
    format, subtitles and On Demand, the things a remote or a pad may have no
    button for."""
    from .screens.menu import Options
    from .video import format_label
    live, v, cfg = app.live, app.video, app.config
    ch = live.channel
    fav = ch is not None and ch.number in cfg.favorites

    def subs():
        tracks = v.tracks("sub")
        return next((t["name"] for t in tracks if t["selected"]), "Off" if tracks else "None")
    app.push(Options(app, "Options", [
        Item("Remove from Favorites" if fav else "Add to Favorites", lambda: app.toggle_favorite(ch), close=True),
        Item("Picture format", lambda: app.cycle_format(1), value=lambda: format_label(cfg.picture_format),
             adjust=app.cycle_format),
        Item("Subtitles", app.cycle_subtitles, value=subs, adjust=lambda d: app.cycle_subtitles(),
             help="Step through this channel's subtitles."),
        Item("On Demand", lambda: open_ondemand(app), close=True),
    ]))


def playback_menu(app, pb):
    app.push(Menu(app, "PLAYING", [
        Item("Audio track", submenu=lambda: track_items(app, "audio")),
        Item("Subtitles", submenu=lambda: subtitle_items(app)),
        Item(f"Play queue ({len(app.ondemand.queue.items)})", submenu=lambda: queue_items(app)),
        Item("Stop", pb.stop, close=True),
    ]))


# Files whose family name isn't what they're called (the CC font is a Space Mono build).
_FONT_LABELS = {"Closed_Caption.ttf": "Closed Caption"}


def _subtitle_fonts():
    """(family name for mpv, label) for each bundled font, once per family."""
    import os
    import pygame
    from . import paths
    d = paths.asset("fonts")
    out = {}
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f.lower().endswith((".ttf", ".otf")):
            try:
                name = pygame.font.Font(os.path.join(d, f), 12).name
            except (pygame.error, AttributeError):
                continue
            if name and name not in out:
                out[name] = _FONT_LABELS.get(f, name)
    return list(out.items())


# ── Remote control ────────────────────────────────────────────────────────

_PRETTY = {R.CH_UP: "Channel up", R.CH_DOWN: "Channel down", R.PAGE_UP: "Page up",
           R.PAGE_DOWN: "Page down", R.PREV: "Previous channel", R.FAV: "Favorite",
           R.VOL_UP: "Volume up", R.VOL_DOWN: "Volume down", R.REW: "Rewind",
           R.FF: "Fast forward", R.SKIP: "Back to live", R.FULLSCREEN: "Full screen",
           R.THEMES: "Themes (genres)", R.LIST: "My Recordings", R.FORMAT: "Picture format", R.SUBTITLE: "Subtitles"}


def _format_label(key):
    from .video import format_label
    return format_label(key)


def _pretty(action):
    return _PRETTY.get(action, action.replace("_", " ").title())


def remote_items(app):
    def reset():
        app.config.key_bindings, app.config.gamepad_bindings = {}, {}
        app.config.save()
        app.reload_remote()
        app.toast("Remote buttons reset")
    remotes = [(k, v[0]) for k, v in R.REMOTES.items()]

    def set_remote(d):
        app.config.remote = _cycle(remotes, app.config.remote, d)
        app.config.save()
        app.invalidate()
    return [
        Item("Button guide", submenu=lambda: button_guide_items(app), help="What every button does, on this box."),
        Item("Remote", value=lambda: _label(remotes, app.config.remote), adjust=set_remote),
        Item("Keyboard keys", submenu=lambda: binding_items(app, "key")),
        Item("Controller buttons", submenu=lambda: binding_items(app, "pad")),
        Item("Reset to defaults", submenu=lambda: _confirm(app, "Reset every button", reset, "Keep my buttons")),
    ]


GUIDE_ROWS = [(R.GUIDE, "Program guide"), (R.INFO, "Channel banner"), (R.SELECT, "Banner, then play buttons"),
              (R.OPTIONS, "Options"), (R.MENU, "Menu"), (R.BACK, "Back"), (R.EXIT, "Close"),
              (R.PREV, "Last channel"), (R.BROWSE, "Browse"), (R.FAV, "Favorite"), (R.LIST, "My Recordings"),
              (R.FORMAT, "Picture format"), (R.SUBTITLE, "Subtitles")]


def button_guide_items(app):
    """What each button does, named as the remote, pad or keyboard in use
    names it."""
    return [Item(what, value=lambda a=a: app.press_hint(a)) for a, what in GUIDE_ROWS]


def open_button_guide(app):
    app.push(Menu(app, "BUTTON GUIDE", button_guide_items(app)))


def binding_items(app, kind):
    from .screens.capture import Capture
    store = app.config.key_bindings if kind == "key" else app.config.gamepad_bindings

    def rebind(action):
        def got(name):
            if name:
                store[action] = name
                app.config.save()
                app.reload_remote()
                app.toast(f"{_pretty(action)}: {name}")
        what = "key" if kind == "key" else "controller button"
        app.push(Capture(app, f"Press the {what} for {_pretty(action)}  (Esc cancels)", kind, got))
    current = app.remote.key_for if kind == "key" else app.remote.pad_for
    return [Item(_pretty(a), (lambda a=a: rebind(a)), value=lambda a=a: current(a))
            for a in R.BINDABLE]


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

    from .skins import FONTS, skin_classes
    skins = [(k, cls.label) for k, cls in skin_classes().items()]
    fonts = [(k, v[2]) for k, v in FONTS.items()]

    def skin():
        return app.skin     # changes when the Skin row does

    def set_skin(d):
        app.set_skin(_cycle(skins, cfg.skin, d))
        m = app.top()
        if isinstance(m, Menu):
            m.refresh(style_items(app))     # the Wide screen row comes and goes with a 4:3 skin

    cw, ch = type(app.skin).canvas
    wide = [Item("Wide screen", value=lambda: "Stretch" if cfg.stretch_43 else "Pillarbox",
                 adjust=set_and(lambda d: setattr(cfg, "stretch_43", not cfg.stretch_43)))] if cw * 3 == ch * 4 else []
    return [
        Item("Skin", value=lambda: _label(skins, cfg.skin), adjust=set_skin),
        Item("Color theme", value=lambda: _label(skin().theme_choices(), skin().theme_key()),
             adjust=set_and(lambda d: skin().set_theme_key(
                 _cycle(skin().theme_choices(), skin().theme_key(), d)))),
        Item("Font", value=lambda: _label(fonts, skin().font_key()),
             adjust=set_and(lambda d: skin().set_font_key(_cycle(fonts, skin().font_key(), d)))),
        Item("Scanlines", value=lambda: "Off" if not cfg.crt_enabled else f"{cfg.scanline_alpha * 100 // 115}%",
             adjust=set_and(lambda d: _scanlines(cfg, d))),
        Item("Vignette", value=lambda: "On" if cfg.vignette_enabled else "Off",
             adjust=set_and(lambda d: setattr(cfg, "vignette_enabled", not cfg.vignette_enabled))),
        Item("Picture format", value=lambda: _format_label(cfg.picture_format),
             adjust=lambda d: app.cycle_format(d)),
        *wide,
        Item("Motion", value=lambda: "On" if cfg.motion_enabled else "Off",
             adjust=set_and(lambda d: setattr(cfg, "motion_enabled", not cfg.motion_enabled))),
        Item("Edit colors", submenu=lambda: color_items(app)),
    ]


COLOR_ROLES = [("bg", "Background"), ("accent", "Accent"), ("accent2", "Highlight"),
               ("text", "Text"), ("chnum", "Channel number")]


def color_items(app):
    """The theme editor: each base colour's red, green and blue, live. The
    rest of the palette is derived (and contrast-solved) from these."""
    cfg, skin = app.config, app.skin
    if skin.theme_key() != "custom" or not skin.custom_base():
        skin.set_custom_base(skin.native_base())    # start from the look you had
        skin.set_theme_key("custom")
        cfg.save()
        skin.reload()

    def channel(role, k):
        def adj(d):
            base = skin.custom_base()
            rgb = list(base[role])
            rgb[k] = max(0, min(255, rgb[k] + 8 * d))
            base[role] = rgb
            cfg.save()
            skin.reload()
            app.invalidate()
        return adj
    items = []
    for role, label in COLOR_ROLES:
        for k, ch in enumerate("RGB"):
            items.append(Item(f"{label} {ch}", value=lambda r=role, k=k: str(skin.custom_base()[r][k]),
                              adjust=channel(role, k)))

    def reset():
        skin.set_theme_key("native" if "native" in dict(skin.theme_choices()) else "blue")
        skin.set_custom_base({})
        cfg.save()
        skin.reload()
        _reopen(app, style_items(app))
    items.append(Item("Back to the skin's own colors", reset))
    return items


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


def _bare(url):
    """Just the http:// the keyboard starts with: nothing typed."""
    return "" if (url or "").strip().lower() in ("http://", "https://") else (url or "")


def _short(url):
    """An address short enough for a menu value."""
    s = (url or "").split("://", 1)[-1]
    return "None" if not s else s if len(s) <= 26 else f"{s[:13]}...{s[-10:]}"


def _check_playlist(app, url, done):
    """Fetch the playlist off the UI thread; done(channel count, error text)."""
    import threading
    from . import playlist as m3u
    from .app import load_error_text

    def work():
        try:
            n, err = len(m3u.load(url, user_agent=app.config.user_agent)), ""
        except Exception as e:
            n, err = 0, load_error_text(e)
        app.post(done, n, err)
    threading.Thread(target=work, daemon=True).start()


PLAYLIST_HINT = "Your IPTV provider's channel list link (M3U), or a playlist file."
GUIDE_HINT = "Your provider's TV guide link (XMLTV). Done as it is skips."


def playlist_items(app, pl):
    def edit(key, prompt, hint):
        def got(url):
            if url is None or (key == "playlist_url" and not _bare(url)):
                return
            active = pl.get("playlist_url") == app.config.playlist_url
            pl[key] = _bare(url)
            app.config.save()
            if active:                  # in use: load it again from the new address
                app.switch_playlist(pl)
            app.toast("Saved.")
        app.push(Keyboard(app, prompt, got, initial=pl.get(key, ""), url=True, hint=hint))

    def delete():
        app.config.playlists.remove(pl)
        app.config.save()
        app.toast(f"Deleted {pl.get('name', 'playlist')}")
        _reopen(app, channel_items(app))
    def rename():
        def got(name):
            if name:
                pl["name"] = name
                app.config.save()
                app.toast(f"Renamed to {name}")
                _reopen(app, channel_items(app))
        app.push(Keyboard(app, "Rename this playlist", got, initial=pl.get("name", "")))
    return [
        Item("Watch this playlist", lambda: app.switch_playlist(pl), close=True),
        Item("Playlist address", lambda: edit("playlist_url", "Playlist address", PLAYLIST_HINT),
             value=lambda: _short(pl.get("playlist_url", ""))),
        Item("Guide address", lambda: edit("epg_url", "Guide address", GUIDE_HINT),
             value=lambda: _short(pl.get("epg_url", ""))),
        Item("Rename it", rename),
        Item("Delete it", submenu=lambda: _confirm(app, "Delete it", delete)),
    ]


def _reopen(app, items):
    """Back out of a submenu that just changed what its parent lists."""
    m = app.top()
    if isinstance(m, Menu):
        m.back()
        m.refresh(items)


def add_playlist(app, on_added=None, first_run=False):
    """The playlist's address, an optional guide address, then its name. On
    first run they're the wizard's step 3, numbered 3a to 3c."""
    entry = {"name": "My Channels"}
    step = (lambda n, s: f"3{n}  {s}") if first_run else (lambda n, s: s)

    def ask_url(initial=""):
        app.push(Keyboard(app, step("a", "Playlist address"), got_url, initial=initial, url=True,
                          hint=PLAYLIST_HINT))

    def got_url(url):
        if not url or not _bare(url):
            return
        app.toast("Checking the address...", 30.0)

        def checked(n, err):
            if not n:                   # say why, then let them fix what they typed
                app.toast(f"Couldn't use that address: {err or 'there are no channels in it'}. "
                          "Check it and try again.", 8.0)
                ask_url(url)
                return
            app.toast(f"Found {n} channel{'' if n == 1 else 's'}.", 4.0)
            entry["playlist_url"] = url
            app.push(Keyboard(app, step("b", "Guide address (optional)"), got_epg, url=True,
                              hint=GUIDE_HINT + " Without one, the guide has no listings."))
        _check_playlist(app, url, checked)

    def got_epg(epg):
        if epg is None:
            return
        entry["epg_url"] = _bare(epg)
        app.push(Keyboard(app, step("c", "Name this playlist"), got_name, initial="My Channels",
                          hint="How it's listed under Settings > Channels."))

    def got_name(name):
        if name is None:
            return
        entry["name"] = name or "My Channels"
        finish()

    def finish():
        app.config.playlists.append(entry)
        app.config.save()
        while isinstance(app.top(), Menu):
            app.pop()
        app.switch_playlist(entry)
        if on_added:
            on_added(entry)
    ask_url()


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
    from . import update_flow
    cfg = app.config
    return [
        Item("Diagnostics", lambda: app.push(Diagnostics(app)), close=True),
        Item("Audio output", submenu=lambda: audio_items(app)),
        Item("Weather", submenu=lambda: weather_items(app)),
        Item("Check for updates", lambda: update_flow.open_check(app)),
        Item("Check at start-up", value=lambda: "Yes" if cfg.update_check else "No",
             adjust=lambda d: (setattr(cfg, "update_check", not cfg.update_check), cfg.save())),
        Item("Start-up screen", value=lambda: "On" if cfg.boot_sequence else "Off",
             adjust=lambda d: (setattr(cfg, "boot_sequence", not cfg.boot_sequence), cfg.save())),
        Item("Screensaver", value=lambda: "On" if cfg.screensaver else "Off",
             adjust=lambda d: (setattr(cfg, "screensaver", not cfg.screensaver), cfg.save())),
        Item(f"Cathode {__version__}", enabled=False),
    ]


def audio_items(app):
    def pick(name):
        app.config.audio_device = name
        app.config.save()
        app.video.audio_device = name
        app.toast("Audio output changed")
        app.top().back()
    current = app.config.audio_device or "auto"
    return [Item(("> " if d["name"] == current else "  ") + d["description"][:40],
                 (lambda n=d["name"]: pick(n)))
            for d in app.video.audio_devices()] or [Item("(no outputs found)", enabled=False)]


def weather_items(app):
    cfg = app.config

    def set_zip():
        def got(z):
            if z is not None:
                cfg.weather_zip = z
                cfg.save()
                app.weather.configure(z, cfg.weather_units, cfg.weather_country)
                app.invalidate()
        app.push(Keyboard(app, "Zip or postal code (empty turns weather off)", got,
                          initial=cfg.weather_zip))

    def units(d):
        cfg.weather_units = "C" if cfg.weather_units == "F" else "F"
        cfg.save()
        app.weather.configure(cfg.weather_zip, cfg.weather_units, cfg.weather_country)

    def country(d):
        from .weather import COUNTRIES
        codes = [code for code, _ in COUNTRIES]
        i = codes.index(cfg.weather_country) if cfg.weather_country in codes else 0
        cfg.weather_country = codes[(i + d) % len(codes)]
        cfg.save()
        app.weather.configure(cfg.weather_zip, cfg.weather_units, cfg.weather_country)
    return [
        Item("Zip / postal code", set_zip, value=lambda: cfg.weather_zip or "Off"),
        Item("Country", value=lambda: cfg.weather_country, adjust=country),
        Item("Units", value=lambda: "Fahrenheit" if cfg.weather_units == "F" else "Celsius",
             adjust=units),
    ]


def handles_menu_button(app, action) -> bool:
    """MENU from anywhere that doesn't use it opens the main menu."""
    if action == R.MENU and not isinstance(app.top(), (Menu, Keyboard)):
        if not app.config.playlist_url and not app.config.playlists:
            open_welcome(app)           # nothing set up yet: straight to setting it up
        else:
            open_main(app)
        return True
    return False
