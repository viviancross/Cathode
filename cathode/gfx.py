"""The window and the GPU compositor.

Each frame: mpv's video (full window or a box), an optional cover over it
(channel-change static or a black cut), the skin's UI canvas scaled into the
window, then the whole scene through the CRT shader. The UI canvas is drawn on
the CPU at the skin's fixed size and uploaded only when it changed.
"""

import ctypes
import ctypes.util
import glob
import os
import sys
from typing import Optional, Tuple

import pygame
import OpenGL
OpenGL.ERROR_CHECKING = False   # a glGetError after every call doubles the cost
from OpenGL import GL  # noqa: E402

Rect = Tuple[float, float, float, float]   # x0, y0, x1, y1


def _load_sdl():
    """The SDL library pygame already loaded, so SDL_GL_* calls reach the
    same copy (a second copy would know nothing about our window)."""
    base = os.path.dirname(pygame.__file__)
    for pat in (os.path.join(base, "SDL2.dll"),
                os.path.join(base, ".dylibs", "libSDL2*.dylib"),
                os.path.join(os.path.dirname(base), "pygame_ce.libs", "libSDL2*"),
                os.path.join(os.path.dirname(base), "pygame.libs", "libSDL2*")):
        for f in glob.glob(pat):
            return ctypes.CDLL(f)
    name = ctypes.util.find_library("SDL2")
    if not name:
        raise RuntimeError("could not find the SDL2 library pygame uses")
    return ctypes.CDLL(name)


_VERT = """#version 150
in vec2 uv;
out vec2 v;
uniform vec4 rect;   // x0 y0 x1 y1, clip space
uniform int flip;    // 1 = rows are top-down (pygame surfaces)
void main() {
    gl_Position = vec4(mix(rect.xy, rect.zw, uv), 0.0, 1.0);
    v = flip == 1 ? vec2(uv.x, 1.0 - uv.y) : uv;
}
"""

_PLAIN = """#version 150
in vec2 v;
out vec4 o;
uniform sampler2D tex;
void main() { o = texture(tex, v); }
"""

# Premultiplied output. kind 0 = black cut, 1 = tube static (coarse cells
# that change every frame, like snow on an untuned set).
_COVER = """#version 150
in vec2 v;
out vec4 o;
uniform float alpha;
uniform int kind;
uniform vec2 cells;
uniform float seed;
float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void main() {
    float g = kind == 1 ? hash(floor(v * cells) + seed) : 0.0;
    g = kind == 1 ? 0.15 + 0.85 * g * g : 0.0;
    o = vec4(vec3(g) * alpha, alpha);
}
"""

_CRT = """#version 150
in vec2 v;
out vec4 o;
uniform sampler2D tex;
uniform float lines;      // scanlines over the full height
uniform float strength;   // 0 = off
uniform float vignette;   // 0 = off
void main() {
    vec3 c = texture(tex, v).rgb;
    float s = 0.5 + 0.5 * cos(v.y * lines * 6.2831853);   // soft raised cosine
    c *= 1.0 - strength * (1.0 - s);
    float vig = smoothstep(0.85, 0.35, length(v - 0.5));   // middle untouched
    c *= mix(1.0, vig, 0.5 * vignette);
    o = vec4(c, 1.0);
}
"""


def _program(frag):
    def sh(kind, src):
        s = GL.glCreateShader(kind)
        GL.glShaderSource(s, src)
        GL.glCompileShader(s)
        if not GL.glGetShaderiv(s, GL.GL_COMPILE_STATUS):
            raise RuntimeError(GL.glGetShaderInfoLog(s).decode())
        return s
    p = GL.glCreateProgram()
    GL.glAttachShader(p, sh(GL.GL_VERTEX_SHADER, _VERT))
    GL.glAttachShader(p, sh(GL.GL_FRAGMENT_SHADER, frag))
    GL.glBindAttribLocation(p, 0, "uv")
    GL.glLinkProgram(p)
    if not GL.glGetProgramiv(p, GL.GL_LINK_STATUS):
        raise RuntimeError(GL.glGetProgramInfoLog(p).decode())
    locs = {}

    def loc(name):
        if name not in locs:
            locs[name] = GL.glGetUniformLocation(p, name)
        return locs[name]
    return p, loc


def _texture(w, h, nearest=False):
    t = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_2D, t)
    f = GL.GL_NEAREST if nearest else GL.GL_LINEAR
    for k, val in ((GL.GL_TEXTURE_MIN_FILTER, f), (GL.GL_TEXTURE_MAG_FILTER, f),
                   (GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE),
                   (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)):
        GL.glTexParameteri(GL.GL_TEXTURE_2D, k, val)
    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, w, h, 0,
                    GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
    return t


class _Target:
    """An FBO with a colour texture, sized to the drawable."""

    def __init__(self):
        self.fbo = GL.glGenFramebuffers(1)
        self.tex = None
        self.size = (0, 0)

    def resize(self, w, h) -> bool:
        if (w, h) == self.size:
            return False
        if self.tex:
            GL.glDeleteTextures([self.tex])
        self.tex = _texture(w, h)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbo)
        GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0,
                                  GL.GL_TEXTURE_2D, self.tex, 0)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
        self.size = (w, h)
        return True


def fit(canvas: Tuple[int, int], window: Tuple[int, int], stretch: bool = False) -> Tuple[int, int, int, int]:
    """Largest box of the canvas's shape centred in the window, in window
    pixels: (x, y, w, h). Pillarboxed on a wider window, letterboxed on a
    taller one; with `stretch`, the whole window whatever its shape."""
    cw, ch = canvas
    ww, wh = window
    if stretch or not (cw and ch and ww and wh):
        return 0, 0, max(ww, 0), max(wh, 0)
    scale = min(ww / cw, wh / ch)
    w, h = round(cw * scale), round(ch * scale)
    return (ww - w) // 2, (wh - h) // 2, w, h


class Gfx:
    def __init__(self, size=(1280, 720), fullscreen=False, display: int = 0,
                 title="Cathode"):
        pygame.display.init()
        for a, val in ((pygame.GL_CONTEXT_MAJOR_VERSION, 3),
                       (pygame.GL_CONTEXT_MINOR_VERSION, 2),
                       (pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)):
            pygame.display.gl_set_attribute(a, val)
        if sys.platform == "darwin":
            pygame.display.gl_set_attribute(pygame.GL_CONTEXT_FORWARD_COMPATIBLE_FLAG, 1)
        flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE
        if fullscreen:
            flags |= pygame.FULLSCREEN
            size = (0, 0)       # the display's own mode
        try:
            pygame.display.set_mode(size, flags, vsync=1, display=display)
        except pygame.error:
            # Software GL (VMs, CI, some drivers) has no vsync. Harmless: the
            # loop only presents when something changed, so it can't spin.
            pygame.display.set_mode(size, flags, display=display)
        pygame.display.set_caption(title)

        self._sdl = _load_sdl()
        self._sdl.SDL_GL_GetProcAddress.restype = ctypes.c_void_p
        self._sdl.SDL_GL_GetProcAddress.argtypes = [ctypes.c_char_p]
        self._sdl.SDL_GL_GetCurrentWindow.restype = ctypes.c_void_p
        self._sdl.SDL_GL_GetDrawableSize.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
        self._window = self._sdl.SDL_GL_GetCurrentWindow()
        if not self._window:
            raise RuntimeError("SDL_GL_GetCurrentWindow returned NULL")

        self.renderer = GL.glGetString(GL.GL_RENDERER).decode()
        self.version = GL.glGetString(GL.GL_VERSION).decode()

        self._vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self._vao)
        vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
        quad = (ctypes.c_float * 8)(0, 0, 1, 0, 0, 1, 1, 1)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, ctypes.sizeof(quad), quad, GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

        self._plain = _program(_PLAIN)
        self._cover = _program(_COVER)
        self._crt = _program(_CRT)
        self.video = _Target()
        self._scene = _Target()
        self._ui_tex = None
        self._ui_size = (0, 0)
        self._ui_nearest = False
        self.size = (0, 0)
        self.stretch = False        # the UI fills the window out of its shape (a 4:3 skin, stretched)

    # ── Window ────────────────────────────────────────────────────────────

    @staticmethod
    def displays() -> int:
        return pygame.display.get_num_displays()

    def move_to_display(self, index: int, fullscreen: bool):
        """Put the window on another monitor (leaving and re-entering full
        screen so it fills the new one)."""
        centred = 0x2FFF0000 | index        # SDL_WINDOWPOS_CENTERED_DISPLAY(index)
        self._sdl.SDL_SetWindowPosition.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        if fullscreen:
            pygame.display.toggle_fullscreen()
        self._sdl.SDL_SetWindowPosition(self._window, centred, centred)
        if fullscreen:
            pygame.display.toggle_fullscreen()

    def get_proc_address(self, name: bytes) -> int:
        return self._sdl.SDL_GL_GetProcAddress(name)

    def drawable(self) -> Tuple[int, int]:
        """Real pixels (Retina-aware), which is what GL draws in."""
        w, h = ctypes.c_int(), ctypes.c_int()
        self._sdl.SDL_GL_GetDrawableSize(self._window, ctypes.byref(w), ctypes.byref(h))
        return w.value, h.value

    def begin(self) -> bool:
        """Size the scene to the drawable. True when that changed."""
        self.size = self.drawable()
        return self._scene.resize(*self.size)

    def fit_video(self, canvas, video_box) -> bool:
        """Shape the video target like the picture it fills: the window, or
        a picture box in window pixels. mpv keeps the aspect within the
        target, so a window-shaped one squeezed into a box of another shape
        would distort. True when it changed (the frame must be redrawn)."""
        w, h = self.size
        if isinstance(video_box, tuple):
            _, _, w, h = self.canvas_px(canvas, video_box)
        return self.video.resize(max(1, round(w)), max(1, round(h)))

    def ui_box(self, canvas: Tuple[int, int]) -> Tuple[int, int, int, int]:
        return fit(canvas, self.size, self.stretch)

    def canvas_px(self, canvas, box):
        """A canvas-pixel (x, y, w, h) in window pixels."""
        ux, uy, uw, uh = self.ui_box(canvas)
        cw, ch = canvas
        bx, by, bw, bh = box
        return ux + bx * uw / cw, uy + by * uh / ch, bw * uw / cw, bh * uh / ch

    def to_canvas(self, canvas, wx, wy) -> Optional[Tuple[int, int]]:
        """Window pixel -> canvas pixel, or None outside the UI box. Pointer
        events arrive in window coordinates; screens think in canvas ones."""
        x, y, w, h = self.ui_box(canvas)
        ww, wh = pygame.display.get_window_size()
        dw, dh = self.size
        # Window coords can differ from drawable ones (Retina): scale first.
        wx, wy = wx * dw / max(ww, 1), wy * dh / max(wh, 1)
        if not (x <= wx < x + w and y <= wy < y + h):
            return None
        return int((wx - x) * canvas[0] / w), int((wy - y) * canvas[1] / h)

    # ── UI canvas ─────────────────────────────────────────────────────────

    def upload_ui(self, surface: pygame.Surface, nearest: bool = False):
        size = surface.get_size()
        if size != self._ui_size or nearest != self._ui_nearest or self._ui_tex is None:
            if self._ui_tex:
                GL.glDeleteTextures([self._ui_tex])
            GL.glActiveTexture(GL.GL_TEXTURE0)
            self._ui_tex = _texture(*size, nearest=nearest)
            self._ui_size, self._ui_nearest = size, nearest
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._ui_tex)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 4)
        GL.glPixelStorei(GL.GL_UNPACK_ROW_LENGTH, 0)
        GL.glBindBuffer(GL.GL_PIXEL_UNPACK_BUFFER, 0)
        GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, 0, 0, size[0], size[1], GL.GL_RGBA,
                           GL.GL_UNSIGNED_BYTE, pygame.image.tobytes(surface, "RGBA_PREMULT"))

    # ── Compose ───────────────────────────────────────────────────────────

    def _ndc(self, px_rect) -> Rect:
        """Window-pixel (x, y, w, h), y down -> clip space."""
        x, y, w, h = px_rect
        dw, dh = self.size
        return (2 * x / dw - 1, 1 - 2 * (y + h) / dh, 2 * (x + w) / dw - 1, 1 - 2 * y / dh)

    def _blit(self, prog, tex, rect: Rect, flip=0):
        p, loc = prog
        GL.glUseProgram(p)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        GL.glUniform1i(loc("tex"), 0)
        GL.glUniform4f(loc("rect"), *rect)
        GL.glUniform1i(loc("flip"), flip)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)

    def compose(self, canvas: Tuple[int, int], video_box=None, cover=None,
                crt: float = 0.0, vignette: bool = False, seed: float = 0.0):
        """Draw a frame to the window's back buffer.

        video_box: (x, y, w, h) in canvas pixels, "full" for the whole window,
        or "hidden".
        cover: (kind, alpha) over the video, kind "static" or "black".
        crt: scanline strength 0..1 (0 skips the CRT pass's darkening).
        """
        # mpv leaves GL state as it likes; restore what drawing here assumes.
        GL.glBindVertexArray(self._vao)
        GL.glDisable(GL.GL_SCISSOR_TEST)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glColorMask(True, True, True, True)

        w, h = self.size
        ux, uy, uw, uh = self.ui_box(canvas)
        boxed = isinstance(video_box, tuple)
        vrect = self._ndc(self.canvas_px(canvas, video_box)) if boxed else (-1, -1, 1, 1)

        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self._scene.fbo)
        GL.glViewport(0, 0, w, h)
        GL.glClearColor(0, 0, 0, 1)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glDisable(GL.GL_BLEND)
        if video_box != "hidden":
            self._blit(self._plain, self.video.tex, vrect)

        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)    # premultiplied
        if cover and cover[1] > 0 and video_box != "hidden":
            p, loc = self._cover
            GL.glUseProgram(p)
            GL.glUniform4f(loc("rect"), *vrect)
            GL.glUniform1i(loc("flip"), 0)
            GL.glUniform1f(loc("alpha"), min(1.0, cover[1]))
            GL.glUniform1i(loc("kind"), 1 if cover[0] == "static" else 0)
            # 144 rows of grain whatever the window: 5px cells at 720p.
            GL.glUniform2f(loc("cells"), 144.0 * w / max(h, 1), 144.0)
            GL.glUniform1f(loc("seed"), seed)
            GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
        if self._ui_tex:
            self._blit(self._plain, self._ui_tex, self._ndc((ux, uy, uw, uh)), flip=1)
        GL.glDisable(GL.GL_BLEND)

        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
        GL.glViewport(0, 0, w, h)
        p, loc = self._crt
        GL.glUseProgram(p)
        # A tube's line count is fixed; tie the pitch to the UI box, not the window.
        GL.glUniform1f(loc("lines"), 240.0 * h / max(uh, 1))
        GL.glUniform1f(loc("strength"), max(0.0, min(1.0, crt)))
        GL.glUniform1f(loc("vignette"), 1.0 if vignette else 0.0)
        self._blit(self._crt, self._scene.tex, (-1, -1, 1, 1))

    def read_pixels(self):
        """The composed back buffer as an RGB PIL image (for --shot)."""
        from PIL import Image
        w, h = self.size
        GL.glPixelStorei(GL.GL_PACK_ALIGNMENT, 1)
        px = GL.glReadPixels(0, 0, w, h, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
        return Image.frombytes("RGB", (w, h), px).transpose(Image.FLIP_TOP_BOTTOM)

    def flip(self):
        pygame.display.flip()
