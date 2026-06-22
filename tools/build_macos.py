"""Build a macOS app bundle (Cathode.app) of Cathode with PyInstaller.

Bundles Python + the app + Pillow/numpy.  mpv is NOT bundled; install it once
with `brew install mpv` and Cathode finds it on PATH automatically.

Install once:  pip3 install pyinstaller
RUN THIS ON macOS:  python3 tools/build_macos.py

PyInstaller can't cross-compile, and the result targets the build machine's CPU
arch (Apple Silicon vs Intel) — build on the Mac you want to run it on (or use
`arch -x86_64` under Rosetta for an Intel build).
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
BUILDS = os.path.join(os.path.dirname(ROOT), "builds")
WORK = os.path.join(ROOT, "_macbuild")


def log(msg):
    print(f"[build] {msg}", flush=True)


def build():
    distpath = os.path.join(WORK, "dist")
    workpath = os.path.join(WORK, "pyi")
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--windowed", "--name", "Cathode",
        "--distpath", distpath, "--workpath", workpath, "--specpath", WORK,
        "--add-data", f"{os.path.join(ROOT, 'assets')}:assets",   # ':' on macOS
        "--add-data", f"{os.path.join(ROOT, 'LICENSES')}:LICENSES",
        "--add-data", f"{os.path.join(ROOT, 'README.md')}:.",
        "--add-data", f"{os.path.join(ROOT, 'LICENSE')}:.",
        "--add-data", f"{os.path.join(ROOT, 'THIRD_PARTY_NOTICES.md')}:.",
    ]
    icns = os.path.join(ROOT, "assets", "cathode.icns")
    if os.path.isfile(icns):
        args += ["--icon", icns]
    args.append(os.path.join(ROOT, "main.py"))
    log("running PyInstaller (this takes a minute)...")
    subprocess.run(args, check=True, cwd=ROOT)
    return os.path.join(distpath, "Cathode.app")


def package(app):
    import cathode
    ver = cathode.__version__
    os.makedirs(BUILDS, exist_ok=True)
    out = os.path.join(BUILDS, f"cathode-macos-{ver}.zip")
    if os.path.exists(out):
        os.remove(out)
    log("zipping the .app with ditto (preserves the bundle)...")
    # `ditto` keeps symlinks/permissions/resource forks intact, unlike a plain
    # zip — the standard way to archive a .app on macOS.
    subprocess.run(["ditto", "-c", "-k", "--keepParent", app, out], check=True)
    mb = os.path.getsize(out) / 1024 / 1024
    log(f"DONE -> {out}  ({mb:.1f} MB)")
    log("mpv is required at runtime — install once with `brew install mpv`.")
    log("First launch: right-click Cathode.app > Open (unsigned app) to bypass "
        "Gatekeeper.")


def main():
    if sys.platform != "darwin":
        log("WARNING: this produces a macOS .app and must be run on macOS "
            "(PyInstaller can't cross-compile).")
    os.makedirs(WORK, exist_ok=True)
    package(build())


if __name__ == "__main__":
    main()
