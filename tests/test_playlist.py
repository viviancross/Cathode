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

        def fetch(url, agent, timeout=30):
            seen.append(agent)
            if "VLC" not in agent:          # the panel answers only to a player, with its own code
                raise urllib.error.HTTPError(url, 884, "Refused", {}, None)
            return "#EXTM3U\n#EXTINF:-1,One\nhttp://h/1.ts\n"
        with mock.patch.object(playlist, "_fetch_url", fetch):
            chans, agent, used = playlist.load_as("http://h/get.php?username=u&password=p", "Cathode/1.0 IPTV")
        self.assertEqual(len(chans), 1)
        self.assertIn("VLC", agent)
        self.assertEqual(used, "http://h/get.php?username=u&password=p")
        self.assertEqual(seen[0], "Cathode/1.0 IPTV")              # its own first

    def test_a_404_is_not_retried(self):
        import urllib.error
        from unittest import mock
        from cathode import playlist
        seen = []

        def fetch(url, agent, timeout=30):
            seen.append(agent)
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        with mock.patch.object(playlist, "_fetch_url", fetch):
            with self.assertRaises(urllib.error.HTTPError):
                playlist.load_as("http://h/list.m3u", "Cathode/1.0 IPTV")
        self.assertEqual(len(seen), 1)


class TestLinkVariants(unittest.TestCase):
    def test_a_get_php_link_has_the_shapes_panels_serve(self):
        from cathode.playlist import link_variants
        v = link_variants("http://h:80/get.php?username=u&password=p&type=m3u_plus&output=ts")
        self.assertEqual(v[0], "http://h:80/get.php?username=u&password=p&type=m3u_plus&output=ts")
        self.assertIn("type=m3u&", v[1] + "&")
        self.assertEqual(v[2], "http://h:80/playlist/u/p/m3u_plus")
        self.assertEqual(link_variants("http://h/list.m3u"), ["http://h/list.m3u"])

    def test_a_panel_that_only_serves_the_playlist_path_is_found(self):
        import urllib.error
        from unittest import mock
        from cathode import playlist

        def fetch(url, agent, timeout=30):
            if "/playlist/" not in url:
                raise urllib.error.HTTPError(url, 884, "Refused", {}, None)
            return "#EXTM3U\n#EXTINF:-1,One\nhttp://h/1.ts\n"
        with mock.patch.object(playlist, "_fetch_url", fetch):
            chans, agent, used = playlist.load_as("http://h/get.php?username=u&password=p&type=m3u_plus", "Cathode/1.0 IPTV")
        self.assertEqual(len(chans), 1)
        self.assertEqual(used, "http://h/playlist/u/p/m3u_plus")


class TestXtreamApi(unittest.TestCase):
    """A panel that refuses the playlist for everyone but serves its API."""

    def _api(self, url, agent):
        import json
        from urllib.parse import urlsplit, parse_qs
        q = parse_qs(urlsplit(url).query)
        action = q.get("action", [""])[0]
        if action == "":
            return {"user_info": {"auth": 1, "status": "Active"}, "server_info": {"output_formats": ["ts"]}}
        if action == "get_live_categories":
            return [{"category_id": "7", "category_name": "US| NEWS"}]
        return [{"num": 3, "name": "Alpha HD", "stream_id": 42, "stream_icon": "http://h/a.png",
                 "epg_channel_id": "alpha.1", "category_id": "7"}]

    def test_channels_come_from_the_api_with_their_stream_urls(self):
        import json
        from unittest import mock
        from cathode import servers
        with mock.patch.object(servers.urllib.request, "urlopen") as uo:
            class R:
                def __init__(self, body): self.body = body
                def read(self): return json.dumps(self.body).encode()
                def __enter__(self): return self
                def __exit__(self, *a): return False
            uo.side_effect = lambda req, timeout=0, context=None: R(self._api(req.full_url, ""))
            rows = servers.xtream_api_channels("http://h:80", "u", "p")
        self.assertEqual(rows, [{"number": 3, "name": "Alpha HD", "url": "http://h:80/live/u/p/42.ts",
                                 "group": "US| NEWS", "logo": "http://h/a.png", "epg_id": "alpha.1"}])

    def test_an_xtream_address_round_trips_and_scrubs(self):
        from cathode import servers
        from cathode.playlist import _scrub
        a = servers.xtream_api_url("http://h:8080", "u", "p")
        self.assertEqual(a, "xtream://h:8080/u/p")
        self.assertEqual(servers.parse_xtream_api(a), ("http://h:8080", "u", "p"))
        self.assertEqual(servers.parse_xtream_api(servers.xtream_api_url("https://h", "u", "p")), ("https://h", "u", "p"))
        self.assertIsNone(servers.parse_xtream_api("http://h/get.php"))
        self.assertEqual(_scrub(a), "xtream://h:8080/***/***")

    def test_a_refused_playlist_falls_back_to_the_api(self):
        import urllib.error
        from unittest import mock
        from cathode import playlist, servers

        def fetch(url, agent, timeout=30):
            raise urllib.error.HTTPError(url, 884, "Refused", {}, None)
        with mock.patch.object(playlist, "_fetch_url", fetch), \
                mock.patch.object(servers, "xtream_api_channels",
                                  lambda *a, **k: [{"number": 1, "name": "One", "url": "http://h/live/u/p/1.ts",
                                                    "group": "", "logo": "", "epg_id": ""}]):
            chans, agent, used = playlist.load_as("http://h/get.php?username=u&password=p&type=m3u_plus", "Cathode/1.0 IPTV")
        self.assertEqual(len(chans), 1)
        self.assertEqual(used, "xtream://h/u/p")


if __name__ == "__main__":
    unittest.main()
