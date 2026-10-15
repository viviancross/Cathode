"""Updates as the user sees them: a quiet check at launch, and the menu's
'Check for updates' page. The network work runs off the UI thread and posts
each step back; the install itself runs after Cathode quits."""

import os
import threading
import time

from . import __version__, paths, updater
from .screens.menu import Item, Menu


def _updates_dir() -> str:
    return os.path.join(paths.cache_dir(), "updates")


def launch_check(app):
    """Speak up only when something is worth saying."""
    if os.path.exists(os.path.join(_updates_dir(), updater.FAILED_LOG)):
        app.toast("The last update didn't install - try Check for updates again", 8.0)
        return

    def work():
        try:
            latest = updater.check_latest()
        except updater.UpdateError:
            return
        if latest and updater.is_newer(latest["tag"], __version__):
            app.post(app.toast, f"Update {latest['tag']} available - see Settings > System", 6.0)
    threading.Thread(target=work, daemon=True).start()


def open_check(app):
    """The menu page: checking -> result -> download -> ready."""
    menu = Menu(app, "CHECK FOR UPDATES", [Item("Contacting GitHub...", enabled=False)])
    app.push(menu)

    def show(*lines, actions=()):
        if menu in app.screens:
            menu.refresh([Item(line, enabled=False) for line in lines] + list(actions))
            menu.cursor = len(lines) if actions else 0
            app.invalidate()

    def done(*lines):
        show(*lines, actions=[Item("OK", menu.back)])

    def check():
        try:
            latest = updater.check_latest()
        except updater.UpdateError as e:
            app.post(done, "The check failed:", str(e))
            return
        if not latest or not updater.is_newer(latest["tag"], __version__):
            app.post(done, f"You're on the latest version ({__version__}).")
            return
        asset = updater.pick_asset(latest["assets"])
        if not asset:
            app.post(done, f"{latest['tag']} is out, but there's no build for this computer.")
            return
        app.post(show, f"{latest['tag']} is available.", actions=[
            Item("Download and install", lambda: download(latest, asset)),
            Item("Not now", menu.back)])

    def download(latest, asset):
        show(f"Downloading {latest['tag']}...")
        last = [0.0]

        def progress(got, total):
            now = time.monotonic()
            if now - last[0] >= 0.2:
                last[0] = now
                mb = f"{got / 1048576:.1f}" + (f" / {total / 1048576:.1f}" if total else "")
                app.post(show, f"Downloading {latest['tag']}...", f"{mb} MB")

        def work():
            try:
                path = updater.download(asset["url"], _updates_dir(), asset["name"],
                                        on_progress=progress, total=asset.get("size", 0))
                side = updater.find_checksum_asset(latest["assets"], asset["name"])
                if side:
                    updater.verify_sha256(path, side["url"])
                script = updater.write_apply_script(path, updater.install_dir(), _updates_dir())
            except Exception as e:
                app.post(done, "The update failed:", str(e))
                return
            app.pending_update = script
            app.post(done, "Downloaded.", "It installs when you quit Cathode.")
        threading.Thread(target=work, daemon=True).start()

    threading.Thread(target=check, daemon=True).start()
