"""M3U parsing — especially quoted attribute values containing commas."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode import playlist  # noqa: E402


class TestExtinf(unittest.TestCase):
    def test_plain_channel(self):
        chans = playlist._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="one" group-title="News",Channel One\n'
            'http://x/1\n')
        self.assertEqual(len(chans), 1)
        self.assertEqual(chans[0].name, "Channel One")
        self.assertEqual(chans[0].group, "News")
        self.assertEqual(chans[0].epg_id, "one")

    def test_comma_inside_quoted_attr(self):
        chans = playlist._parse(
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="a" group-title="News, Local",Channel One\n'
            'http://x/1\n')
        self.assertEqual(len(chans), 1)
        self.assertEqual(chans[0].name, "Channel One")
        self.assertEqual(chans[0].group, "News, Local")

    def test_comma_in_channel_name(self):
        chans = playlist._parse(
            '#EXTINF:-1 group-title="Kids",Tom, Jerry & Friends\n'
            'http://x/2\n')
        self.assertEqual(chans[0].name, "Tom, Jerry & Friends")
        self.assertEqual(chans[0].group, "Kids")

    def test_bare_url_gets_autonamed(self):
        chans = playlist._parse('http://x/raw\n')
        self.assertEqual(chans[0].name, "Channel 1")

    def test_explicit_channel_number(self):
        chans = playlist._parse(
            '#EXTINF:-1 tvg-chno="42",The Answer\nhttp://x/42\n')
        self.assertEqual(chans[0].number, 42)


if __name__ == "__main__":
    unittest.main()
