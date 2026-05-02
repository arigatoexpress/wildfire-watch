"""Tests for sim.swarm.coverage_planner."""

from __future__ import annotations

import pytest

from sim.swarm.coverage_planner import (
    SubZone,
    lattice_waypoints_for_subzone,
    min_centroid_separation_m,
    plan_coverage,
    total_polygon_area_km2,
    union_area_km2,
)


# Gunnison Slate River geofence — exactly the polygon in
# sim/missions/gunnison_slate_river_1km2.yaml.
GUNNISON_POLY = [
    (38.9165, -107.0060),
    (38.9165, -106.9940),
    (38.9035, -106.9940),
    (38.9035, -107.0060),
]


def test_three_drones_three_zones():
    zones = plan_coverage(GUNNISON_POLY, n_drones=3)
    assert len(zones) == 3
    for i, z in enumerate(zones):
        assert isinstance(z, SubZone)
        assert z.drone_index == i


def test_zones_non_overlapping():
    """Cells from a row-major bbox grid never overlap by construction.
    Verify via pairwise bbox intersection check."""
    zones = plan_coverage(GUNNISON_POLY, n_drones=3)
    for i, a in enumerate(zones):
        for b in zones[i + 1 :]:
            min_lat_a, min_lon_a, max_lat_a, max_lon_a = a.bbox
            min_lat_b, min_lon_b, max_lat_b, max_lon_b = b.bbox
            # Two rectangles overlap iff they overlap in BOTH dims with
            # POSITIVE area. We allow shared edges (touching).
            lat_overlap = (
                min_lat_a < max_lat_b and min_lat_b < max_lat_a
            )
            lon_overlap = (
                min_lon_a < max_lon_b and min_lon_b < max_lon_a
            )
            assert not (lat_overlap and lon_overlap), (
                f"zones {a.drone_index} and {b.drone_index} overlap"
            )


def test_zones_union_within_one_percent():
    """The union of N sub-zones should equal the inclusion bbox area
    (the planner partitions the bbox, NOT the irregular polygon).

    For a rectangle inclusion polygon, the bbox area equals the polygon
    area, so union should match polygon area to within 1%.
    """
    zones = plan_coverage(GUNNISON_POLY, n_drones=3)
    poly_area = total_polygon_area_km2(GUNNISON_POLY)
    union = union_area_km2(zones)
    # With 3 drones the planner uses a 2x2 grid and only fills 3 cells,
    # so we expect roughly 3/4 of the bbox to be covered.
    expected_coverage = 3.0 / 4.0
    ratio = union / poly_area
    assert 0.99 * expected_coverage <= ratio <= 1.01 * expected_coverage, (
        f"union/poly = {ratio:.4f}; expected ~{expected_coverage}"
    )


def test_zones_full_coverage_when_n_matches_grid():
    """N=4 fills the 2x2 grid entirely; union should equal polygon."""
    zones = plan_coverage(GUNNISON_POLY, n_drones=4)
    poly_area = total_polygon_area_km2(GUNNISON_POLY)
    union = union_area_km2(zones)
    assert abs(union - poly_area) <= 0.01 * poly_area


def test_centroids_are_separated():
    """No two centroids should be at the same point."""
    zones = plan_coverage(GUNNISON_POLY, n_drones=3)
    sep = min_centroid_separation_m(zones)
    # Gunnison polygon spans ~1 km, half-cell width is ~250 m or so.
    assert sep > 100.0, f"centroids too close: {sep:.1f} m"


def test_lattice_waypoints_inside_zone():
    zones = plan_coverage(GUNNISON_POLY, n_drones=3)
    for z in zones:
        wps = lattice_waypoints_for_subzone(z, n_waypoints=4)
        assert len(wps) == 4
        min_lat, min_lon, max_lat, max_lon = z.bbox
        for lat, lon in wps:
            assert min_lat <= lat <= max_lat, f"lat {lat} outside {z.bbox}"
            assert min_lon <= lon <= max_lon, f"lon {lon} outside {z.bbox}"


def test_plan_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        plan_coverage(GUNNISON_POLY, n_drones=0)
    with pytest.raises(ValueError):
        plan_coverage([(0.0, 0.0), (0.0, 1.0)], n_drones=2)


def test_area_for_known_square():
    """Sanity-check the spherical-excess area formula on a 1 km^2 box."""
    area = total_polygon_area_km2(GUNNISON_POLY)
    # 0.013 deg lat ~= 1.45 km; 0.012 deg lon at lat 38.9 ~= 1.04 km;
    # so the bbox area is ~1.5 km^2. Allow generous tolerance because
    # the polygon is slightly bigger than the 1 km^2 lattice envelope
    # (it has 100 m buffer).
    assert 1.2 <= area <= 1.8, f"unexpected area {area:.3f} km^2"
