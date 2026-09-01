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
            with mock.patch.object(updater.os, "name", nm):
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
            with mock.patch.object(updater.os, "name", nm):
                self.assertIsNone(updater.pick_asset(sides), nm)
                # ...and it still loses when it is listed first.
                self.assertEqual(
                    updater.pick_asset(sides + self.ASSETS)["url"], want, nm)

    def test_non_windows_gets_linux_macos(self):
        with mock.patch.object(updater.os, "name", "posix"):
            self.assertEqual(updater.pick_asset(self.ASSETS)["url"], "u1")

    def test_windows_gets_windows(self):
        with mock.patch.object(updater.os, "name", "nt"):
            self.assertEqual(updater.pick_asset(self.ASSETS)["url"], "u2")

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


if __name__ == "__main__":
    unittest.main()
