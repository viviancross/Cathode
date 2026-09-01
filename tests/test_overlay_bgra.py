"""The overlay buffer mpv reads: premultiplied BGRA, written in place.

Both are easy to break invisibly — a wrong channel order or a lost premultiply
just looks like "the colours are a bit off", and a reopened file still renders
correctly while costing more than the compositing does.
"""

import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.ui import renderer as R


def _numpy_reference(img):
    """The straightforward premultiplied-BGRA conversion, used as ground truth."""
    arr = np.asarray(img, dtype=np.uint8)
    rgb = arr[:, :, :3].astype(np.uint16)
    alpha = arr[:, :, 3:4].astype(np.uint16)
    pm = (rgb * alpha // 255).astype(np.uint8)
    bgra = np.dstack([pm[:, :, 2], pm[:, :, 1], pm[:, :, 0], arr[:, :, 3]])
    return np.ascontiguousarray(bgra).tobytes()


def _sample_image(w=64, h=48):
    """Transparent background, an opaque panel and a half-transparent one —
    the three alpha regimes the UI actually produces."""
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = 200   # R
    arr[:, :, 1] = 100   # G
    arr[:, :, 2] = 50    # B
    arr[5:20, 5:30, 3] = 255
    arr[25:40, 5:30, 3] = 128
    return Image.fromarray(arr, "RGBA")


class TestPremultipliedBGRA(unittest.TestCase):
    def setUp(self):
        R._HAVE_BGRA_PACKER = True

    def test_matches_the_numpy_reference(self):
        img = _sample_image()
        got = np.frombuffer(R._to_premultiplied_bgra(img), np.uint8).astype(int)
        ref = np.frombuffer(_numpy_reference(img), np.uint8).astype(int)
        self.assertEqual(got.size, ref.size)
        # Pillow rounds where the numpy reference truncates, so a channel may
        # differ by one — anything larger means a real conversion bug.
        self.assertLessEqual(np.abs(got - ref).max(), 1)

    def test_channel_order_is_bgra_not_rgba(self):
        img = Image.new("RGBA", (1, 1), (200, 100, 50, 255))
        self.assertEqual(tuple(R._to_premultiplied_bgra(img)), (50, 100, 200, 255))

    def test_alpha_is_premultiplied_and_kept_straight(self):
        img = Image.new("RGBA", (1, 1), (200, 100, 50, 128))
        b, g, r, a = R._to_premultiplied_bgra(img)
        self.assertEqual(a, 128)                 # alpha itself stays straight
        for chan, full in ((b, 50), (g, 100), (r, 200)):
            self.assertAlmostEqual(chan, full * 128 // 255, delta=1)

    def test_transparent_pixels_are_fully_zeroed(self):
        img = Image.new("RGBA", (1, 1), (200, 100, 50, 0))
        self.assertEqual(tuple(R._to_premultiplied_bgra(img)), (0, 0, 0, 0))

    def test_fallback_agrees_with_the_pillow_packer(self):
        img = _sample_image()
        fast = R._to_premultiplied_bgra(img)
        R._HAVE_BGRA_PACKER = False              # force the numpy path
        slow = R._to_premultiplied_bgra(img)
        self.assertEqual(len(fast), len(slow))
        a = np.frombuffer(fast, np.uint8).astype(int)
        b = np.frombuffer(slow, np.uint8).astype(int)
        self.assertLessEqual(np.abs(a - b).max(), 1)


class _FakeRenderer:
    """Just enough of Renderer to exercise the overlay file writes."""

    _close_overlay_file = R.Renderer._close_overlay_file
    _write_overlay = R.Renderer._write_overlay

    def __init__(self, path, w=8, h=4):
        import threading
        self._overlay_path = path
        self._overlay_fh = None
        self._overlay_lock = threading.Lock()
        self.overlay_pos = (0, 0)
        self.width, self.height = w, h
        self.commands = []
        self.player = type("P", (), {"command": lambda _s, *a: None})()
        self.player.command = lambda *a: self.commands.append(a)


class TestOverlayFileWrites(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "overlay.bgra")
        self.r = _FakeRenderer(self.path)

    def tearDown(self):
        self.r._close_overlay_file()

    def test_creates_the_file_on_the_first_frame(self):
        self.r._write_overlay(b"\x01" * 128)
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), b"\x01" * 128)

    def test_keeps_one_handle_across_frames(self):
        self.r._write_overlay(b"\x01" * 128)
        first = self.r._overlay_fh
        self.r._write_overlay(b"\x02" * 128)
        self.assertIs(self.r._overlay_fh, first)

    def test_overwrites_the_same_inode_rather_than_replacing_it(self):
        # mpv mmaps this file once; a new inode would freeze the overlay on the
        # first frame it ever read.
        self.r._write_overlay(b"\x01" * 128)
        ino = os.stat(self.path).st_ino
        self.r._write_overlay(b"\x02" * 128)
        self.assertEqual(os.stat(self.path).st_ino, ino)
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), b"\x02" * 128)

    def test_points_mpv_at_the_buffer_every_frame(self):
        self.r._write_overlay(b"\x00" * 128)
        cmd = self.r.commands[-1]
        self.assertEqual(cmd[0], "overlay-add")
        self.assertIn("bgra", cmd)
        self.assertEqual(cmd[-3:], (8, 4, 8 * 4))   # w, h, stride

    def test_the_overlay_is_placed_at_its_configured_offset(self):
        # Non-zero when the UI is drawn into a box narrower than the display.
        self.r.overlay_pos = (360, 24)
        self.r._write_overlay(b"\x00" * 128)
        cmd = self.r.commands[-1]
        self.assertEqual(cmd[1:4], (1, 360, 24))   # id, x, y

    def test_recovers_after_the_handle_breaks(self):
        self.r._write_overlay(b"\x01" * 128)
        self.r._overlay_fh.close()          # simulate a handle going bad
        self.r._write_overlay(b"\x03" * 128)
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), b"\x03" * 128)


if __name__ == "__main__":
    unittest.main()
