"""Build the Linux AppImage: PyInstaller's one-folder app plus the system's
libmpv (and what it links, bar what must come from the host) in an AppDir,
packed by appimagetool. Run on Linux, or in the container:

    docker build -t cathode-linux-build tools/linux
    docker run --rm -v "$PWD:/src" -v "<builds dir>:/builds" cathode-linux-build

The AppImage runs on distributions at least as new as the one it was built
on (glibc): build on the oldest you want to support.
"""

import ctypes.util
import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cathode  # noqa: E402
# Next to the repo (S:/projects/builds/<version>), also when building from a
# worktree under .claude/worktrees/; CATHODE_BUILDS overrides (the container).
REPO = ROOT.split(os.sep + ".claude" + os.sep)[0]
BUILDS = os.path.join(os.environ.get("CATHODE_BUILDS") or os.path.join(os.path.dirname(REPO), "builds"),
                      cathode.__version__)
WORK = os.environ.get("CATHODE_WORK") or os.path.join(ROOT, "_linuxbuild")
# The AppImage project's list of libraries that must come from the host
# (glibc, GL, X11/Wayland, ALSA...): bundling those breaks on other systems.
EXCLUDELIST = os.environ.get("APPIMAGE_EXCLUDELIST", "/opt/excludelist")


def log(msg):
    print(f"[build] {msg}", flush=True)


def libmpv_path() -> str:
    name = ctypes.util.find_library("mpv")
    for d in ("/usr/lib/x86_64-linux-gnu", "/usr/lib64", "/usr/lib", "/usr/local/lib"):
        hits = sorted(glob.glob(os.path.join(d, name or "libmpv.so.*")))
        if hits:
            return os.path.realpath(hits[0])
    raise SystemExit("[build] libmpv not found: install libmpv2 (Debian/Ubuntu) or mpv-libs")


def build():
    lib = libmpv_path()
    log(f"libmpv: {lib}")
    distpath, workpath = os.path.join(WORK, "dist"), os.path.join(WORK, "pyi")
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", "Cathode",
        "--distpath", distpath, "--workpath", workpath, "--specpath", WORK,
        "--exclude-module", "tkinter",
        "--add-data", f"{os.path.join(ROOT, 'assets')}:assets",
        # Loaded by ctypes at run time, so PyInstaller wouldn't find it; its
        # own dependencies are collected with it.
        "--add-binary", f"{lib}:.",
        "--hidden-import", "OpenGL.platform.glx", "--hidden-import", "OpenGL.platform.egl",
        os.path.join(ROOT, "main.py"),
    ]
    log("running PyInstaller...")
    subprocess.run(args, check=True, cwd=ROOT)
    app = os.path.join(distpath, "Cathode")
    # python-mpv looks for the plain soname.
    base = os.path.basename(lib)
    internal = os.path.join(app, "_internal")
    if not base.startswith("libmpv.so.2") and os.path.exists(os.path.join(internal, base)):
        shutil.copy2(os.path.join(internal, base), os.path.join(internal, "libmpv.so.2"))
    return app


def drop_host_libs(app):
    """Remove bundled libraries that must come from the host system."""
    if not os.path.exists(EXCLUDELIST):
        log(f"WARNING: no excludelist at {EXCLUDELIST}; keeping every library")
        return
    names = set()
    for line in open(EXCLUDELIST, encoding="utf-8"):
        line = line.split("#")[0].strip()
        if line:
            names.add(line)
    # libmpv links JACK, which plenty of desktops (Ubuntu, SteamOS) don't
    # install: from the host, its absence would stop libmpv loading at all.
    # mpv tries PipeWire and Pulse first, so the bundled copy rarely talks.
    names.discard("libjack.so.0")
    gone = 0
    for path in glob.glob(os.path.join(app, "_internal", "**", "*.so*"), recursive=True):
        if os.path.basename(path) in names:
            os.remove(path)
            gone += 1
    log(f"left {gone} host libraries to the host")


def appdir(app):
    d = os.path.join(WORK, "Cathode.AppDir")
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(app, os.path.join(d, "usr", "lib", "cathode"), symlinks=True)
    for top in ("README.md", "CHANGELOG.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(os.path.join(ROOT, top), os.path.join(d, "usr", "lib", "cathode", top))
    shutil.copytree(os.path.join(ROOT, "LICENSES"), os.path.join(d, "usr", "lib", "cathode", "LICENSES"))
    with open(os.path.join(d, "AppRun"), "w", newline="\n") as f:
        f.write('#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\n'
                'exec "$HERE/usr/lib/cathode/Cathode" "$@"\n')
    os.chmod(os.path.join(d, "AppRun"), 0o755)
    with open(os.path.join(d, "cathode.desktop"), "w", newline="\n") as f:
        f.write("[Desktop Entry]\nType=Application\nName=Cathode\nComment=IPTV like a satellite box\n"
                "Exec=Cathode\nIcon=cathode\nCategories=AudioVideo;Video;Player;TV;\n")
    shutil.copy2(os.path.join(ROOT, "assets", "cathode.png"), os.path.join(d, "cathode.png"))
    return d


def package(d):
    os.makedirs(BUILDS, exist_ok=True)
    out = os.path.join(BUILDS, f"cathode-linux-x86_64-{cathode.__version__}.AppImage")
    if os.path.exists(out):
        os.remove(out)
    env = dict(os.environ, ARCH="x86_64")
    subprocess.run(["appimagetool", "--appimage-extract-and-run", "--no-appstream", d, out],
                   check=True, env=env)
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from build_source import write_sha256
    write_sha256(out)
    log(f"DONE -> {out}  ({os.path.getsize(out) / 1024 / 1024:.1f} MB)")


def main():
    if not sys.platform.startswith("linux"):
        raise SystemExit("[build] run this on Linux (or in tools/linux's container)")
    os.makedirs(WORK, exist_ok=True)
    app = build()
    drop_host_libs(app)
    package(appdir(app))


if __name__ == "__main__":
    main()
