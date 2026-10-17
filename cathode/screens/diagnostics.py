"""Diagnostics: the box's signal meter, made of what mpv knows about the
stream. Buffered seconds stand in for signal strength, dropped frames for
quality."""

from .. import remote as R
from ..app import Screen



# mpv's codec names, as a box's info page would put them.
CODECS = {"h264": "H.264", "hevc": "HEVC (H.265)", "mpeg2video": "MPEG-2", "mpeg4": "MPEG-4",
          "av1": "AV1", "vp9": "VP9", "vp8": "VP8", "vc1": "VC-1", "mpeg1video": "MPEG-1",
          "wrapped_avframe": "Test pattern", "rawvideo": "Uncompressed"}


def codec_name(fmt) -> str:
    return CODECS.get(fmt or "", (fmt or "-").upper())


class Diagnostics(Screen):
    name = "diagnostics"
    opaque = True

    def __init__(self, app):
        super().__init__(app)
        self.stats = {}
        self._timer = None
        self._tick()

    def video_box(self):
        return self.app.skin.page_video_box(self)

    def _tick(self):
        if self not in self.app.screens and self._timer:
            return                       # closed
        self.stats = self.app.video.stats() if self.app.video else {}
        self.app.invalidate()
        self._timer = self.app.after(1.0, self._tick)

    def signal(self) -> int:
        """0-100: how far ahead the stream is buffered. A live stream keeps a
        few seconds, so 3 s or more is full."""
        ahead = self.stats.get("demuxer-cache-duration") or 0
        return max(0, min(100, int(ahead * 100 / 3)))

    def quality(self) -> int:
        """0-100: falls as frames are dropped."""
        drops = (self.stats.get("frame-drop-count") or 0) + (self.stats.get("decoder-frame-drop-count") or 0)
        return max(0, 100 - drops)

    def rows(self):
        s = self.stats
        live = self.app.live
        ch = live.channel if live else None
        rate = s.get("video-bitrate")
        res = f"{s.get('width')}x{s.get('height')}" if s.get("width") else "-"
        fps = s.get("container-fps")
        return [
            ("Channel", f"{ch.number} {ch.name}" if ch else "-"),
            ("Stream", codec_name(s.get("video-format"))),
            ("Picture", res + (f" @ {fps:.0f} fps" if fps else "")),
            ("Bitrate", f"{rate / 1e6:.1f} Mbps" if rate else "-"),
            ("Buffered", f"{(s.get('demuxer-cache-duration') or 0):.1f} s"),
            ("Dropped frames", str((s.get("frame-drop-count") or 0) + (s.get("decoder-frame-drop-count") or 0))),
            ("Decoder", "Software" if s.get("hwdec-current") in (None, "", "no") else
             f"Hardware ({s['hwdec-current']})"),
        ]

    def handle(self, a: str) -> bool:
        if a in (R.BACK, R.EXIT, R.MENU, R.SELECT):
            self.app.cancel(self._timer)
            self.app.pop(self)
            return True
        return a not in (R.VOL_UP, R.VOL_DOWN, R.MUTE, R.FULLSCREEN, R.QUIT)
