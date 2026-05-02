"""Tests for ComplementaryFusion."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from sim.perception.fusion import (  # noqa: E402
    ComplementaryFusion,
    GPSReading,
    TRNReadingForFusion,
    VOReadingForFusion,
)
from sim.perception.inertial import InertialDeadReckoner  # noqa: E402
from sim.perception.visual_odometry import VisualOdometry  # noqa: E402


def _meters_apart(lat1, lon1, lat2, lon2):
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    cos_phi = max(1e-6, math.cos(math.radians(lat1)))
    return math.hypot(dlat * 111_320.0, dlon * 111_320.0 * cos_phi)


def test_with_clean_gps_fused_tracks_truth():
    """When GPS is healthy and recent, fused position == GPS within
    a few meters."""
    fusion = ComplementaryFusion(init_lat=38.91, init_lon=-107.0)
    imu = InertialDeadReckoner(seed=0)
    truth_lat, truth_lon = 38.91, -107.0
    dt = 0.1
    for _ in range(100):  # 10 s of clean GPS
        # Move 0.6 m east per tick.
        truth_lon += 0.6 / (111_320.0 * math.cos(math.radians(truth_lat)))
        step = imu.propagate(dt, truth_dx_m=0.6, truth_dy_m=0.0)
        fusion.predict(
            dt,
            truth_dx_m=0.6,
            truth_dy_m=0.0,
            imu_step=step,
            truth_lat=truth_lat,
            truth_lon=truth_lon,
        )
        fusion.update_gps(
            GPSReading(
                lat=truth_lat,
                lon=truth_lon,
                sigma_m=1.5,
                available=True,
                trusted=True,
            )
        )
    err = _meters_apart(truth_lat, truth_lon, fusion.fused_lat, fusion.fused_lon)
    assert err < 3.0, f"clean-GPS fused err {err:.2f} m"


def test_with_gps_lost_for_30s_vo_carries_under_5m():
    """30 s GPS outage with VO running -> fused drift < 5 m."""
    fusion = ComplementaryFusion(init_lat=38.91, init_lon=-107.0)
    imu = InertialDeadReckoner(seed=0)
    vo = VisualOdometry(seed=0)
    truth_lat, truth_lon = 38.91, -107.0
    dt = 0.1
    # 5 s of clean GPS to seed the filter.
    for _ in range(50):
        truth_lon += 0.6 / (111_320.0 * math.cos(math.radians(truth_lat)))
        step = imu.propagate(dt, truth_dx_m=0.6, truth_dy_m=0.0)
        fusion.predict(
            dt, truth_dx_m=0.6, truth_dy_m=0.0,
            imu_step=step, truth_lat=truth_lat, truth_lon=truth_lon,
        )
        fusion.update_gps(
            GPSReading(lat=truth_lat, lon=truth_lon, sigma_m=1.5,
                       available=True, trusted=True)
        )
        vo_r = vo.tick(
            truth_dx_m=0.6, truth_dy_m=0.0,
            altitude_agl_m=80.0, scene_complexity=0.7, smoke_density=0.0,
        )
        fusion.update_vo(VOReadingForFusion(
            dx_m=vo_r.dx_m, dy_m=vo_r.dy_m,
            sigma_m=vo_r.sigma_m, lock_ok=vo_r.lock_ok,
        ))
    # 30 s GPS outage; VO continues.
    for _ in range(300):
        truth_lon += 0.6 / (111_320.0 * math.cos(math.radians(truth_lat)))
        step = imu.propagate(dt, truth_dx_m=0.6, truth_dy_m=0.0)
        fusion.predict(
            dt, truth_dx_m=0.6, truth_dy_m=0.0,
            imu_step=step, truth_lat=truth_lat, truth_lon=truth_lon,
        )
        # GPS unavailable - call with available=False (should be no-op).
        fusion.update_gps(
            GPSReading(lat=0.0, lon=0.0, sigma_m=0.0,
                       available=False, trusted=True)
        )
        vo_r = vo.tick(
            truth_dx_m=0.6, truth_dy_m=0.0,
            altitude_agl_m=80.0, scene_complexity=0.7, smoke_density=0.0,
        )
        fusion.update_vo(VOReadingForFusion(
            dx_m=vo_r.dx_m, dy_m=vo_r.dy_m,
            sigma_m=vo_r.sigma_m, lock_ok=vo_r.lock_ok,
        ))
    err = _meters_apart(truth_lat, truth_lon, fusion.fused_lat, fusion.fused_lon)
    assert err < 5.0, f"30s outage fused err {err:.2f} m exceeds 5 m"


def test_trn_correction_pulls_back_to_truth():
    """A TRN lock should yank the fused state back near truth even
    after IMU+VO have drifted."""
    fusion = ComplementaryFusion(init_lat=38.91, init_lon=-107.0)
    # Manually inject some drift.
    fusion.fused_lat = 38.9105  # ~55 m north
    fusion.fused_sigma_m = 30.0
    truth_lat, truth_lon = 38.91, -107.0
    fusion.update_trn(TRNReadingForFusion(
        lat=truth_lat, lon=truth_lon, sigma_m=5.0, lock_ok=True,
    ))
    err = _meters_apart(truth_lat, truth_lon, fusion.fused_lat, fusion.fused_lon)
    assert err < 10.0


def test_untrusted_gps_does_not_pull_fused():
    """A spoofed (untrusted) GPS reading must NOT move fused_lat."""
    fusion = ComplementaryFusion(init_lat=38.91, init_lon=-107.0)
    fusion.update_gps(GPSReading(
        lat=38.7, lon=-107.05, sigma_m=1.5,
        available=True, trusted=False,
    ))
    # fused_lat should NOT have jumped to the spoof location.
    assert abs(fusion.fused_lat - 38.91) < 0.001
    # And the sigma should be elevated.
    assert fusion.fused_sigma_m >= 25.0


def test_predict_only_uses_imu_noise():
    """With no GPS/VO/TRN updates, predict() should grow uncertainty."""
    fusion = ComplementaryFusion(init_lat=38.91, init_lon=-107.0)
    imu = InertialDeadReckoner(seed=0)
    s0 = fusion.fused_sigma_m
    for _ in range(100):
        step = imu.propagate(0.1, truth_dx_m=0.6, truth_dy_m=0.0)
        fusion.predict(
            0.1, truth_dx_m=0.6, truth_dy_m=0.0,
            imu_step=step, truth_lat=38.91, truth_lon=-107.0,
        )
    assert fusion.fused_sigma_m > s0
