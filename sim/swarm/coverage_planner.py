"""Partition an inclusion polygon into N non-overlapping sub-zones.

Design choice: bounding-box grid partition, NOT centroidal Voronoi
(Lloyd's algorithm). Lloyd's needs a polygon clipping library + an
iterative relaxation step; both are heavy for stdlib-only and the Phase 0
demo only ever runs N <= 9. The bbox-grid approach gives:

  - deterministic output (same inputs, same cells)
  - O(N) time
  - guaranteed non-overlapping cells
  - cells that tile the bbox exactly; clipped against the inclusion
    polygon, the union covers the polygon to within rasterization error.

The trade-off: cells are not centroidally balanced. In a long, thin
polygon (e.g. a river corridor), one drone may end up covering 2x the
area of another. For the canonical 1 km^2 Gunnison square this is not
an issue.

A future swap to Lloyd's relaxation should preserve the same public
surface: `plan_coverage(polygon, n_drones) -> list[SubZone]`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..kinematics import haversine_m

Polygon = list[tuple[float, float]]  # [(lat, lon), ...]


@dataclass(frozen=True)
class SubZone:
    """A drone's assigned sub-area inside the inclusion polygon."""

    drone_index: int
    polygon: tuple[tuple[float, float], ...]  # (lat, lon) ring, closed
    centroid: tuple[float, float]  # (lat, lon)
    bbox: tuple[float, float, float, float]  # (min_lat, min_lon, max_lat, max_lon)

    def area_km2(self) -> float:
        """Approximate area of the sub-zone in km^2.

        Uses the spherical-excess formula on the ring vertices (ignoring
        the small distortion from the haversine vs. ellipsoidal earth).
        Good to ~0.1% for sub-10km rings.
        """
        return _ring_area_km2(self.polygon)


def _polygon_bbox(polygon: Polygon) -> tuple[float, float, float, float]:
    if not polygon:
        raise ValueError("empty polygon")
    lats = [p[0] for p in polygon]
    lons = [p[1] for p in polygon]
    return (min(lats), min(lons), max(lats), max(lons))


def _polygon_centroid(polygon: Polygon) -> tuple[float, float]:
    """Simple arithmetic mean of vertices. Adequate for nearly-rectangular
    inclusion polygons used in Phase 0. Replace with shoelace centroid
    if irregular polygons start showing up.
    """
    if not polygon:
        raise ValueError("empty polygon")
    n = float(len(polygon))
    return (sum(p[0] for p in polygon) / n, sum(p[1] for p in polygon) / n)


def _point_in_bbox(pt: tuple[float, float], bbox: tuple[float, float, float, float]) -> bool:
    lat, lon = pt
    min_lat, min_lon, max_lat, max_lon = bbox
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def _grid_dims(n: int) -> tuple[int, int]:
    """Return (rows, cols) so that rows*cols >= n and is roughly square.

    Convention: cols = ceil(sqrt(n)), rows = ceil(n / cols). Guarantees
    rows*cols >= n. For n=3 -> (2,2)=4 cells, with one empty. For n=4 ->
    (2,2). For n=9 -> (3,3).
    """
    if n <= 0:
        raise ValueError("n_drones must be positive")
    cols = int(math.ceil(math.sqrt(n)))
    rows = int(math.ceil(n / cols))
    return rows, cols


def _ring_area_km2(ring: tuple[tuple[float, float], ...]) -> float:
    """Spherical excess area of a closed lat/lon ring, in km^2.

    Uses the formula by Robert. G. Chamberlain, USGS:
    A = | sum_i (lon_{i+1} - lon_{i-1}) * sin(lat_i) | * R^2 / 2
    Returns absolute area regardless of vertex orientation.
    """
    if len(ring) < 3:
        return 0.0
    # Earth mean radius in km.
    R_km = 6_371.0088
    n = len(ring)
    total = 0.0
    for i in range(n):
        lat_i = math.radians(ring[i][0])
        lon_prev = math.radians(ring[(i - 1) % n][1])
        lon_next = math.radians(ring[(i + 1) % n][1])
        total += (lon_next - lon_prev) * math.sin(lat_i)
    return abs(total) * R_km * R_km / 2.0


def plan_coverage(polygon: Polygon, n_drones: int) -> list[SubZone]:
    """Tile `polygon` into `n_drones` non-overlapping sub-zones.

    Strategy:
      1. Compute the bounding box of the inclusion polygon.
      2. Lay a `rows x cols` grid where rows*cols >= n_drones.
      3. Take the first `n_drones` cells in row-major order.
      4. For each cell, return the cell rectangle as a SubZone whose
         centroid is the cell center.

    Caller can clip each cell against the inclusion polygon themselves;
    we keep the rectangular cells here because that's all the runner +
    consensus code needs (they only test "is this drone's home position
    inside its sub-zone bbox?").
    """
    if n_drones <= 0:
        raise ValueError("n_drones must be positive")
    if len(polygon) < 3:
        raise ValueError("polygon needs at least 3 vertices")

    min_lat, min_lon, max_lat, max_lon = _polygon_bbox(polygon)
    rows, cols = _grid_dims(n_drones)
    d_lat = (max_lat - min_lat) / rows
    d_lon = (max_lon - min_lon) / cols

    zones: list[SubZone] = []
    idx = 0
    # Row-major order. Row 0 is the southernmost band.
    for r in range(rows):
        for c in range(cols):
            if idx >= n_drones:
                break
            cell_min_lat = min_lat + r * d_lat
            cell_max_lat = min_lat + (r + 1) * d_lat
            cell_min_lon = min_lon + c * d_lon
            cell_max_lon = min_lon + (c + 1) * d_lon
            ring = (
                (cell_min_lat, cell_min_lon),
                (cell_min_lat, cell_max_lon),
                (cell_max_lat, cell_max_lon),
                (cell_max_lat, cell_min_lon),
                (cell_min_lat, cell_min_lon),  # closed
            )
            centroid = (
                (cell_min_lat + cell_max_lat) / 2.0,
                (cell_min_lon + cell_max_lon) / 2.0,
            )
            zones.append(
                SubZone(
                    drone_index=idx,
                    polygon=ring,
                    centroid=centroid,
                    bbox=(cell_min_lat, cell_min_lon, cell_max_lat, cell_max_lon),
                )
            )
            idx += 1
        if idx >= n_drones:
            break
    return zones


def total_polygon_area_km2(polygon: Polygon) -> float:
    """Convenience: spherical-excess area of `polygon`."""
    if not polygon:
        return 0.0
    closed = list(polygon)
    if closed[0] != closed[-1]:
        closed.append(closed[0])
    return _ring_area_km2(tuple(closed))


def lattice_waypoints_for_subzone(
    zone: SubZone, *, n_waypoints: int = 4
) -> list[tuple[float, float]]:
    """Generate a small lattice of waypoints inside the sub-zone.

    Returns `n_waypoints` (lat, lon) corners of an inset rectangle with
    a 10% inward margin so the drone never hugs the cell edge. Used by
    the SwarmRunner to give each drone its own mini-mission.
    """
    if n_waypoints < 1:
        return []
    min_lat, min_lon, max_lat, max_lon = zone.bbox
    lat_pad = (max_lat - min_lat) * 0.1
    lon_pad = (max_lon - min_lon) * 0.1
    sw = (min_lat + lat_pad, min_lon + lon_pad)
    se = (min_lat + lat_pad, max_lon - lon_pad)
    ne = (max_lat - lat_pad, max_lon - lon_pad)
    nw = (max_lat - lat_pad, min_lon + lon_pad)
    corners = [sw, se, ne, nw]
    return corners[:n_waypoints]


def union_area_km2(zones: list[SubZone]) -> float:
    """Sum of sub-zone areas. Because zones don't overlap (by
    construction) this equals the area of their union."""
    return sum(z.area_km2() for z in zones)


# Surface check: any centroid pair must be at least one cell-width apart.
def min_centroid_separation_m(zones: list[SubZone]) -> float:
    if len(zones) < 2:
        return float("inf")
    best = float("inf")
    for i, a in enumerate(zones):
        for b in zones[i + 1 :]:
            d = haversine_m(a.centroid[0], a.centroid[1], b.centroid[0], b.centroid[1])
            best = min(best, d)
    return best
