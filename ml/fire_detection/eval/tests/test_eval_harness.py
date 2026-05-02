"""Tests for eval/eval_harness.py.

Strategy: build synthetic FrameSamples with known ground truth + predictions,
then assert that the metric outputs match what we hand-computed. This pins the
math so a future change to the IoU matcher or AP integrator can't silently
regress us.

No ultralytics dependency — all tests use the pure Python sample objects.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# eval is a sibling of fire_detection's tests; expose ml.fire_detection.eval.
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from ml.fire_detection.eval.eval_harness import (  # noqa: E402
    Detection,
    EvalConfig,
    FrameSample,
    GroundTruth,
    average_precision,
    collect_samples_stub,
    compute_eval_report,
    iou_xyxy,
    match_detections,
    precision_at_recall,
    precision_recall_curve,
)


# ---------------------------------------------------------------------------
# IoU primitive — load-bearing.
# ---------------------------------------------------------------------------


def test_iou_identical_boxes_is_1() -> None:
    box = (10, 20, 60, 80)
    assert iou_xyxy(box, box) == pytest.approx(1.0)


def test_iou_disjoint_is_0() -> None:
    a = (0, 0, 10, 10)
    b = (100, 100, 110, 110)
    assert iou_xyxy(a, b) == 0.0


def test_iou_half_overlap() -> None:
    # 100x100 vs 100x100 shifted by 50 in x: intersection 50x100, union 150x100.
    a = (0, 0, 100, 100)
    b = (50, 0, 150, 100)
    assert iou_xyxy(a, b) == pytest.approx((50 * 100) / (150 * 100))


# ---------------------------------------------------------------------------
# Greedy IoU matching.
# ---------------------------------------------------------------------------


def test_match_detections_perfect_alignment() -> None:
    gts = [GroundTruth(0, 0, 50, 50, cls=0), GroundTruth(100, 100, 150, 150, cls=1)]
    dets = [
        Detection(0, 0, 50, 50, score=0.9, cls=0),
        Detection(100, 100, 150, 150, score=0.85, cls=1),
    ]
    det_tp, gt_matched = match_detections(dets, gts, iou_threshold=0.5)
    assert det_tp == [True, True]
    assert gt_matched == [True, True]


def test_match_detections_class_mismatch_is_fp() -> None:
    gts = [GroundTruth(0, 0, 50, 50, cls=0)]
    dets = [Detection(0, 0, 50, 50, score=0.9, cls=1)]  # right box, wrong class
    det_tp, gt_matched = match_detections(dets, gts, iou_threshold=0.5)
    assert det_tp == [False]
    assert gt_matched == [False]


def test_match_detections_only_highest_score_takes_gt() -> None:
    gts = [GroundTruth(0, 0, 50, 50, cls=0)]
    dets = [
        Detection(0, 0, 50, 50, score=0.4, cls=0),
        Detection(0, 0, 50, 50, score=0.9, cls=0),
    ]
    det_tp, gt_matched = match_detections(dets, gts, iou_threshold=0.5)
    assert det_tp == [False, True], "lower-score duplicate must be a false positive"
    assert gt_matched == [True]


def test_match_detections_below_iou_is_fp() -> None:
    gts = [GroundTruth(0, 0, 100, 100, cls=0)]
    # Tiny corner overlap → IoU well below 0.5.
    dets = [Detection(80, 80, 130, 130, score=0.9, cls=0)]
    det_tp, gt_matched = match_detections(dets, gts, iou_threshold=0.5)
    assert det_tp == [False]
    assert gt_matched == [False]


# ---------------------------------------------------------------------------
# Precision-recall curve + AP.
# ---------------------------------------------------------------------------


def test_pr_curve_perfect_classifier() -> None:
    samples = [
        FrameSample(
            image_id="0",
            detections=[Detection(0, 0, 50, 50, score=0.99, cls=0)],
            ground_truths=[GroundTruth(0, 0, 50, 50, cls=0)],
        ),
        FrameSample(
            image_id="1",
            detections=[Detection(0, 0, 50, 50, score=0.97, cls=0)],
            ground_truths=[GroundTruth(0, 0, 50, 50, cls=0)],
        ),
    ]
    recalls, precisions, _ = precision_recall_curve(samples, iou_threshold=0.5)
    assert all(p == 1.0 for p in precisions)
    assert recalls[-1] == pytest.approx(1.0)
    assert average_precision(recalls, precisions) == pytest.approx(1.0)


def test_pr_curve_all_misses_zero_ap() -> None:
    samples = [
        FrameSample(
            image_id="0",
            detections=[Detection(500, 500, 550, 550, score=0.99, cls=0)],
            ground_truths=[GroundTruth(0, 0, 50, 50, cls=0)],
        ),
    ]
    recalls, precisions, _ = precision_recall_curve(samples, iou_threshold=0.5)
    assert average_precision(recalls, precisions) == 0.0


def test_precision_at_recall_080_attained() -> None:
    # Pretty-classifier: 9 of 10 GT recovered, 1 false positive at the bottom.
    samples = []
    for i in range(9):
        samples.append(
            FrameSample(
                image_id=f"hit{i}",
                detections=[Detection(0, 0, 50, 50, score=0.9 - 0.05 * i, cls=0)],
                ground_truths=[GroundTruth(0, 0, 50, 50, cls=0)],
            )
        )
    samples.append(
        FrameSample(
            image_id="miss",
            detections=[Detection(500, 500, 550, 550, score=0.45, cls=0)],
            ground_truths=[GroundTruth(0, 0, 50, 50, cls=0)],
        )
    )
    recalls, precisions, _ = precision_recall_curve(samples, iou_threshold=0.5)
    p_at_r80 = precision_at_recall(recalls, precisions, 0.80)
    assert p_at_r80 == pytest.approx(1.0), (
        "should reach recall 0.80 at the top of the curve before any FP"
    )


# ---------------------------------------------------------------------------
# Full eval report shape.
# ---------------------------------------------------------------------------


def test_compute_eval_report_perfect_classifier_metrics_are_one() -> None:
    samples = [
        FrameSample(
            image_id=f"img{i}",
            detections=[Detection(0, 0, 50, 50, score=0.95, cls=0)],
            ground_truths=[GroundTruth(0, 0, 50, 50, cls=0)],
            inference_ms=1.0 + i * 0.1,
        )
        for i in range(8)
    ]
    config = EvalConfig(checkpoint="stub", dataset="stub", conf_threshold=0.25)
    report = compute_eval_report(samples, config)
    assert report.precision == pytest.approx(1.0)
    assert report.recall == pytest.approx(1.0)
    assert report.f1 == pytest.approx(1.0)
    assert report.map_50 == pytest.approx(1.0)
    assert report.precision_at_recall_080 == pytest.approx(1.0)
    assert report.image_count == 8
    assert report.latency_ms["p50"] > 0.0


def test_compute_eval_report_serializes_to_json() -> None:
    import json as _json

    samples = collect_samples_stub(image_count=6, seed=0)
    config = EvalConfig(checkpoint="stub", dataset="stub")
    report = compute_eval_report(samples, config, note="unit-test run")
    text = _json.dumps(report.to_dict())
    parsed = _json.loads(text)
    assert "metrics" in parsed
    assert "map_50" in parsed["metrics"]
    assert parsed["note"] == "unit-test run"


def test_compute_eval_report_markdown_includes_target_metric() -> None:
    samples = collect_samples_stub(image_count=4, seed=1)
    config = EvalConfig(checkpoint="stub", dataset="stub")
    md = compute_eval_report(samples, config).to_markdown()
    assert "Precision @ Recall=0.80" in md
    assert "mAP@50" in md
    assert "mAP@50:95" in md


def test_collect_samples_stub_is_deterministic() -> None:
    a = collect_samples_stub(image_count=4, seed=42)
    b = collect_samples_stub(image_count=4, seed=42)
    assert len(a) == len(b)
    for sa, sb in zip(a, b, strict=True):
        assert sa.image_id == sb.image_id
        assert len(sa.detections) == len(sb.detections)
        assert len(sa.ground_truths) == len(sb.ground_truths)


def test_compute_eval_report_handles_empty_samples() -> None:
    config = EvalConfig(checkpoint="stub", dataset="stub")
    report = compute_eval_report([], config)
    assert report.image_count == 0
    assert report.map_50 == 0.0
    assert report.precision == 0.0
    assert report.recall == 0.0


def test_per_class_metrics_have_two_classes() -> None:
    samples = collect_samples_stub(image_count=12, seed=7)
    config = EvalConfig(checkpoint="stub", dataset="stub", class_names=("fire", "smoke"))
    report = compute_eval_report(samples, config)
    assert set(report.per_class.keys()) == {"fire", "smoke"}
    for cls_name, m in report.per_class.items():
        assert 0.0 <= m["ap_50"] <= 1.0, cls_name
