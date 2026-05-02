"""Pixel-frame -> world-frame projection for fire-detection bboxes.

The on-drone detector returns bboxes in pixel coordinates. The signal
schema needs target_coords in lat/lon. The bridge between them is:

  1. Center-of-bbox -> direction vector in the camera frame (pinhole).
  2. Rotate by the drone yaw + camera-mount-pitch into the world frame.
  3. Intersect that ray with a ground plane at known elevation below the
     drone (flat-Earth approximation — fine for the ~1 km observation
     radius the Mavic Mini gets).
  4. Convert the meter-offset from the drone to a delta-lat / delta-lon
     using the local-tangent-plane equirectangular approximation.

This is good for hundreds of meters around the camera. Beyond ~5 km we'd
want a proper DEM intersection (rasterio + SRTM) — Phase 1 follow-up.

Pure stdlib — math only. No numpy, no shapely. Tested at scale in
ml/fire_detection/tests/test_geo.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Mean Earth radius (m). Good to ~0.3% — well under our other error sources.
_EARTH_RADIUS_M = 6_378_137.0


# ---------------------------------------------------------------------------
# Camera + bbox + drone state structs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Camera:
    """Pinhole-camera intrinsics.

    horizontal_fov_deg / vertical_fov_deg are the *full* FoV. For the
    Mavic Mini 2 those are ~83 deg horizontal, ~74 deg vertical at the
    default 4:3 sensor mode.
    """

    horizontal_fov_deg: float
    vertical_fov_deg: float
    image_width_px: int
    image_height_px: int

    def __post_init__(self) -> None:
        if self.image_width_px <= 0 or self.image_height_px <= 0:
            raise ValueError("image dimensions must be positive")
        if not (0 < self.horizontal_fov_deg < 180):
            raise ValueError("horizontal_fov_deg must be in (0, 180)")
        if not (0 < self.vertical_fov_deg < 180):
            raise ValueError("vertical_fov_deg must be in (0, 180)")


@dataclass(frozen=True)
class BBox:
    """Pixel-space axis-aligned bounding box. Origin at top-left."""

    x0: float
    y0: float
    x1: float
    y1: float

    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)


@dataclass(frozen=True)
class DroneState:
    """Where the drone was when the frame was captured.

    yaw_deg follows the magnetic-heading convention: 0 = North, 90 = East
    (clockwise from above). camera_pitch_deg is measured from horizontal,
    NEGATIVE pointing down — the Mavic gimbal reports -45 when looking
    down 45 degrees.
    """

    lat: float
    lon: float
    alt_agl_m: float
    yaw_deg: float
    camera_pitch_deg: float


@dataclass(frozen=True)
class GroundProjection:
    """Result of projecting a bbox into the world frame."""

    lat: float
    lon: float
    distance_m: float
    bearing_deg: float  # bearing from drone to target, clockwise from North


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _meters_to_latlon_offset(
    origin_lat: float, north_m: float, east_m: float
) -> tuple[float, float]:
    """Equirectangular approximation: meter offset -> (delta_lat, delta_lon).

    Good to a fraction of a percent within ~10 km of the origin, which is
    well past the Mavic's range. Beyond that, switch to Vincenty.
    """
    delta_lat = math.degrees(north_m / _EARTH_RADIUS_M)
    # Compress longitude by cos(latitude) — meridians converge poleward.
    cos_lat = math.cos(math.radians(origin_lat))
    if abs(cos_lat) < 1e-9:
        # Right at the pole — hand back zero rather than dividing by ~0.
        delta_lon = 0.0
    else:
        delta_lon = math.degrees(east_m / (_EARTH_RADIUS_M * cos_lat))
    return delta_lat, delta_lon


def haversine_distance_m(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Great-circle distance in meters between two lat/lon pairs.

    Used for unit tests + sanity-check on projection round-trips.
    """
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Pixel -> camera-frame ray
# ---------------------------------------------------------------------------


def pixel_to_camera_ray(
    px: float, py: float, camera: Camera
) -> tuple[float, float, float]:
    """Map a pixel to a unit direction vector in the camera frame.

    Camera frame convention (matches OpenCV):
      x: right
      y: down
      z: forward (out of the lens)

    Returns a unit vector (xc, yc, zc) pointing at the world feature that
    landed on (px, py).
    """
    # Half-FoV tangents — the focal length in pixels is W / (2 tan(hfov/2)).
    tan_h = math.tan(math.radians(camera.horizontal_fov_deg) / 2)
    tan_v = math.tan(math.radians(camera.vertical_fov_deg) / 2)

    # Normalised image plane: x in [-1, 1] from left to right, y similarly.
    nx = (2 * px / camera.image_width_px) - 1
    ny = (2 * py / camera.image_height_px) - 1

    # Camera-frame ray. z=1 plane.
    xc = nx * tan_h
    yc = ny * tan_v
    zc = 1.0

    norm = math.sqrt(xc * xc + yc * yc + zc * zc)
    return (xc / norm, yc / norm, zc / norm)


def _rotate_to_world(
    cam_ray: tuple[float, float, float],
    yaw_deg: float,
    pitch_deg: float,
) -> tuple[float, float, float]:
    """Camera-frame -> world-frame (ENU: x=East, y=North, z=Up).

    The rotation is camera-pitch around the camera x-axis (tilt the optical
    axis from forward-horizontal up/down), then yaw around the world z-axis.

    With pitch_deg = 0 the camera is level. pitch_deg negative means the
    nose-down case (Mavic gimbal pointing at the ground).
    """
    xc, yc, zc = cam_ray

    # 1. Pitch about the x-axis. Convention: pitch positive = nose up.
    #    A NEGATIVE pitch (camera looking down) sends a forward ray (zc=1)
    #    to a downward ray.
    cp = math.cos(math.radians(pitch_deg))
    sp = math.sin(math.radians(pitch_deg))
    # After-pitch in an intermediate "drone-body forward" frame:
    #   forward (was +z), right (was +x), up (was -y).
    xb = xc                              # right
    yb = -yc * cp + zc * sp              # up
    zb = yc * sp + zc * cp               # forward

    # 2. Yaw to world ENU. yaw_deg is heading (0 = North, 90 = East).
    #    The drone-body forward axis maps to world (sin(yaw), cos(yaw), 0).
    cy = math.cos(math.radians(yaw_deg))
    sy = math.sin(math.radians(yaw_deg))
    east = zb * sy + xb * cy
    north = zb * cy - xb * sy
    up = yb

    return (east, north, up)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def project_bbox_to_ground(
    bbox: BBox, camera: Camera, drone: DroneState
) -> GroundProjection:
    """Center-of-bbox -> ground-intersection in lat/lon.

    Algorithm:
      1. center pixel -> camera-frame ray
      2. rotate by gimbal pitch + drone yaw -> world ENU ray
      3. intersect with the ground plane at z = -alt_agl_m
      4. convert (east_m, north_m) offset to delta-lat / delta-lon

    Raises:
      ValueError if the ray points up (no ground intersection in front
      of the camera) — common when the gimbal is set to look at the
      horizon and a high pixel happens to project upward.
    """
    cx, cy = bbox.center()
    cam_ray = pixel_to_camera_ray(cx, cy, camera)
    east, north, up = _rotate_to_world(
        cam_ray, drone.yaw_deg, drone.camera_pitch_deg
    )

    # Ground plane at z = -alt_agl_m (ENU origin at the drone).
    if up >= -1e-9:
        raise ValueError(
            f"ray does not intersect ground (up={up:.4f}); "
            "camera is not pointed below horizon"
        )

    # Distance along the ray until z = -alt_agl_m.
    t = -drone.alt_agl_m / up  # `up` < 0, so t > 0.
    east_m = east * t
    north_m = north * t

    delta_lat, delta_lon = _meters_to_latlon_offset(drone.lat, north_m, east_m)
    target_lat = drone.lat + delta_lat
    target_lon = drone.lon + delta_lon

    horizontal_m = math.hypot(east_m, north_m)
    distance_m = math.hypot(horizontal_m, drone.alt_agl_m)
    bearing_deg = (math.degrees(math.atan2(east_m, north_m)) + 360.0) % 360.0

    return GroundProjection(
        lat=target_lat,
        lon=target_lon,
        distance_m=distance_m,
        bearing_deg=bearing_deg,
    )


def estimate_distance_m(
    bbox: BBox, camera: Camera, drone: DroneState
) -> float:
    """Convenience: just the slant-range to the bbox center."""
    return project_bbox_to_ground(bbox, camera, drone).distance_m
