"""One command for a release's artifacts: the source zip, the Windows
portable zip and (through tools/linux's container) the AppImage and
Flatpak, built at the same time, with the unit tests alongside, then every
artifact audited (sha256 sidecar, no backslash paths, nothing that
shouldn't ship). Timings per step at the end.

    python tools/build_all.py            # everything
    python tools/build_all.py --no-linux # skip the container (Windows-only test builds)
    python tools/build_all.py --no-tests

Needs Docker Desktop running for the Linux artifacts. Exits non-zero when
any step fails or an audit finds something."""

import argparse
import hashlib
import os
import subprocess
import sys
import threading
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cathode  # noqa: E402

REPO = ROOT.split(os.sep + ".claude" + os.sep)[0]
BUILDS_ROOT = os.path.join(os.path.dirname(REPO), "builds")
BUILDS = os.path.join(BUILDS_ROOT, cathode.__version__)
IMAGE = "cathode-linux-build"
# Things that must never be inside a shipped zip.
BAD = ("__pycache__", ".pyc", "/.git", ".impeccable", ".claude", "config.json", "cathode.log", "_winbuild",
       "_linuxbuild", "proto/", "scratchpad", ".venv", "Thumbs.db", ".DS_Store", "tests/")


def run(name, cmd, log, env=None):
    """A step as a subprocess, its output to its own log file; (name, seconds, returncode)."""
    t0 = time.monotonic()
    with open(log, "w", encoding="utf-8") as f:
        r = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, env=env)
    return name, time.monotonic() - t0, r.returncode


def docker_cmd():
    # The pip cache in a named volume: wheels download once, not every build.
    return ["docker", "run", "--rm", "--privileged",
            "-v", f"{ROOT}:/src", "-v", f"{BUILDS_ROOT}:/builds", "-v", "cathode-pip-cache:/root/.cache/pip",
            IMAGE]


def audit(path):
    """What's wrong with a shipped zip; [] when nothing is."""
    problems = []
    side = path + ".sha256"
    if not os.path.exists(side):
        problems.append("no sha256 sidecar")
    else:
        want = open(side).read().split()[0].lower()
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != want:
            problems.append("sha256 sidecar MISMATCH")
    if path.endswith(".zip"):
        names = zipfile.ZipFile(path).namelist()
        back = [n for n in names if "\\" in n]
        if back:
            problems.append(f"{len(back)} backslash paths, e.g. {back[0]}")
        bad = sorted({n for n in names for b in BAD if b in n})
        if bad:
            problems.append(f"shouldn't ship: {', '.join(bad[:6])}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-linux", action="store_true", help="skip the AppImage and Flatpak")
    ap.add_argument("--no-tests", action="store_true")
    a = ap.parse_args()
    ver = cathode.__version__
    os.makedirs(BUILDS, exist_ok=True)
    logs = os.path.join(BUILDS, "logs")
    os.makedirs(logs, exist_ok=True)
    py = sys.executable
    print(f"[build-all] {ver} -> {BUILDS}", flush=True)

    steps = [("source+windows", [py, "tools/build_source.py"], [py, "tools/build_windows.py"])]
    if not a.no_tests:
        env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
        steps.append(("tests", [py, "-m", "unittest", "discover", "-s", "tests"], None, env))
    if not a.no_linux:
        steps.append(("linux", ["docker", "build", "-q", "-t", IMAGE, "tools/linux"], docker_cmd()))

    results = []

    def worker(step):
        name, first, second = step[0], step[1], step[2]
        env = step[3] if len(step) > 3 else None
        log = os.path.join(logs, f"{name}.log")
        r = run(name, first, log, env)
        if r[2] == 0 and second:
            r2 = run(name, second, log + ".2", env)
            r = (name, r[1] + r2[1], r2[2])
        results.append(r)

    t0 = time.monotonic()
    threads = [threading.Thread(target=worker, args=(s,), daemon=True) for s in steps]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = time.monotonic() - t0

    failed = False
    print(f"\n[build-all] steps ({total:.0f}s wall):")
    for name, secs, rc in sorted(results, key=lambda r: r[0]):
        tail = ""
        if rc:
            failed = True
            log = os.path.join(logs, f"{name}.log")
            if os.path.exists(log + ".2"):
                log += ".2"
            with open(log, encoding="utf-8", errors="replace") as f:
                tail = " | " + " / ".join(ln.strip() for ln in f.readlines()[-3:])
        print(f"  {name:15} {secs:6.0f}s  {'ok' if rc == 0 else f'FAILED ({rc})'}{tail}")

    want = [f"cathode-linux-macos-{ver}.zip", f"cathode-windows-{ver}-portable.zip"]
    if not a.no_linux:
        want += [f"cathode-linux-x86_64-{ver}.AppImage", f"cathode-linux-x86_64-{ver}.flatpak"]
    print("[build-all] artifacts:")
    for name in want:
        path = os.path.join(BUILDS, name)
        if not os.path.exists(path):
            failed = True
            print(f"  {name:45} MISSING")
            continue
        probs = audit(path)
        failed = failed or bool(probs)
        print(f"  {name:45} {os.path.getsize(path) / 1e6:7.1f} MB  {'; '.join(probs) or 'ok'}")
    print(f"[build-all] logs in {logs}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
