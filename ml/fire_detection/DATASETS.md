# Datasets — wildfire-watch fire/smoke detector

This file documents the training and evaluation datasets used for the
`wfw-fire-yolov8n` model line. URLs and per-dataset checksums also live in
machine-readable form at `eval/targets.yaml` (consumed by
`eval/prep_datasets.py`).

**Operator note.** All three datasets currently require a manual download
step (account login or click-through license). The prep harness verifies
images after you place them on disk and writes a manifest; it does not work
around the upstream auth.

---

## 1. FASDD — Flame And Smoke Detection Dataset

- **Paper:** Ren, M., et al. 2024. *An open flame and smoke detection dataset
  for deep learning in remote sensing based fire detection.* Geo-spatial
  Information Science, 28(2). https://www.tandfonline.com/doi/full/10.1080/10095020.2024.2347922
- **Authors:** Ming Ren, Wei Yan, et al. (OpenRSGIS Lab).
- **Year:** 2024 (preprint 2023; final version of record 2024).
- **Repo / homepage:** https://github.com/openrsgis/FASDD
- **Download:** https://www.scidb.cn/en/detail?dataSetId=ce9c9400b44148e1b0a749f5c3eb0bda
  (Science Data Bank — free account required.)
- **License:** Creative Commons Attribution 4.0 International (CC-BY-4.0).
- **Size on disk:** ~25 GiB (full FASDD with all three sub-datasets).
  The CV+UAV subset we actually use is ~12 GiB.
- **Image count:** ~120,000 across three sub-datasets.
- **Class taxonomy:** `fire`, `smoke`. Bounding-box labels (YOLO format).
- **Sub-datasets:**
  - `FASDD_CV` — ground-based (surveillance + handheld) imagery. **Used for pretrain.**
  - `FASDD_UAV` — UAV / aerial imagery. **Used for pretrain (oversample).**
  - `FASDD_RS` — satellite remote-sensing imagery. **NOT used** —
    spatial-scale mismatch hurts the on-drone model.
- **Splits:** Upstream provides train/val/test in 80/10/10 ratio.
- **Known biases:**
  - Heavy daylight bias; almost no nighttime imagery.
  - China-centric geography; vegetation classes are not 1:1 with Colorado
    montane forest.
  - Some `FASDD_CV` images are indoor / structure fires; we filter those at
    pretrain time via the upstream label JSON.
- **Download recipe (manual):**
  1. Open the Science Data Bank link above.
  2. Sign up for a free account (CN-hosted; works with any email).
  3. Accept the CC-BY-4.0 terms.
  4. Download `FASDD_CV.zip` and `FASDD_UAV.zip` (skip `FASDD_RS.zip`).
  5. Extract under `~/wildfire-watch-data/fasdd/`.
  6. Run: `python3 -m ml.fire_detection.eval.prep_datasets verify fasdd`.
- **BibTeX:**
  ```bibtex
  @article{ren2024fasdd,
    title   = {An open flame and smoke detection dataset for deep learning
               in remote sensing based fire detection},
    author  = {Ren, Ming and Yan, Wei and others},
    journal = {Geo-spatial Information Science},
    volume  = {28},
    number  = {2},
    year    = {2024},
    doi     = {10.1080/10095020.2024.2347922}
  }
  ```

---

## 2. FLAME-2 — UAV Aerial Fire Multi-Spectral Dataset

- **Paper:** Hopkins, B., et al. 2024. *FLAME 2: Fire detection and modeLing —
  Aerial Multi-spectral imagE dataset.* IEEE DataPort.
  https://par.nsf.gov/biblio/10497557
- **Authors:** Bryce Hopkins, Leo O'Neill, Fatemeh Afghah, et al.
  (Northern Arizona University + Clemson University).
- **Year:** 2024 (data collected 2021).
- **Homepage:** https://ieee-dataport.org/open-access/flame-2-fire-detection-and-modeling-aerial-multi-spectral-image-dataset
- **Download:** Same URL as homepage. **Free IEEE DataPort account required.**
- **License:** Creative Commons Attribution 4.0 International (CC-BY-4.0).
  (IEEE DataPort distributes under the contributor's chosen Creative Commons
  variant; the FLAME-2 entry is CC-BY at time of writing — re-verify on
  download.)
- **Size on disk:** ~45 GiB raw + labeled frames; the subset of pre-extracted
  254x254 RGB+IR frame pairs is ~12 GiB.
- **Image count:** ~50,000+ labeled RGB+IR frame pairs from 7 raw video
  pairs of an open-canopy prescribed burn.
- **Class taxonomy:** Frame-level binary labels — `Fire/NoFire`,
  `Smoke/NoSmoke`. Two expert annotators per frame. Note: not bounding-box
  labels; we generate weak boxes via the brightest contiguous region for
  fine-tune training.
- **Splits:** No canonical split shipped — we use a 70/15/15 random split
  with a fixed seed (see `eval/prep_datasets.py` manifest).
- **Known biases:**
  - **Single ecosystem:** ponderosa pine, Northern Arizona, ~7,000 ft elev.
    Beetle-kill, aspen, sage, and riparian environments common in the
    Gunnison AOR are absent. **This is the primary domain shift we worry
    about.**
  - Single fire (a prescribed burn). Smoke plumes are characteristic of
    prescribed-burn intensity, not unplanned wildfire.
  - Single time of day. No dawn / dusk imagery.
  - Camera angle bias: mostly nadir + low-oblique from a quadcopter at
    ~120 m AGL.
- **Download recipe (manual):**
  1. Sign in / sign up at https://ieee-dataport.org/.
  2. Open the FLAME-2 dataset page.
  3. Download the labeled frame archives (RGB and IR pairs).
  4. Extract under `~/wildfire-watch-data/flame2/`.
  5. Run: `python3 -m ml.fire_detection.eval.prep_datasets verify flame2`.
- **BibTeX:**
  ```bibtex
  @data{flame2_2024,
    title     = {{FLAME 2}: Fire detection and modeLing —
                 Aerial Multi-spectral imagE dataset},
    author    = {Hopkins, Bryce and O'Neill, Leo and Afghah, Fatemeh and
                 Razi, Abolfazl and Reardon, Jared and Watts, Adam C. and
                 Fule, Peter Z.},
    publisher = {IEEE DataPort},
    year      = {2024},
    doi       = {10.21227/swyw-6j78}
  }
  ```

---

## 3. D-Fire — fire and smoke image dataset (eval holdout)

- **Paper:** Venâncio, P. V. A. B. de et al. 2022. *An automatic fire detection
  system based on deep convolutional neural networks for low-power,
  resource-constrained devices.* Neural Computing and Applications.
- **Authors:** Pedro Vinícius Almeida Borges de Venâncio, Adriano Chaves
  Lisboa, Adriano Vilela Barbosa (Gaia Solutions on Demand).
- **Year:** 2022.
- **Homepage / repo:** https://github.com/gaia-solutions-on-demand/DFireDataset
- **Download:** Release archive linked from the GitHub repo's README.
  (No login required, but the file is large — ~3 GiB.)
- **License:** Creative Commons Attribution Non-Commercial 4.0 (CC-BY-NC-4.0).
  **Important:** the non-commercial restriction means a commercialization of
  wildfire-watch downstream cannot use D-Fire-trained weights. We use D-Fire
  **only as an eval holdout**, never as training data.
- **Size on disk:** ~3 GiB.
- **Image count:** 21,527 images.
- **Class taxonomy:**
  - Fire only — 1,164 images.
  - Smoke only — 5,867 images.
  - Fire + smoke — 4,658 images.
  - None (negative) — 9,838 images.
  - 26,557 bounding boxes total: 11,865 smoke + 14,692 fire.
- **Splits:** We use the entire D-Fire as holdout — never seen during
  pretrain or fine-tune. Confidence intervals are bootstrap-derived.
- **Known biases:**
  - Mixed indoor + outdoor imagery (laboratory burns, structure fires,
    forest fires).
  - Camera-angle distribution skews ground-level.
  - Brazilian-collected (most labels), so vegetation and smoke colour
    differ from Colorado conifer smoke.
- **Why it's still our holdout:** D-Fire is well-curated, well-labeled, and
  not used during training. Its bias profile differs from FASDD/FLAME-2 in
  useful ways — a model that generalizes to D-Fire is more likely to
  generalize to AOR imagery than one that only memorizes the train sets.
- **Download recipe (manual):**
  1. Open https://github.com/gaia-solutions-on-demand/DFireDataset.
  2. Follow the `README.md` link to the release artifact.
  3. Download into `~/wildfire-watch-data/dfire/`.
  4. Extract.
  5. Run: `python3 -m ml.fire_detection.eval.prep_datasets verify dfire`.
- **BibTeX:**
  ```bibtex
  @article{venancio2022dfire,
    title   = {An automatic fire detection system based on deep convolutional
               neural networks for low-power, resource-constrained devices},
    author  = {Ven{\^a}ncio, Pedro V. A. B. de and Lisboa, Adriano Chaves and
               Barbosa, Adriano Vilela},
    journal = {Neural Computing and Applications},
    year    = {2022},
    doi     = {10.1007/s00521-022-07467-z}
  }
  ```

---

## Datasets we considered but are NOT using

| Dataset | Why not |
|---|---|
| **FLAME-1** (NAU 2020) | Superseded by FLAME-2; smaller, single sensor modality |
| **FireNet** (Jadon et al. 2019) | Too small (~5k images), no bbox labels, image-level only |
| **FireSense** (Dimitropoulos et al. 2014) | Older video-only dataset, mostly indoor; useful for legacy benchmarks but not for our viewpoint |
| **DFS-FIRE-SMOKE** (Wu et al. 2022) | Overlaps significantly with D-Fire; we'd rather hold D-Fire out cleanly than mix both |
| **MSFRD** (multi-source fire dataset) | License unclear at time of writing; revisit before v0.2.0 |
| **CDnet** | Change-detection, not fire-classification — wrong domain |

---

## Disk usage budget

| Dataset | Sub-set | Approx size | Use |
|---|---|---:|---|
| FASDD | CV + UAV (skip RS) | ~12 GiB | Pretrain |
| FLAME-2 | Labeled frame pairs | ~12 GiB | Fine-tune |
| D-Fire | Full | ~3 GiB | Holdout eval |
| **Total** | | **~27 GiB** | |

Datasets land at `~/wildfire-watch-data/<name>/`. The directory is **not**
inside the repo. The repo's `runs/` and `checkpoints/` directories are
gitignored.

## License compliance summary

- The trained weights inherit constraints from the **strictest** dataset
  license used during **training**. Because we train on FASDD (CC-BY-4.0) +
  FLAME-2 (CC-BY-4.0) only, the resulting weights are distributable.
- D-Fire (CC-BY-NC-4.0) is **eval-only**. It does not encumber the trained
  weights. Be very careful never to feed D-Fire into training — the eval
  harness reads it only via `eval/prep_datasets.py` with `role: holdout_eval`.
- The Ultralytics YOLOv8 base weights are AGPL-3.0. This applies separately
  to any combined product that distributes the weights.
