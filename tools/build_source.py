#!/usr/bin/env python3
"""Build the cross-platform source zip (Linux / macOS).

Writes cathode-linux-macos-<version>.zip with forward-slash paths so it extracts
cleanly on Linux. Bundles the Linux/SteamOS (install.sh) and macOS
(install-macos.sh) install scripts; the Windows ones are left out.
"""

import fnmatch
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cathode  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(ROOT), "builds", cathode.__version__)

# Top-level files to include (non-Windows install scripts).
TOP_FILES = [
    "main.py", "requirements.txt", "README.md",
    "LICENSE", "THIRD_PARTY_NOTICES.md",
    "cathode.sh", "install.sh", "install-service.sh", "make-shortcut.sh",
    "install-macos.sh",
]
TREE_DIRS = ["cathode", "assets", "tools", "LICENSES"]

EXCLUDE_DIRS = {"__pycache__", "_winbuild", "_linuxbuild", "_macbuild",
                "preview_out", ".git"}
EXCLUDE_PATTERNS = ["*.pyc", "*.pyo", "*.zip"]
# Windows-install files never belong in the Linux build.
EXCLUDE_NAMES = {"install-windows.ps1", "cathode.bat"}


def _excluded(name):
    return (name in EXCLUDE_NAMES
            or any(fnmatch.fnmatch(name, p) for p in EXCLUDE_PATTERNS))


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

    mb = os.path.getsize(out) / 1024 / 1024
    print(f"[build] DONE -> {out}  ({n} files, {mb:.2f} MB)")


if __name__ == "__main__":
    main()
