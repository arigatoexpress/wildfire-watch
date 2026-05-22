"""Image augmentations applied after composition.

All augmentations are deterministic given a seed and operate on PIL.Image
objects. Lazy-import PIL + numpy. No torchvision, no opencv.

Implemented
-----------
- ``brightness(image, *, seed, magnitude)`` — multiplicative brightness in
  ``[1 - 0.25 * m, 1 + 0.25 * m]``.
- ``color_temperature(image, *, seed, magnitude)`` — kelvin shift in
  ``[-300 * m, +300 * m]`` via R/B channel scaling.
- ``gaussian_noise(image, *, seed, magnitude)`` — additive zero-mean noise,
  sigma in ``[3, 15]`` scaled by m.
- ``perspective_warp(image, *, seed, magnitude)`` — corner-displacement based
  perspective transform; simulates UAV oblique -> nadir warps.
- ``random_occlusion(image, *, seed, magnitude)`` — opaque dark patches that
  imitate canopy occlusion. Returns the augmented image plus the list of
  axis-aligned occlusion rectangles so the caller can prune labels that lose
  too much area.
"""

from __future__ import annotations

import random
from typing import Any

__all__ = [
    "brightness",
    "color_temperature",
    "gaussian_noise",
    "perspective_warp",
    "random_occlusion",
    "apply_augmentations",
]


def _import_pil() -> tuple[Any, Any, Any]:
    """Lazy-import PIL.{Image,ImageEnhance,ImageDraw}."""
    try:
        from PIL import Image, ImageDraw, ImageEnhance  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "ml.fire_detection.synth.augmentation requires Pillow. "
            "Install with: /usr/local/bin/python3 -m pip install Pillow"
        ) from e
    return Image, ImageEnhance, ImageDraw


def _import_numpy() -> Any:
    try:
        import numpy as np  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "ml.fire_detection.synth.augmentation requires numpy. "
            "Install with: /usr/local/bin/python3 -m pip install numpy"
        ) from e
    return np


def _clamp_mag(magnitude: float) -> float:
    return max(0.0, min(1.0, float(magnitude)))


def brightness(image: Any, *, seed: int, magnitude: float = 1.0) -> Any:
    """Random multiplicative brightness factor in ``[1 - 0.25*m, 1 + 0.25*m]``."""
    Image, ImageEnhance, _ = _import_pil()
    m = _clamp_mag(magnitude)
    rng = random.Random(seed ^ 0xB81677)
    factor = 1.0 + rng.uniform(-0.25, 0.25) * m
    return ImageEnhance.Brightness(image).enhance(factor)


def color_temperature(image: Any, *, seed: int, magnitude: float = 1.0) -> Any:
    """Approximate +/- 300K * m colour-temperature shift via R/B channel scaling.

    Positive shift -> warmer (more red, less blue). Negative shift -> cooler.
    Mapping is intentionally approximate; this is augmentation, not photometric
    calibration.
    """
    Image, _, _ = _import_pil()
    m = _clamp_mag(magnitude)
    rng = random.Random(seed ^ 0xCBADCAFE)
    delta_k = rng.uniform(-300.0, 300.0) * m
    # Approx: each +100K warmer scales R by ~1.03, B by ~0.97.
    r_scale = 1.0 + (delta_k / 100.0) * 0.03
    b_scale = 1.0 - (delta_k / 100.0) * 0.03
    img = image.convert("RGB") if image.mode != "RGB" else image
    r, g, b = img.split()
    r = r.point(lambda v, s=r_scale: max(0, min(255, int(v * s))))
    b = b.point(lambda v, s=b_scale: max(0, min(255, int(v * s))))
    out = Image.merge("RGB", (r, g, b))
    if image.mode == "RGBA":
        return out.convert("RGBA")
    return out


def gaussian_noise(image: Any, *, seed: int, magnitude: float = 1.0) -> Any:
    """Additive zero-mean Gaussian noise with sigma in [3, 15] * m."""
    Image, _, _ = _import_pil()
    np = _import_numpy()
    m = _clamp_mag(magnitude)
    rng = np.random.default_rng(seed ^ 0xD153F00D)
    sigma = float(rng.uniform(3.0, 15.0)) * m
    if sigma <= 0.0:
        return image
    arr = np.asarray(image.convert("RGB"), dtype=np.int16)
    noise = rng.normal(0.0, sigma, arr.shape).astype(np.int16)
    out = np.clip(arr + noise, 0, 255).astype(np.uint8)
    res = Image.fromarray(out, mode="RGB")
    if image.mode == "RGBA":
        return res.convert("RGBA")
    return res


def perspective_warp(image: Any, *, seed: int, magnitude: float = 1.0) -> Any:
    """Corner-displacement perspective warp.

    Simulates UAV oblique-to-nadir geometry change. Magnitude 1.0 displaces
    each corner by up to ~10% of the relevant edge length.
    """
    Image, _, _ = _import_pil()
    np = _import_numpy()
    m = _clamp_mag(magnitude)
    rng = random.Random(seed ^ 0xE91E63)

    W, H = image.size
    max_dx = 0.10 * W * m
    max_dy = 0.10 * H * m

    def jitter(x: float, y: float) -> tuple[float, float]:
        return (
            x + rng.uniform(-max_dx, max_dx),
            y + rng.uniform(-max_dy, max_dy),
        )

    src = [(0, 0), (W, 0), (W, H), (0, H)]
    dst = [jitter(x, y) for x, y in src]

    # Solve for the perspective coefficients per PIL recipe.
    matrix = []
    for (sx, sy), (dx, dy) in zip(src, dst):
        matrix.append([dx, dy, 1, 0, 0, 0, -sx * dx, -sx * dy])
        matrix.append([0, 0, 0, dx, dy, 1, -sy * dx, -sy * dy])
    A = np.asarray(matrix, dtype=np.float64)
    B = np.asarray(src, dtype=np.float64).reshape(8)
    coeffs, *_ = np.linalg.lstsq(A, B, rcond=None)
    return image.transform(
        (W, H),
        Image.PERSPECTIVE,
        tuple(float(c) for c in coeffs),
        resample=Image.BILINEAR,
    )


def random_occlusion(
    image: Any,
    *,
    seed: int,
    magnitude: float = 1.0,
) -> tuple[Any, list[tuple[int, int, int, int]]]:
    """Stamp 1-3 dark "canopy" patches over the image.

    Returns
    -------
    (occluded_image, list[(x0, y0, x1, y1)]). The caller can use the patch
    rectangles to drop YOLO labels whose bounding box loses >70% of its area.
    """
    Image, _, ImageDraw = _import_pil()
    m = _clamp_mag(magnitude)
    rng = random.Random(seed ^ 0xF1ECEDED)
    img = image.copy()
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    W, H = img.size
    n_patches = rng.randint(1, max(1, int(round(3 * m)))) if m > 0 else 0
    rects: list[tuple[int, int, int, int]] = []
    for _ in range(n_patches):
        pw = rng.randint(int(0.05 * W), max(int(0.05 * W) + 1, int(0.20 * W * m + 1)))
        ph = rng.randint(int(0.05 * H), max(int(0.05 * H) + 1, int(0.20 * H * m + 1)))
        x0 = rng.randint(0, max(0, W - pw))
        y0 = rng.randint(0, max(0, H - ph))
        x1 = x0 + pw
        y1 = y0 + ph
        # Dark, slightly green canopy colour with high alpha.
        draw.rectangle([x0, y0, x1, y1], fill=(28, 48, 28, 220))
        rects.append((x0, y0, x1, y1))
    return img, rects


def apply_augmentations(
    image: Any,
    *,
    seed: int,
    level: float = 0.5,
) -> tuple[Any, list[tuple[int, int, int, int]]]:
    """Apply the full augmentation chain at the given strength level.

    Returns (image, occlusion_rects). Order: color_temp -> brightness -> noise
    -> perspective -> occlusion. The first three are pixel-level (don't move
    boxes); perspective + occlusion may move/cut boxes (caller handles).
    """
    img = image
    img = color_temperature(img, seed=seed, magnitude=level)
    img = brightness(img, seed=seed + 1, magnitude=level)
    img = gaussian_noise(img, seed=seed + 2, magnitude=level)
    img = perspective_warp(img, seed=seed + 3, magnitude=level)
    img, rects = random_occlusion(img, seed=seed + 4, magnitude=level)
    return img, rects
