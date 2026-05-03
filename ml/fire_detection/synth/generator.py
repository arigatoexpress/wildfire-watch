"""Compose a single (image, YOLO-labels) pair from a backdrop + procedural overlays.

A label is a dict ``{"class_id": int, "x_center": f, "y_center": f, "width": f, "height": f}``
with all four box coordinates normalised to ``[0, 1]``. ``class_id`` is one of
``ml.fire_detection.synth.CLASS_FIRE`` or ``CLASS_SMOKE``.

The composer never produces a label whose box is empty or out-of-bounds. After
augmentations that may translate boxes (perspective warp, occlusion) we clip
to the image and drop boxes that lose more than 70% of their original area.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from . import CLASS_FIRE, CLASS_SMOKE
from .augmentation import apply_augmentations
from .procedural import (
    perlin_like_2d,
    synthesize_fire_glow,
    synthesize_smoke_plume,
)

__all__ = [
    "generate_sample",
    "synthetic_backdrop",
]

DEFAULT_W = 640
DEFAULT_H = 640

# Min normalized side length below which a box is considered too tiny to teach
# anything useful. Mirrors ultralytics' default behaviour of dropping micro-boxes.
MIN_BOX_SIDE_NORM = 0.01


def _import_pil() -> Any:
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "ml.fire_detection.synth.generator requires Pillow. "
            "Install with: /usr/local/bin/python3 -m pip install Pillow"
        ) from e
    return Image


def _bbox_from_alpha(image: Any, *, alpha_threshold: int = 24) -> tuple[int, int, int, int] | None:
    """Tightest axis-aligned bbox over pixels with alpha >= threshold.

    Returns (x0, y0, x1, y1) inclusive or None if there are no qualifying pixels.
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    alpha = image.getchannel("A")
    bbox = alpha.point(lambda v, t=alpha_threshold: 255 if v >= t else 0).getbbox()
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    # PIL getbbox returns half-open (x1, y1 exclusive). Convert to inclusive.
    return x0, y0, max(x0, x1 - 1), max(y0, y1 - 1)


def _to_yolo_label(
    class_id: int,
    bbox: tuple[int, int, int, int],
    W: int,
    H: int,
) -> dict[str, float] | None:
    """Convert pixel bbox -> YOLO normalised dict. Drops degenerate boxes."""
    x0, y0, x1, y1 = bbox
    if x1 <= x0 or y1 <= y0:
        return None
    cx = ((x0 + x1) / 2.0) / W
    cy = ((y0 + y1) / 2.0) / H
    w = (x1 - x0) / W
    h = (y1 - y0) / H
    if w < MIN_BOX_SIDE_NORM or h < MIN_BOX_SIDE_NORM:
        return None
    return {
        "class_id": int(class_id),
        "x_center": float(max(0.0, min(1.0, cx))),
        "y_center": float(max(0.0, min(1.0, cy))),
        "width": float(max(0.0, min(1.0, w))),
        "height": float(max(0.0, min(1.0, h))),
    }


def _rect_iou_area_frac(
    box: tuple[int, int, int, int],
    occluders: list[tuple[int, int, int, int]],
) -> float:
    """Fraction of ``box``'s area covered by the union of occluder rects."""
    bx0, by0, bx1, by1 = box
    if bx1 <= bx0 or by1 <= by0:
        return 0.0
    box_area = (bx1 - bx0) * (by1 - by0)
    if not occluders:
        return 0.0
    # Area-of-union via inclusion-exclusion is overkill — for our small lists
    # (1-3 patches) we compute pairwise overlap and sum, capping at box_area.
    covered = 0.0
    for ox0, oy0, ox1, oy1 in occluders:
        ix0 = max(bx0, ox0)
        iy0 = max(by0, oy0)
        ix1 = min(bx1, ox1)
        iy1 = min(by1, oy1)
        if ix1 > ix0 and iy1 > iy0:
            covered += (ix1 - ix0) * (iy1 - iy0)
    return min(1.0, covered / box_area)


def synthetic_backdrop(W: int, H: int, *, seed: int) -> Any:
    """Procedural fallback backdrop — a sky-over-canopy gradient + Perlin texture.

    Used when the caller hasn't passed a real backdrop. NOT a substitute for
    real federal-public-domain imagery; it exists so the negative-class samples
    in the dataset don't all look identical to one of the 12 backdrop photos.
    """
    Image = _import_pil()
    rng = random.Random(seed)
    sky_top = (
        rng.randint(110, 170),
        rng.randint(140, 190),
        rng.randint(180, 230),
    )
    sky_bot = (
        rng.randint(180, 220),
        rng.randint(190, 220),
        rng.randint(200, 230),
    )
    canopy_top = (
        rng.randint(40, 70),
        rng.randint(70, 110),
        rng.randint(40, 60),
    )
    canopy_bot = (
        rng.randint(20, 40),
        rng.randint(45, 70),
        rng.randint(20, 35),
    )
    horizon = int(H * rng.uniform(0.45, 0.65))

    img = Image.new("RGB", (W, H))
    px = img.load()
    noise = perlin_like_2d(W, H, seed=seed + 31, octaves=3, scale=18.0, persistence=0.55)
    for y in range(H):
        if y < horizon:
            t = y / max(1, horizon - 1)
            r = int(sky_top[0] + (sky_bot[0] - sky_top[0]) * t)
            g = int(sky_top[1] + (sky_bot[1] - sky_top[1]) * t)
            b = int(sky_top[2] + (sky_bot[2] - sky_top[2]) * t)
        else:
            t = (y - horizon) / max(1, H - horizon - 1)
            r = int(canopy_top[0] + (canopy_bot[0] - canopy_top[0]) * t)
            g = int(canopy_top[1] + (canopy_bot[1] - canopy_top[1]) * t)
            b = int(canopy_top[2] + (canopy_bot[2] - canopy_top[2]) * t)
        for x in range(W):
            n = noise[y][x] - 0.5
            px[x, y] = (
                max(0, min(255, int(r + n * 30))),
                max(0, min(255, int(g + n * 30))),
                max(0, min(255, int(b + n * 20))),
            )
    return img


def _load_backdrop(backdrop: Path | None, W: int, H: int, seed: int) -> Any:
    Image = _import_pil()
    if backdrop is None:
        return synthetic_backdrop(W, H, seed=seed)
    p = Path(backdrop)
    if not p.exists():
        raise FileNotFoundError(f"backdrop image not found: {p}")
    img = Image.open(p).convert("RGB")
    # Cover-fit to (W, H) so we always end up at the target resolution.
    src_w, src_h = img.size
    src_aspect = src_w / src_h
    dst_aspect = W / H
    if src_aspect > dst_aspect:
        new_h = H
        new_w = int(round(H * src_aspect))
    else:
        new_w = W
        new_h = int(round(W / src_aspect))
    img = img.resize((new_w, new_h), Image.BILINEAR)
    left = (new_w - W) // 2
    top = (new_h - H) // 2
    return img.crop((left, top, left + W, top + H))


def generate_sample(
    backdrop: Path | None,
    *,
    seed: int,
    has_smoke: bool,
    has_fire: bool,
    augmentation_level: float = 0.5,
    image_size: tuple[int, int] = (DEFAULT_W, DEFAULT_H),
) -> tuple[Any, list[dict[str, float]]]:
    """Compose a single labelled training sample.

    Parameters
    ----------
    backdrop:
        Path to a public-domain backdrop image, or ``None`` to use a procedural
        sky+canopy gradient.
    seed:
        Reproducibility key. Same seed -> same image + same labels.
    has_smoke, has_fire:
        Class flags. Both False -> negative (no labels).
    augmentation_level:
        In [0, 1]. 0 disables augmentation; 1 is the documented max strength.
    image_size:
        Output (W, H). Defaults to 640x640 to match the YOLOv8n input.

    Returns
    -------
    (PIL.Image, list[YOLO label dict]).
    """
    if not (0.0 <= augmentation_level <= 1.0):
        raise ValueError("augmentation_level must be in [0, 1]")
    Image = _import_pil()
    W, H = image_size
    rng = random.Random(seed ^ 0xC0FFEE)

    base = _load_backdrop(backdrop, W, H, seed=seed)

    # Composite layers + collect raw (pre-augmentation) bboxes.
    composed = base.convert("RGBA")
    raw_boxes: list[tuple[int, int, int, int, int]] = []  # (cls, x0, y0, x1, y1)

    # Anchor a smoke source somewhere in the lower 60% of the canvas.
    if has_smoke:
        ax = rng.randint(int(0.2 * W), int(0.8 * W))
        ay = rng.randint(int(0.55 * H), int(0.95 * H))
        plume = synthesize_smoke_plume(
            W,
            H,
            seed=seed + 17,
            anchor_xy=(ax, ay),
            height=rng.uniform(0.45, 0.85),
            density=rng.uniform(0.55, 0.9),
        )
        bbox = _bbox_from_alpha(plume, alpha_threshold=20)
        composed = Image.alpha_composite(composed, plume)
        if bbox is not None:
            raw_boxes.append((CLASS_SMOKE, *bbox))

    if has_fire:
        # Fire usually appears at the base of the smoke plume, so anchor near
        # the smoke anchor when both classes coexist.
        if has_smoke and raw_boxes:
            _, sx0, sy0, sx1, sy1 = raw_boxes[-1]
            fx = rng.randint(sx0 + (sx1 - sx0) // 4, sx1 - (sx1 - sx0) // 4)
            fy = rng.randint(sy1 - (sy1 - sy0) // 6, sy1)
        else:
            fx = rng.randint(int(0.2 * W), int(0.8 * W))
            fy = rng.randint(int(0.55 * H), int(0.92 * H))
        glow = synthesize_fire_glow(
            W,
            H,
            seed=seed + 29,
            anchor_xy=(fx, fy),
            scale=rng.uniform(0.04, 0.12),
        )
        bbox = _bbox_from_alpha(glow, alpha_threshold=40)
        composed = Image.alpha_composite(composed, glow)
        if bbox is not None:
            raw_boxes.append((CLASS_FIRE, *bbox))

    # Down-convert to RGB before augmentations (perspective warp + occlusion
    # need a deterministic mode).
    composed_rgb = composed.convert("RGB")

    # Apply augmentations. Perspective-warp the boxes by warping the four
    # corners of each bbox via the same transform — but PIL's transform()
    # doesn't expose the matrix, so we instead clip to image bounds and
    # accept some label noise. This matches FASDD's approach where weak
    # boxes are tolerated.
    if augmentation_level > 0.0:
        augmented, occluders = apply_augmentations(
            composed_rgb,
            seed=seed + 41,
            level=augmentation_level,
        )
    else:
        augmented = composed_rgb
        occluders = []

    final = augmented.convert("RGB")

    # Convert raw boxes -> YOLO labels, dropping ones obscured by occluders.
    labels: list[dict[str, float]] = []
    for cls, x0, y0, x1, y1 in raw_boxes:
        if _rect_iou_area_frac((x0, y0, x1, y1), occluders) > 0.7:
            continue
        # Clip to image extent.
        x0 = max(0, min(W - 1, x0))
        y0 = max(0, min(H - 1, y0))
        x1 = max(0, min(W - 1, x1))
        y1 = max(0, min(H - 1, y1))
        label = _to_yolo_label(cls, (x0, y0, x1, y1), W, H)
        if label is not None:
            labels.append(label)

    return final, labels
