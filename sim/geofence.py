"""Geofence polygon math — inclusion + exclusions.

A geofence is one inclusion polygon (the area the drone is allowed to fly
in) plus zero or more exclusion polygons (areas the drone is NOT allowed
to fly in). The West Elk Wilderness is the canonical motivating example:
36 CFR 261.16 prohibits aircraft over designated wilderness, so any
mission whose inclusion polygon abuts West Elk MUST also carry the
wilderness as an exclusion.

A point is INSIDE the geofence iff it is inside the inclusion polygon
AND outside every exclusion polygon. A line segment is LEGAL iff its
endpoints are both inside AND it does not cross any inclusion edge AND
does not cross any exclusion edge.

Math model
----------
We treat (lat, lon) as flat 2D coordinates and run a standard ray-casting
point-in-polygon + segment-segment intersection on them. This is
**not** geodesic — it is a flat-earth approximation in the (lon, lat)
plane.

For our use case the approximation is accurate enough:
  - 1 km^2 mission zones at ~38.9 N latitude span ~0.013 deg lat by
    ~0.012 deg lon. A 100 m polygon edge is 0.0009 deg in either
    dimension. Treating that as a straight line in (lon, lat) introduces
    sub-meter error.
  - The West Elk Wilderness exclusion is ~10 km on a side. Same flat
    approximation yields < 1 m of edge-position error at our latitudes.

If wildfire-watch ever expands above ~70 deg latitude or to AOR sizes
above ~50 km on a side, this module needs to switch to a great-circle
intersection model (or to the geographic Cartesian projection in
`sim.kinematics`). For Gunnison-Crested Butte this is fine.

Stdlib only. Reused by `sim.mission`, `sim.runner`, and
`sim.swarm.coverage_planner`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

# Geographic-math constants (used only by `Geofence.buffer`).
EARTH_RADIUS_M = 6_371_008.8
_M_PER_DEG_LAT = math.pi * EARTH_RADIUS_M / 180.0


def _meters_per_deg_lon(lat_deg: float) -> float:
    """Length of one degree of longitude at the given latitude, in meters.

    cos(lat) shrinks the longitude ruler away from the equator. At 38.9 N
    one degree of lon ~= 86.7 km; at 60 N it's ~55 km. Used by
    Geofence.buffer to convert a meter-buffer into an angular shrink/grow.
    """
    return _M_PER_DEG_LAT * math.cos(math.radians(lat_deg))


# ----------------------------------------------------------------------
# Point-in-polygon (ray casting)
# ----------------------------------------------------------------------

def point_in_polygon(
    lat: float, lon: float, polygon: list[tuple[float, float]]
) -> bool:
    """Ray-casting point-in-polygon test.

    `polygon` is a list of (lat, lon) vertices. The polygon may be open
    or closed (last vertex == first vertex); both forms are accepted.

    A point exactly on an edge is treated as INSIDE — the convention
    matches the runner's "stay inside the legal envelope" use case
    (a drone hovering on the edge is not violating).

    Degenerate polygons (< 3 distinct vertices) always return False.
    """
    if polygon is None:
        return False
    pts = list(polygon)
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return False
    # Edge-touch fast path: any vertex match or any edge collinearity is
    # treated as inside.
    for i, (vx, vy) in enumerate(pts):
        if vx == lat and vy == lon:
            return True
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        if _point_on_segment((lat, lon), a, b):
            return True
    # Ray casting in lon (x) at fixed lat (y). For each edge that
    # straddles `lat`, see if the edge crosses the +lon ray from `lon`.
    inside = False
    for i in range(n):
        ay, ax = pts[i]
        by, bx = pts[(i + 1) % n]
        # Edge straddles the horizontal y=lat line?
        if (ay > lat) != (by > lat):
            # x-intersection of this edge with y=lat:
            # x = ax + (lat - ay) * (bx - ax) / (by - ay)
            denom = (by - ay)
            if denom == 0.0:
                continue
            x_cross = ax + (lat - ay) * (bx - ax) / denom
            if lon < x_cross:
                inside = not inside
    return inside


def _point_on_segment(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
    eps: float = 1e-12,
) -> bool:
    """True iff point p lies on segment ab (within eps in both axes)."""
    py, px = p
    ay, ax = a
    by, bx = b
    # Cross product (collinearity) plus bounding-box containment.
    cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    if abs(cross) > eps:
        return False
    if min(ax, bx) - eps <= px <= max(ax, bx) + eps and \
       min(ay, by) - eps <= py <= max(ay, by) + eps:
        return True
    return False


# ----------------------------------------------------------------------
# Segment-polygon intersection
# ----------------------------------------------------------------------

def _segments_cross(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> bool:
    """True iff open segments p1p2 and p3p4 cross (proper intersection or
    collinear overlap on a non-zero-length stretch).

    Coordinates are (lat, lon). We compute orientations on the (lon, lat)
    plane.
    """
    def orient(a, b, c) -> float:
        # Signed area * 2 on the (x=lon, y=lat) plane.
        return (b[1] - a[1]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[1] - a[1])

    o1 = orient(p1, p2, p3)
    o2 = orient(p1, p2, p4)
    o3 = orient(p3, p4, p1)
    o4 = orient(p3, p4, p2)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        # Reject the case where one orientation is exactly zero (touching)
        # — touching does not count as crossing.
        if o1 == 0.0 or o2 == 0.0 or o3 == 0.0 or o4 == 0.0:
            return False
        return True
    return False


def segment_intersects_polygon(
    p1: tuple[float, float],
    p2: tuple[float, float],
    polygon: list[tuple[float, float]],
) -> bool:
    """True iff line segment p1->p2 crosses any edge of the polygon.

    Touching an edge (shared endpoint, parallel coincident) returns False
    — only proper crossings count.
    """
    pts = list(polygon)
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return False
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        if _segments_cross(p1, p2, a, b):
            return True
    return False


# ----------------------------------------------------------------------
# Geofence dataclass
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Geofence:
    """A flight envelope: one inclusion polygon, zero or more exclusion
    polygons.

    `inclusion` is a list of (lat, lon) vertices. `exclusions` is a list
    of polygons, each of the same shape. An empty `inclusion` means
    "no inclusion check" (legacy behaviour for missions without a
    geofence_polygon); `contains()` returns True for any point in that
    case.
    """

    inclusion: tuple[tuple[float, float], ...] = field(default_factory=tuple)
    exclusions: tuple[tuple[tuple[float, float], ...], ...] = field(default_factory=tuple)

    def contains(self, lat: float, lon: float) -> bool:
        """True iff (lat, lon) is inside the inclusion AND outside every
        exclusion. With no inclusion polygon, returns True (open world)
        as long as no exclusion contains the point.
        """
        if self.inclusion and not point_in_polygon(lat, lon, list(self.inclusion)):
            return False
        for excl in self.exclusions:
            if point_in_polygon(lat, lon, list(excl)):
                return False
        return True

    def segment_legal(
        self,
        p1: tuple[float, float],
        p2: tuple[float, float],
    ) -> bool:
        """True iff straight-line travel from p1 to p2 stays inside the
        inclusion AND outside every exclusion.

        Cheap necessary check: both endpoints must be `contains()`-legal.
        Then no inclusion edge may be crossed (else the segment exits
        and re-enters) and no exclusion edge may be crossed.
        """
        if not self.contains(*p1):
            return False
        if not self.contains(*p2):
            return False
        if self.inclusion and segment_intersects_polygon(
            p1, p2, list(self.inclusion)
        ):
            return False
        for excl in self.exclusions:
            if segment_intersects_polygon(p1, p2, list(excl)):
                return False
        return True

    def buffer(self, meters: float) -> "Geofence":
        """Return a new Geofence with inclusion shrunk by `meters` and
        every exclusion grown by `meters`.

        Implementation: a centroid-radial scale. Each polygon's vertices
        are pushed toward (inclusion) or away from (exclusion) the
        polygon centroid by the requested distance. This is **not** a
        true Minkowski offset — concave polygons can self-intersect under
        large offsets — but for the convex-ish boxes used in our
        AOR (~10 km exclusion, ~1 km mission cells) it produces a
        conservative safety margin that's close enough.

        meters == 0 returns an exact copy.
        meters < 0 raises ValueError; use buffer(0) and pass the
        opposite sign in caller code if that semantic is ever needed.
        """
        if meters < 0:
            raise ValueError("buffer meters must be >= 0")
        if meters == 0:
            return Geofence(
                inclusion=tuple(self.inclusion),
                exclusions=tuple(self.exclusions),
            )
        new_incl = _scale_polygon(list(self.inclusion), -meters) if self.inclusion else ()
        new_excl: list[tuple[tuple[float, float], ...]] = []
        for excl in self.exclusions:
            new_excl.append(_scale_polygon(list(excl), +meters))
        return Geofence(
            inclusion=tuple(new_incl),
            exclusions=tuple(new_excl),
        )


def _scale_polygon(
    polygon: list[tuple[float, float]],
    meters: float,
) -> tuple[tuple[float, float], ...]:
    """Push each vertex away from the polygon centroid by `meters`
    (negative meters = shrink toward centroid).

    Used only by Geofence.buffer. Coordinate handling: lat is converted
    by a fixed degrees-per-meter ratio, lon uses the local cos(lat)
    correction at the polygon's centroid latitude.
    """
    pts = list(polygon)
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return tuple(polygon)
    cy = sum(p[0] for p in pts) / len(pts)
    cx = sum(p[1] for p in pts) / len(pts)
    m_per_lon = _meters_per_deg_lon(cy)
    out: list[tuple[float, float]] = []
    for lat, lon in pts:
        # Vector from centroid to vertex, in METERS.
        dy_m = (lat - cy) * _M_PER_DEG_LAT
        dx_m = (lon - cx) * m_per_lon
        d_m = math.hypot(dx_m, dy_m)
        if d_m == 0.0:
            out.append((lat, lon))
            continue
        # New length: original + meters (negative shrinks).
        new_d = d_m + meters
        if new_d <= 0:
            # Vertex would cross the centroid; clamp to centroid.
            out.append((cy, cx))
            continue
        scale = new_d / d_m
        new_dy_m = dy_m * scale
        new_dx_m = dx_m * scale
        new_lat = cy + new_dy_m / _M_PER_DEG_LAT
        new_lon = cx + new_dx_m / m_per_lon
        out.append((new_lat, new_lon))
    # Close the ring to match input convention if the input was closed.
    if polygon and polygon[0] == polygon[-1]:
        out.append(out[0])
    return tuple(out)


# ----------------------------------------------------------------------
# GeoJSON ingest helper (used by sim.mission)
# ----------------------------------------------------------------------

def polygons_from_geojson_feature(feature: dict) -> list[list[tuple[float, float]]]:
    """Extract one or more (lat, lon) rings from a GeoJSON Feature.

    GeoJSON stores coordinates as [lon, lat] (per RFC 7946). We swap to
    (lat, lon) on the way out to match the rest of the simulator's
    convention. Returns the outer ring of each Polygon (or each Polygon
    of a MultiPolygon); ignores inner rings (holes) since the geofence
    model doesn't represent holes — exclusions are first-class instead.
    """
    geom = feature.get("geometry") or {}
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    rings: list[list[tuple[float, float]]] = []
    if gtype == "Polygon":
        if not coords:
            return []
        outer = coords[0]
        rings.append([(float(p[1]), float(p[0])) for p in outer])
    elif gtype == "MultiPolygon":
        for poly in coords:
            if not poly:
                continue
            rings.append([(float(p[1]), float(p[0])) for p in poly[0]])
    return rings


# Convenience: legacy-mode adapter so `sim.mission` can build a Geofence
# from a single inclusion polygon (the historical schema).
def geofence_from_polygon(
    polygon: Iterable[tuple[float, float]] | None,
) -> Geofence:
    if not polygon:
        return Geofence()
    pts = tuple((float(p[0]), float(p[1])) for p in polygon)
    return Geofence(inclusion=pts, exclusions=())
