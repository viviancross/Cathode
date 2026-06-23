"""Update check via GitHub Releases — notify + download, never self-overwrite.

Queries the repo's latest release, compares its tag to the running version, and
(when newer) downloads the asset matching this platform/build into a folder.
The app then tells the user where it is; installing is manual on purpose, so a
running Cathode.exe / live Deck install is never clobbered.

Stdlib only (urllib + json + ssl; certifi if present, like cathode.plex).
"""

from __future__ import annotations

import json
import os
import re
import ssl
import sys
import urllib.request
from typing import List, Optional, Tuple

REPO = "viviancross/Cathode"
_API = f"https://api.github.com/repos/{REPO}/releases/latest"
_TIMEOUT = 15


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


_SSL = _ssl_context()


def parse_version(s: str) -> Tuple[int, ...]:
    """Digits out of a tag/version string: 'v2.0' -> (2,0), 'v2.2b' -> (2,2),
    '2.0.5' -> (2,0,5). No digits -> () (treated as not-newer)."""
    nums = re.findall(r"\d+", s or "")
    return tuple(int(n) for n in nums)


def is_newer(remote: str, local: str) -> bool:
    r, l = parse_version(remote), parse_version(local)
    return bool(r) and r > l


class UpdateError(Exception):
    pass


def _asset_match(name: str) -> bool:
    """Pick the release asset for this OS: Windows gets the portable Windows zip;
    the Deck, Linux, and macOS all use the cathode-linux-macos source zip."""
    n = name.lower()
    if os.name == "nt":
        return "windows" in n
    return "linux-macos" in n


def check_latest() -> Optional[dict]:
    """Return {tag, assets:[{name,url,size}]} for the latest release, or None if
    the repo has no releases. Raises UpdateError on network/parse failure."""
    req = urllib.request.Request(_API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "Cathode-Updater",
    })
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_SSL) as r:
            data = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None               # no releases published yet
        raise UpdateError(f"GitHub returned {e.code}.")
    except Exception as e:
        raise UpdateError(str(e) or "Couldn't reach GitHub.")
    assets = [{"name": a.get("name", ""), "url": a.get("browser_download_url", ""),
               "size": a.get("size", 0)}
              for a in (data.get("assets") or []) if a.get("browser_download_url")]
    return {"tag": data.get("tag_name", ""), "assets": assets}


def pick_asset(assets: List[dict]) -> Optional[dict]:
    for a in assets:
        if _asset_match(a["name"]):
            return a
    return None


def download(url: str, dest_dir: str, name: str = "",
             on_progress=None, total: int = 0) -> str:
    """Stream a release asset to dest_dir; returns the saved path. `on_progress`,
    if given, is called as on_progress(bytes_done, bytes_total) as it streams
    (bytes_total is 0 when the server doesn't report a length)."""
    os.makedirs(dest_dir, exist_ok=True)
    name = name or os.path.basename(url.split("?", 1)[0]) or "cathode-update"
    dest = os.path.join(dest_dir, name)
    req = urllib.request.Request(url, headers={"User-Agent": "Cathode-Updater"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_SSL) as r, \
                open(dest, "wb") as f:
            clen = total or int(r.headers.get("Content-Length") or 0)
            done = 0
            if on_progress:
                on_progress(0, clen)
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if on_progress:
                    on_progress(done, clen)
    except Exception as e:
        raise UpdateError(str(e) or "Download failed.")
    return dest


def install_dir() -> str:
    """Where the running build lives. Frozen: the exe's folder. Source: the repo
    root (the parent of the cathode/ package, where main.py sits)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write_apply_script(archive: str, dest: str, updates_dir: str) -> str:
    """Write a detached install script that, once Cathode has exited, extracts
    `archive` over `dest` so the NEXT launch runs the new version. Binary build
    archives nest everything under a top-level Cathode/ dir (stripped); the
    source zip is flat. Returns the script path. The app spawns it on quit."""
    os.makedirs(updates_dir, exist_ok=True)
    if os.name == "nt":
        path = os.path.join(updates_dir, "apply_update.bat")
        tmp = os.path.join(updates_dir, "_stage")
        script = (
            "@echo off\r\n"
            "timeout /t 2 /nobreak >nul\r\n"            # let Cathode.exe close
            f'rmdir /s /q "{tmp}" 2>nul\r\n'
            "powershell -NoProfile -Command "
            f"\"Expand-Archive -LiteralPath '{archive}' -DestinationPath '{tmp}' -Force\"\r\n"
            f'if exist "{tmp}\\Cathode" (set SRC={tmp}\\Cathode) else (set SRC={tmp})\r\n'
            f'robocopy "%SRC%" "{dest}" /E /NFL /NDL /NJH /NJS /NC /NS /NP >nul\r\n'
            f'rmdir /s /q "{tmp}" 2>nul\r\n'
            f'del "{archive}" 2>nul\r\n'
            '(del "%~f0") 2>nul\r\n'
        )
    else:
        path = os.path.join(updates_dir, "apply_update.sh")
        tmp = os.path.join(updates_dir, "_stage")
        script = (
            "#!/bin/sh\n"
            "sleep 1\n"                                  # let Cathode release files
            f'rm -rf "{tmp}"; mkdir -p "{tmp}"\n'
            f'case "{archive}" in\n'
            f'  *.tar.gz) tar -xzf "{archive}" -C "{tmp}" ;;\n'
            f'  *) unzip -o "{archive}" -d "{tmp}" ;;\n'
            'esac\n'
            f'src="{tmp}"; [ -d "{tmp}/Cathode" ] && src="{tmp}/Cathode"\n'
            f'cp -R "$src/." "{dest}/"\n'
            f'rm -rf "{tmp}" "{archive}" "$0"\n'
        )
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(script)
    if os.name != "nt":
        os.chmod(path, 0o755)
    return path


def spawn_apply(script: str):
    """Run the apply script detached so it survives this process exiting."""
    import subprocess
    if os.name == "nt":
        DETACHED = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_PROCESS_GROUP
        subprocess.Popen(["cmd", "/c", script], creationflags=DETACHED,
                         close_fds=True)
    else:
        subprocess.Popen(["sh", script], start_new_session=True, close_fds=True)


if __name__ == "__main__":   # tiny self-check (no network)
    assert parse_version("v2.0") == (2, 0)
    assert parse_version("v2.2b") == (2, 2)
    assert parse_version("2.0.5") == (2, 0, 5)
    assert parse_version("nightly") == ()
    assert is_newer("v2.1", "2.0")
    assert is_newer("2.0.5", "2.0")
    assert not is_newer("2.0", "2.0")
    assert not is_newer("1.9", "2.0")
    assert not is_newer("bad", "2.0")
    print("updater self-check OK")
