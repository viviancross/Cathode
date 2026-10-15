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
| Liberation Sans (Regular, Bold, Italic) | Red Hat, Inc.; digitized data Google (Arimo) | SIL OFL 1.1 | https://github.com/liberationfonts/liberation-fonts |

Notes:
- **CC BY / CC BY-SA** require attribution (given above). CC BY-SA additionally
  requires that modifications to *the font itself* be shared under the same
  license — Cathode ships these fonts unmodified.
- **OFL 1.1** fonts: the full license is in `LICENSES/fonts/`. The OFL Reserved
  Font Names (e.g. "Space Mono", "Liberation") must not be used on a modified version of the
  font. Cathode ships them unmodified.
- License URLs: CC BY 4.0 https://creativecommons.org/licenses/by/4.0/ ·
  CC BY-SA 4.0 https://creativecommons.org/licenses/by-sa/4.0/ ·
  OFL 1.1 https://openfontlicense.org/

## Video playback: libmpv

Cathode 4 plays video with **libmpv**, mpv's library, loaded into Cathode's own
process (Cathode 3 ran `mpv.exe` as a separate program). The Windows build
bundles `libmpv-2.dll` from the
[shinchiro](https://github.com/shinchiro/mpv-winbuild-cmake) builds; on macOS
and Linux libmpv comes from Homebrew, the distribution, or the AppImage /
Flatpak bundle.

mpv/libmpv is licensed under the **GNU General Public License v2 or later**
(these builds include GPL components). Because Cathode now links it, the
combined program is covered by the GPL. Cathode itself is **GPL v3**
(see `LICENSE`), which is compatible with mpv's "v2 or later": the combined
work is distributed under GPL v3. See `LICENSES/mpv-NOTICE.txt` for mpv's
statement and the written offer for corresponding source code.

## Python runtime libraries (Windows portable build only)

The PyInstaller portable build bundles the Python interpreter and these
libraries; their licenses ship inside the build's `_internal/*.dist-info/`:

| Library | License |
|---------|---------|
| pygame-ce (with SDL 2: zlib license) | LGPL 2.1 |
| python-mpv (`mpv.py`) | GPL v2+ or LGPL v2.1+ |
| PyOpenGL | BSD-style |
| Pillow | MIT-CMU / HPND |
| certifi (CA bundle) | MPL 2.0 (bundled CA data: MPL 2.0) |
| CPython | PSF License |
