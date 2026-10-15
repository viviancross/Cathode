"""The DVR: what a downloaded item is when the server isn't there.

The whole point of a download is the flight it survives, so the tests that
matter are the offline ones — the index round-trips without the network, a
detail page builds from disk, a half-finished file resumes from where it
stopped rather than starting a four-gigabyte movie over, and nothing anywhere
writes the account token to a second file.
"""

import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.downloads import DownloadStore
from cathode.plex import _first_part

PAYLOAD = bytes(range(256)) * 400          # 102,400 bytes


class _Handler(http.server.BaseHTTPRequestHandler):
    """Serves PAYLOAD, honouring Range so a resume can be observed."""

    ranged = []          # every Range header the server was sent

    def log_message(self, *a):
        pass

    def do_GET(self):
        rng = self.headers.get("Range", "")
        self.ranged.append(rng)
        start = 0
        if rng.startswith("bytes="):
            start = int(rng[6:].split("-")[0])
        body = PAYLOAD[start:]
        self.send_response(206 if start else 200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Server:
    def __init__(self):
        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/movie.mkv"

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


DETAIL = {"rating_key": "1234", "title": "The Thing", "subtitle": "1982  R",
          "summary": "It imitates.", "duration": 6120, "type": "movie",
          "poster": "", "poster_headers": {}}


def _wait(store, rk, state, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        if store.state(rk) == state:
            return True
        time.sleep(0.02)
    return False


def _wait_for(pred, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


class TestDownloading(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.srv = _Server()
        _Handler.ranged = []

    def tearDown(self):
        self.srv.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_download_lands_whole_and_playable(self):
        s = DownloadStore(self.dir)
        s.add(DETAIL, self.srv.url, {"X-Plex-Token": "secret"})
        self.assertTrue(_wait(s, "1234", "done"), "download never finished")
        path = s.local_path("1234")
        self.assertTrue(path and os.path.exists(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), PAYLOAD)
        self.assertEqual(s.percent("1234"), 100)

    def test_poster_art_is_capped(self):
        # The poster URL comes from the server's metadata; a huge body there
        # was read whole into memory and written beside the film.
        from unittest import mock
        from cathode import downloads
        for cap, kept in ((len(PAYLOAD) - 1, False), (len(PAYLOAD), True)):
            with self.subTest(cap=cap), mock.patch.object(downloads, "POSTER_MAX", cap):
                d = tempfile.mkdtemp(dir=self.dir)
                s = DownloadStore(d)
                s.add(dict(DETAIL, poster=self.srv.url), self.srv.url, {})
                self.assertTrue(_wait(s, "1234", "done"))   # poster goes first
                self.assertEqual(bool(s._items["1234"].get("poster")), kept)

    def test_the_index_survives_a_restart(self):
        s = DownloadStore(self.dir)
        s.add(DETAIL, self.srv.url, {})
        self.assertTrue(_wait(s, "1234", "done"))
        # A second store over the same directory is the next launch.
        again = DownloadStore(self.dir)
        self.assertEqual(again.state("1234"), "done")
        self.assertEqual(again.items()[0]["title"], "The Thing")
        self.assertTrue(again.local_path("1234"))

    def test_the_token_is_never_written_to_disk(self):
        # It already lives in config.json. A second copy is a second thing to
        # leak, and the index is the file most likely to be handed around.
        s = DownloadStore(self.dir)
        s.add(DETAIL, self.srv.url, {"X-Plex-Token": "secret"})
        self.assertTrue(_wait(s, "1234", "done"))
        with open(os.path.join(self.dir, "index.json"), encoding="utf-8") as f:
            self.assertNotIn("secret", f.read())

    def test_an_interrupted_download_resumes_where_it_stopped(self):
        # Half a file on disk, and an index that says it was mid-flight.
        entry = dict(DETAIL, file="1234.mkv", size=len(PAYLOAD),
                     got=40000, state="downloading")
        with open(os.path.join(self.dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"items": [entry]}, f)
        with open(os.path.join(self.dir, "1234.mkv.part"), "wb") as f:
            f.write(PAYLOAD[:40000])

        s = DownloadStore(self.dir)
        # Not resumed on its own: a download that restarts itself over cellular
        # the moment the app opens is a bill, not a feature.
        self.assertEqual(s.state("1234"), "paused")
        self.assertEqual(_Handler.ranged, [])

        s.add(DETAIL, self.srv.url, {})
        self.assertTrue(_wait(s, "1234", "done"))
        self.assertEqual(_Handler.ranged, ["bytes=40000-"])
        with open(s.local_path("1234"), "rb") as f:
            self.assertEqual(f.read(), PAYLOAD)

    def test_removing_takes_the_file_with_it(self):
        s = DownloadStore(self.dir)
        s.add(DETAIL, self.srv.url, {})
        self.assertTrue(_wait(s, "1234", "done"))
        path = s.local_path("1234")
        s.remove("1234")
        self.assertEqual(s.items(), [])
        self.assertEqual(s.state("1234"), "")
        self.assertFalse(os.path.exists(path))

    def test_progress_is_reported_while_it_runs(self):
        seen = []
        s = DownloadStore(self.dir, on_change=lambda: seen.append(True))
        s.add(DETAIL, self.srv.url, {})
        self.assertTrue(_wait(s, "1234", "done"))
        self.assertGreater(len(seen), 1)


class TestOffline(unittest.TestCase):
    """Nothing below touches the network — that is the test."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        entry = dict(DETAIL, file="1234.mkv", size=100, got=100, state="done",
                     offset=900)
        with open(os.path.join(self.dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"items": [entry]}, f)
        with open(os.path.join(self.dir, "1234.mkv"), "wb") as f:
            f.write(b"x" * 100)
        self.store = DownloadStore(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_detail_page_builds_from_disk(self):
        d = self.store.detail("1234")
        self.assertEqual(d["title"], "The Thing")
        self.assertEqual(d["summary"], "It imitates.")
        self.assertEqual(d["duration"], 6120)
        # No series above it, so it plays on its own rather than queueing a show.
        self.assertEqual(d["grandparent_key"], "")

    def test_the_resume_point_is_kept_locally(self):
        self.assertEqual(self.store.offset("1234"), 900)
        self.store.set_offset("1234", 1800)
        self.assertEqual(DownloadStore(self.dir).offset("1234"), 1800)

    def test_a_browse_row_says_what_state_it_is_in(self):
        row = self.store.items()[0]
        self.assertEqual(row["type"], "download")
        self.assertTrue(row["playable"])
        self.assertEqual(row["offset"], 900)

    def test_a_file_deleted_behind_our_back_is_forgotten(self):
        os.remove(os.path.join(self.dir, "1234.mkv"))
        self.assertEqual(DownloadStore(self.dir).items(), [])

    def test_an_unfinished_entry_is_not_playable(self):
        self.store._items["1234"]["state"] = "paused"
        self.assertEqual(self.store.local_path("1234"), "")
        self.assertFalse(self.store.items()[0]["playable"])


class _FlakyHandler(http.server.BaseHTTPRequestHandler):
    """Stops early, the way a dropped connection or a frozen process does.

    `mode` "silent" sends no Content-Length and simply closes half way, which is
    the nasty one: read() returns b"" and a finished download looks exactly the
    same. "abrupt" advertises the full length and then closes, which surfaces as
    an exception instead.
    """

    mode = "silent"
    requests = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        rng = self.headers.get("Range", "")
        self.requests.append(rng)
        start = int(rng[6:].split("-")[0]) if rng.startswith("bytes=") else 0
        body = PAYLOAD[start:]
        if _FlakyHandler.mode == "ok":
            self.send_response(206 if start else 200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        half = body[:len(body) // 2]
        self.send_response(206 if start else 200)
        if _FlakyHandler.mode == "abrupt":
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(half)
        self.close_connection = True


class _FlakyServer(_Server):
    def __init__(self):
        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), _FlakyHandler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


class TestInterrupted(unittest.TestCase):
    """What happens when a download stops before the end of the file.

    Reported from a phone: backgrounding the app stopped the transfer, and the
    half-file was then listed as ON DVR and had to be deleted by hand — with
    every other queued download marked FAILED beside it.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.srv = _FlakyServer()
        _FlakyHandler.requests = []
        _FlakyHandler.mode = "silent"
        # Retries are tested on their own below; elsewhere a timer firing
        # mid-assertion would make these race.
        self._backoff = DownloadStore.RETRY_BACKOFF
        DownloadStore.RETRY_BACKOFF = ()

    def tearDown(self):
        DownloadStore.RETRY_BACKOFF = self._backoff
        self.srv.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_silent_truncation_is_not_a_finished_download(self):
        s = DownloadStore(self.dir)
        s.add(DETAIL, self.srv.url, {}, size=len(PAYLOAD))
        self.assertTrue(_wait_for(lambda: s.state("1234") == "paused"))
        self.assertEqual(s.local_path("1234"), "")       # nothing to play
        self.assertLess(s.percent("1234"), 100)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "1234.mkv")))
        self.assertTrue(os.path.exists(os.path.join(self.dir, "1234.mkv.part")))

    def test_an_abrupt_truncation_is_not_either(self):
        _FlakyHandler.mode = "abrupt"
        s = DownloadStore(self.dir)
        s.add(DETAIL, self.srv.url, {}, size=len(PAYLOAD))
        self.assertTrue(_wait_for(lambda: s.state("1234") == "paused"))
        self.assertEqual(s.local_path("1234"), "")

    def test_it_is_paused_rather_than_failed(self):
        # FAILED is a dead end the user has to clear up; none of this was
        # their doing, and every byte already fetched is still good.
        s = DownloadStore(self.dir)
        s.add(DETAIL, self.srv.url, {}, size=len(PAYLOAD))
        self.assertTrue(_wait_for(lambda: s.state("1234") == "paused"))
        self.assertIn("PAUSED", s.items()[0]["meta"])

    def test_the_rest_of_the_queue_is_not_marked_failed_with_it(self):
        s = DownloadStore(self.dir)
        for i in (1, 2, 3):
            s.add(dict(DETAIL, rating_key=str(i), title=f"Film {i}"),
                  self.srv.url, {}, size=len(PAYLOAD))
        self.assertTrue(_wait_for(
            lambda: all(s.state(str(i)) == "paused" for i in (1, 2, 3))))
        self.assertEqual([r["state"] for r in s.items()], ["paused"] * 3)

    def test_resuming_finishes_it_from_where_it_stopped(self):
        s = DownloadStore(self.dir)
        s.add(DETAIL, self.srv.url, {}, size=len(PAYLOAD))
        self.assertTrue(_wait_for(lambda: s.state("1234") == "paused"))
        part = os.path.getsize(os.path.join(self.dir, "1234.mkv.part"))
        self.assertGreater(part, 0)

        _FlakyHandler.mode = "ok"          # the network came back
        self.assertEqual(s.resume(), 1)
        self.assertTrue(_wait_for(lambda: s.state("1234") == "done"))
        self.assertEqual(_FlakyHandler.requests[-1], f"bytes={part}-")
        with open(s.local_path("1234"), "rb") as f:
            self.assertEqual(f.read(), PAYLOAD)

    def test_resume_brings_the_whole_queue_back(self):
        s = DownloadStore(self.dir)
        for i in (1, 2, 3):
            s.add(dict(DETAIL, rating_key=str(i), title=f"Film {i}"),
                  self.srv.url, {}, size=len(PAYLOAD))
        self.assertTrue(_wait_for(lambda: all(s.state(str(i)) == "paused"
                                              for i in (1, 2, 3))))
        _FlakyHandler.mode = "ok"
        self.assertEqual(s.resume(), 3)
        self.assertTrue(_wait_for(lambda: all(s.state(str(i)) == "done"
                                              for i in (1, 2, 3)), timeout=20))

    def test_resume_leaves_alone_what_the_user_stopped(self):
        s = DownloadStore(self.dir)
        s.add(DETAIL, self.srv.url, {}, size=len(PAYLOAD))
        self.assertTrue(_wait_for(lambda: s.state("1234") == "paused"))
        s.cancel("1234")                    # the user pressing Stop
        _FlakyHandler.mode = "ok"
        self.assertEqual(s.resume(), 0)
        self.assertEqual(s.state("1234"), "paused")

    def test_the_host_is_told_when_a_run_starts_and_ends(self):
        # Android freezes a backgrounded process; this is the bracket the
        # foreground service hangs off.
        seen = []
        s = DownloadStore(self.dir, on_change=lambda: None)
        s.on_active = seen.append
        s.add(DETAIL, self.srv.url, {}, size=len(PAYLOAD))
        self.assertTrue(_wait_for(lambda: seen[-1:] == [False]))
        self.assertEqual(seen[0], True)
        self.assertEqual(seen[-1], False)

    def test_it_retries_on_its_own_after_a_blip(self):
        # A phone walking into a lift should not need the user to come back and
        # press anything. Backoff shortened; the real one is 5s/20s/60s.
        DownloadStore.RETRY_BACKOFF = (0.2, 0.4)
        s = DownloadStore(self.dir)
        s.add(DETAIL, self.srv.url, {}, size=len(PAYLOAD))
        self.assertTrue(_wait_for(lambda: s.state("1234") == "paused"))
        _FlakyHandler.mode = "ok"           # the network came back on its own
        self.assertTrue(_wait_for(lambda: s.state("1234") == "done", timeout=10))

    def test_it_gives_up_retrying_eventually(self):
        # Retrying every minute all night is a battery bill.
        DownloadStore.RETRY_BACKOFF = (0.1, 0.1)
        s = DownloadStore(self.dir)
        s.add(DETAIL, self.srv.url, {}, size=len(PAYLOAD))
        self.assertTrue(_wait_for(lambda: s.state("1234") == "paused"))
        time.sleep(1.0)
        self.assertEqual(s.state("1234"), "paused")
        self.assertEqual(s._retries.get("1234"), len(DownloadStore.RETRY_BACKOFF))

    def test_a_source_can_be_re_derived_when_this_process_has_none(self):
        # The index holds no token, so a download resumed after a restart has
        # to ask the server for a fresh URL.
        entry = dict(DETAIL, file="1234.mkv", size=len(PAYLOAD), got=0,
                     state="downloading")
        with open(os.path.join(self.dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"items": [entry]}, f)
        _FlakyHandler.mode = "ok"
        s = DownloadStore(self.dir)
        asked = []

        def refresh(rk):
            asked.append(rk)
            return self.srv.url, {"X-Plex-Token": "fresh"}

        s.refresh_url = refresh
        s._interrupted.add("1234")          # as if the network had dropped it
        s.resume()
        self.assertTrue(_wait_for(lambda: s.state("1234") == "done"))
        self.assertEqual(asked, ["1234"])


class TestPartInfo(unittest.TestCase):
    """_first_part hands back the whole Part now — the DVR needs its size."""

    def test_it_carries_size_and_container(self):
        meta = {"Media": [{"Part": [{"key": "/library/parts/9/file.mkv",
                                     "size": 42, "container": "mkv"}]}]}
        part = _first_part(meta)
        self.assertEqual(part["key"], "/library/parts/9/file.mkv")
        self.assertEqual(part["size"], 42)
        self.assertEqual(part["container"], "mkv")

    def test_nothing_playable_is_still_none(self):
        self.assertIsNone(_first_part({"Media": [{"Part": [{}]}]}))


if __name__ == "__main__":
    unittest.main()
