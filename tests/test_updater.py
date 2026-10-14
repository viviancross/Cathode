"""Unit tests for cathode.updater — version parsing + asset matching."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import updater  # noqa: E402


class TestVersion(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(updater.parse_version("v2.0"), (2, 0))
        self.assertEqual(updater.parse_version("v2.2b"), (2, 2))
        self.assertEqual(updater.parse_version("2.0.5"), (2, 0, 5))
        self.assertEqual(updater.parse_version("nightly"), ())

    def test_is_newer(self):
        self.assertTrue(updater.is_newer("v2.1", "2.0"))
        self.assertTrue(updater.is_newer("2.0.5", "2.0"))
        self.assertFalse(updater.is_newer("2.0", "2.0"))
        self.assertFalse(updater.is_newer("1.9", "2.0"))
        self.assertFalse(updater.is_newer("bad", "2.0"))   # unparseable -> not newer


class TestMainlineTag(unittest.TestCase):
    """The port branches publish to the same repo; the desktop updater must not
    treat one of their releases as an update for itself."""

    def test_bare_versions_are_mainline(self):
        for t in ("v3.0", "3.0", "v3.0.1", "10.2"):
            self.assertTrue(updater.is_mainline_tag(t), t)

    def test_port_tags_are_not(self):
        for t in ("android-v3.0", "v3.0-tizen", "ps2-1.0", "miyoo-v3.0",
                  "nightly", "", "v3.0b"):
            self.assertFalse(updater.is_mainline_tag(t), t)


class TestCheckLatest(unittest.TestCase):
    """check_latest reads the release LIST and filters it, so what it returns is
    the newest desktop release rather than whatever was published last."""

    @staticmethod
    def _releases(payload):
        """Patch urlopen to serve `payload` as the /releases JSON body."""
        class _Resp:
            def read(self, *a):
                return json.dumps(payload).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return mock.patch.object(updater.urllib.request, "urlopen",
                                 lambda *a, **k: _Resp())

    def test_skips_a_port_release_published_after_the_desktop_one(self):
        # The exact hazard: the Android build ships later, so GitHub's own
        # "latest" would be android-v3.1 — a version the desktop app can't use.
        with self._releases([
            {"tag_name": "android-v3.1", "assets": []},
            {"tag_name": "v3.0", "assets": []},
        ]):
            self.assertEqual(updater.check_latest()["tag"], "v3.0")

    def test_skips_drafts_and_prereleases(self):
        with self._releases([
            {"tag_name": "v4.0", "prerelease": True, "assets": []},
            {"tag_name": "v3.9", "draft": True, "assets": []},
            {"tag_name": "v3.0", "assets": []},
        ]):
            self.assertEqual(updater.check_latest()["tag"], "v3.0")

    def test_highest_version_wins_not_the_most_recent(self):
        # A 2.9 patch published after 3.0 must not roll a 3.0 user back.
        with self._releases([
            {"tag_name": "v2.9.1", "assets": []},
            {"tag_name": "v3.0", "assets": []},
        ]):
            self.assertEqual(updater.check_latest()["tag"], "v3.0")

    def test_none_when_only_ports_have_released(self):
        with self._releases([{"tag_name": "android-v1.0", "assets": []}]):
            self.assertIsNone(updater.check_latest())

    def test_assets_are_carried_through(self):
        with self._releases([{"tag_name": "v3.0", "assets": [
                {"name": "cathode-windows-3.0-portable.zip",
                 "browser_download_url": "u", "size": 7}]}]):
            got = updater.check_latest()["assets"]
        self.assertEqual(got, [{"name": "cathode-windows-3.0-portable.zip",
                                "url": "u", "size": 7}])


class TestAssetMatch(unittest.TestCase):
    ASSETS = [
        {"name": "cathode-linux-macos-2.1.zip", "url": "u1", "size": 1},
        {"name": "cathode-windows-2.1-portable.zip", "url": "u2", "size": 2},
    ]

    def test_a_ports_asset_is_never_picked(self):
        # A fork's Windows zip in a mainline release must lose to ours, and must
        # not be picked at all when ours is absent.
        forks = [{"name": "cathode-android-3.0.apk", "url": "bad1", "size": 1},
                 {"name": "tizen-cathode-windows-3.0.zip", "url": "bad2", "size": 1},
                 {"name": "CathodePy-miyoo-linux-macos-3.0.zip", "url": "bad3",
                  "size": 1}]
        for nm in ("nt", "posix"):
            with mock.patch.object(updater.os, "name", nm), \
                    mock.patch.object(updater.sys, "frozen", True, create=True):
                self.assertIsNone(updater.pick_asset(forks), nm)
                self.assertEqual(
                    updater.pick_asset(forks + self.ASSETS)["url"],
                    "u2" if nm == "nt" else "u1")

    def test_the_sidecar_is_never_mistaken_for_the_build(self):
        # "<build>.sha256" shares the build's whole name, so it matches every
        # prefix the build does; today it loses only because the zip happens to
        # sort first. Downloading the sidecar as the update would then verify
        # 65 bytes against themselves.
        sides = [{"name": a["name"] + ".sha256", "url": "side", "size": 65}
                 for a in self.ASSETS]
        for nm, want in (("nt", "u2"), ("posix", "u1")):
            with mock.patch.object(updater.os, "name", nm), \
                    mock.patch.object(updater.sys, "frozen", True, create=True):
                self.assertIsNone(updater.pick_asset(sides), nm)
                # ...and it still loses when it is listed first.
                self.assertEqual(
                    updater.pick_asset(sides + self.ASSETS)["url"], want, nm)

    def test_non_windows_gets_linux_macos(self):
        with mock.patch.object(updater.os, "name", "posix"):
            self.assertEqual(updater.pick_asset(self.ASSETS)["url"], "u1")

    def test_windows_gets_windows(self):
        with mock.patch.object(updater.os, "name", "nt"), \
                mock.patch.object(updater.sys, "frozen", True, create=True):
            self.assertEqual(updater.pick_asset(self.ASSETS)["url"], "u2")

    def test_a_source_run_on_windows_gets_the_source_zip(self):
        # The PyInstaller tree copied over a source checkout leaves a
        # Cathode.exe nobody runs and the .py files untouched.
        with mock.patch.object(updater.os, "name", "nt"), \
                mock.patch.object(updater.sys, "frozen", False, create=True):
            self.assertEqual(updater.pick_asset(self.ASSETS)["url"], "u1")

    def test_none_when_no_match(self):
        with mock.patch.object(updater.os, "name", "posix"):
            self.assertIsNone(updater.pick_asset(
                [{"name": "cathode-windows-2.1-portable.zip", "url": "u", "size": 1}]))


class TestDownloadProgress(unittest.TestCase):
    def test_streams_and_reports_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src.bin")
            payload = b"x" * (200 * 1024)            # 200 KB -> several chunks
            with open(src, "wb") as f:
                f.write(payload)
            url = Path(src).as_uri()                 # file:// URL, no network
            calls = []
            dest = updater.download(url, os.path.join(tmp, "out"), "got.bin",
                                    on_progress=lambda d, t: calls.append((d, t)),
                                    total=len(payload))
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), payload)  # file landed intact
            self.assertTrue(calls)
            self.assertEqual(calls[-1][0], len(payload))   # ends at 100%
            self.assertEqual(calls[-1][1], len(payload))   # total carried through


class TestApplyScript(unittest.TestCase):
    """Runs the real install script against a throwaway install. The old one
    slept a fixed two seconds that, detached, didn't sleep at all, so it copied
    over a Cathode that hadn't exited yet; it also deleted the archive whether
    or not extraction worked."""

    def _install(self, tmp, archive_files, nested):
        import zipfile
        # The apostrophe is deliberate: it broke the old script's quoting.
        root = os.path.join(tmp, "O'Brien")
        dest = os.path.join(root, "install")
        updates = os.path.join(root, "updates")
        pkg = "_internal" if os.name == "nt" else "cathode"
        for rel, body in {f"{pkg}/old.py": "stale", f"{pkg}/keep.py": "v1",
                          "assets/fonts/mine.ttf": "user font"}.items():
            p = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            Path(p).write_text(body)
        os.makedirs(updates, exist_ok=True)
        archive = os.path.join(updates, "new.zip")
        if archive_files is None:
            Path(archive).write_bytes(b"not a zip")
        else:
            with zipfile.ZipFile(archive, "w") as z:
                for rel, body in archive_files.items():
                    z.writestr(("Cathode/" if nested else "") + rel.replace(
                        "PKG", pkg), body)
        return dest, updates, archive, pkg

    def _run(self, archive, dest, updates):
        import subprocess
        # Stand-in for Cathode: the script must not touch anything until it
        # has exited.
        app = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3)"])
        try:
            script = updater.write_apply_script(archive, dest, updates, pid=app.pid)
            proc = updater.spawn_apply(script)
            import time
            time.sleep(1.5)
            self.assertTrue(os.path.exists(archive), "installed before exit")
        finally:
            app.wait()
        proc.wait(timeout=120)
        return script

    def test_installs_after_exit_and_prunes_only_the_package(self):
        files = {"PKG/keep.py": "v2", "PKG/new.py": "added", "README.md": "r"}
        for nested in (True, False):
            with self.subTest(nested=nested), tempfile.TemporaryDirectory() as tmp:
                dest, updates, archive, pkg = self._install(tmp, files, nested)
                script = self._run(archive, dest, updates)
                read = lambda rel: Path(dest, rel).read_text()
                self.assertEqual(read(f"{pkg}/keep.py"), "v2")
                self.assertEqual(read(f"{pkg}/new.py"), "added")
                self.assertEqual(read("README.md"), "r")
                self.assertFalse(Path(dest, pkg, "old.py").exists())
                self.assertEqual(read("assets/fonts/mine.ttf"), "user font")
                for left in (archive, script, os.path.join(updates, "_stage"),
                             os.path.join(updates, updater.FAILED_LOG)):
                    self.assertFalse(os.path.exists(left), left)

    def test_a_bad_archive_is_kept_and_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest, updates, archive, pkg = self._install(tmp, None, True)
            self._run(archive, dest, updates)
            self.assertTrue(os.path.exists(archive))
            self.assertTrue(os.path.exists(os.path.join(updates, updater.FAILED_LOG)))
            self.assertEqual(Path(dest, pkg, "keep.py").read_text(), "v1")
            self.assertTrue(Path(dest, pkg, "old.py").exists())

    def test_never_installs_under_a_relaunched_cathode(self):
        # Cathode was started again before the installer got going: copying
        # now would swap files out from under it.
        from cathode.app import hold_instance_lock
        if os.name != "nt":
            import shutil as sh
            if not sh.which("flock"):
                self.skipTest("no flock(1) here; the installer skips the lock")
        files = {"PKG/keep.py": "v2"}
        with tempfile.TemporaryDirectory() as tmp:
            dest, updates, archive, pkg = self._install(tmp, files, True)
            relaunched = hold_instance_lock(
                os.path.join(os.path.dirname(updates), updater.LOCK_FILE))
            try:
                self._run(archive, dest, updates)
            finally:
                relaunched.close()
            self.assertEqual(Path(dest, pkg, "keep.py").read_text(), "v1")
            self.assertTrue(os.path.exists(archive))
            self.assertTrue(os.path.exists(os.path.join(updates, updater.FAILED_LOG)))

    def test_a_failed_install_is_reported_on_the_next_launch(self):
        from types import SimpleNamespace
        from cathode.app_menus import MenusMixin
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "updates"))
            Path(tmp, "updates", updater.FAILED_LOG).write_text("x")
            said = []
            app = SimpleNamespace(_runtime_dir=tmp, renderer=SimpleNamespace(
                show_notification=lambda msg, secs: said.append(msg)))
            with mock.patch.object(updater, "check_latest") as net:
                MenusMixin._update_check_launch(app)
            self.assertIn("didn't install", said[0])
            net.assert_not_called()

    def test_powershell_quoting(self):
        self.assertEqual(updater._ps_quote("C:\\O'Brien"), "'C:\\O''Brien'")
        self.assertEqual(updater._ps_quote("a\u2019b"), "'a\u2019\u2019b'")


if __name__ == "__main__":
    unittest.main()
