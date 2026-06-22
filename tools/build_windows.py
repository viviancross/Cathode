"""Build a self-contained Windows binary of Cathode with PyInstaller.

Bundles Python + the app + Pillow/numpy AND a copy of mpv.exe, so the result
has no prerequisites — extract and run Cathode.exe.

Requires (install once):  pip install pyinstaller
(7zr.exe for extracting the mpv archive is downloaded automatically.)
Run from the project root:  python tools/build_windows.py
"""
import os
import subprocess
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)   # so `import cathode` works when run from tools/
# Rewrite release zips land in builds/rewrite/ (matches build_source.py).
BUILDS = os.path.join(os.path.dirname(ROOT), "builds", "rewrite")
WORK = os.path.join(ROOT, "_winbuild")
MPV_DIR = os.path.join(WORK, "mpv")


def log(msg):
    print(f"[build] {msg}", flush=True)


def _ensure_7zr():
    """Download the standalone 7zr.exe (handles BCJ2-filtered .7z archives)."""
    sevenzr = os.path.join(WORK, "7zr.exe")
    if not os.path.isfile(sevenzr):
        log("downloading 7zr.exe...")
        urllib.request.urlretrieve("https://www.7-zip.org/a/7zr.exe", sevenzr)
    return sevenzr


def fetch_mpv():
    """Download the latest shinchiro mpv x86_64 build and extract mpv.exe."""
    import json
    os.makedirs(MPV_DIR, exist_ok=True)
    out_exe = os.path.join(MPV_DIR, "mpv.exe")
    if os.path.isfile(out_exe):
        log(f"mpv.exe already present ({os.path.getsize(out_exe)//1024//1024} MB)")
        return out_exe

    # Reuse a previously-downloaded archive if present.
    archive = None
    for f in os.listdir(WORK) if os.path.isdir(WORK) else []:
        if f.startswith("mpv-x86_64") and f.endswith(".7z"):
            archive = os.path.join(WORK, f)
            break
    if not archive:
        log("querying latest mpv build...")
        req = urllib.request.Request(
            "https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest",
            headers={"User-Agent": "cathode-build"})
        rel = json.loads(urllib.request.urlopen(req, timeout=60).read())
        assets = [a for a in rel["assets"]
                  if a["name"].startswith("mpv-x86_64-2") and a["name"].endswith(".7z")
                  and "v3" not in a["name"]]
        if not assets:
            assets = [a for a in rel["assets"]
                      if a["name"].startswith("mpv-x86_64") and a["name"].endswith(".7z")]
        asset = assets[0]
        archive = os.path.join(WORK, asset["name"])
        log(f"downloading {asset['name']} ({asset['size']//1024//1024} MB)...")
        urllib.request.urlretrieve(asset["browser_download_url"], archive)

    sevenzr = _ensure_7zr()
    log("extracting mpv.exe with 7zr...")
    # 'e' = extract flat (ignore archive paths) -> mpv.exe lands in MPV_DIR
    subprocess.run([sevenzr, "e", archive, "-o" + MPV_DIR, "mpv.exe", "-y"],
                   check=True, stdout=subprocess.DEVNULL)
    if not os.path.isfile(out_exe):
        raise RuntimeError("7zr did not produce mpv.exe")
    log(f"mpv.exe ready ({os.path.getsize(out_exe)//1024//1024} MB)")
    return out_exe


def build(mpv_exe):
    distpath = os.path.join(WORK, "dist")
    workpath = os.path.join(WORK, "pyi")
    sep = ";"  # Windows add-data separator
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--console", "--name", "Cathode",
        "--distpath", distpath, "--workpath", workpath,
        "--specpath", WORK,
        "--icon", os.path.join(ROOT, "assets", "cathode.ico"),
        "--add-data", f"{os.path.join(ROOT, 'assets')}{sep}assets",
        "--add-binary", f"{mpv_exe}{sep}mpv",
        os.path.join(ROOT, "main.py"),
    ]
    log("running PyInstaller (this takes a minute)...")
    subprocess.run(args, check=True, cwd=ROOT)
    return os.path.join(distpath, "Cathode")


def package(app_dir):
    import cathode
    ver = cathode.__version__
    os.makedirs(BUILDS, exist_ok=True)
    out_zip = os.path.join(BUILDS, f"cathode-ppv-windows-{ver}-portable.zip")
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
        for top in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
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
    mb = os.path.getsize(out_zip) / 1024 / 1024
    log(f"DONE -> {out_zip}  ({n} files, {mb:.1f} MB)")


def main():
    if os.name != "nt":
        log("WARNING: this produces a Windows binary; run it on Windows.")
    os.makedirs(WORK, exist_ok=True)
    mpv_exe = fetch_mpv()
    app_dir = build(mpv_exe)
    package(app_dir)


if __name__ == "__main__":
    main()
