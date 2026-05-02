# `checkpoints/` — pretrained weights cache

This directory is **gitignored**, except for this README.

Place pretrained YOLOv8 weights here for offline training:

```
checkpoints/
  yolov8n.pt       # 6.2 MB, Ultralytics base
  yolov8s.pt       # 21.5 MB, optional larger base
```

Download via the ultralytics CLI on first use, or curl from the official
GitHub release. We do not vendor weights into the repo because:

1. Binary blobs are a poor fit for git.
2. Ultralytics' weight licenses (AGPL-3.0 by default) interact awkwardly with
   the repo's own LICENSE — keep their bits out of our tree.

For Jetson exports, the produced `*.engine` files also live here (or under
`runs/wildfire_yolo/weights/`).
