"""NIFC ArcGIS REST fetcher for historic fire perimeters.

Public, no-auth ArcGIS Feature Service queries. Caches results under
~/.cache/wildfire-watch/historic_fires/<source>/<query_hash>.geojson
so subsequent backtest runs are offline-capable.

Honors `freshness_days` and `--refresh` for cache invalidation.

Stdlib + lazy `requests`. Tests run offline against bundled fixtures.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .sources import HISTORIC_SOURCES, HistoricFireSource, get

CACHE_BASE = Path(
    os.environ.get(
        "WFW_HISTORIC_CACHE", str(Path.home() / ".cache" / "wildfire-watch" / "historic_fires")
    )
)

# Gunnison County, Colorado bounding box (approximate, lat/lon).
# Used as a default geographic filter for the AOR.
GUNNISON_COUNTY_BBOX = {
    "min_lat": 38.15,
    "max_lat": 39.20,
    "min_lon": -107.50,
    "max_lon": -106.20,
}

# Wider Crested Butte / Gunnison corridor, more focused than the county bbox.
CRESTED_BUTTE_CORRIDOR_BBOX = {
    "min_lat": 38.40,
    "max_lat": 39.05,
    "min_lon": -107.10,
    "max_lon": -106.85,
}


@dataclass(frozen=True)
class HistoricFire:
    """A single historic-fire record, source-agnostic.

    All sources normalize to this shape. Ground truth for backtest replay.
    """

    fire_id: str               # source_name + native_id
    name: str
    year: int
    start_date: str | None     # ISO-8601, may be None for older records
    contained_date: str | None
    cause: str | None
    acres_burned: float
    polygon_geojson: dict      # GeoJSON Polygon or MultiPolygon
    centroid_lat: float
    centroid_lon: float
    severity: str | None       # "low" | "moderate" | "high" | None
    state: str
    county: str | None
    source: str
    raw_attributes: dict       # source-native attribute dict


def _cache_key(source_name: str, query: dict[str, Any]) -> Path:
    canonical = json.dumps(query, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()[:16]
    return CACHE_BASE / source_name / f"{digest}.geojson"


def _is_fresh(path: Path, freshness_days: int) -> bool:
    if not path.exists():
        return False
    age_s = (datetime.now(UTC).timestamp()) - path.stat().st_mtime
    return age_s < freshness_days * 86400


def _bbox_polygon(bbox: dict[str, float]) -> dict:
    """Build a GeoJSON Polygon from a bbox dict."""
    return {
        "type": "Polygon",
        "coordinates": [[
            [bbox["min_lon"], bbox["min_lat"]],
            [bbox["max_lon"], bbox["min_lat"]],
            [bbox["max_lon"], bbox["max_lat"]],
            [bbox["min_lon"], bbox["max_lat"]],
            [bbox["min_lon"], bbox["min_lat"]],
        ]],
    }


def _arcgis_query(
    base_url: str,
    *,
    where: str = "1=1",
    geometry_envelope: dict[str, float] | None = None,
    out_fields: str = "*",
    timeout: float = 30.0,
) -> dict:
    """Run an ArcGIS REST `query` against a Feature Service layer.

    Returns the raw response JSON (with .features = list of feature dicts).
    Lazy-imports `requests`. Raises on HTTP error.
    """
    try:
        import requests  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "requests not installed; install with `pip install requests` "
            "or use the bundled fixture for offline use"
        ) from exc

    params: dict[str, Any] = {
        "where": where,
        "outFields": out_fields,
        "f": "geojson",
        "outSR": 4326,
        "returnGeometry": "true",
    }
    if geometry_envelope is not None:
        params["geometry"] = json.dumps({
            "xmin": geometry_envelope["min_lon"],
            "ymin": geometry_envelope["min_lat"],
            "xmax": geometry_envelope["max_lon"],
            "ymax": geometry_envelope["max_lat"],
            "spatialReference": {"wkid": 4326},
        })
        params["geometryType"] = "esriGeometryEnvelope"
        params["spatialRel"] = "esriSpatialRelIntersects"

    url = f"{base_url.rstrip('/')}/query"
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _polygon_centroid(polygon: dict) -> tuple[float, float]:
    """Compute a rough lat/lon centroid for a GeoJSON Polygon or MultiPolygon."""
    if polygon.get("type") == "Polygon":
        rings = polygon["coordinates"]
    elif polygon.get("type") == "MultiPolygon":
        rings = [r for poly in polygon["coordinates"] for r in poly]
    else:
        return (0.0, 0.0)
    if not rings or not rings[0]:
        return (0.0, 0.0)
    outer = rings[0]
    n = len(outer)
    if n == 0:
        return (0.0, 0.0)
    lon_sum = sum(p[0] for p in outer)
    lat_sum = sum(p[1] for p in outer)
    return (lat_sum / n, lon_sum / n)


def _normalize_nifc_feature(feature: dict, source_name: str) -> HistoricFire | None:
    """Convert a raw NIFC GeoJSON feature into a HistoricFire."""
    props = feature.get("properties") or {}
    geom = feature.get("geometry") or {}
    if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
        return None

    name = (
        props.get("IncidentName")
        or props.get("incident_name")
        or props.get("INCIDENT_NAME")
        or props.get("FIRE_NAME")
        or props.get("Name")
        or "unnamed"
    )

    # NIFC stores dates as epoch milliseconds in many layers, ISO in others.
    def _date_from(prop_keys: tuple[str, ...]) -> str | None:
        for k in prop_keys:
            v = props.get(k)
            if v is None:
                continue
            if isinstance(v, str):
                return v
            if isinstance(v, int | float):
                try:
                    return datetime.fromtimestamp(v / 1000.0, tz=UTC).isoformat()
                except (ValueError, OSError):
                    continue
        return None

    start_date = _date_from(
        ("FireDiscoveryDateTime", "fire_discovery_datetime", "DISCOVERY_DATE", "StartDate")
    )
    contained_date = _date_from(
        ("ContainmentDateTime", "containment_datetime", "CONT_DATE", "ContainmentDate")
    )
    year = None
    if start_date:
        try:
            year = int(start_date[:4])
        except ValueError:
            pass
    if year is None:
        year_prop = props.get("FireYear") or props.get("FIRE_YEAR") or props.get("Year")
        try:
            year = int(year_prop) if year_prop else 0
        except (TypeError, ValueError):
            year = 0

    acres = (
        props.get("GISAcres")
        or props.get("gis_acres")
        or props.get("ACRES")
        or props.get("FinalAcres")
        or 0.0
    )
    try:
        acres_f = float(acres)
    except (TypeError, ValueError):
        acres_f = 0.0

    cause = (
        props.get("FireCause")
        or props.get("fire_cause")
        or props.get("CAUSE")
        or props.get("StatisticalCause")
    )
    state = (
        props.get("POOState")
        or props.get("State")
        or props.get("STATE")
        or "?"
    )
    county = (
        props.get("POOCounty")
        or props.get("County")
        or props.get("COUNTY")
    )

    centroid_lat, centroid_lon = _polygon_centroid(geom)
    native_id = (
        props.get("OBJECTID")
        or props.get("UniqueFireIdentifier")
        or props.get("IrwinID")
        or hashlib.sha1(json.dumps(props, sort_keys=True).encode()).hexdigest()[:12]
    )

    return HistoricFire(
        fire_id=f"{source_name}:{native_id}",
        name=str(name).strip() or "unnamed",
        year=year,
        start_date=start_date,
        contained_date=contained_date,
        cause=str(cause) if cause else None,
        acres_burned=acres_f,
        polygon_geojson=geom,
        centroid_lat=float(centroid_lat),
        centroid_lon=float(centroid_lon),
        severity=None,
        state=str(state),
        county=str(county) if county else None,
        source=source_name,
        raw_attributes={k: v for k, v in props.items()},
    )


def fetch_state(
    *,
    state: str = "CO",
    source_name: str = "nifc_wfigs_perimeters",
    refresh: bool = False,
    freshness_days: int = 7,
) -> list[HistoricFire]:
    """Fetch all NIFC fire perimeters for a US state (default CO).

    Cached under ~/.cache/wildfire-watch/historic_fires/<source>/<hash>.geojson.
    """
    src = get(source_name)
    if src is None:
        raise ValueError(f"unknown source: {source_name}")
    if src.fetch_strategy != "arcgis_rest":
        raise NotImplementedError(
            f"fetch_state currently supports arcgis_rest sources only; "
            f"{source_name!r} is {src.fetch_strategy}"
        )

    query = {"state": state, "source": source_name}
    cache_path = _cache_key(source_name, query)
    if refresh or not _is_fresh(cache_path, freshness_days):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        # NIFC layers use POOState / State / etc. — try the most common.
        where = (
            f"POOState IN ('US-{state}','{state}')"
            f" OR State='{state}' OR STATE='{state}'"
        )
        data = _arcgis_query(src.url, where=where)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
    else:
        data = json.loads(cache_path.read_text(encoding="utf-8"))

    fires: list[HistoricFire] = []
    for feature in data.get("features") or []:
        f = _normalize_nifc_feature(feature, source_name)
        if f is not None:
            fires.append(f)
    return fires


def fetch_gunnison_county(
    *,
    source_name: str = "nifc_wfigs_perimeters",
    refresh: bool = False,
    freshness_days: int = 7,
    bbox: dict[str, float] | None = None,
) -> list[HistoricFire]:
    """Fetch all NIFC fire perimeters in (or near) Gunnison County, CO.

    Uses a bounding-box query for efficiency. Defaults to GUNNISON_COUNTY_BBOX.
    """
    src = get(source_name)
    if src is None:
        raise ValueError(f"unknown source: {source_name}")
    if src.fetch_strategy != "arcgis_rest":
        raise NotImplementedError(
            f"fetch_gunnison_county supports arcgis_rest sources only; "
            f"{source_name!r} is {src.fetch_strategy}"
        )

    bbox = bbox or GUNNISON_COUNTY_BBOX
    query = {"bbox": bbox, "source": source_name}
    cache_path = _cache_key(source_name, query)
    if refresh or not _is_fresh(cache_path, freshness_days):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = _arcgis_query(src.url, geometry_envelope=bbox)
        cache_path.write_text(json.dumps(data), encoding="utf-8")
    else:
        data = json.loads(cache_path.read_text(encoding="utf-8"))

    fires: list[HistoricFire] = []
    for feature in data.get("features") or []:
        f = _normalize_nifc_feature(feature, source_name)
        if f is not None:
            fires.append(f)
    return fires


def load_cached(source_name: str) -> list[HistoricFire]:
    """Load every cached HistoricFire for a source. Used offline + in tests."""
    source_dir = CACHE_BASE / source_name
    fires: list[HistoricFire] = []
    if not source_dir.exists():
        return fires
    for path in source_dir.glob("*.geojson"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for feature in data.get("features") or []:
            f = _normalize_nifc_feature(feature, source_name)
            if f is not None:
                fires.append(f)
    return fires


def to_jsonl(fires: list[HistoricFire], output_path: Path) -> int:
    """Write a list of HistoricFire to a JSONL file. Returns the count."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for f in fires:
            row = asdict(f)
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    return len(fires)


def fixture_features() -> list[dict]:
    """Return synthetic NIFC-shaped GeoJSON features for offline tests.

    Three fires across the Gunnison-Crested Butte corridor: a real-name
    1994 South Canyon-style fire (synthetic coords), a 2018 Tincup analog,
    and a 2026 hypothetical for forward-projection tests.
    """
    return [
        {
            "type": "Feature",
            "properties": {
                "OBJECTID": 1001,
                "IncidentName": "Slate River Test Fire (synthetic)",
                "FireDiscoveryDateTime": "2018-07-04T14:30:00Z",
                "ContainmentDateTime": "2018-07-12T18:00:00Z",
                "GISAcres": 1842.5,
                "FireCause": "Lightning",
                "POOState": "US-CO",
                "POOCounty": "Gunnison",
                "FireYear": 2018,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-107.0050, 38.9080],
                    [-107.0050, 38.9160],
                    [-106.9940, 38.9160],
                    [-106.9940, 38.9080],
                    [-107.0050, 38.9080],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "OBJECTID": 1002,
                "IncidentName": "Cement Creek Test Fire (synthetic)",
                "FireDiscoveryDateTime": "2020-08-12T09:15:00Z",
                "ContainmentDateTime": "2020-08-19T17:00:00Z",
                "GISAcres": 624.8,
                "FireCause": "Human - Campfire",
                "POOState": "US-CO",
                "POOCounty": "Gunnison",
                "FireYear": 2020,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-106.9100, 38.8400],
                    [-106.9100, 38.8550],
                    [-106.8950, 38.8550],
                    [-106.8950, 38.8400],
                    [-106.9100, 38.8400],
                ]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "OBJECTID": 1003,
                "IncidentName": "East River Test Fire (synthetic)",
                "FireDiscoveryDateTime": "2022-06-28T11:00:00Z",
                "ContainmentDateTime": "2022-07-05T10:00:00Z",
                "GISAcres": 287.3,
                "FireCause": "Lightning",
                "POOState": "US-CO",
                "POOCounty": "Gunnison",
                "FireYear": 2022,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-106.9700, 38.8800],
                    [-106.9700, 38.9050],
                    [-106.9500, 38.9050],
                    [-106.9500, 38.8800],
                    [-106.9700, 38.8800],
                ]],
            },
        },
    ]


def load_fixture() -> list[HistoricFire]:
    """Load the 3-fire synthetic fixture without hitting the network."""
    fires: list[HistoricFire] = []
    for feature in fixture_features():
        f = _normalize_nifc_feature(feature, "fixture")
        if f is not None:
            fires.append(f)
    return fires
