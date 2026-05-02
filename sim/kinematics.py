"""WGS84 great-circle math for the flight simulator.

All inputs are in degrees (lat/lon/bearing) and meters (distance/altitude).
Bearings are measured clockwise from true north, in [0, 360).

Reference: https://www.movable-type.co.uk/scripts/latlong.html

Tested to better than 1m drift on a 1km dead-reckoning round trip.
"""

from __future__ import annotations

import math

# WGS84 mean radius (meters). Good enough for sub-1km legs to ~1m.
EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in meters."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from (lat1, lon1) toward (lat2, lon2), deg true.

    Returned value is in [0, 360). Exact at the equator and along
    meridians. Caller should not depend on it when the two points are
    identical (returns 0.0 by convention).
    """
    if lat1 == lat2 and lon1 == lon2:
        return 0.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    y = math.sin(dlam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    theta = math.atan2(y, x)
    return (math.degrees(theta) + 360.0) % 360.0


def move_along_bearing(
    lat: float, lon: float, bearing_deg: float, distance_m: float
) -> tuple[float, float]:
    """Forward dead-reckoning on a great circle. Returns (lat, lon)."""
    if distance_m == 0.0:
        return (lat, lon)
    delta = distance_m / EARTH_RADIUS_M
    theta = math.radians(bearing_deg)
    phi1 = math.radians(lat)
    lam1 = math.radians(lon)
    sin_phi2 = math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    phi2 = math.asin(max(-1.0, min(1.0, sin_phi2)))
    y = math.sin(theta) * math.sin(delta) * math.cos(phi1)
    x = math.cos(delta) - math.sin(phi1) * math.sin(phi2)
    lam2 = lam1 + math.atan2(y, x)
    # Normalize to [-180, 180].
    lon_out = ((math.degrees(lam2) + 540.0) % 360.0) - 180.0
    return (math.degrees(phi2), lon_out)


def heading_diff_deg(a: float, b: float) -> float:
    """Smallest signed angular difference b - a, in (-180, 180]."""
    d = (b - a + 540.0) % 360.0 - 180.0
    # The above maps 180 -> -180; flip back.
    if d == -180.0:
        return 180.0
    return d


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
