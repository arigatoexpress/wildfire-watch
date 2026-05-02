# Model Card - `wfw-fire-heuristic-v0.0.1`

Following the model-card framework introduced by Mitchell et al. 2019,
"Model Cards for Model Reporting" (https://arxiv.org/abs/1810.03993).

This is the **per-version** model card for the wildfire-watch v0.0.1 release.
The repo-level `ml/fire_detection/MODEL_CARD.md` documents the model line as
a whole; this file pins the v0.0.1 column.

> **v0.0.1 is a deterministic colour-temperature heuristic, not a trained
> model.** It is shipped as the registry's v0 anchor: it gives the model
> registry, valuation engine, and Phase-0 post-flight processor a real
> versioned artifact to cite, and it gives v0.1.0 a baseline to beat.

---

## 1. Model Details

- **Name:** `wfw-fire-heuristic-v0.0.1`
- **Version:** `0.0.1`
- **Owner:** wildfire-watch (Aristotle Ribs / `aristotlespec@gmail.com`)
- **Architecture:** Deterministic colour-channel heuristic. Two scoring
  predicates over downsampled (320x320) RGB pixels:
  - **Smoke:** mean RGB in [90, 200] AND `max-min` channel spread <= 25
    AND smoke-pixel area >= 0.5% of frame.
  - **Fire:** `R - max(G, B) >= 60` AND `R > 150` AND fire-pixel area >=
    0.1% of frame.
  No learned parameters. No training step. Mirrors the constants already
  used in `ml/fire_detection/mavic_post_flight.py` so v0.0.1 is bit-for-bit
  consistent with the Phase-0 post-flight pipeline already in production.
- **Framework:** Pure Python; PIL is lazy-imported only for `predict_image`.
- **Inputs:**
  - **Real-mode:** RGB image (path or PIL.Image), 8-bit, 3-channel,
    arbitrary size (downsampled to 320x320 internally).
  - **Stub-mode:** `(rgb_score: float, thermal_delta_c: float)` scalars,
    used by the simulator and registry tests.
- **Outputs:** `Detection(score: float, class_name: str, bbox_xyxy: tuple |
  None, latency_ms: float)`. `class_name` is one of `{'smoke', 'fire',
  'none'}`.
- **License:** Apache-2.0 (code). No weights ship - the model is its source
  code.
- **Training data summary:** None. v0.0.1 is training-free.
- **Eval data summary:** Synthetic-100 (rgb_score x thermal_delta_c grid,
  seed 42). D-Fire holdout reserved for v0.1.0.
- **Cite:** v0.0.1 is unpublished. Heuristic constants follow the Phase-0
  post-flight pipeline (see `ml/fire_detection/mavic_post_flight.py`).

## 2. Intended Use

### Primary use

- **Phase-0 post-flight processor.** Given Mavic Mini SD-card footage,
  flag candidate smoke / fire frames before the operator does the manual
  review pass. v0.0.1 IS the heuristic that the existing
  `mavic_post_flight.py` pipeline already calls - this release factors it
  out into a registered, versioned, schema-stable model.
- **Simulator stub.** The kinematic simulator passes
  `(rgb_score, thermal_delta_c)` scalars directly; v0.0.1 returns a
  `Detection` so the downstream signal pipeline gets a deterministic,
  reproducible source of model outputs without ultralytics installed.
- **Eval-harness baseline.** v0.1.0 (the first trained YOLO model) must
  beat v0.0.1's synthetic eval numbers on the same plane to qualify as a
  release.

### Out-of-scope use - explicitly NOT a basis for

Same out-of-scope set as the parent `MODEL_CARD.md`:

- Fire suppression decisions, evacuation orders, wilderness flights,
  controlled-burn discrimination without an allow-list, smoke-source
  disambiguation in WUI, wildlife or human identification.
- Additionally for v0.0.1: **never** ship v0.0.1 as the only detector on a
  drone in production. Its precision floor is too low (synthetic
  precision-at-recall-0.80 = 0.82) and it has no thermal corroboration
  step (callers must compose with `infer.should_emit()`).

## 3. Factors

Same factor list as the parent card. v0.0.1 specifically is most affected
by:

| Factor | v0.0.1 sensitivity |
|---|---|
| Greyscale-saturated cloud cover | High false-positive risk on smoke (cloud shadow looks like smoke to the spread-based heuristic) |
| Beetle-killed timber | Very high false-positive risk; gray dead crowns trip the smoke gate |
| Dust devils | Moderate false-positive risk on smoke |
| Low-sun rim lighting | Reduces smoke recall (back-lit plumes lose channel-spread structure) |
| Image compression | JPEG at low quality blurs the channel spread, raises false-positive rate |
| Camera saturation | Mavic over-saturates orange; v0.0.1 fire gate fires on synthetic orange foliage |

## 4. Metrics

Same metric definitions as the parent card. v0.0.1 reports:

- **Synthetic precision-at-recall-0.80** in stub-mode.
- **Mac-CPU end-to-end `predict_image` latency** (p50 / p95 / p99 / mean).
- **CPU throughput** (FPS).
- **Jetson FP16 latency: n/a** (heuristic is CPU-only, no GPU
  acceleration).

## 5. Evaluation Data

### Synthetic eval (v0.0.1)

100 cases sampled from the (rgb_score in [0, 1], thermal_delta_c in [0,
30] Celsius) plane with a fixed seed (42). Ground truth labelled as:

- `fire` if rgb_score >= 0.4 AND thermal_delta_c >= 15.0
- `smoke` if rgb_score >= 0.4 AND thermal_delta_c >= 5.0
- `none` otherwise

This eval covers the fusion-gate decision surface that `infer.should_emit`
implements. **It is not a holdout image dataset.** v0.0.1 cannot be
evaluated against D-Fire bounding-box labels because v0.0.1 does not emit
bounding boxes from random RGB inputs at the precision required for box
IoU - it emits region masks, which are not directly comparable.

### Holdout eval (deferred to v0.1.0)

D-Fire (CC-BY-NC-4.0) is reserved for v0.1.0. See `../../DATASETS.md`.

## 6. Training Data

**None.** v0.0.1 is a deterministic heuristic. The threshold constants
were tuned manually against early Mavic Mini test footage during the
Phase-0 build-out (no fitted parameters, no validation split).

## 7. Quantitative Analyses

### Measured (v0.0.1, this card)

| Metric                              | Target  | v0.0.1 measured |
|---|---|---|
| precision @ recall=0.80 (D-Fire)    | >= 0.95 | TBD (deferred to v0.1.0) |
| precision @ recall=0.80 (synthetic) | n/a     | **0.8246** |
| precision (synthetic, threshold)    | n/a     | **0.8214** |
| recall (synthetic)                  | n/a     | **0.9787** |
| F1 (synthetic)                      | n/a     | **0.8932** |
| mAP@50                              | >= 0.65 | TBD (no bbox eval) |
| mAP@50:95                           | >= 0.40 | TBD (no bbox eval) |
| latency p95 (Mac CPU, predict_image)| n/a     | **39.77 ms** |
| latency p50 (Mac CPU, predict_image)| n/a     | **38.81 ms** |
| throughput (Mac CPU)                | n/a     | **25.93 FPS** |
| latency p95 (Jetson Orin Super FP16)| <= 25 ms| **n/a** (CPU-only heuristic, no GPU acceleration) |
| throughput (Jetson Orin Super FP16) | >= 60 FPS | **n/a** (same) |

### Synthetic per-class

| Class | GT count | Correct | Per-class recall |
|---|---:|---:|---:|
| fire  | 32 | 32 | 1.0000 |
| smoke | 15 | 14 | 0.9333 |
| none  | 53 | 43 | 0.8113 |

False-positive rate on synthetic negatives is 10/53 = 18.9%, driven by
the deliberately-loose smoke-grey thresholds. The fusion gate
(`infer.should_emit`) is the safety net that filters these in production.

### Confusion (synthetic, n=100)

|  | predicted positive | predicted negative |
|---|---:|---:|
| **GT positive (47)** | TP = 46 | FN = 1 |
| **GT negative (53)** | FP = 10 | TN = 43 |

### Targets status

- **Primary target (precision-at-recall-0.80 >= 0.95):** synthetic-only
  number is 0.8246. **Does not meet target.** This is the v0.0.1 floor;
  v0.1.0 (YOLO-trained) is the release that must clear 0.95 on the real
  D-Fire holdout.
- **Deployment latency target (Jetson p95 <= 25 ms):** **n/a** -
  heuristic is CPU-only.

Raw eval output: `eval.json` in this directory.

## 8. Ethical Considerations

Same as the parent card. For v0.0.1 specifically:

- **The fusion gate is mandatory.** v0.0.1's precision is too low to
  emit signals without `infer.should_emit()` corroborating against
  thermal delta-T, persistence, geofence, and wind direction.
- **No training-data privacy concerns** (the model has no training
  data).
- **Reproducibility:** the seed-42 synthetic eval is replayable. The
  inference path is deterministic by construction.

## 9. Caveats and Recommendations

- **v0.0.1 is the colour-heuristic baseline.** Treat its outputs as
  approximate. Use it as the v0.1.0 baseline-to-beat, not as a
  production detector.
- **No bbox eval.** v0.0.1 emits region masks; mAP@50 / mAP@50:95 are
  TBD until a model that produces tight boxes (v0.1.0 YOLO) is trained.
- **Jetson path is unexercised.** The heuristic runs on CPU; do not
  cite v0.0.1 latency as evidence the on-drone target is achievable.
- **Calibrate on AOR data before any real deployment.** Beetle-kill
  stands trip the smoke gate. Phase-0 post-flight footage from the
  Gunnison AOR is the cheapest re-tuning input.
- **Same-as-parent caveat:** before tagging any new wfw-fire-* version,
  re-run the eval harness and regenerate this file.

## 10. Provenance

- **Repository:** `wildfire-watch`, branch `main`.
- **Released by:** wildfire-watch maintainer team.
- **Released at:** 2026-05-02T05:12:55Z (UTC).
- **code_sha at release:** `5ac0dc6900c1e9e1c4d3f92c909f67584bfbb99e`
  (see `manifest.json`).
- **Reproducibility:**
  - `inference.py` (this directory) is the entry point.
  - `eval.json` (this directory) is the raw eval output.
  - `manifest.json` (this directory) carries the provenance fields the
    registry consumes.
  - `eval_harness.py` and `latency_bench.py` (parent eval/ dir) provide
    the shared harness machinery; v0.0.1's measurements were taken via
    direct calls to `predict_image` and `predict_stub` since the harness
    is currently ultralytics-shaped.
- **Schema integration:** Detections from this model are wrapped into
  `wildfire_signal` v1.0.0 records by `infer.build_signal()`. The
  `evidence.model_outputs` envelope cites `wfw-fire-heuristic-v0.0.1`
  via the registry.

---

## References

- Mitchell, M. et al. 2019. *Model Cards for Model Reporting.* FAT.
  https://arxiv.org/abs/1810.03993
- See parent card `../../MODEL_CARD.md` for the full reference list and
  v0.1.0 / v0.2.0 targets.
