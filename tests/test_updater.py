"""Unit tests for cathode.updater — version parsing + asset matching."""

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


class TestAssetMatch(unittest.TestCase):
    ASSETS = [
        {"name": "cathode-linux-macos-2.1.zip", "url": "u1", "size": 1},
        {"name": "cathode-windows-2.1-portable.zip", "url": "u2", "size": 2},
    ]

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
