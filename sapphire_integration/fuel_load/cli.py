"""CLI for the fuel-load ingestion + classifier pipeline.

Usage
-----
List registered sources:

    python -m sapphire_integration.fuel_load.cli sources

Fetch a source artifact into the cache:

    python -m sapphire_integration.fuel_load.cli fetch usfs_ids
    python -m sapphire_integration.fuel_load.cli fetch nifc_fire_perimeters --force

Enrich a zones GeoJSON file:

    python -m sapphire_integration.fuel_load.cli enrich \
        missions/zones/gunnison_crested_butte_corridor.geojson \
        --out missions/zones/gunnison_crested_butte_corridor.enriched.geojson

Classify a single ad-hoc polygon (JSON [[lat,lon],...]):

    python -m sapphire_integration.fuel_load.cli classify-zone \
        --polygon '[[38.9035,-107.0060],[38.9165,-107.0060],[38.9165,-106.9940],[38.9035,-106.9940]]'
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .classifier import classify_zone
from .fetch import FetchUnavailable, fetch_to_cache
from .pipeline import enrich_zones
from .sources import REGISTERED_SOURCES, get_source


def _cmd_sources(_: argparse.Namespace) -> int:
    """Print the registered sources as a human-readable table."""
    for s in REGISTERED_SOURCES:
        print(f"- {s.name}")
        print(f"    url:        {s.url}")
        print(f"    license:    {s.license}")
        print(f"    strategy:   {s.fetch_strategy}")
        print(f"    freshness:  {s.freshness_days} days")
        print(f"    citation:   {s.citation}")
        print()
    return 0


def _cmd_fetch(args: argparse.Namespace) -> int:
    """Fetch one source into the cache."""
    try:
        src = get_source(args.source_name)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        result = fetch_to_cache(src, force=args.force)
    except FetchUnavailable as e:
        print(f"unavailable: {e}", file=sys.stderr)
        return 3
    print(f"fetched {src.name}")
    print(f"  cache_path: {result.cache_path}")
    print(f"  sha256:     {result.sha256}")
    print(f"  bytes:      {result.bytes_written}")
    return 0


def _cmd_enrich(args: argparse.Namespace) -> int:
    """Run the pipeline on a zones GeoJSON file."""
    in_path = Path(args.zones_geojson)
    out_path = Path(args.out) if args.out else None

    cowrap = _load_zone_keyed_floats(args.co_wrap_json) if args.co_wrap_json else None
    fia = _load_zone_keyed_floats(args.fia_json) if args.fia_json else None

    written = enrich_zones(
        in_path,
        output_path=out_path,
        co_wrap_scores=cowrap,
        fia_canopy_pcts=fia,
    )
    print(f"wrote enriched zones to {written}")
    return 0


def _cmd_classify_zone(args: argparse.Namespace) -> int:
    """Classify one ad-hoc polygon. Polygon is a JSON array of [lat,lon]."""
    try:
        ring = json.loads(args.polygon)
    except json.JSONDecodeError as e:
        print(f"error: --polygon is not valid JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(ring, list) or len(ring) < 3:
        print("error: --polygon must be a list of >= 3 [lat,lon] pairs", file=sys.stderr)
        return 2
    try:
        ring_pts = [(float(p[0]), float(p[1])) for p in ring]
    except (ValueError, TypeError, IndexError) as e:
        print(f"error: malformed polygon vertex: {e}", file=sys.stderr)
        return 2

    result = classify_zone(
        ring_pts,
        ids_polygons=None,
        historical_fires=None,
        co_wrap_risk_score=args.co_wrap,
        fia_canopy_pct=args.fia_canopy,
    )
    print(json.dumps(result, indent=2))
    return 0


def _load_zone_keyed_floats(path: str) -> dict[str, float]:
    """Load a {zone_id: float} mapping from JSON."""
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"zone-keyed JSON not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{p} must be a JSON object of {{zone_id: number}}")
    return {str(k): float(v) for k, v in data.items()}


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse hierarchy. Exposed for testing."""
    parser = argparse.ArgumentParser(
        prog="python -m sapphire_integration.fuel_load.cli",
        description="Public fuel-load + wildfire-risk data ingestion CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_sources = sub.add_parser("sources", help="List registered data sources")
    p_sources.set_defaults(func=_cmd_sources)

    p_fetch = sub.add_parser("fetch", help="Fetch a source into the cache")
    p_fetch.add_argument("source_name", help="Registered source name (e.g. usfs_ids)")
    p_fetch.add_argument("--force", action="store_true", help="Bypass freshness cache")
    p_fetch.set_defaults(func=_cmd_fetch)

    p_enrich = sub.add_parser("enrich", help="Enrich a zones GeoJSON file")
    p_enrich.add_argument("zones_geojson", help="Path to input zones GeoJSON")
    p_enrich.add_argument("--out", help="Output path (default <input>.enriched.geojson)")
    p_enrich.add_argument(
        "--co-wrap-json",
        help='Path to JSON {zone_id: co_wrap_score (0-100)}',
    )
    p_enrich.add_argument(
        "--fia-json",
        help='Path to JSON {zone_id: fia_canopy_pct (0-100)}',
    )
    p_enrich.set_defaults(func=_cmd_enrich)

    p_class = sub.add_parser("classify-zone", help="Classify one ad-hoc polygon")
    p_class.add_argument("--polygon", required=True, help='JSON [[lat,lon],...]')
    p_class.add_argument("--co-wrap", type=float, default=None, help="CO-WRAP score 0-100")
    p_class.add_argument("--fia-canopy", type=float, default=None, help="FIA canopy %")
    p_class.set_defaults(func=_cmd_classify_zone)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    return int(func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
