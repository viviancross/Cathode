"""Cathode 4 stack spike: own window (pygame-ce/SDL2) + libmpv render API.

Proves, on each desktop OS, the four things the rebuild depends on:
  1. libmpv draws video into our own OpenGL context (no mpv window, no IPC).
  2. A fixed-size UI canvas (720x480, like an SD box) is composited over the
     video and scaled to any window size by the GPU.
  3. A CRT post-process shader runs over video + UI together.
  4. Video can be placed anywhere (guide picture-in-picture), and SDL sees
     game controllers.

Keys: C = CRT on/off, P = picture-in-picture, F = fullscreen, Esc = quit.

    python spike/spike.py [--source URL] [--seconds N] [--shot out.png]
"""

import argparse
import ctypes
import ctypes.util
import glob
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# Windows: libmpv-2.dll lives in _libmpv/ (see spike/README.md).
os.environ["PATH"] = os.path.join(ROOT, "_libmpv") + os.pathsep + os.environ["PATH"]

import pygame  # noqa: E402
import mpv  # noqa: E402
import OpenGL  # noqa: E402
OpenGL.ERROR_CHECKING = False   # a glGetError after every call doubles the cost
from OpenGL import GL  # noqa: E402

CANVAS = (720, 480)  # the UI is drawn at this size, whatever the window is


def load_sdl():
    """The SDL library pygame already loaded, so SDL_GL_* calls hit the same
    copy (a second copy would know nothing about our window)."""
    base = os.path.dirname(pygame.__file__)
    pats = [os.path.join(base, "SDL2.dll"),
            os.path.join(base, ".dylibs", "libSDL2*.dylib"),
            os.path.join(os.path.dirname(base), "pygame_ce.libs", "libSDL2*"),
            os.path.join(os.path.dirname(base), "pygame.libs", "libSDL2*")]
    for p in pats:
        for f in glob.glob(p):
            return ctypes.CDLL(f)
    name = ctypes.util.find_library("SDL2")
    if not name:
        sys.exit("could not find the SDL2 library pygame uses")
    return ctypes.CDLL(name)


VERT = """#version 150
in vec2 uv;
out vec2 v;
uniform vec4 rect;   // x0 y0 x1 y1 in clip space
uniform int flip;    // 1 = texture rows are top-down (pygame surfaces)
void main() {
    gl_Position = vec4(mix(rect.xy, rect.zw, uv), 0.0, 1.0);
    v = flip == 1 ? vec2(uv.x, 1.0 - uv.y) : uv;
}
"""

FRAG_PLAIN = """#version 150
in vec2 v;
out vec4 o;
uniform sampler2D tex;
void main() { o = texture(tex, v); }
"""

FRAG_CRT = """#version 150
in vec2 v;
out vec4 o;
uniform sampler2D tex;
uniform float lines;     // scanline count, independent of window size
uniform float strength;  // 0 = off
void main() {
    vec3 c = texture(tex, v).rgb;
    float s = 0.5 + 0.5 * cos(v.y * lines * 6.2831853);   // soft raised cosine
    c *= 1.0 - strength * (1.0 - s);
    float vig = smoothstep(0.85, 0.35, length(v - 0.5));   // middle untouched
    c *= mix(1.0, vig, 0.5 * strength / 0.35);
    o = vec4(c, 1.0);
}
"""


def program(frag):
    def sh(kind, src):
        s = GL.glCreateShader(kind)
        GL.glShaderSource(s, src)
        GL.glCompileShader(s)
        if not GL.glGetShaderiv(s, GL.GL_COMPILE_STATUS):
            sys.exit(GL.glGetShaderInfoLog(s).decode())
        return s
    p = GL.glCreateProgram()
    GL.glAttachShader(p, sh(GL.GL_VERTEX_SHADER, VERT))
    GL.glAttachShader(p, sh(GL.GL_FRAGMENT_SHADER, frag))
    GL.glBindAttribLocation(p, 0, "uv")
    GL.glLinkProgram(p)
    if not GL.glGetProgramiv(p, GL.GL_LINK_STATUS):
        sys.exit(GL.glGetProgramInfoLog(p).decode())
    return p


def texture(w, h, data=None, nearest=False):
    t = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_2D, t)
    f = GL.GL_NEAREST if nearest else GL.GL_LINEAR
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, f)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, f)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
    GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, w, h, 0,
                    GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, data)
    return t


class Target:
    """An FBO with a colour texture, sized to the drawable."""

    def __init__(self):
        self.fbo = GL.glGenFramebuffers(1)
        self.tex = None
        self.size = (0, 0)

    def resize(self, w, h):
        if (w, h) == self.size:
            return
        if self.tex:
            GL.glDeleteTextures([self.tex])
        self.tex = texture(w, h)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbo)
        GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0,
                                  GL.GL_TEXTURE_2D, self.tex, 0)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
        self.size = (w, h)


def draw_ui(surf, font, small, fps, frame_ms, crt, pip, pads):
    """The stand-in for a skin: an SD-box channel banner at 720x480."""
    surf.fill((0, 0, 0, 0))
    w, h = surf.get_size()
    band = pygame.Rect(24, h - 130, w - 48, 100)
    pygame.draw.rect(surf, (10, 30, 90, 225), band, border_radius=6)
    pygame.draw.rect(surf, (120, 170, 255, 255), band, 2, border_radius=6)
    surf.blit(font.render("205", True, (40, 255, 90)), (band.x + 16, band.y + 12))
    surf.blit(font.render("SPIKE NEWS", True, (255, 255, 255)), (band.x + 110, band.y + 12))
    clock = font.render(time.strftime("%H:%M:%S"), True, (255, 220, 80))
    surf.blit(clock, (band.right - 16 - clock.get_width(), band.y + 12))
    info = (f"{fps:5.1f} fps  {frame_ms:4.1f} ms cpu/frame  "
            f"CRT {'on' if crt else 'off'}  PiP {'on' if pip else 'off'}  pads {pads}")
    surf.blit(small.render(info, True, (200, 210, 230)), (band.x + 16, band.y + 62))


def check(shot, pip):
    """Sample the composed frame where each layer must be. Catches a missing
    video, a missing UI, or a video drawn in the wrong place, without anyone
    having to look at the PNG."""
    w, h = shot.size

    def mean(x0, y0, x1, y1):
        """Average colour over a 7x7 grid inside a box given as fractions, so
        one dark detail in the video can't decide the result."""
        pts = [shot.getpixel((int((x0 + (x1 - x0) * i / 6) * w), int((y0 + (y1 - y0) * j / 6) * h)))
               for i in range(7) for j in range(7)]
        return tuple(sum(p[k] for p in pts) // len(pts) for k in range(3))

    def lit(c):
        return sum(c) > 60

    banner = mean(0.04, 0.82, 0.05, 0.90)   # left margin of the banner, no text
    results = {"ui banner is blue": (banner, banner[2] > banner[0] and banner[2] > banner[1])}
    if pip:
        inside, outside = mean(0.06, 0.08, 0.39, 0.40), mean(0.55, 0.08, 0.95, 0.60)
        results["video inside PiP box"] = (inside, lit(inside))
        results["black outside PiP box"] = (outside, not lit(outside))
    else:
        mid = mean(0.1, 0.1, 0.9, 0.6)
        results["video fills window"] = (mid, lit(mid))
    for name, (rgb, ok) in results.items():
        print(f"check: {'PASS' if ok else 'FAIL'}  {name}  rgb={rgb}")
    return all(ok for _, ok in results.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="av://lavfi:testsrc2=size=1280x720:rate=30")
    ap.add_argument("--seconds", type=float, default=0, help="quit after N seconds")
    ap.add_argument("--shot", help="save the final composed frame to this PNG")
    ap.add_argument("--crt", action="store_true")
    ap.add_argument("--pip", action="store_true")
    ap.add_argument("--paused", action="store_true", help="measure idle cost")
    ap.add_argument("--check", action="store_true",
                    help="with --shot: verify the composed frame, exit 1 if wrong")
    args = ap.parse_args()

    pygame.init()
    for a, v in ((pygame.GL_CONTEXT_MAJOR_VERSION, 3), (pygame.GL_CONTEXT_MINOR_VERSION, 2),
                 (pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)):
        pygame.display.gl_set_attribute(a, v)
    if sys.platform == "darwin":
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_FORWARD_COMPATIBLE_FLAG, 1)
    flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE
    try:
        pygame.display.set_mode((1280, 720), flags, vsync=1)
    except pygame.error:
        # Software GL (VMs, CI, some drivers) has no vsync. Harmless here: the
        # loop only presents when a frame or the UI changes, so it can't spin.
        pygame.display.set_mode((1280, 720), flags)
    pygame.display.set_caption("Cathode 4 spike")
    pygame.display.set_allow_screensaver(False)   # "keep screen awake" is one line

    sdl = load_sdl()
    sdl.SDL_GL_GetProcAddress.restype = ctypes.c_void_p
    sdl.SDL_GL_GetProcAddress.argtypes = [ctypes.c_char_p]
    sdl.SDL_GL_GetCurrentWindow.restype = ctypes.c_void_p
    sdl.SDL_GL_GetDrawableSize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
                                           ctypes.POINTER(ctypes.c_int)]
    window = sdl.SDL_GL_GetCurrentWindow()
    if not window:
        sys.exit("SDL_GL_GetCurrentWindow returned NULL: loaded a second SDL copy")

    def drawable():
        w, h = ctypes.c_int(), ctypes.c_int()
        sdl.SDL_GL_GetDrawableSize(window, ctypes.byref(w), ctypes.byref(h))
        return w.value, h.value   # real pixels, so Retina is handled

    print("GL:", GL.glGetString(GL.GL_VERSION).decode(), "|",
          GL.glGetString(GL.GL_RENDERER).decode())

    player = mpv.MPV(vo="libmpv", hwdec="auto-safe", keep_open="yes", idle="yes",
                     input_default_bindings=False, input_vo_keyboard=False,
                     log_handler=lambda lvl, comp, msg: print(f"[mpv/{comp}] {msg.strip()}")
                     if lvl in ("error", "fatal") else None)
    gpa = mpv.MpvGlGetProcAddressFn(lambda _, name: sdl.SDL_GL_GetProcAddress(name))
    ctx = mpv.MpvRenderContext(player, "opengl", opengl_init_params={"get_proc_address": gpa})
    # mpv calls this from its own thread when it has a frame; posting an SDL
    # event wakes the UI thread, which otherwise sleeps in event.wait().
    mpv_frame = pygame.event.custom_type()
    ctx.update_cb = lambda: pygame.event.post(pygame.event.Event(mpv_frame))
    player.play(args.source)
    if args.paused:
        player.pause = True

    vao = GL.glGenVertexArrays(1)
    GL.glBindVertexArray(vao)
    vbo = GL.glGenBuffers(1)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
    quad = (ctypes.c_float * 8)(0, 0, 1, 0, 0, 1, 1, 1)
    GL.glBufferData(GL.GL_ARRAY_BUFFER, ctypes.sizeof(quad), quad, GL.GL_STATIC_DRAW)
    GL.glEnableVertexAttribArray(0)
    GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

    plain, crt_prog = program(FRAG_PLAIN), program(FRAG_CRT)
    video, scene = Target(), Target()

    font_path = os.path.join(ROOT, "assets", "fonts", "VCR_OSD_MONO.ttf")
    font = pygame.font.Font(font_path if os.path.exists(font_path) else None, 40)
    small = pygame.font.Font(font_path if os.path.exists(font_path) else None, 18)
    ui = pygame.Surface(CANVAS, pygame.SRCALPHA)
    ui_tex = texture(*CANVAS)

    def blit(prog, tex, rect, flip=0):
        GL.glUseProgram(prog)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        GL.glUniform1i(GL.glGetUniformLocation(prog, "tex"), 0)
        GL.glUniform4f(GL.glGetUniformLocation(prog, "rect"), *rect)
        GL.glUniform1i(GL.glGetUniformLocation(prog, "flip"), flip)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)

    crt, pip = args.crt, args.pip
    pads = {}
    t_start = time.monotonic()
    cpu_start = time.process_time()
    failed = False
    frames, cpu_ms, ui_uploads, last_sec = 0, 0.0, 0, -1
    video_frames, rendered_size = 0, (0, 0)
    fps, frame_ms = 0.0, 0.0
    fps_t, fps_n = time.monotonic(), 0
    running = True
    while running:
        # Sleep until something happens: a video frame, input, or the next
        # clock second. Nothing changed = nothing drawn = no CPU.
        until_sec = int((1.0 - time.time() % 1.0) * 1000) + 1
        if args.seconds:
            until_sec = min(until_sec, 100)
        events = [pygame.event.wait(until_sec)] + pygame.event.get()
        t0 = time.perf_counter()
        dirty = False
        for e in events:
            if e.type == mpv_frame:
                dirty = True
            elif e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_c:
                    crt = not crt
                elif e.key == pygame.K_p:
                    pip = not pip
                elif e.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()
                last_sec = -1   # force a UI redraw
            elif e.type == pygame.CONTROLLERDEVICEADDED:
                c = pygame._sdl2.controller.Controller(e.device_index)
                pads[c.id] = c
                print("controller connected:", c.name)
                last_sec = -1
            elif e.type == pygame.CONTROLLERDEVICEREMOVED:
                pads.pop(e.instance_id, None)
                last_sec = -1
            elif e.type == pygame.CONTROLLERBUTTONDOWN:
                print("controller button", e.button)

        w, h = drawable()
        video.resize(w, h)
        scene.resize(w, h)

        # UI: redraw + upload only when something on it changed (here: the clock).
        sec = int(time.time())
        ending = args.seconds and time.monotonic() - t_start >= args.seconds
        if sec == last_sec and not dirty and (w, h) == rendered_size and not ending:
            continue

        # 1. mpv draws a video frame into its own FBO, only when it has a new
        #    one (or the size changed); otherwise the last frame is reused.
        if ctx.update() or (w, h) != rendered_size:
            ctx.render(flip_y=True, block_for_target_time=False,
                       opengl_fbo={"w": w, "h": h, "fbo": video.fbo,
                                   "internal_format": GL.GL_RGBA8})
            rendered_size = (w, h)
            video_frames += 1
        # mpv leaves GL state as it likes; put back everything drawn below relies on.
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glDisable(GL.GL_SCISSOR_TEST)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glColorMask(True, True, True, True)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 4)
        GL.glPixelStorei(GL.GL_UNPACK_ROW_LENGTH, 0)
        GL.glBindBuffer(GL.GL_PIXEL_UNPACK_BUFFER, 0)

        # UI: redraw + upload only when something on it changed (here: the clock).
        if sec != last_sec:
            last_sec = sec
            draw_ui(ui, font, small, fps, frame_ms, crt, pip, len(pads))
            GL.glBindTexture(GL.GL_TEXTURE_2D, ui_tex)
            GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, 0, 0, *CANVAS, GL.GL_RGBA,
                               GL.GL_UNSIGNED_BYTE, pygame.image.tobytes(ui, "RGBA_PREMULT"))
            ui_uploads += 1

        # 2. Compose video (full or PiP) + UI canvas into the scene FBO.
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, scene.fbo)
        GL.glViewport(0, 0, w, h)
        GL.glClearColor(0, 0, 0, 1)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        GL.glBindVertexArray(vao)
        GL.glDisable(GL.GL_BLEND)
        vrect = (-0.95, 0.15, -0.15, 0.9) if pip else (-1, -1, 1, 1)
        blit(plain, video.tex, vrect)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)   # premultiplied
        blit(plain, ui_tex, (-1, -1, 1, 1), flip=1)
        GL.glDisable(GL.GL_BLEND)

        # 3. Scene to the window, through the CRT shader or straight.
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
        GL.glViewport(0, 0, w, h)
        if crt:
            GL.glUseProgram(crt_prog)
            GL.glUniform1f(GL.glGetUniformLocation(crt_prog, "lines"), 240.0)
            GL.glUniform1f(GL.glGetUniformLocation(crt_prog, "strength"), 0.35)
        blit(crt_prog if crt else plain, scene.tex, (-1, -1, 1, 1))

        cpu_ms += (time.perf_counter() - t0) * 1000
        frames += 1
        fps_n += 1
        now = time.monotonic()
        if now - fps_t >= 1.0:
            fps, frame_ms = fps_n / (now - fps_t), cpu_ms / max(frames, 1)
            fps_t, fps_n = now, 0

        if args.seconds and now - t_start >= args.seconds:
            if args.shot:
                GL.glPixelStorei(GL.GL_PACK_ALIGNMENT, 1)
                px = GL.glReadPixels(0, 0, w, h, GL.GL_RGB, GL.GL_UNSIGNED_BYTE)
                from PIL import Image
                shot = Image.frombytes("RGB", (w, h), px).transpose(Image.FLIP_TOP_BOTTOM)
                shot.save(args.shot)
                print("saved", args.shot)
                if args.check and not check(shot, pip):
                    failed = True
            running = False

        pygame.display.flip()
        ctx.report_swap()

    wall = time.monotonic() - t_start
    print(f"{player.mpv_version} | hwdec {player.hwdec_current or 'no'} | video {player.width}x{player.height}"
          f" @ {player.container_fps} fps")
    print(f"frames {frames} in {wall:.1f}s = {frames / wall:.1f} fps | "
          f"main-loop cpu {cpu_ms / max(frames, 1):.2f} ms/frame | "
          f"video frames {video_frames} | ui uploads {ui_uploads} | process cpu {100 * (time.process_time() - cpu_start) / wall:.0f}%")
    ctx.free()
    player.terminate()
    pygame.quit()
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
