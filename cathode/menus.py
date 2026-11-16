"""What MENU opens: the box's menu tree. Settings apply as they change and
are saved straight away."""

import os
import time

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


WELCOME_HELP = "Have your Tunarr or ErsatzTV address ready (or your provider's M3U link)."

# Beside each box's name on the wizard's first page, and what it is.
LOOK_NOTES = {"classic": "Retro CRT", "indirect": "1997, 4:3", "indirect_hd": "2007, HD",
              "plate": "2005, 4:3", "plate_hd": "2007, HD",
              "igrid": "2006, cable, 4:3", "passage": "2004, cable, 4:3"}
LOOK_HELP = {"classic": "Cathode's own look: a retro CRT, every theme.",
             "indirect": "A 1997 satellite box: purple pages, 4:3.",
             "indirect_hd": "A 2007 HD satellite box: the blue guide.",
             "plate": "A 2005 dish box: grey pages, blue pills, 4:3.",
             "plate_hd": "A 2007 HD dish box: teal pages, gold cursor.",
             "igrid": "A 2006 cable box: navy pages, blue grid, yellow cursor.",
             "passage": "A 2004 cable box: silver page, purple grid, cream card and cursor."}

DESCRIPTIONS.update({
    # Main Menu
    "Program Guide": "Show the on-screen programming schedule.",
    "Themes & Genres": "Channels grouped by what they show.",
    "Favorites": "The guide with just your favorite channels.",
    "On Demand": "Movies and shows from your Plex server.",
    "Link Plex": "Link your Plex account: On Demand plays its movies and shows here.",
    "Refresh guide": "Fetch the TV guide again now.",
    "My Recordings": "What you've downloaded to watch here.",
    "Button Guide": "What every button does, on this box.",
    "Settings": "Picture, channels, subtitles, buttons and more.",
    "Exit Cathode": "Close Cathode.",
    "Restart Cathode": "Close Cathode and start it again.",
    # Settings
    "Picture & Style": "The box, its colors and lettering, screen effects.",
    "Channels": "Your playlists and their guides.",
    "Cathode's channels": "A TV Guide channel and a Weather channel of Cathode's own, in the lineup.",
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
    "FLIRC receiver": "Teach a FLIRC USB receiver any remote, button by button.",
    "Keyboard keys": "Change which key does what.",
    "Controller buttons": "Change which pad button does what.",
    "Reset to defaults": "Put every button back as it came.",
    # System
    "Diagnostics": "Signal, stream and picture details.",
    "Audio output": "Which speakers or HDMI the sound uses.",
    "Video Channels": "YouTube playlists and channels, mixed, as channels of videos on a timeline.",
    "Library Channels": "Channels made from your Plex library: genres, decades, studios, shows, movies.",
    "Plays": "What the channel draws from.",
    "Weather": "Local weather in the guide's header and on the Weather channel.",
    "Check for updates": "See if there's a newer Cathode.",
    "Check at start-up": "Look for a newer Cathode each time it opens.",
    "Start-up screen": "The box's start-up screen when Cathode opens.",
    "Screensaver": "A moving logo when nothing's on screen for a while.",
    # Subtitles
    "Track": "Which subtitles to show.",
    "Size": "How big subtitles are.",
    "Find subtitles": "Search for subtitles through your Plex server.",
    "Search language": "The language Find subtitles looks for.",
    "Auto-sync": "Plex lines subtitle files up with the speech, once it has analysed the title.",
    # On Demand
    "View": "A list, or a wall of posters.",
    "Quality": "How much Plex sends: lower if it stutters.",
    "Libraries": "Which Plex libraries On Demand shows.",
    "Who's watching": "Switch to another Plex Home user.",
    "Unlink Plex account": "Sign this Cathode out of Plex.",
    # The welcome
    "Set up your channels": "Type in the channel list link (M3U) your IPTV provider gave you.",
    "Server": "The Tunarr or ErsatzTV this playlist comes from.",
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
        def plex_only():
            from . import lineup as lu
            app.config.playlist_url, app.config.epg_url = lu.NONE, ""
            app.config.setup_done = True
            app.config.save()
            app.switch_playlist({"playlist_url": lu.NONE, "epg_url": ""})
            m.close()
            app.toast("Link Plex under On Demand: Cathode makes channels from your library.", 8.0)
        return [title, [Item("Set up your channels", setup),
                        Item("No playlist: my Plex library", plex_only,
                             help="No Tunarr or M3U: channels made from your Plex library and YouTube."), *extra,
                        Item("Restart Cathode", submenu=lambda: _confirm(app, "Restart Cathode", app.restart,
                                                                          "Keep going", close=True)),
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

        def choose_box():
            m.open("1/3 CHOOSE YOUR BOX", boxes)
            m.cursor = names.index(app.config.skin) if app.config.skin in names else 0
        m.pages = [["WELCOME TO CATHODE", [Item("Start", choose_box, help=WELCOME_HELP)], 0]]
    app.push(m)


def leave_ondemand(app):
    """Back to live TV from inside On Demand (the Main Menu opened over a
    playing title): the title stops, keeping its resume point, On Demand's
    pages close, and the channel has the picture again."""
    from .screens.ondemand import OnDemandScreen
    from .screens.playback import Playback
    od = app.find(OnDemandScreen)
    if od is None:
        return
    pb = app.find(Playback)
    if pb:
        pb.stop()
    for s in app.screens[app.screens.index(od) + 1:]:
        app.pop(s)
    od.leave()


def main_items(app):
    from .screens.guide import Guide

    def guide(cat="All"):
        def go():
            leave_ondemand(app)
            if app.channels:
                app.push(Guide(app, category=cat))
        return go

    def ondemand(recordings=False):
        def go():
            leave_ondemand(app)
            open_ondemand(app, recordings=recordings)
        return go
    return [
        Item("Program Guide", guide(), close=True, enabled=bool(app.channels)),
        Item("Themes & Genres", submenu=lambda: [
            Item(c, guide(c), close=True) for c in app.categories() if c not in ("All", "Favorites")
        ] or [Item("(no genres in this lineup)", enabled=False)], enabled=bool(app.channels)),
        Item("Favorites", guide("Favorites"), close=True, enabled=bool(app.channels)),
        Item("On Demand" if app.ondemand.signed_in else "Link Plex", ondemand(), close=True),
        *([Item("My Recordings", ondemand(recordings=True), close=True)] if app.ondemand.downloads.items() else []),
        Item("Settings", submenu=lambda: settings_items(app)),
        Item("Button Guide", submenu=lambda: button_guide_items(app)),
        Item("Restart Cathode", submenu=lambda: _confirm(app, "Restart Cathode", app.restart, "Keep watching", close=True)),
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
            if cfg.sub_auto_sync and not any(s.get("sync") for s in pb.subs):
                app.toast("Plex can't sync these subtitles yet: it hasn't analysed this title's speech. "
                          "In Plex, turn on Settings > Library > Generate voice activity data.", 8.0)
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
                if not app.video.add_subtitle(pb.sub_url(sub), sub.get("title", ""), sub.get("lang", ""), select=True):
                    app.toast("The server fetched them, but they wouldn't load. Try another.", 5.0)
                    return
                cfg.subtitles = True
                cfg.save()
            app.toast(f"Subtitles added: {sub.get('title') or lang}")
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
    ]))


def playback_menu(app, pb):
    app.push(Menu(app, "PLAYING", [
        Item("Audio track", submenu=lambda: track_items(app, "audio")),
        Item("Subtitles", submenu=lambda: subtitle_items(app)),
        Item(f"Play queue ({len(app.ondemand.queue.items)})", submenu=lambda: queue_items(app)),
        Item("Main Menu", lambda: open_main(app), close=True,
             help="Settings and the rest, over the title. The guide stops it and goes back to TV."),
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
        Item("FLIRC receiver", submenu=lambda: flirc_items(app)),
        Item("Keyboard keys", submenu=lambda: binding_items(app, "key")),
        Item("Controller buttons", submenu=lambda: binding_items(app, "pad")),
        Item("Reset to defaults", submenu=lambda: _confirm(app, "Reset every button", reset, "Keep my buttons")),
    ]


# The walk-through's order: what every remote has first, the TV's own
# buttons (volume) last, where a TV remote's user skips them.
FLIRC_ORDER = [R.UP, R.DOWN, R.LEFT, R.RIGHT, R.SELECT, R.BACK, R.EXIT, R.MENU, R.GUIDE, R.INFO, R.OPTIONS,
               R.CH_UP, R.CH_DOWN, R.PREV, R.PAUSE, R.STOP, R.REW, R.FF, R.FAV, R.BROWSE, R.LIST, R.THEMES,
               R.FORMAT, R.SUBTITLE, *R.DIGITS, R.VOL_UP, R.VOL_DOWN, R.MUTE]


def _flirc_pretty(a):
    return a[5:] if a.startswith("DIGIT") else _pretty(a)


def flirc_steps(app, actions):
    """[(prompt, flirc_util args)] recording each action's key, named as the
    chosen remote names the button. Actions without a typeable key are left out."""
    from . import flirc
    steps = []
    for a in actions:
        key = flirc.key_for(app.remote.keys, a)
        if not key:
            continue
        prof = R.REMOTES.get(app.config.remote, R.REMOTES[""])[1]
        name = prof.get(a) or (a if prof and not a.startswith("DIGIT") else "")   # a named remote: its own words
        who = f"Press {name}" if name else "Press the button"
        steps.append((f"{who} for {_flirc_pretty(a)}", ["record_api", "0", str(flirc.HID[key])]))
    return steps


def flirc_items(app):
    from .flirc import Flirc
    from .screens.flircwiz import FlircTest, FlircWizard

    def done(n, skipped):
        app.toast(f"{n} recorded" + (f", {len(skipped)} skipped" if skipped else ""), 4)

    def walk():
        app.push(FlircWizard(app, flirc_steps(app, FLIRC_ORDER), done))

    def one_items():
        return [Item(_flirc_pretty(a), (lambda a=a: app.push(FlircWizard(app, flirc_steps(app, [a]), done))))
                for a in FLIRC_ORDER]

    def delete():
        app.push(FlircWizard(app, [("Press the button to forget", ["delete"])],
                             lambda n, s: app.toast("Forgotten" if n else "Nothing forgotten")))

    def test():
        app.push(FlircTest(app, {a: _flirc_pretty(a) for a in FLIRC_ORDER}))

    def simple(args, said):
        Flirc(app).run(args, lambda ok, text: app.toast(said if ok else text, 4))
    return [
        Item("Set up every button", walk,
             help="First put the remote in a mode your TV ignores (SAT/CABLE, DVD). Then press each button as it's asked for; RIGHT skips one."),
        Item("Record one button", submenu=one_items, help="Teach the FLIRC one button, or move a job to another button."),
        Item("Forget a button", delete, help="Press a button and the FLIRC forgets it: for one the TV answers too."),
        Item("Test the buttons", test, help="Press buttons; each names itself. If the TV reacts to one, forget it and use another."),
        Item("Turn off built-in profiles", lambda: simple(["profiles", "disable"], "Built-in profiles off"),
             help="The FLIRC also answers remotes it knows (Fire TV, Harmony, Media Center). Off, only your recorded buttons type."),
        Item("Erase the FLIRC", submenu=lambda: _confirm(app, "Erase every button", lambda: simple(["format"], "FLIRC erased"),
                                                        "Keep them")),
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

    def banner_time(d):             # the HR20's 2-8 s, a second a step
        cfg.osd_timeout = float(max(2, min(8, int(cfg.osd_timeout) + d)))
        cfg.save()
    banner = [Item("Banner time", value=lambda: f"{int(cfg.osd_timeout)} seconds", adjust=banner_time,
                   help="How long the channel banner stays after a change.")] \
        if getattr(app.skin, "banner_time_setting", False) else []
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
        *banner,
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
    items.append(Item("Add a playlist...", lambda: add_playlist(app),
                      help="An M3U link, a Tunarr or ErsatzTV address, a provider line, or an HDHomeRun tuner "
                           "(hdhomerun://its address)."))

    def no_playlist():
        from . import lineup as lu
        app.config.playlist_url, app.config.epg_url = lu.NONE, ""
        app.config.save()
        app.switch_playlist({"playlist_url": lu.NONE, "epg_url": ""})
    from . import lineup as _lu
    items.append(Item(("> " if cfg.playlist_url == _lu.NONE else "  ") + "No playlist", no_playlist, close=True,
                      help="Only Cathode's own channels: the library, YouTube, TV Guide and Weather channels."))
    items.append(Item("Edit lineup", submenu=lambda: lineup_items(app),
                      help="Hide, rename and renumber channels; make packs (guide tabs)."))
    items.append(Item("Cathode's channels", submenu=lambda: own_channel_items(app)))
    items.append(Item("Video Channels", submenu=lambda: video_channel_items(app)))
    items.append(Item("Library Channels", submenu=lambda: library_channel_items(app)))
    days = [(2, "2 days"), (7, "A week"), (14, "Two weeks"), (30, "A month")]

    def guide_days(d):
        from . import videochannels as vc
        cfg.guide_days = _cycle(days, int(cfg.guide_days or 2), d)
        cfg.save()
        vc.rebuild(app)
    items.append(Item("Guide listings", value=lambda: _label(days, int(cfg.guide_days or 2)), adjust=guide_days,
                      help="How far ahead the guide lists the library and video channels. Further takes longer to "
                           "draw up and more memory."))

    def sync_value():
        s = getattr(app, "sync", None)
        if not cfg.lan_sync or s is None:
            return "Off"
        names = sorted(p["name"] for p in s.others())
        return ("On: " + ", ".join(names))[:32] if names else "On, none found"

    def sync_toggle(d=0):
        from . import sync
        cfg.lan_sync = not cfg.lan_sync
        cfg.save()
        (sync.start if cfg.lan_sync else sync.stop)(app)
    items.append(Item("Sync with other Cathodes", value=sync_value, adjust=sync_toggle, action=sync_toggle,
                      help="Every Cathode on your network keeps the same channels: the lists, the library channels' "
                           "schedules and the YouTube lists. The same channel shows the same thing on each. The last "
                           "edit made on any of them wins."))
    if cfg.epg_url:
        items.append(Item("Refresh guide", lambda: (app.load_epg(), app.toast("Loading the guide...")),
                          close=True))
    return items


def own_channel_items(app):
    """Where Cathode's own channels sit: automatic (after the lineup), a
    number typed in, or off. LEFT/RIGHT switch one on and off; SELECT
    types its number."""
    from . import ownchannels
    cfg = app.config

    def value(kind):
        want = cfg.own_channels.get(kind, "auto")
        if want == "off":
            return "Off"
        ch = next((c for c in app.channels if c.url == ownchannels.SCHEME + kind), None)
        at = f" {ch.number:g}" if ch else ""
        return f"Auto{at}" if want == "auto" else f"Channel{at}"

    def toggle(kind):
        cfg.own_channels[kind] = "off" if cfg.own_channels.get(kind, "auto") != "off" else "auto"
        cfg.save()
        app.place_own_channels()

    def set_number(kind):
        def got(text):
            if text is None:
                return
            text = text.strip()
            try:
                cfg.own_channels[kind] = int(text) if text else "auto"
            except ValueError:
                app.toast("A channel number is a whole number.")
                return
            cfg.save()
            app.place_own_channels()
        want = cfg.own_channels.get(kind, "auto")
        app.push(Keyboard(app, "Channel number (empty = automatic)", got,
                          initial=str(want) if isinstance(want, int) else ""))
    def music(_d=0):
        cfg.own_music = not cfg.own_music
        cfg.save()
        if not cfg.own_music:
            ownchannels.stop_music()
        elif app.live and app.live.page is not None:
            ownchannels.play_music(ownchannels.kind_of(app.channels[app.live.idx]), app)
    return [Item(f"{name} channel", lambda k=kind: set_number(k), value=lambda k=kind: value(k),
                 adjust=lambda d, k=kind: toggle(k), help=desc)
            for kind, (name, _t, desc) in ownchannels.KINDS.items()] + [
        Item("Background music", music, value=lambda: "On" if cfg.own_music else "Off", adjust=music,
             help="The channels' own music while one is tuned. Drop your own tvguide.ogg or weather.ogg "
                  "in ~/.config/cathode/music to play that instead.")]


def video_channel_items(app):
    """The video channels: each opens its own page (the maker); one more at
    the foot; yt-dlp (what resolves them) brought up to date."""
    from . import videochannels as vc, ytdl
    cfg = app.config

    def lineup(c):
        return next((ch for ch in app.channels if vc.is_video(ch) and vc.cid_of(ch) == c["id"]), None)

    def name_of(c):
        ch = lineup(c)
        return c.get("name") or (ch.name if ch else "Video Channel")

    def number_of(c):
        ch = lineup(c)
        return f"{ch.number:g}" if ch else ""

    def add():
        def got(text):
            text = (text or "").strip()
            if not text:
                return
            c = vc.new_channel(text)
            cfg.video_channels.append(c)
            cfg.save()
            app.place_own_channels()
            app.top().refresh(video_channel_items(app))
            app.top().open(text.upper(), video_channel_page(app, c["id"]))
        app.push(Keyboard(app, "Channel name", got, hint="Then add its sources: playlists, channels, @handles."))
    items = [Item(name_of(c), submenu=lambda c=c: video_channel_page(app, c["id"]), value=lambda c=c: number_of(c),
                  help="A channel of videos on a timeline, from the sources it mixes. SELECT opens it.")
             for c in cfg.video_channels]
    items.append(Item("Add a channel...", add, help="A new channel: name it, then add what it plays."))
    heights = [(h, f"{h}p") for h in (1080, 720, 480, 360)]

    def quality(d):
        cfg.video_quality = _cycle(heights, int(cfg.video_quality or 1080), d)
        cfg.save()
    items.append(Item("Video quality", value=lambda: _label(heights, int(cfg.video_quality or 1080)), adjust=quality,
                      help="The tallest picture a video plays in. If videos stop to buffer, go lower: 720p takes "
                           "about half the bandwidth of 1080p. Takes effect at the next video."))
    items.append(Item("YouTube support", lambda: app.check_ytdl(manual=True),
                      value=lambda: f"yt-dlp {ytdl.version()}",
                      help="yt-dlp resolves the videos. YouTube changes break it now and then: SELECT fetches "
                           "the newest release (checked weekly on its own); it takes over at the next start."))
    return items


def video_channel_page(app, cid):
    """The channel maker: name, number, sources, how they mix, what's
    skipped, how the guide lists it, the card, a check, removal."""
    from . import videochannels as vc
    cfg = app.config
    c = vc.entry(cfg, cid)
    if c is None:
        return [Item("(this channel is gone)", enabled=False)]

    def save(place=True):
        cfg.save()
        if place:
            app.place_own_channels()
        else:
            vc.rebuild(app)
        app.invalidate()

    def set_name():
        def got(text):
            if text is None:
                return
            c["name"] = text.strip()
            save()
        app.push(Keyboard(app, "Channel name (empty = its first source's)", got, initial=c.get("name", "")))

    def set_number():
        def got(text):
            if text is None:
                return
            text = text.strip()
            try:
                c["number"] = int(text) if text else "auto"
            except ValueError:
                app.toast("A channel number is a whole number.")
                return
            save()
        want = c.get("number", "auto")
        app.push(Keyboard(app, "Channel number (empty = automatic)", got,
                          initial=str(want) if isinstance(want, int) else ""))

    def number_value():
        ch = next((ch for ch in app.channels if vc.is_video(ch) and vc.cid_of(ch) == cid), None)
        at = f" {ch.number:g}" if ch else ""
        return f"Auto{at}" if c.get("number", "auto") == "auto" else f"Channel{at}"

    def cycle(key, options, d):
        c[key] = _cycle(options, c.get(key, options[0][0]), d)
        save(place=False)

    def min_len(d):
        opts = [(v, v) for v in vc.MIN_SECONDS]
        c["min_seconds"] = _cycle(opts, c.get("min_seconds", 60), d)
        save(place=False)

    def max_len(d):
        opts = [(v, v) for v in vc.MAX_SECONDS]
        c["max_seconds"] = _cycle(opts, c.get("max_seconds", 0), d)
        save(place=False)

    def hours(secs):
        return "Any" if not secs else f"{secs // 60} min" if secs < 3600 else f"{secs / 3600:g} h"

    def toggle(key, d=0):
        c[key] = not c.get(key, True)
        save(place=False)

    def refresh():
        """The sources fetched again, today's running order drawn anew,
        and the channel started over if it's on."""
        c["seed"] = int(time.time())
        cfg.save()
        app.toast("Refreshing the schedule...", 60.0)

        def report():
            rows = vc.source_report(app, c)
            app.toast("Schedule refreshed.  " + "  ".join(f"{t or u}: {n}" for u, t, n, _w in rows), 10.0)
            ch = app.live.channel
            if ch is not None and vc.is_video(ch) and vc.cid_of(ch) == cid and ch in app.channels:
                app.live.tune(app.channels.index(ch))
        vc.load(app, done=report, cid=cid, fresh=True)

    def remove():
        cfg.video_channels[:] = [x for x in cfg.video_channels if x["id"] != cid]
        save()
        m = app.top()
        m.back()
        m.refresh(video_channel_items(app))

    def move(d):
        lst = cfg.video_channels
        i = lst.index(c)
        if 0 <= i + d < len(lst):
            lst[i], lst[i + d] = lst[i + d], lst[i]
            save()
            m = app.top()
            m.back()
            m.refresh(video_channel_items(app))
            m.open((c.get("name") or "Video Channel").upper(), video_channel_page(app, cid))
    return [
        Item("Name", set_name, value=lambda: c.get("name") or "(its first source's)",
             help="The channel's name in the lineup and the guide. Empty: named for its first source."),
        Item("Channel number", set_number, value=number_value,
             help="Automatic (after the lineup's last number) or one you choose; a taken number moves to the next free."),
        Item("Sources", submenu=lambda: video_source_items(app, cid), value=lambda: str(len(c.get("sources") or [])),
             help="The playlists, channels and @handles this channel mixes."),
        *timeline_items(app, c, cid, save, unit="videos", default="mix"),
        Item("Minimum length", value=lambda: (f"{c.get('min_seconds', 60)} s" if c.get("min_seconds", 60) else "Any"),
             adjust=min_len, help="Videos shorter than this stay out of the day."),
        Item("Maximum length", value=lambda: hours(c.get("max_seconds", 0)), adjust=max_len,
             help="Videos longer than this stay out of the day (a day-long upload, say)."),
        Item("Skip Shorts", value=lambda: "On" if c.get("skip_shorts", True) else "Off",
             adjust=lambda d: toggle("skip_shorts"), help="YouTube Shorts stay out of the day."),
        Item("Skip live streams", value=lambda: "On" if c.get("skip_live", True) else "Off",
             adjust=lambda d: (toggle("skip_live"), vc.load(app, cid=cid)),
             help="On: a channel's streams and their recordings (hours long) stay out of the day. "
                  "Off: its Streams tab is fetched and mixed in with its videos."),
        Item("Guide", value=lambda: _label(vc.GUIDES, c.get("guide", "auto")),
             adjust=lambda d: cycle("guide", vc.GUIDES, d),
             help="Per video: each video is a programme in the guide. Half-hour blocks: each block names the videos "
                  "starting in it. Auto: per video when the videos are long (episodes), blocks for songs."),
        Item("Lower-third", value=lambda: "On" if c.get("card", True) else "Off",
             adjust=lambda d: toggle("card"), help="The name card as each video starts and before it ends."),
        Item("Refresh schedule", refresh,
             help="Fetches every source's list again, draws up today's running order anew (your changes "
                  "to the sources and their order included) and starts the channel over if it's on."),
        Item("Move up", lambda: move(-1), enabled=cfg.video_channels.index(c) > 0,
             help="Earlier in the list: channels numbered automatically take the lower number."),
        Item("Move down", lambda: move(1), enabled=cfg.video_channels.index(c) < len(cfg.video_channels) - 1),
        Item("Make a copy", lambda: _copy_channel(app, cfg.video_channels, c, video_channel_page),
             help="The same channel again, to change into another."),
        Item("Remove channel", submenu=lambda: _confirm(app, "Remove channel", remove, "Keep it")),
    ]


# ── The lineup: hide, rename, renumber, packs (lineup.py) ────────────────

def lineup_items(app):
    from . import lineup as lu
    cfg = app.config
    chans = getattr(app, "lineup_all", None) or app.channels

    def unhide():
        for k in list(cfg.channel_edits):
            cfg.channel_edits[k].pop("hide", None)
            if not cfg.channel_edits[k]:
                del cfg.channel_edits[k]
        cfg.save()
        app.relineup()
        app.top().refresh(lineup_items(app))
    hidden = sum(1 for e in cfg.channel_edits.values() if e.get("hide"))
    rows = [Item("Packs", submenu=lambda: pack_items(app), value=lambda: str(len(lu.packs(cfg))),
                 help="Named sets of channels, each a tab in the guide's categories (THEMES, or OPTIONS)."),
            Item("Show every hidden channel", unhide, value=lambda: str(hidden), enabled=hidden > 0)]
    for ch in chans:
        e = cfg.channel_edits.get(ch.url) or {}
        rows.append(Item(f"{ch.number:g}  {ch.name}", submenu=lambda ch=ch: channel_edit_items(app, ch),
                         value=lambda e=e: "Hidden" if e.get("hide") else "Edited" if e else "",
                         help="SELECT: show or hide it, its name, its number, its packs."))
    return rows


def _lineup_changed(app):
    app.config.save()
    app.relineup()
    m = app.top()
    if getattr(m, "pages", None) and len(m.pages) > 1:
        m.pages[-2][1] = lineup_items(app) if m.pages[-2][0] in ("EDIT LINEUP", "Edit lineup") else m.pages[-2][1]


def channel_edit_items(app, ch):
    from . import lineup as lu
    cfg = app.config

    def e():
        return cfg.channel_edits.get(ch.url) or {}

    def show(d=0):
        lu.edit(cfg, ch, hide=not e().get("hide"))
        _lineup_changed(app)

    def rename():
        def got(text):
            if text is not None:
                lu.edit(cfg, ch, name=text.strip() or None)
                _lineup_changed(app)
        app.push(Keyboard(app, "Channel name (empty = as it came)", got, initial=e().get("name", "")))

    def renumber():
        def got(text):
            if text is None:
                return
            if not text.strip():
                lu.edit(cfg, ch, number=None)
            else:
                n = lu.number(text)
                if n is None:
                    app.toast("A channel number, like 12 or 10.5.")
                    return
                lu.edit(cfg, ch, number=n)
            _lineup_changed(app)
        app.push(Keyboard(app, "Channel number (empty = as it came; 10.5 is fine)", got,
                          initial=f"{e()['number']:g}" if "number" in e() else ""))

    def reset():
        cfg.channel_edits.pop(ch.url, None)
        _lineup_changed(app)

    def packs_page():
        def flip(p):
            keys = p.setdefault("keys", [])
            (keys.remove if ch.url in keys else keys.append)(ch.url)
            cfg.save()
            app._cats = None
        return [Item(p["name"], lambda p=p: flip(p), adjust=lambda d, p=p: flip(p),
                     value=lambda p=p: "In" if ch.url in (p.get("keys") or []) else "-") for p in lu.packs(cfg)] or \
            [Item("No packs yet", enabled=False, help="Make one under Edit lineup > Packs.")]
    orig = getattr(ch, "orig", (ch.name, ch.number))
    return [
        Item("Show in the lineup", show, value=lambda: "Hidden" if e().get("hide") else "Shown", adjust=show,
             help="Hidden channels are skipped by channel up and down and left out of the guide."),
        Item("Name", rename, value=lambda: e().get("name") or orig[0], help=f"As it came: {orig[0]}"),
        Item("Number", renumber, value=lambda: f"{e().get('number', orig[1]):g}",
             help=f"As it came: {orig[1]:g}. A taken number is shared: the guide lists them side by side."),
        Item("Packs", submenu=packs_page, value=lambda: str(sum(ch.url in (p.get("keys") or []) for p in lu.packs(cfg)))),
        Item("As it came", reset, enabled=bool(e()), help="Its own name and number, shown."),
    ]


def pack_items(app):
    from . import lineup as lu
    cfg = app.config

    def add():
        def got(text):
            text = (text or "").strip()
            if text and not any(p["name"] == text for p in cfg.packs):
                cfg.packs.append({"name": text, "keys": []})
                cfg.save()
                app._cats = None
                app.top().refresh(pack_items(app))
        app.push(Keyboard(app, "Pack name", got, hint="Then add channels to it from their pages, or its own."))
    rows = [Item(p["name"], submenu=lambda p=p: pack_page(app, p), value=lambda p=p: str(len(p.get("keys") or [])))
            for p in lu.packs(cfg)]
    rows.append(Item("Make a pack...", add, help="A guide tab of the channels you put in it."))
    return rows


def pack_page(app, p):
    cfg = app.config
    chans = getattr(app, "lineup_all", None) or app.channels

    def flip(ch):
        keys = p.setdefault("keys", [])
        (keys.remove if ch.url in keys else keys.append)(ch.url)
        cfg.save()
        app._cats = None

    def rename():
        def got(text):
            if text and text.strip():
                p["name"] = text.strip()
                cfg.save()
                app._cats = None
        app.push(Keyboard(app, "Pack name", got, initial=p["name"]))

    def remove():
        cfg.packs[:] = [x for x in cfg.packs if x is not p]
        cfg.save()
        app._cats = None
        m = app.top()
        m.back()
        m.refresh(pack_items(app))
    return [
        Item("Channels", submenu=lambda: [Item(f"{ch.number:g}  {ch.name}", lambda ch=ch: flip(ch),
                                               adjust=lambda d, ch=ch: flip(ch),
                                               value=lambda ch=ch: "In" if ch.url in (p.get("keys") or []) else "-")
                                          for ch in chans],
             value=lambda: str(len(p.get("keys") or []))),
        Item("Name", rename, value=lambda: p["name"]),
        Item("Remove pack", submenu=lambda: _confirm(app, "Remove pack", remove, "Keep it")),
    ]


# ── Library channels (libchannels.py): the maker ─────────────────────────

ORDER_HELP = {
    "mix": "The sources interleaved by their shares of the airtime; each one's titles shuffled, or in order.",
    "random": "Any title, any time; nothing comes round again soon.",
    "cyclic_shuffle": "Every title once, shuffled, then a fresh shuffle.",
    "block_shuffle": "A few episodes of one show in order, then a random other show.",
    "block_cyclic": "A few episodes of one show in order, the shows taking turns by name.",
    "marathon_shuffle": "One show for hours, in order, then a random other show.",
    "marathon_cyclic": "One show for hours, in order, the shows taking turns by name.",
    "round_robin_shuffle": "One episode of each show in turn; the turn order reshuffled every round.",
    "round_robin_cyclic": "One episode of each show in turn, by name.",
    "playlist": "As listed: each show from its first episode to its last, shows by name.",
}


# ── Timeline channels (library and video): the rows they share ───────────

def _label_of(options, key, other="Custom"):
    """_label for options whose keys are lists or dicts."""
    return next((label for k, label in options if k == key), other)


def _ago(t: float) -> str:
    s = time.time() - t
    return "just now" if s < 120 else f"{int(s // 60)} min ago" if s < 3600 else \
        f"{int(s // 3600)} h ago" if s < 86400 else f"{int(s // 86400)} d ago"


def timeline_items(app, c, tid, save, unit="episodes", default="cyclic_shuffle"):
    """How a timeline channel is sorted and when it's on: its sort method
    (and block length, or Mix's weighting), on-air hours, word filters,
    what's coming up, what was skipped."""
    from . import libchannels as lc

    def order(d):
        c["order"] = _cycle(lc.ORDERS, c.get("order", default), d)
        c["block"] = 0
        save(place=False)

    def block(d):
        if c.get("order", default) not in lc.BLOCKS:
            return
        c["block"] = max(1, min(48, int(c.get("block") or lc.BLOCKS[c["order"]]) + d))
        save(place=False)

    def block_value():
        o = c.get("order", default)
        return f"{int(c.get('block') or lc.BLOCKS[o])} {unit}" if o in lc.BLOCKS else "-"

    def weighting(d):
        if c.get("order", default) != "mix":
            return
        c["weighting"] = _cycle(lc.WEIGHTINGS, c.get("weighting", "auto"), d)
        save(place=False)

    def hours(d):
        c["hours"] = _cycle(lc.HOURS, c.get("hours"), d)
        save(place=False)

    def words(key, prompt):
        def got(text):
            if text is None:
                return
            c[key] = [w.strip() for w in text.split(",") if w.strip()]
            save(place=False)
        app.push(Keyboard(app, prompt, got, initial=", ".join(c.get(key) or [])))

    def words_value(key):
        ws = c.get(key) or []
        return ", ".join(ws)[:24] if ws else "None"
    return [
        Item("Sort method", value=lambda: _label(lc.ORDERS, c.get("order", default)), adjust=order,
             help=ORDER_HELP.get(c.get("order", default), "") + "  LEFT/RIGHT changes it."),
        Item("Block length", value=block_value, adjust=block,
             help=f"How many {unit} of one show run before the next (the Block and Marathon methods)."),
        Item("Weighting", value=lambda: _label(lc.WEIGHTINGS, c.get("weighting", "auto"))
             if c.get("order", default) == "mix" else "-", adjust=weighting,
             help="Mix only. Auto: each source's share of the airtime follows how much of it there is, none under "
                  "5%. Equal: the same airtime each. Manual: the weights set on the sources."),
        Item("On the air", value=lambda: _label_of(lc.HOURS, c.get("hours")), adjust=hours,
             help="When the channel broadcasts. Outside its hours it signs off to the colour bars until it's back. "
                  "The last programme before sign-off plays to its end."),
        Item("Leave out titles with", lambda: words("words_out", "Leave out titles with (commas between)"),
             value=lambda: words_value("words_out"),
             help="Anything whose title has one of these words stays off the channel: trailer, reaction, live..."),
        Item("Only titles with", lambda: words("words_in", "Only titles with (commas between; empty = any)"),
             value=lambda: words_value("words_in"),
             help="When set, only titles with one of these words are on the channel."),
        Item("Breaks", submenu=lambda: breaks_items(app, c, save),
             value=lambda: "On" if c.get("breaks") else "Off",
             help="Commercials and bumpers from your Plex libraries between programmes and in long ones, lined "
                  "up with the clock."),
        Item("Coming up", submenu=lambda: coming_up_items(app, tid),
             help="What's on now and what follows, with the times."),
        Item("Skipped", submenu=lambda: skipped_items(app, tid),
             value=lambda: str(len(getattr(lc.SCHEDULES.get(tid), "dropped", {}) or {})),
             help="Titles that couldn't play, kept off the channel for a week. SELECT one to put it back."),
    ]


def breaks_items(app, c, save):
    """A channel's breaks: on or off, the libraries the commercials and the
    bumpers come from, the clock, the length, breaks during programmes."""
    from . import libchannels as lc
    index = getattr(app, "library", None)
    if index is None:
        return [Item("Link Plex first", enabled=False,
                     help="Breaks come from Plex libraries of commercials and bumpers.")]

    def b():
        return c.get("breaks") or {}

    def ensure():
        if not c.get("breaks"):
            c["breaks"] = lc.default_breaks(c, index)
        return c["breaks"]

    def toggle(d=0):
        c["breaks"] = {} if c.get("breaks") else lc.default_breaks(c, index)
        save(place=False)

    def flip(key, skey):
        lst = ensure().setdefault(key, [])
        have = [s for s in lst if s.get("section") == skey]
        for s in have:
            lst.remove(s)
        if not have:
            lst.append({"section": skey, "kind": "all"})
        save(place=False)

    def libs(key):
        secs = sorted((s for s in index.sections.values() if s.breaks or s.kind == "clip"), key=lambda s: s.title.lower())
        return [Item(s.title, lambda s=s: flip(key, s.key), adjust=lambda d, s=s: flip(key, s.key),
                     value=lambda s=s: "On" if any(x.get("section") == s.key for x in b().get(key) or []) else "Off",
                     help=f"{len(s.items):,} clips.") for s in secs] or \
            [Item("No libraries of clips", enabled=False, help="Plex Other Videos libraries of commercials or bumpers.")]

    def cycle(key, options, default, d):
        ensure()[key] = _cycle(options, b().get(key, default), d)
        save(place=False)
    lengths = [(n, f"{n // 60}:{n % 60:02d}") for n in lc.BREAK_LENGTHS]
    return [
        Item("Breaks", toggle, value=lambda: "On" if c.get("breaks") else "Off", adjust=toggle,
             help="On: commercials from the libraries below (it starts with your commercials libraries, and "
                  "bumpers named for the channel's studio)."),
        Item("Commercials from", submenu=lambda: libs("ads"), value=lambda: str(len(b().get("ads") or [])),
             help="The libraries the commercials come from."),
        Item("Bumpers from", submenu=lambda: libs("bumps"), value=lambda: str(len(b().get("bumps") or [])),
             help="Bumpers and idents, one going into each break and one coming out."),
        Item("Line up with the clock", value=lambda: _label(lc.PADS, b().get("pad", 30)),
             adjust=lambda d: cycle("pad", lc.PADS, 30, d),
             help="Breaks fill to the next quarter hour, half hour or hour, so programmes start on time as on real "
                  "TV. No: every break is the length below."),
        Item("Break length", value=lambda: _label(lengths, int(b().get("length", 120))),
             adjust=lambda d: cycle("length", lengths, 120, d),
             help="A break during a programme, and every break when they don't line up with the clock."),
        Item("During programmes", value=lambda: _label(lc.MIDS, b().get("mid", "halfway")),
             adjust=lambda d: cycle("mid", lc.MIDS, "halfway", d),
             help="Breaks inside programmes of fifteen minutes or more: one halfway, or one every twenty minutes."),
    ]


def coming_up_items(app, tid):
    from . import libchannels as lc, videochannels as vc
    tl = lc.SCHEDULES.get(tid)
    rows = []
    for start, e in (tl.coming(30) if tl is not None else []):
        when = f"{start.astimezone():%a %I:%M %p}".replace(" 0", " ")
        if e.get("kind") == "signoff":
            title, about = "Off the air", "The colour bars until it signs on."
        elif e.get("kind") in ("ad", "bump", "brb"):
            continue                                    # (breaks: the list is of programmes)
        elif e.get("yt"):
            artist, song = vc.parse_title(e["title"], e.get("uploader", ""))
            title, about = song, f"From {artist}, {max(1, round(e['duration'] / 60))} min."
        else:
            title = e["title"] + (f"  {e['episode_text']}" if e.get("episode_text") else "")
            about = e.get("desc", "")[:240]
        rows.append(Item(title, value=lambda w=when: w, help=about))
    return rows or [Item("Nothing drawn up yet", enabled=False)]


def skipped_items(app, tid):
    from . import libchannels as lc
    tl = lc.SCHEDULES.get(tid)
    if tl is None or not tl.dropped:
        return [Item("Nothing skipped", enabled=False,
                     help="A title that can't play (a damaged file, a deleted video) shows up here.")]

    def restore(k):
        tl.restore(k)
        app.toast("It's back in the days drawn up from here on.")
        app.top().refresh(skipped_items(app, tid))
    return [Item(tl.title_of(k), lambda k=k: restore(k), value=lambda k=k: _ago(tl.dropped.get(k, time.time())),
                 help="SELECT puts it back on the channel.")
            for k in sorted(tl.dropped, key=lambda k: -tl.dropped[k])]


def _copy_channel(app, lst: list, c: dict, page):
    """A copy of a channel after it, renamed, numbered automatically."""
    import copy
    import uuid
    d = copy.deepcopy(c)
    d.update(id=uuid.uuid4().hex[:8], name=(c.get("name") or "Channel") + " (copy)", number="auto", starter=False)
    d.pop("seed", None)
    lst.insert(lst.index(c) + 1, d)
    app.config.save()
    from . import libchannels as lc
    lc.place(app)
    m = app.top()
    m.back()
    m.open(d["name"].upper(), page(app, d["id"]))


def library_channel_items(app):
    """The library channels: each opens its page; one more at the foot; the
    starter lineup; the library read again."""
    from . import libchannels as lc
    cfg = app.config
    if not app.ondemand.signed_in:
        return [Item("Link your Plex account first", enabled=False,
                     help="Library channels are made from your Plex library. Link it under On Demand.")]

    def number_of(c):
        ch = next((ch for ch in app.channels if lc.is_library(ch) and ch.url.endswith(c["id"])), None)
        return f"{ch.number:g}" if ch else ""

    def again():
        app.top().refresh(library_channel_items(app))

    def add():
        def got(text):
            text = (text or "").strip()
            if not text:
                return
            c = lc.new_channel(text)
            cfg.library_channels.append(c)
            cfg.save()
            lc.place(app)
            again()
            app.top().open(text.upper(), library_channel_page(app, c["id"]))
        app.push(Keyboard(app, "Channel name", got, hint="Then add what it plays: a library, a genre, a decade, a show."))

    def make_starter():
        if app.library is None:
            app.toast("Still reading your library. Try again in a moment.")
            return
        n = lc.add_starter(cfg, app.library)
        cfg.library_starter_done = True
        cfg.save()
        lc.place(app)
        again()
        app.toast(f"{n} channels added." if n else "Every starter channel is already here.")

    def drop_starter():
        cfg.library_channels[:] = [c for c in cfg.library_channels if not c.get("starter")]
        cfg.save()
        lc.place(app)
        m = app.top()
        m.back()
        m.refresh(library_channel_items(app))

    def reread():
        app.toast("Reading your Plex library...", 120.0)
        lc.start(app, fresh=True, done=lambda idx, err: (
            app.toast(f"{idx.count():,} titles in {len(idx.sections)} libraries." if idx and not err
                      else "Couldn't reach your Plex server.", 6.0)))

    def library_value():
        if getattr(app, "library_loading", False):
            p = getattr(app, "library_progress", None)
            return f"Reading {p[0]}" if p else "Reading..."
        return f"{app.library.count():,} titles" if app.library else "Not read yet"
    items = [Item(c.get("name") or "Library Channel", submenu=lambda c=c: library_channel_page(app, c["id"]),
                  value=lambda c=c: number_of(c),
                  help="A channel made from your Plex library. SELECT opens it.")
             for c in cfg.library_channels]
    items.append(Item("Add a channel...", add, help="A new channel: name it, then add what it plays."))
    items.append(Item("Content groups", submenu=lambda: content_group_items(app),
                      value=lambda: str(len(cfg.content_groups)),
                      help="Named sets of sources (\"Saturday cartoons\", \"90s sitcoms\") to use on any channel: change "
                           "the group and every channel naming it follows."))
    def all_breaks():
        if app.library is None:
            app.toast("Still reading your library. Try again in a moment.")
            return
        n = 0
        for c in list(cfg.library_channels) + list(cfg.video_channels):
            if not c.get("breaks"):
                c["breaks"] = lc.default_breaks(c, app.library)
                c["starter"] = False if c in cfg.library_channels else c.get("starter")
                n += 1
        cfg.save()
        lc.place(app)
        app.toast(f"Breaks on {n} channels." if n else "Every channel already has breaks.")
    def mids(d):
        withb = [c for c in list(cfg.library_channels) + list(cfg.video_channels) if c.get("breaks")]
        if not withb:
            app.toast("No channel has breaks yet.")
            return
        now = withb[0]["breaks"].get("mid", "halfway")
        to = _cycle(lc.MIDS, now, d)
        for c in withb:
            c["breaks"]["mid"] = to
        cfg.save()
        lc.place(app)

    def mids_value():
        got = {c["breaks"].get("mid", "halfway") for c in list(cfg.library_channels) + list(cfg.video_channels)
               if c.get("breaks")}
        return _label(lc.MIDS, got.pop()) if len(got) == 1 else "Mixed" if got else "-"
    items.append(Item("Breaks during programmes", value=mids_value, adjust=mids,
                      help="For every channel with breaks at once: none during programmes (Off), one halfway, or one "
                           "every twenty minutes. Each channel's Breaks page sets its own."))
    items.append(Item("Give every channel breaks", all_breaks,
                      help="Commercials from your commercials libraries on every library and YouTube channel that "
                           "has none, bumpers named for each channel's studio, lined up with the half hours."))
    items.append(Item("Add the starter lineup", make_starter,
                      help="Channels made from what your library holds: genres, decades, studios, long-running "
                           "shows, movies. Ones you already have (by name) are left alone."))
    if any(c.get("starter") for c in cfg.library_channels):
        items.append(Item("Remove the starter lineup",
                          submenu=lambda: _confirm(app, "Remove its channels", drop_starter, "Keep them"),
                          help="Takes out every channel the starter lineup made. Channels you made stay."))
    items.append(Item("Read the library again", reread, value=library_value,
                      help="Asks Plex for everything it holds. It checks for changes by itself every few hours; "
                           "this reads it all afresh."))
    return items


def content_group_items(app):
    """Content groups: each opens its page; one more at the foot."""
    from . import libchannels as lc
    cfg = app.config

    def add():
        def got(text):
            text = (text or "").strip()
            if not text:
                return
            import uuid
            g = {"id": "g" + uuid.uuid4().hex[:7], "name": text, "sources": []}
            cfg.content_groups.append(g)
            cfg.save()
            app.top().refresh(content_group_items(app))
            app.top().open(text.upper(), content_group_page(app, g["id"]))
        app.push(Keyboard(app, "Group name", got, hint="Then add what's in it: libraries, genres, decades, shows."))
    rows = [Item(g["name"], submenu=lambda g=g: content_group_page(app, g["id"]),
                 value=lambda g=g: str(len(g.get("sources") or [])), help="SELECT: what's in it, its name, removing it.")
            for g in cfg.content_groups]
    rows.append(Item("Make a group...", add, help="A named set of sources, to name on any channel."))
    return rows


def content_group_page(app, gid):
    from . import libchannels as lc
    cfg = app.config
    g = next((x for x in cfg.content_groups if x["id"] == gid), None)
    if g is None:
        return [Item("(this group is gone)", enabled=False)]

    def rename():
        def got(text):
            if text and text.strip():
                g["name"] = text.strip()
                for c in cfg.library_channels:
                    for s in c.get("sources") or []:
                        if s.get("kind") == "group" and s.get("value") == gid:
                            s["label"] = g["name"]
                cfg.save()
                lc.rebuild(app)
        app.push(Keyboard(app, "Group name", got, initial=g["name"]))

    def remove():
        cfg.content_groups[:] = [x for x in cfg.content_groups if x["id"] != gid]
        for c in cfg.library_channels:
            c["sources"] = [s for s in c.get("sources") or [] if not (s.get("kind") == "group" and s.get("value") == gid)]
        cfg.save()
        lc.rebuild(app)
        m = app.top()
        m.back()
        m.refresh(content_group_items(app))
    users = [c["name"] for c in cfg.library_channels
             if any(s.get("kind") == "group" and s.get("value") == gid for s in c.get("sources") or [])]
    return [
        Item("Plays", submenu=lambda: library_source_items(app, gid), value=lambda: str(len(g.get("sources") or [])),
             help="What's in the group."),
        Item("Name", rename, value=lambda: g["name"]),
        Item("Used by", value=lambda: str(len(users)), help=", ".join(users) or "No channel names it yet."),
        Item("Remove group", submenu=lambda: _confirm(app, "Remove group", remove, "Keep it"),
             help="Channels naming it lose it from what they play."),
    ]


def library_channel_page(app, cid):
    """A library channel: name, number, what it plays, its sort method."""
    from . import libchannels as lc
    cfg = app.config
    c = next((x for x in cfg.library_channels if x["id"] == cid), None)
    if c is None:
        return [Item("(this channel is gone)", enabled=False)]

    def save(place=True):
        c["starter"] = False                # edited: the starter lineup's removal leaves it be
        cfg.save()
        if place:
            lc.place(app)
        else:
            lc.rebuild(app)
        app.invalidate()

    def set_name():
        def got(text):
            if text is None or not text.strip():
                return
            c["name"] = text.strip()
            save()
        app.push(Keyboard(app, "Channel name", got, initial=c.get("name", "")))

    def set_number():
        def got(text):
            if text is None:
                return
            text = text.strip()
            try:
                c["number"] = int(text) if text else "auto"
            except ValueError:
                app.toast("A channel number is a whole number.")
                return
            save()
        want = c.get("number", "auto")
        app.push(Keyboard(app, "Channel number (empty = automatic)", got,
                          initial=str(want) if isinstance(want, int) else ""))

    def number_value():
        ch = next((ch for ch in app.channels if lc.is_library(ch) and ch.url.endswith(cid)), None)
        at = f" {ch.number:g}" if ch else ""
        return f"Auto{at}" if c.get("number", "auto") == "auto" else f"Channel{at}"

    def content(d):
        c["content"] = _cycle(lc.CONTENT, c.get("content", "any"), d)
        save(place=False)

    def premieres(d):
        c["premieres"] = _cycle(lc.PREMIERES, c.get("premieres", "off"), d)
        save(place=False)

    def card(d=0):
        c["card"] = not c.get("card", False)
        save(place=False)

    def refresh():
        c["seed"] = int(time.time())
        save(place=False)
        app.toast("Today onward drawn up again.")
        ch = app.live.channel
        if ch is not None and lc.is_library(ch) and ch.url.endswith(cid):
            app.after(1.5, lambda: ch in app.channels and app.live.tune(app.channels.index(ch)))

    def remove():
        cfg.library_channels[:] = [x for x in cfg.library_channels if x["id"] != cid]
        cfg.save()
        lc.place(app)
        m = app.top()
        m.back()
        m.refresh(library_channel_items(app))

    def holds():
        tl = lc.SCHEDULES.get(lc.PREFIX + cid)
        if not tl or not tl.entries:
            return "Nothing yet"
        hours = sum(i["duration"] for i in tl.entries) / 3600
        return f"{len(tl.entries):,} titles, {hours:,.0f} h"
    return [
        Item("Name", set_name, value=lambda: c.get("name") or "", help="The channel's name in the lineup and the guide."),
        Item("Channel number", set_number, value=number_value,
             help="Automatic (with the other library channels, after the lineup) or one you choose; a taken "
                  "number moves to the next free."),
        Item("Plays", submenu=lambda: library_source_items(app, cid), value=holds,
             help="What the channel draws from: libraries, genres, decades, studios, ratings, shows."),
        *timeline_items(app, c, lc.PREFIX + cid, save),
        Item("Premieres", value=lambda: _label(lc.PREMIERES, c.get("premieres", "off")), adjust=premieres,
             help="Each evening at 8, the newest arrival in your library the channel hasn't premiered yet. The "
                  "guide marks it, and marks every title added in the last two weeks as New."),
        Item("Ratings", value=lambda: _label(lc.CONTENT, c.get("content", "any")), adjust=content,
             help="Anything; nothing rated TV-MA, R or NC-17; or only TV-Y, TV-Y7, TV-G and G (unrated titles "
                  "stay off a kids' channel)."),
        Item("Lower-third", value=lambda: "On" if c.get("card", False) else "Off", adjust=card,
             help="A name card as each programme starts and before it ends."),
        Item("Draw up the schedule again", refresh,
             help="Today onward in a fresh order. The show on now changes."),
        Item("Make a copy", lambda: _copy_channel(app, cfg.library_channels, c, library_channel_page),
             help="The same channel again, to change into another."),
        Item("Remove channel", submenu=lambda: _confirm(app, "Remove channel", remove, "Keep it")),
    ]


def _holder(cfg, cid):
    """A library channel, or a content group, by id: what has sources."""
    return next((x for x in list(cfg.library_channels) + list(getattr(cfg, "content_groups", []) or [])
                 if x["id"] == cid), None)


def library_source_items(app, cid):
    """What a library channel (or a content group) plays: each source
    opens its page; one more at the foot."""
    from . import libchannels as lc
    cfg = app.config
    c = _holder(cfg, cid)
    if c is None:
        return [Item("(this channel is gone)", enabled=False)]
    index = app.library

    def changed():
        c["starter"] = False
        cfg.save()
        lc.rebuild(app)
        m = app.top()
        while len(m.pages) > 1 and m.pages[-1][0] != "Plays":
            m.back()
        m.refresh(library_source_items(app, cid))

    def remove(i):
        c["sources"].pop(i)
        changed()

    def add(section, kind, value):
        c.setdefault("sources", []).append({"section": section, "kind": kind, "value": value})
        changed()

    def values(section, kind):
        return [Item(label, lambda v=v: add(section, kind, v), value=lambda k=k: str(k))
                for v, label, k in lc.options(index, section, kind)] or [Item("(nothing here)", enabled=False)]

    def kinds(section):
        sec = index.sections.get(section)
        rows = [Item("Everything in it", lambda: add(section, "all", None))]
        for kind, label in lc.KINDS[1:]:
            if kind == "rating":
                rows.append(Item("Kids' ratings", lambda: add(section, "rating", lc.KIDS),
                                 help="TV-Y, TV-Y7, TV-G and G."))
                rows.append(Item("Grown-ups' ratings", lambda: add(section, "rating", lc.MATURE),
                                 help="TV-MA, R and NC-17."))
            elif kind == "show" and sec is not None and sec.kind == "music":
                rows.append(Item("An artist...", submenu=lambda: values(section, "show")))
            elif kind != "show" or sec is None or sec.kind == "show":
                rows.append(Item(f"A {label.lower()}...", submenu=lambda kind=kind: values(section, kind)))
        return rows

    def group_rows():
        return [Item(g["name"], lambda g=g: (c.setdefault("sources", []).append(
                    {"kind": "group", "value": g["id"], "label": g["name"]}), changed()))
                for g in cfg.content_groups] or [Item("No content groups yet", enabled=False,
                                                      help="Make one under Library Channels > Content groups.")]

    def where():
        rows = [Item("Every library", submenu=lambda: kinds(""),
                     help="All your programme libraries together (not the bumpers, nor ones hidden from On Demand).")]
        if c in cfg.library_channels:
            rows.append(Item("A content group...", submenu=group_rows,
                             help="A named set of sources you made once, to use on any channel."))
        for sec in sorted(index.sections.values(), key=lambda s: s.title.lower()):
            rows.append(Item(sec.title, submenu=lambda sec=sec: kinds(sec.key), value=lambda sec=sec: f"{len(sec.items):,}"))
        return rows
    if index is None:
        return [Item("Still reading your library...", enabled=False)]
    def label(s):
        return ("Not: " if s.get("exclude") else "") + lc.source_label(index, s)

    def when(s):
        bits = [_label_of(lc.AIRS, s.get("airs"))] if s.get("airs") else []
        bits += [_label_of(lc.SEASONS, s.get("season"))] if s.get("season") else []
        return ", ".join(bits)[:24] or ("Left out" if s.get("exclude") else "Any time")
    items = [Item(label(s), submenu=lambda i=i: library_source_page(app, cid, i), value=lambda s=s: when(s),
                  help="SELECT: when it airs, its weight, leaving it out, removing it.")
             for i, s in enumerate(c.get("sources") or [])]
    items.append(Item("Add...", submenu=where, help="One more slice of the library for this channel."))
    return items


def source_rule_items(app, s, changed, mix=lambda: False):
    """When a source airs and how much: rows a library source and a video
    source share."""
    from . import libchannels as lc

    def cycle(key, options, d):
        s[key] = _cycle(options, s.get(key), d)
        changed()

    def weight(d):
        s["weight"] = max(1, min(10, int(s.get("weight", 1) or 1) + d))
        changed()

    def shuffle(d=0):
        s["shuffle"] = not s.get("shuffle", True)
        changed()
    return [
        Item("Airs", value=lambda: _label_of(lc.AIRS, s.get("airs")), adjust=lambda d: cycle("airs", lc.AIRS, d),
             help="A time slot: while it's this one's time, the channel plays only sources whose slot it is. "
                  "Sources without a slot fill the rest of the day."),
        Item("Season", value=lambda: _label_of(lc.SEASONS, s.get("season")),
             adjust=lambda d: cycle("season", lc.SEASONS, d),
             help="Months it's on the channel at all: holiday specials in December, say."),
        Item("Weight", value=lambda: str(s.get("weight", 1)), adjust=weight,
             help="How much it airs against the others: with Mix (Manual weighting) its share of the airtime; with "
                  "the Shuffle methods how often its shows come up (1 to 10)."),
        Item("Shuffle", value=lambda: ("On" if s.get("shuffle", True) else "Off") if mix() else "-", adjust=shuffle,
             help="Mix only. On: its titles shuffled, every one before any comes round again. Off: in its order, "
                  "carrying on where it left off."),
    ]


def library_source_page(app, cid, i):
    from . import libchannels as lc
    cfg = app.config
    c = _holder(cfg, cid)
    srcs = (c or {}).get("sources") or []
    if c is None or i >= len(srcs):
        return [Item("(this is gone)", enabled=False)]
    s = srcs[i]

    def changed():
        c["starter"] = False
        cfg.save()
        lc.rebuild(app)

    def leave_out(d=0):
        s["exclude"] = not s.get("exclude")
        changed()

    def remove():
        srcs.pop(i)
        changed()
        m = app.top()
        m.back()
        m.refresh(library_source_items(app, cid))
    return [
        Item("Leave these out", leave_out, value=lambda: "On" if s.get("exclude") else "Off", adjust=leave_out,
             help="On: whatever this matches is kept off the channel, though another source takes it in (a "
                  "Comedy channel without one show, say)."),
        *source_rule_items(app, s, changed, mix=lambda: c.get("order") == "mix"),
        Item("Remove it", submenu=lambda: _confirm(app, "Remove it", remove, "Keep it")),
    ]


def video_source_items(app, cid):
    """A channel's sources: each opens its page; one more at the foot."""
    from . import videochannels as vc
    cfg = app.config
    c = vc.entry(cfg, cid)
    if c is None:
        return [Item("(this channel is gone)", enabled=False)]
    report = {u: (t, n, w) for u, t, n, w in vc.source_report(app, c)}

    def label(s):
        t, n, _w = report.get(s["url"], ("", 0, ""))
        return t or s["url"]

    def value(s):
        t, n, w = report.get(s["url"], ("", 0, "not fetched yet"))
        return f"{n} videos" if n else w

    def add():
        def got(text):
            text = (text or "").strip()
            if text and text != Keyboard.URL_START:
                c.setdefault("sources", []).append({"url": text, "weight": 1})
                cfg.save()
                app.top().refresh(video_source_items(app, cid))
                vc.load(app, cid=cid)
        app.push(Keyboard(app, "Playlist link, channel link or @handle", got,
                          hint="A YouTube playlist link or list id, a channel link, or @handle."))
    items = [Item(label(s), submenu=lambda i=i: video_source_page(app, cid, i), value=lambda s=s: value(s),
                  help="SELECT: its link, weight, order, removal.")
             for i, s in enumerate(c.get("sources") or [])]
    items.append(Item("Add a source...", add))
    return items


def video_source_page(app, cid, i):
    from . import videochannels as vc
    cfg = app.config
    c = vc.entry(cfg, cid)
    srcs = (c or {}).get("sources") or []
    if c is None or i >= len(srcs):
        return [Item("(this source is gone)", enabled=False)]
    s = srcs[i]

    def done():
        cfg.save()
        vc.rebuild(app)
        app.invalidate()

    def edit():
        def got(text):
            text = (text or "").strip()
            if text and text != Keyboard.URL_START:
                s["url"] = text
                done()
                vc.load(app, cid=cid)
        app.push(Keyboard(app, "Playlist link, channel link or @handle", got, initial=s["url"]))

    def weight(d):
        s["weight"] = max(1, min(10, int(s.get("weight", 1) or 1) + d))
        done()

    def order(d):
        s["order"] = _cycle(vc.ORDERS, s.get("order", "listed"), d)
        done()

    def plays_as(d):
        from .libchannels import default_as
        now = s.get("as") or default_as(s["url"])
        s["as"] = _cycle(vc.AS, now, d)
        done()

    def limit(d):
        s["limit"] = _cycle([(n, n) for n in vc.LIMITS], int(s.get("limit") or 0), d)
        done()

    def as_value():
        from .libchannels import default_as
        return _label(vc.AS, s.get("as") or default_as(s["url"]))

    def move(d):
        j = i + d
        if 0 <= j < len(srcs):
            srcs[i], srcs[j] = srcs[j], srcs[i]
            done()
            m = app.top()
            m.back()
            m.refresh(video_source_items(app, cid))
            m.open(label().upper(), video_source_page(app, cid, j))

    def remove():
        srcs.pop(i)
        done()
        m = app.top()
        m.back()
        m.refresh(video_source_items(app, cid))

    def label():
        rows = vc.source_report(app, c)
        return (rows[i][1] if i < len(rows) else "") or s["url"]
    return [
        Item("Link", edit, value=lambda: s["url"][-28:], help="The playlist, channel or @handle this source is."),
        Item("Weight", value=lambda: str(s.get("weight", 1)), adjust=weight,
             help="How much it airs against the others: with Mix (Manual weighting) its share of the airtime; "
                  "with the Shuffle methods how often it comes up (1 to 10)."),
        Item("Order", value=lambda: _label(vc.ORDERS, s.get("order", "listed")), adjust=order,
             help="How its videos run: as the playlist or channel lists them (a channel: newest first), "
                  "reversed (oldest first), or by title."),
        Item("Plays as", value=as_value, adjust=plays_as,
             help="One show, in order: its videos run in the order above, like a show's episodes (a creator's "
                  "channel). Separate videos: each stands alone (a playlist of songs). It matters to the Block, "
                  "Marathon, Round Robin and Playlist methods."),
        Item("Newest only", value=lambda: f"{s['limit']} videos" if s.get("limit") else "All", adjust=limit,
             help="Only the newest this many of its videos (as it lists them) are on the channel."),
        *[it for it in source_rule_items(app, s, done, mix=lambda: c.get("order", "mix") == "mix")
          if it.label != "Weight"],
        Item("Move up", lambda: move(-1), enabled=i > 0),
        Item("Move down", lambda: move(1), enabled=i < len(srcs) - 1),
        Item("Remove source", submenu=lambda: _confirm(app, "Remove source", remove, "Keep it")),
    ]


def _bare(url):
    """Just the http:// the keyboard starts with: nothing typed."""
    return "" if (url or "").strip().lower() in ("http://", "https://") else (url or "")


def _short(url):
    """An address short enough for a menu value, a line's password hidden."""
    from .playlist import _scrub
    s = _scrub(url or "").split("://", 1)[-1]
    return "None" if not s else s if len(s) <= 26 else f"{s[:13]}...{s[-10:]}"


def _offer_lan_server(app, kb):
    """Look for a Tunarr or ErsatzTV on the local network while the address
    keyboard is up; the first one found is typed in, so a Deck or a TV box
    needs no typing at all. Nothing happens if the user has started typing."""
    import threading
    from . import servers

    def work():
        found = servers.scan_lan(user_agent=app.agent)
        if found:
            app.post(offer, found[0])

    def offer(server):
        if app.top() is not kb or kb.value:
            return
        kb.value, kb.caret = server.base, len(server.base)
        app.toast(f"Found {server.name} at {server.base}. Press DONE to use it, or type another address.", 10.0)
        app.invalidate()
    threading.Thread(target=work, daemon=True).start()


def _find_server(app, address, done):
    """Ask the address what it is, off the UI thread; done(Server or None)."""
    import threading
    from . import servers

    def work():
        app.post(done, servers.detect(address, user_agent=app.config.user_agent))
    threading.Thread(target=work, daemon=True).start()


def _check_playlist(app, url, done, entry=None):
    """Fetch the playlist off the UI thread; done(channel count, error text).
    A provider that only answers a player's User-Agent is fetched as one,
    and `entry` remembers which, for its guide and streams."""
    import threading
    from . import playlist as m3u
    from .app import load_error_text

    def work():
        try:
            chans, agent, used = m3u.load_as(url, user_agent=app.config.user_agent)
            n, err = len(chans), ""
            if entry is not None:
                if agent != app.config.user_agent:
                    entry["user_agent"] = agent
                if used != url:                 # another shape of the link answered: keep that one
                    entry["playlist_url"] = used
        except Exception as e:
            n, err = 0, load_error_text(e)
        app.post(done, n, err)
    threading.Thread(target=work, daemon=True).start()


SERVER_HINT = "Your Tunarr or ErsatzTV address (10.0.0.215:8000), or your provider's M3U Plus link."
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
    ] + ([Item("Server", value=lambda: _short(pl.get("server", "")), enabled=False)] if pl.get("server") else []) + [
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
    step = (lambda n, s: f"3/3  {s}") if first_run else (lambda n, s: s)

    def ask_url(initial=""):
        kb = Keyboard(app, step("a", "Server address"), got_address, initial=initial, url=True, hint=SERVER_HINT)
        app.push(kb)
        if not initial:
            _offer_lan_server(app, kb)

    def got_address(text):
        """A bare host is asked what it is; a known server skips the guide
        step; an M3U Plus (Xtream) link brings its guide with it. Anything
        else is taken as a playlist link."""
        from . import servers
        if not text or not _bare(text):
            return
        provider = servers.xtream(text)
        if provider is not None:
            app.toast("Checking the address...", 30.0)

            def checked(n, err):
                if not n:
                    app.toast(f"Couldn't use that address: {err or 'there are no channels in it'}. "
                              "Check it and try again.", 8.0)
                    ask_url(text)
                    return
                entry.setdefault("playlist_url", provider.playlist_url)   # the check keeps the address that answered
                # a line that only answers through its API gets its guide the same way
                entry["epg_url"] = entry["playlist_url"] if entry["playlist_url"].startswith("xtream://") else provider.epg_url
                entry["name"] = "My Channels"
                app.toast(f"Found {n} channel{'' if n == 1 else 's'}. The guide comes from the same provider.", 5.0)
                app.push(Keyboard(app, step("c", "Name this playlist"), got_name, initial="My Channels",
                                  hint="How it's listed under Settings > Channels."))
            _check_playlist(app, provider.playlist_url, checked, entry)
            return
        if not servers.looks_like_address(text):
            got_url(text)
            return
        app.toast("Looking for the server...", 30.0)

        def found(server):
            if server is None:
                got_url(text)       # not a server: maybe it's a playlist link
                return
            entry["server"] = server.base
            entry["playlist_url"], entry["epg_url"] = server.playlist_url, server.epg_url
            entry["name"] = server.name
            app.toast(f"Found {server}.", 4.0)

            def checked(n, err):
                if not n:
                    app.toast(f"{server} answered, but its channel list didn't load: {err or 'no channels'}.", 8.0)
                    ask_url(text)
                    return
                app.toast(f"Found {server}: {n} channel{'' if n == 1 else 's'}.", 4.0)
                finish()
            _check_playlist(app, server.playlist_url, checked)
        _find_server(app, text, found)

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
            entry.setdefault("playlist_url", url)       # the check may have kept another shape of the link
            app.push(Keyboard(app, step("b", "Guide address (optional)"), got_epg, url=True,
                              hint=GUIDE_HINT + " Without one, the guide has no listings."))
        _check_playlist(app, url, checked, entry)

    def got_epg(epg):
        if epg is None:
            return
        entry["epg_url"] = _bare(epg)
        app.push(Keyboard(app, step("c", "Name this playlist"), got_name, initial="My Channels",
                          hint="How it's listed under Settings > Channels."))

    def got_name(name):
        if name is None:
            return
        if "://" in (name or ""):           # a link pasted into the name by mistake: a URL isn't a name
            name = ""
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

def _save_diagnostics(app):
    from . import diagnostics_zip
    try:
        path = diagnostics_zip.write(app)
    except OSError as e:
        app.toast(f"Couldn't write the diagnostics file: {e}", 6.0)
        return
    app.toast(f"Saved {os.path.basename(path)} on your Desktop. Attach it to a bug report.", 8.0)


def system_items(app):
    from . import __version__, sounds
    from .screens.diagnostics import Diagnostics
    from . import update_flow
    cfg = app.config
    return [
        Item("Diagnostics", lambda: app.push(Diagnostics(app)), close=True),
        Item("Save diagnostics", lambda: _save_diagnostics(app),
             help="One zip on your Desktop to attach to a bug report: logs, settings without passwords, system."),
        Item("Audio output", submenu=lambda: audio_items(app)),
        Item("Weather", submenu=lambda: weather_items(app)),
        Item("Check for updates", lambda: update_flow.open_check(app)),
        Item("Check at start-up", value=lambda: "Yes" if cfg.update_check else "No",
             adjust=lambda d: (setattr(cfg, "update_check", not cfg.update_check), cfg.save())),
        *([Item("Sound effects", value=lambda: _label(sounds.LEVELS, cfg.sound_effects),
                adjust=lambda d: (setattr(cfg, "sound_effects", _cycle(sounds.LEVELS, cfg.sound_effects, d)), cfg.save(),
                                  app.sound("key")),
                help="The box's key sounds and its error bonk, as the HR20 had them.")]
          if getattr(app.skin, "ui_sounds", False) else []),
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
        from . import spelunkr
        if not app.config.playlist_url and not [p for p in app.config.playlists if not spelunkr.is_shipped(p)]:
            open_welcome(app)           # nothing set up yet (Spelunkr comes with it): straight to setting it up
        else:
            open_main(app)
        return True
    return False
