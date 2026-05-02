# Model Card — `wfw-fire-yolov8n-v0.0.1`

Following the model-card framework introduced by Mitchell et al. 2019,
"Model Cards for Model Reporting" (https://arxiv.org/abs/1810.03993).

This card documents the **wildfire-watch fire/smoke detector**, the on-drone
inference head that emits `wildfire_signal` v1.0.0 records into the Sapphire
signal pipeline. The card will be revised at every minor release.

> **Status — v0.0.1 is a placeholder, not a trained model.** The current
> on-drone path runs the colour-heuristic stub in `infer.py`. Real model
> training is gated on dataset acquisition (see `DATASETS.md`). Until v0.1.0
> ships, the multimodal fusion gate caps `risk_score` at 60 and the
> `recommended_action` ladder is capped at `notify_operator`.

---

## 1. Model Details

- **Name:** `wfw-fire-yolov8n-v0.0.1`
- **Version:** `0.0.1` (pre-training placeholder; first real model = `v0.1.0`)
- **Owner:** wildfire-watch (Aristotle Ribs / `aristotlespec@gmail.com`)
- **Architecture:** YOLOv8n object detector, 3.2M parameters, 640x640 input.
  Two output classes: `fire`, `smoke`. Single-stage anchor-free detector with
  C2f backbone and decoupled detection head, as released by Ultralytics.
- **Framework:** Ultralytics YOLOv8 (PyTorch >= 2.1). Exported to TensorRT FP16
  for Jetson Orin Nano Super 8 GB inference at deployment.
- **Inputs:** RGB image, 8-bit, 3-channel, 640x640. (Thermal is consumed
  separately by the multimodal fusion gate in `infer.should_emit()`, not by
  the YOLO head.)
- **Outputs:** A list of detections `(class_id, confidence, xyxy_pixel_bbox)`.
- **License:** Code under repository LICENSE; weights AGPL-3.0 (inherited from
  Ultralytics). Inputs (datasets) carry their own licenses — see `DATASETS.md`.
- **Training data summary:** FASDD (pretrain) + FLAME-2 (fine-tune). Eval on
  D-Fire holdout. See `DATASETS.md`.
- **Cite:** v0.0.1 is unpublished. The detector design follows DSS-YOLO (2025),
  FASDD (Ren et al. 2024), and FLAME-2 (Hopkins et al. 2024). Citations in
  `DATASETS.md`.

## 2. Intended Use

### Primary use

Early-stage wildfire detection from a small UAS (DJI Mavic Mini 1/2 in Phase 0;
Holybro X500 V2 + Cube Orange+ + Jetson Orin Nano Super in Phase 1) flying
over the **Gunnison Valley + Crested Butte corridor, Gunnison County,
Colorado**, during fire season (June–September), at altitudes 50–120 m AGL,
in support of partner agencies CBFPD, GCFPD, Mt. Crested Butte FPD, and the
GMUG Gunnison Ranger District. See `AOR.md`.

The model emits a **bounding box + class + score** per frame. The detection
becomes a `wildfire_signal` only after the multimodal fusion gate in
`ml/fire_detection/infer.py::should_emit()` corroborates with thermal delta-T,
persistence, geofence compliance, and wind direction.

### Out-of-scope use — explicitly NOT a basis for

- **Fire suppression decisions.** The model is an early-warning trigger.
  Decisions to dispatch, ground crews, drop water, or commit aviation assets
  must be made by an Incident Commander (IC) in accordance with NIMS.
- **Evacuation orders.** Evacuations are a county sheriff / OEM responsibility.
  Operator-in-the-loop is mandatory before any external notification.
- **Wilderness flights.** West Elk, Maroon Bells–Snowmass, and Raggeds
  wilderness areas are hard no-fly under 36 CFR 261.16. Model invocation
  inside a wilderness exclusion polygon is a programmatic bug, not an
  operational case.
- **Controlled-burn discrimination without an allow-list.** Where the USFS
  GMUG district has an active prescribed burn, the operator must add an
  explicit allow-list entry; otherwise the model will (correctly) flag it.
- **Smoke-source disambiguation in WUI.** Campground fires, BBQs, chimneys,
  and slash-pile burns are out of scope.
- **Wildlife or human identification.** The wildlife head (MegaDetector v6)
  lives in a separate model and is not covered by this card.

### Users

- **Volunteer drone pilots** (RPIC certified Part 107) running scout flights
  in the AOR.
- **Partner fire department dispatchers** consuming alerts via Sapphire's
  hermes Telegram bot or the TAK/CoT bridge into ATAK / Lattice / Apollo.
- **Wildfire-watch maintainers** auditing model performance and dataset bias.

The model is **not directly invokable** by the public; signals route through
the operator-in-the-loop ground station before any external notification.

## 3. Factors

Variation expected to affect model behaviour, listed in approximate order of
impact:

| Factor | Range observed in AOR | Why it matters |
|---|---|---|
| Time of day | Civil dawn → 30 min before sunset | Smoke contrast inverts with low-sun angles; rim-lit plumes are easy to miss |
| Season | Late June – mid September primary | Spring red-flag (Apr–Jun) is a secondary window; winter ops are non-existent |
| Altitude AGL | 50–120 m typical | Smaller plumes occupy fewer pixels at higher altitudes; mAP drops on small targets |
| Camera angle | Nadir vs oblique (15–30°) | FLAME-2 is mostly oblique; FASDD has both; oblique exposes the plume's vertical extent which helps recall |
| Terrain | Montane forest, beetle-killed timber, riparian, sage, WUI | Beetle-kill (gray dead crowns) confuses the smoke class — high false-positive risk |
| Confounders | Cloud shadow, dust devils, USFS prescribed burns, controlled slash burns, woodsmoke from cabins | All produce smoke-like signatures; mitigated by geofence + persistence + thermal corroboration in `should_emit` |
| Weather | RH 15–60%, wind 5–35 kt, ambient 10–30°C in season | Jetson thermal-throttling above 30°C ambient inside the airframe pod |
| Sensor | DJI Mavic Mini RGB (Phase 0) → Arducam IMX477 (Phase 1) | Different colour science and lens fields — DJI tends to over-saturate orange |

## 4. Metrics

### Primary

- **Precision @ recall=0.80** — the operationally useful number. Catching
  ≥80% of real fires while suppressing the false-positive flood that wastes
  fire-department dispatch time. Target: **>= 0.95**.

### Secondary

- **mAP@50** — VOC-style mean average precision at IoU=0.50.
- **mAP@50:95** — COCO-style mean over IoU thresholds 0.50:0.05:0.95.
- **Per-class precision/recall** for `fire` and `smoke` separately. Smoke
  recall is the harder problem and the more operationally valuable.

### Latency (deployment)

- **p50 / p95 / p99 inference latency** at 640x640, batch=1, on:
  - Mac mini CPU (developer reference; not a deployment target).
  - Jetson Orin Nano Super 8 GB FP16 TensorRT (the deployment target).
  - Target: **p95 <= 25 ms** (= 40 FPS minimum).

### Operational (system, not model-internal)

- **Δ-detection-time vs. ALERTColorado / NIFC visual-spotter baseline** —
  the seconds wildfire-watch beats the closest production analog (PTZ camera
  spotter network) on a matched ignition. Target: **detect ≥ 120 s earlier**.

## 5. Evaluation Data

- **D-Fire** (CC-BY-NC-4.0) — primary holdout. 21,527 images, mixed indoor +
  outdoor, fire and smoke labels with bounding boxes. Used **only** for eval;
  not seen during pretrain or fine-tune. See `DATASETS.md`.
- **wildfire-watch-internal hand-labeled set** (TBD) — 5,000+ frames captured
  over the Gunnison-Crested Butte AOR by the volunteer pilot network.
  Eventually the most important eval set because it is in-distribution. As of
  v0.0.1 this set is **TBD: zero frames collected**.

### Known biases of the eval data

- D-Fire is heavily biased toward indoor and structure fires; only a subset of
  it resembles wildland-urban interface fires.
- D-Fire camera angles are mostly ground-level, not aerial.
- Class imbalance: D-Fire has more smoke than fire boxes.
- FLAME-2 (the fine-tune set we eval on as a sanity check) is captured at
  Northern Arizona pine forest in 2021. **It is not representative of
  Colorado beetle-kill stands or aspen riparian.** Expect a sim-to-real
  performance gap when first deploying in the AOR — Colorado-specific
  augmentation is on the roadmap before v0.2.0.

## 6. Training Data

- **FASDD** (CC-BY-4.0) — pretrain. ~120,000 images across CV / UAV / RS
  sub-datasets. We use FASDD_CV for general fire/smoke priors and FASDD_UAV
  to bias toward aerial viewpoints.
- **FLAME-2** (CC-BY-4.0) — fine-tune. Northern Arizona prescribed-burn 2021,
  RGB + IR pairs, frame-level fire/smoke labels.

See `DATASETS.md` for sources, paper citations, license details, and download
recipe.

### Training data limitations

- FASDD_RS contains satellite imagery — we deliberately exclude it from the
  pretrain mix because the spatial scale mismatch hurts more than it helps.
- FLAME-2 is a single ecosystem (ponderosa pine, Northern Arizona). The bias
  this introduces is the primary justification for collecting Colorado
  imagery before v0.2.0.
- Neither dataset has nighttime imagery; the model is not validated for
  night ops.

## 7. Quantitative Analyses

The numbers below are targets, not measurements. v0.0.1 has no measured
metrics because no model was trained — this card pins the bar for v0.1.0
to clear.

| Metric                              | Target | v0.0.1 (placeholder) | v0.1.0 (target) |
|---|---|---|---|
| precision @ recall=0.80             | >= 0.95 | TBD | >= 0.92 |
| mAP@50                              | >= 0.65 | TBD | >= 0.55 |
| mAP@50:95                           | >= 0.40 | TBD | >= 0.32 |
| latency p95 (Mac CPU, 640x640)      | n/a    | TBD | n/a |
| latency p95 (Jetson Orin Super FP16)| <= 25 ms | TBD | <= 30 ms |
| throughput (Jetson Orin Super FP16) | >= 60 FPS | TBD | >= 45 FPS |

The v0.1.0 column intentionally relaxes the targets — the precision target
drops 0.95 → 0.92 because the very first trained model is not expected to
clear the production bar without a Colorado-augmented training set. v0.2.0
is the production-target release.

## 8. Ethical Considerations

- **Wildfire false positives waste fire-department resources** — every spurious
  page costs a unit dispatch. The fusion gate (`should_emit`) is intentionally
  conservative; we accept lower recall in exchange for higher precision.
- **Wildfire false negatives kill people.** The model is one input among many
  in the alerting stack. It does not replace human spotters, lookout towers,
  or the ALERTColorado camera network. Operator-in-the-loop is mandatory.
- **Operator-in-the-loop is mandatory** for `recommended_action` >=
  `notify_fire_dept`. The drone may emit `notify_operator` or
  `loiter_and_capture` autonomously, but external pages require a human.
- **Controlled-burn allow-list** — the model will (correctly) flag smoke
  during USFS prescribed burns. Operators MUST coordinate with the GMUG
  Gunnison Ranger District and add allow-list entries for active burns;
  otherwise the model produces predictable, avoidable false alarms.
- **Privacy** — the model is trained for fire/smoke detection. No
  identifiable images of human subjects are collected, retained, or
  re-shared. Any frame containing recognizable people is deleted at the
  ground station before retraining ingest. Camera-trap-style wildlife frames
  flow through MegaDetector v6, governed by a separate model card.
- **Geofence + Wilderness compliance** — flights within the West Elk,
  Maroon Bells–Snowmass, or Raggeds wilderness exclusion polygons are
  prohibited regardless of detection state. The mission planner enforces
  this; the model is not the appropriate place to fix policy violations.
- **Civilian-only.** The wildfire-watch project is explicitly civilian.
  Defense-adjacent applications would require separate counsel and a
  separate organizational entity.

## 9. Caveats and Recommendations

- **v0.0.1 is the colour-heuristic placeholder in `infer.py`.** Treat its
  output as approximate. Real metrics arrive with v0.1.0.
- **The fusion gate is the safety net.** Even when the YOLO head fires, the
  `should_emit` AND-gate (RGB score >= threshold AND thermal delta >= 5°C
  AND persistence >= 5 frames AND geofence OK AND wind consistent) prevents
  most spurious emits. Do not relax the fusion gate to chase recall.
- **Beetle-killed timber is the dominant Colorado false-positive risk.** Gray
  dead crowns share visual statistics with smoke at low sun. Training data
  collected post-2024 should oversample beetle-kill stands.
- **Ground-truth from controlled burns** is the cheapest training-data
  win. CAL FIRE archive video and USFS GMUG prescribed-burn video are
  CC0/PD; harvest them.
- **Sim-to-real gap is real.** Until we have hand-labeled AOR imagery, expect
  a 5–10 point precision drop when first deploying in Gunnison County.
- **Re-evaluate every release.** Before tagging any `wfw-fire-yolov8n-v*`,
  run the eval harness against `dfire` and the (eventually) AOR-internal
  set; regenerate this card's quantitative table.

## 10. Provenance

- **Repository:** `wildfire-watch`, branch `main`.
- **Card author:** wildfire-watch maintainer team.
- **Card date:** 2026-05-01.
- **Reproducibility:**
  - `train.py` is the training entrypoint.
  - `eval/eval_harness.py` is the evaluation harness.
  - `eval/latency_bench.py` is the latency benchmark.
  - `eval/targets.yaml` pins the performance targets.
  - `RELEASE.md` documents the cut-a-release workflow.
- **Schema integration:** Detections produced by this model are wrapped into
  `wildfire_signal` v1.0.0 records (`sapphire_integration/wildfire_signal_schema.json`)
  by `infer.build_signal()`. Bumping the model version requires bumping the
  `evidence.model_versions.fire_yolo` field in emitted signals.

---

## References

- Mitchell, M. et al. 2019. **Model Cards for Model Reporting.** *FAT*. https://arxiv.org/abs/1810.03993
- Ren, M. et al. 2024. **An open flame and smoke detection dataset for deep learning in remote sensing based fire detection.** *Geo-spatial Information Science.* https://www.tandfonline.com/doi/full/10.1080/10095020.2024.2347922
- Hopkins, B. et al. 2024. **FLAME 2: Fire detection and modeLing — Aerial Multi-spectral imagE dataset.** IEEE DataPort. https://ieee-dataport.org/open-access/flame-2-fire-detection-and-modeling-aerial-multi-spectral-image-dataset
- Venâncio, P. V. A. B. de et al. 2022. **An automatic fire detection system based on deep convolutional neural networks for low-power, resource-constrained devices.** *Neural Computing and Applications.* https://github.com/gaia-solutions-on-demand/DFireDataset
- Ultralytics YOLOv8 — https://github.com/ultralytics/ultralytics
- See also: `docs/30-ml-stack.md`, `docs/intel/SYNTHESIS-2026-05-01.md`.
