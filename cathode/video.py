"""Video: libmpv in-process, drawing into Cathode's own OpenGL context.

mpv runs on its own threads; nothing here touches app state from them. Every
mpv event is forwarded through `post`, which queues it for the UI thread.
"""

import os
from typing import Callable, Optional

from . import paths

# Windows looks for libmpv-2.dll on PATH: next to the frozen exe, or _libmpv/
# in a source checkout. Must happen before `import mpv`.
if os.name == "nt":
    os.environ["PATH"] = os.pathsep.join([paths.libmpv_dir(), os.environ.get("PATH", "")])

import mpv  # noqa: E402

# GL_RENDERER substrings that mean "no GPU". Software GL hands out
# uninitialised texture memory, mpv's float intermediates pick up garbage, and
# about half of all runs show black or dimmed video while mpv logs a normal
# render (found in the 4.0 spike). Dumb mode skips the intermediates and is
# the faster choice on a CPU anyway.
_SOFTWARE_GL = ("llvmpipe", "softpipe", "software")


class Video:
    """One mpv instance. `post(kind, **data)` must be safe to call from any
    thread; it is how mpv's events reach the UI thread."""

    def __init__(self, post: Callable, renderer: str, user_agent: str = "",
                 volume: int = 80, extra: Optional[dict] = None, log_path: str = ""):
        self._post = post
        opts = dict(
            vo="libmpv", hwdec="auto-safe", keep_open="yes", idle="yes",
            input_default_bindings=False, input_vo_keyboard=False,
            osc=False, cache="yes", demuxer_max_bytes="64MiB",
            # Pause-live: keep the recent past so REW can reach back into it.
            demuxer_max_back_bytes="128MiB",
            vf="bwdif=deint=1", volume=str(volume))
        if user_agent:
            opts["user_agent"] = user_agent
        if any(s in renderer.lower() for s in _SOFTWARE_GL):
            opts["gpu-dumb-mode"] = "yes"
        if log_path:
            opts["log_file"] = log_path
        opts.update(extra or {})
        self.player = mpv.MPV(**opts)
        self.ctx = None
        self._want = None        # playlist entry id of the file we asked for
        self._current = None     # entry id of the file mpv says it started
        self.player.register_event_callback(self._on_event)

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

    def play(self, url: str, headers: Optional[dict] = None, start: float = 0):
        """Load `url`, replacing whatever plays. Events about any earlier file
        are ignored from here on: only this load's start can reveal it."""
        # Always set (empty clears), so a Plex token can't ride along onto the
        # next live stream. Headers go out before the load they belong to.
        self.player["http-header-fields"] = (
            [f"{k}: {v}" for k, v in headers.items()] if headers else [])
        self.player["start"] = str(start) if start > 0 else "none"
        self.player.pause = False
        rv = self.player.command("loadfile", url, "replace")
        self._want = rv.get("playlist_entry_id") if isinstance(rv, dict) else None
        self._current = None

    def stop(self):
        self._want = self._current = None
        self.player.command("stop")

    def _on_event(self, event):
        """mpv's event thread. Translate, filter to the file we asked for,
        and post; never touch app state here."""
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

    def seek(self, seconds: float, mode: str = "relative"):
        try:
            self.player.command("seek", seconds, mode)
        except Exception:
            pass        # nothing loaded, or not seekable

    def stats(self) -> dict:
        """What the diagnostics screen shows as a 'signal' readout."""
        p = self.player

        def get(name):
            try:
                return p[name]
            except Exception:
                return None
        return {k: get(k) for k in ("video-bitrate", "audio-bitrate", "frame-drop-count",
                                    "decoder-frame-drop-count", "demuxer-cache-duration",
                                    "hwdec-current", "video-codec", "width", "height",
                                    "container-fps", "cache-buffering-state")}

    def terminate(self):
        try:
            if self.ctx:
                self.ctx.free()
                self.ctx = None
            self.player.terminate()
        except Exception:
            pass
