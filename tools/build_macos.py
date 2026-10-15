"""Build the macOS app (Cathode.app, zipped) with PyInstaller, libmpv inside.

RUN THIS ON macOS, once per CPU: the app targets the build machine's arch, so
build on an Apple Silicon Mac for arm64 and on an Intel Mac (or under Rosetta:
`arch -x86_64 python3 ...` with an x86_64 Homebrew in /usr/local) for x86_64.

    brew install mpv python
    python3 -m venv .venv && . .venv/bin/activate
    pip install -r requirements.txt pyinstaller
    python tools/build_macos.py

The app is unsigned: first launch is right-click > Open (or System Settings >
Privacy & Security > Open Anyway).
"""

import glob
import os
import platform
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cathode  # noqa: E402
# Next to the repo (S:/projects/builds/<version>), also when building from a
# worktree under .claude/worktrees/.
REPO = ROOT.split(os.sep + ".claude" + os.sep)[0]
BUILDS = os.path.join(os.path.dirname(REPO), "builds", cathode.__version__)
WORK = os.path.join(ROOT, "_macbuild")
ARCH = platform.machine()          # arm64 | x86_64


def log(msg):
    print(f"[build] {msg}", flush=True)


def strip_dot_dirs(root):
    """Delete any dot-directories under `root` (e.g. .impeccable AI-tool caches
    PyInstaller copied in from assets/) so no agent tooling ships in a release."""
    import shutil
    for dp, dn, _fn in os.walk(root):
        for d in [x for x in dn if x.startswith(".")]:
            shutil.rmtree(os.path.join(dp, d), ignore_errors=True)
            dn.remove(d)


def libmpv_path() -> str:
    # Homebrew: /opt/homebrew on Apple Silicon, /usr/local on Intel.
    for d in ("/opt/homebrew/lib", "/usr/local/lib"):
        hits = glob.glob(os.path.join(d, "libmpv.2.dylib"))
        if hits:
            return os.path.realpath(hits[0])
    raise SystemExit("[build] libmpv not found: brew install mpv")


def build():
    lib = libmpv_path()
    log(f"libmpv: {lib}")
    distpath = os.path.join(WORK, "dist")
    workpath = os.path.join(WORK, "pyi")
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--windowed", "--name", "Cathode", "--osx-bundle-identifier", "io.github.viviancross.Cathode",
        "--distpath", distpath, "--workpath", workpath, "--specpath", WORK,
        "--exclude-module", "tkinter",
        "--add-data", f"{os.path.join(ROOT, 'assets')}:assets",   # ':' on macOS
        "--add-data", f"{os.path.join(ROOT, 'LICENSES')}:LICENSES",
        "--add-data", f"{os.path.join(ROOT, 'README.md')}:.",
        "--add-data", f"{os.path.join(ROOT, 'CHANGELOG.md')}:.",
        "--add-data", f"{os.path.join(ROOT, 'LICENSE')}:.",
        "--add-data", f"{os.path.join(ROOT, 'THIRD_PARTY_NOTICES.md')}:.",
        # Loaded by ctypes at run time, so PyInstaller wouldn't find it; it
        # collects the dylibs it links (ffmpeg, libass...) and relinks them.
        "--add-binary", f"{lib}:.",
        "--hidden-import", "OpenGL.platform.darwin",
    ]
    icns = os.path.join(ROOT, "assets", "cathode.icns")
    if os.path.isfile(icns):
        args += ["--icon", icns]
    args.append(os.path.join(ROOT, "main.py"))
    log("running PyInstaller (this takes a minute)...")
    subprocess.run(args, check=True, cwd=ROOT)
    app = os.path.join(distpath, "Cathode.app")
    # python-mpv looks for libmpv.2.dylib by that name.
    fw = os.path.join(app, "Contents", "Frameworks")
    base = os.path.basename(lib)
    if base != "libmpv.2.dylib" and os.path.exists(os.path.join(fw, base)):
        os.symlink(base, os.path.join(fw, "libmpv.2.dylib"))
    return app


def package(app):
    strip_dot_dirs(app)               # no AI-tool dot-dirs in the release
    # Re-seal after the edits above: Apple Silicon refuses to load code whose
    # (ad-hoc) signature doesn't match.
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app], check=True)
    os.makedirs(BUILDS, exist_ok=True)
    out = os.path.join(BUILDS, f"cathode-macos-{ARCH}-{cathode.__version__}.zip")
    if os.path.exists(out):
        os.remove(out)
    log("zipping the .app with ditto (preserves the bundle)...")
    # `ditto` keeps symlinks/permissions/resource forks intact, unlike a plain
    # zip — the standard way to archive a .app on macOS.
    subprocess.run(["ditto", "-c", "-k", "--keepParent", app, out], check=True)
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from build_source import write_sha256
    write_sha256(out)
    log(f"DONE -> {out}  ({os.path.getsize(out) / 1024 / 1024:.1f} MB)")
    log("First launch: right-click Cathode.app > Open (unsigned app).")


def main():
    if sys.platform != "darwin":
        raise SystemExit("[build] run this on macOS (PyInstaller can't cross-compile)")
    os.makedirs(WORK, exist_ok=True)
    package(build())


if __name__ == "__main__":
    main()
