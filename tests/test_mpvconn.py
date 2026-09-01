"""Player must work over a connection that isn't a subprocess.

This is the seam the Android port plugs into: an in-process libmpv connection
supplies the same three methods (connect / alive / shutdown) and Player never
learns the difference. The fake below stands in for it, so the seam is exercised
on the desktop long before any Android code exists.
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.player import Player
from cathode.mpvconn import SubprocessConnection


class FakeTransport:
    """Records what Player sends and lets a test push lines back at it."""

    def __init__(self):
        self.sent = []
        self.closed = False
        self._on_line = None
        self._ready = threading.Event()
        self._stop = threading.Event()

    def try_connect(self):
        return True

    def send(self, data: bytes):
        for line in data.splitlines():
            if line.strip():
                self.sent.append(json.loads(line))

    def serve(self, on_line):
        self._on_line = on_line
        self._ready.set()
        self._stop.wait(5.0)      # block like a real reader until closed

    def close(self):
        self.closed = True
        self._stop.set()

    # test helpers
    def commands(self):
        return [m["command"] for m in self.sent if "command" in m]

    def emit(self, obj):
        self._ready.wait(2.0)
        self._on_line((json.dumps(obj) + "\n").encode())


class FakeConnection:
    """An in-process connection, the shape Android's libmpv one will have."""

    def __init__(self):
        self.transport = FakeTransport()
        self.args = None
        self.connected = False
        self.shutdowns = 0

    def connect(self, args):
        self.args = list(args)
        self.connected = True
        return self.transport

    def alive(self):
        return self.connected

    def shutdown(self):
        self.shutdowns += 1
        self.connected = False


class TestPlayerOverAnInjectedConnection(unittest.TestCase):
    def setUp(self):
        self.conn = FakeConnection()
        self.tmp = tempfile.mkdtemp()
        self.player = Player(runtime_dir=self.tmp, connection=self.conn)

    def tearDown(self):
        self.player.terminate()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_start_uses_the_connection_instead_of_launching_anything(self):
        self.player.start()
        self.assertTrue(self.conn.connected)
        self.assertIs(self.player._transport, self.conn.transport)

    def test_the_connection_owns_the_ipc_endpoint_not_the_options(self):
        # An in-process connection has no socket, so Player must not bake one in.
        self.player.start()
        self.assertFalse(any("input-ipc-server" in a for a in self.conn.args))
        self.assertIn("--no-config", self.conn.args)

    def test_commands_reach_the_transport(self):
        self.player.start()
        self.player.command("loadfile", "http://example/x.ts", "replace")
        self.assertIn(["loadfile", "http://example/x.ts", "replace"],
                      self.conn.transport.commands())

    def test_startup_observes_the_properties_the_ui_depends_on(self):
        self.player.start()
        observed = [c[2] for c in self.conn.transport.commands()
                    if c[0] == "observe_property"]
        self.assertEqual(set(observed), {"eof-reached", "osd-width", "osd-height"})

    def test_events_from_the_connection_reach_key_handlers(self):
        fired = threading.Event()
        self.player.start()
        self.player.bind_key("x", fired.set, name="k_x")
        self.conn.transport.emit({"event": "client-message",
                                  "args": ["cathode-key", "k_x"]})
        self.assertTrue(fired.wait(2.0), "key handler never ran")

    def test_terminate_quits_mpv_then_releases_the_connection(self):
        self.player.start()
        self.player.terminate()
        self.assertIn(["quit"], self.conn.transport.commands())
        self.assertTrue(self.conn.transport.closed)
        self.assertEqual(self.conn.shutdowns, 1)


class TestSubprocessConnectionStillBuildsItsCommand(unittest.TestCase):
    """The desktop connection must keep launching mpv exactly as it always did."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_it_adds_its_own_ipc_endpoint(self):
        c = SubprocessConnection(self.tmp, backend="system", mpv_path="mpv")
        cmd = c.build_cmd(["--no-config"])
        self.assertTrue(any("--input-ipc-server=" in a for a in cmd))
        self.assertIn("--no-config", cmd)

    def test_flatpak_wraps_the_same_options(self):
        c = SubprocessConnection(self.tmp, backend="flatpak")
        cmd = c.build_cmd(["--no-config"])
        self.assertEqual(cmd[:2], ["flatpak", "run"])
        self.assertIn("io.mpv.Mpv", cmd)
        self.assertIn("--no-config", cmd)

    def test_an_explicit_command_overrides_everything(self):
        c = SubprocessConnection(self.tmp, mpv_command=["/my/mpv", "--foo"])
        self.assertEqual(c.build_cmd(["--no-config"]), ["/my/mpv", "--foo"])

    def test_shutdown_is_safe_before_connect(self):
        SubprocessConnection(self.tmp, backend="system").shutdown()   # must not raise


if __name__ == "__main__":
    unittest.main()
