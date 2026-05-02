"""Kinematics tests — haversine round-trip, bearing math, dead-reckoning drift."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sim.kinematics import (  # noqa: E402
    haversine_m,
    heading_diff_deg,
    initial_bearing_deg,
    move_along_bearing,
)


def test_haversine_zero_distance():
    assert haversine_m(36.49, -121.18, 36.49, -121.18) == 0.0


def test_haversine_known_distance_one_degree_lat():
    # 1 degree of latitude is ~111.2 km regardless of longitude.
    d = haversine_m(0.0, 0.0, 1.0, 0.0)
    assert 111_000.0 < d < 111_400.0


def test_initial_bearing_due_north():
    b = initial_bearing_deg(0.0, 0.0, 1.0, 0.0)
    assert abs(b - 0.0) < 1e-6


def test_initial_bearing_due_east():
    b = initial_bearing_deg(0.0, 0.0, 0.0, 1.0)
    assert abs(b - 90.0) < 1e-6


def test_initial_bearing_due_south():
    b = initial_bearing_deg(1.0, 0.0, 0.0, 0.0)
    # Should be 180 deg from south to south, i.e. heading south = 180.
    assert abs(b - 180.0) < 1e-6


def test_initial_bearing_due_west():
    b = initial_bearing_deg(0.0, 1.0, 0.0, 0.0)
    assert abs(b - 270.0) < 1e-6


def test_move_along_bearing_zero_distance():
    lat, lon = move_along_bearing(36.49, -121.18, 90.0, 0.0)
    assert lat == 36.49 and lon == -121.18


def test_move_along_bearing_short_distance():
    # Moving 100 m east from a known point should land ~100 m east.
    lat0, lon0 = 36.4906, -121.1825
    lat1, lon1 = move_along_bearing(lat0, lon0, 90.0, 100.0)
    d = haversine_m(lat0, lon0, lat1, lon1)
    assert abs(d - 100.0) < 0.5
    # Latitude should not change appreciably for a due-east move.
    assert abs(lat1 - lat0) < 1e-5


def test_dead_reckoning_round_trip_1km_under_1m_drift():
    """Walk 1 km out, 1 km back, on multiple bearings. End point ~= start."""
    lat0, lon0 = 36.4906, -121.1825
    for bearing in (0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0):
        lat1, lon1 = move_along_bearing(lat0, lon0, bearing, 1000.0)
        # Reverse bearing.
        back = (bearing + 180.0) % 360.0
        lat2, lon2 = move_along_bearing(lat1, lon1, back, 1000.0)
        drift = haversine_m(lat0, lon0, lat2, lon2)
        # 1m budget over a 2 km out-and-back at any bearing.
        assert drift < 1.0, f"bearing {bearing}: drift={drift:.3f}m"


def test_heading_diff_basic():
    assert heading_diff_deg(0.0, 90.0) == 90.0
    assert heading_diff_deg(350.0, 10.0) == 20.0
    # Wrap the other way.
    assert heading_diff_deg(10.0, 350.0) == -20.0
    assert heading_diff_deg(0.0, 180.0) == 180.0


def test_haversine_symmetric():
    d1 = haversine_m(36.49, -121.18, 36.50, -121.17)
    d2 = haversine_m(36.50, -121.17, 36.49, -121.18)
    assert math.isclose(d1, d2, rel_tol=1e-12)
