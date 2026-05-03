# synth — procedural fire/smoke synthetic-data pipeline

A deterministic, reproducible generator for YOLO-format fire/smoke training
data. Composes Perlin-noise smoke plumes, radial fire glow, and false-colour
thermal anomalies onto the 12 federal-public-domain backdrop images already
checked in at `eval/real_bench/images/`.

This package exists so v0.1.0 has a defensible "we have training data" claim
**before** the auth-walled FASDD / FLAME-2 / D-Fire archives land. The
synthetic dataset is intentionally not a substitute for those — see DATASETS.md
for the production-grade plan.

## Quickstart

```bash
cd ~/Code/wildfire-watch
/usr/local/bin/python3 -m ml.fire_detection.synth.cli preview \
    --output /tmp/synth_preview.png

/usr/local/bin/python3 -m ml.fire_detection.synth.cli generate \
    --output ~/wildfire-watch-data/synth-v0/ \
    --n-train 200 --n-val 50 --n-test 50

/usr/local/bin/python3 -m ml.fire_detection.synth.cli stats \
    ~/wildfire-watch-data/synth-v0/
```

## Output structure

```
output_dir/
+-- data.yaml              # ultralytics-compatible
+-- images/{train,val,test}/
+-- labels/{train,val,test}/
+-- manifest.json          # provenance: seed, generator version, backdrops
```

## Composition

Each split is class-balanced to:

- 30% fire-only
- 30% smoke-only
- 20% both
- 20% negative (no labels)

YOLO labels: `class_id x_center y_center width height` with all coords
normalized to `[0, 1]`. `class_id` is `0=fire`, `1=smoke`.

## Constraints

- Lazy-imports only — tests run without PIL/numpy/torch installed.
- No emoji.
- Output dataset directory lives under `~/wildfire-watch-data/`, NOT in the
  repo.
- Backdrop attribution comes from `eval/real_bench/images/README.md`. We never
  invent a citation.

## Train against this dataset

After generation, the standard ultralytics command:

```bash
yolo detect train data=~/wildfire-watch-data/synth-v0/data.yaml \
                  model=yolov8n.pt epochs=5 imgsz=640 batch=8 device=cpu
```

This will produce a checkpoint that has *learned the procedural distribution*
— do not interpret its mAP as representative of real wildfire-detection
performance. Use the `eval/real_bench/` images as a sanity-check after training.

## Caveats — read these

1. The procedural smoke does not model atmospheric Mie scattering. Models
   trained on it will overfit to Perlin-noise statistics.
2. The fire glow is a radial palette, not a fluid-dynamic flame. Scale, hue
   variation, and ember dynamics are absent.
3. The thermal-anomaly synthesizer is a magma-ramp stand-in for a real FLIR
   Lepton frame. It is NOT a Black-body curve.
4. Augmentation perspective-warp does not propagate through to the bounding
   boxes (we keep the pre-warp box and clip to image bounds). This introduces
   label noise at high `aug_level`. Mirrors how FASDD handles weak-box train.
5. Negative samples are intentionally augmented just like positives so the
   model cannot trivially distinguish "I was augmented therefore I contain
   fire".

When real datasets land, retire this generator from the training mix and
demote it to a regression-test asset.
