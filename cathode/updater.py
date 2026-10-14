"""Update check via GitHub Releases — notify + download, never self-overwrite.

Queries the repo's releases, compares the newest mainline tag to the running
version, and (when newer) downloads the asset matching this platform/build into
a folder. Nothing is overwritten while Cathode runs: the app stages an install
script that waits for the process to exit, then copies the new build over it.

The port branches (Android, Tizen, PS2, Miyoo) publish to this same repo, so
this module is deliberately narrow about what counts as an update for the
desktop app: only a bare version tag, and only an asset named with the desktop
build's own prefix. See `is_mainline_tag` and `_asset_match`.

Stdlib only (urllib + json + ssl; certifi if present, like cathode.plex).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import List, Optional, Tuple

from .net import SSL as _SSL

REPO = "viviancross/Cathode"
# The release LIST, not /releases/latest. GitHub's "latest" is whichever release
# was published most recently regardless of its tag, so a port release
# (android-v3.1, tizen-v3.1) would be handed to the desktop app as its own
# update. Filtering the list by tag shape is what keeps the ports invisible.
_API = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
_TIMEOUT = 15

# A mainline desktop release: a bare version, optionally v-prefixed. Anything
# carrying a platform prefix or suffix is another build's release, not ours.
_MAINLINE_TAG = re.compile(r"^v?\d+(?:\.\d+)*$", re.I)


def parse_version(s: str) -> Tuple[int, ...]:
    """Digits out of a tag/version string: 'v2.0' -> (2,0), 'v2.2b' -> (2,2),
    '2.0.5' -> (2,0,5). No digits -> () (treated as not-newer)."""
    nums = re.findall(r"\d+", s or "")
    return tuple(int(n) for n in nums)


def is_mainline_tag(tag: str) -> bool:
    """True for a desktop release tag ('v3.0', '3.0.1'), false for a port's
    ('android-v3.0', 'v3.0-tizen', 'nightly'). Port builds share this repo's
    releases page; the desktop updater must not offer one as an update."""
    return bool(_MAINLINE_TAG.match((tag or "").strip()))


def is_newer(remote: str, local: str) -> bool:
    r, l = parse_version(remote), parse_version(local)
    return bool(r) and r > l


class UpdateError(Exception):
    pass


def _asset_match(name: str) -> bool:
    """Pick the release asset for this build: the Windows exe gets the portable
    Windows zip; the Deck, Linux, macOS and source runs on Windows all use the
    cathode-linux-macos source zip.

    Matched on the desktop build's full filename prefix, not on a loose
    substring. A port release that happened to carry its own windows zip would
    otherwise be downloaded and staged over the desktop install."""
    n = name.lower()
    # The sidecar shares the build's whole name, so it matches every prefix the
    # build does. Today it loses only because the zip happens to sort first.
    if n.endswith(".sha256"):
        return False
    # Only the frozen exe takes the Windows build: a source checkout run with
    # python on Windows would otherwise get the PyInstaller tree copied over it.
    if os.name == "nt" and getattr(sys, "frozen", False):
        return n.startswith("cathode-windows-")
    return n.startswith("cathode-linux-macos-")


def _release_entry(data: dict) -> dict:
    assets = [{"name": a.get("name", ""), "url": a.get("browser_download_url", ""),
               "size": a.get("size", 0)}
              for a in (data.get("assets") or []) if a.get("browser_download_url")]
    return {"tag": data.get("tag_name", ""), "assets": assets}


def check_latest() -> Optional[dict]:
    """Return {tag, assets:[{name,url,size}]} for the newest MAINLINE release, or
    None if the repo publishes none. Raises UpdateError on network/parse failure.

    Drafts, prereleases and the port builds' releases are all skipped, and the
    winner is the highest version rather than the most recently published one —
    publishing a 2.9 patch after 3.0 must not roll anybody back."""
    req = urllib.request.Request(_API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "Cathode-Updater",
    })
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_SSL) as r:
            data = json.loads(r.read() or b"[]")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None               # no releases published yet
        raise UpdateError(f"GitHub returned {e.code}.")
    except Exception as e:
        raise UpdateError(str(e) or "Couldn't reach GitHub.")
    if not isinstance(data, list):
        raise UpdateError("GitHub returned an unexpected response.")
    mainline = [r for r in data
                if isinstance(r, dict)
                and not r.get("draft") and not r.get("prerelease")
                and is_mainline_tag(r.get("tag_name", ""))]
    if not mainline:
        return None
    return _release_entry(max(mainline,
                              key=lambda r: parse_version(r.get("tag_name", ""))))


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


def find_checksum_asset(assets: List[dict], name: str) -> Optional[dict]:
    """The '<name>.sha256' sidecar asset for a release file, or None if the
    release doesn't publish one (verification is then skipped)."""
    want = (name + ".sha256").lower()
    for a in assets:
        if a.get("name", "").lower() == want:
            return a
    return None


def verify_sha256(path: str, checksum_url: str):
    """Compare the downloaded file's sha256 against the sidecar's hex digest.
    Raises UpdateError on mismatch or an unreadable/malformed sidecar."""
    req = urllib.request.Request(checksum_url,
                                 headers={"User-Agent": "Cathode-Updater"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_SSL) as r:
            text = r.read(4096).decode("utf-8", "replace")
    except Exception as e:
        raise UpdateError(f"Couldn't fetch the update checksum: {e}")
    m = re.search(r"\b[0-9a-fA-F]{64}\b", text)
    if not m:
        raise UpdateError("The update checksum file is malformed.")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest().lower() != m.group(0).lower():
        raise UpdateError("The downloaded update failed checksum verification.")


def install_dir() -> str:
    """Where the running build lives. Frozen: the exe's folder. Source: the repo
    root (the parent of the cathode/ package, where main.py sits)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


FAILED_LOG = "apply_update.log"
# The app's single-instance lock, in the runtime dir (the parent of updates/).
# The installer takes it too, so Cathode can't be relaunched mid-copy.
LOCK_FILE = "cathode.lock"


def _ps_quote(s: str) -> str:
    """A PowerShell single-quoted literal. PowerShell treats the curly single
    quotes as quote characters too, so they are doubled along with ' ."""
    return "'" + re.sub("(['\u2018\u2019\u201a\u201b])", r"\1\1", s) + "'"


def write_apply_script(archive: str, dest: str, updates_dir: str,
                       pid: Optional[int] = None) -> str:
    """Write an install script that waits for this process (`pid`) to exit,
    then extracts `archive` over `dest` so the NEXT launch runs the new version.
    Binary build archives nest everything under a top-level Cathode/ dir
    (stripped); the source zip is flat. Returns the script path. The app spawns
    it on quit.

    Any failure leaves the archive in place and appends the reason to
    FAILED_LOG in `updates_dir`; success removes the archive, the staging dir,
    the script and that log. Files the new build no longer ships are removed
    only where nothing of the user's can live: PyInstaller's _internal/ on
    Windows, the cathode/ package on Linux and macOS."""
    import shlex
    os.makedirs(updates_dir, exist_ok=True)
    pid = os.getpid() if pid is None else pid
    tmp = os.path.join(updates_dir, "_stage")
    log = os.path.join(updates_dir, FAILED_LOG)
    lock = os.path.join(os.path.dirname(os.path.abspath(updates_dir)), LOCK_FILE)
    if os.name == "nt":
        path = os.path.join(updates_dir, "apply_update.ps1")
        q = _ps_quote
        rc = "/R:5 /W:1 /NP /NJH /NJS /NFL /NDL"
        script = f"""$ErrorActionPreference = 'Stop'
$archive = {q(archive)}; $dest = {q(dest)}; $stage = {q(tmp)}
$log = {q(log)}; $self = {q(path)}; $lk = $null
try {{
  Wait-Process -Id {int(pid)} -Timeout 60 -ErrorAction SilentlyContinue
  if (Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue) {{ throw 'Cathode did not exit' }}
  # Exclusive: fails if Cathode was already relaunched, and holds off a
  # relaunch until the copy is done.
  $lk = [IO.File]::Open({q(lock)}, 'OpenOrCreate', 'ReadWrite', 'None')
  if (Test-Path -LiteralPath $stage) {{ Remove-Item -LiteralPath $stage -Recurse -Force }}
  Expand-Archive -LiteralPath $archive -DestinationPath $stage -Force
  $src = Join-Path $stage 'Cathode'
  if (-not (Test-Path -LiteralPath $src -PathType Container)) {{ $src = $stage }}
  $int = Join-Path $src '_internal'
  if (Test-Path -LiteralPath $int -PathType Container) {{
    robocopy $int (Join-Path $dest '_internal') /MIR {rc} | Out-Null
    if ($LASTEXITCODE -ge 8) {{ throw "robocopy _internal exit $LASTEXITCODE" }}
  }}
  robocopy $src $dest /E /XD $int {rc} | Out-Null
  if ($LASTEXITCODE -ge 8) {{ throw "robocopy exit $LASTEXITCODE" }}
  Remove-Item -LiteralPath $stage -Recurse -Force
  Remove-Item -LiteralPath $archive, $self -Force
  Remove-Item -LiteralPath $log -ErrorAction SilentlyContinue
}} catch {{
  "$(Get-Date -Format o) update not applied: $_" | Out-File -LiteralPath $log -Append -Encoding utf8
}} finally {{
  if ($lk) {{ $lk.Close() }}
}}
"""
    else:
        path = os.path.join(updates_dir, "apply_update.sh")
        q = shlex.quote
        py = q(sys.executable or "python3")
        script = f"""#!/bin/sh
exec >>{q(log)} 2>&1
trap '[ $? -eq 0 ] || echo "$(date) update not applied"' EXIT
set -e
i=0
while kill -0 {int(pid)} 2>/dev/null && [ $i -lt 60 ]; do sleep 1; i=$((i+1)); done
# Hold Cathode's instance lock while copying (no flock(1) on macOS: skipped).
if command -v flock >/dev/null; then exec 9>>{q(lock)}; flock -n 9; fi
rm -rf {q(tmp)}; mkdir -p {q(tmp)}
{py} -m zipfile -e {q(archive)} {q(tmp)}
src={q(tmp)}; [ -d {q(tmp)}/Cathode ] && src={q(tmp)}/Cathode
cp -R "$src/." {q(dest)}/
if [ -d "$src/cathode" ] && [ -d {q(dest)}/cathode ]; then
  (cd {q(dest)}/cathode && find . -type f ! -path '*/__pycache__/*') |
  while IFS= read -r f; do
    [ -e "$src/cathode/$f" ] || rm -f {q(dest)}/cathode/"$f"
  done
fi
rm -rf {q(tmp)} {q(archive)} "$0" {q(log)}
"""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(script)
    if os.name != "nt":
        os.chmod(path, 0o755)
    return path


def spawn_apply(script: str):
    """Run the apply script so it survives this process exiting. Windows runs
    it through -EncodedCommand, which no execution policy applies to."""
    import base64
    import subprocess
    if os.name == "nt":
        with open(script, encoding="utf-8") as f:
            enc = base64.b64encode(f.read().encode("utf-16-le")).decode("ascii")
        NO_WINDOW, NEW_GROUP = 0x08000000, 0x00000200
        return subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive",
                          "-EncodedCommand", enc],
                         creationflags=NO_WINDOW | NEW_GROUP, close_fds=True)
    else:
        return subprocess.Popen(["sh", script], start_new_session=True,
                                close_fds=True)


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
    assert is_mainline_tag("v3.0") and is_mainline_tag("3.0.1")
    assert not is_mainline_tag("android-v3.0")
    assert not is_mainline_tag("v3.0-tizen")
    print("updater self-check OK")
