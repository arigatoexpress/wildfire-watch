"""wfw-fire-yolov8n-v0.1.0 - YOLOv8n fire/smoke detector entrypoint.

This module is the v0.1.0 detector entrypoint for the wildfire-watch model
registry. The trained weights at ``runs/v0.1.0/weights/best.pt`` are produced
by the recipe at ``train_recipe.yaml``.

Status: TRAINING_READY. The Python entrypoint is shipped, but the trained
weights are pending dataset access + ultralytics installation. See
``status.md`` and ``manifest.json["weights_blocker"]``.

Two operating modes (mirrors v0.0.1's API contract for callers that compose
against the registry):

- **Real-mode**: lazy-import ultralytics. Loads ``weights/best.pt``, runs
  YOLOv8n inference, returns a Detection. If weights are missing OR
  ultralytics isn't installed, raises a RuntimeError with an actionable
  message — callers MUST handle this and either install + train or
  fall back explicitly to v0.0.1.

- **Stub-mode**: given pre-computed scalars ``(rgb_score, thermal_delta_c)``,
  runs the same fusion arithmetic v0.0.1 uses. Used by the simulator
  and registry tests so they remain deterministic without ultralytics.

Released 2026-05-02 by wildfire-watch as a TRAINING_READY artifact. The
RELEASED state is contingent on weights landing — see ``status.md``.

The module is dependency-free at import time: ultralytics, torch, PIL, and
numpy are all lazy-imported inside the functions that need them. The
registry test suite imports this module without any ML dependencies.
"""

from __future__ import annotations

import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MODEL_ID = "wfw-fire-yolov8n-v0.1.0"
VERSION = "0.1.0"
STATUS = "TRAINING_READY"

# Class index -> name mapping. Aligns with FASDD + D-Fire taxonomies.
CLASS_NAMES = ("fire", "smoke")

# Inference defaults. Overridable per-call.
DEFAULT_CONF_THRESHOLD = 0.25
DEFAULT_IOU_THRESHOLD = 0.50
DEFAULT_IMGSZ = 640
DEFAULT_MAX_DET = 300

# Where the trained checkpoint will land. Gitignored at runtime.
WEIGHTS_PATH = Path(__file__).resolve().parent / "weights" / "best.pt"

# Threshold constants mirrored from v0.0.1 (kept here so stub-mode is
# self-contained and doesn't need to import a path-with-dots module).
SMOKE_MIN_AREA_FRAC = 0.005
THERMAL_FIRE_FLOOR_C = 5.0
THERMAL_AUTO_FIRE_C = 15.0


@dataclass(frozen=True)
class Detection:
    """One v0.1.0 detection.

    Mirrors v0.0.1's Detection contract so call-sites composing against the
    registry don't need to special-case versions. ``bbox_xyxy`` is in absolute
    pixel coordinates; ``score`` is in [0, 1]; ``class_name`` is one of
    ``CLASS_NAMES`` plus the sentinel ``"none"``.
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
            "status": STATUS,
        }


def weights_available() -> bool:
    """Cheap check used by callers to decide whether real-mode is reachable."""
    return WEIGHTS_PATH.exists() and WEIGHTS_PATH.stat().st_size > 0


def _load_yolo_model() -> Any:
    """Lazy-load the ultralytics YOLOv8n model. Raises if unavailable.

    Pulled out so tests can stub it (and so the import error surfaces
    actionable next steps, not a generic ImportError).
    """
    try:
        from ultralytics import YOLO  # noqa: PLC0415
    except ImportError as e:
        raise RuntimeError(
            "wfw-fire-yolov8n-v0.1.0 real-mode requires ultralytics. "
            "Install: pip install ultralytics torch. "
            "Or call predict_stub() / fall back to v0.0.1."
        ) from e
    if not weights_available():
        raise RuntimeError(
            f"Trained weights not found at {WEIGHTS_PATH}. "
            "v0.1.0 is TRAINING_READY but not yet trained — see status.md "
            "for the unblocking steps."
        )
    return YOLO(str(WEIGHTS_PATH))


def predict_image(
    image_path: str | Path,
    conf: float = DEFAULT_CONF_THRESHOLD,
    iou: float = DEFAULT_IOU_THRESHOLD,
    imgsz: int = DEFAULT_IMGSZ,
) -> Detection:
    """Run YOLOv8n inference on a JPEG/PNG path.

    Raises RuntimeError if weights or ultralytics are unavailable. The caller
    is expected to either (a) install + train, (b) handle the error, or (c)
    use predict_stub() for the deterministic-scalars path.

    Returns a Detection wrapping the highest-confidence box. If the model
    produces no boxes above ``conf``, returns class_name="none" with
    score=0.0 and bbox=None.
    """
    t0 = time.perf_counter()

    model = _load_yolo_model()  # may raise RuntimeError
    results = model.predict(
        str(image_path),
        conf=conf,
        iou=iou,
        imgsz=imgsz,
        max_det=DEFAULT_MAX_DET,
        verbose=False,
    )

    if not results:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return Detection(score=0.0, class_name="none", bbox_xyxy=None, latency_ms=latency_ms)

    boxes = getattr(results[0], "boxes", None)
    if boxes is None or len(boxes) == 0:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return Detection(score=0.0, class_name="none", bbox_xyxy=None, latency_ms=latency_ms)

    # Pick the highest-confidence box across all detected classes.
    confs = boxes.conf.tolist() if hasattr(boxes.conf, "tolist") else list(boxes.conf)
    best_idx = max(range(len(confs)), key=lambda i: confs[i])
    cls_idx = int(boxes.cls[best_idx])
    score = float(confs[best_idx])
    xyxy = boxes.xyxy[best_idx]
    x1, y1, x2, y2 = (float(v) for v in (xyxy[0], xyxy[1], xyxy[2], xyxy[3]))

    class_name = CLASS_NAMES[cls_idx] if 0 <= cls_idx < len(CLASS_NAMES) else "none"
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return Detection(
        score=score,
        class_name=class_name,
        bbox_xyxy=(x1, y1, x2, y2),
        latency_ms=latency_ms,
    )


def predict_stub(rgb_score: float, thermal_delta_c: float) -> Detection:
    """Stub-mode: pre-computed scalars in, Detection out.

    Mirrors v0.0.1's stub fusion arithmetic so the simulator + registry
    tests stay deterministic without ultralytics installed. Promotion logic:
    thermal >= 15 C bumps a candidate to fire; thermal in [5, 15) keeps it
    smoke; below 5 C returns 'none' (the fusion gate would reject anyway).

    The returned Detection's model_id reads v0.1.0 (since the call-site
    asked for v0.1.0) — the underlying logic is the v0.0.1-shape fusion.
    Callers that want strict YOLO-vs-heuristic separation should branch on
    weights_available().
    """
    t0 = time.perf_counter()
    rgb_score = max(0.0, min(1.0, float(rgb_score)))
    thermal_delta_c = float(thermal_delta_c)

    # Below the heuristic's confidence floor.
    if rgb_score < SMOKE_MIN_AREA_FRAC + 0.4:
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
        # Below thermal floor; fusion gate would reject downstream.
        class_name = "smoke" if rgb_score >= 0.4 else "none"
        score = rgb_score

    latency_ms = (time.perf_counter() - t0) * 1000.0
    return Detection(
        score=score,
        class_name=class_name,
        bbox_xyxy=None,
        latency_ms=latency_ms,
    )


def predict(*args, **kwargs) -> Detection:
    """Dispatch to predict_image or predict_stub by argument shape.

    Mirrors v0.0.1.predict() so callers don't need version-specific code.

    - ``predict("path/to.jpg")`` -> real-mode (raises if weights pending).
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


# Suppress an unused-import lint complaint for warnings (kept for future use
# when fallbacks become explicit). Currently predict_image RAISES rather than
# warns + falls back, since silent fallbacks are exactly the gaming-the-metric
# anti-pattern this file is designed to avoid.
_ = warnings
