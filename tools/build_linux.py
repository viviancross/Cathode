"""Build an easy-to-use Linux binary of Cathode with PyInstaller.

Bundles Python + the app + Pillow/numpy into a one-folder app, so users don't
need to create a virtualenv or install Python deps — just extract and run
`./Cathode`.  mpv is NOT bundled (Linux mpv pulls in many shared libraries);
install it once via Flatpak (io.mpv.Mpv) or your package manager and Cathode
auto-detects it.

Install once:  pip install pyinstaller
RUN THIS ON LINUX (e.g. the Steam Deck in Desktop mode):
    python3 tools/build_linux.py

PyInstaller can't cross-compile — the binary targets the OS + CPU arch you build
it on (so build on the Deck for the Deck).
"""

import os
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
BUILDS = os.path.join(os.path.dirname(ROOT), "builds")
WORK = os.path.join(ROOT, "_linuxbuild")


def log(msg):
    print(f"[build] {msg}", flush=True)


def build():
    distpath = os.path.join(WORK, "dist")
    workpath = os.path.join(WORK, "pyi")
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--console", "--name", "Cathode",
        "--distpath", distpath, "--workpath", workpath, "--specpath", WORK,
        "--add-data", f"{os.path.join(ROOT, 'assets')}:assets",   # ':' on Linux
        os.path.join(ROOT, "main.py"),
    ]
    log("running PyInstaller (this takes a minute)...")
    subprocess.run(args, check=True, cwd=ROOT)
    return os.path.join(distpath, "Cathode")


def package(app_dir):
    import cathode
    ver = cathode.__version__
    os.makedirs(BUILDS, exist_ok=True)
    out = os.path.join(BUILDS, f"cathode-linux-{ver}.tar.gz")
    if os.path.exists(out):
        os.remove(out)
    log("creating tar.gz (preserves the executable bit)...")
    with tarfile.open(out, "w:gz") as t:
        t.add(app_dir, arcname="Cathode")
        for top in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
            p = os.path.join(ROOT, top)
            if os.path.exists(p):
                t.add(p, arcname=f"Cathode/{top}")
        lic = os.path.join(ROOT, "LICENSES")
        if os.path.isdir(lic):
            t.add(lic, arcname="Cathode/LICENSES")
    mb = os.path.getsize(out) / 1024 / 1024
    log(f"DONE -> {out}  ({mb:.1f} MB)")
    log("Run it with:  tar xzf <file>.tar.gz && ./Cathode/Cathode")
    log("mpv is required at runtime — install once with "
        "`flatpak install flathub io.mpv.Mpv` (Steam Deck) or your distro's "
        "mpv package; Cathode finds it automatically.")


def main():
    if sys.platform == "win32" or sys.platform == "darwin":
        log("WARNING: this produces a LINUX binary and must be run on Linux "
            "(PyInstaller can't cross-compile).")
    os.makedirs(WORK, exist_ok=True)
    package(build())


if __name__ == "__main__":
    main()
