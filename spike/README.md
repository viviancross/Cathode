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

`--check` (with `--shot`) samples the composed frame: UI banner present,
video inside the PiP box and black outside it, and, with SMPTE bars as the
source, each bar's colour. `--mpvlog FILE` writes mpv's full verbose log.

## Results

| Where | GL | Result |
|-------|----|--------|
| Windows 10, real GPU | RTX 2080, GL 3.2 core | Pass. nvdec 1080p60 HLS; ~1.2 ms main-loop CPU per frame; process 5% (30fps stream), 17% (1080p60 HLS), 2% paused |
| CI Windows | Mesa llvmpipe 4.6 | Pass |
| CI macOS arm64 / Intel | Apple Software Renderer 4.1 | Pass (2-5 fps: no GPU on the runner) |
| CI Ubuntu 24.04 (mpv 0.37) | Mesa llvmpipe 4.5 | Pass |
| Docker Ubuntu 24.04 + Xvfb | Mesa llvmpipe 4.5 | 10/10 |

CI runs every OS twice (`.github/workflows/spike.yml`); job output lands in
each job's summary and annotation, since job logs need a GitHub sign-in.

## What the spike found

- **Software GL needs mpv's dumb mode.** llvmpipe and Apple's software
  renderer hand out uninitialised texture memory; mpv's float intermediates
  pick up garbage and about half of all runs show black or dimmed video, with
  mpv logging a normal render. `gpu-dumb-mode=yes` fixes it and is faster on a
  CPU. Applied automatically when `GL_RENDERER` names a software renderer.
- **mpv leaves GL state changed after `render()`** (texture unit, unpack
  settings, scissor). Reset what the compositor relies on after every call.
- **Software GL has no vsync**; `set_mode(vsync=1)` raises. Fall back to none.
  Harmless with an event-driven loop, which only presents on change.
- **Render non-blocking** (`block_for_target_time=False`) so the UI thread
  never waits on a frame's display time while input is queued.
- mpv's frame callback posts an SDL event; the UI thread sleeps in
  `event.wait()` otherwise. Idle cost is effectively zero.

Still to confirm on real hardware: a Mac with a GPU, and a Linux box with a
GPU (the Steam Deck is a good one), plus a live controller.
