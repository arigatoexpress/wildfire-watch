"""Tests for the real-image bench."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent  # eval/real_bench/
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(REPO_ROOT))

from ml.fire_detection.eval.real_bench import bench  # noqa: E402


def test_load_inference_works() -> None:
    """v0.0.1 inference module loads and exposes predict_image."""
    inf = bench._load_inference()
    assert hasattr(inf, "predict_image")
    assert hasattr(inf, "Detection")


def test_load_labels_round_trip() -> None:
    """The committed labels.yaml parses as a list of label entries."""
    pytest.importorskip("yaml")
    labels = bench._load_labels(HERE / "labels.yaml")
    assert len(labels) == 12
    for entry in labels:
        assert "filename" in entry
        assert "expected_class" in entry
        assert "notes" in entry


def test_verdict_classifications() -> None:
    # True positive: expected smoke, got smoke at adequate score
    assert bench._verdict("smoke", "smoke", 0.7, 0.5) == "TP"
    # OOR: expected smoke, got smoke but below floor
    assert bench._verdict("smoke", "smoke", 0.3, 0.5) == "OOR"
    # FN: expected fire, got none
    assert bench._verdict("fire", "none", 0.0, 0.5) == "FN"
    # FP: expected none, got fire
    assert bench._verdict("none", "fire", 0.7, None) == "FP"
    # TN: expected wildlife, got none (correct rejection)
    assert bench._verdict("wildlife", "none", 0.0, None) == "TN"
    # No floor + correct family = TP (no OOR check)
    assert bench._verdict("fire", "fire", 0.1, None) == "TP"


def test_run_bench_against_real_images() -> None:
    """End-to-end against the 12 committed images. PIL must be installed."""
    pytest.importorskip("PIL")
    pytest.importorskip("yaml")
    results = bench.run_bench(HERE / "images", HERE / "labels.yaml")
    assert len(results) == 12
    # Every result has a verdict in the closed set.
    valid = {"TP", "FP", "FN", "TN", "OOR"}
    for r in results:
        assert r.verdict in valid, f"{r.filename}: bad verdict {r.verdict}"
    # The detector has nonzero latency on real images.
    assert all(r.latency_ms > 0 or r.predicted_class == "error" for r in results)


def test_aggregate_shape() -> None:
    pytest.importorskip("PIL")
    pytest.importorskip("yaml")
    results = bench.run_bench(HERE / "images", HERE / "labels.yaml")
    agg = bench.aggregate(results)
    for k in (
        "total", "tp", "fp", "fn", "tn", "oor",
        "precision", "recall", "f1", "mean_latency_ms",
    ):
        assert k in agg
    assert agg["total"] == 12
    # Total verdicts sum to total images.
    assert agg["tp"] + agg["fp"] + agg["fn"] + agg["tn"] + agg["oor"] == agg["total"]
    # Fire/smoke recall should be perfect or near-perfect on this curated set.
    assert agg["recall"] >= 0.8


def test_render_report_contains_required_sections() -> None:
    pytest.importorskip("PIL")
    pytest.importorskip("yaml")
    results = bench.run_bench(HERE / "images", HERE / "labels.yaml")
    agg = bench.aggregate(results)
    report = bench.render_report(
        results, agg, HERE / "images", license_block="CC-BY-4.0 placeholder."
    )
    for section in (
        "# wildfire-watch real-image bench",
        "## Aggregate",
        "## Per-image results",
        "## Failure mode analysis",
        "## Recommendations for v0.1.0",
        "## License attribution",
    ):
        assert section in report, f"missing section: {section!r}"


def test_main_writes_report(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    pytest.importorskip("yaml")
    out = tmp_path / "report.md"
    rc = bench.main(["--out", str(out)])
    assert rc == 0
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "wildfire-watch real-image bench" in text
