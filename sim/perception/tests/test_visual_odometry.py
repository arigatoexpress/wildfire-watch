"""Tests for the mock VisualOdometry sensor."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from sim.perception.visual_odometry import VisualOdometry  # noqa: E402


def _integrate_drift(
    vo: VisualOdometry,
    *,
    duration_s: float,
    dt: float,
    truth_step_m: float,
    altitude_agl_m: float,
    scene_complexity: float,
    smoke_density: float,
) -> float:
    """Integrate per-tick VO output for `duration_s` seconds and return
    the magnitude of (estimated_displacement - truth_displacement)."""
    n_ticks = int(duration_s / dt)
    est_x = 0.0
    est_y = 0.0
    truth_x = 0.0
    truth_y = 0.0
    for _ in range(n_ticks):
        truth_dx = truth_step_m * dt
        truth_dy = 0.0  # all motion eastward
        reading = vo.tick(
            truth_dx_m=truth_dx,
            truth_dy_m=truth_dy,
            altitude_agl_m=altitude_agl_m,
            scene_complexity=scene_complexity,
            smoke_density=smoke_density,
        )
        if not reading.lock_ok:
            return float("inf")
        est_x += reading.dx_m
        est_y += reading.dy_m
        truth_x += truth_dx
        truth_y += truth_dy
    return math.hypot(est_x - truth_x, est_y - truth_y)


def test_drift_under_clean_conditions_under_six_meters():
    """At 80 m AGL, scene complexity 0.7, no smoke, 6 m/s cruise (= 1 m/s
    truth-step at dt=1.0/6), drift over 60 s must stay under 6 m.

    This is the Bavovna AI 1%-of-distance budget: 60 s * 6 m/s = 360 m
    traveled, 1% = 3.6 m. We allow 6 m to leave headroom for noise.
    """
    vo = VisualOdometry(seed=42)
    drift = _integrate_drift(
        vo,
        duration_s=60.0,
        dt=0.1,  # 10 Hz
        truth_step_m=6.0,  # 6 m/s
        altitude_agl_m=80.0,
        scene_complexity=0.7,
        smoke_density=0.0,
    )
    assert drift < 6.0, f"drift {drift:.2f} m exceeds 6 m budget"


def test_lock_lost_under_heavy_smoke():
    """smoke_density >= 0.85 -> lock_ok False, drift undefined."""
    vo = VisualOdometry(seed=42)
    reading = vo.tick(
        truth_dx_m=1.0,
        truth_dy_m=0.0,
        altitude_agl_m=80.0,
        scene_complexity=0.7,
        smoke_density=1.0,
    )
    assert not reading.lock_ok
    assert reading.sigma_m == float("inf")


def test_higher_altitude_increases_drift():
    """Drift at 160 m AGL should exceed drift at 80 m, all else equal."""
    drift_low = _integrate_drift(
        VisualOdometry(seed=7),
        duration_s=30.0,
        dt=0.1,
        truth_step_m=6.0,
        altitude_agl_m=80.0,
        scene_complexity=0.7,
        smoke_density=0.0,
    )
    drift_high = _integrate_drift(
        VisualOdometry(seed=7),
        duration_s=30.0,
        dt=0.1,
        truth_step_m=6.0,
        altitude_agl_m=160.0,
        scene_complexity=0.7,
        smoke_density=0.0,
    )
    assert drift_high > drift_low


def test_low_complexity_increases_drift():
    """Featureless scene (complexity 0.1) drifts more than rich (0.9)."""
    drift_rich = _integrate_drift(
        VisualOdometry(seed=11),
        duration_s=30.0,
        dt=0.1,
        truth_step_m=6.0,
        altitude_agl_m=80.0,
        scene_complexity=0.9,
        smoke_density=0.0,
    )
    drift_poor = _integrate_drift(
        VisualOdometry(seed=11),
        duration_s=30.0,
        dt=0.1,
        truth_step_m=6.0,
        altitude_agl_m=80.0,
        scene_complexity=0.1,
        smoke_density=0.0,
    )
    assert drift_poor > drift_rich
