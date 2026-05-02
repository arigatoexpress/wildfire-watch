# `eval/` — evaluation harness

Three CLIs and one config:

| File | Purpose |
|---|---|
| `prep_datasets.py` | Download + extract + verify FASDD, FLAME-2, D-Fire |
| `eval_harness.py` | Given a checkpoint + dataset, compute mAP, P, R, F1 |
| `latency_bench.py` | Measure CPU latency, estimate Jetson FP16 latency |
| `targets.yaml` | Performance targets + dataset URLs/sha256 |

## Quickstart — stub mode (no datasets, no GPU)

```bash
cd ~/Code/wildfire-watch
/usr/local/bin/python3 -m ml.fire_detection.eval.eval_harness \
    --checkpoint stub --dataset stub --limit 16

/usr/local/bin/python3 -m ml.fire_detection.eval.latency_bench \
    --checkpoint stub --runs 25
```

## Real eval (requires datasets prepared)

```bash
# 1. Prepare datasets (most need a manual download — the harness prints
#    actionable instructions and exits if they're missing).
python3 -m ml.fire_detection.eval.prep_datasets prep all

# 2. Run eval against the trained checkpoint on D-Fire.
python3 -m ml.fire_detection.eval.eval_harness \
    --checkpoint runs/wildfire_yolo/weights/best.pt \
    --dataset dfire \
    --output runs/eval/dfire_v0.1.0.json \
    --markdown runs/eval/dfire_v0.1.0.md

# 3. Bench Jetson-projected latency.
python3 -m ml.fire_detection.eval.latency_bench \
    --checkpoint runs/wildfire_yolo/weights/best.pt \
    --runs 100
```

## Tests

```bash
/usr/local/bin/python3 -m pytest ml/fire_detection/eval/tests/ -q
```

Tests run without `ultralytics`, `requests`, or `pyyaml` installed. They
exercise the pure-Python metric math against synthetic detections.
