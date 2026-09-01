"""Logo fetching is the app's one untrusted-input path.

Logo URLs arrive in third-party data — XMLTV `<icon src>` and M3U `tvg-logo`,
from playlists people download from IPTV providers — and each one is fetched on
its own thread. A timeout bounds how long a fetch can stall, not how much it can
send, so the size caps are what stop one bad entry from taking the app down.
"""

import io
import os
import shutil
import tempfile
import unittest
import zlib

from PIL import Image

from cathode.logos import LogoStore, _read_capped


class _Resp:
    """Minimal stand-in for an HTTP response body."""

    def __init__(self, payload: bytes, chunk: int = 64 * 1024):
        self._buf = io.BytesIO(payload)
        self._chunk = chunk

    def read(self, n=-1):
        return self._buf.read(self._chunk if n is None or n < 0 else n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestCappedRead(unittest.TestCase):
    def test_reads_a_normal_body_whole(self):
        payload = b"x" * 5000
        self.assertEqual(_read_capped(_Resp(payload), 1 << 20), payload)

    def test_refuses_a_body_over_the_cap(self):
        self.assertIsNone(_read_capped(_Resp(b"x" * 5000), 1000))

    def test_stops_early_rather_than_buffering_everything(self):
        # The point is to not hold the whole thing in memory first: a body far
        # over the cap must be refused without being fully read.
        huge = _Resp(b"x" * (4 << 20), chunk=64 * 1024)
        self.assertIsNone(_read_capped(huge, 128 * 1024))
        self.assertLess(huge._buf.tell(), 1 << 20)

    def test_an_empty_body_is_empty_not_an_error(self):
        self.assertEqual(_read_capped(_Resp(b""), 1024), b"")

    def test_a_body_exactly_at_the_cap_is_allowed(self):
        payload = b"x" * 1000
        self.assertEqual(_read_capped(_Resp(payload), 1000), payload)


class TestDecodeLimits(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cathode-logo-test")
        self.store = LogoStore(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_an_ordinary_logo_decodes(self):
        im = Image.new("RGB", (120, 60), (10, 90, 200))
        out = self.store._decode(im)
        self.assertIsNotNone(out)
        self.assertEqual(out.mode, "RGBA")

    def test_a_decompression_bomb_is_refused_before_it_is_decoded(self):
        # Sized into the band Pillow itself lets through. Pillow hard-errors
        # only above twice its 178 MP limit and merely *warns* between one and
        # two times it, so an 8000x8000 image passes its checks entirely — and
        # is 256 MB once decoded to RGBA. It is also tiny on the wire, so the
        # byte cap does not catch it either. This is the case _decode exists
        # for, and it is refused off the header, before any pixels are read.
        bomb = io.BytesIO()
        Image.new("L", (8000, 8000), 0).save(bomb, format="PNG",
                                             compress_level=9)
        data = bomb.getvalue()
        self.assertLess(len(data), self.store._MAX_BYTES)   # passes the byte cap
        lazy = Image.open(io.BytesIO(data))                 # header only, no pixels
        self.assertGreater(lazy.size[0] * lazy.size[1], self.store._MAX_PIXELS)
        self.assertIsNone(self.store._decode(lazy))

    def test_pillows_own_hard_error_is_still_survivable(self):
        # Above 2x Pillow's limit it raises instead of warning. That happens
        # inside _fetch's try, so it must surface as "no logo", not a crash.
        bomb = io.BytesIO()
        Image.new("L", (20000, 20000), 0).save(bomb, format="PNG",
                                               compress_level=9)
        with self.assertRaises(Exception):
            Image.open(io.BytesIO(bomb.getvalue()))

    def test_a_zero_sized_image_is_refused(self):
        class _Fake:
            size = (0, 0)
            def convert(self, mode):
                raise AssertionError("must not decode a zero-sized image")
        self.assertIsNone(self.store._decode(_Fake()))

    def test_the_pixel_cap_is_the_boundary(self):
        class _Fake:
            def __init__(self, wh):
                self.size = wh
            def convert(self, mode):
                return "decoded"
        cap = self.store._MAX_PIXELS
        self.assertEqual(self.store._decode(_Fake((cap // 1000, 1000))), "decoded")
        self.assertIsNone(self.store._decode(_Fake((cap // 1000 + 1, 1001))))


class TestFetchRefusals(unittest.TestCase):
    """A refused logo must fail like any other missing one: no crash, no cache
    entry left behind, and the channel simply draws without art."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cathode-logo-test")
        self.store = LogoStore(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _fetch_with(self, payload):
        import urllib.request
        url = "http://example.invalid/logo.png"
        orig = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: _Resp(payload)
        try:
            self.store._fetch(url)
        finally:
            urllib.request.urlopen = orig
        return url

    def test_an_oversized_logo_is_recorded_as_a_failure_not_a_crash(self):
        url = self._fetch_with(b"x" * (self.store._MAX_BYTES + 1))
        self.assertIsNone(self.store._orig[url])

    def test_an_oversized_logo_is_not_written_to_the_disk_cache(self):
        self._fetch_with(b"x" * (self.store._MAX_BYTES + 1))
        self.assertEqual(os.listdir(self.dir), [])

    def test_junk_that_is_not_an_image_is_not_cached(self):
        self._fetch_with(b"<html>404 not found</html>")
        self.assertEqual(os.listdir(self.dir), [])

    def test_a_good_logo_is_cached(self):
        buf = io.BytesIO()
        Image.new("RGB", (64, 32), (200, 40, 40)).save(buf, format="PNG")
        url = self._fetch_with(buf.getvalue())
        self.assertIsNotNone(self.store._orig[url])
        self.assertEqual(len(os.listdir(self.dir)), 1)


if __name__ == "__main__":
    unittest.main()
