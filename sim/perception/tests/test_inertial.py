"""Tests for the InertialDeadReckoner random-walk model."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from sim.perception.inertial import InertialDeadReckoner  # noqa: E402


def _drift_after_seconds(seed: int, duration_s: float, dt: float) -> float:
    """Integrate pure-INS over `duration_s` seconds (no truth motion).
    Returns final position drift magnitude in meters."""
    imu = InertialDeadReckoner(seed=seed)
    x = 0.0
    y = 0.0
    n = int(duration_s / dt)
    for _ in range(n):
        step = imu.propagate(dt, truth_dx_m=0.0, truth_dy_m=0.0)
        x += step.dx_m
        y += step.dy_m
    return math.hypot(x, y)


def test_pure_ins_drifts_within_expected_envelope():
    """Mean drift over many seeds should land in [3, 60] m at 60 s.

    Loose bounds — the random-walk variance has a long tail. We are
    checking the order-of-magnitude is right, not a tight CI.
    """
    drifts = [_drift_after_seconds(s, duration_s=60.0, dt=0.1) for s in range(40)]
    mean = sum(drifts) / len(drifts)
    assert 3.0 < mean < 60.0, f"mean 60s drift {mean:.2f} m out of envelope"


def test_drift_grows_with_time():
    """Drift at 60 s should exceed drift at 10 s, on average."""
    drifts_10 = [_drift_after_seconds(s, duration_s=10.0, dt=0.1) for s in range(20)]
    drifts_60 = [_drift_after_seconds(s, duration_s=60.0, dt=0.1) for s in range(20)]
    mean10 = sum(drifts_10) / len(drifts_10)
    mean60 = sum(drifts_60) / len(drifts_60)
    assert mean60 > mean10


def test_reset_unaided_clears_clock():
    imu = InertialDeadReckoner(seed=0)
    for _ in range(50):
        imu.propagate(0.1)
    assert imu.unaided_seconds > 0.0
    imu.reset_unaided()
    assert imu.unaided_seconds == 0.0


def test_truth_displacement_is_added_to_output():
    """Output dx/dy should include the truth-step plus noise."""
    imu = InertialDeadReckoner(seed=0)
    step = imu.propagate(0.1, truth_dx_m=10.0, truth_dy_m=0.0)
    # noise on a single tick is tiny; truth dominates.
    assert abs(step.dx_m - 10.0) < 1.0
