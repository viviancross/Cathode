"""Clipboard on Linux: whichever of wl-paste / xclip / xsel is installed wins,
and having none of them is an empty paste, not an error. Mocked; the real
clipboard is never touched."""

import os
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import clipboard  # noqa: E402


class TestNixClipboard(unittest.TestCase):
    def test_falls_through_to_the_tool_that_exists(self):
        tried = []

        def run(cmd, **k):
            tried.append(cmd[0])
            if cmd[0] != "xsel":
                raise FileNotFoundError(cmd[0])
            return SimpleNamespace(returncode=0, stdout="pasted ✓".encode())
        with mock.patch.object(clipboard.os, "name", "posix"), \
                mock.patch.object(clipboard.subprocess, "run", run):
            self.assertEqual(clipboard.get_text(), "pasted ✓")
        self.assertEqual(tried, ["wl-paste", "xclip", "xsel"])

    def test_no_tool_is_an_empty_paste(self):
        def run(cmd, **k):
            raise subprocess.TimeoutExpired(cmd, 2)
        with mock.patch.object(clipboard.os, "name", "posix"), \
                mock.patch.object(clipboard.subprocess, "run", run), \
                mock.patch.object(clipboard.subprocess, "Popen",
                                  side_effect=FileNotFoundError):
            self.assertEqual(clipboard.get_text(), "")
            self.assertFalse(clipboard.set_text("x"))


if __name__ == "__main__":
    unittest.main()
