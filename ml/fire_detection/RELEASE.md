# Release Workflow — `wfw-fire-yolov8n-v*`

Checklist for cutting a fire/smoke detector release. Follow in order.

## 0. Prerequisites

- Working tree clean (`git status` empty), on `main` branch.
- All tests pass: `cd ~/Code/wildfire-watch && /usr/local/bin/python3 -m pytest -q`.
- The four research datasets prepared on disk (verify with `prep_datasets.py status`).
- Training rig available: Windows PC at `100.71.10.48` with RTX 5070 Ti.
- Jetson Orin Nano Super available for the latency confirmation run (Phase 1+).

## 1. Prepare datasets

```bash
cd ~/Code/wildfire-watch
/usr/local/bin/python3 -m ml.fire_detection.eval.prep_datasets prep all
```

Most datasets require a manual download — the harness prints actionable
instructions. After manual extraction, re-run `prep all` to verify and write
the manifest. Confirm:

```bash
/usr/local/bin/python3 -m ml.fire_detection.eval.prep_datasets status
```

Expect: three rows with `prepared=True` and image counts within the
expected ranges from `eval/targets.yaml`.

## 2. Train

On the Windows PC (or wherever the GPU lives):

```bash
cd /e/Sapphire/Code/wildfire-watch/ml/fire_detection      # adjust for your environment
python3 train.py \
    --base yolov8n.pt \
    --data fasdd_cv.yaml \
    --epochs 100 \
    --imgsz 640 \
    --batch 32 \
    --device 0 \
    --export-trt
```

Wall time: ~6 hours on RTX 5070 Ti for the FASDD pretrain. Then re-run
fine-tune on FLAME-2 with `--data flame2.yaml` and a lower learning rate
(see `docs/30-ml-stack.md`).

Outputs land in `runs/wildfire_yolo/weights/` — copy `best.pt` and
`best.engine` to the Mac for evaluation.

## 3. Evaluate detection metrics

```bash
cd ~/Code/wildfire-watch
/usr/local/bin/python3 -m ml.fire_detection.eval.eval_harness \
    --checkpoint runs/wildfire_yolo/weights/best.pt \
    --dataset dfire \
    --conf 0.25 --iou 0.50 \
    --output runs/eval/wfw-fire-yolov8n-v0.1.0_dfire.json \
    --markdown runs/eval/wfw-fire-yolov8n-v0.1.0_dfire.md
```

Open the markdown output and confirm against `eval/targets.yaml`:

| Metric | Target |
|---|---|
| precision @ recall=0.80 | >= 0.95 (production) / >= 0.92 (v0.1.0 first cut) |
| mAP@50 | >= 0.65 (production) / >= 0.55 (v0.1.0) |
| mAP@50:95 | >= 0.40 (production) / >= 0.32 (v0.1.0) |

If any metric misses the v0.1.0 target, do not tag — diagnose, retrain, repeat.

## 4. Benchmark latency

```bash
/usr/local/bin/python3 -m ml.fire_detection.eval.latency_bench \
    --checkpoint runs/wildfire_yolo/weights/best.pt \
    --imgsz 640 --batch 1 --warmup 5 --runs 100 \
    --output runs/eval/wfw-fire-yolov8n-v0.1.0_latency_cpu.json
```

The bench script estimates Jetson FP16 p95 from the CPU measurement using
the speedup factor in `eval/targets.yaml`. The estimate is rough — when
Jetson hardware is available, repeat the bench on the Jetson with the
exported `*.engine` file and replace the estimate with a direct measurement.

Recommendation strings:
- `ready_for_jetson_fp16_deployment` → proceed.
- `needs_optimization` → consider FP16/INT8 quantization, smaller imgsz, or
  YOLOv8-tuned export flags before tagging.
- `stub_run_inconclusive` → you ran with `--checkpoint stub`; rerun with the
  real checkpoint.

## 5. Verify against `eval/targets.yaml`

```bash
# Sanity check — does the produced JSON satisfy the targets?
python3 - <<'PY'
import json, yaml
metrics = json.loads(open('runs/eval/wfw-fire-yolov8n-v0.1.0_dfire.json').read())
targets = yaml.safe_load(open('ml/fire_detection/eval/targets.yaml'))
m = metrics['metrics']
ok  = m['precision_at_recall_0.80'] >= targets['detection']['primary_target']
ok &= m['map_50']                  >= targets['detection']['map50_target']
ok &= m['map_50_95']               >= targets['detection']['map50_95_target']
print('READY' if ok else 'NOT READY')
PY
```

Iterate until READY before continuing.

## 6. Update MODEL_CARD.md

Replace the v0.0.1 quantitative table column with measured numbers from step
3 + 4. Bump the `Version:` line in section 1. Update `Card date:` in section
10. Sanity check: have any of the bias considerations changed because of new
training data? Update Section 3 (Factors) and Section 5 (Evaluation Data) if
so.

## 7. Commit + tag

```bash
cd ~/Code/wildfire-watch
git add ml/fire_detection/MODEL_CARD.md \
        runs/eval/wfw-fire-yolov8n-v0.1.0_dfire.json \
        runs/eval/wfw-fire-yolov8n-v0.1.0_latency_cpu.json
git commit -m "release(ml): wfw-fire-yolov8n-v0.1.0 — first trained checkpoint"
git tag wfw-fire-yolov8n-v0.1.0
git push --tags
```

Note: the JSON eval artifacts under `runs/` are gitignored by default. For a
release commit, we deliberately add them to source control so the metric
table on MODEL_CARD.md can be reproduced. For larger artifacts (the
`best.pt` and `best.engine` checkpoints themselves), use a separate
`wildfire-watch-eval` repo or push to GCS at
`gs://wildfire-watch-evidence/eval/<version>/`.

## 8. Post-release

- Open a follow-up issue: "v0.2.0 — collect Colorado-AOR imagery for fine-tune".
- Bump the `evidence.model_versions.fire_yolo` field in any signal-emitting
  code that hard-codes a version string.
- If the Jetson p95 latency was estimated rather than measured, schedule a
  hardware-in-hand measurement; replace the estimate in MODEL_CARD.md
  Section 7 with the real number on the next minor release.
- Notify partner FDs (CBFPD, GCFPD) that a new model is deployed; update the
  monthly partnership update.

## Versioning convention

- `v0.0.x` — placeholder / pre-training. Stub model in `infer.py`.
- `v0.1.0` — first trained model on FASDD + FLAME-2; relaxed targets.
- `v0.2.0` — first Colorado-AOR augmented model; full targets.
- `v1.0.0` — production-grade; >= 12 weeks of operational data; AOR-augmented;
  Jetson-FP16 measured (not estimated); deployed at >= 1 partner FD.

Major-version bumps require a partner-agency review of the model card.
