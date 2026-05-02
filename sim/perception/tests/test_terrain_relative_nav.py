"""Tests for the mock TerrainRelativeNav sensor."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from sim.perception.terrain_relative_nav import TerrainRelativeNav  # noqa: E402


def _meters_apart(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Quick equirectangular metric distance — fine for ~5 m scale tests."""
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    cos_phi = max(1e-6, math.cos(math.radians(lat1)))
    return math.hypot(dlat * 111_320.0, dlon * 111_320.0 * cos_phi)


def test_lock_returns_position_within_10m():
    trn = TerrainRelativeNav(seed=0, update_period_s=2.0)
    truth_lat, truth_lon = 38.91, -107.0
    # Step forward enough ticks to trigger an update.
    reading = None
    for _ in range(25):
        r = trn.step(
            dt=0.1,
            truth_lat=truth_lat,
            truth_lon=truth_lon,
            altitude_agl_m=80.0,
            canopy_density=0.2,
            smoke_density=0.0,
            water_fraction=0.0,
        )
        if r is not None:
            reading = r
            break
    assert reading is not None
    assert reading.lock_ok
    err = _meters_apart(truth_lat, truth_lon, reading.lat, reading.lon)
    assert err < 10.0, f"TRN error {err:.2f} m exceeds 10 m"


def test_no_correction_under_heavy_canopy():
    trn = TerrainRelativeNav(seed=0, update_period_s=2.0)
    reading = None
    for _ in range(25):
        r = trn.step(
            dt=0.1,
            truth_lat=38.91,
            truth_lon=-107.0,
            altitude_agl_m=80.0,
            canopy_density=1.0,
            smoke_density=0.0,
            water_fraction=0.0,
        )
        if r is not None:
            reading = r
            break
    assert reading is not None
    assert not reading.lock_ok


def test_no_correction_below_minimum_altitude():
    trn = TerrainRelativeNav(seed=0, update_period_s=2.0)
    reading = None
    for _ in range(25):
        r = trn.step(
            dt=0.1,
            truth_lat=38.91,
            truth_lon=-107.0,
            altitude_agl_m=10.0,  # too low
            canopy_density=0.0,
            smoke_density=0.0,
            water_fraction=0.0,
        )
        if r is not None:
            reading = r
            break
    assert reading is not None
    assert not reading.lock_ok


def test_update_period_respected():
    """Within one update_period_s we should get exactly one reading."""
    trn = TerrainRelativeNav(seed=0, update_period_s=2.0)
    readings = []
    for _ in range(19):  # 19 * 0.1 = 1.9 s, no update yet
        r = trn.step(
            dt=0.1,
            truth_lat=38.91,
            truth_lon=-107.0,
            altitude_agl_m=80.0,
            canopy_density=0.0,
            smoke_density=0.0,
            water_fraction=0.0,
        )
        if r is not None:
            readings.append(r)
    assert len(readings) == 0
    # One more tick crosses 2.0 s.
    r = trn.step(
        dt=0.1,
        truth_lat=38.91,
        truth_lon=-107.0,
        altitude_agl_m=80.0,
        canopy_density=0.0,
        smoke_density=0.0,
        water_fraction=0.0,
    )
    assert r is not None
