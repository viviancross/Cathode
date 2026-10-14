"""Channel changes under load: presses arrive on their own threads, and mpv's
events for the file being replaced can still be in flight when the next one is
asked for. Headless — a fake transport, no mpv."""

import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.app import App  # noqa: E402
from cathode.config import Config  # noqa: E402
from cathode.player import Player  # noqa: E402
from tests.test_mpvconn import FakeConnection  # noqa: E402


class TestPlayerIgnoresTheReplacedFile(unittest.TestCase):
    def setUp(self):
        self.conn = FakeConnection()
        self.tmp = tempfile.mkdtemp()
        self.started = []
        self.eofs = []
        self.p = Player(runtime_dir=self.tmp, connection=self.conn,
                        on_playback_started=lambda: self.started.append(1),
                        on_eof=self.eofs.append)
        self.p.start()
        self.t = self.conn.transport

    def tearDown(self):
        self.p.terminate()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _load_rid(self):
        return [m for m in self.t.sent
                if m.get("command", [None])[0] == "loadfile"][-1]["request_id"]

    def _seeks(self):
        return [c for c in self.t.commands() if c[0] == "seek"]

    def test_a_late_restart_from_the_last_file_is_not_this_ones(self):
        self.p.play("http://a")
        self.t.emit({"request_id": self._load_rid(), "error": "success"})
        self.t.emit({"event": "start-file"})
        self.p.play("http://b", start=120)
        # A's first frame, sent before mpv read the loadfile for B...
        self.t.emit({"event": "playback-restart"})
        self.t.emit({"event": "end-file", "reason": "eof"})
        self.t.emit({"event": "property-change", "name": "eof-reached",
                     "data": True})
        self.t.emit({"request_id": self._load_rid(), "error": "success"})
        # ...and one more from A between B's reply and B starting.
        self.t.emit({"event": "playback-restart"})
        self.assertEqual(self.started, [])
        self.assertEqual(self.eofs, [])
        self.assertEqual(self._seeks(), [])        # B's resume point kept
        self.t.emit({"event": "start-file"})
        self.t.emit({"event": "playback-restart"})
        self.assertEqual(self.started, [1])
        self.assertEqual(self._seeks(), [["seek", 120.0, "absolute"]])

    def test_window_events_still_arrive_while_a_file_loads(self):
        sizes = []
        self.p._on_resize = lambda w, h: sizes.append((w, h))
        self.p.play("http://a")
        self.t.emit({"event": "property-change", "name": "osd-width", "data": 640})
        self.t.emit({"event": "property-change", "name": "osd-height", "data": 360})
        self.assertEqual(sizes, [(640, 360)])

    def test_headers_and_load_stay_together(self):
        # Two plays at once: each loadfile must directly follow its own
        # headers, or a Plex token rides along on a live-TV stream.
        barrier = threading.Barrier(8)

        def go(i):
            barrier.wait()
            self.p.play(f"http://{i}", headers={"X-Plex-Token": str(i)}
                        if i % 2 else None)
        ts = [threading.Thread(target=go, args=(i,)) for i in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        cmds = [c for c in self.t.commands()
                if c[0] == "loadfile" or c[1:2] == ["http-header-fields"]]
        for hdr, load in zip(cmds[::2], cmds[1::2]):
            i = int(load[1].rsplit("/", 1)[1])
            self.assertEqual(hdr[2], [f"X-Plex-Token: {i}"] if i % 2 else [])


class TestConcurrentTunes(unittest.TestCase):
    def _app(self):
        cfg = Config("")
        cfg.gamepad = False
        app = App(config=cfg, width=320, height=240, fullscreen=False, demo=True)
        from cathode import demo
        app.channels = demo.build_channels(320, 240)
        app.renderer.update = lambda: None
        self.loads = []
        app.player.play = lambda url, *a, **k: self.loads.append(url)
        return app

    def test_every_press_moves_one_channel_and_mpv_ends_on_the_osd_channel(self):
        app = self._app()
        n = len(app.channels)
        presses = 2 * n + 3
        barrier = threading.Barrier(presses)

        def press():
            barrier.wait()
            app._channel_up()
        ts = [threading.Thread(target=press) for _ in range(presses)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        app._cancel_tune_timeout()
        self.assertEqual(app._ch_idx, presses % n)
        self.assertEqual(app.renderer.current_channel_idx, app._ch_idx)
        self.assertEqual(self.loads[-1], app.channels[app._ch_idx].url)

    def test_a_stale_timeout_does_not_reveal_the_next_channel(self):
        app = self._app()
        app._tune(0)
        old = app._tune_gen
        app._tune(1)
        app._finish_tune(True, old)          # channel 0's safety net firing late
        self.assertTrue(app._awaiting_playback)
        self.assertFalse(app.renderer.standby)
        app._finish_tune(True, app._tune_gen)
        self.assertFalse(app._awaiting_playback)
        self.assertTrue(app.renderer.standby)


if __name__ == "__main__":
    unittest.main()
