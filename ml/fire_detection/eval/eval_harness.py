"""wildfire-watch fire/smoke detector — evaluation harness.

Given a trained checkpoint (or "stub" for testing) and a dataset name, computes:

  - Detection metrics: mAP@50, mAP@50:95, precision, recall, F1.
  - Precision @ recall=0.80 (the primary metric — see targets.yaml).
  - Per-class metrics if the dataset is multi-class (fire / smoke).
  - Latency p50/p95/p99 measured during eval.
  - A confusion matrix.
  - A Markdown table of metrics, ready to paste into MODEL_CARD.md.

Usage:
    python3 -m ml.fire_detection.eval.eval_harness \\
        --checkpoint runs/wildfire_yolo/weights/best.pt \\
        --dataset dfire \\
        --conf 0.25 --iou 0.50 \\
        --output runs/eval/dfire_v0.1.0.json

Stub mode: if --checkpoint is the literal string "stub", or if ultralytics is
not importable, run a deterministic fake-detector. Tests use stub mode.

Dependencies are all lazy-imported — module imports cleanly with stdlib only.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Pure data classes — no third-party deps required to import this module.
# ---------------------------------------------------------------------------


@dataclass
class Detection:
    """One predicted bounding box. xyxy in absolute pixel coords."""

    x1: float
    y1: float
    x2: float
    y2: float
    score: float
    cls: int

    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)


@dataclass
class GroundTruth:
    """One ground-truth bounding box."""

    x1: float
    y1: float
    x2: float
    y2: float
    cls: int


@dataclass
class FrameSample:
    """One image's worth of GT + predictions."""

    image_id: str
    detections: list[Detection]
    ground_truths: list[GroundTruth]
    inference_ms: float = 0.0


@dataclass
class EvalConfig:
    checkpoint: str
    dataset: str
    conf_threshold: float = 0.25
    iou_threshold: float = 0.50
    max_det_per_image: int = 300
    image_count_limit: int | None = None
    class_names: tuple[str, ...] = ("fire", "smoke")


@dataclass
class EvalReport:
    config: EvalConfig
    map_50: float
    map_50_95: float
    precision: float
    recall: float
    f1: float
    precision_at_recall_080: float
    per_class: dict[str, dict[str, float]] = field(default_factory=dict)
    confusion: dict[str, int] = field(default_factory=dict)
    latency_ms: dict[str, float] = field(default_factory=dict)
    image_count: int = 0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": {
                "checkpoint": self.config.checkpoint,
                "dataset": self.config.dataset,
                "conf_threshold": self.config.conf_threshold,
                "iou_threshold": self.config.iou_threshold,
                "max_det_per_image": self.config.max_det_per_image,
                "image_count_limit": self.config.image_count_limit,
                "class_names": list(self.config.class_names),
            },
            "metrics": {
                "map_50": self.map_50,
                "map_50_95": self.map_50_95,
                "precision": self.precision,
                "recall": self.recall,
                "f1": self.f1,
                "precision_at_recall_0.80": self.precision_at_recall_080,
            },
            "per_class": self.per_class,
            "confusion": self.confusion,
            "latency_ms": self.latency_ms,
            "image_count": self.image_count,
            "note": self.note,
        }

    def to_markdown(self) -> str:
        lines = [
            f"### Evaluation — {self.config.dataset} (n={self.image_count})",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| mAP@50 | {self.map_50:.4f} |",
            f"| mAP@50:95 | {self.map_50_95:.4f} |",
            f"| Precision | {self.precision:.4f} |",
            f"| Recall | {self.recall:.4f} |",
            f"| F1 | {self.f1:.4f} |",
            f"| Precision @ Recall=0.80 | {self.precision_at_recall_080:.4f} |",
        ]
        for tag in ("p50", "p95", "p99"):
            if tag in self.latency_ms:
                lines.append(f"| Latency {tag} (ms) | {self.latency_ms[tag]:.2f} |")
        if self.per_class:
            lines.extend(["", "#### Per-class", "", "| Class | Precision | Recall | AP@50 |", "|---|---:|---:|---:|"])
            for cls_name, m in self.per_class.items():
                lines.append(
                    f"| {cls_name} | {m.get('precision', 0):.4f} "
                    f"| {m.get('recall', 0):.4f} | {m.get('ap_50', 0):.4f} |"
                )
        if self.note:
            lines.extend(["", f"_{self.note}_"])
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# IoU + matching primitives — used by the metrics computer.
# ---------------------------------------------------------------------------


def iou_xyxy(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Intersection-over-union of two axis-aligned boxes in xyxy form."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter = inter_w * inter_h
    a_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    b_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = a_area + b_area - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def match_detections(
    detections: list[Detection],
    ground_truths: list[GroundTruth],
    iou_threshold: float,
    cls: int | None = None,
) -> tuple[list[bool], list[bool]]:
    """Greedy IoU-matching, sorted by detection score descending.

    Returns (det_is_tp, gt_is_matched). Boxes filtered to `cls` if given.
    Matches require equal class and IoU >= threshold.
    """
    dets = [d for d in detections if cls is None or d.cls == cls]
    gts = [g for g in ground_truths if cls is None or g.cls == cls]

    dets_sorted = sorted(enumerate(dets), key=lambda ix_d: ix_d[1].score, reverse=True)
    det_is_tp = [False] * len(dets)
    gt_is_matched = [False] * len(gts)

    for orig_idx, det in dets_sorted:
        best_iou = 0.0
        best_j = -1
        for j, gt in enumerate(gts):
            if gt_is_matched[j]:
                continue
            if det.cls != gt.cls:
                continue
            iou = iou_xyxy((det.x1, det.y1, det.x2, det.y2), (gt.x1, gt.y1, gt.x2, gt.y2))
            if iou >= iou_threshold and iou > best_iou:
                best_iou = iou
                best_j = j
        if best_j >= 0:
            det_is_tp[orig_idx] = True
            gt_is_matched[best_j] = True
    return det_is_tp, gt_is_matched


# ---------------------------------------------------------------------------
# Metric computation — VOC-2007-style 11-point AP, with COCO-style 50:95 sweep.
# ---------------------------------------------------------------------------


def precision_recall_curve(
    samples: list[FrameSample],
    iou_threshold: float,
    cls: int | None = None,
) -> tuple[list[float], list[float], list[float]]:
    """Return (recall, precision, score_threshold) curves for one IoU threshold."""
    all_dets: list[tuple[float, bool]] = []  # (score, is_tp)
    total_gt = 0
    for sample in samples:
        det_tp, _gt_matched = match_detections(
            sample.detections, sample.ground_truths, iou_threshold, cls=cls
        )
        dets = [d for d in sample.detections if cls is None or d.cls == cls]
        total_gt += len([g for g in sample.ground_truths if cls is None or g.cls == cls])
        for d, is_tp in zip(dets, det_tp, strict=True):
            all_dets.append((d.score, is_tp))

    if total_gt == 0:
        return [0.0], [0.0], [0.0]
    if not all_dets:
        return [0.0], [1.0], [1.0]

    all_dets.sort(key=lambda sd: sd[0], reverse=True)
    tp_cum = 0
    fp_cum = 0
    precisions: list[float] = []
    recalls: list[float] = []
    score_thresholds: list[float] = []
    for score, is_tp in all_dets:
        if is_tp:
            tp_cum += 1
        else:
            fp_cum += 1
        prec = tp_cum / max(tp_cum + fp_cum, 1)
        rec = tp_cum / total_gt
        precisions.append(prec)
        recalls.append(rec)
        score_thresholds.append(score)
    return recalls, precisions, score_thresholds


def average_precision(recalls: list[float], precisions: list[float]) -> float:
    """11-point interpolated AP (VOC 2007). Robust on small datasets."""
    if not recalls:
        return 0.0
    ap = 0.0
    for r in (i / 10.0 for i in range(11)):
        # Highest precision among detections with recall >= r.
        candidates = [p for rec, p in zip(recalls, precisions, strict=True) if rec >= r]
        ap += max(candidates, default=0.0)
    return ap / 11.0


def precision_at_recall(recalls: list[float], precisions: list[float], target_recall: float) -> float:
    """Highest precision at recall >= target. 0.0 if recall is unreachable."""
    candidates = [p for rec, p in zip(recalls, precisions, strict=True) if rec >= target_recall]
    return max(candidates, default=0.0)


def compute_eval_report(
    samples: list[FrameSample],
    config: EvalConfig,
    note: str = "",
) -> EvalReport:
    """Compute the full EvalReport from a list of FrameSample.

    Pure function — does not load any model. The harness's main() handles
    populating samples; this is what tests target for correctness.
    """
    # mAP @ IoU=0.50 (VOC-style)
    recalls_50, precisions_50, _ = precision_recall_curve(samples, iou_threshold=0.50)
    map_50 = average_precision(recalls_50, precisions_50)

    # mAP @ IoU=0.50:0.95 step 0.05 (COCO-style)
    iou_steps = [0.50 + 0.05 * i for i in range(10)]
    aps: list[float] = []
    for thr in iou_steps:
        r, p, _ = precision_recall_curve(samples, iou_threshold=thr)
        aps.append(average_precision(r, p))
    map_50_95 = sum(aps) / len(aps)

    # Aggregate precision/recall at the configured confidence threshold.
    tp = fp = fn = 0
    for sample in samples:
        det_tp, gt_matched = match_detections(
            sample.detections, sample.ground_truths, iou_threshold=config.iou_threshold
        )
        for det, is_tp in zip(sample.detections, det_tp, strict=True):
            if det.score < config.conf_threshold:
                continue
            if is_tp:
                tp += 1
            else:
                fp += 1
        # Unmatched GT = false negatives (regardless of conf, since GT has no score).
        fn += sum(1 for matched in gt_matched if not matched)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    # Precision @ recall=0.80 on the IoU=0.50 PR curve.
    p_at_r80 = precision_at_recall(recalls_50, precisions_50, target_recall=0.80)

    # Per-class breakdown.
    per_class: dict[str, dict[str, float]] = {}
    for cls_idx, cls_name in enumerate(config.class_names):
        rc, pc, _ = precision_recall_curve(samples, iou_threshold=0.50, cls=cls_idx)
        ap_cls = average_precision(rc, pc)
        # Final-point precision/recall at the curve's last entry.
        per_class[cls_name] = {
            "precision": pc[-1] if pc else 0.0,
            "recall": rc[-1] if rc else 0.0,
            "ap_50": ap_cls,
        }

    # Confusion matrix (multi-class, includes background as miss/extra).
    confusion = {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
    }

    # Latency.
    timings = [s.inference_ms for s in samples if s.inference_ms > 0.0]
    latency_ms: dict[str, float] = {}
    if timings:
        timings_sorted = sorted(timings)
        latency_ms = {
            "p50": _percentile(timings_sorted, 50),
            "p95": _percentile(timings_sorted, 95),
            "p99": _percentile(timings_sorted, 99),
            "mean": statistics.fmean(timings_sorted),
            "n": float(len(timings_sorted)),
        }

    return EvalReport(
        config=config,
        map_50=map_50,
        map_50_95=map_50_95,
        precision=precision,
        recall=recall,
        f1=f1,
        precision_at_recall_080=p_at_r80,
        per_class=per_class,
        confusion=confusion,
        latency_ms=latency_ms,
        image_count=len(samples),
        note=note,
    )


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (p / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return sorted_values[int(k)]
    frac = k - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


# ---------------------------------------------------------------------------
# Sample sources — ultralytics-backed and stub.
# ---------------------------------------------------------------------------


def collect_samples_stub(image_count: int = 16, seed: int = 0) -> list[FrameSample]:
    """Deterministic fake samples. Used by tests and when ultralytics is missing."""
    import random

    rng = random.Random(seed)
    samples: list[FrameSample] = []
    for i in range(image_count):
        # Each frame: 1-2 GT boxes; predictions mostly track GT with jitter, plus
        # occasional false positives.
        gts: list[GroundTruth] = []
        dets: list[Detection] = []
        n_gt = rng.choice([1, 1, 2])
        for _ in range(n_gt):
            cls = rng.choice([0, 1])
            x1 = rng.uniform(0, 540)
            y1 = rng.uniform(0, 380)
            w = rng.uniform(40, 100)
            h = rng.uniform(40, 100)
            gts.append(GroundTruth(x1=x1, y1=y1, x2=x1 + w, y2=y1 + h, cls=cls))
            # Matching detection with jitter + decent score.
            dx = rng.uniform(-3, 3)
            dy = rng.uniform(-3, 3)
            score = rng.uniform(0.55, 0.95)
            dets.append(
                Detection(
                    x1=x1 + dx,
                    y1=y1 + dy,
                    x2=x1 + w + dx,
                    y2=y1 + h + dy,
                    score=score,
                    cls=cls,
                )
            )
        # Maybe inject a false positive ~25% of the time.
        if rng.random() < 0.25:
            x1 = rng.uniform(0, 580)
            y1 = rng.uniform(0, 400)
            dets.append(
                Detection(
                    x1=x1,
                    y1=y1,
                    x2=x1 + 50,
                    y2=y1 + 50,
                    score=rng.uniform(0.30, 0.55),
                    cls=rng.choice([0, 1]),
                )
            )
        # Synthesize an inference timing (stub: ~1-3 ms — implausibly fast on
        # purpose; latency_bench.py is the real measurement tool).
        samples.append(
            FrameSample(
                image_id=f"stub_{i:03d}",
                detections=dets,
                ground_truths=gts,
                inference_ms=rng.uniform(1.0, 3.0),
            )
        )
    return samples


def collect_samples_ultralytics(
    checkpoint: str,
    dataset_root: Path,
    config: EvalConfig,
) -> list[FrameSample]:  # pragma: no cover - exercised only with ultralytics installed
    """Run the real model. Lazy import — never invoked from tests."""
    try:
        from ultralytics import YOLO  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "ultralytics not installed. Run with --checkpoint stub for a "
            "deterministic dry run, or install requirements.txt."
        ) from e

    model = YOLO(checkpoint)
    image_files = sorted(p for p in dataset_root.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if config.image_count_limit:
        image_files = image_files[: config.image_count_limit]

    samples: list[FrameSample] = []
    for img_path in image_files:
        t0 = time.perf_counter()
        results = model.predict(
            source=str(img_path),
            conf=config.conf_threshold,
            iou=config.iou_threshold,
            max_det=config.max_det_per_image,
            verbose=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        dets: list[Detection] = []
        for r in results:
            for box in r.boxes or []:
                xyxy = box.xyxy[0].tolist()
                dets.append(
                    Detection(
                        x1=xyxy[0],
                        y1=xyxy[1],
                        x2=xyxy[2],
                        y2=xyxy[3],
                        score=float(box.conf[0]),
                        cls=int(box.cls[0]),
                    )
                )
        gts = _load_yolo_labels(img_path)
        samples.append(
            FrameSample(
                image_id=img_path.stem,
                detections=dets,
                ground_truths=gts,
                inference_ms=elapsed_ms,
            )
        )
    return samples


def _load_yolo_labels(image_path: Path) -> list[GroundTruth]:  # pragma: no cover
    """Sibling .txt label file in YOLO format (cls cx cy w h, normalized).

    Returns absolute-pixel ground truths. Returns empty list if no labels.
    Image dims are read via PIL (lazy import).
    """
    label_path = image_path.with_suffix(".txt")
    if not label_path.exists():
        # Try the conventional images/ vs labels/ layout.
        try:
            label_path = Path(str(image_path).replace("/images/", "/labels/")).with_suffix(".txt")
        except Exception:
            return []
    if not label_path.exists():
        return []
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return []
    with Image.open(image_path) as im:
        w, h = im.size
    out: list[GroundTruth] = []
    for line in label_path.read_text().strip().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cls = int(parts[0])
        cx = float(parts[1]) * w
        cy = float(parts[2]) * h
        bw = float(parts[3]) * w
        bh = float(parts[4]) * h
        out.append(
            GroundTruth(
                x1=cx - bw / 2.0,
                y1=cy - bh / 2.0,
                x2=cx + bw / 2.0,
                y2=cy + bh / 2.0,
                cls=cls,
            )
        )
    return out


# ---------------------------------------------------------------------------
# CLI entrypoint.
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="wildfire-watch fire detector eval harness")
    p.add_argument("--checkpoint", required=True, help="Path to weights, or 'stub' for synthetic eval")
    p.add_argument("--dataset", required=True, help="Dataset name (fasdd | flame2 | dfire | stub)")
    p.add_argument("--data-root", default=None, help="Override dataset root (default ~/wildfire-watch-data/<name>/)")
    p.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    p.add_argument("--iou", type=float, default=0.50, help="IoU matching threshold")
    p.add_argument("--max-det", type=int, default=300)
    p.add_argument("--limit", type=int, default=None, help="Limit images for fast eval")
    p.add_argument("--output", type=Path, default=None, help="JSON output path")
    p.add_argument("--markdown", type=Path, default=None, help="Markdown output path")
    return p.parse_args()


def main() -> None:  # pragma: no cover - CLI wrapper
    args = parse_args()
    config = EvalConfig(
        checkpoint=args.checkpoint,
        dataset=args.dataset,
        conf_threshold=args.conf,
        iou_threshold=args.iou,
        max_det_per_image=args.max_det,
        image_count_limit=args.limit,
    )

    if args.checkpoint == "stub" or args.dataset == "stub":
        samples = collect_samples_stub(image_count=args.limit or 16)
        note = "stub-mode evaluation — synthetic samples, not a real model run."
    else:
        data_root = (
            Path(args.data_root)
            if args.data_root
            else Path.home() / "wildfire-watch-data" / args.dataset
        )
        if not data_root.exists():
            raise SystemExit(
                f"Dataset root {data_root} not found. "
                "Run: python3 -m ml.fire_detection.eval.prep_datasets prep "
                f"{args.dataset}"
            )
        samples = collect_samples_ultralytics(args.checkpoint, data_root, config)
        note = f"checkpoint={args.checkpoint}, dataset_root={data_root}"

    report = compute_eval_report(samples, config, note=note)
    payload = report.to_dict()
    print(json.dumps(payload, indent=2))
    print()
    print(report.to_markdown())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(report.to_markdown() + "\n")


if __name__ == "__main__":
    main()
