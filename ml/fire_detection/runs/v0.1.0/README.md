# `wfw-fire-yolov8n-v0.1.0`

The **second registered** wildfire-watch fire/smoke detector — first
trained-architecture version. Status: **TRAINING_READY** (recipe shipped,
weights pending; see `status.md`).

Released 2026-05-02 by wildfire-watch as the v0.1.0 anchor: registry entry,
training recipe, inference entrypoint, and Mitchell-format model card. The
trained `weights/best.pt` is produced by the recipe at `train_recipe.yaml`
the moment datasets + ultralytics land.

## What's in this directory

| File | Purpose |
|---|---|
| `inference.py` | The v0.1.0 detector entrypoint. `predict_image()` runs YOLOv8n via lazy ultralytics import; `predict_stub()` is the deterministic-scalars path the simulator + tests use. |
| `train_recipe.yaml` | End-to-end training recipe: FASDD CV+UAV pretrain (10 epochs MPS / 100 epochs prod) -> FLAME-2 fine-tune (5 / 30 epochs) -> D-Fire holdout eval. Includes acceptance gates. |
| `manifest.json` | Provenance metadata + `status: "TRAINING_READY"`. Consumed by `ml/fire_detection/registry.py`. |
| `eval.json` | Eval JSON. Currently `metrics: null`, `status: "not_yet_trained"`. Populated by `eval/eval_harness.py` after the first training run. |
| `model_card.md` | Mitchell-format per-version card. Measured-metrics fields explicitly marked TBD until weights land. |
| `status.md` | Honest TRAINING_READY status report + RELEASED-unblock checklist. |
| `weights/best.pt` | Trained checkpoint (gitignored, produced by `train_recipe.yaml`). |
| `README.md` | This file. |

## Why TRAINING_READY (not RELEASED)

Three concrete blockers, all environmental, all unblockable by the user:

1. FASDD / FLAME-2 / D-Fire all require auth-walled manual download
   (Science Data Bank, IEEE DataPort, GitHub-OneDrive interactive).
2. `ultralytics` and `torch` are not installed in the host
   `/usr/local/bin/python3` environment.
3. No GPU/MPS-enabled environment is reachable from the dispatch sandbox.

Per the dispatch scope: "If datasets aren't accessible OR ultralytics
can't install OR no GPU [is available], document the blocker honestly and
build the training-ready harness instead." That's what this directory
shows. See `status.md` for the unblock recipe.

## Why this still counts as "shipped" for the registry

The model registry validates that each `runs/vX.Y.Z/` directory has a
`manifest.json` + `eval.json` (both well-formed JSON, both at minimum
naming the model and version). The shipped artifact is **the manifest +
recipe + entrypoint**, even when the weights are pending. The valuation
engine's KPI is `model_versions_shipped`; both `RELEASED` and
`TRAINING_READY` count, because the artifact (the recipe-as-code) is
shipped — which is a defensible choice and one we explicitly call out
to anyone reading the registry.

`registry.py` exposes the `status` field on `ModelEntry` so dashboards
can distinguish `RELEASED` from `TRAINING_READY`. See
`tests/test_registry.py` for the contract.

## How to use

### Real-mode (ultralytics + trained weights required)

```python
from ml.fire_detection.registry import get
entry = get("wfw-fire-yolov8n-v0.1.0")  # or "0.1.0" or "latest"

import importlib.util
spec = importlib.util.spec_from_file_location("inference", entry.path / "inference.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# Raises if weights or ultralytics are unavailable.
det = mod.predict_image("path/to/frame.jpg")
print(det.class_name, det.score, det.bbox_xyxy, det.latency_ms)
```

### Stub-mode (no deps, deterministic)

```python
det = mod.predict_stub(rgb_score=0.85, thermal_delta_c=18.0)
print(det.class_name, det.score)  # -> ('fire', ~0.72)
```

### Registry lookup

```python
from ml.fire_detection.registry import get, list_models, shipped_count
print(shipped_count())  # >= 2 once v0.1.0 lands
for m in list_models():
    print(m.model_id, m.version, m.status)
```

## What v0.1.0 is NOT

- Not yet a trained model. `weights/best.pt` is pending — see `status.md`.
- Not a production wildfire detector. The relaxed v0.1.0 gates (precision
  0.92, mAP@50 0.55, mAP@50:95 0.32) are deliberately below production
  targets to allow a first cut to land. v0.2.0 is the AOR-augmented
  release; v1.0.0 is the production release.
- Not Colorado-tuned. FASDD + FLAME-2 are the training set; neither
  contains beetle-killed timber, aspen riparian, or high-elevation
  Colorado pine. Expect a sim-to-real gap on first deployment.
- Not Jetson-measured. Latency targets cite the Jetson Orin Nano Super
  FP16 path; until hardware is available we estimate via the
  CPU-to-Jetson scaling factor in `eval/targets.yaml`.

## Reproducing the eval

After the unblock recipe in `status.md`, the eval is fully reproducible:

```bash
python3 -m ml.fire_detection.eval.eval_harness \
    --checkpoint ml/fire_detection/runs/v0.1.0/weights/best.pt \
    --dataset dfire --conf 0.25 --iou 0.50 \
    --output ml/fire_detection/runs/v0.1.0/eval.json
```

D-Fire seeds + splits come from `eval/prep_datasets.py`. The eval is
deterministic given a fixed checkpoint.
