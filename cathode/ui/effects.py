"""Retro visual effects: scanlines, static noise, CRT glow."""

import numpy as np
from PIL import Image, ImageFilter


# ── Scanline overlay ────────────────────────────────────────────────────────

def apply_scanlines(img: Image.Image, alpha: int = 40) -> Image.Image:
    """Overlay dark horizontal lines to simulate CRT scanlines."""
    if alpha <= 0:
        return img
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pixels = overlay.load()
    for y in range(0, h, 2):
        for x in range(w):
            pixels[x, y] = (0, 0, 0, alpha)
    return Image.alpha_composite(img, overlay)


def make_scanline_cache(width: int, height: int, alpha: int = 40) -> Image.Image:
    """Pre-render a hard 1px-on/1px-off scanline overlay.

    Kept for the static/tuning paths, where a coarse line pattern suits the
    noise. The screen tube itself uses make_crt_overlay, which is resolution
    aware and much kinder to small text.
    """
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[::2, :, 3] = alpha  # every other row, alpha only
    return Image.fromarray(arr, "RGBA")


# Scanlines drawn across the picture. The count belongs to the *tube*, not to
# the window: at a fixed 1px-on/1px-off the pitch silently changed with
# resolution, so the same app was coarse-striped at 480p and had invisible,
# moire-prone hairlines at 4K.
#
# 240, not the 480 of an NTSC field, and that is deliberate. A soft line needs
# at least three device pixels to fall off across; at 480 lines on an 800px
# panel the pitch clamps to two and the profile collapses back into the hard
# on/off row this replaced. 240 is also the structure people actually read as
# "CRT" — 480i on a small panel just averages into a grey wash.
TUBE_LINES = 240.0


def scanline_pitch(height: int, lines: float = TUBE_LINES) -> float:
    """Device pixels per scanline pair for a screen `height` tall."""
    return max(2.0, height / max(1.0, lines))


def make_crt_overlay(width: int, height: int, alpha: int = 40,
                     mask_amp: float = 0.35,
                     lines: float = TUBE_LINES) -> Image.Image:
    """A black overlay whose alpha carries the structure of a CRT face:
    soft horizontal scanlines crossed with a faint vertical slot mask.

    Two things make this read as a tube rather than as stripes drawn on a
    screen. The scanline profile is a raised cosine, not a hard on/off row —
    real phosphor lines fall off gradually, and a soft profile also stops the
    1px pattern from aliasing into moire when the overlay is scaled or the
    panel is not 1:1. The slot mask is the RGB triad structure of the shadow
    mask; it is what the eye actually reads as "CRT" up close, and at this
    amplitude it is invisible as individual stripes from the couch.

    Cost is unchanged from a plain scanline cache: built once, composited once.
    """
    if alpha <= 0:
        return Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pitch = scanline_pitch(height, lines)
    y = np.arange(height, dtype=np.float32)
    # Raised cosine, 0 at the line centre and 1 in the gap between lines.
    scan = 0.5 - 0.5 * np.cos(2.0 * np.pi * y / pitch)
    # Slightly sharpen the trough so lines stay legible without raising alpha,
    # which is what used to eat the smallest metadata text.
    scan = scan ** 1.4

    x = np.arange(width, dtype=np.float32)
    # One period per RGB triad. Kept at 3px regardless of resolution: it is a
    # property of the mask, and stretching it turns stripes into visible bands.
    slot = 0.5 - 0.5 * np.cos(2.0 * np.pi * x / 3.0)

    a = alpha * scan[:, None] + (alpha * mask_amp) * slot[None, :]
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[:, :, 3] = np.clip(a, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def combine_dark_overlays(*layers) -> Image.Image:
    """Flatten black-with-alpha overlays into one, so the frame pays for a
    single composite instead of one per effect.

    Alpha composites in sequence, which for same-colour layers is exactly
    1 - (1-a1)(1-a2)... — so the merged layer is indistinguishable from
    stacking them, at a fraction of the per-frame cost.
    """
    layers = [l for l in layers if l is not None]
    if not layers:
        return None
    if len(layers) == 1:
        return layers[0]
    keep = np.ones(layers[0].size[::-1], dtype=np.float32)
    for l in layers:
        keep *= 1.0 - (np.asarray(l, dtype=np.float32)[:, :, 3] / 255.0)
    arr = np.zeros((layers[0].size[1], layers[0].size[0], 4), dtype=np.uint8)
    arr[:, :, 3] = np.clip((1.0 - keep) * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


# ── Static / noise ──────────────────────────────────────────────────────────

def block_noise_gray(width: int, height: int, block: int = 1) -> np.ndarray:
    """Grayscale TV-static noise where each 'particle' is a block×block square.

    Larger blocks look like a coarser, older tube TV.  Generating noise at the
    reduced (height/block, width/block) resolution and upscaling is also much
    cheaper than per-pixel noise.
    """
    if block <= 1:
        return np.random.randint(30, 240, size=(height, width), dtype=np.uint8)
    bh = (height + block - 1) // block
    bw = (width + block - 1) // block
    small = np.random.randint(30, 240, size=(bh, bw), dtype=np.uint8)
    return np.repeat(np.repeat(small, block, axis=0), block, axis=1)[:height, :width]


def make_static_frame(
    width: int,
    height: int,
    intensity: float = 1.0,
    max_alpha: int = 255,
    blur: bool = True,
    block: int = 1,
) -> Image.Image:
    """Generate a single frame of TV static noise.

    intensity 1.0 + max_alpha 255 => fully opaque (covers the video beneath),
    which is what the channel-change "buffering" cover needs.  Lower intensity
    lets the video bleed through (used while fading out on reveal).  `block`
    sets the particle size (see block_noise_gray).
    """
    gray = block_noise_gray(width, height, block)
    rgb = np.stack([gray, gray, gray], axis=-1)

    alpha_val = int(min(255, max_alpha) * max(0.0, min(1.0, intensity)))
    alpha = np.full((height, width, 1), alpha_val, dtype=np.uint8)
    rgba = np.concatenate([rgb, alpha], axis=-1)

    img = Image.fromarray(rgba, "RGBA")

    # Apply slight blur for more organic look (skipped on the fast 60fps path)
    if blur and intensity > 0.5:
        img = img.filter(ImageFilter.GaussianBlur(radius=0.5))

    return img


def make_static_sequence(
    width: int,
    height: int,
    frames: int = 6,
) -> list:
    """Pre-generate several static frames for cycling."""
    return [make_static_frame(width, height) for _ in range(frames)]


# ── SMPTE color bars ─────────────────────────────────────────────────────────

# Classic 75% test-bar colors, left to right.
SMPTE_BARS = [(192, 192, 192), (192, 192, 0), (0, 192, 192), (0, 192, 0),
              (192, 0, 192), (192, 0, 0), (0, 0, 192)]


def draw_smpte_bars(draw, x0: int, y0: int, x1: int, y1: int):
    """Draw the 7-bar SMPTE test pattern into [x0,y0,x1,y1]. Used by the
    PLEASE STAND BY card and as the 'off air' motif on empty states."""
    n = len(SMPTE_BARS)
    w = (x1 - x0) / n
    for i, c in enumerate(SMPTE_BARS):
        draw.rectangle([int(x0 + i * w), y0,
                        int(x0 + (i + 1) * w) - 1, y1], fill=(*c, 255))


# ── Glow / bloom effect ─────────────────────────────────────────────────────

def apply_glow(
    img: Image.Image,
    radius: int = 3,
    strength: float = 0.6,
) -> Image.Image:
    """Apply a phosphor-glow bloom to bright areas."""
    blurred = img.filter(ImageFilter.GaussianBlur(radius=radius))
    # Blend original with blurred
    r, g, b, a = img.split()
    br, bg, bb, ba = blurred.split()

    def blend_channel(orig, glow):
        arr_o = np.array(orig, dtype=np.float32)
        arr_g = np.array(glow, dtype=np.float32)
        result = np.clip(arr_o + arr_g * strength, 0, 255).astype(np.uint8)
        return Image.fromarray(result)

    return Image.merge("RGBA", (
        blend_channel(r, br),
        blend_channel(g, bg),
        blend_channel(b, bb),
        a,
    ))


# ── CRT vignette ────────────────────────────────────────────────────────────

def make_vignette(width: int, height: int, strength: float = 0.4,
                  max_alpha: int = 150) -> Image.Image:
    """Dark corners to simulate the curve and edge falloff of a tube face.

    The falloff is a power curve on normalised corner distance rather than a
    linear ramp: a linear one starts darkening immediately away from centre,
    which reads as a grey wash over the middle of the picture instead of as
    edges rolling off. This keeps the centre clean and puts the darkening where
    a real tube has it — the last third out to the corners.
    """
    ys = np.linspace(-1.0, 1.0, height, dtype=np.float32)
    xs = np.linspace(-1.0, 1.0, width, dtype=np.float32)
    xx, yy = np.meshgrid(xs, ys)
    # Normalised so the corners sit at 1.0 whatever the aspect ratio.
    dist = np.sqrt(xx ** 2 + yy ** 2) / np.sqrt(2.0)
    falloff = np.clip(dist, 0.0, 1.0) ** 2.4
    alpha = falloff * (max_alpha * np.clip(strength / 0.4, 0.0, 2.0))
    result = np.zeros((height, width, 4), dtype=np.uint8)
    result[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    return Image.fromarray(result, "RGBA")


# ── Chromatic aberration (VHS color fringing) ────────────────────────────────

def apply_chroma_shift(img: Image.Image, shift: int = 2) -> Image.Image:
    """Shift red channel slightly right for VHS color bleeding effect."""
    if shift <= 0:
        return img
    r, g, b, a = img.split()
    # Shift red channel right
    r_arr = np.array(r)
    r_shifted = np.roll(r_arr, shift, axis=1)
    r_shifted[:, :shift] = 0
    return Image.merge("RGBA", (Image.fromarray(r_shifted), g, b, a))


# ── Channel flip transition ──────────────────────────────────────────────────

def make_channel_flip_frame(
    width: int,
    height: int,
    progress: float,  # 0.0 = full static, 1.0 = clear
) -> Image.Image:
    """Transition frame: static fading out as new channel locks in."""
    intensity = max(0.0, 1.0 - progress)

    # White flash at t=0
    if progress < 0.1:
        flash_alpha = int(255 * (1.0 - progress / 0.1) * 0.8)
        frame = Image.new("RGBA", (width, height), (255, 255, 255, flash_alpha))
        return frame

    return make_static_frame(width, height, intensity=intensity * 0.9)
