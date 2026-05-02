"""Tests for sim.geofence + the runner's geofence enforcement + the
exclusion-aware swarm coverage planner.

Coordinate convention throughout: (lat, lon) in degrees. Test polygons
are unit-ish boxes around the origin or the Gunnison AOR.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sim.geofence import (  # noqa: E402
    Geofence,
    point_in_polygon,
    segment_intersects_polygon,
)
from sim.mission import load_mission  # noqa: E402
from sim.runner import RunnerConfig, SimulationRunner  # noqa: E402
from sim.scenario import ScenarioEngine, load_scenario  # noqa: E402
from sim.swarm.coverage_planner import (  # noqa: E402
    MIN_CELL_AREA_KM2,
    plan_coverage,
)

SIM_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SIM_ROOT.parent

# A simple unit square around (0,0).
UNIT_SQUARE = [
    (0.0, 0.0),
    (0.0, 1.0),
    (1.0, 1.0),
    (1.0, 0.0),
]

# A concave "L" shape (arrow notch in the lower-right corner).
CONCAVE_L = [
    (0.0, 0.0),
    (0.0, 1.0),
    (1.0, 1.0),
    (1.0, 0.5),
    (0.5, 0.5),
    (0.5, 0.0),
]


# ---------------------------------------------------------------------
# point_in_polygon
# ---------------------------------------------------------------------

def test_point_in_polygon_convex_inside():
    assert point_in_polygon(0.5, 0.5, UNIT_SQUARE) is True


def test_point_in_polygon_convex_outside():
    assert point_in_polygon(2.0, 2.0, UNIT_SQUARE) is False
    assert point_in_polygon(-0.1, 0.5, UNIT_SQUARE) is False


def test_point_in_polygon_concave_in_arm():
    # The L's lower (full-width) band — point at lat=0.2, lon=0.7 lives
    # in the bottom half of the bbox where the polygon spans the full
    # width. This IS inside the L.
    assert point_in_polygon(0.2, 0.7, CONCAVE_L) is True


def test_point_in_polygon_concave_in_notch():
    # The L's notch — top-left of the bbox at lat=0.7, lon=0.2 — falls
    # outside the L (the L only fills lon>=0.5 in its top half).
    assert point_in_polygon(0.7, 0.2, CONCAVE_L) is False


def test_point_in_polygon_on_boundary():
    # A vertex.
    assert point_in_polygon(0.0, 0.0, UNIT_SQUARE) is True
    # Midpoint of an edge.
    assert point_in_polygon(0.0, 0.5, UNIT_SQUARE) is True


def test_point_in_polygon_far_outside():
    assert point_in_polygon(100.0, -100.0, UNIT_SQUARE) is False


def test_point_in_polygon_degenerate():
    assert point_in_polygon(0.5, 0.5, []) is False
    assert point_in_polygon(0.5, 0.5, [(0.0, 0.0), (1.0, 1.0)]) is False


# ---------------------------------------------------------------------
# segment_intersects_polygon
# ---------------------------------------------------------------------

def test_segment_straddles_polygon():
    # A segment from outside-left to outside-right that crosses the box.
    assert segment_intersects_polygon((-1.0, 0.5), (2.0, 0.5), UNIT_SQUARE) is True


def test_segment_fully_inside_does_not_cross():
    assert segment_intersects_polygon((0.2, 0.2), (0.8, 0.8), UNIT_SQUARE) is False


def test_segment_fully_outside_does_not_cross():
    assert segment_intersects_polygon((-1.0, -1.0), (-2.0, -2.0), UNIT_SQUARE) is False


def test_segment_touching_vertex():
    # A segment that passes through a vertex but does not cross any edge.
    assert segment_intersects_polygon((-0.1, 0.0), (-0.5, 0.0), UNIT_SQUARE) is False


def test_segment_parallel_to_edge():
    # Parallel to and outside the bottom edge.
    assert segment_intersects_polygon((-0.1, 0.0), (1.1, 0.0), UNIT_SQUARE) is False


def test_segment_identical_to_edge():
    # Same as bottom edge — touching, not crossing.
    assert segment_intersects_polygon((0.0, 0.0), (0.0, 1.0), UNIT_SQUARE) is False


# ---------------------------------------------------------------------
# Geofence.contains
# ---------------------------------------------------------------------

def test_geofence_inclusion_only():
    fence = Geofence(inclusion=tuple(UNIT_SQUARE))
    assert fence.contains(0.5, 0.5) is True
    assert fence.contains(2.0, 2.0) is False


def test_geofence_with_exclusion():
    inner = [(0.4, 0.4), (0.4, 0.6), (0.6, 0.6), (0.6, 0.4)]
    fence = Geofence(
        inclusion=tuple(UNIT_SQUARE),
        exclusions=(tuple(inner),),
    )
    # In inclusion, in exclusion -> not legal.
    assert fence.contains(0.5, 0.5) is False
    # In inclusion, outside exclusion -> legal.
    assert fence.contains(0.2, 0.2) is True
    # Outside inclusion -> not legal.
    assert fence.contains(2.0, 2.0) is False


def test_geofence_contains_on_inclusion_border():
    fence = Geofence(inclusion=tuple(UNIT_SQUARE))
    # Edge midpoint -> inside per ray-casting + edge-touch convention.
    assert fence.contains(0.0, 0.5) is True


def test_geofence_no_inclusion_open_world():
    """Empty inclusion = no inclusion check; exclusions still apply."""
    inner = [(0.4, 0.4), (0.4, 0.6), (0.6, 0.6), (0.6, 0.4)]
    fence = Geofence(exclusions=(tuple(inner),))
    assert fence.contains(0.5, 0.5) is False
    assert fence.contains(100.0, 100.0) is True


# ---------------------------------------------------------------------
# Geofence.segment_legal
# ---------------------------------------------------------------------

def test_segment_legal_through_exclusion():
    inner = [(0.4, 0.4), (0.4, 0.6), (0.6, 0.6), (0.6, 0.4)]
    fence = Geofence(
        inclusion=tuple(UNIT_SQUARE),
        exclusions=(tuple(inner),),
    )
    # Both endpoints legal but segment crosses exclusion.
    assert fence.segment_legal((0.2, 0.5), (0.8, 0.5)) is False
    # Both endpoints legal AND segment doesn't cross.
    assert fence.segment_legal((0.1, 0.1), (0.2, 0.2)) is True


# ---------------------------------------------------------------------
# Geofence.buffer
# ---------------------------------------------------------------------

def test_geofence_buffer_zero_is_noop():
    fence = Geofence(inclusion=tuple(UNIT_SQUARE))
    same = fence.buffer(0.0)
    assert same.inclusion == fence.inclusion
    assert same.exclusions == fence.exclusions


def test_geofence_buffer_shrinks_inclusion_grows_exclusion():
    # Use realistic Gunnison-scale coordinates so cos(lat) is sensible.
    inclusion = [
        (38.90, -107.01),
        (38.92, -107.01),
        (38.92, -106.99),
        (38.90, -106.99),
    ]
    exclusion = [
        (38.905, -107.005),
        (38.915, -107.005),
        (38.915, -106.995),
        (38.905, -106.995),
    ]
    fence = Geofence(
        inclusion=tuple(inclusion),
        exclusions=(tuple(exclusion),),
    )
    buffered = fence.buffer(50.0)
    # Inclusion shrinks: the new vertices are pulled inward toward the
    # centroid (which is approximately the midpoint).
    assert buffered.inclusion is not fence.inclusion
    # All original-inclusion outer corners are now OUTSIDE the buffered
    # inclusion.
    for v in inclusion:
        assert not point_in_polygon(v[0], v[1], list(buffered.inclusion))
    # Exclusion grows: original-exclusion vertices remain inside the
    # buffered exclusion (it expanded).
    new_excl = list(buffered.exclusions[0])
    for v in exclusion:
        assert point_in_polygon(v[0], v[1], new_excl)


def test_geofence_buffer_negative_raises():
    fence = Geofence(inclusion=tuple(UNIT_SQUARE))
    with pytest.raises(ValueError):
        fence.buffer(-10.0)


# ---------------------------------------------------------------------
# Mission YAML parsing — structured + zone-reference forms
# ---------------------------------------------------------------------

def test_mission_loads_with_geojson_zone_references(tmp_path):
    yaml_text = """
name: zone-ref-test
zone_id: zone-ref
home: {lat: 38.91, lon: -107.0, alt_msl_m: 2743}
airframe: mavic_mini_2
flight_params: {altitude_agl_m: 80, cruise_speed_mps: 6}
waypoints:
  - {lat: 38.911, lon: -107.001, alt_agl_m: 80, action: capture}
geofence:
  inclusion_from_zone: gunnison_crested_butte_corridor:slate-river-drainage
  exclusion_from_zone:
    - gunnison_crested_butte_corridor:west-elk-wilderness-exclusion
    - gunnison_crested_butte_corridor:kguc-class-e-surface-area
return_to_home: true
"""
    p = tmp_path / "m.yaml"
    p.write_text(yaml_text)
    m = load_mission(p)
    assert len(m.geofence.inclusion) >= 4
    assert len(m.exclusions) == 2
    names = {e.name for e in m.exclusions}
    assert "west-elk-wilderness-exclusion" in names
    assert "kguc-class-e-surface-area" in names
    # Wilderness should be 'hard', class-E should be 'warn'.
    by_name = {e.name: e for e in m.exclusions}
    assert by_name["west-elk-wilderness-exclusion"].kind == "hard"
    assert by_name["kguc-class-e-surface-area"].kind == "warn"


def test_mission_legacy_geofence_polygon_still_works(tmp_path):
    yaml_text = """
name: legacy
zone_id: legacy
home: {lat: 38.91, lon: -107.0, alt_msl_m: 2743}
airframe: mavic_mini_2
waypoints:
  - {lat: 38.911, lon: -107.001, alt_agl_m: 80}
geofence_polygon:
  - [38.9165, -107.0060]
  - [38.9165, -106.9940]
  - [38.9035, -106.9940]
  - [38.9035, -107.0060]
"""
    p = tmp_path / "m.yaml"
    p.write_text(yaml_text)
    m = load_mission(p)
    assert len(m.geofence_polygon) == 4
    assert len(m.geofence.inclusion) == 4
    assert m.exclusions == ()


# ---------------------------------------------------------------------
# Runner: hard-exclusion clamps + RTL system_event
# ---------------------------------------------------------------------

WILDERNESS_MISSION = SIM_ROOT / "missions" / "gunnison_with_wilderness_exclusion.yaml"
BREACH_SCENARIO = SIM_ROOT / "scenarios" / "wilderness_breach_attempt.yaml"
CLEAN_SCENARIO = SIM_ROOT / "scenarios" / "clean_patrol.yaml"


def test_runner_blocks_at_exclusion():
    """Mission whose last two waypoints reach into West Elk wilderness.
    Runner must clamp before crossing and emit a system_event with
    recommended_action=rtl.
    """
    mission = load_mission(WILDERNESS_MISSION)
    scenario = load_scenario(BREACH_SCENARIO)
    captured: list[dict] = []
    runner = SimulationRunner(
        mission=mission,
        scenario_engine=ScenarioEngine(scenario),
        config=RunnerConfig(
            drone_id="wfw-test01",
            tick_hz=10.0,
            start_wallclock=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        on_signal=captured.append,
    )
    result = runner.run(max_sim_seconds=600.0)
    # At least one system_event with recommended_action=rtl was emitted.
    rtl_events = [
        s for s in captured
        if s["signal_type"] == "system_event"
        and s["recommended_action"] == "rtl"
    ]
    assert rtl_events, (
        f"expected at least one rtl system_event; got {len(captured)} "
        f"signals: {[s['signal_type'] for s in captured]}"
    )
    # The drone never made it through to the last waypoint.
    assert result.waypoints_reached < len(mission.waypoints)
    # The signal carries the wilderness name in its subtype.
    sub = rtl_events[0]["signal_subtype"]
    assert "west-elk-wilderness" in sub


def test_runner_warns_at_class_e():
    """If a warn-type exclusion is entered, the runner emits a single
    notify_operator system_event but keeps flying.

    Construct a synthetic mission whose only waypoint is INSIDE the
    KGUC class-E warn-zone (so the drone enters it on the first move).
    """
    yaml_text = """
name: kguc-warn-test
zone_id: kguc-test
home: {lat: 38.55, lon: -106.93, alt_msl_m: 2348}
airframe: mavic_mini_2
flight_params: {altitude_agl_m: 80, cruise_speed_mps: 6}
waypoints:
  - {lat: 38.555, lon: -106.93, alt_agl_m: 80, action: capture}
return_to_home: false
geofence:
  inclusion:
    - [38.40, -107.10]
    - [38.65, -107.10]
    - [38.65, -106.70]
    - [38.40, -106.70]
  exclusions:
    - name: kguc-class-e
      type: warn
      regulatory_basis: "FAA LAANC required"
      polygon:
        - [38.48, -107.05]
        - [38.61, -107.05]
        - [38.61, -106.80]
        - [38.48, -106.80]
"""
    import tempfile
    with tempfile.NamedTemporaryFile(
        "w", suffix=".yaml", delete=False
    ) as f:
        f.write(yaml_text)
        path = f.name
    mission = load_mission(path)
    scenario = load_scenario(CLEAN_SCENARIO)
    captured: list[dict] = []
    runner = SimulationRunner(
        mission=mission,
        scenario_engine=ScenarioEngine(scenario),
        config=RunnerConfig(
            drone_id="wfw-test02",
            tick_hz=10.0,
            start_wallclock=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        on_signal=captured.append,
    )
    result = runner.run(max_sim_seconds=600.0)
    warn_events = [
        s for s in captured
        if s["signal_type"] == "system_event"
        and s["recommended_action"] == "notify_operator"
    ]
    assert warn_events, "expected at least one warn-type system_event"
    # Continued flying (warn-type does not lock the runner).
    assert result.waypoints_reached >= 1
    # Only one warn per zone (deduplication on name).
    assert len(warn_events) == 1


# ---------------------------------------------------------------------
# Swarm coverage planner: exclusion-aware tiling
# ---------------------------------------------------------------------

def test_swarm_planner_avoids_exclusion():
    """3 drones over a polygon overlapping the West Elk exclusion.
    Returned cells must not overlap the exclusion bbox."""
    inclusion = [
        (38.85, -107.10),
        (38.85, -106.99),
        (38.92, -106.99),
        (38.92, -107.10),
    ]
    # West Elk-ish wilderness exclusion (covers SW corner of inclusion).
    exclusion = [
        (38.85, -107.10),
        (38.85, -107.05),
        (38.88, -107.05),
        (38.88, -107.10),
    ]
    zones = plan_coverage(inclusion, n_drones=3, exclusions=[exclusion])
    assert len(zones) == 3
    # No assigned zone overlaps the exclusion bbox.
    e_min_lat, e_min_lon = 38.85, -107.10
    e_max_lat, e_max_lon = 38.88, -107.05
    for z in zones:
        z_min_lat, z_min_lon, z_max_lat, z_max_lon = z.bbox
        lat_overlap = (e_min_lat < z_max_lat) and (e_max_lat > z_min_lat)
        lon_overlap = (e_min_lon < z_max_lon) and (e_max_lon > z_min_lon)
        assert not (lat_overlap and lon_overlap), (
            f"zone {z.drone_index} bbox {z.bbox} overlaps exclusion"
        )
    # Each surviving cell still has at least the minimum useful area.
    for z in zones:
        assert z.area_km2() >= MIN_CELL_AREA_KM2


def test_swarm_planner_drops_tiny_cells_and_round_robins():
    """If most cells shrink below MIN_CELL_AREA_KM2, the surviving cells
    absorb the displaced drones via round-robin."""
    # Gunnison-scale inclusion (~3 km^2 ish).
    inclusion = [
        (38.85, -107.10),
        (38.85, -106.99),
        (38.92, -106.99),
        (38.92, -107.10),
    ]
    # Exclusion eats the entire western half of the inclusion. With a
    # 2x2 grid, the two western cells become tiny strips and get dropped;
    # the two eastern cells survive. With n_drones=4, drone-3 wraps onto
    # cell-0 (round-robin).
    exclusion = [
        (38.85, -107.10),
        (38.85, -107.040),
        (38.92, -107.040),
        (38.92, -107.10),
    ]
    zones = plan_coverage(inclusion, n_drones=4, exclusions=[exclusion])
    assert len(zones) == 4, f"got {len(zones)} zones; expected 4"
    # Round-robin: indices 0..3 must each get assigned, but distinct
    # underlying cells should be < n_drones.
    distinct_bboxes = {z.bbox for z in zones}
    assert len(distinct_bboxes) < 4
    # No assigned bbox overlaps the exclusion bbox (even partially).
    e_min_lat, e_min_lon = 38.85, -107.10
    e_max_lat, e_max_lon = 38.92, -107.040
    for z in zones:
        z_min_lat, z_min_lon, z_max_lat, z_max_lon = z.bbox
        lat_overlap = (e_min_lat < z_max_lat) and (e_max_lat > z_min_lat)
        lon_overlap = (e_min_lon < z_max_lon) and (e_max_lon > z_min_lon)
        assert not (lat_overlap and lon_overlap), (
            f"zone {z.drone_index} bbox {z.bbox} overlaps exclusion"
        )
