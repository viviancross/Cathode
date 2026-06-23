# Third-Party Notices

Cathode bundles or depends on the third-party components below. Each is the
property of its respective authors and is used under the license shown. Full
license texts live in [`LICENSES/`](LICENSES/).

Cathode is a **non-commercial** project and is not affiliated with, endorsed by,
or sponsored by any of these projects or their authors.

---

## Bundled fonts (`assets/fonts/`)

| Font | Author | License | Source |
|------|--------|---------|--------|
| VCR OSD Mono | Riciery Leal | CC BY 4.0 | https://www.dafont.com/vcr-osd-mono.font |
| PxPlus IBM VGA8 | VileR (int10h.org) | CC BY-SA 4.0 | https://int10h.org/oldschool-pc-fonts/ |
| Glass TTY VT220 | Viacheslav Slavinsky | Public domain (Unlicense) | https://github.com/svofski/glasstty |
| Pixel Operator | Jayvee Enaguas (HarvettFox96) | CC0 1.0 (public domain) | https://notabug.org/HarvettFox96/ttf-pixeloperator |
| VT323 | The VT323 Project Authors (Peter Hull) | SIL OFL 1.1 | https://github.com/google/fonts/tree/main/ofl/vt323 |
| Jersey 10 | Sarah Cadigan-Fried | SIL OFL 1.1 | https://github.com/google/fonts/tree/main/ofl/jersey10 |
| Space Mono (file name `Closed_Caption.ttf`) | Colophon Foundry / The Space Mono Project Authors | SIL OFL 1.1 | https://github.com/googlefonts/spacemono |

Notes:
- **CC BY / CC BY-SA** require attribution (given above). CC BY-SA additionally
  requires that modifications to *the font itself* be shared under the same
  license — Cathode ships these fonts unmodified.
- **OFL 1.1** fonts: the full license is in `LICENSES/fonts/`. The OFL Reserved
  Font Names (e.g. "Space Mono") must not be used on a modified version of the
  font. Cathode ships them unmodified.
- License URLs: CC BY 4.0 https://creativecommons.org/licenses/by/4.0/ ·
  CC BY-SA 4.0 https://creativecommons.org/licenses/by-sa/4.0/ ·
  OFL 1.1 https://openfontlicense.org/

## Bundled player — mpv (Windows portable build only)

The Windows portable zip bundles **mpv** (`mpv.exe`, from the
[shinchiro](https://github.com/shinchiro/mpv-winbuild-cmake) Windows builds).
mpv is licensed under the **GNU General Public License v2 or later** (these
builds link GPL components). See `LICENSES/mpv-NOTICE.txt` for the full
statement and the written offer for corresponding source code.

Cathode does **not** link mpv as a library. It launches `mpv.exe` as a separate
process and controls it over mpv's JSON IPC socket. Cathode and mpv are
therefore separate works combined only by aggregation; Cathode's own license
(see `LICENSE`) applies to Cathode's code, and the GPL applies to mpv.

The source-only zip and the Linux/macOS instructions do **not** bundle mpv —
the user installs it themselves (Flatpak `io.mpv.Mpv`, Homebrew, or distro
package).

## Python runtime libraries (Windows portable build only)

The PyInstaller portable build bundles the Python interpreter and these
libraries; their licenses ship inside the build's `_internal/*.dist-info/`:

| Library | License |
|---------|---------|
| Pillow | MIT-CMU / HPND |
| NumPy | BSD-3-Clause |
| certifi (CA bundle) | MPL 2.0 (bundled CA data: MPL 2.0) |
| CPython | PSF License |
