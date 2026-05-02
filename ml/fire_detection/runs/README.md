# `runs/` — training and evaluation artifacts

This directory is **gitignored**, except for this README.

Contents (after a real training run):

```
runs/
  wildfire_yolo/
    weights/
      best.pt          # best validation mAP checkpoint
      best.engine      # TensorRT FP16 engine for Jetson
      last.pt
    results.csv        # per-epoch metrics
    args.yaml          # ultralytics-rendered training config
  eval/
    dfire_v0.1.0.json  # output of eval_harness.py
    dfire_v0.1.0.md    # markdown table for MODEL_CARD.md
```

Do not commit checkpoints or large eval JSONs into the repo. For reproducible
release artifacts, push them to:
- the wildfire-watch GitHub Releases page (small JSONs only), or
- a separate `wildfire-watch-eval` artifacts repo, or
- GCS bucket `gs://wildfire-watch-evidence/eval/<version>/`.

See `../RELEASE.md` for the release checklist.
