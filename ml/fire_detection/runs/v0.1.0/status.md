# `wfw-fire-yolov8n-v0.1.0` — Status: TRAINING_READY

> **Honest deferral.** This release is the recipe + harness + manifest +
> entrypoint, NOT a trained model. The blockers below are environmental
> (auth-walled datasets, missing ultralytics, no GPU/MPS in the agent
> sandbox) and are unblockable by the user with a few hours of work.

## Status legend

| State | Meaning |
|---|---|
| `RELEASED` | Trained weights present, eval JSON has measured metrics, latency benchmarked, archetype gate clear. Production-ready (within v0.1.0's relaxed gates). |
| `TRAINING_READY` | Manifest, training recipe, inference entrypoint, and status doc all in place. Eval JSON is a placeholder explicitly labelled `not_yet_trained`. Datasets and/or ultralytics may be missing. |
| `BLOCKED` | A dependency that no operator action can resolve has stopped progress (eg. dataset license withdrawn, paper retracted). Not the current state. |

This release is **TRAINING_READY** as of 2026-05-02.

## Why TRAINING_READY and not RELEASED

Three concrete blockers were verified during the dispatch:

1. **All three datasets require auth-walled manual download.**
   - **FASDD** (CC-BY-4.0, ~12 GiB CV+UAV subset) is hosted at the Science
     Data Bank: https://www.scidb.cn/en/detail?dataSetId=ce9c9400b44148e1b0a749f5c3eb0bda
     The DOI link 10.57760/sciencedb.j00104.00103 redirects to scidb.cn
     and requires a free account. No open mirror found on Hugging Face
     or Zenodo as of 2026-05-02 (verified via WebSearch).
   - **FLAME-2** (CC-BY-4.0, ~12 GiB) is on IEEE DataPort:
     https://ieee-dataport.org/open-access/flame-2-fire-detection-and-modeling-aerial-multi-spectral-image-dataset
     Requires a free IEEE DataPort account.
   - **D-Fire** (CC-BY-NC-4.0, ~3 GiB, eval-only) is mirrored on Kaggle
     (https://www.kaggle.com/datasets/sayedgamal99/smoke-fire-detection-yolo)
     and on the upstream GitHub repo's OneDrive links
     (https://github.com/gaia-solutions-on-demand/DFireDataset). Both
     paths require an interactive browser session.

2. **`ultralytics` and `torch` are not installed** in the host
   `/usr/local/bin/python3` environment. (Verified: `python3 -c
   "import ultralytics"` -> `ModuleNotFoundError`.)

3. **No GPU/MPS-enabled environment** is available to the agent for
   training. The right hardware exists in the household — the Windows
   machine at `100.71.10.48` (RTX 5070 Ti) and the Mac mini's MPS
   backend — but neither is reachable from inside this dispatch.

Per the task scope, the correct response when datasets aren't accessible
OR ultralytics can't install OR no GPU is available is to **document the
blocker honestly** and ship the **training-ready harness** instead. That
is what this directory is.

## What's shipped here vs. what's pending

| Artifact | Status | Notes |
|---|---|---|
| `manifest.json` | shipped | `status: "TRAINING_READY"`, points at recipe + entrypoint, declares `weights_status: "pending"`. Registry consumes it. |
| `eval.json` | shipped | Placeholder. `metrics: null`, `status: "not_yet_trained"`, with explicit unblock list. Registry consumes it. |
| `train_recipe.yaml` | shipped | End-to-end runnable recipe: pretrain on FASDD CV+UAV, fine-tune on FLAME-2, eval on D-Fire holdout. CLI invocations included. |
| `inference.py` | shipped | YOLOv8n entrypoint with lazy ultralytics import. Stub-mode fusion mirrors v0.0.1 so the simulator + registry tests stay deterministic. |
| `model_card.md` | shipped | Mitchell-format card with measured fields explicitly marked TBD. |
| `README.md` | shipped | What's-in-this-directory pointer doc. |
| `weights/best.pt` | **pending** | Produced by `train_recipe.yaml`. Gitignored. |
| Eval JSON measured metrics | **pending** | Will populate after training. |
| Latency JSON | **pending** | Will populate after training. |

## How to flip TRAINING_READY -> RELEASED

The shortest path (rough wall-clock estimates assume reliable network +
the existing Mac mini):

```bash
# 1. Install training deps (~10 minutes).
pip install ultralytics torch torchvision

# 2. Manual dataset download (~30-60 minutes incl. logins).
#    - Sign in to scidb.cn, accept FASDD CC-BY-4.0, download FASDD_CV.zip
#      and FASDD_UAV.zip into ~/wildfire-watch-data/fasdd/.
#    - Sign in to ieee-dataport.org, download the FLAME-2 labeled-frame
#      archives into ~/wildfire-watch-data/flame2/.
#    - Open https://github.com/gaia-solutions-on-demand/DFireDataset
#      and follow the OneDrive link into ~/wildfire-watch-data/dfire/.
#    - Re-run: python3 -m ml.fire_detection.eval.prep_datasets prep all

# 3. Train (~12 hours Mac MPS, or ~6 hours RTX 5070 Ti).
#    Recipe pulls hyperparams from ml/fire_detection/runs/v0.1.0/train_recipe.yaml.
python3 -m ml.fire_detection.train \
    --base yolov8n.pt \
    --data ml/fire_detection/runs/v0.1.0/data/fasdd_cv_uav.yaml \
    --epochs 10 \
    --imgsz 640 \
    --batch 16 \
    --device mps \
    --project ml/fire_detection/runs/v0.1.0/_pretrain \
    --name fasdd_cv_uav

python3 -m ml.fire_detection.train \
    --base ml/fire_detection/runs/v0.1.0/_pretrain/fasdd_cv_uav/weights/best.pt \
    --data ml/fire_detection/runs/v0.1.0/data/flame2.yaml \
    --epochs 5 \
    --imgsz 640 \
    --batch 16 \
    --device mps \
    --project ml/fire_detection/runs/v0.1.0/_finetune \
    --name flame2

# 4. Move weights into place.
cp ml/fire_detection/runs/v0.1.0/_finetune/flame2/weights/best.pt \
   ml/fire_detection/runs/v0.1.0/weights/best.pt

# 5. Eval (~5 minutes on Mac CPU).
python3 -m ml.fire_detection.eval.eval_harness \
    --checkpoint ml/fire_detection/runs/v0.1.0/weights/best.pt \
    --dataset dfire --conf 0.25 --iou 0.50 \
    --output ml/fire_detection/runs/v0.1.0/eval.json \
    --markdown ml/fire_detection/runs/v0.1.0/eval.md

# 6. Latency bench (~2 minutes on Mac CPU; estimates Jetson FP16 via scaling factor).
python3 -m ml.fire_detection.eval.latency_bench \
    --checkpoint ml/fire_detection/runs/v0.1.0/weights/best.pt \
    --imgsz 640 --batch 1 --warmup 5 --runs 100 \
    --output ml/fire_detection/runs/v0.1.0/latency.json

# 7. Verify gates clear, flip status, commit.
python3 - <<'PY'
import json
m = json.loads(open('ml/fire_detection/runs/v0.1.0/eval.json').read())['metrics']
assert m['precision_at_recall_0.80'] >= 0.92
assert m['map_50'] >= 0.55
assert m['map_50_95'] >= 0.32
print('READY for RELEASED')
PY

# 8. Edit manifest.json:  "status": "TRAINING_READY"  ->  "status": "RELEASED"
#    + bump released_at to the new timestamp.
```

## Honest brutal-truth section

A trained YOLOv8n on FASDD->FLAME-2 evaluated on D-Fire is a **research-grade
detector**, not a production wildfire monitoring system. The relaxed v0.1.0
gates (precision 0.92, mAP@50 0.55, mAP@50:95 0.32) are deliberately
permissive to allow a first cut to land. Production wildfire detection
needs:

1. **Colorado-AOR-specific training data** — beetle-killed timber, aspen
   riparian, and high-elevation montane pine are all underrepresented in
   FASDD/FLAME-2. The single biggest expected v0.1.0 -> v0.2.0 gap.
2. **Thermal-fusion at the model level**, not just at the post-processing
   gate. v0.1.0 is RGB-only.
3. **Multi-frame persistence baked into the architecture** (current
   approach: single-frame YOLO + persistence enforced in
   `infer.should_emit`). A video-level model would catch dawn/dusk
   plumes the single-frame head misses.
4. **Adversarial / domain-shift validation** — there is no test for
   smoke vs. wildfire-watch failure modes at low sun, high humidity, or
   in-cloud overhead light. v0.1.0's eval is purely D-Fire.

The right next milestone is `v0.2.0`: AOR-augmented, with at least 500
hand-labeled Colorado frames and a thermal-fusion head. Treat v0.1.0 as
the **load-bearing first version**, not the destination.
