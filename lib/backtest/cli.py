"""CLI for the backtest engine.

    python -m lib.backtest.cli demo
    python -m lib.backtest.cli run --year 2018 --year 2020
    python -m lib.backtest.cli summary --in /tmp/results.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from sapphire_integration.historical_fires import nifc

from . import engine

REPO_ROOT = Path(__file__).resolve().parents[2]
ZONES_GEOJSON = REPO_ROOT / "missions" / "zones" / "gunnison_crested_butte_corridor.geojson"


def _load_aor_polygons(geojson_path: Path) -> list[list[tuple[float, float]]]:
    """Load AOR polygons (lat, lon) from the canonical zones file."""
    if not geojson_path.exists():
        return []
    fc = json.loads(geojson_path.read_text(encoding="utf-8"))
    polys: list[list[tuple[float, float]]] = []
    for feature in fc.get("features") or []:
        props = feature.get("properties") or {}
        if props.get("exclusion"):
            continue
        geom = feature.get("geometry") or {}
        if geom.get("type") == "Polygon":
            coords = geom.get("coordinates") or []
            if not coords:
                continue
            ring = coords[0]
            polys.append([(p[1], p[0]) for p in ring])
        elif geom.get("type") == "MultiPolygon":
            for poly in geom.get("coordinates") or []:
                if not poly:
                    continue
                ring = poly[0]
                polys.append([(p[1], p[0]) for p in ring])
    return polys


def _cmd_demo(args: argparse.Namespace) -> int:
    fires = nifc.load_fixture()
    aor = _load_aor_polygons(ZONES_GEOJSON)
    results = engine.backtest_set(fires, aor_polygons=aor, n_trials_per_fire=args.trials)
    print(f"\nbacktest demo: {len(fires)} fires, {len(aor)} AOR polygons\n")
    for r in results:
        if r.in_fleet_aor and r.counterfactual_detection_minutes_after_ignition is not None:
            print(
                f"  {r.fire_year}  {r.fire_name[:38]:38s}  "
                f"{r.fire_acres_actual:>8.1f} ac actual  "
                f"-> would have detected at T+{r.counterfactual_detection_minutes_after_ignition:>5.1f} min  "
                f"({r.acres_saved_estimate or 0:>7.1f} ac saved)"
            )
        else:
            why = "out of AOR" if not r.in_fleet_aor else "would have missed"
            print(
                f"  {r.fire_year}  {r.fire_name[:38]:38s}  "
                f"{r.fire_acres_actual:>8.1f} ac actual  -> {why}"
            )

    summary = engine.summarize(results)
    print(f"\nsummary: {summary['rationale']}")
    if args.out:
        n = engine.to_jsonl(results, Path(args.out))
        print(f"\nwrote {n} backtest results to {args.out}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    fires = nifc.load_cached(args.source)
    if not fires:
        print(f"no cached fires found for source={args.source}; run fetch first", file=sys.stderr)
        return 1
    if args.year:
        fires = [f for f in fires if f.year in args.year]
    aor = _load_aor_polygons(ZONES_GEOJSON)
    fleet = engine.FleetConfig(
        n_drones=args.drones,
        revisit_interval_min=args.revisit,
        detection_prob_per_pass=args.dp,
    )
    results = engine.backtest_set(fires, fleet=fleet, aor_polygons=aor, n_trials_per_fire=args.trials)
    summary = engine.summarize(results)
    print(json.dumps({"summary": summary, "fleet": asdict(fleet)}, indent=2, default=str))
    if args.out:
        n = engine.to_jsonl(results, Path(args.out))
        print(f"\nwrote {n} results to {args.out}")
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    path = Path(args.in_file)
    if not path.exists():
        print(f"missing: {path}", file=sys.stderr)
        return 1
    rows = []
    for line in path.read_text(encoding="utf-8").strip().split("\n"):
        if line:
            rows.append(json.loads(line))
    # Reconstruct BacktestResult objects.
    results = [engine.BacktestResult(**r) for r in rows]
    s = engine.summarize(results)
    print(json.dumps(s, indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="historic-fire backtest engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="run the backtest against the bundled fixture")
    d.add_argument("--trials", type=int, default=100)
    d.add_argument("--out", help="write JSONL output")
    d.set_defaults(func=_cmd_demo)

    r = sub.add_parser("run", help="run against a cached source")
    r.add_argument("--source", default="nifc_wfigs_perimeters")
    r.add_argument("--year", type=int, action="append")
    r.add_argument("--drones", type=int, default=3)
    r.add_argument("--revisit", type=float, default=12.0)
    r.add_argument("--dp", type=float, default=0.78)
    r.add_argument("--trials", type=int, default=100)
    r.add_argument("--out")
    r.set_defaults(func=_cmd_run)

    s = sub.add_parser("summary", help="summarize a JSONL result file")
    s.add_argument("--in", dest="in_file", required=True)
    s.set_defaults(func=_cmd_summary)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
