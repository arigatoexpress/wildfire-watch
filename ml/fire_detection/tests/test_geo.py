"""Unit tests for pixel -> world-frame projection.

Coverage:
  - Camera ray math (center pixel = forward axis, edges pin to FoV).
  - Yaw + pitch rotation invariants (level forward, nadir, cardinal yaws).
  - Ground intersection (nadir camera at altitude h -> distance == h).
  - Round-trip: project a bbox, convert (east, north) back via
    haversine, recover the same horizontal distance.
  - Error mode: above-horizon ray raises.

Run:
    cd ~/Code/wildfire-watch
    python3 -m pytest ml/fire_detection/tests/test_geo.py -q
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.fire_detection.geo import (  # noqa: E402
    BBox,
    Camera,
    DroneState,
    estimate_distance_m,
    haversine_distance_m,
    pixel_to_camera_ray,
    project_bbox_to_ground,
)


# ---------------------------------------------------------------------------
# Fixtures: a Mavic-Mini-shaped camera (1920x1080, ~83 deg H FoV, 47 H FoV V).
# ---------------------------------------------------------------------------


@pytest.fixture
def mavic_camera() -> Camera:
    return Camera(
        horizontal_fov_deg=83.0,
        vertical_fov_deg=47.0,
        image_width_px=1920,
        image_height_px=1080,
    )


@pytest.fixture
def square_bbox() -> BBox:
    """100x100 bbox centered on the image center for the mavic_camera."""
    return BBox(x0=910, y0=490, x1=1010, y1=590)


# ---------------------------------------------------------------------------
# Pixel -> camera ray
# ---------------------------------------------------------------------------


def test_camera_ray_center_pixel_is_forward_axis(mavic_camera: Camera) -> None:
    cx = mavic_camera.image_width_px / 2
    cy = mavic_camera.image_height_px / 2
    x, y, z = pixel_to_camera_ray(cx, cy, mavic_camera)
    # Center pixel -> +z, no x or y component.
    assert z == pytest.approx(1.0, abs=1e-9)
    assert abs(x) < 1e-9
    assert abs(y) < 1e-9


def test_camera_ray_right_edge_pins_to_horizontal_fov(mavic_camera: Camera) -> None:
    """A pixel at the right edge should make an angle of hFoV/2 with the
    optical axis."""
    cx = mavic_camera.image_width_px  # right edge
    cy = mavic_camera.image_height_px / 2
    x, _, z = pixel_to_camera_ray(cx, cy, mavic_camera)
    angle = math.degrees(math.atan2(x, z))
    assert angle == pytest.approx(mavic_camera.horizontal_fov_deg / 2, abs=0.5)


def test_camera_ray_unit_length(mavic_camera: Camera) -> None:
    for px in (0, 100, 960, 1920):
        for py in (0, 540, 1080):
            x, y, z = pixel_to_camera_ray(px, py, mavic_camera)
            assert math.sqrt(x * x + y * y + z * z) == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Ground projection: nadir camera (pitch = -90) at altitude h.
# ---------------------------------------------------------------------------


def test_nadir_center_pixel_lands_directly_below(
    mavic_camera: Camera, square_bbox: BBox
) -> None:
    """Camera looking straight down, center bbox -> target == drone position
    horizontally, distance_m == altitude (slant = vertical)."""
    drone = DroneState(
        lat=38.8200,
        lon=-106.9870,
        alt_agl_m=80.0,
        yaw_deg=0.0,
        camera_pitch_deg=-90.0,
    )
    out = project_bbox_to_ground(square_bbox, mavic_camera, drone)
    assert out.lat == pytest.approx(drone.lat, abs=1e-7)
    assert out.lon == pytest.approx(drone.lon, abs=1e-7)
    # Slant distance from drone to nadir == altitude.
    assert out.distance_m == pytest.approx(80.0, abs=0.01)


def test_nadir_offset_pixel_lands_offset_on_ground(mavic_camera: Camera) -> None:
    """At nadir, an off-center pixel projects to a ground point whose
    horizontal offset matches altitude * tan(angle-from-axis)."""
    drone = DroneState(
        lat=38.8200,
        lon=-106.9870,
        alt_agl_m=100.0,
        yaw_deg=0.0,
        camera_pitch_deg=-90.0,
    )
    # A bbox centered at (right_edge, image_center_y) — full hFoV/2 to one side.
    bbox = BBox(
        x0=mavic_camera.image_width_px - 10,
        y0=mavic_camera.image_height_px / 2 - 10,
        x1=mavic_camera.image_width_px,
        y1=mavic_camera.image_height_px / 2 + 10,
    )
    out = project_bbox_to_ground(bbox, mavic_camera, drone)
    horiz = haversine_distance_m(drone.lat, drone.lon, out.lat, out.lon)
    expected_horiz = drone.alt_agl_m * math.tan(
        math.radians(mavic_camera.horizontal_fov_deg / 2)
    )
    # 2% tolerance — equirectangular offset + haversine round-trip.
    assert horiz == pytest.approx(expected_horiz, rel=0.02)


# ---------------------------------------------------------------------------
# Yaw rotates the bearing.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "yaw_deg,expected_bearing",
    [
        (0.0, 0.0),     # facing north -> forward goes north
        (90.0, 90.0),   # facing east  -> forward goes east
        (180.0, 180.0), # facing south
        (270.0, 270.0), # facing west
    ],
)
def test_camera_pointed_forward_at_horizon_then_tilted_down(
    mavic_camera: Camera, yaw_deg: float, expected_bearing: float
) -> None:
    """Camera tilted 30 deg below the horizon, drone facing the cardinal
    yaw. The center bbox should land at that bearing from the drone."""
    drone = DroneState(
        lat=38.8200,
        lon=-106.9870,
        alt_agl_m=100.0,
        yaw_deg=yaw_deg,
        camera_pitch_deg=-30.0,
    )
    cx = mavic_camera.image_width_px / 2
    cy = mavic_camera.image_height_px / 2
    bbox = BBox(cx - 10, cy - 10, cx + 10, cy + 10)
    out = project_bbox_to_ground(bbox, mavic_camera, drone)
    # Bearing from drone to target == drone yaw (since the optical axis
    # is forward-aligned).
    diff = abs((out.bearing_deg - expected_bearing + 540) % 360 - 180)
    assert diff < 1.0, f"yaw={yaw_deg}: bearing {out.bearing_deg} vs {expected_bearing}"


def test_distance_with_30deg_tilt_matches_geometry(mavic_camera: Camera) -> None:
    """Camera 30 deg below horizon, altitude 100 m. The ray makes a 30 deg
    angle with the ground plane, so slant range = alt / sin(30) = 200 m."""
    drone = DroneState(
        lat=38.8200,
        lon=-106.9870,
        alt_agl_m=100.0,
        yaw_deg=0.0,
        camera_pitch_deg=-30.0,
    )
    cx = mavic_camera.image_width_px / 2
    cy = mavic_camera.image_height_px / 2
    bbox = BBox(cx - 10, cy - 10, cx + 10, cy + 10)
    d = estimate_distance_m(bbox, mavic_camera, drone)
    expected = drone.alt_agl_m / math.sin(math.radians(30))
    assert d == pytest.approx(expected, rel=0.02)


# ---------------------------------------------------------------------------
# Error mode
# ---------------------------------------------------------------------------


def test_camera_pointed_above_horizon_raises(mavic_camera: Camera) -> None:
    """Camera tilted 10 deg ABOVE horizon -> ground intersection is undefined."""
    drone = DroneState(
        lat=38.8200,
        lon=-106.9870,
        alt_agl_m=100.0,
        yaw_deg=0.0,
        camera_pitch_deg=10.0,
    )
    cx = mavic_camera.image_width_px / 2
    cy = mavic_camera.image_height_px / 2
    bbox = BBox(cx - 10, cy - 10, cx + 10, cy + 10)
    with pytest.raises(ValueError, match="ray does not intersect ground"):
        project_bbox_to_ground(bbox, mavic_camera, drone)


def test_camera_construction_validates_inputs() -> None:
    with pytest.raises(ValueError):
        Camera(0, 47, 1920, 1080)  # zero hFoV
    with pytest.raises(ValueError):
        Camera(83, 47, 0, 1080)    # zero width
    with pytest.raises(ValueError):
        Camera(83, 200, 1920, 1080)  # vFoV >= 180


# ---------------------------------------------------------------------------
# Haversine sanity (used internally by other tests).
# ---------------------------------------------------------------------------


def test_haversine_distance_m_zero_for_same_point() -> None:
    assert haversine_distance_m(38.0, -106.0, 38.0, -106.0) == pytest.approx(0.0)


def test_haversine_distance_m_one_degree_lat_is_111km() -> None:
    """One degree of latitude = ~111.32 km on a sphere."""
    d = haversine_distance_m(38.0, -106.0, 39.0, -106.0)
    assert d == pytest.approx(111_320.0, rel=0.01)
