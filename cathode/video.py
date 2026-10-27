"""Video: libmpv in-process, drawing into Cathode's own OpenGL context.

mpv runs on its own threads; nothing here touches app state from them. Every
mpv event is forwarded through `post`, which queues it for the UI thread.
"""

import os
import threading
from typing import Callable, Optional

from . import paths

# Windows looks for libmpv-2.dll on PATH: next to the frozen exe, or _libmpv/
# in a source checkout. Must happen before `import mpv`.
if os.name == "nt":
    os.environ["PATH"] = os.pathsep.join(paths.libmpv_dirs() + [os.environ.get("PATH", "")])
else:
    # python-mpv asks ctypes.util.find_library("mpv"), which can't see inside
    # an AppImage or .app, nor Homebrew's lib folder on Apple Silicon. Answer
    # it with a bundled copy first, then Homebrew's.
    import ctypes.util
    import glob

    def _libmpv():
        for d in paths.libmpv_dirs() + ["/opt/homebrew/lib", "/usr/local/lib"]:
            for pat in ("libmpv.so.2", "libmpv.so.1", "libmpv.so", "libmpv.2.dylib", "libmpv.dylib"):
                hits = glob.glob(os.path.join(d, pat))
                if hits:
                    return hits[0]
        return None
    _found = _libmpv()
    if _found:
        _find_library = ctypes.util.find_library
        ctypes.util.find_library = lambda name: _found if name == "mpv" else _find_library(name)

import mpv  # noqa: E402

# GL_RENDERER substrings that mean "no GPU". Software GL hands out
# uninitialised texture memory, mpv's float intermediates pick up garbage, and
# about half of all runs show black or dimmed video while mpv logs a normal
# render (found in the 4.0 spike). Dumb mode skips the intermediates and is
# the faster choice on a CPU anyway.
_SOFTWARE_GL = ("llvmpipe", "softpipe", "software")


# The FORMAT key's picture formats, in the order it cycles them: (key, label,
# mpv properties). Original keeps the picture's shape (pillar or letterbox);
# Zoom fills the screen and crops; Stretch fills it and distorts; 4:3 fixes a
# 4:3 picture a stream mislabels as widescreen.
FORMATS = [
    ("original", "Original", {"keepaspect": True, "panscan": 0.0, "video-aspect-override": "no"}),
    ("zoom", "Zoom", {"keepaspect": True, "panscan": 1.0, "video-aspect-override": "no"}),
    ("stretch", "Stretch", {"keepaspect": False, "panscan": 0.0, "video-aspect-override": "no"}),
    ("4:3", "4:3", {"keepaspect": True, "panscan": 0.0, "video-aspect-override": "4:3"}),
]


def format_label(key: str) -> str:
    return next((label for k, label, _ in FORMATS if k == key), FORMATS[0][1])


class Video:
    """One mpv instance. `post(kind, **data)` must be safe to call from any
    thread; it is how mpv's events reach the UI thread."""

    def __init__(self, post: Callable, renderer: str, user_agent: str = "",
                 volume: int = 80, extra: Optional[dict] = None, log_path: str = ""):
        self._post = post
        opts = dict(
            # auto-copy: decode in hardware but hand the frames back to
            # system memory, so the deinterlacer can take them. auto-safe
            # left them on the GPU (cuda), where bwdif can't run: mpv dropped
            # the filter and every interlaced channel played interlaced.
            vo="libmpv", hwdec="auto-copy", keep_open="yes", idle="yes",
            # A file queued behind this one (follow()) is opened as soon as
            # this one's source has been read to its end, so a live stream's
            # replacement is ready by the time the buffered picture runs out.
            prefetch_playlist="yes",
            input_default_bindings=False, input_vo_keyboard=False,
            osc=False, cache="yes", demuxer_max_bytes="64MiB",
            # Pause-live: keep the recent past so REW can reach back into it.
            demuxer_max_back_bytes="128MiB",
            vf="bwdif=deint=1", volume=str(volume),
            # A deeper audio buffer: the default 0.2 s ran dry ("Audio device
            # underrun detected") at a live handover on a Windows PC, heard
            # as a glitch; half a second rides it out.
            audio_buffer=0.5,
            sub_fonts_dir=paths.asset("fonts"))     # the bundled fonts, for subtitles
        if user_agent:
            opts["user_agent"] = user_agent
        if any(s in renderer.lower() for s in _SOFTWARE_GL):
            opts["gpu-dumb-mode"] = "yes"
        if log_path:
            opts["log_file"] = log_path
        opts.update(extra or {})
        # mpv's warnings and errors go to cathode.log: a glitch on someone's
        # PC (a damaged audio frame, an audio underrun, a decoder giving up)
        # leaves its cause there. Repeats are counted, not written again.
        self._last_log, self._log_repeats = None, 0
        self.player = mpv.MPV(log_handler=self._on_log, loglevel="warn", **opts)
        self.ctx = None
        self._want = None        # playlist entry id of the file we asked for
        self._current = None     # entry id of the file mpv says it started
        # mpv's event thread can report the new file starting before loadfile
        # returns; it waits on this until play() has recorded what it asked for.
        self._ids = threading.Lock()
        self._drained = None     # entry whose source end was reported
        self.player.register_event_callback(self._on_event)
        # Tracks come and go after a start: broadcast captions (EIA-608/708
        # in the picture) become a track only when caption data turns up.
        self.player.observe_property("track-list", lambda _name, _v: self._post("tracks_changed"))
        # keep-open holds a file that ends on its last frame, paused, and sends
        # no END_FILE: its end is eof-reached turning true. Without this a live
        # stream the server closed sat paused instead of being picked back up.
        self.player.observe_property("eof-reached", self._on_eof)
        # The source read to its end while picture is still buffered: for a
        # live stream, the moment to queue its replacement.
        self.player.observe_property("demuxer-cache-state", self._on_cache)
        # Waiting on the network with nothing left to show.
        self.player.observe_property("paused-for-cache", self._on_stall)

    def _on_log(self, level, prefix, text):
        line = f"{prefix}: {text.strip()}"
        # The chosen output can't be opened (unplugged, a different PC): mpv
        # would play on in silence. Back to the default output, and say so.
        if level == "error" and "Could not open/initialize audio device" in text and                 (self.player["audio-device"] or "auto") != "auto":
            print(f"[video] audio output {self.player['audio-device']!r} isn't there: using the default")
            self.player["audio-device"] = "auto"
            self._post("audio_fallback")
        if line == self._last_log:
            self._log_repeats += 1
            return
        if self._log_repeats:
            print(f"[mpv] (repeated {self._log_repeats} more times)")
        self._last_log, self._log_repeats = line, 0
        print(f"[mpv] {level} {line}"[:300])

    # ── GL ────────────────────────────────────────────────────────────────

    def attach_gl(self, get_proc_address):
        """Create the render context. Call on the UI thread with its GL
        context current. mpv's frame callback becomes a 'frame' post."""
        self._gpa = mpv.MpvGlGetProcAddressFn(lambda _, name: get_proc_address(name))
        self.ctx = mpv.MpvRenderContext(self.player, "opengl",
                                        opengl_init_params={"get_proc_address": self._gpa})
        self.ctx.update_cb = lambda: self._post("frame")

    def render(self, fbo: int, w: int, h: int) -> bool:
        """Draw the newest frame into `fbo` if there is one. Never blocks for
        the frame's display time: the UI thread must stay free for input."""
        if not self.ctx or not self.ctx.update():
            return False
        self.redraw(fbo, w, h)
        return True

    def redraw(self, fbo: int, w: int, h: int):
        """Draw the current frame unconditionally (after a resize)."""
        if self.ctx:
            self.ctx.render(flip_y=True, block_for_target_time=False,
                            opengl_fbo={"w": w, "h": h, "fbo": fbo,
                                        "internal_format": 0x8058})   # GL_RGBA8

    def report_swap(self):
        if self.ctx:
            self.ctx.report_swap()

    # ── Playback ──────────────────────────────────────────────────────────

    def play(self, url: str, headers: Optional[dict] = None, start: float = 0, sub_delay: float = 0.0,
             audio: Optional[str] = None):
        """Load `url`, replacing whatever plays. Events about any earlier file
        are ignored from here on: only this load's start can reveal it.
        `audio` is a separate audio stream played with it (YouTube's)."""
        # Always set (empty clears), so a Plex token can't ride along onto the
        # next live stream. Headers go out before the load they belong to.
        self.player["http-header-fields"] = (
            [f"{k}: {v}" for k, v in headers.items()] if headers else [])
        self.player["audio-files"] = [audio] if audio else []
        self.player["start"] = str(start) if start > 0 else "none"
        self.player["sub-delay"] = sub_delay     # a transcode's clock starts mid-file
        with self._ids:
            self._current = None
            self.player.pause = False
            rv = self.player.command("loadfile", url, "replace")
            # Again after: a file that ended under keep-open re-pauses itself,
            # and the next one would start paused (a retuned live stream sat still).
            self.player.pause = False
            self._want = rv.get("playlist_entry_id") if isinstance(rv, dict) else None

    def stop(self):
        with self._ids:
            self._want = self._current = None
        self.player.command("stop")

    def follow(self, url: str):
        """Play `url` straight after the current file, with no gap if it opens
        in time (mpv prefetches it); it becomes the file we want."""
        with self._ids:
            try:
                self.player.command("playlist-clear")   # all but the one playing
                rv = self.player.command("loadfile", url, "append")
            except Exception as e:                  # the drop then ends it, and that reconnects
                print(f"[video] follow failed: {e!r}"[:300])
                return
            self._want = rv.get("playlist_entry_id") if isinstance(rv, dict) else None

    def _on_cache(self, _name, state):
        if not (state and state.get("eof")):
            return
        with self._ids:
            if self._current is None or self._current != self._want or self._drained == self._current:
                return
            self._drained = self._current
        self._post("video_draining")

    def _on_stall(self, _name, stalled):
        with self._ids:
            ours = self._current is not None and self._current == self._want
        if ours:
            self._post("video_buffering", on=bool(stalled))

    def _on_eof(self, _name, reached):
        with self._ids:
            ours = self._want is None or self._current == self._want
        if reached and ours:
            self._post("video_ended", reason="eof")

    def _on_event(self, event):
        """mpv's event thread. Translate, filter to the file we asked for,
        and post; never touch app state here."""
        with self._ids:
            self._on_event_locked(event)

    def _on_event_locked(self, event):
        eid = event.event_id.value
        if eid == mpv.MpvEventID.START_FILE:
            entry = event.data.playlist_entry_id
            self._current = entry
        elif eid == mpv.MpvEventID.PLAYBACK_RESTART:
            # No entry id on this event: it is about whatever started last,
            # so it counts only once our own load has started.
            if self._want is None or self._current == self._want:
                self._post("video_started")
        elif eid == mpv.MpvEventID.END_FILE:
            d = event.data
            if self._want is not None and d.playlist_entry_id != self._want:
                return            # the file we replaced, not the one we want
            reason = {d.EOF: "eof", d.ERROR: "error"}.get(d.reason)
            if reason:
                self._post("video_ended", reason=reason)

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def volume(self) -> int:
        return int(self.player.volume or 0)

    @volume.setter
    def volume(self, v: int):
        self.player.volume = max(0, min(100, int(v)))

    @property
    def muted(self) -> bool:
        return bool(self.player.mute)

    @muted.setter
    def muted(self, on: bool):
        self.player.mute = bool(on)

    @property
    def paused(self) -> bool:
        return bool(self.player.pause)

    @paused.setter
    def paused(self, on: bool):
        self.player.pause = bool(on)

    def set_format(self, key: str):
        """Apply a picture format from FORMATS (unknown keys: Original)."""
        props = next((p for k, _, p in FORMATS if k == key), FORMATS[0][2])
        for name, value in props.items():
            try:
                self.player[name] = value
            except Exception:
                pass        # an mpv without the property keeps its default

    def seek(self, seconds: float, mode: str = "relative"):
        try:
            self.player.command("seek", seconds, mode)
        except Exception:
            pass        # nothing loaded, or not seekable

    def prop(self, name):
        """A property, or None when there's nothing loaded to have it.
        (python-mpv's player[name] reads *options*: properties such as
        time-pos are attributes, dashes as underscores.)"""
        try:
            return getattr(self.player, name.replace("-", "_"))
        except Exception:
            return None

    def tracks(self, kind: str) -> list:
        """[{id, lang, title, selected, name}] for kind 'audio' or 'sub';
        name is what a person would call it."""
        out = []
        for t in self.prop("track-list") or []:
            if t.get("type") == kind:
                cc = str(t.get("codec", "")).startswith("eia_")
                name = t.get("title") or (f"{t['lang'].upper()}" if t.get("lang") else "") or \
                    ("Closed captions" if cc else f"Track {t.get('id')}")
                out.append({"id": t.get("id"), "lang": t.get("lang", ""), "title": t.get("title", ""),
                            "selected": bool(t.get("selected")), "name": name,
                            "external": bool(t.get("external")), "file": t.get("external-filename", "")})
        return out

    def apply_subtitles(self, on: bool):
        """The subtitles setting, on a stream that just started: on keeps a
        chosen track or picks the first; off shows none."""
        subs = self.tracks("sub")
        if not on:
            if any(t["selected"] for t in subs):
                self.set_track("sub", None)
        elif subs and not any(t["selected"] for t in subs):
            self.set_track("sub", subs[0]["id"])

    def cycle_subtitles(self) -> str:
        """Off, then each track in turn: the name of what's on now, '' for
        off, None when the stream has none."""
        subs = self.tracks("sub")
        if not subs:
            return None
        cur = next((i for i, t in enumerate(subs) if t["selected"]), -1)
        nxt = cur + 1
        if nxt >= len(subs):
            self.set_track("sub", None)
            return ""
        self.set_track("sub", subs[nxt]["id"])
        return subs[nxt]["name"]

    def _try(self, what: str, fn) -> bool:
        """A track command mpv may refuse (a file the server won't hand over,
        a track already gone): said in the log, never the end of the app."""
        try:
            fn()
            return True
        except Exception as e:
            print(f"[video] {what} failed: {e!r}"[:300])
            return False

    def set_track(self, kind: str, tid):
        key = "aid" if kind == "audio" else "sid"
        self._try(f"{key}={tid}", lambda: self.player.__setitem__(key, tid if tid is not None else "no"))

    def add_subtitle(self, url: str, title: str = "", lang: str = "", select: bool = False) -> bool:
        """A subtitle file for the playing video, fetched with its headers;
        select shows it straight away. False when mpv couldn't load it."""
        return self._try("sub-add", lambda: self.player.command("sub-add", url, "select" if select else "auto",
                                                                title or "", lang or ""))

    def remove_subtitle(self, tid) -> bool:
        return self._try("sub-remove", lambda: self.player.command("sub-remove", tid))

    def sub_style(self, font=None, size=None, color=None, back=None):
        if font:
            self.player["sub-font"] = font
        if size:
            self.player["sub-font-size"] = int(size)
        if color:
            self.player["sub-color"] = color
        if back is not None:
            self.player["sub-back-color"] = back or "#00000000"
            try:
                self.player["sub-border-style"] = "background-box" if back else "outline-and-shadow"
            except AttributeError:
                pass        # mpv before 0.38 (Ubuntu 24.04's, in the Linux builds): the back colour alone boxes it

    def chapter(self, d: int):
        try:
            self.player.command("add", "chapter", d)
        except Exception:
            pass

    def audio_devices(self) -> list:
        """[{name, description}] mpv can play to; 'auto' first."""
        return list(self.prop("audio-device-list") or [])

    @property
    def audio_device(self) -> str:
        return self.player["audio-device"] or "auto"

    @audio_device.setter
    def audio_device(self, name: str):
        self.player["audio-device"] = name or "auto"

    def has_audio_device(self, name: str) -> bool:
        """Whether mpv lists that output now (a saved one may be unplugged)."""
        return not name or name == "auto" or any(d.get("name") == name for d in self.audio_devices())

    def buffered_behind(self) -> float:
        """How far back REW can reach: seconds of past still in the buffer."""
        ranges = (self.prop("demuxer-cache-state") or {}).get("seekable-ranges") or []
        pos = self.prop("time-pos")
        if not ranges or pos is None:
            return 0.0
        return max(0.0, float(pos) - min(float(r["start"]) for r in ranges))

    def stats(self) -> dict:
        """What the diagnostics screen shows as a 'signal' readout."""
        return {k: self.prop(k) for k in ("video-bitrate", "audio-bitrate", "frame-drop-count",
                                    "decoder-frame-drop-count", "demuxer-cache-duration",
                                    "hwdec-current", "video-format", "width", "height",
                                    "container-fps", "cache-buffering-state")}

    def terminate(self):
        try:
            if self.ctx:
                self.ctx.free()
                self.ctx = None
            self.player.terminate()
        except Exception:
            pass
