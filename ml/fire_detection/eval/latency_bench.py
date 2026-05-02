"""wildfire-watch fire/smoke detector — inference latency benchmark.

Measures inference latency on the local machine (Mac CPU, on the developer's
laptop) and estimates the corresponding Jetson Orin Nano Super FP16 TensorRT
latency by applying a documented scaling factor.

Usage:
    python3 -m ml.fire_detection.eval.latency_bench \\
        --checkpoint runs/wildfire_yolo/weights/best.pt \\
        --imgsz 640 --batch 1 --warmup 5 --runs 50

    # Stub run (no ultralytics required):
    python3 -m ml.fire_detection.eval.latency_bench --checkpoint stub --runs 25

The scaling factor is configured in `eval/targets.yaml` under
`latency.cpu_to_jetson_fp16_speedup_factor`. The default value is 4.5x and is
based on Ultralytics' published Jetson Orin Nano Super benchmarks for YOLOv8n
@ 640x640 (FP16 TRT typically lands ~3-6x faster than a Mac CPU forward pass
at the same batch size; we use the conservative midpoint). The estimate is
rough — replace with a real Jetson measurement when hardware is available.

Returns a recommendation:
    - "ready_for_jetson_fp16_deployment" if estimated p95 <= target.
    - "needs_optimization" if estimated p95 > target.
    - "stub_run_inconclusive" for stub runs (latency floor is fake).
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

DEFAULT_TARGETS_PATH = Path(__file__).parent / "targets.yaml"


@dataclass
class BenchConfig:
    checkpoint: str
    imgsz: int = 640
    batch: int = 1
    warmup_runs: int = 5
    bench_runs: int = 50
    targets_path: Path = field(default_factory=lambda: DEFAULT_TARGETS_PATH)


@dataclass
class BenchReport:
    config: BenchConfig
    cpu_latency_ms: dict[str, float]
    jetson_estimate_ms: dict[str, float]
    speedup_factor: float
    jetson_target_p95_ms: float
    recommendation: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": {
                "checkpoint": self.config.checkpoint,
                "imgsz": self.config.imgsz,
                "batch": self.config.batch,
                "warmup_runs": self.config.warmup_runs,
                "bench_runs": self.config.bench_runs,
            },
            "cpu_latency_ms": self.cpu_latency_ms,
            "jetson_estimate_ms": self.jetson_estimate_ms,
            "speedup_factor": self.speedup_factor,
            "jetson_target_p95_ms": self.jetson_target_p95_ms,
            "recommendation": self.recommendation,
            "note": self.note,
        }


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


def summarize_latencies(timings_ms: list[float]) -> dict[str, float]:
    if not timings_ms:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0, "n": 0.0}
    s = sorted(timings_ms)
    return {
        "p50": _percentile(s, 50),
        "p95": _percentile(s, 95),
        "p99": _percentile(s, 99),
        "mean": statistics.fmean(s),
        "min": s[0],
        "max": s[-1],
        "n": float(len(s)),
    }


def estimate_jetson_latency(cpu_latency_ms: dict[str, float], speedup_factor: float) -> dict[str, float]:
    if speedup_factor <= 0.0:
        return {k: 0.0 for k in cpu_latency_ms}
    return {k: v / speedup_factor for k, v in cpu_latency_ms.items()}


def load_targets(targets_path: Path) -> dict[str, Any]:
    """Lazy-import yaml, with a stdlib fallback for the two values we need."""
    text = targets_path.read_text()
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ImportError:
        # Stdlib fallback: parse only the two scalar values we need. This keeps
        # latency_bench fully usable in environments without pyyaml installed.
        out: dict[str, Any] = {"latency": {}}
        in_latency = False
        for raw in text.splitlines():
            line = raw.rstrip()
            if line.startswith("latency:"):
                in_latency = True
                continue
            if in_latency:
                if line and not line.startswith(" "):
                    in_latency = False
                    continue
                stripped = line.strip()
                if stripped.startswith("jetson_orin_super_fp16_p95_ms:"):
                    out["latency"]["jetson_orin_super_fp16_p95_ms"] = float(
                        stripped.split(":", 1)[1].strip()
                    )
                elif stripped.startswith("cpu_to_jetson_fp16_speedup_factor:"):
                    out["latency"]["cpu_to_jetson_fp16_speedup_factor"] = float(
                        stripped.split(":", 1)[1].strip()
                    )
        return out


def time_runs_stub(config: BenchConfig, seed: int = 0) -> list[float]:
    """Deterministic timing list for tests + when ultralytics is missing.

    Synthesizes a plausible Mac-mini-CPU latency distribution for YOLOv8n @ 640x640:
    mean ~95 ms, mild right-skew. The numbers are illustrative — see latency_bench
    docstring on why we don't claim them as a real measurement.
    """
    import random

    rng = random.Random(seed)
    base_mean = 95.0
    return [
        max(40.0, base_mean + rng.gauss(0.0, 6.0) + (rng.expovariate(0.2) if rng.random() < 0.05 else 0.0))
        for _ in range(config.bench_runs)
    ]


def time_runs_ultralytics(config: BenchConfig) -> list[float]:  # pragma: no cover
    """Real measurement. Lazy-imports ultralytics + numpy."""
    try:
        from ultralytics import YOLO  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "ultralytics + numpy required for real bench. Use --checkpoint stub."
        ) from e
    model = YOLO(config.checkpoint)
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, size=(config.imgsz, config.imgsz, 3), dtype=np.uint8)
    # Warmup.
    for _ in range(config.warmup_runs):
        model.predict(source=img, verbose=False)
    timings: list[float] = []
    for _ in range(config.bench_runs):
        t0 = time.perf_counter()
        model.predict(source=img, verbose=False)
        timings.append((time.perf_counter() - t0) * 1000.0)
    return timings


def build_report(config: BenchConfig, cpu_timings_ms: list[float], stub: bool) -> BenchReport:
    targets = load_targets(config.targets_path)
    speedup = float(
        targets.get("latency", {}).get("cpu_to_jetson_fp16_speedup_factor", 4.5)
    )
    target_p95 = float(targets.get("latency", {}).get("jetson_orin_super_fp16_p95_ms", 25.0))

    cpu = summarize_latencies(cpu_timings_ms)
    jetson_est = estimate_jetson_latency(cpu, speedup)

    if stub:
        recommendation = "stub_run_inconclusive"
    elif jetson_est["p95"] <= target_p95:
        recommendation = "ready_for_jetson_fp16_deployment"
    else:
        recommendation = "needs_optimization"

    note_parts = [
        f"speedup_factor={speedup}x (CPU→Jetson FP16, see eval/targets.yaml)",
        f"target_p95={target_p95}ms",
    ]
    if stub:
        note_parts.append("STUB run — replace with real Jetson measurement before claiming the target.")
    return BenchReport(
        config=config,
        cpu_latency_ms=cpu,
        jetson_estimate_ms=jetson_est,
        speedup_factor=speedup,
        jetson_target_p95_ms=target_p95,
        recommendation=recommendation,
        note=" | ".join(note_parts),
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="wildfire-watch latency benchmark")
    p.add_argument("--checkpoint", required=True, help="Path to weights or 'stub'.")
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--runs", type=int, default=50)
    p.add_argument("--targets", type=Path, default=DEFAULT_TARGETS_PATH)
    p.add_argument("--output", type=Path, default=None)
    return p.parse_args()


def main() -> None:  # pragma: no cover
    args = parse_args()
    config = BenchConfig(
        checkpoint=args.checkpoint,
        imgsz=args.imgsz,
        batch=args.batch,
        warmup_runs=args.warmup,
        bench_runs=args.runs,
        targets_path=args.targets,
    )
    stub = args.checkpoint == "stub"
    if stub:
        cpu_timings = time_runs_stub(config)
    else:
        cpu_timings = time_runs_ultralytics(config)
    report = build_report(config, cpu_timings, stub=stub)
    payload = report.to_dict()
    print(json.dumps(payload, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
