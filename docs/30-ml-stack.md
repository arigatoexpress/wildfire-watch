# ML Stack

## TL;DR

- **Fire/smoke head**: YOLOv8n (3.2 M params), fine-tuned on FASDD + D-Fire +
  FLAME-2, exported to TensorRT FP16, target ~120 FPS at 640×640 on Orin Nano Super.
- **Wildlife head**: MegaDetector v6 Compact (MDV6-yolov10-c), <2% of MDV5
  parameter size with better recall, exported to ONNX → TensorRT, runs at 30 FPS
  on a separate stream.
- **Audio (perch / hover-only)**: BirdNET-Analyzer running on Jetson CPU at 1 Hz
  windowed over 3-second mic frames. ~3000 species, useful for ecology side-channel.
- **Anomaly head (cheap)**: ResNet-18 classifier head trained on "normal patrol"
  vs. "anomalous" frames (smoke being one anomaly, but also: fallen tree, flooding,
  unusual human activity). Late-fusion gate before signal emit.
- **Training compute**: User's RTX 5070 Ti (16 GB VRAM) + Windows PC (`100.71.10.48`).
  Full retrain of YOLOv8n on FASDD ~6 h. MegaDetector v6 we don't retrain — just
  fine-tune the classifier head if needed.

## Why these models (2026)

State-of-the-art in 2026 wildfire-CV is converging on **YOLOv8/v11 lightweight
variants with multimodal fusion (RGB + thermal + temporal)**:

- DSS-YOLO (2025) — improved YOLOv8, real-time, lightweight, designed for fire.
  mAP@0.5 on FASDD ~92.6%, precision 83.7%, recall 95.2%.
- FASDD (2024) — 120k+ images across `_CV` / `_UAV` / `_RS` sub-datasets, the
  current go-to dataset.
- FLAME / FLAME-2 — Northern Arizona drone-captured fire imagery, regular +
  thermal, 4 color palettes (fusion / regular / green-hot / white-hot).
- D-Fire — 21k images, fire / smoke / no-fire, well-curated, easy starter.

We pretrain on FASDD, fine-tune on FLAME-2 (UAV-specific) for our flight profile,
and hold out a custom zone-specific eval set we collect ourselves.

## Datasets

| Name | Size | License | Use |
|---|---:|---|---|
| FASDD (Flame and Smoke Detection Dataset) | 120k images, 3 sub-sets | CC-BY-4.0 | Pretrain |
| FLAME / FLAME-2 | 50k+ images + videos, RGB + thermal | CC-BY-4.0 | Fine-tune for UAV viewpoint |
| D-Fire | 21k images | CC-BY-NC-4.0 | Eval, validation |
| Custom zone set (TBD) | 5k+ images we collect | — | Held-out eval |
| LILA BC (camera trap collection) | millions of images | varies | MegaDetector context, wildlife |
| BirdNET reference | global eBird-derived | CC-BY-NC-SA | Audio classification |

## Training plan

### Phase 1 — pretrain fire head on FASDD (week 1)

```bash
cd ml/fire_detection
python train.py \
  --base yolov8n.pt \
  --data fasdd_cv.yaml \
  --epochs 100 \
  --imgsz 640 \
  --batch 32 \
  --device cuda:0          # 5070 Ti
```

Compute: ~6 h. Target: mAP@0.5 ≥ 0.85 on FASDD val, ≥ 0.80 on D-Fire as zero-shot
sanity check.

### Phase 2 — fine-tune on FLAME-2 (week 2)

Same script, lower LR, freeze backbone for first 20 epochs.

### Phase 3 — collect custom zone footage (weeks 3–4)

Fly the MVP drone over the chosen zone in normal conditions. Hand-label any
controlled-burn footage from CAL FIRE archive (public). Augment with synthetic
smoke (Stable Diffusion conditioned on real smoke) — 2025–2026 papers show
synthetic augmentation lifts mAP 3–5 pts on rare-class recall.

### Phase 4 — TensorRT export + on-edge benchmark

```bash
python -m ultralytics.export \
  --weights runs/train/exp/weights/best.pt \
  --include engine \
  --device cuda:0 \
  --half             # FP16
```

Deploy to Jetson. Target: 100+ FPS at 640×640.

## Model card outline (per-head)

Each head ships a model card in `ml/fire_detection/MODEL_CARD.md` and
`ml/wildlife_id/MODEL_CARD.md`:

- Intended use, out-of-scope use
- Training data sources, license, statistics
- Evaluation metrics on held-out set + per-class breakdown
- Known failure modes (e.g. fog ↔ smoke confusion, dust devils, sun glare)
- Bias considerations (geography, season, time-of-day)
- Update cadence and provenance hash

## Multimodal fusion

The signal-emit gate is **not** the YOLO score alone. It is:

```
fire_signal = (
  rgb_yolo_smoke_score >= 0.6
  AND thermal_delta_T >= 5 °C above local median
  AND persistent across N >= 5 frames
  AND not in geofenced "known smoke source" (campground, BBQ, smokestack)
  AND wind_direction_consistent (smoke plume direction matches NOAA local wind)
)
```

This is intentionally conservative — false positives are expensive
(unnecessary dispatch), false negatives during a real fire are catastrophic but
very unlikely once the plume reaches detectable size. We accept slightly lower
recall in exchange for ≥0.95 precision on edge-emitted signals.

## Wildlife head (MegaDetector v6)

We use **MDV6-yolov10-c** (Compact) because it's 2% the parameter size of MDV5
with 4% better animal recall, runs at 30+ FPS on Orin Nano. Output: bounding
boxes + class (animal / person / vehicle), no species ID at this stage. Species
ID is a downstream cloud step using PyTorch-Wildlife's classification heads
(SpeciesNet) on flagged frames.

## Audio head (BirdNET)

Only runs when drone is in **perch mode** (landed on a survey perch) or **hover
mode** at <2 m/s, both because rotor noise dominates at flight speed. Captures
3-second windows at 48 kHz mono, runs BirdNET-Analyzer on Jetson CPU
(GPU dedicated to vision). Output: species + confidence per window.

## Continuous improvement loop

Every flight uploads:
- `signal_*.jsonl` — every frame's top-K detections
- `evidence_*.tar.zst` — frames around any emitted signal (10 s before + 30 s after)
- `flight_*.bin` — ArduPilot DataFlash log

Nightly retraining cron on Windows PC:
1. Pull new evidence from GCS
2. Auto-label using current model + manual triage queue (operator clicks
   yes/no/relabel in dashboard)
3. Retrain head if labeled queue has ≥500 new samples since last retrain
4. Push new TRT engine to drones via OTA update channel (Tailscale + signed payload)

## Open research questions

- **Smoke-vs-fog**: still the hardest false positive. Polarization sensors
  separate them but add weight + cost. We're not solving this yet — geofencing
  helps (don't trigger over known fog basins in mornings).
- **Pre-ignition heat**: Lepton 3.5 has 50 mK NETD. Fire-prone fuels can be
  identified by anomalous warming hours before ignition (per Stanford 2024
  paper on heat-anomaly precursors). Phase-3 model — needs longitudinal data.
- **Multi-drone consensus**: a 3-drone cell over a zone could vote on
  detection. Reduces false positives below single-drone floor. Phase-2.
