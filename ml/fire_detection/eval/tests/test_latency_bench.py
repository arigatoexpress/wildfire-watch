"""Tests for eval/latency_bench.py.

We don't have a Jetson on the test runner, so all tests use stub mode. The
stub generates a deterministic distribution and the build_report glue computes
percentiles + applies the configured speedup factor. We assert:
  - the report shape
  - the recommendation logic
  - the targets.yaml load path (with and without pyyaml)
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from ml.fire_detection.eval.latency_bench import (  # noqa: E402
    BenchConfig,
    build_report,
    estimate_jetson_latency,
    load_targets,
    summarize_latencies,
    time_runs_stub,
)


def test_summarize_latencies_basic_percentiles() -> None:
    timings = [10.0, 20.0, 30.0, 40.0, 50.0]
    summary = summarize_latencies(timings)
    assert summary["p50"] == 30.0
    assert summary["min"] == 10.0
    assert summary["max"] == 50.0
    assert summary["n"] == 5.0


def test_summarize_latencies_empty_safe() -> None:
    summary = summarize_latencies([])
    assert summary["p50"] == 0.0
    assert summary["n"] == 0.0


def test_estimate_jetson_latency_applies_factor() -> None:
    cpu = {"p50": 90.0, "p95": 110.0, "p99": 150.0}
    estimated = estimate_jetson_latency(cpu, speedup_factor=4.5)
    assert estimated["p50"] == 20.0
    assert estimated["p95"] == 110.0 / 4.5
    assert estimated["p99"] == 150.0 / 4.5


def test_estimate_jetson_latency_zero_speedup_returns_zeros() -> None:
    cpu = {"p50": 90.0, "p95": 110.0}
    estimated = estimate_jetson_latency(cpu, speedup_factor=0.0)
    assert all(v == 0.0 for v in estimated.values())


def test_load_targets_returns_speedup_factor() -> None:
    targets_path = Path(__file__).resolve().parents[1] / "targets.yaml"
    loaded = load_targets(targets_path)
    assert "latency" in loaded
    assert "cpu_to_jetson_fp16_speedup_factor" in loaded["latency"]
    assert "jetson_orin_super_fp16_p95_ms" in loaded["latency"]
    assert loaded["latency"]["cpu_to_jetson_fp16_speedup_factor"] > 0


def test_time_runs_stub_is_deterministic_and_positive() -> None:
    config = BenchConfig(checkpoint="stub", bench_runs=20)
    a = time_runs_stub(config, seed=0)
    b = time_runs_stub(config, seed=0)
    assert a == b
    assert all(t > 0 for t in a)
    assert len(a) == 20


def test_build_report_stub_path_returns_inconclusive() -> None:
    config = BenchConfig(checkpoint="stub", bench_runs=20)
    timings = time_runs_stub(config, seed=0)
    report = build_report(config, timings, stub=True)
    assert report.recommendation == "stub_run_inconclusive"
    assert report.cpu_latency_ms["p95"] > 0.0
    assert report.jetson_estimate_ms["p95"] > 0.0
    assert report.speedup_factor > 0.0
    assert "STUB" in report.note


def test_build_report_real_path_below_target_recommends_deployment() -> None:
    """Force a fast CPU distribution → estimated Jetson p95 well under 25 ms."""
    config = BenchConfig(checkpoint="/tmp/fake.pt", bench_runs=10)
    fast_timings = [40.0, 41.0, 42.0, 43.0, 44.0, 45.0, 46.0, 47.0, 48.0, 49.0]
    report = build_report(config, fast_timings, stub=False)
    assert report.recommendation == "ready_for_jetson_fp16_deployment"
    assert report.jetson_estimate_ms["p95"] < report.jetson_target_p95_ms


def test_build_report_real_path_above_target_recommends_optimization() -> None:
    config = BenchConfig(checkpoint="/tmp/fake.pt", bench_runs=10)
    slow_timings = [400.0] * 10
    report = build_report(config, slow_timings, stub=False)
    assert report.recommendation == "needs_optimization"
    assert report.jetson_estimate_ms["p95"] > report.jetson_target_p95_ms


def test_build_report_to_dict_round_trips() -> None:
    import json as _json

    config = BenchConfig(checkpoint="stub", bench_runs=12)
    timings = time_runs_stub(config, seed=1)
    report = build_report(config, timings, stub=True)
    payload = report.to_dict()
    text = _json.dumps(payload)
    parsed = _json.loads(text)
    assert parsed["recommendation"] == "stub_run_inconclusive"
    assert parsed["cpu_latency_ms"]["p95"] == report.cpu_latency_ms["p95"]
