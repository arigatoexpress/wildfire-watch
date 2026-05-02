# real_bench - public-domain image bench for wfw-fire-heuristic-v0.0.1

A small curated set of federal-public-domain wildfire / smoke / negative-control imagery, hand-labeled, scored by v0.0.1's deterministic heuristic, and rendered as a Markdown report. The qualitative ground truth that the synthetic eval (`../eval_harness.py`) cannot replace.

## Structure

```
real_bench/
├── README.md                      # this file
├── images/                        # 12 federal-public-domain JPGs
│   └── README.md                  # full per-image attribution
├── labels.yaml                    # hand-labeled ground truth
├── bench.py                       # runs v0.0.1 against the set + renders report
├── report_2026-05-02.md           # latest generated report
└── tests/                         # 13 tests
```

## Run

```bash
cd ~/Code/wildfire-watch
python3 -m ml.fire_detection.eval.real_bench.bench
# or:
python3 -m ml.fire_detection.eval.real_bench.bench --out /tmp/bench.md
```

## Tests

```bash
python3 -m pytest ml/fire_detection/eval/real_bench/tests/ -q
```

## What this is + isn't

- **Is**: a 12-image qualitative ground-truth check for v0.0.1's behavior on real federal-source wildfire imagery, with full per-image attribution and a 1-rater label set.
- **Isn't**: a statistically meaningful benchmark. n=12 is too small; one labeler's judgement is a noisy oracle; recall on this curated set is not generalizable. The synthetic eval at `../eval_harness.py` (n=100) is the quantitative claim. This bench is the "does it actually fire on real photos" sanity check.

The headline line for the v0.0.1 model card: **recall 1.000, precision 0.583, F1 0.737** on 7 positives + 5 negatives. The detector catches every real fire/smoke event in the set but over-fires on yellow foliage, charred terrain, B&W historical photos, and wildlife.

## v0.1.0 implications

Each FP in the report is a hard-negative-mining hint for the YOLOv8n fine-tune in `../../runs/v0.1.0/`. The report's "Recommendations for v0.1.0" section names the specific files to add to the FASDD pretrain set as hard negatives.

## License

All 12 images are works of U.S. federal employees in the course of official duties (NPS, USFS, USDA), public domain under 17 U.S.C. Sec. 105. See `images/README.md` for per-image attribution + source URLs (Wikimedia Commons mirrors of the federal originals).

The bench code itself is Apache-2.0 (matches the parent repo).
