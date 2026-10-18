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


class TestProviderLists(unittest.TestCase):
    """The shapes an IPTV provider's M3U Plus list takes."""

    def test_name_in_tvg_name_extgrp_and_attributes_after_the_comma(self):
        from cathode.playlist import _parse
        text = """#EXTM3U url-tvg="http://h/xmltv.php?username=u&password=p"
#EXTINF:-1 tvg-id="a.1" tvg-name="Alpha HD" tvg-logo="http://h/1.png" group-title="US| NEWS",
http://h/live/u/p/1.ts
#EXTGRP:UK| SPORTS
#EXTINF:-1 tvg-name="Beta",Beta
http://h/live/u/p/2.ts
#EXTINF:-1  tvg-id="c.3" group-title="CA| KIDS", Gamma: Kids, East
http://h/live/u/p/3.ts
"""
        chans = _parse(text)
        self.assertEqual([c.name for c in chans], ["Alpha HD", "Beta", "Gamma: Kids, East"])
        self.assertEqual([c.group for c in chans], ["US| NEWS", "UK| SPORTS", "CA| KIDS"])
        self.assertEqual(chans[0].epg_id, "a.1")
        self.assertEqual(chans[1].url, "http://h/live/u/p/2.ts")


class TestProviderAgents(unittest.TestCase):
    def test_a_refusal_is_retried_as_a_player_and_the_agent_comes_back(self):
        import urllib.error
        from unittest import mock
        from cathode import playlist
        seen = []

        def fetch(url, agent):
            seen.append(agent)
            if "VLC" not in agent:          # the panel answers only to a player, with its own code
                raise urllib.error.HTTPError(url, 884, "Refused", {}, None)
            return "#EXTM3U\n#EXTINF:-1,One\nhttp://h/1.ts\n"
        with mock.patch.object(playlist, "_fetch_url", fetch):
            chans, agent = playlist.load_as("http://h/get.php?username=u&password=p", "Cathode/1.0 IPTV")
        self.assertEqual(len(chans), 1)
        self.assertIn("VLC", agent)
        self.assertEqual(seen[0], "Cathode/1.0 IPTV")              # its own first

    def test_a_404_is_not_retried(self):
        import urllib.error
        from unittest import mock
        from cathode import playlist
        seen = []

        def fetch(url, agent):
            seen.append(agent)
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        with mock.patch.object(playlist, "_fetch_url", fetch):
            with self.assertRaises(urllib.error.HTTPError):
                playlist.load_as("http://h/list.m3u", "Cathode/1.0 IPTV")
        self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main()
