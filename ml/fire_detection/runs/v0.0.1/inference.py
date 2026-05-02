"""wfw-fire-heuristic-v0.0.1 - colour-temperature + thermal-aware baseline detector.

This is a deterministic, training-free baseline. It exists so:

1. The model registry has a v0 anchor.
2. Phase 0 post-flight processing has a real model name + version to cite.
3. The eval harness has something to score (so v0.1.0 has a baseline to beat).
4. The fusion-gate signal pipeline doesn't depend on having ultralytics installed.

The detector is a function: given an RGB image (numpy or PIL is optional;
in stub-mode it accepts a (rgb_score: float, thermal_delta_c: float) tuple
and returns the same shape downstream callers expect).

Released 2026-05-02 by wildfire-watch.

Two operating modes:

- **Real-mode**: lazy-import PIL. Given a JPEG path or a PIL Image, compute a
  colour-histogram-based smoke/fire score (greyscale-saturated regions for
  smoke; red+yellow regions for fire). Reuses the heuristic constants that
  already live in ``mavic_post_flight.py``.
- **Stub-mode**: given pre-computed scalars ``(rgb_score, thermal_delta_c)``,
  pass them through unchanged. This is what the simulator + eval harness use.

Output: a ``Detection`` dataclass with ``score``, ``class_name``,
``bbox_xyxy``, ``latency_ms``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MODEL_ID = "wfw-fire-heuristic-v0.0.1"
VERSION = "0.0.1"

# Heuristic thresholds. These mirror the constants already used by
# ``mavic_post_flight.py`` so v0.0.1 is bit-for-bit consistent with the
# Phase-0 signal pipeline that's already in production.
SMOKE_GREY_MIN = 90
SMOKE_GREY_MAX = 200
SMOKE_CHANNEL_SPREAD = 25
SMOKE_MIN_AREA_FRAC = 0.005
FIRE_RED_DOMINANCE = 60
FIRE_RED_MIN_BRIGHTNESS = 150
FIRE_MIN_AREA_FRAC = 0.001

# Fusion gate (mirrors infer.should_emit). v0.0.1's Detection score is
# capped/promoted by these conditions when callers pass thermal_delta_c.
THERMAL_FIRE_FLOOR_C = 5.0
THERMAL_AUTO_FIRE_C = 15.0


@dataclass(frozen=True)
class Detection:
    """One v0.0.1 detection.

    ``score`` is in [0, 1]. ``class_name`` is one of {'smoke', 'fire', 'none'}.
    ``bbox_xyxy`` is the smoke/fire-pixel bounding box in image pixel coords
    (None in stub-mode or when the heuristic finds no contiguous region).
    ``latency_ms`` is wall-clock time spent in :func:`predict`.
    """

    score: float
    class_name: str
    bbox_xyxy: tuple[float, float, float, float] | None
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "class_name": self.class_name,
            "bbox_xyxy": list(self.bbox_xyxy) if self.bbox_xyxy is not None else None,
            "latency_ms": self.latency_ms,
            "model_id": MODEL_ID,
            "version": VERSION,
        }


# ---------------------------------------------------------------------------
# Real-mode: PIL-backed colour-histogram detector.
# ---------------------------------------------------------------------------


def _score_rgb_pixels(pixels: list[tuple[int, int, int]]) -> tuple[float, float]:
    """Return (smoke_area_frac, fire_area_frac) over a flat pixel iterable.

    Pure-stdlib so the registry test can import without PIL.
    """
    total = len(pixels) or 1
    smoke = 0
    fire = 0
    for r, g, b in pixels:
        max_chan = r if r >= g and r >= b else (g if g >= b else b)
        min_chan = r if r <= g and r <= b else (g if g <= b else b)
        spread = max_chan - min_chan
        mean = (r + g + b) / 3.0
        if SMOKE_GREY_MIN <= mean <= SMOKE_GREY_MAX and spread <= SMOKE_CHANNEL_SPREAD:
            smoke += 1
        if (r - max(g, b)) >= FIRE_RED_DOMINANCE and r > FIRE_RED_MIN_BRIGHTNESS:
            fire += 1
    return smoke / total, fire / total


def _classify(smoke_frac: float, fire_frac: float) -> tuple[str, float]:
    """Map the two area fractions to (class_name, score)."""
    if fire_frac >= FIRE_MIN_AREA_FRAC:
        return "fire", min(1.0, 0.5 + fire_frac * 5.0)
    if smoke_frac >= SMOKE_MIN_AREA_FRAC:
        return "smoke", min(1.0, 0.4 + smoke_frac * 2.0)
    return "none", 0.0


def predict_image(image_path: str | Path) -> Detection:
    """Run the heuristic against a JPEG/PNG path.

    Lazy-imports PIL. Returns a Detection with the bounding box of the
    contiguous smoke/fire region (axis-aligned, computed from the
    candidate-pixel mask).
    """
    t0 = time.perf_counter()
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "wfw-fire-heuristic-v0.0.1 real-mode requires Pillow. "
            "Use predict_stub() for stub-mode evaluation."
        ) from e

    with Image.open(image_path) as im:
        im = im.convert("RGB")
        # Downsample for speed. Mirrors mavic_post_flight.heuristic_score_pil.
        im.thumbnail((320, 320))
        w, h = im.size
        raw = im.tobytes()

    pixels = [
        (raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)
    ]
    smoke_frac, fire_frac = _score_rgb_pixels(pixels)
    class_name, score = _classify(smoke_frac, fire_frac)

    bbox: tuple[float, float, float, float] | None = None
    if class_name != "none":
        # Compute axis-aligned bbox over candidate pixels (whichever class won).
        threshold_smoke = class_name == "smoke"
        xs: list[int] = []
        ys: list[int] = []
        idx = 0
        for y in range(h):
            for x in range(w):
                r, g, b = raw[idx], raw[idx + 1], raw[idx + 2]
                idx += 3
                if threshold_smoke:
                    spread = max(r, g, b) - min(r, g, b)
                    mean = (r + g + b) / 3.0
                    is_cand = (
                        SMOKE_GREY_MIN <= mean <= SMOKE_GREY_MAX
                        and spread <= SMOKE_CHANNEL_SPREAD
                    )
                else:
                    is_cand = (
                        (r - max(g, b)) >= FIRE_RED_DOMINANCE
                        and r > FIRE_RED_MIN_BRIGHTNESS
                    )
                if is_cand:
                    xs.append(x)
                    ys.append(y)
        if xs and ys:
            bbox = (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))

    latency_ms = (time.perf_counter() - t0) * 1000.0
    return Detection(
        score=score,
        class_name=class_name,
        bbox_xyxy=bbox,
        latency_ms=latency_ms,
    )


# ---------------------------------------------------------------------------
# Stub-mode: pass-through scalar fusion. Used by tests + simulator.
# ---------------------------------------------------------------------------


def predict_stub(rgb_score: float, thermal_delta_c: float) -> Detection:
    """Stub-mode: pre-computed scalars in, Detection out.

    Class promotion logic mirrors the existing infer.should_emit / build_signal
    flow: thermal >= 15 C bumps a smoke candidate to fire; thermal between
    5 and 15 C keeps it smoke; thermal below 5 C returns 'none' regardless
    of rgb_score (the fusion gate would reject it anyway).
    """
    t0 = time.perf_counter()
    # Clamp inputs to documented ranges.
    rgb_score = max(0.0, min(1.0, float(rgb_score)))
    thermal_delta_c = float(thermal_delta_c)

    if rgb_score < SMOKE_MIN_AREA_FRAC + 0.4:  # mirrors min smoke score floor
        # Below the heuristic's confidence floor; return a 'none' detection.
        if rgb_score <= 0.0:
            class_name = "none"
            score = 0.0
        else:
            class_name = "none"
            score = rgb_score
    elif thermal_delta_c >= THERMAL_AUTO_FIRE_C:
        class_name = "fire"
        score = min(1.0, 0.5 * rgb_score + 0.5 * min(thermal_delta_c / 30.0, 1.0))
    elif thermal_delta_c >= THERMAL_FIRE_FLOOR_C:
        class_name = "smoke"
        score = min(1.0, 0.5 * rgb_score + 0.5 * min(thermal_delta_c / 30.0, 1.0))
    else:
        # Below thermal floor - the fusion gate would reject downstream.
        # The detector still returns the rgb-only smoke candidate so callers
        # see what was scored.
        class_name = "smoke" if rgb_score >= 0.4 else "none"
        score = rgb_score

    latency_ms = (time.perf_counter() - t0) * 1000.0
    return Detection(
        score=score,
        class_name=class_name,
        bbox_xyxy=None,
        latency_ms=latency_ms,
    )


# ---------------------------------------------------------------------------
# Public predict() dispatcher.
# ---------------------------------------------------------------------------


def predict(*args, **kwargs) -> Detection:
    """Dispatch to predict_image or predict_stub by argument shape.

    - ``predict("path/to.jpg")`` -> real-mode.
    - ``predict(image_path=...)`` -> real-mode.
    - ``predict(rgb_score=0.9, thermal_delta_c=12.0)`` -> stub-mode.
    - ``predict(0.9, 12.0)`` -> stub-mode.
    """
    if "image_path" in kwargs:
        return predict_image(kwargs["image_path"])
    if "rgb_score" in kwargs or "thermal_delta_c" in kwargs:
        return predict_stub(
            rgb_score=kwargs.get("rgb_score", 0.0),
            thermal_delta_c=kwargs.get("thermal_delta_c", 0.0),
        )
    if len(args) == 1 and isinstance(args[0], (str, Path)):
        return predict_image(args[0])
    if len(args) == 2 and all(isinstance(a, (int, float)) for a in args):
        return predict_stub(rgb_score=args[0], thermal_delta_c=args[1])
    raise TypeError(
        "predict() expects either an image path or (rgb_score, thermal_delta_c). "
        f"got args={args!r} kwargs={kwargs!r}"
    )
