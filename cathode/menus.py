"""What MENU opens: the box's menu tree. Settings apply as they change and
are saved straight away."""

import json
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


WELCOME_HELP = "Your Plex library as cable TV, or an M3U list."
PLAYLIST_HELP = "Your Tunarr or ErsatzTV address, or your provider's M3U link."

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
    "Settings": "Channels, commercials, the schedule, the look and the rest.",
    "Exit Cathode": "Close Cathode.",
    "Restart Cathode": "Close Cathode and start it again.",
    # Settings
    "Picture & Style": "The box, its colors and lettering, screen effects.",
    "Channels": "Add, edit, hide and group channels; where they come from.",
    "Commercials": "What every channel's breaks are made of, and which channels have them.",
    "Schedule": "Draw the schedule up afresh, read the library again, how far ahead.",
    "Design": "The box, its colors and lettering, screen effects.",
    "Preferences": "Subtitles, the channel logo, the screen, start-up, sound, the remote, weather.",
    "Servers": "Plex, Jellyfin, Emby and folders.",
    "Admin": "The phone remote, other Cathodes, backups, diagnostics, updates.",
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
    "Content": "What the channel plays.",
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
    "From my Plex library": "Cathode makes its channels from your Plex library.",
    "From Tunarr, ErsatzTV or an M3U link": "Type in your server's address or the link your provider gave you.",
    "Server": "The Tunarr or ErsatzTV this playlist comes from.",
    "Playlist address": "Where the channels come from: your provider's M3U link, or a file.",
    "Guide address": "Where the listings come from: your provider's XMLTV link. Optional.",
    "Change the look": "Pick the box and its colors again.",
})


def first_run(app) -> bool:
    """Nothing set up yet: the setup never finished, no playlist of yours,
    no library channels."""
    from . import lineup as lu, spelunkr
    cfg = app.config
    return not cfg.setup_done and cfg.playlist_url in ("", lu.NONE) and not cfg.library_channels \
        and not [p for p in cfg.playlists if not spelunkr.is_shipped(p)]


def open_welcome(app):
    """First run, as a wizard: 1/4 the box, 2/4 its colours, 3/4 the
    channels (made from your Plex library, linked right there, or a
    playlist), 4/4 your area for the weather; then, for Plex, the library
    read and the lineup it made, ready to watch. The look pages redraw in
    whatever the cursor is on; BACK steps back a page. Once the look is
    chosen, coming back here goes straight to the channels."""
    from . import libchannels as lc, lineup as lu
    from .skins import skin_classes
    cfg = app.config
    m = Menu(app, "", [])

    def finish(first=None):
        cfg.setup_done = True
        cfg.save()
        m.close()
        if first is not None and app.live is not None:
            app.live.tune(first)

    def area(then):
        def zip_code():
            def got(text):
                if text is not None:
                    cfg.weather_zip = text.strip()
                    cfg.save()
                    if getattr(app, "weather", None) is not None:
                        app.weather.configure(cfg.weather_zip, cfg.weather_units, cfg.weather_country)
                    app.invalidate()
            app.push(Keyboard(app, "ZIP or postal code", got, initial=cfg.weather_zip))
        m.open("4/4 YOUR AREA", [
            Item("ZIP or postal code", zip_code, value=lambda: cfg.weather_zip or "Not set",
                 help="For the Weather channel and the forecast in the guide. You can skip it; Settings > "
                      "System > Weather has it, and the country."),
            Item("Continue", then)])

    def build():
        state = {"done": False}

        def progress():
            p = getattr(app, "library_progress", None)
            if p:
                title, d, t = p
                return f"{title}: {d:,} of {t:,}" if t else title
            return "Asking your server..."

        def built(index, err=""):
            if state["done"]:
                return
            state["done"] = True
            if not cfg.library_channels and index is not None:      # (a starter lineup taken out before)
                lc.add_starter(cfg, index)
                cfg.save()
                lc.place(app)
            n = len(cfg.library_channels)
            if not n:
                m.open("NO CHANNELS YET", [
                    Item("Try again", lambda: (m.back(), build())),
                    Item("Use a playlist instead", setup),
                    Item("Finish for now", finish)])
                m.items[0].help = f"Cathode couldn't make channels from your Plex library. {err}".strip()
                return
            first = next((i for i, ch in enumerate(app.channels or []) if lc.is_library(ch)), None)
            libs = [ch for ch in app.channels or [] if lc.is_library(ch)]
            names = ", ".join(ch.name for ch in libs[:8])
            at = f" from {libs[0].number:g}" if libs else ""
            m.open("YOUR LINEUP IS READY", [
                Item("Start watching", lambda: finish(first), value=lambda: f"{n} channels",
                     help=f"{n} channels{at}: {names}{'...' if n > 8 else ''}. Change them under Settings > "
                          "Channels.")])

        def tick():
            if state["done"] or m not in app.screens:
                return
            if not app.ondemand.signed_in:
                built(None, "Plex isn't linked.")
                return
            if not getattr(app, "library_loading", False) and cfg.library_channels and \
                    getattr(app, "library", None) is not None:
                built(app.library)          # (a read already under way finished first)
                return
            app.invalidate()
            app.after(0.5, tick)
        m.open("BUILDING YOUR CHANNELS", [
            Item("Reading your Plex library", enabled=False, value=progress,
                 help="Your channels as your Tunarr had them, every show and movie on one. A big library takes "
                      "a minute or two the first time; after that it's quick.")])
        lc.start(app, done=built)
        app.after(0.5, tick)

    def plex():
        if cfg.playlist_url != lu.NONE:
            cfg.playlist_url, cfg.epg_url = lu.NONE, ""
            cfg.save()
            app.switch_playlist({"playlist_url": lu.NONE, "epg_url": ""})
        if app.ondemand.signed_in:
            area(build)
            return
        from .screens.ondemand import OnDemandScreen
        s = OnDemandScreen(app)                 # the plex.tv/link code, who's watching, the server
        s.then = lambda: area(build)
        app.push(s)

    def setup():
        def added(entry):
            from .screens.boot import Boot
            area(lambda: (finish(), app.push(Boot(app))))
        add_playlist(app, on_added=added, first_run=True)

    def channels(title, extra=()):
        return [title, [Item("From my Plex library", plex, value=lambda: "Recommended",
                             help="Cathode makes a cable lineup from your library: your channels as your Tunarr "
                                  "had them, every show and movie on one. You'll link Plex next."),
                        Item("From Tunarr, ErsatzTV or an M3U link", setup, help=PLAYLIST_HELP), *extra,
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
            cfg.look_chosen = True
            cfg.save()
            m.pages.append(channels("3/4 YOUR CHANNELS"))
        keys = [k for k, _ in choices]
        m.open("2/4 CHOOSE COLORS", [Item(label, lambda k=k: chosen(k), preview=lambda k=k: show(k),
                                          help="The box's own colors, as it looked. Recommended." if k == "native"
                                          else "Cathode 3's colors, kept readable on this box.")
                                     for k, label in choices])
        m.cursor = keys.index(skin.theme_key()) if skin.theme_key() in keys else 0

    def restart():
        m.close()
        cfg.look_chosen = False
        open_welcome(app)

    if cfg.look_chosen:
        m.pages = [channels("WELCOME TO CATHODE", [Item("Change the look", restart)])]
    else:
        names = list(skin_classes())
        boxes = [Item(cls.label, lambda k=k: (app.set_skin(k), colours()), value=lambda k=k: LOOK_NOTES.get(k, ""),
                      preview=lambda k=k: app.set_skin(k), help=LOOK_HELP.get(k, ""))
                 for k, cls in skin_classes().items()]

        def choose_box():
            m.open("1/4 CHOOSE YOUR BOX", boxes)
            m.cursor = names.index(cfg.skin) if cfg.skin in names else 0
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
        *([Item("Who's watching", submenu=lambda: who_items(app),
                value=lambda: _who_name(app))]
          if app.config.profiles else []),
        Item("Channel Search", lambda: channel_search(app), enabled=bool(app.channels),
             help="Type part of a channel's name or its number."),
        Item("Sleep Timer", lambda: sleep_step(app, 1), value=lambda: sleep_value(app), adjust=lambda d: sleep_step(app, d),
             help="Cathode closes when it runs out, as a TV switches itself off. SELECT or RIGHT for longer."),
        Item("Settings", lambda: _pin_then(app, lambda: app.top().open("Settings", settings_items(app)))),
        Item("Button Guide", submenu=lambda: button_guide_items(app)),
        Item("Restart Cathode", submenu=lambda: _confirm(app, "Restart Cathode", app.restart, "Keep watching", close=True)),
        Item("Exit Cathode", submenu=lambda: _confirm(app, "Exit Cathode", app.quit, "Keep watching", close=True)),
    ]


def channel_search(app):
    """A channel by part of its name or its number, tuned with SELECT."""
    def got(text):
        text = (text or "").strip().lower()
        if not text:
            return
        hits = [ch for ch in app.channels if text in ch.name.lower() or f"{ch.number:g}".startswith(text)][:60]

        def tune(ch):
            leave_ondemand(app)
            if ch in app.channels:
                app.live.tune(app.channels.index(ch))
        app.top().open("CHANNEL SEARCH", [Item(f"{ch.number:g}  {ch.name}", lambda ch=ch: tune(ch), close=True)
                                          for ch in hits] or [Item("No channel has that", enabled=False)])
    app.push(Keyboard(app, "Channel name or number", got))


SLEEP = [0, 30, 60, 120, 240, 360, 480]          # minutes; 0 off


def sleep_value(app) -> str:
    left = getattr(app, "_sleep_at", 0) - time.time()
    if left <= 0:
        return "Off"
    m = int(left // 60) + 1
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d}"


def sleep_step(app, d):
    """Off, 30 minutes, an hour, 2, 4, 6, 8 hours, round again: Cathode
    closes when it runs out."""
    cur = getattr(app, "_sleep_for", 0) if getattr(app, "_sleep_at", 0) > time.time() else 0
    to = SLEEP[(SLEEP.index(cur) + d) % len(SLEEP)] if cur in SLEEP else SLEEP[1]
    app._sleep_for, app._sleep_at = to, (time.time() + to * 60) if to else 0
    app._sleep_gen = gen = getattr(app, "_sleep_gen", 0) + 1
    if to:
        app.after(to * 60, lambda: gen == app._sleep_gen and app.quit())
        app.toast(f"Sleep timer: {sleep_value(app)}.")
    else:
        app.toast("Sleep timer off.")


def _confirm(app, yes: str, do, keep: str = "Keep it", close: bool = False):
    """The page before something that can't be undone, as the recording
    delete has: the safe choice first, so SELECT twice doesn't do it."""
    act = do if close else (lambda: (app.top().back(), do()))
    return [Item(keep, lambda: app.top().back()), Item(yes, act, close=close)]


def settings_items(app):
    """Settings, laid out as NostalgiaTV's tabs: Channels, Commercials,
    Schedule, Design, Preferences, Servers, Profiles, Admin."""
    return [
        Item("Channels", submenu=lambda: channels_tab(app)),
        Item("Commercials", submenu=lambda: commercials_tab(app)),
        Item("Schedule", submenu=lambda: schedule_tab(app)),
        Item("Design", submenu=lambda: style_items(app)),
        Item("Preferences", submenu=lambda: preference_items(app)),
        Item("Servers", submenu=lambda: server_items(app)),
        Item("Profiles", submenu=lambda: profile_items(app),
             help="Who's watching: each profile its own look and favourites; kids' profiles; the parent PIN; the "
                  "watch history."),
        Item("Admin", submenu=lambda: admin_items(app)),
    ]


def _lineup_all(app) -> list:
    """Every channel in the lineup, the hidden ones too."""
    return getattr(app, "lineup_all", None) or getattr(app, "channels", None) or []


def _by_url(app, url):
    return next((ch for ch in _lineup_all(app) if ch.url == url), None)


def _refresh(app, pages: dict):
    """Pages further back in the menu made again (a page's rows are made
    as it opens): a channel added, renamed or taken out shows on them."""
    m = app.top() if callable(getattr(app, "top", None)) else None
    for pg in getattr(m, "pages", None) or []:
        fn = pages.get(pg[0])
        if fn is not None:
            pg[1] = fn()
            pg[2] = max(0, min(pg[2], len(pg[1]) - 1))


def _lists_changed(app):
    _refresh(app, {"Channels": lambda: channels_tab(app), "Hidden Channels": lambda: hidden_items(app)})


def _kind(app, ch) -> str:
    from . import libchannels as lc, ownchannels, videochannels as vc
    if (app.config.channel_edits.get(ch.url) or {}).get("hide"):
        return "Hidden"
    if lc.is_library(ch):
        return "Library"
    if vc.is_video(ch) and vc.entry(app.config, vc.cid_of(ch)):
        return "YouTube"
    if ch.url.startswith(ownchannels.SCHEME):
        return "Cathode"
    return "Playlist"


def channels_tab(app):
    """Settings > Channels, as NostalgiaTV's: a channel of your own first,
    where the rest come from, packs, hidden ones, content groups, Cathode's
    own, the starter lineup; then every channel, each opening its editor."""
    from . import lineup as lu
    cfg = app.config

    def sort(d):
        cfg.channel_sort = _cycle(CHANNEL_SORTS, cfg.channel_sort, d)
        cfg.save()
        _lists_changed(app)
    rows = [
        Item("Add Custom Channel", submenu=lambda: add_channel_items(app),
             help="A channel of your own: from your library (shows, movies, genres, decades...) or from YouTube."),
        Item("Live TV Sources", submenu=lambda: source_items(app), value=lambda: str(len(cfg.playlists)),
             help="Where the rest of the lineup comes from: Tunarr, ErsatzTV, an M3U link, an HDHomeRun tuner."),
        Item("Channel Packs", submenu=lambda: pack_items(app), value=lambda: str(len(lu.packs(cfg))),
             help="Named sets of channels, each a tab in the guide's categories (THEMES, or OPTIONS)."),
        Item("Hidden Channels", submenu=lambda: hidden_items(app),
             value=lambda: str(sum(1 for e in cfg.channel_edits.values() if e.get("hide"))),
             help="Channels you've hidden, to show again."),
        Item("Content Groups", submenu=lambda: content_group_items(app), value=lambda: str(len(cfg.content_groups)),
             help="Named sets of content (Saturday cartoons, 90s sitcoms) to add to any channel: change the group "
                  "and every channel with it follows."),
        Item("Cathode's channels", submenu=lambda: own_channel_items(app)),
        Item("Starter Lineup", submenu=lambda: starter_items(app),
             value=lambda: str(sum(1 for c in cfg.library_channels if c.get("starter"))),
             help="The channels Cathode makes from your library: your Tunarr lineup and a few of its own."),
        Item("Find a Title", lambda: find_title(app),
             help="Type part of a show's or a movie's title: the channels that play it."),
        Item("Bulk Edit", submenu=lambda: bulk_items(app),
             help="Pick several library channels, then set one thing on all of them at once."),
        Item("Sort By", value=lambda: _label(CHANNEL_SORTS, cfg.channel_sort), adjust=sort,
             help="The list below by number, by name or by kind. LEFT/RIGHT on a channel moves it up or down the "
                  "lineup."),
    ]
    chans = _lineup_all(app)
    if cfg.channel_sort == "name":
        chans = sorted(chans, key=lambda ch: ch.name.lower())
    elif cfg.channel_sort == "kind":
        chans = sorted(chans, key=lambda ch: (_kind(app, ch), ch.number))
    return rows + [Item(f"{ch.number:g}  {ch.name}", submenu=lambda ch=ch: channel_editor(app, ch),
                        value=lambda ch=ch: _kind(app, ch), adjust=lambda d, ch=ch: move_channel(app, ch, d),
                        help="SELECT: everything about this channel. LEFT/RIGHT moves it down or up the lineup.")
                   for ch in chans]


def channel_editor(app, ch):
    """One page for everything about a channel, as NostalgiaTV's channel
    editor: a library or YouTube channel's whole make-up; any other its
    name, number, place in the lineup, logo and bug."""
    from . import libchannels as lc, videochannels as vc
    if lc.is_library(ch):
        return library_channel_page(app, vc.cid_of(ch)[len(lc.PREFIX):])
    if vc.is_video(ch) and vc.entry(app.config, vc.cid_of(ch)):
        return video_channel_page(app, vc.cid_of(ch))
    return channel_edit_items(app, ch)


def _entry_at(ch, prog):
    """The library title a guide cell stands for (None for other channels)."""
    from datetime import timedelta
    from . import libchannels as lc, videochannels as vc
    if prog is None or not vc.is_video(ch):
        return None, None
    tl = lc.SCHEDULES.get(vc.cid_of(ch))
    got = tl.at(prog.start + timedelta(seconds=1)) if tl is not None else None
    e = (got or {}).get("entry") or {}
    return tl, (e if e.get("plex") else None)


def open_guide_options(app, ch, prog):
    """SELECT on a programme's info in the guide (NostalgiaTV's long-press):
    watch, browse what the channel plays, put the show on another channel,
    edit the channel."""
    from . import libchannels as lc, videochannels as vc
    if ch is None:
        return
    tl, e = _entry_at(ch, prog)

    def watch():
        while len(app.screens) > 1 and app.top() is not app.live:
            app.pop(app.top())
        if ch in app.channels:
            app.live.tune(app.channels.index(ch))

    def add_to(c):
        src = {"kind": "show", "value": e["show_key"]} if e.get("show_key") else \
            {"kind": "title", "value": [e["plex"]]}
        if any(s.get("kind") == src["kind"] and s.get("value") == src["value"] for s in c.get("sources") or []):
            app.toast(f"{c.get('name')} already has it.")
            return
        c.setdefault("sources", []).append(src)
        c["starter"] = False
        app.config.save()
        lc.rebuild(app)
        app.toast(f"{e['title']} added to {c.get('name') or 'that channel'}.")
    rows = [Item("Watch this channel", watch, close=True)]
    if tl is not None:
        rows.append(Item("Browse this channel", submenu=lambda: browse_channel(app, ch, tl),
                         help="Every show and movie it plays, with when each is next on."))
    if e is not None:
        rows.append(Item(f"Add {e['title']} to a channel", submenu=lambda: [
            Item(c.get("name") or "Library Channel", lambda c=c: add_to(c), close=True)
            for c in app.config.library_channels if not vc.SCHEME + lc.PREFIX + c["id"] == ch.url] or
            [Item("No other library channels", enabled=False)],
            help="Puts this show (or movie) on another library channel too."))
    rows.append(Item("Edit this channel", lambda: open_channel_editor(app, ch)))
    app.push(Menu(app, f"{ch.number:g}  {ch.name}", rows))


def browse_channel(app, ch, tl):
    """A channel's titles, each with its next airing in the days drawn up."""
    from datetime import datetime, timezone
    nxt = {}
    for start, e in tl.coming(400, datetime.now(timezone.utc)):
        if e.get("kind") == "show":
            nxt.setdefault(e.get("title"), start)
    titles = sorted({g["title"] for g in tl.groups}, key=lambda t: (t not in nxt, t.lower()))

    def when(t):
        s = nxt.get(t)
        return s.astimezone().strftime("%a %I:%M %p").replace(" 0", " ") if s else "Later"
    return [Item(t, value=lambda t=t: when(t), help="When it's next on this channel.") for t in titles] or \
        [Item("Nothing yet", enabled=False)]


def open_channel_editor(app, ch):
    """The editor over live TV (Options > Edit this channel)."""
    if ch is not None:
        app.push(Menu(app, f"{ch.number:g}  {ch.name}", channel_editor(app, ch)))


def add_channel_items(app):
    """Add Custom Channel: from the library or from YouTube; named, then
    straight to what it plays."""
    from . import libchannels as lc, videochannels as vc
    cfg = app.config
    linked = bool(app.ondemand.signed_in or cfg.media_servers or cfg.local_folders)

    def make(kind):
        def got(text):
            if text is None:
                return
            text = text.strip() or "New Channel"
            if kind == "library":
                c = lc.new_channel(text)
                cfg.library_channels.append(c)
                cfg.save()
                lc.place(app)
            else:
                c = vc.new_channel(text)
                cfg.video_channels.append(c)
                cfg.save()
                app.place_own_channels()
            m = app.top()
            m.back()                                    # (off this page: the new channel is on the list)
            _lists_changed(app)
            if kind == "library":
                m.open(text.upper(), library_channel_page(app, c["id"]))
                m.open("Content", library_source_items(app, c["id"]))
            else:
                m.open(text.upper(), video_channel_page(app, c["id"]))
                m.open("Content", video_source_items(app, c["id"]))
        app.push(Keyboard(app, "Channel Name", got, hint="Then add what it plays."))
    return [
        Item("From my library", lambda: make("library"), enabled=linked,
             help="Shows, movies, a library, genres, decades, studios: on a timeline, with breaks." if linked else
             "Link Plex first (Settings > Servers), or add Jellyfin, Emby or a folder there."),
        Item("From YouTube", lambda: make("video"),
             help="Playlists, channels and @handles, mixed, on a timeline."),
        Item("A stream address", lambda: add_stream(app),
             help="One live stream (an .m3u8, a .ts, an rtsp:// camera, a radio station) as a channel."),
        Item("Stream channels", submenu=lambda: stream_items(app), value=lambda: str(len(cfg.stream_channels)),
             enabled=bool(cfg.stream_channels), help="The stream addresses you've added: SELECT one to remove it."),
    ]


def add_stream(app):
    cfg = app.config

    def got_url(url):
        url = (url or "").strip()
        if not url:
            return
        if "://" not in url:
            app.toast("A stream address has its scheme: https://, rtsp://, udp://...")
            return

        def got_name(name):
            if name is None:
                return
            cfg.stream_channels.append({"name": name.strip() or "Stream", "url": url})
            cfg.save()
            app.place_own_channels()
            _lists_changed(app)
            app.toast(f"{name.strip() or 'Stream'} added.")
        app.push(Keyboard(app, "Channel Name", got_name))
    app.push(Keyboard(app, "Stream address", got_url, hint="https://.../live.m3u8"))


def stream_items(app):
    cfg = app.config

    def drop(s):
        cfg.stream_channels.remove(s)
        cfg.save()
        app.place_own_channels()
        _lists_changed(app)
        app.top().back()
    return [Item(s.get("name") or "Stream", submenu=lambda s=s: _confirm(app, "Remove it", lambda: drop(s)),
                 help=s["url"][:80]) for s in cfg.stream_channels] or [Item("None yet", enabled=False)]


CHANNEL_SORTS = [("number", "Number"), ("name", "Name"), ("kind", "Kind")]


def move_channel(app, ch, d):
    """A channel swapped with its neighbour in the lineup (their numbers
    traded), the list following it."""
    from . import lineup as lu
    chans = sorted(_lineup_all(app), key=lambda c: c.number)
    if ch not in chans:
        return
    k = chans.index(ch) + (1 if d > 0 else -1)
    if not 0 <= k < len(chans):
        return
    other = chans[k]
    a, b = ch.number, other.number
    lu.edit(app.config, ch, number=b)
    lu.edit(app.config, other, number=a)
    _lineup_changed(app)
    m = app.top()
    if m is not None and getattr(m, "pages", None):
        items = m.pages[-1][1]
        at = next((n for n, it in enumerate(items) if it.label.endswith(f"  {ch.name}")), None)
        if at is not None:
            m.pages[-1][2] = at


def find_title(app):
    """Which channels play a title: each library and YouTube channel's
    titles searched; SELECT one to open its page."""
    from . import libchannels as lc, videochannels as vc

    def got(text):
        text = (text or "").strip().lower()
        if not text:
            return
        hits = []
        for ch in _lineup_all(app):
            tl = lc.SCHEDULES.get(vc.cid_of(ch)) if vc.is_video(ch) else None
            names = sorted({g["title"] for g in getattr(tl, "groups", None) or [] if text in g["title"].lower()})
            if names:
                hits.append((ch, names))
        app.top().open("FIND A TITLE", [
            Item(f"{ch.number:g}  {ch.name}", submenu=lambda ch=ch: channel_editor(app, ch),
                 value=f"{len(names)}", help="Has " + ", ".join(names[:6]) + ("..." if len(names) > 6 else ""))
            for ch, names in hits] or [Item("No channel plays that", enabled=False)])
    app.push(Keyboard(app, "Find a title", got, hint="Part of a show's or a movie's title."))


def bulk_items(app):
    """Bulk Edit: tick library channels, then one setting for them all."""
    from . import libchannels as lc
    cfg = app.config
    picked: set = set()

    def flip(c):
        picked.symmetric_difference_update({c["id"]})

    def chosen():
        return [c for c in cfg.library_channels if c["id"] in picked]

    def apply(key, value):
        cs = chosen()
        for c in cs:
            if value is None:
                c.pop(key, None)
            else:
                c[key] = value
            c["starter"] = False
        cfg.save()
        lc.rebuild(app)
        app.toast(f"Set on {len(cs)} channels.")

    def hide(on):
        from types import SimpleNamespace as NS
        from . import lineup as lu, videochannels as vc
        for c in chosen():
            lu.edit(cfg, NS(url=vc.SCHEME + lc.PREFIX + c["id"]), hide=on or None)
        _lineup_changed(app)

    def choices(key, options):
        return [Item(label, lambda v=v: apply(key, v), close=False) for v, label in options]

    def settings():
        if not picked:
            return [Item("Tick some channels first", enabled=False)]
        return [
            Item("Audience", submenu=lambda: choices("content", lc.CONTENT)),
            Item("Sorting Method", submenu=lambda: choices("order", lc.ORDERS)),
            Item("On the air", submenu=lambda: [Item(lab, lambda v=v: apply("hours", v), close=False)
                                                for v, lab in lc.HOURS]),
            Item("Commercials", submenu=lambda: [Item("On (each channel's usual)", lambda: apply("breaks", None)),
                                                 Item("Off", lambda: apply("breaks", {}))]),
            Item("Watched Filter", submenu=lambda: choices("watched", lc.WATCHED)),
            Item("Specials", submenu=lambda: choices("specials", [(True, "On"), (False, "Off")])),
            Item("Max Movies Per Day", submenu=lambda: choices("max_movies", MAX_MOVIES)),
            Item("Restrict Ratings After", submenu=lambda: [Item(lab, lambda v=v: apply("mature_from", v), close=False)
                                                            for v, lab in MATURE_FROM]),
            Item("Random Marathons", submenu=lambda: choices("marathons", [(True, "On"), (False, "Off")])),
            Item("Premieres", submenu=lambda: choices("premieres", lc.PREMIERES)),
            Item("Hide them", lambda: hide(True)),
            Item("Show them", lambda: hide(False)),
        ]
    return [Item("Set on the ticked channels", submenu=settings, value=lambda: str(len(picked)),
                 help="What to set on every ticked channel.")] + [
        Item(c.get("name") or "Library Channel", lambda c=c: flip(c), adjust=lambda d, c=c: flip(c),
             value=lambda c=c: "Ticked" if c["id"] in picked else "", help="SELECT ticks it; again unticks it.")
        for c in cfg.library_channels]


def hidden_items(app):
    """Hidden Channels: each shown again with SELECT, or all at once."""
    from . import lineup as lu
    cfg = app.config
    hid = [ch for ch in _lineup_all(app) if (cfg.channel_edits.get(ch.url) or {}).get("hide")]

    def show(chs):
        for ch in chs:
            lu.edit(cfg, ch, hide=None)
        _lineup_changed(app)
    def hide(chs):
        for ch in chs:
            lu.edit(cfg, ch, hide=True)
        _lineup_changed(app)

    def empty():
        from . import libchannels as lc, videochannels as vc
        return [ch for ch in _lineup_all(app) if vc.is_video(ch) and vc.cid_of(ch) in lc.SCHEDULES
                and not lc.SCHEDULES[vc.cid_of(ch)].entries]

    def starters():
        from . import libchannels as lc
        ids = {lc.PREFIX + c["id"] for c in cfg.library_channels if c.get("starter")}
        return [ch for ch in _lineup_all(app) if ch.url.split("://", 1)[-1] in ids]
    rows = [Item("Hide Empty Channels", lambda: hide(empty()),
                 help="Library and YouTube channels with nothing to play."),
            Item("Hide Starter Channels", lambda: hide(starters()),
                 help="The starter lineup's channels you haven't changed."),
            Item("Hide All", submenu=lambda: _confirm(app, "Hide every channel", lambda: hide(_lineup_all(app))),
                 help="Every channel hidden, to show again the ones you want.")]
    if not hid:
        return rows + [Item("No hidden channels", enabled=False,
                            help="Hide one on its page (Channel Visible): it's skipped by channel up and down and "
                                 "left out of the guide.")]
    return rows + [Item("Show All", lambda: show(hid), help="Every hidden channel back in the lineup.")] + [
        Item(f"{ch.number:g}  {ch.name}", lambda ch=ch: show([ch]), value=lambda: "Restore",
             help="SELECT shows it again.") for ch in hid]


def starter_items(app):
    """The starter lineup: made again (what's missing of it), or taken out."""
    from . import libchannels as lc
    cfg = app.config

    def make():
        if getattr(app, "library", None) is None:
            app.toast("Still reading your library. Try again in a moment.")
            return
        n = lc.add_starter(cfg, app.library)
        cfg.library_starter_done = True
        cfg.save()
        lc.place(app)
        _lists_changed(app)
        _refresh(app, {"Starter Lineup": lambda: starter_items(app)})
        app.toast(f"{n} channels added." if n else "Every starter channel is already here.")

    def drop():
        cfg.library_channels[:] = [c for c in cfg.library_channels if not c.get("starter")]
        cfg.save()
        lc.place(app)
        _lists_changed(app)
        _refresh(app, {"Starter Lineup": lambda: starter_items(app)})
    rows = [Item("Add the starter lineup", make,
                 help="Your channels as your Tunarr had them (their numbers, shows, movies, bumpers, logos and "
                      "screen bugs, with Cathode's dayparts), a few of Cathode's own, and every show or movie "
                      "nothing else has put on the channel it belongs on. Ones you already have (by name) are "
                      "left alone.")]
    if any(c.get("starter") for c in cfg.library_channels):
        rows.append(Item("Remove the starter lineup",
                         submenu=lambda: _confirm(app, "Remove its channels", drop, "Keep them"),
                         help="Takes out every channel the starter lineup made that you haven't changed. Channels "
                              "you made or changed stay."))
    return rows


def commercials_tab(app):
    """Settings > Commercials, as NostalgiaTV's: what every channel's breaks
    are made of, at once (each channel's page can still set its own), and
    which channels have breaks."""
    from . import libchannels as lc
    cfg, index = app.config, getattr(app, "library", None)
    if index is None:
        return [Item("Link Plex first", enabled=False,
                     help="Commercials and bumpers come from your Plex libraries of clips.")]

    def chans():
        return list(cfg.library_channels) + list(cfg.video_channels)

    def on():
        return [c for c in chans() if lc.breaks_of(c, index)]

    def done():
        cfg.save()
        lc.place(app)
        app.invalidate()

    def set_all(key, options, default, d):
        w = on()
        if not w:
            app.toast("No channel has breaks: turn them on under Channel Configuration.")
            return
        to = _cycle(options, lc.breaks_of(w[0], index).get(key, default), d)
        for c in w:
            c["breaks"] = dict(lc.breaks_of(c, index), **{key: to})
        done()

    def all_value(key, options, default):
        got = {lc.breaks_of(c, index).get(key, default) for c in on()}
        return _label(options, got.pop()) if len(got) == 1 else "Mixed" if got else "-"

    def has(c, skey):
        return any(x.get("section") == skey for x in lc.breaks_of(c, index).get("ads") or [])

    def lib_value(skey):
        w = on()
        n = sum(has(c, skey) for c in w)
        return "Off" if not n else "On" if n == len(w) else f"{n} of {len(w)}"

    def flip_lib(skey):
        w = on()
        add = not all(has(c, skey) for c in w)
        for c in w:
            b = dict(lc.breaks_of(c, index))
            b["ads"] = [x for x in b.get("ads") or [] if x.get("section") != skey] + (
                [{"section": skey, "kind": "all"}] if add else [])
            c["breaks"] = b
        done()

    def libs():
        secs = sorted((x for x in index.sections.values() if x.breaks or x.kind == "clip"),
                      key=lambda x: x.title.lower())
        return [Item(x.title, lambda x=x: flip_lib(x.key), adjust=lambda d, x=x: flip_lib(x.key),
                     value=lambda x=x: lib_value(x.key), help=f"{len(x.items):,} clips. SELECT: on every channel "
                                                               "with breaks, or off them all.")
                for x in secs] or [Item("No libraries of clips", enabled=False)]

    def flip(c, want=None):
        now = bool(lc.breaks_of(c, index))
        if want is None:
            want = not now
        if want == now:
            return
        if want:
            c.pop("breaks", None)                   # back to the defaults
            if not lc.breaks_of(c, index):
                c["breaks"] = lc.default_breaks(c, index)
        else:
            c["breaks"] = {}

    def flip_one(c):
        flip(c)
        done()

    def every(want):
        for c in chans():
            flip(c, want)
        done()

    def channel_rows():
        return [Item("Enable All", lambda: every(True), help="Breaks on every library and YouTube channel."),
                Item("Disable All", lambda: every(False), help="No breaks anywhere.")] + [
            Item(c.get("name") or "Channel", lambda c=c: flip_one(c), adjust=lambda d, c=c: flip_one(c),
                 value=lambda c=c: "On" if lc.breaks_of(c, index) else "Off") for c in chans()]
    lengths = [(n, f"{n // 60}:{n % 60:02d}") for n in lc.BREAK_LENGTHS]
    return [
        Item("Commercial Libraries", submenu=libs,
             help="The libraries every channel's commercials come from. Bumpers are each channel's own (its page)."),
        Item("Commercial Alignment", value=lambda: all_value("pad", lc.PADS, 30),
             adjust=lambda d: set_all("pad", lc.PADS, 30, d),
             help="Breaks fill to the next quarter hour, half hour or hour, so programmes start on time. No: "
                  "every break is the length below."),
        Item("Break Length", value=lambda: all_value("length", lengths, 120),
             adjust=lambda d: set_all("length", lengths, 120, d),
             help="A break during a programme, and every break when they don't line up with the clock."),
        Item("During Programmes", value=lambda: all_value("mid", lc.MIDS, "off"),
             adjust=lambda d: set_all("mid", lc.MIDS, "off", d),
             help="Breaks inside programmes of fifteen minutes or more: none, halfway, every so many minutes, "
                  "at chapter marks or at the quiet moments the show faded out for its own breaks."),
        Item("Commercials Per Break", value=lambda: all_value("count", lc.COUNTS, 0),
             adjust=lambda d: set_all("count", lc.COUNTS, 0, d),
             help="Fill the time, or just this many commercials each break."),
        Item("Coming Up Next Card", value=lambda: all_value("next_card", [(True, "On"), (False, "Off")], False),
             adjust=lambda d: set_all("next_card", [(False, "Off"), (True, "On")], False, d),
             help="The next programme's name on a card at the end of each break."),
        Item("Announcer", value=lambda: "On" if cfg.announcer else "Off",
             adjust=lambda d: (setattr(cfg, "announcer", not cfg.announcer), cfg.save()),
             help="A voice reads the coming-up-next card (Windows' own voice; espeak on Linux, where it's "
                  "installed)."),
        Item("Break Screen", submenu=lambda: break_screen_items(app),
             help="The slate when a break has time no commercial fits: its words and a picture of your own."),
        Item("Channel Configuration", submenu=channel_rows, value=lambda: f"{len(on())} of {len(chans())}",
             help="Which channels have breaks: SELECT one to turn them on or off."),
    ]


def break_screen_items(app):
    from . import logos
    cfg = app.config

    def words():
        def got(text):
            if text is not None:
                cfg.brb_text = text.strip()
                cfg.save()
        app.push(Keyboard(app, "The slate's words (empty = We'll be right back)", got, initial=cfg.brb_text))

    def picture(d):
        names = [""] + sorted(os.path.basename(p) for p in logos.files(cfg).values())
        cur = cfg.brb_image if cfg.brb_image in names else ""
        cfg.brb_image = names[(names.index(cur) + d) % len(names)]
        cfg.save()
        app.invalidate()
    return [Item("Words", words, value=lambda: cfg.brb_text or "We'll be right back"),
            Item("Picture", lambda: picture(1), value=lambda: cfg.brb_image or "None", adjust=picture,
                 help="A picture from your logos folder behind the slate and the coming-up-next card.")]


def schedule_tab(app):
    """Settings > Schedule, as NostalgiaTV's: the schedule drawn up afresh,
    the library read again, how far ahead the guide goes."""
    from . import libchannels as lc, videochannels as vc
    cfg = app.config
    days = [(2, "2 Days"), (7, "7 Days"), (14, "14 Days"), (30, "30 Days")]

    def length(d):
        cfg.guide_days = _cycle(days, int(cfg.guide_days or 2), d)
        cfg.save()
        vc.rebuild(app)

    def refresh_all():
        t = int(time.time())
        for c in list(cfg.library_channels) + list(cfg.video_channels):
            c["seed"] = t
        cfg.save()
        lc.rebuild(app)
        vc.rebuild(app)
        app.toast("Every channel drawn up again from now.", 6.0)

    def reread():
        app.toast("Reading your library...", 120.0)
        lc.start(app, fresh=True, done=lambda idx, err: (
            app.toast(f"{idx.count():,} titles in {len(idx.sections)} libraries." if idx and not err
                      else "Couldn't reach your Plex server.", 6.0)))

    def library_value():
        if getattr(app, "library_loading", False):
            p = getattr(app, "library_progress", None)
            return f"Reading {p[0]}" if p else "Reading..."
        lib = getattr(app, "library", None)
        return f"{lib.count():,} titles" if lib else "Not read yet"
    rows = [
        Item("Refresh Schedule", submenu=lambda: _confirm(app, "Refresh every channel", refresh_all,
                                                          "Keep the schedule"),
             help="Every library and YouTube channel drawn up again from now, in a fresh order: what's on now "
                  "changes. (A change to a channel applies by itself; this is a new shuffle.)"),
        Item("Refresh Library & Schedule", reread, value=library_value,
             help="Asks your server for everything it holds; new arrivals go on their channels. It checks for "
                  "changes by itself every few hours."),
        Item("Schedule Length", value=lambda: _label(days, int(cfg.guide_days or 2)), adjust=length,
             help="How far ahead the library and YouTube channels are drawn up and listed in the guide. Further "
                  "takes longer and more memory."),
    ]
    if cfg.epg_url:
        rows.append(Item("Refresh Listings", lambda: (app.load_epg(), app.toast("Loading the guide...")),
                         close=True, help="Fetch your playlist's guide again now."))
    return rows


def preference_items(app):
    """Settings > Preferences: subtitles, the channel logo, the screen,
    start-up, sound, the remote, the weather, YouTube."""
    cfg = app.config
    return [
        Item("Subtitles", submenu=lambda: subtitle_items(app), help="Subtitle language, size and look."),
        Item("Channel Logo", submenu=lambda: bug_items(app),
             value=lambda: f"{cfg.bug_opacity}%, {cfg.bug_corner}" if cfg.bug_on else "Off",
             help="The screen bug: the channel's logo in a corner of the picture, as stations ran theirs. A "
                  "channel's own page sets its own."),
        Item("Display", submenu=lambda: display_items(app), help="Full screen, and which screen to use."),
        Item("On Screen", submenu=lambda: on_screen_items(app),
             help="The up-next countdown, the rating box, the tuning screen, seasonal decorations, a TV's frame."),
        Item("Start-up", submenu=lambda: startup_items(app),
             help="The start-up screen, the screensaver, the box's sounds, the update check."),
        Item("Audio output", submenu=lambda: audio_items(app)),
        Item("Remote control", submenu=lambda: remote_items(app)),
        Item("Weather", submenu=lambda: weather_items(app)),
        Item("YouTube", submenu=lambda: youtube_items(app), help="Video quality, and what plays YouTube."),
    ]


BUG_MODES = [("always", "Always"), ("change", "On change"), ("periodic", "Periodic")]
BUG_ANCHORS = [("screen", "Screen"), ("picture", "4:3 picture")]
UPNEXT = [(0, "Off"), (10, "10 seconds"), (20, "20 seconds"), (30, "30 seconds"), (60, "A minute")]
TUNE_SCREENS = [("box", "The box's own"), ("static", "Static"), ("black", "Black"), ("blue", "Blue"),
                ("logo", "Channel logo")]


def on_screen_items(app):
    from .skins import overlays
    cfg = app.config

    def cyc(name, options):
        def f(d=1):
            setattr(cfg, name, _cycle(options, getattr(cfg, name), d))
            cfg.save()
            app.invalidate()
        return f

    def flip(name):
        def f(d=1):
            setattr(cfg, name, not getattr(cfg, name))
            cfg.save()
            app.invalidate()
        return f
    return [
        Item("Up Next Countdown", value=lambda: _label(UPNEXT, cfg.upnext_seconds), adjust=cyc("upnext_seconds", UPNEXT),
             help="Over a programme's last seconds on Cathode's channels: what's next and how long till it."),
        Item("Rating Box", value=lambda: "On" if cfg.rating_box else "Off", adjust=flip("rating_box"),
             help="The programme's rating (TV-PG, TV-14...) in a box top left as it starts, as networks ran it."),
        Item("Tuning Screen", value=lambda: _label(TUNE_SCREENS, cfg.tune_screen), adjust=cyc("tune_screen", TUNE_SCREENS),
             help="What covers a channel change: the box's own (snow on the analog ones, black on the digital), "
                  "static, black, blue, or the channel's logo."),
        Item("Seasonal Decorations", value=lambda: ("On" + (f" ({overlays.season()})" if overlays.season() else ""))
             if cfg.decorations else "Off", adjust=flip("decorations"),
             help="Snow in December, leaves in the autumn, hearts for Valentine's, stars for the Fourth, on the "
                  "guide."),
        Item("Bezel", value=lambda: _label(overlays.BEZELS, cfg.bezel), adjust=cyc("bezel", overlays.BEZELS),
             help="A television's frame round the screen: wood grain, black plastic or silver."),
    ]


def startup_items(app):
    from . import sounds
    cfg = app.config
    return [
        Item("Start-up screen", value=lambda: "On" if cfg.boot_sequence else "Off",
             adjust=lambda d: (setattr(cfg, "boot_sequence", not cfg.boot_sequence), cfg.save())),
        Item("Screensaver", value=lambda: "On" if cfg.screensaver else "Off",
             adjust=lambda d: (setattr(cfg, "screensaver", not cfg.screensaver), cfg.save())),
        *([Item("Sound effects", value=lambda: _label(sounds.LEVELS, cfg.sound_effects),
                adjust=lambda d: (setattr(cfg, "sound_effects", _cycle(sounds.LEVELS, cfg.sound_effects, d)), cfg.save(),
                                  app.sound("key")),
                help="The box's key sounds and its error bonk, as the HR20 had them.")]
          if getattr(app.skin, "ui_sounds", False) else []),
        Item("Check for updates at start-up", value=lambda: "Yes" if cfg.update_check else "No",
             adjust=lambda d: (setattr(cfg, "update_check", not cfg.update_check), cfg.save())),
    ]


def youtube_items(app):
    from . import ytdl
    cfg = app.config
    heights = [(h, f"{h}p") for h in (1080, 720, 480, 360)]

    def quality(d):
        cfg.video_quality = _cycle(heights, int(cfg.video_quality or 1080), d)
        cfg.save()
    return [
        Item("Video quality", value=lambda: _label(heights, int(cfg.video_quality or 1080)), adjust=quality,
             help="The tallest picture a video plays in. If videos stop to buffer, go lower: 720p takes about half "
                  "the bandwidth of 1080p. Takes effect at the next video."),
        Item("YouTube support", lambda: app.check_ytdl(manual=True), value=lambda: f"yt-dlp {ytdl.version()}",
             help="yt-dlp resolves the videos. YouTube changes break it now and then: SELECT fetches the newest "
                  "release (checked weekly on its own); it takes over at the next start."),
    ]


def server_items(app):
    """Settings > Servers: Plex, and Jellyfin, Emby and folders."""
    cfg = app.config
    od = app.ondemand
    plex = Item("Plex", submenu=lambda: ondemand_settings(app), value=lambda: "Linked",
                help="Quality, which libraries On Demand shows, who's watching, unlinking.") if od.signed_in else         Item("Link Plex", lambda: open_ondemand(app), close=True,
             help="Link your Plex account: the library channels and On Demand come from it.")
    return [plex,
            Item("Jellyfin, Emby and folders", submenu=lambda: places_items(app),
                 value=lambda: str(len(cfg.media_servers) + len(cfg.local_folders)),
                 help="More places for library channels to draw from, beside Plex.")]


def admin_items(app):
    """Settings > Admin: the phone remote, other Cathodes, sharing the
    channels, backups, diagnostics, updates."""
    from . import __version__, update_flow
    from .screens.diagnostics import Diagnostics
    cfg = app.config

    def sync_value():
        sy = getattr(app, "sync", None)
        if not cfg.lan_sync or sy is None:
            return "Off"
        names = sorted(p["name"] for p in sy.others())
        return ("On: " + ", ".join(names))[:32] if names else "On, none found"

    def sync_toggle(d=0):
        from . import sync
        cfg.lan_sync = not cfg.lan_sync
        cfg.save()
        sync.restart(app)

    def web_toggle(key):
        from . import sync
        setattr(cfg, key, not getattr(cfg, key))
        cfg.save()
        sync.restart(app)

    def web_value():
        from . import web
        sy = getattr(app, "sync", None)
        if not cfg.web_remote or sy is None or not sy.port:
            return "Off"
        return f"http://{web.my_address()}:{sy.port}"

    def show_qr():
        from . import sync
        if not cfg.web_remote:
            cfg.web_remote = True
            cfg.save()
            sync.restart(app)
        addr = web_value()
        if addr == "Off":
            app.toast("The phone remote couldn't start: is another app using its port?", 6.0)
            return
        from .screens.qrcode import QrCode
        app.push(QrCode(app, addr, "Phone remote", "Point your phone's camera here, on the same Wi-Fi."))
    return [
        Item("Phone remote", show_qr, value=web_value, adjust=lambda d: web_toggle("web_remote"),
             help="SELECT shows its address as a QR code: point a phone's camera at it (on your network) for a "
                  "remote, the channels with what's on (tap to tune), and the lineup and channel settings. "
                  "LEFT/RIGHT turns it on or off."),
        Item("Sync with other Cathodes", sync_toggle, value=sync_value, adjust=sync_toggle,
             help="Every Cathode on your network keeps the same channels: the lists, the library channels' "
                  "schedules and the YouTube lists. The same channel shows the same thing on each. The last edit "
                  "made on any of them wins."),
        Item("Share channels with other apps", lambda: web_toggle("share_channels"),
             value=lambda: "On" if cfg.share_channels else "Off", adjust=lambda d: web_toggle("share_channels"),
             help="The library channels for other apps on your network: /lineup.m3u and /xmltv.xml at the Phone "
                  "remote's address, and as an HDHomeRun tuner there. Their players get the programme on the air "
                  "through Plex's transcoder; the address carries your Plex token."),
        Item("Back up settings", lambda: _back_up(app),
             help="Every setting to a file in the settings folder's backups (one is also made by itself each week). "
                  "Your Plex, Jellyfin and Emby sign-ins aren't in it; playlist links are."),
        Item("Restore settings", submenu=lambda: restore_items(app),
             help="Put the settings back as a backup has them. Sign-ins stay as they are."),
        Item("Diagnostics", lambda: app.push(Diagnostics(app)), close=True),
        Item("Save diagnostics", lambda: _save_diagnostics(app),
             help="One zip on your Desktop to attach to a bug report: logs, settings without passwords, system."),
        Item("Check for updates", lambda: update_flow.open_check(app)),
        Item(f"Cathode {__version__}", enabled=False),
    ]


# ── On Demand ─# ── On Demand ─────────────────────────────────────────────────────────────

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
        Item("Edit this channel", lambda: open_channel_editor(app, ch), close=True, enabled=ch is not None,
             help="Its name, number, logo and bug; for a library or YouTube channel what it plays and how."),
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


BUG_SIZES = [(5, "Tiny"), (7, "Small"), (9, "Medium"), (12, "Large"), (16, "Huge")]
BUG_OPACITY = [5, 10, 15, 20, 25, 30, 40, 50, 60, 75, 100]
BUG_MARGINS = [(2, "Close"), (4, "Normal"), (6, "Wide"), (9, "Wider")]


def bug_items(app):
    """The screen bug: on or off, its corner, size, opacity, distance from
    the edge, white or in colour, and whether it stays up during breaks."""
    from . import logos
    from .skins import Skin
    cfg = app.config

    def set_and(fn):
        def run(d=1):
            fn(d)
            cfg.save()
            app.invalidate()
        return run

    def step(name, options, d):
        keys = [k if not isinstance(k, tuple) else k[0] for k in options]
        cur = getattr(cfg, name)
        i = keys.index(cur) if cur in keys else 0
        setattr(cfg, name, keys[max(0, min(len(keys) - 1, i + d))])
    corners = [(c, c.capitalize()) for c in Skin.BUG_CORNERS]
    return [
        Item("Screen bug", set_and(lambda d: setattr(cfg, "bug_on", not cfg.bug_on)),
             value=lambda: "On" if cfg.bug_on else "Off", adjust=set_and(lambda d: setattr(cfg, "bug_on", not cfg.bug_on)),
             help="The channel's logo, faint, in a corner, on every channel. A channel with a look of its own "
                  "(your Tunarr ones; any, from its page's Screen Bug) keeps its corner, size and opacity."),
        Item("Corner", value=lambda: _label(corners, cfg.bug_corner),
             adjust=set_and(lambda d: setattr(cfg, "bug_corner", _cycle(corners, cfg.bug_corner, d)))),
        Item("Size", value=lambda: _label(BUG_SIZES, cfg.bug_size), adjust=set_and(lambda d: step("bug_size", BUG_SIZES, d))),
        Item("Opacity", value=lambda: f"{cfg.bug_opacity}%", adjust=set_and(lambda d: step("bug_opacity", BUG_OPACITY, d))),
        Item("Distance from the edge", value=lambda: _label(BUG_MARGINS, cfg.bug_margin),
             adjust=set_and(lambda d: step("bug_margin", BUG_MARGINS, d))),
        Item("Look", value=lambda: "White" if cfg.bug_white else "In its colors",
             adjust=set_and(lambda d: setattr(cfg, "bug_white", not cfg.bug_white)),
             help="White: the logo's shape in white, as most stations ran theirs."),
        Item("During breaks", value=lambda: "Shown" if cfg.bug_in_breaks else "Hidden",
             adjust=set_and(lambda d: setattr(cfg, "bug_in_breaks", not cfg.bug_in_breaks)),
             help="Cathode's own channels take the bug down for commercials and bumpers."),
        Item("Logo Mode", value=lambda: _label(BUG_MODES, cfg.bug_mode),
             adjust=set_and(lambda d: setattr(cfg, "bug_mode", _cycle(BUG_MODES, cfg.bug_mode, d))),
             help="Always; On change: fifteen seconds after you tune and as each programme starts; Periodic: half "
                  "a minute in every ten, as stations flashed theirs."),
        Item("Anchor", value=lambda: _label(BUG_ANCHORS, cfg.bug_anchor),
             adjust=set_and(lambda d: setattr(cfg, "bug_anchor", _cycle(BUG_ANCHORS, cfg.bug_anchor, d))),
             help="The screen's corner, or a 4:3 picture's corner on a wide screen (inside the black bars)."),
        Item("Your logos", enabled=False, value=lambda: logos.folder(cfg),
             help="Put a picture named for a channel in this folder (Nickelodeon.gif, 107.png; GIF and APNG "
                  "animate) and it's that channel's logo. Name one 'Nickelodeon bug.png' for its screen bug. "
                  "A channel's edit page can pick one too."),
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

def source_items(app):
    """Live TV Sources: your playlists (SELECT one for its page), one more,
    or none (only Cathode's own channels)."""
    from . import lineup as lu
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
        app.config.playlist_url, app.config.epg_url = lu.NONE, ""
        app.config.save()
        app.switch_playlist({"playlist_url": lu.NONE, "epg_url": ""})
    items.append(Item(("> " if cfg.playlist_url == lu.NONE else "  ") + "No playlist", no_playlist, close=True,
                      help="Only Cathode's own channels: the library, YouTube, TV Guide and Weather channels."))
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
            _lists_changed(app)
        else:
            vc.rebuild(app)
        app.invalidate()

    def set_name():
        def got(text):
            if text is None:
                return
            c["name"] = text.strip()
            save()
        app.push(Keyboard(app, "Channel Name (empty = its first source's)", got, initial=c.get("name", "")))

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
        app.top().back()
        _lists_changed(app)

    def move(d):
        lst = cfg.video_channels
        i = lst.index(c)
        if 0 <= i + d < len(lst):
            lst[i], lst[i + d] = lst[i + d], lst[i]
            save()
    rows = timeline_items(app, c, cid, save, unit="videos", default="mix")
    return [
        Item("Channel Name", set_name, value=lambda: c.get("name") or "(its first source's)",
             help="The channel's name in the lineup and the guide. Empty: named for its first source."),
        Item("Channel Number", set_number, value=number_value,
             help="Automatic (after the lineup's last number) or one you choose; a taken number moves to the next free."),
        *_lineup_rows(app, vc.SCHEME + cid),
        *rows[:-2],
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
        Item("Content", submenu=lambda: video_source_items(app, cid), value=lambda: str(len(c.get("sources") or [])),
             help="The playlists, channels and @handles this channel mixes."),
        *rows[-2:],
        Item("Refresh Schedule", refresh,
             help="Fetches every source's list again, draws up today's running order anew (your changes "
                  "to the sources and their order included) and starts the channel over if it's on."),
        Item("Move up", lambda: move(-1), enabled=cfg.video_channels.index(c) > 0,
             help="Earlier in the list: channels numbered automatically take the lower number."),
        Item("Move down", lambda: move(1), enabled=cfg.video_channels.index(c) < len(cfg.video_channels) - 1),
        Item("Make a copy", lambda: _copy_channel(app, cfg.video_channels, c, video_channel_page),
             help="The same channel again, to change into another."),
        Item("Remove channel", submenu=lambda: _confirm(app, "Remove channel", remove, "Keep it")),
    ]


# ── Other places: Jellyfin and Emby servers, folders ─────────────────────

def places_items(app):
    from . import folders, jellyfin, libchannels as lc
    cfg = app.config

    def reread():
        app.toast("Reading your libraries...", 60.0)
        lc.start(app, done=lambda idx, err: app.toast(
            f"{idx.count():,} titles in {len(idx.sections)} libraries." if idx else "Nothing could be read.", 6.0))

    def add_server():
        got = {}

        def password(text):
            if text is None:
                return
            app.toast("Signing in...", 30.0)

            def work():
                return jellyfin.sign_in(got["url"], got["user"], text, cfg.sync_id or "")
            app.ondemand.run(work, lambda s: (cfg.media_servers.append(s), cfg.save(),
                                              app.toast(f"{s['kind']}: {s['name']} added.", 5.0), reread()),
                             lambda msg: app.toast("Couldn't sign in: check the address, the name and the password.", 6.0))

        def user(text):
            if text:
                got["user"] = text.strip()
                app.push(Keyboard(app, "Password", password, hint="Used once to sign in; only the sign-in is kept."))

        def url(text):
            if text and text.strip() != Keyboard.URL_START:
                got["url"] = text.strip()
                app.push(Keyboard(app, "User name", user))
        app.push(Keyboard(app, "Jellyfin or Emby address (http://...:8096)", url, url=True))

    def add_folder():
        def got(text):
            path = (text or "").strip()
            if not path:
                return
            if not os.path.isdir(path):
                app.toast("That folder isn't there.")
                return
            cfg.local_folders.append({"path": path, "name": os.path.basename(path.rstrip("/\\")) or path, "kind": "movie"})
            cfg.save()
            app.top().refresh(places_items(app))
            reread()
        app.push(Keyboard(app, "Folder (its full path)", got, hint="Movies, shows by SxxEyy, or clips; set which after."))

    def server_page(s):
        def remove():
            cfg.media_servers[:] = [x for x in cfg.media_servers if x is not s]
            cfg.save()
            m = app.top()
            m.back()
            m.refresh(places_items(app))
            reread()
        return [Item("Address", value=lambda: s["url"]), Item("Signed in as", value=lambda: s.get("user", "")),
                Item("Remove server", submenu=lambda: _confirm(app, "Remove it", remove, "Keep it"))]

    def folder_page(f):
        def kind(d):
            f["kind"] = _cycle(folders.KINDS, f.get("kind", "movie"), d)
            cfg.save()

        def remove():
            cfg.local_folders[:] = [x for x in cfg.local_folders if x is not f]
            cfg.save()
            m = app.top()
            m.back()
            m.refresh(places_items(app))
            reread()
        return [Item("Folder", value=lambda: f["path"][-30:]),
                Item("Holds", value=lambda: _label(folders.KINDS, f.get("kind", "movie")), adjust=kind,
                     help="Movies; shows (episodes found by S01E02 in their names, the show named for its folder); "
                          "or clips, bumpers and commercials, for breaks. Read the libraries again after changing it."),
                Item("Remove folder", submenu=lambda: _confirm(app, "Remove it", remove, "Keep it"))]
    rows = [Item(f"{s.get('kind', 'Jellyfin')}: {s.get('name', s['url'])}", submenu=lambda s=s: server_page(s))
            for s in cfg.media_servers]
    rows.append(Item("Add a Jellyfin or Emby server...", add_server,
                     help="Its libraries join Plex's for library channels and breaks. A title on both is kept from Plex."))
    rows += [Item(f"Folder: {f.get('name') or f['path']}", submenu=lambda f=f: folder_page(f),
                  value=lambda f=f: _label(folders.KINDS, f.get("kind", "movie"))) for f in cfg.local_folders]
    rows.append(Item("Add a folder...", add_folder,
                     help="Videos on this computer: MP4, MKV, WebM, MOV and AVI files, their lengths read from them."))
    rows.append(Item("Read the libraries again", reread))
    return rows


# ── Profiles, the parent PIN, the watch history (profiles.py) ────────────

def _pin_then(app, go):
    """go(), after the parent PIN when a kids' profile is on and there is one."""
    from . import profiles
    cfg = app.config
    if not profiles.is_kids(cfg) or not cfg.parent_pin:
        return go()

    def got(text):
        if text is not None and text.strip() == cfg.parent_pin:
            go()
        elif text is not None:
            app.toast("That's not the parent PIN.")
    app.push(Keyboard(app, "Parent PIN", got, hint="A grown-up's to enter."))


def _who_name(app) -> str:
    from . import profiles
    return profiles.active(app.config)["name"]


def who_items(app):
    """Who's watching: the main profile and the others; SELECT switches."""
    from . import profiles
    cfg = app.config
    on = profiles.active(cfg)

    def go(pid):
        def done():
            profiles.switch(app, pid)
            app.toast(f"Watching as {profiles.active(cfg)['name']}.")
            m = app.top()
            if hasattr(m, "close"):
                m.close()
        _pin_then(app, done) if on.get("kids") else done()
    rows = [Item(("> " if not on["id"] else "  ") + (cfg.main_fields.get("_name") or "Main"), lambda: go(""))]
    rows += [Item(("> " if on["id"] == p["id"] else "  ") + p["name"], lambda p=p: go(p["id"]),
                  value=lambda p=p: "Kids" if p.get("kids") else "") for p in cfg.profiles]
    return rows


def profile_items(app):
    from . import profiles
    cfg = app.config

    def add():
        def got(text):
            text = (text or "").strip()
            if text:
                profiles.new(cfg, text)
                cfg.save()
                app.top().refresh(profile_items(app))
        app.push(Keyboard(app, "Profile name", got, hint="It starts with the look on now and no favourites."))

    def set_pin():
        def got(text):
            if text is None:
                return
            pin = text.strip()
            if pin and not (pin.isdigit() and 4 <= len(pin) <= 8):
                app.toast("A PIN is four to eight digits.")
                return
            cfg.parent_pin = pin
            cfg.save()
            app.toast("Parent PIN set." if pin else "No parent PIN.")
        _pin_then(app, lambda: app.push(Keyboard(app, "Parent PIN (empty = none)", got,
                                                 hint="Four to eight digits. Kids' profiles need it for Settings.")))
    rows = [Item("Who's watching", submenu=lambda: who_items(app), value=lambda: profiles.active(cfg)["name"],
                 help="Switch profile: each has its own look and favourites.")]
    rows += [Item(p["name"], submenu=lambda p=p: profile_page(app, p), value=lambda p=p: "Kids" if p.get("kids") else "")
             for p in cfg.profiles]
    rows.append(Item("Add a profile...", add))
    rows.append(Item("Parent PIN", set_pin, value=lambda: "Set" if cfg.parent_pin else "None",
                     help="Asked of a kids' profile for Settings and for switching to another profile."))
    rows.append(Item("Watch history", submenu=lambda: history_items(app),
                     help="What was watched, when and for how long, the last month."))
    return rows


def profile_page(app, p):
    from . import profiles
    cfg = app.config

    def rename():
        def got(text):
            if text and text.strip():
                p["name"] = text.strip()
                cfg.save()
        app.push(Keyboard(app, "Profile name", got, initial=p["name"]))

    def kids(d=0):
        p["kids"] = not p.get("kids")
        cfg.save()
        if profiles.active(cfg)["id"] == p["id"]:
            app.relineup()

    def remove():
        if profiles.active(cfg)["id"] == p["id"]:
            profiles.switch(app, "")
        cfg.profiles[:] = [x for x in cfg.profiles if x is not p]
        cfg.save()
        m = app.top()
        m.back()
        m.refresh(profile_items(app))
    return [
        Item("Name", rename, value=lambda: p["name"]),
        Item("Kids' profile", kids, value=lambda: "On" if p.get("kids") else "Off", adjust=kids,
             help="On: only the channels marked for kids (On kids' profiles, on a channel's page) and library channels set "
                  "to kids' ratings; Settings ask for the parent PIN."),
        Item("Remove profile", submenu=lambda: _confirm(app, "Remove profile", remove, "Keep it")),
    ]


def history_items(app):
    from . import profiles
    rows = profiles.history()

    def clear():
        profiles.clear()
        m = app.top()
        m.back()
        m.refresh(profile_items(app))
    out = [Item("Most watched this week", submenu=lambda: [
        Item(ch, value=lambda h=h: f"{h:.1f} h") for ch, h in profiles.most_watched(profiles.history())]
        or [Item("Nothing yet", enabled=False)])]
    for r in sorted(rows, key=lambda r: -r["t"])[:60]:
        when = time.strftime("%a %I:%M %p", time.localtime(r["t"])).replace(" 0", " ")
        out.append(Item(f"{when}  {r['num']:g} {r['ch']}", value=lambda r=r: f"{max(1, r['s'] // 60)} min",
                        help=(r.get("title") or "") + (f"  ({r['who']})" if r.get("who") else "")))
    out.append(Item("Clear the history", submenu=lambda: _confirm(app, "Clear it", clear, "Keep it")))
    return out


# ── The lineup: hide, rename, renumber, packs (lineup.py) ────────────────

def _lineup_changed(app):
    app.config.save()
    app.relineup()
    _lists_changed(app)


def _packs_page(app, url):
    from . import lineup as lu
    cfg = app.config

    def flip(p):
        keys = p.setdefault("keys", [])
        (keys.remove if url in keys else keys.append)(url)
        cfg.save()
        app._cats = None
    return [Item(p["name"], lambda p=p: flip(p), adjust=lambda d, p=p: flip(p),
                 value=lambda p=p: "In" if url in (p.get("keys") or []) else "-") for p in lu.packs(cfg)] or \
        [Item("No packs yet", enabled=False, help="Make one under Settings > Channels > Channel Packs.")]


def _pick(app, url, kind, d):
    """A picture from the logos folder for a channel's logo or bug, in
    turn: as it comes, then each file."""
    from types import SimpleNamespace as NS
    from . import logos, lineup as lu
    cfg = app.config
    names = sorted(os.path.basename(p) for p in logos.files(cfg).values())
    options = [""] + names
    cur = (cfg.channel_edits.get(url) or {}).get(kind, "")
    lu.edit(cfg, NS(url=url), **{kind: options[((options.index(cur) if cur in options else 0) + d) % len(options)]})
    cfg.save()
    app.invalidate()


def _picked(app, url, kind):
    v = (app.config.channel_edits.get(url) or {}).get(kind, "")
    return "None" if v == "off" else v or ("Its logo" if kind == "bug" else "Automatic")


def _lineup_rows(app, url, fallback=None) -> list:
    """The rows every channel's page has: favourite, shown or hidden, packs,
    logo and screen bug (what the lineup keeps by the channel's address)."""
    from types import SimpleNamespace as NS
    from . import lineup as lu
    cfg = app.config

    def ch():
        return _by_url(app, url) or fallback
    if ch() is None:
        return []

    def e():
        return cfg.channel_edits.get(url) or {}

    def fav(d=0):
        app.toggle_favorite(ch())

    def show(d=0):
        lu.edit(cfg, NS(url=url), hide=not e().get("hide"))
        _lineup_changed(app)

    def bug_value():
        own = app.skin.own_bug(ch()) if hasattr(getattr(app, "skin", None), "own_bug") else {}
        if not cfg.bug_on or own.get("off") or e().get("bug") == "off":
            return "Off"
        return (own.get("corner") or cfg.bug_corner).capitalize()
    return [
        Item("Favorite", fav, value=lambda: "Yes" if ch().number in cfg.favorites else "No", adjust=fav,
             help="Starred: in the guide's Favorites."),
        Item("Channel Visible", show, value=lambda: "No" if e().get("hide") else "Yes", adjust=show,
             help="Hidden channels are skipped by channel up and down and left out of the guide."),
        Item("Channel Packs", submenu=lambda: _packs_page(app, url),
             value=lambda: str(sum(url in (p.get("keys") or []) for p in lu.packs(cfg)))),
        Item("Custom Logo", lambda: _pick(app, url, "logo", 1), value=lambda: _picked(app, url, "logo"),
             adjust=lambda d: _pick(app, url, "logo", d),
             help="A picture from your logos folder (a GIF or APNG moves). Automatic: one named for the channel, "
                  "else the one it came with."),
        Item("Logo From a Web Address", lambda: _logo_url(app, url),
             help="A picture's address (https://...png, .gif, .svg): the channel's logo. Empty: back to automatic."),
        Item("Screen Bug", submenu=lambda: channel_bug_items(app, url, fallback), value=bug_value,
             help="The logo in the corner on this channel: on or off, its picture, where, how big, how faint."),
    ]


def _logo_url(app, url):
    from types import SimpleNamespace as NS
    from . import lineup as lu
    cur = (app.config.channel_edits.get(url) or {}).get("logo", "")

    def got(text):
        if text is None:
            return
        text = text.strip()
        if text and not text.lower().startswith(("http://", "https://")):
            app.toast("A web address starts with http:// or https://.")
            return
        lu.edit(app.config, NS(url=url), logo=text or None)
        app.config.save()
        app.invalidate()
        _lists_changed(app)
    app.push(Keyboard(app, "Logo's web address", got, initial=cur if cur.startswith("http") else ""))


BUG_WIDTHS = [5, 7, 8, 10, 12, 15, 20]          # a channel's own bug: its width, % of the picture's
BUG_EDGES = [2, 3, 5, 7, 9]                     # its distance from the edges, %


def _step(values, cur, d):
    """The next value up (d > 0) or down from cur, which needn't be one of
    them (Tunarr's 35% opacity), round at the ends."""
    vals = sorted(values)
    if d > 0:
        return next((v for v in vals if v > cur), vals[0])
    return next((v for v in reversed(vals) if v < cur), vals[-1])


def channel_bug_items(app, url, fallback=None):
    """A channel's own screen bug: on or off, its picture, corner, size,
    opacity, distance from the edge; or back to how it came."""
    from types import SimpleNamespace as NS
    from . import lineup as lu
    from .skins import Skin
    cfg = app.config
    at = NS(url=url)

    def e():
        return cfg.channel_edits.get(url) or {}

    def own():
        c = _by_url(app, url) or fallback
        return app.skin.own_bug(c) if c is not None and hasattr(getattr(app, "skin", None), "own_bug") else {}

    def look(**kw):
        lk = dict(e().get("bug_look") or {})
        lk.update(kw)
        lu.edit(cfg, at, bug_look=lk)
        cfg.save()
        app.invalidate()

    def shown():
        return not own().get("off") and e().get("bug") != "off"

    def show(d=0):
        if shown():
            look(off=True)
        else:
            look(off=False)
            if e().get("bug") == "off":
                lu.edit(cfg, at, bug=None)
                cfg.save()

    def reset():
        lu.edit(cfg, at, bug_look=None, bug=None)
        cfg.save()
        app.invalidate()
    corners = [(k, k.capitalize()) for k in Skin.BUG_CORNERS]

    def corner():
        return own().get("corner") or cfg.bug_corner

    def edge():
        m = own().get("margin")
        return m[0] if m else None
    return [
        Item("Show It", show, value=lambda: "On" if shown() else "Off", adjust=show,
             help="This channel's bug on or off. (Preferences > Channel Logo turns every channel's off.)"),
        Item("Picture", lambda: _pick(app, url, "bug", 1), value=lambda: _picked(app, url, "bug"),
             adjust=lambda d: _pick(app, url, "bug", d),
             help="Its logo, or a picture from your logos folder."),
        Item("Position", value=lambda: _label(corners, corner()), adjust=lambda d: look(corner=_cycle(corners, corner(), d))),
        Item("Size", value=lambda: f"{own()['width']:g}% wide" if own().get("width") else "As every channel",
             adjust=lambda d: look(width=_step(BUG_WIDTHS, own().get("width") or 9, d)),
             help="Its width, a share of the picture's."),
        Item("Opacity", value=lambda: f"{own().get('opacity', cfg.bug_opacity):g}%",
             adjust=lambda d: look(opacity=_step(BUG_OPACITY, own().get("opacity", cfg.bug_opacity), d))),
        Item("Distance from the Edge", value=lambda: f"{edge():g}%" if edge() else "As every channel",
             adjust=lambda d: look(margin=[_step(BUG_EDGES, edge() or 4, d)] * 2)),
        Item("As It Came", reset,
             help="Back to how it came: Tunarr's look on a channel made from your Tunarr setup, else the one "
                  "every channel has (Preferences > Channel Logo)."),
    ]


def channel_edit_items(app, ch):
    """A channel from a playlist (or one of Cathode's own): its name and
    number in the lineup, and the rows every channel has."""
    from . import lineup as lu
    cfg = app.config

    def e():
        return cfg.channel_edits.get(ch.url) or {}

    def rename():
        def got(text):
            if text is not None:
                lu.edit(cfg, ch, name=text.strip() or None)
                _lineup_changed(app)
        app.push(Keyboard(app, "Channel Name (empty = as it came)", got, initial=e().get("name", "")))

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
        app.push(Keyboard(app, "Channel Number (empty = as it came; 10.5 is fine)", got,
                          initial=f"{e()['number']:g}" if "number" in e() else ""))

    def reset():
        cfg.channel_edits.pop(ch.url, None)
        _lineup_changed(app)

    def kids(d=0):
        lu.edit(cfg, ch, kids=not e().get("kids"))
        _lineup_changed(app)
    orig = getattr(ch, "orig", (ch.name, ch.number))
    return [
        Item("Channel Name", rename, value=lambda: e().get("name") or orig[0], help=f"As it came: {orig[0]}"),
        Item("Channel Number", renumber, value=lambda: f"{e().get('number', orig[1]):g}",
             help=f"As it came: {orig[1]:g}. A taken number is shared: the guide lists them side by side."),
        *_lineup_rows(app, ch.url, ch),
        Item("On kids' profiles", kids, value=lambda: "Shown" if e().get("kids") else "-", adjust=kids,
             help="Kids' profiles see only the channels shown here (and library channels for Kids)."),
        Item("As it came", reset, enabled=bool(e()), help="Its own name and number, shown, its own logo and bug."),
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
        Item("Sorting Method", value=lambda: _label(lc.ORDERS, c.get("order", default)), adjust=order,
             help=ORDER_HELP.get(c.get("order", default), "") + "  LEFT/RIGHT changes it."),
        Item("Block Size", value=block_value, adjust=block,
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
        Item("Commercials", submenu=lambda: breaks_items(app, c, save),
             value=lambda: "On" if lc.breaks_of(c, getattr(app, "library", None)) else "Off",
             help="This channel's breaks: commercials and its bumpers from your Plex libraries between programmes "
                  "and in long ones, lined up with the clock."),
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
        return lc.breaks_of(c, index)

    def ensure():
        if not c.get("breaks"):
            c["breaks"] = lc.default_breaks(c, index)
        return c["breaks"]

    def toggle(d=0):
        if b():
            c["breaks"] = {}                        # off
        else:
            c.pop("breaks", None)                   # back to the defaults
            if not b():
                c["breaks"] = lc.default_breaks(c, index)
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
        secs = sorted((s for s in index.sections.values() if s.breaks or s.kind in ("clip", "music")),
                      key=lambda s: s.title.lower())
        return [Item(s.title, lambda s=s: flip(key, s.key), adjust=lambda d, s=s: flip(key, s.key),
                     value=lambda s=s: "On" if any(x.get("section") == s.key for x in b().get(key) or []) else "Off",
                     help=f"{len(s.items):,} clips.") for s in secs] or \
            [Item("No libraries of clips", enabled=False, help="Plex Other Videos libraries of commercials or bumpers.")]

    def cycle(key, options, default, d):
        ensure()[key] = _cycle(options, b().get(key, default), d)
        save(place=False)
    lengths = [(n, f"{n // 60}:{n % 60:02d}") for n in lc.BREAK_LENGTHS]
    return [
        Item("Breaks", toggle, value=lambda: "On" if b() else "Off", adjust=toggle,
             help="On (as every channel starts): commercials between programmes from the libraries below (your "
                  "commercials libraries, and bumpers named for the channel's studio)."),
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
        Item("During programmes", value=lambda: _label(lc.MIDS, b().get("mid", "off")),
             adjust=lambda d: cycle("mid", lc.MIDS, "off", d),
             help="Breaks inside programmes of fifteen minutes or more: halfway, every so many minutes, at the "
                  "chapter marks Plex has, or at the quiet moments where the show faded out for its own breaks "
                  "(each title's sound is read once, in the background; until then, halfway)."),
        Item("Commercials Per Break", value=lambda: _label(lc.COUNTS, int(b().get("count") or 0)),
             adjust=lambda d: cycle("count", lc.COUNTS, 0, d),
             help="Fill the time (to the clock, or the break length), or just this many commercials each break."),
        Item("Running Order", value=lambda: "In order" if b().get("ad_order") == "in_order" else "Shuffled",
             adjust=lambda d: (ensure().__setitem__("ad_order", None if b().get("ad_order") == "in_order"
                                                     else "in_order"), save(place=False)),
             help="Shuffled, or the commercials one after another in their order, carrying on break to break."),
        Item("Pick Commercials", submenu=lambda: pick_ads(app, c, save, ensure),
             help="Commercials one by one from your libraries, instead of whole libraries."),
        Item("Idents from", submenu=lambda: libs("idents"), value=lambda: str(len(b().get("idents") or [])),
             help="The station's own IDs: one between programmes, ahead of the bumper and the commercials."),
        Item("Long Videos as Commercials", submenu=lambda: long_libs(app, c, save, ensure),
             help="A TV show (or movies, or long clips) of old commercials, cut into 30 to 90 second pieces."),
        Item("Coming Up Next Card", value=lambda: "On" if b().get("next_card") else "Off",
             adjust=lambda d: (ensure().__setitem__("next_card", not b().get("next_card")), save(place=False)),
             help="The next programme's name on a card for eight seconds at the end of the break."),
    ]


def pick_ads(app, c, save, ensure):
    """Commercials ticked one by one: a source of picked titles per library."""
    from . import libchannels as lc
    index = app.library

    def srcs():
        return ensure().setdefault("ads", [])

    def picked(sec):
        return next((s for s in srcs() if s.get("section") == sec.key and s.get("kind") == "title"), None)

    def flip(sec, i):
        s = picked(sec)
        if s is None:
            s = {"section": sec.key, "kind": "title", "value": []}
            srcs().append(s)
        vals = s["value"]
        (vals.remove if i["plex"] in vals else vals.append)(i["plex"])
        if not vals:
            srcs().remove(s)
        save(place=False)

    def clips(sec):
        return [Item(i["title"], lambda i=i: flip(sec, i), adjust=lambda d, i=i: flip(sec, i),
                     value=lambda i=i: "Added" if i["plex"] in ((picked(sec) or {}).get("value") or []) else
                     f"{int(i['duration'])} s") for i in sorted(sec.items, key=lambda i: i["title"].lower())
                if i["duration"] <= lc.CLIP_MAX][:400] or [Item("(no short clips)", enabled=False)]
    return [Item(s.title, submenu=lambda s=s: clips(s), value=lambda s=s: str(len((picked(s) or {}).get("value") or [])))
            for s in sorted(index.sections.values(), key=lambda s: s.title.lower())
            if s.breaks or s.kind in ("clip", "music")] or [Item("No libraries of clips", enabled=False)]


def long_libs(app, c, save, ensure):
    index = app.library

    def on(key):
        return any(s.get("section") == key and s.get("chunks") for s in ensure().get("ads") or [])

    def flip(key):
        lst = ensure().setdefault("ads", [])
        have = [s for s in lst if s.get("section") == key and s.get("chunks")]
        for s in have:
            lst.remove(s)
        if not have:
            lst.append({"section": key, "kind": "all", "chunks": True})
        save(place=False)
    return [Item(s.title, lambda s=s: flip(s.key), adjust=lambda d, s=s: flip(s.key),
                 value=lambda s=s: "On" if on(s.key) else "Off", help=f"{len(s.items):,} titles.")
            for s in sorted(index.sections.values(), key=lambda s: s.title.lower())] or \
        [Item("No libraries", enabled=False)]


BALANCES = [("duration", "By duration"), ("count", "By count")]
PREMIERE_TIMES = [([20], "8 PM"), ([19], "7 PM"), ([21], "9 PM"), ([22], "10 PM"), ([20, 22], "8 and 10 PM"),
                  ([9, 20], "9 AM and 8 PM"), ([17, 20], "5 and 8 PM")]
PREMIERE_DAYS = [(None, "Every night"), ([4], "Fridays"), ([6], "Sundays"), ([4, 5], "Friday and Saturday"),
                 ([0, 1, 2, 3, 4], "Weeknights"), ([3], "Thursdays")]
PIN_DAYS = [(None, "Every day"), ([0, 1, 2, 3, 4], "Weekdays"), ([5, 6], "Weekends")] + [
    ([d], n) for d, n in enumerate(("Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays",
                                    "Sundays"))]
WEIGHTS = [0, 0.5, 1, 2, 3, 5]


def _label_of_list(options, key):
    return next((lab for k, lab in options if k == key), str(key))


def premiere_items(app, c, save):
    from . import libchannels as lc
    index = getattr(app, "library", None)

    def cyc(key, options, default):
        def f(d):
            keys = [k for k, _ in options]
            cur = c.get(key, default)
            c[key] = keys[((keys.index(cur) if cur in keys else 0) + d) % len(keys)]
            save(place=False)
        return f

    def preroll(d):
        secs = [None] + sorted((s.key for s in index.sections.values() if s.kind == "clip"),
                               key=lambda k: index.sections[k].title.lower()) if index else [None]
        cur = c.get("premiere_preroll")
        c["premiere_preroll"] = secs[((secs.index(cur) if cur in secs else 0) + d) % len(secs)]
        save(place=False)

    def preroll_value():
        k = c.get("premiere_preroll")
        return index.sections[k].title if k and index and k in index.sections else "None"
    return [
        Item("Premiere Times", value=lambda: _label_of_list(PREMIERE_TIMES, c.get("premiere_times") or [20]),
             adjust=cyc("premiere_times", PREMIERE_TIMES, [20]), help="The hour (or hours) premieres start from."),
        Item("Premiere Nights", value=lambda: _label_of_list(PREMIERE_DAYS, c.get("premiere_days")),
             adjust=cyc("premiere_days", PREMIERE_DAYS, None), help="The nights that have premieres."),
        Item("Back to Back", value=lambda: str(int(c.get("premiere_count") or 1)),
             adjust=lambda d: (c.__setitem__("premiere_count", max(1, min(4, int(c.get("premiere_count") or 1) + d))),
                               save(place=False)),
             help="How many new arrivals premiere one after another."),
        Item("Pre-roll", value=preroll_value, adjust=preroll,
             help="A clip from this library before the premieres (a \"world premiere\" bumper)."),
    ]


def pin_items(app, c, save):
    """Pinned Times: a show or movie at a set time, on set days."""
    from . import libchannels as lc
    tl = lc.SCHEDULES.get(lc.PREFIX + c["id"])

    def add(src, label):
        def got(text):
            text = (text or "").strip().upper().replace(".", ":")
            import re
            m = re.fullmatch(r"(\d{1,2})(?::(\d\d))?\s*(AM|PM)?", text)
            if not m:
                app.toast("A time like 8:00 PM or 20:00.")
                return
            h, mi = int(m.group(1)), int(m.group(2) or 0)
            if m.group(3):
                h = h % 12 + (12 if m.group(3) == "PM" else 0)
            if not (0 <= h < 24 and 0 <= mi < 60):
                app.toast("A time like 8:00 PM or 20:00.")
                return
            c.setdefault("pins", []).append({"at": f"{h:02d}:{mi:02d}", "days": None, "src": src, "label": label})
            save(place=False)
            _refresh(app, {"Pinned Times": lambda: pin_items(app, c, save)})
        app.push(Keyboard(app, f"{label} starts at", got, hint="8:00 PM, or 20:00"))

    def titles():
        if tl is None:
            return [Item("Nothing on the channel yet", enabled=False)]
        out = []
        for g in sorted(tl.groups, key=lambda g: g["title"].lower()):
            i = g["items"][0]
            src = {"kind": "show", "value": i["show_key"]} if i["type"] == "episode" else \
                {"kind": "title", "value": [i["plex"]]}
            out.append(Item(g["title"], lambda src=src, t=g["title"]: add(src, t)))
        return out

    def days(p, d):
        p["days"] = _cycle_list(PIN_DAYS, p.get("days"), d)
        save(place=False)

    def drop(p):
        c["pins"].remove(p)
        save(place=False)
        app.top().back()
        _refresh(app, {"Pinned Times": lambda: pin_items(app, c, save)})

    def when(p):
        h, m = (int(x) for x in p["at"].split(":"))
        return f"{h % 12 or 12}:{m:02d} {'PM' if h >= 12 else 'AM'}, {_label_of_list(PIN_DAYS, p.get('days')).lower()}"
    return [Item("Pin a title", submenu=titles, help="A show (its next episode each time) or a movie.")] + [
        Item(p.get("label") or "A title", submenu=lambda p=p: [
            Item("Days", value=lambda p=p: _label_of_list(PIN_DAYS, p.get("days")), adjust=lambda d, p=p: days(p, d)),
            Item("Remove", lambda p=p: drop(p))],
            value=lambda p=p: when(p), help="SELECT: its days, or remove it.")
        for p in c.get("pins") or []]


def _cycle_list(options, cur, d):
    keys = [k for k, _ in options]
    return keys[((keys.index(cur) if cur in keys else 0) + d) % len(keys)]


def weight_items(app, c, save):
    from . import libchannels as lc
    tl = lc.SCHEDULES.get(lc.PREFIX + c["id"])
    tws = c.setdefault("title_weights", {})

    def step(g, d):
        cur = tws.get(g["id"], 1)
        k = WEIGHTS.index(cur) if cur in WEIGHTS else 2
        v = WEIGHTS[max(0, min(len(WEIGHTS) - 1, k + d))]
        if v == 1:
            tws.pop(g["id"], None)
        else:
            tws[g["id"]] = v
        save(place=False)
    if tl is None or not tl.groups:
        return [Item("Nothing on the channel yet", enabled=False)]
    return [Item(g["title"], value=lambda g=g: f"{tws.get(g['id'], 1):g}", adjust=lambda d, g=g: step(g, d),
                 help="LEFT/RIGHT: 0 (off the channel), 0.5, 1, 2, 3 or 5 times as often.")
            for g in sorted(tl.groups, key=lambda g: g["title"].lower())]


def running_order_items(app, tid):
    """Today on the channel, hour by hour: each programme and each break
    (its length and what's in it)."""
    from datetime import datetime, timezone, timedelta
    from . import libchannels as lc
    tl = lc.SCHEDULES.get(tid)
    if tl is None:
        return [Item("Nothing drawn up yet", enabled=False)]
    now = datetime.now(timezone.utc)
    tl.at(now + timedelta(hours=24))
    t0 = now.timestamp() - 3600
    rows, hour, brk = [], None, None

    def flush():
        if brk:
            mins, secs = divmod(int(brk[1]), 60)
            what = ", ".join(f"{n} {k}{'s' if n > 1 else ''}" for k, n in brk[2].items())
            rows.append(Item(f"   Break {mins}:{secs:02d}", value=lambda w=brk[0]: w, enabled=False, help=what))
    for s in list(tl._slots):
        if s[0] + s[2] < t0 or s[0] > t0 + 25 * 3600:
            continue
        lt = datetime.fromtimestamp(s[0])
        when = f"{lt:%I:%M %p}".lstrip("0")
        x = s[3] if len(s) > 3 else {}
        if x.get("brk"):
            kind = {"ad": "commercial", "bump": "bumper", "brb": "slate"}.get(x["brk"], x["brk"])
            if brk is None:
                brk = [when, 0.0, {}]
            brk[1] += s[2]
            brk[2][kind] = brk[2].get(kind, 0) + 1
            continue
        flush()
        brk = None
        if lt.hour != hour:
            hour = lt.hour
            rows.append(Item(f"-- {lt:%a} {lt.hour % 12 or 12} {'PM' if lt.hour >= 12 else 'AM'} --", enabled=False))
        title = "Off the air" if s[1] == lc.OFF else tl.title_of(s[1])
        rows.append(Item(title, value=lambda w=when: w, help=f"{max(1, round(s[2] / 60))} min." + (" (part)" if x.get("part") else "")))
    flush()
    return rows or [Item("Nothing drawn up yet", enabled=False)]


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
        Item("Content", submenu=lambda: library_source_items(app, gid), value=lambda: str(len(g.get("sources") or [])),
             help="What's in the group."),
        Item("Name", rename, value=lambda: g["name"]),
        Item("Used by", value=lambda: str(len(users)), help=", ".join(users) or "No channel names it yet."),
        Item("Remove group", submenu=lambda: _confirm(app, "Remove group", remove, "Keep it"),
             help="Channels naming it lose it from what they play."),
    ]


def library_channel_page(app, cid):
    """A library channel's editor, NostalgiaTV's rows in its order: name,
    number, favourite, shown, audience, packs, logo, bug, the logic, the
    content; what's coming up, a fresh schedule, a copy, removal."""
    from . import libchannels as lc, videochannels as vc
    cfg = app.config
    c = next((x for x in cfg.library_channels if x["id"] == cid), None)
    if c is None:
        return [Item("(this channel is gone)", enabled=False)]
    url = vc.SCHEME + lc.PREFIX + cid

    def save(place=True):
        c["starter"] = False                # edited: the starter lineup's removal leaves it be
        cfg.save()
        if place:
            lc.place(app)
            _lists_changed(app)
        else:
            lc.rebuild(app)
        app.invalidate()

    def set_name():
        def got(text):
            if text is None or not text.strip():
                return
            c["name"] = text.strip()
            save()
        app.push(Keyboard(app, "Channel Name", got, initial=c.get("name", "")))

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
        app.push(Keyboard(app, "Channel Number (empty = automatic)", got,
                          initial=str(want) if isinstance(want, int) else ""))

    def number_value():
        ch = _by_url(app, url)
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
        app.toast("Drawn up again from now.")
        ch = app.live.channel
        if ch is not None and lc.is_library(ch) and ch.url.endswith(cid):
            app.after(1.5, lambda: ch in app.channels and app.live.tune(app.channels.index(ch)))

    def remove():
        cfg.library_channels[:] = [x for x in cfg.library_channels if x["id"] != cid]
        cfg.save()
        lc.place(app)
        app.top().back()
        _lists_changed(app)

    def holds():
        tl = lc.SCHEDULES.get(lc.PREFIX + cid)
        if not tl or not tl.entries:
            return "Nothing yet"
        hours = sum(i["duration"] for i in tl.entries) / 3600
        return f"{len(tl.entries):,} titles, {hours:,.0f} h"
    rows = timeline_items(app, c, lc.PREFIX + cid, save)
    return [
        Item("Channel Name", set_name, value=lambda: c.get("name") or "",
             help="The channel's name in the lineup and the guide."),
        Item("Channel Number", set_number, value=number_value,
             help="Automatic (with the other library channels, after the lineup) or one you choose; a taken "
                  "number moves to the next free."),
        *_lineup_rows(app, url),
        Item("Audience", value=lambda: _label(lc.CONTENT, c.get("content", "any")), adjust=content,
             help="Adults: anything. Everyone: nothing rated TV-MA, R or NC-17. Kids: only TV-Y, TV-Y7, TV-G and G "
                  "(unrated titles stay off); kids' profiles see the Kids channels."),
        *programming_items(app, c, save),
        *rows[:-2],
        Item("Premieres", value=lambda: _label(lc.PREMIERES, c.get("premieres", "off")), adjust=premieres,
             help="Each evening at 8, the newest arrival in your library the channel hasn't premiered yet. The "
                  "guide marks it, and marks every title added in the last two weeks as New."),
        Item("Premiere Options", submenu=lambda: premiere_items(app, c, save),
             help="When premieres air, on which nights, how many back to back, and a pre-roll before them."),
        Item("Pinned Times", submenu=lambda: pin_items(app, c, save), value=lambda: str(len(c.get("pins") or [])),
             help="A show or movie that starts at a set time (8:00 PM weeknights, say), the time before it "
                  "filled to the minute."),
        Item("Title Weights", submenu=lambda: weight_items(app, c, save),
             help="How often each show or movie comes round: 0 keeps it off, 2 twice as often."),
        Item("Balance", value=lambda: _label(BALANCES, c.get("balance", "duration")),
             adjust=lambda d: (c.__setitem__("balance", _cycle(BALANCES, c.get("balance", "duration"), d)),
                               save(place=False)),
             help="Mix with Auto weighting: each source's share by its hours of programmes, or by its number of "
                  "titles."),
        Item("Seasonal Episodes", value=lambda: "On" if c.get("seasonal", True) else "Off",
             adjust=lambda d: (c.__setitem__("seasonal", not c.get("seasonal", True)), save(place=False)),
             help="Halloween, Thanksgiving, Christmas, Valentine's and other holiday episodes and movies air only "
                  "in their season, and more often then. (A channel mostly of them is left alone.)"),
        Item("Running Order", submenu=lambda: running_order_items(app, lc.PREFIX + cid),
             help="Today hour by hour, the breaks too: what airs when, and how long each break runs."),
        Item("Lower-third", value=lambda: "On" if c.get("card", False) else "Off", adjust=card,
             help="A name card as each programme starts and before it ends."),
        Item("Content", submenu=lambda: library_source_items(app, cid), value=holds,
             help="What it plays: shows, movies, libraries, genres, decades, studios, groups. SELECT to add some "
                  "or take some out."),
        *rows[-2:],
        Item("Refresh Schedule", refresh,
             help="This channel drawn up again from now in a fresh order: what's on now changes. (A change to "
                  "the channel applies by itself; this is a new shuffle.)"),
        Item("Make a copy", lambda: _copy_channel(app, cfg.library_channels, c, library_channel_page),
             help="The same channel again, to change into another."),
        Item("Remove channel", submenu=lambda: _confirm(app, "Remove channel", remove, "Keep it")),
    ]


MATURE_FROM = [(None, "Any time")] + [(h, f"From {h % 12 or 12} {'PM' if h >= 12 else 'AM'}") for h in (18, 19, 20, 21, 22, 23)]
MAX_MOVIES = [(0, "No limit")] + [(n, f"{n} a day") for n in (1, 2, 3, 4, 6, 8)]


def programming_items(app, c, save):
    """NostalgiaTV's programming rows: watched filter, specials, where a
    show starts, movies a day, when grown-ups' titles may air, marathons,
    a redirect, starting every show over."""
    from . import libchannels as lc

    def cyc(key, options, default):
        def f(d):
            c[key] = _cycle(options, c.get(key, default), d)
            save(place=False)
        return f

    def flip(key, default):
        def f(d=0):
            c[key] = not c.get(key, default)
            save(place=False)
        return f

    def over():
        c["reset"] = int(c.get("reset", 0)) + 1
        save(place=False)
        app.toast("Every show starts again from its first episode, from now.")
    return [
        Item("Watched Filter", value=lambda: _label(lc.WATCHED, c.get("watched", "all")),
             adjust=cyc("watched", lc.WATCHED, "all"),
             help="Everything, only what you haven't watched in Plex yet, or only what you have. Read again with "
                  "the library."),
        Item("Specials", value=lambda: "On" if c.get("specials", True) else "Off", adjust=flip("specials", True),
             help="Season 0: a show's specials, after its seasons. Off: the seasons only."),
        Item("Episode Start", value=lambda: _label(lc.EPISODE_START, c.get("episode_start", "first")),
             adjust=cyc("episode_start", lc.EPISODE_START, "first"),
             help="Where a show new to the channel starts: its first episode, or one picked at random. Then it "
                  "carries on in order."),
        Item("Start Shows Over", over,
             help="Every show on the channel back to its first episode, from now."),
        Item("Max Movies Per Day", value=lambda: _label(MAX_MOVIES, int(c.get("max_movies") or 0)),
             adjust=cyc("max_movies", MAX_MOVIES, 0),
             help="Once the broadcast day has had this many movies, only shows until 4 AM."),
        Item("Restrict Ratings After", value=lambda: _label(MATURE_FROM, c.get("mature_from")),
             adjust=cyc("mature_from", MATURE_FROM, None),
             help="TV-MA, R and NC-17 titles only from this hour until 6 AM, as networks kept them to late night."),
        Item("Random Marathons", value=lambda: "On" if c.get("marathons") else "Off", adjust=flip("marathons", False),
             help="On about one day in three, from an hour picked at random: four to eight episodes of one show "
                  "back to back. The guide marks them."),
        Item("Redirect", submenu=lambda: redirect_items(app, c, save),
             value=lambda: _redirect_value(app, c),
             help="In set hours the channel carries another one's programmes (a simulcast), as stations did "
                  "overnight."),
    ]


REDIRECT_HOURS = [[0, 6], [1, 6], [2, 6], [22, 6], [18, 6], [6, 18], [20, 23]]


def _redirect_value(app, c):
    r = c.get("redirect") or {}
    ch = next((x for x in app.channels if x.url.endswith(r.get("to") or "-")), None) if r.get("to") else None
    return f"{ch.number:g} {_hours_label(r)}" if ch else "Off"


def _hours_label(r):
    def h(x):
        return f"{x % 12 or 12} {'PM' if x >= 12 else 'AM'}"
    return f"{h(r.get('from', 0))}-{h(r.get('until', 6))}"


def redirect_items(app, c, save):
    """The channel to carry, and the hours it's carried."""
    from . import libchannels as lc, videochannels as vc
    me = vc.cid_of(_by_url(app, vc.SCHEME + lc.PREFIX + c["id"])) if c.get("id") else ""
    r = c.get("redirect") or {}

    def pick(ch):
        if ch is None:
            c.pop("redirect", None)
        else:
            c["redirect"] = {"to": vc.cid_of(ch), "from": r.get("from", 0), "until": r.get("until", 6)}
        save(place=False)
        app.top().back()

    def hours(d):
        if not c.get("redirect"):
            return
        cur = [c["redirect"].get("from", 0), c["redirect"].get("until", 6)]
        k = REDIRECT_HOURS.index(cur) if cur in REDIRECT_HOURS else -1
        c["redirect"]["from"], c["redirect"]["until"] = REDIRECT_HOURS[(k + d) % len(REDIRECT_HOURS)]
        save(place=False)
    chans = [ch for ch in app.channels if vc.is_video(ch) and vc.cid_of(ch) != me]
    return [
        Item("Hours", value=lambda: _hours_label(c.get("redirect") or {}) if c.get("redirect") else "-", adjust=hours,
             help="When the other channel's programmes are carried."),
        Item("No redirect", lambda: pick(None), help="The channel's own programmes all day."),
        *[Item(f"{ch.number:g}  {ch.name}", lambda ch=ch: pick(ch),
               value=lambda ch=ch: "On" if (c.get("redirect") or {}).get("to") == vc.cid_of(ch) else "")
          for ch in chans],
    ]


def _holder(cfg, cid):
    """A library channel, or a content group, by id: what has sources."""
    return next((x for x in list(cfg.library_channels) + list(getattr(cfg, "content_groups", []) or [])
                 if x["id"] == cid), None)


def library_source_items(app, cid):
    """What a library channel (or a content group) plays, NostalgiaTV's
    Added Content: each source opens its page. Add Content: by search, by
    library, genre, decade, studio, show, rating or group, each a list to
    tick in and out (it stays open to tick several)."""
    from . import libchannels as lc
    cfg = app.config
    c = _holder(cfg, cid)
    if c is None:
        return [Item("(this channel is gone)", enabled=False)]
    index = getattr(app, "library", None)
    if index is None:
        return [Item("Still reading your library...", enabled=False)]

    def changed():
        c["starter"] = False
        cfg.save()
        lc.rebuild(app)
        _refresh(app, {"Content": lambda: library_source_items(app, cid)})

    def same(src, section, kind):
        """(Shows and titles are one of a kind wherever they are: any library.)"""
        return not src.get("exclude") and src.get("kind") == kind and (
            kind in ("show", "title", "season", "collection", "playlist")
            or (src.get("section") or "") == (section or ""))

    def has(section, kind, v):
        for src in c.get("sources") or []:
            if same(src, section, kind):
                vals = src.get("value")
                if vals == v or (kind == "title" and isinstance(vals, list) and v in vals):
                    return True
        return False

    def tick(section, kind, v):
        srcs = c.setdefault("sources", [])
        for src in list(srcs):
            if not same(src, section, kind):
                continue
            vals = src.get("value")
            if kind == "title" and isinstance(vals, list) and v in vals:
                vals.remove(v)
                if not vals:
                    srcs.remove(src)
                return changed()
            if vals == v:
                srcs.remove(src)
                return changed()
        srcs.append({"section": section, "kind": kind, "value": [v] if kind == "title" else v})
        changed()

    def row(label, section, kind, v, count="", help=None):
        return Item(label, lambda: tick(section, kind, v), adjust=lambda d: tick(section, kind, v),
                    value=lambda: "Added" if has(section, kind, v) else count,
                    help=help or "SELECT adds it; again takes it out.")

    def values(section, kind):
        return [row(label, section, kind, v, f"{k:,}") for v, label, k in lc.options(index, section, kind)] or \
            [Item("(nothing here)", enabled=False)]

    def ratings(section):
        return [row("Kids' ratings", section, "rating", lc.KIDS, help="TV-Y, TV-Y7, TV-G and G."),
                row("Grown-ups' ratings", section, "rating", lc.MATURE, help="TV-MA, R and NC-17.")]

    def slices(section):
        sec = index.sections.get(section)
        rows = [row("Everything in it", section, "all", None, f"{len(sec.items):,}" if sec else "")]
        for kind, label in lc.KINDS[1:]:
            if kind == "rating":
                rows += ratings(section)
            elif kind == "show" and sec is not None and sec.kind == "music":
                rows.append(Item("An artist...", submenu=lambda: values(section, "show")))
            elif (kind == "show" and (sec is None or sec.kind == "show")) or (
                    kind == "title" and sec is not None and sec.kind not in ("show", "music")) or \
                    kind not in ("show", "title"):
                rows.append(Item(f"A {label.lower()}...", submenu=lambda kind=kind: values(section, kind)))
        return rows

    def libraries():
        return [Item(sec.title, submenu=lambda sec=sec: slices(sec.key), value=lambda sec=sec: f"{len(sec.items):,}")
                for sec in sorted(index.sections.values(), key=lambda x: x.title.lower())]

    def found(text):
        hits = []
        for sec in index.sections.values():
            if sec.breaks:
                continue
            if sec.kind in ("show", "music"):
                hits += [(sh["title"], sec, "show", k, "Show" if sec.kind == "show" else "Artist")
                         for k, sh in sec.shows.items() if text in sh["title"].lower()]
            else:
                hits += [(f"{i['title']} ({i['year']})" if i.get("year") else i["title"], sec, "title", i["plex"],
                          "Movie" if sec.kind == "movie" else "Clip") for i in sec.items if text in i["title"].lower()]
        hits.sort(key=lambda h: h[0].lower())
        return [row(t, sec.key, kind, v, what, help=f"A {what.lower()} in {sec.title}. SELECT adds it; again takes "
                                                    "it out.") for t, sec, kind, v, what in hits[:80]] or \
            [Item("Nothing has that in its title", enabled=False)]

    def search():
        def got(text):
            text = (text or "").strip().lower()
            if text:
                app.top().open(text.upper(), found(text))
        app.push(Keyboard(app, "Search titles", got, hint="Part of a show's or a movie's title."))

    def groups():
        return [row(g["name"], "", "group", g["id"]) for g in cfg.content_groups] or [
            Item("No content groups yet", enabled=False, help="Make one under Settings > Channels > Content Groups.")]

    def episodes(sec, key, season):
        its = [i for i in sec.items if i["show_key"] == key and i["season"] == season]
        return [row(f"E{i['episode']}  {i['name']}", sec.key, "title", i["plex"]) for i in its] or \
            [Item("(nothing here)", enabled=False)]

    def seasons(sec, key):
        got = sorted({i["season"] for i in sec.items if i["show_key"] == key}, key=lambda s: (s == 0, s))
        out = [row("The whole show", "", "show", key)]
        for s in got:
            name = f"Season {s}" if s else "Specials"
            out.append(row(name, "", "season", f"{key}:{s}", help="SELECT adds the season; again takes it out."))
            out.append(Item(f"  {name}: pick episodes", submenu=lambda s=s: episodes(sec, key, s)))
        return out

    def shows():
        rows = [(sh["title"], sec, k) for sec in index.sections.values() if sec.kind == "show" and not sec.breaks
                for k, sh in sec.shows.items()]
        rows.sort(key=lambda r: r[0].lower())
        return [Item(t, submenu=lambda sec=sec, k=k: seasons(sec, k)) for t, sec, k in rows] or \
            [Item("(no shows)", enabled=False)]

    def copy_from():
        def take(o):
            c["sources"] = json.loads(json.dumps(o.get("sources") or []))
            changed()
            app.toast(f"Content copied from {o.get('name') or 'that channel'}.")
        return [Item(o.get("name") or "Library Channel", lambda o=o: take(o), close=False,
                     help=f"{len(o.get('sources') or [])} sources. Takes the place of this channel's content.")
                for o in cfg.library_channels if o is not c] or [Item("No other channels", enabled=False)]

    def clear():
        c["sources"] = []
        changed()
        app.top().back()

    def add_rows():
        rows = [Item("Add by Search", search, help="Type part of a title: the shows and movies that have it."),
                Item("Add by Library", submenu=libraries, help="A whole library, or a slice of one."),
                Item("Add by Genre", submenu=lambda: values("", "genre"), help="A genre from every library."),
                Item("Add by Decade", submenu=lambda: values("", "decade"), help="A decade from every library."),
                Item("Add by Studio", submenu=lambda: values("", "studio"),
                     help="A studio or network from every library."),
                Item("Add by Show", submenu=lambda: values("", "show")),
                Item("Add by Season or Episode", submenu=shows,
                     help="A show's seasons, or episodes picked one by one."),
                Item("Add by Collection", submenu=lambda: values("", "collection"),
                     help="A Plex collection: its shows and movies."),
                Item("Add by Playlist", submenu=lambda: values("", "playlist"),
                     help="A Plex video playlist: its episodes and movies."),
                Item("Add by Rating", submenu=lambda: ratings("")),
                Item("Copy From Another Channel", submenu=copy_from,
                     help="Another library channel's content in place of this one's."),
                Item("Clear Content", submenu=lambda: _confirm(app, "Take everything out", clear, "Keep it"),
                     help="Every source taken out.")]
        if c in cfg.library_channels:
            rows.append(Item("Add by Group", submenu=groups,
                             help="A content group: change it and every channel with it follows."))
        return rows

    def label(src):
        if src.get("kind") == "group":
            g = next((g for g in cfg.content_groups if g["id"] == src.get("value")), None)
            return f"Group: {g['name'] if g else src.get('label') or 'a content group'}"
        return ("Not: " if src.get("exclude") else "") + lc.source_label(index, src)

    def when(src):
        bits = [_label_of(lc.AIRS, src.get("airs"))] if src.get("airs") else []
        bits += [_label_of(lc.SEASONS, src.get("season"))] if src.get("season") else []
        return ", ".join(bits)[:24] or ("Left out" if src.get("exclude") else "Any time")
    items = [Item(label(src), submenu=lambda i=i: library_source_page(app, cid, i), value=lambda src=src: when(src),
                  help="SELECT: when it airs, its weight, leaving it out, taking it out.")
             for i, src in enumerate(c.get("sources") or [])]
    items.append(Item("Add Content", submenu=add_rows, help="Search, or add by library, genre, decade, studio, show, "
                                                            "rating or group."))
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
        app.top().back()
        _refresh(app, {"Content": lambda: library_source_items(app, cid)})
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
        _reopen(app, source_items(app))
    def rename():
        def got(name):
            if name:
                pl["name"] = name
                app.config.save()
                app.toast(f"Renamed to {name}")
                _reopen(app, source_items(app))
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
    step = (lambda n, s: f"3/4  {s}") if first_run else (lambda n, s: s)

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
                                  hint="How it's listed under Settings > Channels > Live TV Sources."))
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
                          hint="How it's listed under Settings > Channels > Live TV Sources."))

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


def _back_up(app):
    from . import backup
    try:
        path = backup.save(app.config)
        app.toast(f"Saved: {path}", 8.0)
    except OSError as e:
        app.toast(f"Couldn't save the backup ({e.strerror or e}).", 6.0)


def restore_items(app):
    from . import backup

    def restore(b):
        try:
            n = backup.restore(app.config, b["path"])
        except (OSError, ValueError) as e:
            app.toast(f"Couldn't read that backup ({e}).", 6.0)
            return
        app.toast(f"{n} settings put back.", 4.0)
        app.top().open("RESTART CATHODE?", _confirm(app, "Restart now", app.restart, "Later", close=True))
    rows = []
    for b in backup.backups(app.config)[:30]:
        when = time.strftime("%a %d %b %Y, %I:%M %p", time.localtime(b["saved"])).replace(" 0", " ")
        rows.append(Item(when, submenu=lambda b=b: _confirm(app, "Put these settings back", lambda b=b: restore(b),
                                                             "Keep mine"),
                         value=lambda b=b: "Weekly" if b["auto"] else "", help=b["path"]))
    return rows or [Item("No backups yet", enabled=False, help="Back up settings makes one; one is made each week.")]


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
        if first_run(app):
            open_welcome(app)           # nothing set up yet (Spelunkr comes with it): straight to setting it up
        else:
            open_main(app)
        return True
    return False
