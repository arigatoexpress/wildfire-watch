# `wfw-fire-heuristic-v0.0.1`

The **first registered** wildfire-watch fire/smoke detector.

A deterministic, training-free colour-temperature heuristic. Released
2026-05-02 as the v0 anchor for the model registry, the Phase-0
post-flight processor, and the eval-harness baseline.

## What's in this directory

| File | Purpose |
|---|---|
| `inference.py` | The detector. Two modes: `predict_image(path)` (real, PIL-backed) and `predict_stub(rgb_score, thermal_delta_c)` (scalar pass-through). Returns a `Detection` dataclass. |
| `model_card.md` | Mitchell-format per-version card. Pins the v0.0.1 measured numbers. |
| `manifest.json` | Provenance metadata (model_id, version, license, code_sha, released_at, ...). Consumed by `ml/fire_detection/registry.py`. |
| `eval.json` | Raw eval output: synthetic-100 metrics + Mac-CPU latency. |
| `README.md` | This file. |

## Why v0.0.1 (and not v0.1.0)

v0.0.1 is intentionally a heuristic, not a trained model. The first
trained YOLO version is `v0.1.0`, gated on FASDD + FLAME-2 dataset
acquisition (see `../../DATASETS.md`). Shipping v0.0.1 first means:

1. The model registry has a real entry to discover.
2. The Phase-0 post-flight pipeline (`mavic_post_flight.py`) has a
   versioned, schema-stable model to cite in emitted signals.
3. The eval harness has a baseline to score against, so v0.1.0 has a
   measurable floor to beat.
4. The fusion-gate signal pipeline doesn't depend on having ultralytics
   installed.

## How to use

### Real-mode (PIL required)

```python
from ml.fire_detection.runs.v0.0.1.inference import predict
det = predict("path/to/frame.jpg")
print(det.class_name, det.score, det.bbox_xyxy, det.latency_ms)
```

### Stub-mode (no deps)

```python
from ml.fire_detection.runs.v0.0.1.inference import predict
det = predict(rgb_score=0.85, thermal_delta_c=18.0)
print(det.class_name, det.score)  # -> 'fire', ~0.72
```

### Registry lookup

```python
from ml.fire_detection.registry import get
entry = get("wfw-fire-heuristic-v0.0.1")
# or
entry = get("0.0.1")
# or
entry = get("latest")
print(entry.path, entry.released_at)
```

## What v0.0.1 is NOT

- Not a trained model. No weights, no PyTorch state-dict.
- Not a production detector. Synthetic precision-at-recall-0.80 is
  0.82, well below the >=0.95 target. Deploy only behind the fusion
  gate (`infer.should_emit`).
- Not Jetson-deployable as-is. CPU-only Python code; no GPU
  acceleration. v0.1.0 (YOLO + TensorRT FP16) is the deployment-target
  release.

## Reproducing the eval

The eval-harness measurement command is documented in
`model_card.md` section 10. Synthetic eval is seeded (seed=42), so
re-running yields identical numbers.
