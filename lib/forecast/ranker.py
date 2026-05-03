"""Forward-projection scout-target ranker.

Combines historic-fire density + fuel-load class + AOR zone metadata into
a per-zone priority score in [0, 100] with a rationale string. Used to
generate the ranked-scout-target list the operator brings to the fire chief.

Pure stdlib + the local repo modules. Deterministic.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sapphire_integration.historical_fires.nifc import HistoricFire

# Fuel-load class -> base score [0, 100]. Cite each value in the demo pack.
FUEL_LOAD_BASE_SCORE = {
    "low": 10.0,
    "moderate": 30.0,
    "moderate-high": 55.0,
    "high": 75.0,
    "extreme": 90.0,
}

# Each historic fire whose centroid is within `BUFFER_KM` of a zone
# centroid contributes to that zone's score. The contribution decays
# linearly inside the buffer so a fire 1 km away is more salient than
# one 10 km away.
HISTORICAL_BUFFER_KM = 15.0
HISTORICAL_WEIGHT = 25.0  # max contribution to score from history alone

# Recency weighting — fires from the last 5 years count more.
RECENCY_HALF_LIFE_YEARS = 8.0

# Zone-area weighting: smaller (sub-1 km^2) zones get a slight boost in
# patrol priority because revisit cadence is cheaper. Caps at +10.
SMALL_ZONE_BONUS_KM2 = 1.0
SMALL_ZONE_BONUS_MAX = 10.0


@dataclass(frozen=True)
class ScoutTarget:
    """One ranked scout target (a zone) for the upcoming fire season."""

    zone_id: str
    corridor: str
    centroid_lat: float
    centroid_lon: float
    area_km2: float
    fuel_load_class: str
    historical_fire_count: int
    historical_acres_total: float
    most_recent_fire_year: int | None
    nearest_fire_distance_km: float | None
    priority_score: float
    recommended_revisit_min: float
    rationale: str
    sources: list[str]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance, km. Stdlib-only."""
    import math
    r_earth_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlon / 2) ** 2
    return 2 * r_earth_km * math.asin(math.sqrt(a))


def _polygon_centroid(coords: list[list[float]]) -> tuple[float, float]:
    """Centroid of a GeoJSON ring (list of [lon, lat] pairs)."""
    if not coords:
        return (0.0, 0.0)
    n = len(coords)
    lon_sum = sum(p[0] for p in coords)
    lat_sum = sum(p[1] for p in coords)
    return (lat_sum / n, lon_sum / n)


def _polygon_area_km2(coords: list[list[float]]) -> float:
    """Approximate area in km^2 via flat-earth shoelace at the centroid latitude.

    For 1km^2 zones at 38 deg N this is accurate to ~0.5%.
    """
    import math
    if len(coords) < 3:
        return 0.0
    lat_c, _ = _polygon_centroid(coords)
    cos_lat = math.cos(math.radians(lat_c))
    # 1 deg lat ≈ 111.32 km, 1 deg lon ≈ 111.32 * cos(lat) km
    lat_km = 111.32
    lon_km = 111.32 * cos_lat
    # Project to local cartesian (km).
    pts = [(p[1] * lat_km, p[0] * lon_km) for p in coords]
    n = len(pts)
    area_2 = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area_2 += x1 * y2 - x2 * y1
    return abs(area_2) / 2.0


def _historical_contribution(
    zone_lat: float,
    zone_lon: float,
    fires: list[HistoricFire],
    *,
    current_year: int,
) -> tuple[float, int, float, int | None, float | None]:
    """Compute the historical-fire contribution to a zone's score.

    Returns (history_score, fire_count_in_buffer, acres_total,
    most_recent_year, nearest_distance_km).
    """
    in_buffer: list[tuple[float, HistoricFire]] = []
    for f in fires:
        d = _haversine_km(zone_lat, zone_lon, f.centroid_lat, f.centroid_lon)
        if d <= HISTORICAL_BUFFER_KM:
            in_buffer.append((d, f))

    if not in_buffer:
        return (0.0, 0, 0.0, None, None)

    fire_count = len(in_buffer)
    acres_total = sum(f.acres_burned for _, f in in_buffer)
    most_recent = max(f.year for _, f in in_buffer if f.year > 0) or None
    nearest = min(d for d, _ in in_buffer)

    # Score: per-fire = (acres / 1000) * recency_factor * proximity_factor
    score = 0.0
    for d, f in in_buffer:
        if f.year <= 0:
            recency = 0.5
        else:
            years_ago = max(0, current_year - f.year)
            recency = 0.5 ** (years_ago / RECENCY_HALF_LIFE_YEARS)
        proximity = 1.0 - (d / HISTORICAL_BUFFER_KM)  # 1 at zero distance, 0 at buffer edge
        acreage = min(1.0, f.acres_burned / 5000.0)   # saturates at 5000 ac
        score += acreage * recency * max(0.0, proximity)
    # Normalize: cap at HISTORICAL_WEIGHT.
    score = min(HISTORICAL_WEIGHT, score * HISTORICAL_WEIGHT / 4.0)
    return (score, fire_count, acres_total, most_recent, nearest)


def _recommended_revisit(priority_score: float) -> float:
    """Higher priority -> shorter revisit interval (min)."""
    if priority_score >= 80:
        return 8.0
    if priority_score >= 60:
        return 12.0
    if priority_score >= 40:
        return 18.0
    if priority_score >= 20:
        return 30.0
    return 60.0


def _build_rationale(
    fuel_score: float,
    history_score: float,
    bonus: float,
    fuel_class: str,
    fire_count: int,
    most_recent: int | None,
    nearest_km: float | None,
) -> str:
    pieces = [f"fuel_load={fuel_class} (+{fuel_score:.0f})"]
    if fire_count:
        recency_str = f", most recent {most_recent}" if most_recent else ""
        nearest_str = f" nearest {nearest_km:.1f}km" if nearest_km is not None else ""
        pieces.append(
            f"history: {fire_count} fires in {HISTORICAL_BUFFER_KM:.0f}km buffer{recency_str}{nearest_str} (+{history_score:.0f})"
        )
    else:
        pieces.append("no historic fires in buffer (+0)")
    if bonus > 0:
        pieces.append(f"small-zone bonus (+{bonus:.0f})")
    return "; ".join(pieces)


def rank_zones(
    zones_geojson: dict,
    *,
    fires: list[HistoricFire] | None = None,
    current_year: int = 2026,
    sources: list[str] | None = None,
) -> list[ScoutTarget]:
    """Rank inclusion zones by priority score.

    Exclusion zones (e.g. wilderness no-fly) are filtered out of the
    output — we don't recommend patrolling no-fly areas.
    """
    fires = fires or []
    sources = sources or [
        "missions/zones/gunnison_crested_butte_corridor.geojson",
        "lib.forecast.ranker (this module)",
    ]
    if fires:
        sources.append("sapphire_integration.historical_fires (NIFC perimeters)")

    targets: list[ScoutTarget] = []
    for feature in zones_geojson.get("features") or []:
        props = feature.get("properties") or {}
        if props.get("exclusion"):
            continue
        zone_id = props.get("zone_id") or "unknown"
        corridor = zones_geojson.get("name") or props.get("corridor") or "unknown"
        fuel_class = props.get("fuel_load_class", "moderate")
        fuel_score = FUEL_LOAD_BASE_SCORE.get(fuel_class, FUEL_LOAD_BASE_SCORE["moderate"])

        geom = feature.get("geometry") or {}
        if geom.get("type") != "Polygon":
            continue
        coords = (geom.get("coordinates") or [[]])[0]
        if not coords:
            continue
        lat, lon = _polygon_centroid(coords)
        area_km2 = _polygon_area_km2(coords)

        history_score, fire_count, acres_total, most_recent, nearest = _historical_contribution(
            lat, lon, fires, current_year=current_year
        )

        # Small-zone bonus
        bonus = 0.0
        if area_km2 < SMALL_ZONE_BONUS_KM2 and area_km2 > 0:
            bonus = SMALL_ZONE_BONUS_MAX * (1.0 - area_km2 / SMALL_ZONE_BONUS_KM2)
            bonus = min(SMALL_ZONE_BONUS_MAX, bonus)

        score = min(100.0, fuel_score + history_score + bonus)
        rationale = _build_rationale(
            fuel_score, history_score, bonus, fuel_class, fire_count, most_recent, nearest
        )

        targets.append(
            ScoutTarget(
                zone_id=zone_id,
                corridor=corridor,
                centroid_lat=lat,
                centroid_lon=lon,
                area_km2=area_km2,
                fuel_load_class=fuel_class,
                historical_fire_count=fire_count,
                historical_acres_total=acres_total,
                most_recent_fire_year=most_recent,
                nearest_fire_distance_km=nearest,
                priority_score=score,
                recommended_revisit_min=_recommended_revisit(score),
                rationale=rationale,
                sources=list(sources),
            )
        )

    targets.sort(key=lambda t: t.priority_score, reverse=True)
    return targets


def summarize(targets: list[ScoutTarget]) -> dict[str, Any]:
    """Aggregate a list of ScoutTargets into a summary dict for the demo pack."""
    if not targets:
        return {
            "total_zones": 0,
            "patrolled_zones": 0,
            "total_aor_km2": 0.0,
            "weighted_priority_mean": 0.0,
        }
    return {
        "total_zones": len(targets),
        "patrolled_zones": sum(1 for t in targets if t.priority_score >= 40),
        "total_aor_km2": sum(t.area_km2 for t in targets),
        "weighted_priority_mean": (
            sum(t.priority_score * t.area_km2 for t in targets)
            / max(1e-9, sum(t.area_km2 for t in targets))
        ),
        "top_zone_id": targets[0].zone_id,
        "top_zone_score": targets[0].priority_score,
        "top_zone_revisit_min": targets[0].recommended_revisit_min,
    }


def to_jsonl(targets: list[ScoutTarget], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for t in targets:
            fh.write(json.dumps(asdict(t), separators=(",", ":")) + "\n")
    return len(targets)
