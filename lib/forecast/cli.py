"""CLI for the forward-projection scout-target ranker.

    python -m lib.forecast.cli rank
    python -m lib.forecast.cli rank --year 2026 --out /tmp/targets.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sapphire_integration.historical_fires import nifc

from . import ranker

REPO_ROOT = Path(__file__).resolve().parents[2]
ZONES_GEOJSON = REPO_ROOT / "missions" / "zones" / "gunnison_crested_butte_corridor.geojson"


def _cmd_rank(args: argparse.Namespace) -> int:
    if not ZONES_GEOJSON.exists():
        print(f"missing zones GeoJSON: {ZONES_GEOJSON}", file=sys.stderr)
        return 1
    zones = json.loads(ZONES_GEOJSON.read_text(encoding="utf-8"))

    fires = nifc.load_cached(args.source)
    if not fires and args.use_fixture:
        fires = nifc.load_fixture()
    if not fires:
        print("no cached fires available; pass --use-fixture for offline demo", file=sys.stderr)
        return 1

    targets = ranker.rank_zones(zones, fires=fires, current_year=args.year)
    print(f"\nranked scout targets ({len(targets)} patrolable zones, year={args.year}):\n")
    for t in targets:
        print(
            f"  {t.priority_score:>5.1f}  {t.zone_id:<35s}  "
            f"fuel={t.fuel_load_class:<14s}  "
            f"history={t.historical_fire_count} fires "
            f"({t.historical_acres_total:>7.0f} ac)  "
            f"->  revisit every {t.recommended_revisit_min:.0f} min"
        )
        print(f"        {t.rationale}")

    summary = ranker.summarize(targets)
    print()
    print(
        f"summary: {summary['total_zones']} zones | "
        f"{summary['patrolled_zones']} priority-patrol | "
        f"{summary['total_aor_km2']:.2f} km² total | "
        f"weighted-mean priority {summary['weighted_priority_mean']:.1f} | "
        f"top: {summary['top_zone_id']} (score {summary['top_zone_score']:.1f}, "
        f"every {summary['top_zone_revisit_min']:.0f}min)"
    )

    if args.out:
        n = ranker.to_jsonl(targets, Path(args.out))
        print(f"\nwrote {n} ranked targets to {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="forward-projection scout-target ranker")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("rank", help="rank inclusion zones by priority score")
    r.add_argument("--source", default="nifc_wfigs_perimeters")
    r.add_argument("--use-fixture", action="store_true", default=True)
    r.add_argument("--year", type=int, default=2026)
    r.add_argument("--out")
    r.set_defaults(func=_cmd_rank)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
