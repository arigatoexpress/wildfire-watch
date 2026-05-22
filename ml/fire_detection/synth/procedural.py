"""Procedural fire / smoke / thermal-anomaly synthesizers.

Lazy-imports PIL + numpy. Pure-stdlib seeded RNG so tests can verify
determinism without re-rolling the heavy wheels. Each synthesizer returns a
PIL.Image that is intended to be alpha-composited onto a backdrop by the
caller (see ``generator.py``).

Design notes
------------
The synthesisers are *procedural*, not generative-model-based. The goal is a
defensible ``we trained on labelled data`` claim that a downstream YOLO can
learn from the bounding-box statistics of (smoke is tall, fire is bright,
thermal anomalies are radial). The pixel statistics are intentionally crude —
no atmospheric scattering, no flame fluid dynamics, no IR Black-body curve.
Models trained only on this data WILL overfit to Perlin-noise statistics.
This package's job is to provide the schema-correct training set that proves
the pipeline runs end-to-end; the real data work is in DATASETS.md.
"""

from __future__ import annotations

import math
import random
from typing import Any

# Public API.
__all__ = [
    "synthesize_smoke_plume",
    "synthesize_fire_glow",
    "synthesize_thermal_anomaly",
    "value_noise_2d",
    "perlin_like_2d",
]


# ---------------------------------------------------------------------------
# Lazy-import helpers.
# ---------------------------------------------------------------------------


def _import_pil() -> Any:
    """Lazy-import PIL.Image. Raises ImportError with an actionable message."""
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - exercised only without PIL
        raise ImportError(
            "ml.fire_detection.synth.procedural requires Pillow. "
            "Install with: /usr/local/bin/python3 -m pip install Pillow"
        ) from e
    return Image


def _import_numpy() -> Any:
    """Lazy-import numpy. Raises ImportError with an actionable message."""
    try:
        import numpy as np  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - exercised only without numpy
        raise ImportError(
            "ml.fire_detection.synth.procedural requires numpy. "
            "Install with: /usr/local/bin/python3 -m pip install numpy"
        ) from e
    return np


# ---------------------------------------------------------------------------
# Stdlib value-noise (Perlin-shaped) primitive.
# ---------------------------------------------------------------------------


def value_noise_2d(W: int, H: int, *, seed: int, scale: float = 8.0) -> list[list[float]]:
    """Pure-stdlib 2D value-noise grid in [0, 1].

    This is the cheap stand-in for proper Perlin noise. We sample a coarse
    random lattice at ``scale``-pixel spacing and bilinearly interpolate. It
    looks blob-shaped which is good enough for procedural smoke / glow.

    Implemented in stdlib so test_procedural can verify the grid is bit-for-bit
    deterministic without numpy.
    """
    rng = random.Random(seed)
    cells_x = max(2, int(math.ceil(W / scale)) + 1)
    cells_y = max(2, int(math.ceil(H / scale)) + 1)
    lattice = [[rng.random() for _ in range(cells_x)] for _ in range(cells_y)]

    grid: list[list[float]] = [[0.0] * W for _ in range(H)]
    for y in range(H):
        fy = y / scale
        cy = int(fy)
        ty = fy - cy
        # Smoothstep: 6t^5 - 15t^4 + 10t^3 — same easing classic Perlin uses.
        sy = ty * ty * ty * (ty * (ty * 6 - 15) + 10)
        cy0 = min(cy, cells_y - 1)
        cy1 = min(cy + 1, cells_y - 1)
        for x in range(W):
            fx = x / scale
            cx = int(fx)
            tx = fx - cx
            sx = tx * tx * tx * (tx * (tx * 6 - 15) + 10)
            cx0 = min(cx, cells_x - 1)
            cx1 = min(cx + 1, cells_x - 1)
            v00 = lattice[cy0][cx0]
            v10 = lattice[cy0][cx1]
            v01 = lattice[cy1][cx0]
            v11 = lattice[cy1][cx1]
            top = v00 + (v10 - v00) * sx
            bot = v01 + (v11 - v01) * sx
            grid[y][x] = top + (bot - top) * sy
    return grid


def perlin_like_2d(
    W: int,
    H: int,
    *,
    seed: int,
    octaves: int = 4,
    scale: float = 16.0,
    persistence: float = 0.5,
) -> list[list[float]]:
    """Multi-octave fBm composed of value_noise_2d layers, normalised to [0, 1]."""
    if octaves < 1:
        raise ValueError("octaves must be >= 1")
    grid = [[0.0] * W for _ in range(H)]
    amplitude = 1.0
    total_amp = 0.0
    cur_scale = scale
    for o in range(octaves):
        layer = value_noise_2d(W, H, seed=seed + o * 1009, scale=max(2.0, cur_scale))
        for y in range(H):
            for x in range(W):
                grid[y][x] += layer[y][x] * amplitude
        total_amp += amplitude
        amplitude *= persistence
        cur_scale = max(2.0, cur_scale * 0.5)
    if total_amp > 0:
        inv = 1.0 / total_amp
        for y in range(H):
            for x in range(W):
                grid[y][x] *= inv
    return grid


# ---------------------------------------------------------------------------
# Synthesizers.
# ---------------------------------------------------------------------------


def synthesize_smoke_plume(
    W: int,
    H: int,
    *,
    seed: int,
    anchor_xy: tuple[int, int],
    height: float = 0.6,
    density: float = 0.7,
) -> Any:
    """Procedural grayscale smoke plume rising from ``anchor_xy``.

    Returns
    -------
    PIL.Image (RGBA) of size (W, H). Plume pixels carry alpha proportional to
    a Perlin-shaped column with a vertical buoyancy gradient that widens with
    height. Empty pixels carry alpha 0.

    Parameters
    ----------
    W, H: image dimensions in pixels.
    seed: reproducibility key.
    anchor_xy: pixel (x, y) the plume rises from. y is the bottom.
    height: fraction of the image vertical extent the plume reaches, in (0, 1].
    density: peak alpha multiplier in (0, 1].
    """
    if not (0.0 < height <= 1.0):
        raise ValueError("height must be in (0, 1]")
    if not (0.0 < density <= 1.0):
        raise ValueError("density must be in (0, 1]")
    Image = _import_pil()

    ax, ay = anchor_xy
    plume_h = max(8, int(H * height))
    noise = perlin_like_2d(W, plume_h, seed=seed, octaves=4, scale=24.0, persistence=0.55)

    # Build an RGBA buffer as a flat list of 4*W*H bytes.
    buf = bytearray(4 * W * H)
    # Smoke colour drifts grey-white based on density: low-density wisps are
    # lighter (atmospheric scattering proxy), high-density columns darker.
    base_grey = int(180 * (1.0 - density * 0.5))  # ~150 dense, ~180 wispy
    # Iterate with plume-local coords.
    for plume_y in range(plume_h):
        # img_y is the destination row in the canvas. Plume rises from ay.
        img_y = ay - plume_y
        if img_y < 0 or img_y >= H:
            continue
        # Vertical buoyancy: alpha falls off at the top, peaks just above
        # anchor, widens with plume_y.
        vert_factor = math.sin(math.pi * (plume_y / max(1, plume_h - 1)))
        # Width of column expands roughly sqrt(plume_y) — buoyancy gradient.
        half_w = max(8.0, 12.0 + 1.4 * math.sqrt(max(1, plume_y)) * (W / 320.0) * 4.0)
        for x in range(W):
            dx = x - ax
            radial = max(0.0, 1.0 - abs(dx) / half_w)
            n = noise[plume_y][x]  # in [0, 1]
            # Threshold low-noise edge so the plume has irregular silhouette.
            edge = max(0.0, n - 0.35) / 0.65
            alpha_f = density * vert_factor * radial * edge
            if alpha_f <= 0.0:
                continue
            alpha = min(255, max(0, int(255 * alpha_f)))
            # Slightly redden the dense core (combustion soot) and lighten the
            # wisps (cooler scatter). Stays in monochrome.
            tint = base_grey + int(40 * (1.0 - vert_factor))  # tops are lighter
            r = min(255, tint + 8)
            g = min(255, tint + 4)
            b = min(255, tint)
            i = 4 * (img_y * W + x)
            buf[i] = r
            buf[i + 1] = g
            buf[i + 2] = b
            buf[i + 3] = alpha
    return Image.frombytes("RGBA", (W, H), bytes(buf))


def synthesize_fire_glow(
    W: int,
    H: int,
    *,
    seed: int,
    anchor_xy: tuple[int, int],
    scale: float = 0.08,
) -> Any:
    """Procedural radial red-yellow fire glow with flicker noise.

    Returns an RGBA PIL.Image. Fire pixels carry red-orange-yellow hot-end
    palette colours; empty pixels carry alpha 0.

    Parameters
    ----------
    scale: glow radius as a fraction of min(W, H), in (0, 0.5].
    """
    if not (0.0 < scale <= 0.5):
        raise ValueError("scale must be in (0, 0.5]")
    Image = _import_pil()

    ax, ay = anchor_xy
    radius = max(6.0, scale * min(W, H))
    flicker = perlin_like_2d(W, H, seed=seed + 7919, octaves=3, scale=8.0, persistence=0.6)

    buf = bytearray(4 * W * H)
    rsq = radius * radius
    for y in range(H):
        for x in range(W):
            dx = x - ax
            dy = y - ay
            d2 = dx * dx + dy * dy
            if d2 > 4 * rsq:
                continue
            # Radial falloff with flicker modulation.
            d = math.sqrt(d2)
            base = max(0.0, 1.0 - d / (radius * 1.6))
            f = flicker[y][x] * 1.4 - 0.2
            heat = max(0.0, min(1.0, base * 0.7 + f * 0.5 * base))
            if heat <= 0.05:
                continue
            # Colour ramp: hot core white-yellow -> mid orange -> outer red.
            if heat > 0.85:
                r, g, b = 255, 240, 200
            elif heat > 0.55:
                r, g, b = 255, 180, 60
            elif heat > 0.30:
                r, g, b = 240, 110, 30
            else:
                r, g, b = 200, 60, 15
            alpha = int(255 * heat)
            i = 4 * (y * W + x)
            buf[i] = r
            buf[i + 1] = g
            buf[i + 2] = b
            buf[i + 3] = alpha
    return Image.frombytes("RGBA", (W, H), bytes(buf))


def synthesize_thermal_anomaly(
    W: int,
    H: int,
    *,
    seed: int,
    anchor_xy: tuple[int, int],
    scale: float = 0.06,
) -> Any:
    """Procedural false-colour thermal anomaly patch.

    Returns an RGBA PIL.Image. Anomaly pixels carry a magma-style blue->red
    palette over a Perlin-noise hotspot; empty pixels carry alpha 0.

    Used for synthetic thermal-overlay channels — NOT a substitute for a real
    FLIR Lepton frame.
    """
    if not (0.0 < scale <= 0.5):
        raise ValueError("scale must be in (0, 0.5]")
    Image = _import_pil()

    ax, ay = anchor_xy
    radius = max(6.0, scale * min(W, H))
    noise = perlin_like_2d(W, H, seed=seed + 13003, octaves=3, scale=10.0, persistence=0.55)

    buf = bytearray(4 * W * H)
    for y in range(H):
        for x in range(W):
            dx = x - ax
            dy = y - ay
            d = math.sqrt(dx * dx + dy * dy)
            base = max(0.0, 1.0 - d / (radius * 2.0))
            heat = max(0.0, min(1.0, base * 0.8 + noise[y][x] * 0.3 * base))
            if heat <= 0.05:
                continue
            # Magma-style ramp: deep blue -> magenta -> orange -> yellow.
            t = heat
            r = int(255 * min(1.0, max(0.0, t * 1.4 - 0.2)))
            g = int(255 * min(1.0, max(0.0, t * t)))
            b = int(255 * min(1.0, max(0.0, 0.6 - 0.8 * t + 0.5 * t * t)))
            alpha = int(220 * heat)
            i = 4 * (y * W + x)
            buf[i] = r
            buf[i + 1] = g
            buf[i + 2] = b
            buf[i + 3] = alpha
    return Image.frombytes("RGBA", (W, H), bytes(buf))
