"""Evidence-based fuel-load + risk-score classifier.

Replaces hand-set `fuel_load_class` strings on AOR zones with a numeric
risk_score (0-100) and a publishable class boundary.

CLASS BOUNDARIES (immutable — referenced from public docs)
----------------------------------------------------------
    risk_score < 25         -> "low"
    25 <= risk_score < 50   -> "moderate"
    50 <= risk_score < 70   -> "moderate-high"
    70 <= risk_score < 85   -> "high"
    risk_score >= 85        -> "extreme"

RISK SCORE FORMULA (weighted blend of available evidence)
----------------------------------------------------------
    component                                weight
    ----------------------------------------------
    IDS overlap pct (severity-weighted)       0.35
    historical-fire density (5km buffer)      0.20
    CO-WRAP risk score                        0.25
    FIA canopy cover %                        0.10
    distance-to-WUI proxy                     0.10

If a component is unavailable (`None`), its weight is redistributed
pro-rata across the remaining present components. So if CO-WRAP is
missing, the IDS, historical-fire, FIA-canopy, and WUI components each
absorb a 0.25 / 4 = 0.0625 share.

Each component is normalized to a 0-100 sub-score. Final risk_score is
the weighted sum (also 0-100).

PROVENANCE
----------
Every component cites the registered source it consumes. See `sources.py`
for the canonical citation block per source.

  - IDS overlap pct          ← `usfs_ids` (USDA FS, Forest Health Protection)
  - historical fires         ← `nifc_fire_perimeters` (NIFC IFPH)
  - CO-WRAP risk             ← `co_wrap` (Colorado State Forest Service)
  - FIA canopy %             ← `usfs_fia` (USDA FS Forest Inventory & Analysis)
  - distance-to-WUI proxy    ← computed in-package from zone geometry +
                                a static WUI anchor list (Crested Butte,
                                Mt. Crested Butte, Gunnison)

Stdlib only. No GDAL, no shapely, no fiona — polygon math reuses
`sim/geofence.py`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Optional


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

CLASS_BOUNDARIES: tuple[tuple[float, str], ...] = (
    (25.0, "low"),
    (50.0, "moderate"),
    (70.0, "moderate-high"),
    (85.0, "high"),
    (float("inf"), "extreme"),
)

# Component weights — must sum to 1.0.
WEIGHTS: dict[str, float] = {
    "ids": 0.35,
    "historical_fires": 0.20,
    "co_wrap": 0.25,
    "fia_canopy": 0.10,
    "wui_distance": 0.10,
}

# Static WUI anchor coordinates (lat, lon). These are the population
# centers the classifier treats as "the wildland-urban interface" for
# the distance-to-WUI proxy. Pulled from AOR.md.
WUI_ANCHORS: tuple[tuple[str, float, float], ...] = (
    ("crested-butte", 38.8697, -106.9878),
    ("mt-crested-butte", 38.8975, -106.9647),
    ("gunnison", 38.5458, -106.9253),
)

# The radius around each WUI anchor that we treat as fully-WUI (sub-score 100).
# Beyond ~10 km the WUI sub-score asymptotes to 0.
WUI_FULL_DISTANCE_KM = 1.0
WUI_ZERO_DISTANCE_KM = 10.0

# IDS severity multipliers — applied to the IDS overlap pct.
# Heavy beetle-kill is treated as a strong fuel-load signal, so the
# multiplier on a "heavy" or "very_heavy" overlap is > 1 (clamped at
# sub-score 100). A "moderate" overlap is treated at parity.
IDS_SEVERITY_MULTIPLIER: dict[str, float] = {
    "very_light": 0.6,
    "light": 0.8,
    "moderate": 1.0,
    "heavy": 1.4,       # 50% heavy-overlap -> sub-score 70
    "very_heavy": 1.7,  # 50% very-heavy-overlap -> sub-score 85
    "unknown": 0.9,
}

# Historical-fire density: number of perimeters in the 5 km buffer that
# saturate the sub-score at 100.
HISTORICAL_FIRE_SATURATION_COUNT = 5

# Recent-fire bonus: a fire within this many years of "now" (the fire-
# perimeter dataset's reporting year) is treated as more predictive.
RECENT_FIRE_THRESHOLD_YEARS = 10
RECENT_FIRE_BONUS_PCT = 15.0


@dataclass(frozen=True)
class IdsPolygon:
    """Lightweight typed view of one IDS polygon.

    The real USFS feed returns much more (TPA, host, agent, year, ...).
    For the classifier we only need the polygon ring (lat, lon vertices
    in the simulator convention) and the severity class.
    """

    polygon: tuple[tuple[float, float], ...]
    severity: str  # one of IDS_SEVERITY_MULTIPLIER keys
    survey_year: int


@dataclass(frozen=True)
class HistoricalFire:
    """One historic fire perimeter."""

    perimeter: tuple[tuple[float, float], ...]
    fire_year: int
    fire_name: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_zone(
    zone_polygon: list[tuple[float, float]],
    *,
    ids_polygons: Optional[list[dict]] = None,
    historical_fires: Optional[list[dict]] = None,
    co_wrap_risk_score: Optional[float] = None,
    fia_canopy_pct: Optional[float] = None,
    reference_year: Optional[int] = None,
) -> dict:
    """Classify one zone polygon into a fuel-load class + risk score.

    Inputs
    ------
    zone_polygon: closed (lat, lon) ring per the simulator convention.
    ids_polygons: list of {polygon: [(lat,lon),...], severity: str,
                  survey_year: int} dicts — already filtered to the AOR.
    historical_fires: list of {perimeter: [(lat,lon),...], fire_year: int,
                  fire_name: str} dicts — already filtered to the AOR
                  bounding box.
    co_wrap_risk_score: 0-100. CO-WRAP publishes 0-5; multiply by 20 in
                  the caller.
    fia_canopy_pct: 0-100. Regional median canopy-cover from FIA.
    reference_year: year the analysis is anchored to (default = current
                  calendar year).

    Returns
    -------
    {
      "fuel_load_class": "low" | "moderate" | "moderate-high" | "high" | "extreme",
      "risk_score": float (0-100),
      "evidence": {
        "ids_overlap_pct": float,
        "ids_severity_class": str,
        "historical_fires_in_buffer_5km": int,
        "most_recent_fire_year": int | None,
        "co_wrap_risk": float | None,
        "fia_canopy_pct": float | None,
        "wui_distance_km": float,
      },
      "rationale": "<1-2 sentence summary>",
      "data_freshness_days_max": int,
    }
    """
    if not zone_polygon or len(zone_polygon) < 3:
        raise ValueError("zone_polygon must have >= 3 vertices")

    if reference_year is None:
        from datetime import datetime, UTC  # noqa: PLC0415
        reference_year = datetime.now(UTC).year

    # --- IDS component -----------------------------------------------------
    ids_overlap_pct, ids_severity_label = _compute_ids_overlap(
        zone_polygon, ids_polygons or []
    )
    ids_subscore: Optional[float] = None
    if ids_polygons is not None:
        # Severity-weighted overlap: clamp at 100.
        mult = IDS_SEVERITY_MULTIPLIER.get(ids_severity_label, 0.7)
        ids_subscore = min(100.0, ids_overlap_pct * mult)

    # --- Historical-fires component ---------------------------------------
    fire_count, most_recent_year = _count_historical_fires(
        zone_polygon, historical_fires or [], buffer_km=5.0
    )
    fires_subscore: Optional[float] = None
    if historical_fires is not None:
        sat = max(1, HISTORICAL_FIRE_SATURATION_COUNT)
        base = min(1.0, fire_count / sat) * 100.0
        if most_recent_year is not None:
            age = max(0, reference_year - most_recent_year)
            if age <= RECENT_FIRE_THRESHOLD_YEARS:
                base = min(100.0, base + RECENT_FIRE_BONUS_PCT)
        fires_subscore = base

    # --- CO-WRAP component -------------------------------------------------
    cowrap_subscore: Optional[float] = None
    if co_wrap_risk_score is not None:
        cowrap_subscore = max(0.0, min(100.0, float(co_wrap_risk_score)))

    # --- FIA canopy-cover component ---------------------------------------
    fia_subscore: Optional[float] = None
    if fia_canopy_pct is not None:
        # Higher canopy = more fuel = higher risk. Treat 80% canopy as the
        # "saturated" sub-score.
        clamped = max(0.0, min(80.0, float(fia_canopy_pct)))
        fia_subscore = (clamped / 80.0) * 100.0

    # --- WUI distance component (always available — derived in-package) ----
    wui_distance_km = _min_distance_to_wui_km(zone_polygon)
    wui_subscore = _wui_distance_to_subscore(wui_distance_km)

    # --- Weighted blend ----------------------------------------------------
    components: dict[str, Optional[float]] = {
        "ids": ids_subscore,
        "historical_fires": fires_subscore,
        "co_wrap": cowrap_subscore,
        "fia_canopy": fia_subscore,
        "wui_distance": wui_subscore,
    }
    risk_score = _weighted_blend(components)
    fuel_load_class = _class_for_score(risk_score)

    # --- Freshness ---------------------------------------------------------
    freshness_days_max = _data_freshness_max(components)

    rationale = _build_rationale(
        fuel_load_class=fuel_load_class,
        risk_score=risk_score,
        ids_overlap_pct=ids_overlap_pct if ids_polygons is not None else None,
        ids_severity=ids_severity_label if ids_polygons is not None else None,
        fire_count=fire_count if historical_fires is not None else None,
        most_recent_year=most_recent_year,
        co_wrap=cowrap_subscore,
        wui_distance_km=wui_distance_km,
    )

    return {
        "fuel_load_class": fuel_load_class,
        "risk_score": round(risk_score, 2),
        "evidence": {
            "ids_overlap_pct": round(ids_overlap_pct, 2),
            "ids_severity_class": ids_severity_label,
            "historical_fires_in_buffer_5km": fire_count,
            "most_recent_fire_year": most_recent_year,
            "co_wrap_risk": (round(cowrap_subscore, 2) if cowrap_subscore is not None else None),
            "fia_canopy_pct": (round(float(fia_canopy_pct), 2) if fia_canopy_pct is not None else None),
            "wui_distance_km": round(wui_distance_km, 3),
        },
        "rationale": rationale,
        "data_freshness_days_max": freshness_days_max,
    }


# ---------------------------------------------------------------------------
# IDS overlap math
# ---------------------------------------------------------------------------

def _compute_ids_overlap(
    zone_polygon: list[tuple[float, float]],
    ids_polygons: list[dict],
) -> tuple[float, str]:
    """Estimate the pct of `zone_polygon` that's covered by IDS polygons.

    Approach: sample-grid Monte Carlo on the zone bounding box. For every
    sample we check (a) is it inside the zone, and (b) is it inside any
    IDS polygon. The ratio (b)/(a) is the overlap pct.

    Returns (overlap_pct, dominant_severity_class). Dominant severity is
    the most-common severity among IDS polygons that cover any sample.
    """
    if not ids_polygons:
        return 0.0, "unknown"

    # Bounding box of the zone.
    lat_min = min(p[0] for p in zone_polygon)
    lat_max = max(p[0] for p in zone_polygon)
    lon_min = min(p[1] for p in zone_polygon)
    lon_max = max(p[1] for p in zone_polygon)

    # 30x30 grid is plenty for ~1 km^2 zones.
    n = 30
    inside_zone = 0
    inside_ids = 0
    severity_counts: dict[str, int] = {}

    # Local import to avoid circular dependency at package load.
    from sim.geofence import point_in_polygon  # noqa: PLC0415

    zone_pts = list(zone_polygon)
    ids_views: list[tuple[list[tuple[float, float]], str]] = []
    for poly_dict in ids_polygons:
        ring = list(poly_dict.get("polygon") or [])
        sev = str(poly_dict.get("severity", "unknown"))
        if len(ring) >= 3:
            ids_views.append((ring, sev))

    if not ids_views:
        return 0.0, "unknown"

    for i in range(n):
        for j in range(n):
            lat = lat_min + (lat_max - lat_min) * (i + 0.5) / n
            lon = lon_min + (lon_max - lon_min) * (j + 0.5) / n
            if not point_in_polygon(lat, lon, zone_pts):
                continue
            inside_zone += 1
            for ring, sev in ids_views:
                if point_in_polygon(lat, lon, ring):
                    inside_ids += 1
                    severity_counts[sev] = severity_counts.get(sev, 0) + 1
                    break

    if inside_zone == 0:
        return 0.0, "unknown"

    overlap_pct = (inside_ids / inside_zone) * 100.0
    dominant = max(severity_counts.items(), key=lambda kv: kv[1])[0] if severity_counts else "unknown"
    return overlap_pct, dominant


def _count_historical_fires(
    zone_polygon: list[tuple[float, float]],
    fires: list[dict],
    *,
    buffer_km: float,
) -> tuple[int, Optional[int]]:
    """Count historical fire perimeters within `buffer_km` of the zone centroid.

    Returns (count, most_recent_year). Coarse: any perimeter whose
    bounding-box centroid lies within `buffer_km` km of the zone
    centroid. Good enough for the AOR-scale 5 km buffer.
    """
    if not fires:
        return 0, None

    czl, czo = _polygon_centroid(zone_polygon)
    count = 0
    most_recent: Optional[int] = None
    for f in fires:
        perim = f.get("perimeter") or []
        if not perim or len(perim) < 3:
            continue
        cfl, cfo = _polygon_centroid(perim)
        d_km = _haversine_km(czl, czo, cfl, cfo)
        if d_km <= buffer_km:
            count += 1
            year = f.get("fire_year")
            if isinstance(year, int):
                if most_recent is None or year > most_recent:
                    most_recent = year
    return count, most_recent


# ---------------------------------------------------------------------------
# Geometry helpers (no shapely)
# ---------------------------------------------------------------------------

def _polygon_centroid(polygon: Iterable[tuple[float, float]]) -> tuple[float, float]:
    """Average-vertex centroid. Sufficient for AOR-scale polygons."""
    pts = [p for p in polygon if isinstance(p, (tuple, list)) and len(p) >= 2]
    if not pts:
        return 0.0, 0.0
    if pts[0] == pts[-1] and len(pts) > 1:
        pts = pts[:-1]
    n = max(1, len(pts))
    return (
        sum(p[0] for p in pts) / n,
        sum(p[1] for p in pts) / n,
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _min_distance_to_wui_km(zone_polygon: list[tuple[float, float]]) -> float:
    """Min haversine distance from zone centroid to any WUI anchor."""
    cz_lat, cz_lon = _polygon_centroid(zone_polygon)
    return min(
        _haversine_km(cz_lat, cz_lon, lat, lon)
        for _, lat, lon in WUI_ANCHORS
    )


def _wui_distance_to_subscore(distance_km: float) -> float:
    """Map distance-to-WUI to a 0-100 sub-score.

    Closer = higher risk. <= WUI_FULL_DISTANCE_KM clamps to 100.
    >= WUI_ZERO_DISTANCE_KM clamps to 0. Linear in between.
    """
    if distance_km <= WUI_FULL_DISTANCE_KM:
        return 100.0
    if distance_km >= WUI_ZERO_DISTANCE_KM:
        return 0.0
    span = WUI_ZERO_DISTANCE_KM - WUI_FULL_DISTANCE_KM
    frac = (distance_km - WUI_FULL_DISTANCE_KM) / span
    return 100.0 * (1.0 - frac)


# ---------------------------------------------------------------------------
# Score blending + class lookup
# ---------------------------------------------------------------------------

def _weighted_blend(components: dict[str, Optional[float]]) -> float:
    """Weighted blend with pro-rata redistribution of missing components."""
    present_w_total = sum(
        WEIGHTS[k] for k, v in components.items() if v is not None
    )
    if present_w_total <= 0:
        return 0.0
    score = 0.0
    for k, v in components.items():
        if v is None:
            continue
        # Pro-rata redistribute: scale this component's weight up so
        # present-component weights sum to 1.
        w = WEIGHTS[k] / present_w_total
        score += w * float(v)
    return max(0.0, min(100.0, score))


def _class_for_score(score: float) -> str:
    """Map a 0-100 score to one of the five class strings."""
    for upper, label in CLASS_BOUNDARIES:
        if score < upper:
            return label
    return "extreme"


def _data_freshness_max(components: dict[str, Optional[float]]) -> int:
    """Worst-case freshness across the components used in this analysis."""
    # Map components to source names for freshness lookup.
    src_map = {
        "ids": "usfs_ids",
        "historical_fires": "nifc_fire_perimeters",
        "co_wrap": "co_wrap",
        "fia_canopy": "usfs_fia",
    }
    from .sources import get_source  # noqa: PLC0415

    worst = 0
    for comp, src_name in src_map.items():
        if components.get(comp) is None:
            continue
        try:
            src = get_source(src_name)
            worst = max(worst, src.freshness_days)
        except KeyError:
            continue
    return worst


def _build_rationale(
    *,
    fuel_load_class: str,
    risk_score: float,
    ids_overlap_pct: Optional[float],
    ids_severity: Optional[str],
    fire_count: Optional[int],
    most_recent_year: Optional[int],
    co_wrap: Optional[float],
    wui_distance_km: float,
) -> str:
    """Plain-English 1-2 sentence summary of the score."""
    parts: list[str] = [
        f"Classified {fuel_load_class} (risk_score={risk_score:.1f}/100)."
    ]
    drivers: list[str] = []
    if ids_overlap_pct is not None and ids_overlap_pct > 0:
        drivers.append(
            f"IDS beetle-kill overlap {ids_overlap_pct:.0f}% ({ids_severity})"
        )
    if fire_count is not None and fire_count > 0:
        if most_recent_year is not None:
            drivers.append(
                f"{fire_count} historic fires within 5km (most recent {most_recent_year})"
            )
        else:
            drivers.append(f"{fire_count} historic fires within 5km")
    if co_wrap is not None:
        drivers.append(f"CO-WRAP risk {co_wrap:.0f}/100")
    if wui_distance_km < WUI_ZERO_DISTANCE_KM:
        drivers.append(f"{wui_distance_km:.1f} km to nearest WUI anchor")
    if drivers:
        parts.append("Drivers: " + "; ".join(drivers) + ".")
    else:
        parts.append("No active beetle-kill or fire-history evidence; score driven by WUI proxy alone.")
    return " ".join(parts)


__all__ = [
    "CLASS_BOUNDARIES",
    "WEIGHTS",
    "WUI_ANCHORS",
    "IdsPolygon",
    "HistoricalFire",
    "classify_zone",
]
