"""Build a self-contained Windows binary of Cathode with PyInstaller.

Bundles Python, the app, pygame-ce (SDL), Pillow, PyOpenGL and libmpv-2.dll,
so the result has no prerequisites: extract and run Cathode.exe.

Requires (install once):  pip install pyinstaller
(libmpv comes from _libmpv/ if present, else shinchiro's mpv-dev build;
7zr.exe for extracting it is downloaded automatically.)
Run from the project root:  python tools/build_windows.py
"""
import os
import re
import subprocess
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)   # so `import cathode` works when run from tools/
import cathode  # noqa: E402
# Release zips land in builds/<version>/ (matches the other build scripts).
# Next to the repo (S:/projects/builds/<version>), also when building from a
# worktree under .claude/worktrees/.
REPO = ROOT.split(os.sep + ".claude" + os.sep)[0]
BUILDS = os.path.join(os.path.dirname(REPO), "builds", cathode.__version__)
WORK = os.path.join(ROOT, "_winbuild")
MPV_DIR = os.path.join(WORK, "libmpv")


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


def _ensure_7zr():
    """Download the standalone 7zr.exe (handles BCJ2-filtered .7z archives)."""
    sevenzr = os.path.join(WORK, "7zr.exe")
    if not os.path.isfile(sevenzr):
        log("downloading 7zr.exe...")
        urllib.request.urlretrieve("https://www.7-zip.org/a/7zr.exe", sevenzr)
    return sevenzr


def fetch_libmpv():
    """libmpv-2.dll: the one in _libmpv/ (what the source checkout runs on),
    else the latest shinchiro mpv-dev x86_64 build."""
    import json
    import shutil
    local = os.path.join(ROOT, "_libmpv", "libmpv-2.dll")
    os.makedirs(MPV_DIR, exist_ok=True)
    out = os.path.join(MPV_DIR, "libmpv-2.dll")
    if os.path.isfile(local):
        shutil.copy2(local, out)
        log(f"libmpv-2.dll from _libmpv/ ({os.path.getsize(out) // 1024 // 1024} MB)")
        return out
    if os.path.isfile(out):
        return out
    with urllib.request.urlopen(
            "https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest") as r:
        assets = json.load(r)["assets"]
    url = next(a["browser_download_url"] for a in assets
               if a["name"].startswith("mpv-dev-x86_64-2") and a["name"].endswith(".7z"))
    archive = os.path.join(WORK, url.rsplit("/", 1)[-1])
    if not os.path.isfile(archive):
        log(f"downloading {os.path.basename(archive)}...")
        urllib.request.urlretrieve(url, archive)
    subprocess.run([_ensure_7zr(), "e", "-y", f"-o{MPV_DIR}", archive, "libmpv-2.dll"], check=True)
    if not os.path.isfile(out):
        raise RuntimeError("7zr did not produce libmpv-2.dll")
    log(f"libmpv-2.dll ready ({os.path.getsize(out) // 1024 // 1024} MB)")
    return out


def build(libmpv):
    distpath = os.path.join(WORK, "dist")
    workpath = os.path.join(WORK, "pyi")
    sep = ";"  # Windows add-data separator
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        # No console: closing it killed the app, and it sat behind the video.
        # Output goes to %LOCALAPPDATA%/cathode/cathode.log instead.
        "--windowed", "--name", "Cathode",
        # Pillow's Tk bridge rides along with PIL; nothing here draws with Tk.
        "--exclude-module", "tkinter", "--exclude-module", "PIL.ImageTk",
        "--exclude-module", "PIL._imagingtk",
        "--distpath", distpath, "--workpath", workpath,
        "--specpath", WORK,
        "--icon", os.path.join(ROOT, "assets", "cathode.ico"),
        "--add-data", f"{os.path.join(ROOT, 'assets')}{sep}assets",
        "--add-binary", f"{libmpv}{sep}.",
        # PyOpenGL picks its platform module at import time.
        "--hidden-import", "OpenGL.platform.win32",
        os.path.join(ROOT, "main.py"),
    ]
    log("running PyInstaller (this takes a minute)...")
    subprocess.run(args, check=True, cwd=ROOT)
    return os.path.join(distpath, "Cathode")


def package(app_dir):
    import cathode
    ver = cathode.__version__
    strip_dot_dirs(app_dir)            # no AI-tool dot-dirs in the release
    os.makedirs(BUILDS, exist_ok=True)
    out_zip = os.path.join(BUILDS, f"cathode-windows-{ver}-portable.zip")
    if os.path.exists(out_zip):
        os.remove(out_zip)
    log("zipping portable build...")
    n = 0
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, _dn, fn in os.walk(app_dir):
            for f in fn:
                full = os.path.join(dp, f)
                rel = os.path.join("Cathode", os.path.relpath(full, app_dir))
                z.write(full, rel.replace(os.sep, "/"))
                n += 1
        # Ship the README + license notices alongside the binary (offline docs +
        # GPL/OFL/CC compliance for the bundled mpv and fonts).
        for top in ("README.md", "CHANGELOG.md", "LICENSE",
                    "THIRD_PARTY_NOTICES.md"):
            p = os.path.join(ROOT, top)
            if os.path.exists(p):
                z.write(p, f"Cathode/{top}")
                n += 1
        lic_dir = os.path.join(ROOT, "LICENSES")
        for dp, _dn, fn in os.walk(lic_dir):
            for f in fn:
                full = os.path.join(dp, f)
                rel = os.path.join("Cathode", "LICENSES",
                                   os.path.relpath(full, lic_dir))
                z.write(full, rel.replace(os.sep, "/"))
                n += 1
    from build_source import write_sha256
    write_sha256(out_zip)
    mb = os.path.getsize(out_zip) / 1024 / 1024
    log(f"DONE -> {out_zip}  ({n} files, {mb:.1f} MB)")


# The build ships the interpreter and libraries it ran on, so their age is the
# user's exposure. 3.3 went out on Python 3.10 and Pillow 9.0 (older than the
# libwebp fix for CVE-2023-4863) although requirements.txt asked for 10+,
# because nothing checked. Build from a venv: see RELEASING.md.
MIN_PYTHON = (3, 12)


def _vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def check_toolchain():
    from importlib.metadata import PackageNotFoundError, version
    bad = []
    if sys.version_info < MIN_PYTHON:
        bad.append(f"Python {sys.version.split()[0]} < "
                   f"{'.'.join(map(str, MIN_PYTHON))}")
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\s*([A-Za-z0-9_.-]+)\s*>=\s*([\d.]+)", line)
            if not m:
                continue
            try:
                have = version(m.group(1))
            except PackageNotFoundError:
                have = "missing"
            if have == "missing" or _vtuple(have) < _vtuple(m.group(2)):
                bad.append(f"{m.group(1)} {have} (needs >= {m.group(2)})")
    if bad:
        raise SystemExit("[build] refusing to build with: " + "; ".join(bad))
    log(f"toolchain: Python {sys.version.split()[0]}, pygame-ce {version('pygame-ce')}, "
        f"Pillow {version('Pillow')}, PyInstaller {version('pyinstaller')}")


def main():
    if os.name != "nt":
        log("WARNING: this produces a Windows binary; run it on Windows.")
    check_toolchain()
    os.makedirs(WORK, exist_ok=True)
    app_dir = build(fetch_libmpv())
    package(app_dir)


if __name__ == "__main__":
    main()
