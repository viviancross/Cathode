# Cathode 4 stack spike

One file, `spike.py`, that proves the 4.0 stack before anything is built on
it: Cathode owns its window (pygame-ce / SDL2), libmpv draws video into that
window's OpenGL context, and a fixed 720x480 UI canvas plus a CRT shader are
composited over it on the GPU.

Keys: `C` CRT, `P` picture-in-picture, `F` fullscreen, `Esc` quit.

## Run it

Python 3.10+ and:

```bash
pip install pygame-ce mpv PyOpenGL Pillow
```

plus libmpv for your OS:

- **Windows:** extract `libmpv-2.dll` from shinchiro's `mpv-dev-x86_64-*.7z`
  (github.com/shinchiro/mpv-winbuild-cmake/releases) into `_libmpv/` at the
  repo root.
- **macOS:** `brew install mpv`, then
  `export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib"`.
- **Linux:** `sudo apt install libmpv2` (Fedora: `mpv-libs`, Arch: `mpv`).

```bash
python spike/spike.py
python spike/spike.py --source https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8
python spike/spike.py --seconds 8 --crt --pip --shot out.png   # self-check
```

The last line prints frame rate, main-loop CPU per frame, the hardware decoder
in use, and process CPU, then saves the composed frame.

## Results

| OS | GPU / GL | Result |
|----|----------|--------|
| Windows 10, Python 3.13 | RTX 2080, GL 3.2 core | Pass. nvdec 1080p60 HLS; 1.0-1.4 ms main-loop CPU per frame; process 5% (30fps test pattern), 17% (1080p60 HLS), 2% paused |
| macOS, Linux | | CI: `.github/workflows/spike.yml` |
