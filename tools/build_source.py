#!/usr/bin/env python3
"""Build the cross-platform source zip: what source installs update from.

Writes cathode-linux-macos-<version>.zip with forward-slash paths so it extracts
cleanly on Linux. Bundles the venv launcher and the Linux helper scripts; the
Windows launcher is left out.
"""

import fnmatch
import hashlib
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cathode  # noqa: E402

# Next to the repo (S:/projects/builds/<version>), also when building from a
# worktree inside the repository.
def _repo(d):
    """The repository's root: up from here to the folder holding .git as a
    folder (a worktree's .git is a file), else here."""
    while not os.path.isdir(os.path.join(d, ".git")) and os.path.dirname(d) != d:
        d = os.path.dirname(d)
    return d if os.path.isdir(os.path.join(d, ".git")) else ROOT


REPO = _repo(ROOT)
OUT_DIR = os.path.join(os.path.dirname(REPO), "builds", cathode.__version__)

# Top-level files to include (no Windows launcher).
TOP_FILES = [
    "main.py", "requirements.txt", "README.md", "CHANGELOG.md",
    "LICENSE", "THIRD_PARTY_NOTICES.md",
    "cathode.sh", "install-service.sh", "make-shortcut.sh",
]
TREE_DIRS = ["cathode", "assets", "tools", "LICENSES"]

EXCLUDE_DIRS = {"__pycache__", "_winbuild", "_linuxbuild", "_macbuild",
                "preview_out", ".git"}
EXCLUDE_PATTERNS = ["*.pyc", "*.pyo", "*.zip"]
# Windows-install files never belong in the Linux build; make_steam_art.py is
# a local Steam-library asset helper, not part of the app.
EXCLUDE_NAMES = {"cathode.bat", "make_steam_art.py"}


def _excluded(name):
    return (name in EXCLUDE_NAMES
            or any(fnmatch.fnmatch(name, p) for p in EXCLUDE_PATTERNS))


def write_sha256(path):
    """Write the '<zip>.sha256' sidecar the in-app updater verifies against
    (sha256sum format: '<hex digest>  <filename>')."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    side = path + ".sha256"
    with open(side, "w") as f:
        f.write(f"{h.hexdigest()}  {os.path.basename(path)}\n")
    print(f"[build] sha256 -> {side}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    ver = cathode.__version__
    out = os.path.join(OUT_DIR, f"cathode-linux-macos-{ver}.zip")
    if os.path.exists(out):
        os.remove(out)

    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for t in TOP_FILES:
            p = os.path.join(ROOT, t)
            if os.path.exists(p) and not _excluded(t):
                z.write(p, t)
                n += 1
        for d in TREE_DIRS:
            base = os.path.join(ROOT, d)
            for root, dirs, files in os.walk(base):
                # Skip EXCLUDE_DIRS and ALL dot-directories (.git, .impeccable
                # and any other AI-agent tool cache) so they never ship.
                dirs[:] = [x for x in dirs
                           if x not in EXCLUDE_DIRS and not x.startswith(".")]
                for f in files:
                    if _excluded(f):
                        continue
                    full = os.path.join(root, f)
                    arc = os.path.relpath(full, ROOT).replace(os.sep, "/")
                    z.write(full, arc)
                    n += 1

    write_sha256(out)
    mb = os.path.getsize(out) / 1024 / 1024
    print(f"[build] DONE -> {out}  ({n} files, {mb:.2f} MB)")


if __name__ == "__main__":
    main()
