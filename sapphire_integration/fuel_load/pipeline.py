"""Pipeline: read zones GeoJSON, classify each, write enriched GeoJSON.

Each Feature gets `fuel_load_class`, `risk_score`, `evidence`, and
`rationale` written into its `properties` block. Existing properties
are preserved untouched. Exclusion features (`exclusion: true`) are
PASSED THROUGH unchanged — the classifier doesn't run on no-fly polygons.

The pipeline accepts pre-fetched IDS / fire / CO-WRAP / FIA datasets
as parameters, which makes the unit tests deterministic (no network).
The CLI wires `fetch.py` outputs to these parameters in the live path.

Stdlib only (json) — pyyaml is NOT needed; GeoJSON is straight JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .classifier import classify_zone
from .sources import REGISTERED_SOURCES


def enrich_zones(
    zones_geojson_path: Path,
    *,
    output_path: Optional[Path] = None,
    ids_polygons: Optional[list[dict]] = None,
    historical_fires: Optional[list[dict]] = None,
    co_wrap_scores: Optional[dict[str, float]] = None,
    fia_canopy_pcts: Optional[dict[str, float]] = None,
    reference_year: Optional[int] = None,
) -> Path:
    """Read a zones GeoJSON, classify each non-exclusion zone, write
    enriched GeoJSON.

    `co_wrap_scores` and `fia_canopy_pcts` are dicts keyed by zone_id —
    they let the operator feed per-zone CO-WRAP risk values + FIA canopy
    percentages without round-tripping through a fetch step (CO-WRAP +
    FIA are both manual-only sources per `sources.py`).

    Returns the path the enriched GeoJSON was written to.
    """
    in_path = Path(zones_geojson_path).expanduser()
    if not in_path.exists():
        raise FileNotFoundError(f"zones GeoJSON not found: {in_path}")

    out_path = (
        Path(output_path).expanduser()
        if output_path
        else in_path.with_suffix(".enriched.geojson")
    )

    with in_path.open("r", encoding="utf-8") as f:
        gj = json.load(f)

    if not isinstance(gj, dict) or gj.get("type") != "FeatureCollection":
        raise ValueError(
            f"input must be a GeoJSON FeatureCollection; got {gj.get('type')!r}"
        )

    enriched_features: list[dict] = []
    for feat in gj.get("features", []) or []:
        props = dict(feat.get("properties") or {})
        zone_id = props.get("zone_id", "<unknown>")

        # Pass-through: exclusion features get a stamp but no risk_score.
        if props.get("exclusion") is True:
            props.setdefault("fuel_load_class", "n/a")
            props.setdefault("risk_score", None)
            props.setdefault(
                "rationale",
                "Exclusion zone (regulatory no-fly). Classifier not run.",
            )
            enriched_features.append({**feat, "properties": props})
            continue

        # Extract the outer ring as (lat, lon) per simulator convention.
        ring = _extract_ring_latlon(feat)
        if ring is None or len(ring) < 3:
            props.setdefault("fuel_load_class", props.get("fuel_load_class", "moderate"))
            props.setdefault("rationale", "No usable polygon geometry; classifier skipped.")
            enriched_features.append({**feat, "properties": props})
            continue

        per_zone_cowrap = (
            co_wrap_scores.get(zone_id) if co_wrap_scores else None
        )
        per_zone_fia = (
            fia_canopy_pcts.get(zone_id) if fia_canopy_pcts else None
        )

        result = classify_zone(
            ring,
            ids_polygons=ids_polygons,
            historical_fires=historical_fires,
            co_wrap_risk_score=per_zone_cowrap,
            fia_canopy_pct=per_zone_fia,
            reference_year=reference_year,
        )
        props["fuel_load_class"] = result["fuel_load_class"]
        props["risk_score"] = result["risk_score"]
        props["evidence"] = result["evidence"]
        props["rationale"] = result["rationale"]
        props["data_freshness_days_max"] = result["data_freshness_days_max"]
        enriched_features.append({**feat, "properties": props})

    enriched = {
        **gj,
        "features": enriched_features,
        "fuel_load_metadata": _build_metadata(),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, sort_keys=False)
        f.write("\n")
    return out_path


def _extract_ring_latlon(feature: dict) -> Optional[list[tuple[float, float]]]:
    """Pull the outer ring as (lat, lon) tuples, swapping from GeoJSON's
    [lon, lat] convention."""
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    if geom.get("type") != "Polygon" or not coords:
        return None
    outer = coords[0]
    return [(float(p[1]), float(p[0])) for p in outer if len(p) >= 2]


def _build_metadata() -> dict[str, Any]:
    """Top-level metadata block embedded in the enriched GeoJSON."""
    return {
        "schema_version": "1.0.0",
        "generator": "wildfire-watch sapphire_integration.fuel_load",
        "sources": [
            {
                "name": s.name,
                "url": s.url,
                "license": s.license,
                "citation": s.citation,
            }
            for s in REGISTERED_SOURCES
        ],
        "class_boundaries": {
            "low": "risk_score < 25",
            "moderate": "25 <= risk_score < 50",
            "moderate-high": "50 <= risk_score < 70",
            "high": "70 <= risk_score < 85",
            "extreme": "risk_score >= 85",
        },
    }


__all__ = ["enrich_zones"]
