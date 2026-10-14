# Releasing

Checklist for cutting a Cathode release.

1. **Bump the version** — `__version__` in `cathode/__init__.py` and the
   README's "Version" line; add the release's section to `CHANGELOG.md`.
2. **Run the tests** — `python -m unittest discover tests` (all green before
   anything ships).
3. **Build the zips** — they land in `../builds/<version>/`, each with a
   `.sha256` sidecar written next to it:
   - `python tools/build_source.py` — the Linux / macOS source zip
   - `python tools/build_windows.py` — the Windows portable zip (run on Windows).
     The zip ships the interpreter and libraries it was built with, so build
     from a fresh venv on a current Python: `py -3.13 -m venv _winbuild\venv313`,
     then `_winbuild\venv313\Scripts\pip install -r requirements.txt pyinstaller`
     and run the script with `_winbuild\venv313\Scripts\python`. It refuses to run
     on Python older than 3.12 or on anything below `requirements.txt`.
4. **Audit the zips** — list each archive's contents and check nothing
   unexpected shipped: local helper scripts, caches, dot-directories, personal
   configs, or backslash paths in the source zip.
5. **Tag the commit the zips were built from** — commit first, then
   `git tag v<version>` on that commit and push the tag. Check with
   `git rev-list -n1 v<version>`: a tag on an older commit publishes the wrong
   source.
6. **Publish the GitHub release** — create it from the tag, paste the
   CHANGELOG section as the notes, and upload **both zips and both `.sha256`
   files**. The updater picks the highest-versioned release and verifies its
   download against the sidecar, so a release without one skips verification.

## Tags: keep the ports off the desktop line

The ports (Android, Tizen, PS2, Miyoo) publish to this same releases page, and
the desktop app's updater tells them apart **by tag shape**:

- Desktop releases use a bare version — `v3.0`, `3.0.1`. Nothing else.
- **Every port release must carry a platform prefix** — `android-v3.0`,
  `tizen-v3.0`, `ps2-v1.0`, `miyoo-v1.0`.

A port release tagged `v3.1` would be offered to desktop users as their own
update. Asset names are the second guard: the updater only accepts a file named
`cathode-windows-*` or `cathode-linux-macos-*`, so don't reuse those prefixes
for a port's build. `cathode/updater.py` (`is_mainline_tag`, `_asset_match`)
holds both rules, and `tests/test_updater.py` covers them.
