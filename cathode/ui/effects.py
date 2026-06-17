"""Retro visual effects: scanlines, static noise, CRT glow."""

import numpy as np
from PIL import Image, ImageFilter, ImageDraw
import random
from typing import Tuple


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
    """Pre-render a scanline overlay (reuse every frame)."""
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[::2, :, 3] = alpha  # every other row, alpha only
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

def make_vignette(width: int, height: int, strength: float = 0.4) -> Image.Image:
    """Dark corners vignette to simulate CRT tube curvature."""
    ys = np.linspace(-1, 1, height)
    xs = np.linspace(-1, 1, width)
    xx, yy = np.meshgrid(xs, ys)
    dist = np.sqrt(xx**2 + yy**2)
    vignette = np.clip(1.0 - dist * strength, 0.0, 1.0)
    alpha = ((1.0 - vignette) * 162).astype(np.uint8)   # ~10% lighter than before
    result = np.zeros((height, width, 4), dtype=np.uint8)
    result[:, :, 3] = alpha  # black with varying alpha
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
