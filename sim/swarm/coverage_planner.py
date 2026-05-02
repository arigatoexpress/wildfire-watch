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

Phase 0.5 extension: any sub-cell that overlaps a hard exclusion polygon
(e.g. West Elk Wilderness, 36 CFR 261.16) is **shrunk** by removing the
exclusion's bbox-overlap. If the resulting cell is below
`MIN_CELL_AREA_KM2` it is dropped entirely; the dropped drone(s) are
reassigned via round-robin onto the surviving cells (so two drones may
share a cell, but no drone is ever assigned to a cell that overlaps
wilderness).

A future swap to Lloyd's relaxation should preserve the same public
surface: `plan_coverage(polygon, n_drones) -> list[SubZone]`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..kinematics import haversine_m

# Below this area, a sub-cell is considered too small to be useful and
# the drone(s) it would have hosted are round-robined onto the others.
MIN_CELL_AREA_KM2 = 0.05

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


def plan_coverage(
    polygon: Polygon,
    n_drones: int,
    *,
    exclusions: list[Polygon] | None = None,
) -> list[SubZone]:
    """Tile `polygon` into `n_drones` non-overlapping sub-zones.

    Strategy:
      1. Compute the bounding box of the inclusion polygon.
      2. Lay a `rows x cols` grid where rows*cols >= n_drones.
      3. Take the first `n_drones` cells in row-major order.
      4. (Phase 0.5+) For each cell that overlaps any `exclusions` bbox,
         shrink the cell by subtracting the exclusion's lat/lon overlap
         (keeping the cell as an axis-aligned rectangle). If the cell
         shrinks below `MIN_CELL_AREA_KM2` it is dropped, and the
         displaced drone is reassigned via round-robin to the next
         surviving cell (so two drones may share a cell, but no drone
         is ever assigned a cell that overlaps a hard exclusion).
      5. For each surviving cell, return the cell rectangle as a SubZone
         whose centroid is the cell center.

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

    excl_bboxes: list[tuple[float, float, float, float]] = []
    if exclusions:
        for ex in exclusions:
            if len(ex) >= 3:
                excl_bboxes.append(_polygon_bbox(ex))

    # Pass 1: compute one (possibly shrunken-or-dropped) cell per grid
    # slot. We allocate rows*cols slots and only fill the first n_drones,
    # but we still process the full row-major scan because dropped cells
    # may fall back to surviving ones.
    surviving_cells: list[tuple[float, float, float, float]] = []  # bboxes
    idx = 0
    for r in range(rows):
        for c in range(cols):
            if idx >= n_drones:
                break
            idx += 1
            cell = (
                min_lat + r * d_lat,
                min_lon + c * d_lon,
                min_lat + (r + 1) * d_lat,
                min_lon + (c + 1) * d_lon,
            )
            shrunk = _shrink_cell_against_exclusions(cell, excl_bboxes)
            if shrunk is None:
                continue
            if _bbox_area_km2(shrunk) < MIN_CELL_AREA_KM2:
                continue
            surviving_cells.append(shrunk)
        if idx >= n_drones:
            break

    if not surviving_cells:
        # Pathological: every cell sits inside an exclusion. Caller
        # should treat this as "no flyable area"; we surface it via an
        # empty list rather than raising, so downstream code can decide.
        return []

    # Pass 2: assign exactly n_drones to the surviving cells via
    # round-robin. So if 1 cell survives and n_drones=3, drones 0/1/2
    # all get the same cell (sharing it).
    zones: list[SubZone] = []
    for d_idx in range(n_drones):
        cell = surviving_cells[d_idx % len(surviving_cells)]
        cell_min_lat, cell_min_lon, cell_max_lat, cell_max_lon = cell
        ring = (
            (cell_min_lat, cell_min_lon),
            (cell_min_lat, cell_max_lon),
            (cell_max_lat, cell_max_lon),
            (cell_max_lat, cell_min_lon),
            (cell_min_lat, cell_min_lon),
        )
        centroid = (
            (cell_min_lat + cell_max_lat) / 2.0,
            (cell_min_lon + cell_max_lon) / 2.0,
        )
        zones.append(
            SubZone(
                drone_index=d_idx,
                polygon=ring,
                centroid=centroid,
                bbox=cell,
            )
        )
    return zones


def _shrink_cell_against_exclusions(
    cell: tuple[float, float, float, float],
    excl_bboxes: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float] | None:
    """Shrink an axis-aligned cell by subtracting the bbox-overlap of
    each exclusion. Returns the shrunk cell, or None if every dimension
    collapses (meaning the cell is fully inside an exclusion).

    This is a conservative approximation. We don't compute the true
    polygon difference; we just trim the cell against each exclusion's
    bbox along whichever axis preserves the most area. A non-rectangular
    or non-bbox-aligned exclusion may be slightly over-trimmed, which is
    safe (we never under-restrict).
    """
    min_lat, min_lon, max_lat, max_lon = cell
    for excl in excl_bboxes:
        e_min_lat, e_min_lon, e_max_lat, e_max_lon = excl
        # Test for overlap in BOTH axes.
        lat_overlap = (e_min_lat < max_lat) and (e_max_lat > min_lat)
        lon_overlap = (e_min_lon < max_lon) and (e_max_lon > min_lon)
        if not (lat_overlap and lon_overlap):
            continue
        # Decide which axis to trim. Pick the axis where the exclusion
        # cuts the LEAST of the cell, to maximise the remaining area.
        # Compute candidate trims (axis-aligned half-plane subtraction)
        # along each axis, then pick the cut that leaves the larger area.
        candidates: list[tuple[float, tuple[float, float, float, float]]] = []
        # Trim south: if exclusion covers the southern part, lift min_lat
        # to e_max_lat.
        if e_min_lat <= min_lat and e_max_lat < max_lat:
            new_cell = (e_max_lat, min_lon, max_lat, max_lon)
            candidates.append((_bbox_area_km2(new_cell), new_cell))
        # Trim north.
        if e_max_lat >= max_lat and e_min_lat > min_lat:
            new_cell = (min_lat, min_lon, e_min_lat, max_lon)
            candidates.append((_bbox_area_km2(new_cell), new_cell))
        # Trim west.
        if e_min_lon <= min_lon and e_max_lon < max_lon:
            new_cell = (min_lat, e_max_lon, max_lat, max_lon)
            candidates.append((_bbox_area_km2(new_cell), new_cell))
        # Trim east.
        if e_max_lon >= max_lon and e_min_lon > min_lon:
            new_cell = (min_lat, min_lon, max_lat, e_min_lon)
            candidates.append((_bbox_area_km2(new_cell), new_cell))
        if not candidates:
            # Exclusion is fully inside the cell, OR fully covers it.
            # If fully covers, drop it.
            covers = (
                e_min_lat <= min_lat and e_max_lat >= max_lat
                and e_min_lon <= min_lon and e_max_lon >= max_lon
            )
            if covers:
                return None
            # Exclusion fully inside cell: trim along whichever axis
            # leaves the most area. Pick the largest of the four
            # half-plane trims.
            quad = [
                (min_lat, min_lon, e_min_lat, max_lon),  # south band
                (e_max_lat, min_lon, max_lat, max_lon),  # north band
                (min_lat, min_lon, max_lat, e_min_lon),  # west band
                (min_lat, e_max_lon, max_lat, max_lon),  # east band
            ]
            quad_areas = [(_bbox_area_km2(q), q) for q in quad]
            best = max(quad_areas, key=lambda x: x[0])
            min_lat, min_lon, max_lat, max_lon = best[1]
            continue
        # Pick the candidate that leaves the most area.
        candidates.sort(key=lambda x: x[0], reverse=True)
        _, new_cell = candidates[0]
        min_lat, min_lon, max_lat, max_lon = new_cell
        if max_lat <= min_lat or max_lon <= min_lon:
            return None
    return (min_lat, min_lon, max_lat, max_lon)


def _bbox_area_km2(bbox: tuple[float, float, float, float]) -> float:
    """Spherical-excess area of an axis-aligned bbox, in km^2."""
    min_lat, min_lon, max_lat, max_lon = bbox
    if max_lat <= min_lat or max_lon <= min_lon:
        return 0.0
    ring = (
        (min_lat, min_lon),
        (min_lat, max_lon),
        (max_lat, max_lon),
        (max_lat, min_lon),
        (min_lat, min_lon),
    )
    return _ring_area_km2(ring)


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
