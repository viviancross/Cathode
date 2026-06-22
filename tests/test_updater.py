"""Unit tests for cathode.updater — version parsing + asset matching."""

import os
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
