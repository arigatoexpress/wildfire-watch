"""CLI for the historic-fire ingester.

Usage:

    python -m sapphire_integration.historical_fires.cli sources
    python -m sapphire_integration.historical_fires.cli fetch-state --state CO
    python -m sapphire_integration.historical_fires.cli fetch-gunnison
    python -m sapphire_integration.historical_fires.cli export --out fires.jsonl
    python -m sapphire_integration.historical_fires.cli fixture --out fixture.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import nifc, sources


def _cmd_sources(args: argparse.Namespace) -> int:
    rows = sources.list_sources()
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    print(f"{len(rows)} historic-fire sources registered:\n")
    for r in rows:
        print(f"- {r['name']}")
        print(f"    {r['url']}")
        print(f"    {r['fetch_strategy']:18s} {r['license']:25s} {r['earliest_year']}-{r['latest_year'] or 'present'}")
        print(f"    {r['citation']}")
        print()
    return 0


def _cmd_fetch_state(args: argparse.Namespace) -> int:
    fires = nifc.fetch_state(state=args.state, refresh=args.refresh)
    print(f"fetched {len(fires)} fires for state={args.state}")
    if args.out:
        n = nifc.to_jsonl(fires, Path(args.out))
        print(f"wrote {n} rows to {args.out}")
    return 0


def _cmd_fetch_gunnison(args: argparse.Namespace) -> int:
    fires = nifc.fetch_gunnison_county(refresh=args.refresh)
    print(f"fetched {len(fires)} fires in Gunnison County bbox")
    if args.out:
        n = nifc.to_jsonl(fires, Path(args.out))
        print(f"wrote {n} rows to {args.out}")
    for f in sorted(fires, key=lambda x: (x.year, x.start_date or ""), reverse=True)[:10]:
        print(f"  {f.year} {f.name[:40]:40s} {f.acres_burned:>10.1f} ac  ({f.cause or '?'})")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    """Export every cached source as JSONL into a directory."""
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for source in sources.HISTORIC_SOURCES:
        if source.fetch_strategy != "arcgis_rest":
            continue
        cached = nifc.load_cached(source.name)
        if not cached:
            continue
        path = out_dir / f"{source.name}.jsonl"
        n = nifc.to_jsonl(cached, path)
        total += n
        print(f"  {source.name:40s} -> {n} fires -> {path}")
    print(f"\ntotal cached fires exported: {total}")
    return 0


def _cmd_fixture(args: argparse.Namespace) -> int:
    fires = nifc.load_fixture()
    print(f"fixture: {len(fires)} synthetic fires")
    for f in fires:
        print(f"  {f.year} {f.name[:50]:50s} {f.acres_burned:>10.1f} ac")
    if args.out:
        n = nifc.to_jsonl(fires, Path(args.out))
        print(f"wrote {n} rows to {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="historic-fire ingester")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sources", help="list registered data sources")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=_cmd_sources)

    fs = sub.add_parser("fetch-state", help="fetch all NIFC fires for a state")
    fs.add_argument("--state", default="CO")
    fs.add_argument("--refresh", action="store_true")
    fs.add_argument("--out", help="write JSONL output")
    fs.set_defaults(func=_cmd_fetch_state)

    fg = sub.add_parser("fetch-gunnison", help="fetch NIFC fires in Gunnison County, CO")
    fg.add_argument("--refresh", action="store_true")
    fg.add_argument("--out", help="write JSONL output")
    fg.set_defaults(func=_cmd_fetch_gunnison)

    e = sub.add_parser("export", help="export all cached sources to JSONL files")
    e.add_argument("--out", required=True, help="output directory")
    e.set_defaults(func=_cmd_export)

    fx = sub.add_parser("fixture", help="dump bundled fixture (offline)")
    fx.add_argument("--out", help="write JSONL output")
    fx.set_defaults(func=_cmd_fixture)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
