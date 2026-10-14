"""A second Cathode must not start on top of the first: they share the overlay
file, the config and, on Linux, the mpv socket."""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cathode.app import hold_instance_lock, start_log  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestInstanceLock(unittest.TestCase):
    def test_second_holder_is_refused_until_the_first_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cathode.lock")
            first = hold_instance_lock(path)
            self.assertIsNotNone(first)
            # Another process, as a real second launch would be.
            probe = ("import sys; sys.path.insert(0, sys.argv[2]);"
                     "from cathode.app import hold_instance_lock as h;"
                     "sys.exit(0 if h(sys.argv[1]) else 3)")
            run = lambda: subprocess.run([sys.executable, "-c", probe, path, ROOT]).returncode
            self.assertEqual(run(), 3)
            first.close()                      # what process exit does
            self.assertEqual(run(), 0)


class TestLogFile(unittest.TestCase):
    """The Windows build has no console; this file is the only record."""

    def test_output_lands_in_the_log_and_the_last_run_is_kept(self):
        out, err = sys.stdout, sys.stderr
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "cathode.log"), "w") as f:
                f.write("last run")
            try:
                sys.stdout = sys.stderr = None      # what --windowed gives us
                path = start_log(tmp)
                print("tuned")
                sys.stderr.write("Traceback\n")
            finally:
                log = sys.stdout._streams[0]
                sys.stdout, sys.stderr = out, err
                log.close()
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "tuned\nTraceback\n")
            with open(path + ".1") as f:
                self.assertEqual(f.read(), "last run")


if __name__ == "__main__":
    unittest.main()
