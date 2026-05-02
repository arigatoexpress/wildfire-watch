# Model Card - `wfw-fire-yolov8n-v0.1.0`

Following the model-card framework introduced by Mitchell et al. 2019,
"Model Cards for Model Reporting" (https://arxiv.org/abs/1810.03993).

This is the **per-version** model card for the wildfire-watch v0.1.0
release. The repo-level `ml/fire_detection/MODEL_CARD.md` documents the
model line as a whole; this file pins the v0.1.0 column.

> **v0.1.0 is the first trained-architecture version of the wildfire-watch
> fire/smoke detector.** Status: **TRAINING_READY**. The recipe + harness +
> manifest + inference entrypoint are shipped; the trained `weights/best.pt`
> is pending dataset access + ultralytics installation. Measured metrics
> arrive as soon as the recipe runs end-to-end on the unblocked
> environment. See `status.md` for the unblock checklist.

---

## 1. Model Details

- **Name:** `wfw-fire-yolov8n-v0.1.0`
- **Version:** `0.1.0`
- **Status:** `TRAINING_READY` (manifest + recipe + entrypoint shipped;
  weights pending — see `manifest.json["weights_blocker"]`).
- **Owner:** wildfire-watch (Aristotle Ribs / `aristotlespec@gmail.com`)
- **Architecture:** Ultralytics YOLOv8n object detector. 3.2 M parameters,
  640x640 input. C2f backbone, decoupled detection head, anchor-free.
  Two output classes: `fire` (cls 0), `smoke` (cls 1).
- **Framework:** Ultralytics YOLOv8 >= 8.3 + PyTorch >= 2.1. Trained on
  Mac MPS or CUDA. Exported to TensorRT FP16 for Jetson Orin Nano Super
  deployment (Phase 1).
- **Inputs:** RGB image, 8-bit, 3-channel, 640x640. Stub-mode also accepts
  pre-computed `(rgb_score, thermal_delta_c)` scalars for the simulator
  + registry tests.
- **Outputs:** A `Detection(score, class_name, bbox_xyxy, latency_ms)`
  dataclass mirroring v0.0.1's contract — call-sites composing against
  the registry don't need to special-case versions.
- **License:** AGPL-3.0 (inherited from Ultralytics YOLOv8 base weights).
  Trained-weight redistribution must respect the base-weight license.
  Inputs (datasets) carry their own licenses — see `../../DATASETS.md`
  and `manifest.json["license_note"]`.
- **Training data summary:** FASDD CV + UAV (pretrain, CC-BY-4.0) ->
  FLAME-2 (fine-tune, CC-BY-4.0). FASDD_RS satellite imagery is excluded.
- **Eval data summary:** D-Fire (CC-BY-NC-4.0, eval-only holdout) plus
  the synthetic-100 plane v0.0.1 used (sanity baseline).
- **Cite:** v0.1.0 is unpublished. Architecture from Ultralytics YOLOv8;
  recipe lineage from FASDD (Ren et al. 2024), FLAME-2 (Hopkins et al.
  2024), and D-Fire (Venâncio et al. 2022). Citations in
  `../../DATASETS.md`.

## 2. Intended Use

### Primary use

- **On-drone / post-flight fire and smoke detection** in Phase 0 (Mavic
  Mini SD-card replay) and Phase 1 (live IMX477 + Jetson Orin Nano
  Super) operations over the Gunnison Valley + Crested Butte corridor.
- **Drop-in replacement for the v0.0.1 colour heuristic** at every
  call-site that composes against the model registry. Same Detection
  contract, same fusion-gate composition (`infer.should_emit`).
- **Eval baseline for v0.2.0.** v0.2.0 (the AOR-augmented release) must
  beat v0.1.0's measured D-Fire numbers on the same plane to qualify.

### Out-of-scope use - explicitly NOT a basis for

Same out-of-scope set as the parent `MODEL_CARD.md`:

- Fire suppression decisions, evacuation orders, wilderness flights
  (West Elk / Maroon Bells–Snowmass / Raggeds — hard no-fly per
  36 CFR 261.16), controlled-burn discrimination without an allow-list,
  smoke-source disambiguation in WUI, wildlife or human identification.

Additionally for v0.1.0 specifically:

- **Do NOT deploy v0.1.0 standalone in Colorado.** FASDD + FLAME-2 are
  trained on imagery that is not representative of beetle-killed
  timber, aspen riparian, or high-elevation montane pine. Expect a
  5-10 point precision drop on AOR imagery; mitigated by the fusion
  gate and operator-in-the-loop. v0.2.0 is the AOR-augmented release.
- **Do NOT cite v0.1.0 metrics as production-ready.** v0.1.0's targets
  are deliberately relaxed (precision 0.92 vs production 0.95; mAP@50
  0.55 vs 0.65; mAP@50:95 0.32 vs 0.40). Production gates apply at
  v1.0.0.
- **Do NOT use v0.1.0 in stub-mode for anything but tests + simulation.**
  The fusion arithmetic in `predict_stub` mirrors v0.0.1; it is not the
  YOLO head. Real-mode (`predict_image`) is the only YOLO path.

### Users

- **Volunteer drone pilots** (RPIC certified Part 107) running scout
  flights in the AOR.
- **Partner fire department dispatchers** consuming alerts via Sapphire's
  hermes Telegram bot or the TAK/CoT bridge into ATAK / Lattice / Apollo.
- **Wildfire-watch maintainers** auditing model performance and
  dataset bias.

The model is **not directly invokable** by the public; signals route
through the operator-in-the-loop ground station before any external
notification.

## 3. Factors

Same factor table as the parent card. v0.1.0 specifically is most
sensitive to:

| Factor | v0.1.0 sensitivity |
|---|---|
| Beetle-killed timber | High false-positive risk; absent from FASDD + FLAME-2. |
| Aspen riparian | Moderate false-positive risk; light-on-light-on-grey patterns. |
| Camera angle | FLAME-2 is mostly nadir/low-oblique; recall on near-vertical plumes is the well-trained case. |
| Smoke at low sun | Reduced recall — back-lit plumes lose channel-spread structure. FASDD partially covers this. |
| Image compression | YOLO is more compression-robust than v0.0.1's heuristic, but JPEG quality < 60 still degrades mAP visibly. |
| FLAME-2 single ecosystem | Ponderosa pine / NAU 2021. Domain shift is the primary v0.2.0 motivation. |

## 4. Metrics

Same metric definitions as the parent card. v0.1.0 reports:

- **Precision @ recall=0.80** on D-Fire holdout — the operationally useful
  number. Target: **>= 0.92** (relaxed first-cut; production = 0.95).
- **mAP@50 / mAP@50:95** on D-Fire holdout. Targets: **>= 0.55 / >= 0.32**.
- **Per-class precision/recall** for fire and smoke separately.
- **Latency p50 / p95 / p99** at 640x640, batch=1, on:
  - Mac mini CPU (developer reference).
  - Jetson Orin Nano Super 8 GB FP16 TensorRT (deployment target;
    measured directly when hardware available, otherwise estimated via
    `eval/targets.yaml::cpu_to_jetson_fp16_speedup_factor = 4.5`).
  Target: Jetson p95 **<= 30 ms** (relaxed from production 25 ms).

## 5. Evaluation Data

Same as parent card. v0.1.0 evaluates on:

- **D-Fire holdout** — 21,527 images, mixed indoor + outdoor, fire and
  smoke labels with bounding boxes. CC-BY-NC-4.0; eval-only.
- **Synthetic-100 sanity plane** (v0.0.1's eval set) — kept as a
  cross-version sanity check that the YOLO output is not pathologically
  worse than the heuristic on the simple fusion-gate decision surface.

### Holdout protocol

D-Fire is **never seen during training**. Bootstrap CIs over 1000
resamples for precision and recall. Conf threshold defaults to 0.25;
IoU defaults to 0.50; max detections per image = 300. See
`eval/targets.yaml` for the canonical defaults.

## 6. Training Data

- **FASDD CV + UAV** (CC-BY-4.0) — pretrain. ~120 k images across CV
  (ground-based) and UAV (aerial) sub-datasets. Used jointly to bias
  toward aerial viewpoints. FASDD_RS (satellite) is **excluded** —
  spatial-scale mismatch hurts.
- **FLAME-2** (CC-BY-4.0) — fine-tune. ~50 k labeled RGB+IR frame pairs
  from a Northern Arizona prescribed burn (2021). Frame-level fire/smoke
  labels; we generate weak boxes via brightest-contiguous-region for
  fine-tune.

The strictest training license is CC-BY-4.0; trained weights are
distributable. D-Fire (CC-BY-NC-4.0) is held out for eval and never
encumbers the trained weights. See `../../DATASETS.md`.

### Training data limitations

- **Single ecosystem fine-tune.** FLAME-2 is ponderosa pine, ~7000 ft
  elevation, single fire. The Gunnison AOR's beetle-killed timber,
  aspen, and sage are absent. **This is the primary domain shift we
  worry about.**
- **No nighttime imagery** in either dataset. Model is not validated
  for night ops.
- **Single time-of-day** in FLAME-2; daylight-bias in FASDD.

## 7. Quantitative Analyses

### Measured (v0.1.0, this card) — pending training run

| Metric                              | Target  | v0.1.0 measured |
|---|---|---|
| precision @ recall=0.80 (D-Fire)    | >= 0.92 | **TBD (TRAINING_READY)** |
| mAP@50 (D-Fire)                     | >= 0.55 | **TBD (TRAINING_READY)** |
| mAP@50:95 (D-Fire)                  | >= 0.32 | **TBD (TRAINING_READY)** |
| latency p95 (Mac CPU, 640x640)      | n/a     | **TBD** (will measure via `eval/latency_bench.py`) |
| latency p95 (Jetson Orin Super FP16)| <= 30 ms| **TBD** (estimate via cpu_to_jetson_fp16_speedup_factor = 4.5) |
| throughput (Jetson Orin Super FP16) | >= 45 FPS | **TBD** |

These cells WILL populate via the eval harness the moment the unblock
recipe in `status.md` runs end-to-end. We deliberately leave them TBD
rather than pre-populating with synthetic numbers — fake metrics are
exactly the gaming-the-metric anti-pattern this release is designed to
avoid.

### v0.0.1 baseline (for reference)

| Metric (v0.0.1)                   | Value |
|---|---|
| synthetic precision @ recall=0.80 | 0.8246 |
| synthetic precision               | 0.8214 |
| synthetic recall                  | 0.9787 |
| Mac CPU p95                       | 39.77 ms |

v0.1.0 must materially clear v0.0.1 on D-Fire (the synthetic floor is
not directly comparable but is the cheapest sanity baseline). v0.1.0's
target of 0.92 precision-at-recall-0.80 requires beating v0.0.1's
synthetic-precision-at-recall-0.80 floor of 0.82 on real D-Fire imagery.

## 8. Ethical Considerations

Same as the parent card. For v0.1.0 specifically:

- **The fusion gate is still mandatory.** YOLO precision on D-Fire is
  not predictive of AOR precision (FASDD + FLAME-2 != Colorado). Until
  v0.2.0 lands, treat v0.1.0 as the on-drone first pass and
  `infer.should_emit` as the safety net.
- **Bias from FLAME-2 is structural.** A single-ecosystem fine-tune
  will not generalize to beetle-kill stands or aspen. Operators must
  not assume v0.1.0's measured precision applies to AOR conditions.
- **License rigor.** D-Fire (CC-BY-NC-4.0) is eval-only. Training on
  D-Fire would encumber the weights with a non-commercial restriction
  and would invalidate downstream commercial use. The eval harness
  reads D-Fire only via `eval/prep_datasets.py` with `role:
  holdout_eval`.
- **Reproducibility.** The recipe at `train_recipe.yaml` pins all
  hyperparams, dataset splits, and seeds. The eval harness is
  deterministic given a fixed checkpoint.

## 9. Caveats and Recommendations

- **TRAINING_READY != RELEASED.** This card pins the bar v0.1.0
  must clear; until the trained weights land, the measured-metrics
  cells stay TBD. Do not paraphrase TRAINING_READY as "shipped" in
  external comms.
- **No bbox eval until trained.** mAP@50 / mAP@50:95 require the
  trained YOLO head; the v0.0.1 heuristic's region masks aren't
  directly comparable.
- **Calibrate on AOR data before any real deployment.** The
  ponderosa-pine fine-tune does not reflect Gunnison Valley beetle-kill
  stands. Phase 0 post-flight footage from the AOR is the cheapest
  re-tuning input.
- **Re-evaluate every release.** Before flipping `manifest.json` from
  `TRAINING_READY` to `RELEASED`, re-run the eval harness, regenerate
  this file's quantitative tables, and update Section 10 (Provenance).
- **Same-as-parent caveat:** before tagging any new wfw-fire-* version,
  re-run the eval harness and regenerate this file.

## 10. Provenance

- **Repository:** `wildfire-watch`, branch `main`.
- **Released by:** wildfire-watch maintainer team.
- **Released at:** 2026-05-02T13:50:20Z (UTC).
- **code_sha at release:** `d31c4430d3743f4bf715d1e9d9486c1cabb68616`
  (see `manifest.json`).
- **Reproducibility:**
  - `inference.py` (this directory) is the entry point.
  - `train_recipe.yaml` (this directory) pins all hyperparams + CLI
    invocations.
  - `eval.json` (this directory) is the raw eval output (currently
    `metrics: null`, `status: "not_yet_trained"`).
  - `manifest.json` (this directory) carries the provenance fields the
    registry consumes plus the new `status` field.
  - `eval/eval_harness.py` and `eval/latency_bench.py` (parent eval/
    dir) are the harness machinery.
  - `eval/targets.yaml` (parent eval/ dir) pins the performance targets
    + dataset URLs + sha256 placeholders.
- **Schema integration:** Detections from this model wrap into
  `wildfire_signal` v1.0.0 records by `infer.build_signal()`. The
  `evidence.model_outputs` envelope cites `wfw-fire-yolov8n-v0.1.0`
  via the registry. While `weights_status: "pending"`, downstream
  callers must check `weights_available()` before calling
  `predict_image` — a TRAINING_READY model raises rather than
  silently falls back, by design.

---

## References

- Mitchell, M. et al. 2019. *Model Cards for Model Reporting.* FAT.
  https://arxiv.org/abs/1810.03993
- Ren, M. et al. 2024. *An open flame and smoke detection dataset for
  deep learning in remote sensing based fire detection.* Geo-spatial
  Information Science, 28(2). https://www.tandfonline.com/doi/full/10.1080/10095020.2024.2347922
- Hopkins, B. et al. 2024. *FLAME 2: Fire detection and modeLing —
  Aerial Multi-spectral imagE dataset.* IEEE DataPort.
  https://ieee-dataport.org/open-access/flame-2-fire-detection-and-modeling-aerial-multi-spectral-image-dataset
- Venâncio, P. V. A. B. de et al. 2022. *An automatic fire detection
  system based on deep convolutional neural networks for low-power,
  resource-constrained devices.* Neural Computing and Applications.
  https://github.com/gaia-solutions-on-demand/DFireDataset
- Ultralytics YOLOv8 — https://github.com/ultralytics/ultralytics
- See parent card `../../MODEL_CARD.md` for the full reference list and
  v0.1.0 / v0.2.0 / v1.0.0 targets.
