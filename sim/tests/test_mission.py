"""Mission YAML round-trip + waypoint count + ground-distance budget tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sim.mission import load_mission, parse_mission_dict  # noqa: E402

MONTEREY_PATH = Path(__file__).resolve().parent.parent / "missions" / "monterey_pinnacles_east_1km2.yaml"


def test_canonical_mission_loads():
    m = load_mission(MONTEREY_PATH)
    assert m.name == "monterey-pinnacles-east-1km2"
    assert m.zone_id == "monterey-pinnacles-east"
    assert m.airframe_name == "mavic_mini_2"
    assert len(m.waypoints) == 8


def test_canonical_mission_returns_to_home():
    m = load_mission(MONTEREY_PATH)
    assert m.return_to_home is True


def test_canonical_mission_battery_budget_fits():
    """Total ground distance / cruise speed must fit in mavic_mini_2 31-min budget."""
    m = load_mission(MONTEREY_PATH)
    assert m.battery_budget_ok(reserve_minutes=5.0)
    # The 1km^2 survey should not be more than ~2km of ground travel.
    assert m.total_ground_distance_m() < 2_500.0


def test_parse_minimal_dict():
    data = {
        "name": "test",
        "zone_id": "z",
        "home": {"lat": 36.0, "lon": -121.0, "alt_msl_m": 0.0},
        "airframe": "mavic_mini_2",
        "waypoints": [
            {"lat": 36.001, "lon": -121.001, "alt_agl_m": 80, "action": "capture"},
        ],
        "return_to_home": False,
    }
    m = parse_mission_dict(data)
    assert len(m.waypoints) == 1
    assert m.waypoints[0].action == "capture"
    assert m.return_to_home is False


def test_estimated_flight_time_positive():
    m = load_mission(MONTEREY_PATH)
    t = m.estimated_flight_time_s()
    assert t > 0.0
    assert t < m.airframe.battery_minutes * 60.0


def test_geofence_polygon_parsed_as_tuples():
    m = load_mission(MONTEREY_PATH)
    assert len(m.geofence_polygon) == 4
    for pt in m.geofence_polygon:
        assert isinstance(pt, tuple)
        assert len(pt) == 2
