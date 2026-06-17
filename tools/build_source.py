#!/usr/bin/env python3
"""Build the cross-platform source zip (used on Linux / Steam Deck).

Writes cathode-v<version>.zip into the sibling `builds/` folder with forward
slashes (so it extracts correctly on Linux — see the zip-for-linux gotcha).
Windows‑install files (install-windows.ps1, cathode.bat) are deliberately left
out of this build.
"""

import fnmatch
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import cathode  # noqa: E402

BUILDS = os.path.join(os.path.dirname(ROOT), "builds")

# Top-level files to include (Linux launcher/installer + docs; NOT Windows ones).
TOP_FILES = [
    "main.py", "requirements.txt", "README.md",
    "cathode.sh", "install.sh", "install-service.sh", "make-shortcut.sh",
]
TREE_DIRS = ["cathode", "assets", "tools", "docs"]

EXCLUDE_DIRS = {"__pycache__", "_winbuild", "preview_out", ".git"}
EXCLUDE_PATTERNS = ["*.pyc", "*.pyo", "*.zip"]
# Windows-install files never belong in the Linux build.
EXCLUDE_NAMES = {"install-windows.ps1", "cathode.bat"}


def _excluded(name):
    return (name in EXCLUDE_NAMES
            or any(fnmatch.fnmatch(name, p) for p in EXCLUDE_PATTERNS))


def main():
    os.makedirs(BUILDS, exist_ok=True)
    ver = cathode.__version__
    out = os.path.join(BUILDS, f"cathode-v{ver}.zip")
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
                dirs[:] = [x for x in dirs if x not in EXCLUDE_DIRS]
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
