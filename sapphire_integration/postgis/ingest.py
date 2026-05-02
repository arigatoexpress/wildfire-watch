"""Ingest wildfire_signals into PostGIS.

Reads JSONL from `~/Code/Sapphire/data/wildfire_signals.jsonl` (or any path
specified) and INSERTs each row into `wfw.wildfire_signal` with idempotency
on `signal_id`. Also seeds `wfw.drone`, `wfw.zone`, `wfw.fire_department_unit`
from local sources of truth.

Stdlib + lazy-imported `psycopg` only. Falls back to a dry-run mode if
psycopg isn't available — this is a developer convenience tool, not
production critical-path.

Usage:
    python -m sapphire_integration.postgis.ingest seed-zones \
        --geojson missions/zones/gunnison_crested_butte_corridor.geojson

    python -m sapphire_integration.postgis.ingest seed-fire-depts

    python -m sapphire_integration.postgis.ingest seed-drone wfw-unit01 mavic_mini_2

    python -m sapphire_integration.postgis.ingest signals \
        --jsonl ~/Code/Sapphire/data/wildfire_signals.jsonl

    python -m sapphire_integration.postgis.ingest signals --dry-run --jsonl /path/to.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


DEFAULT_DSN = os.environ.get(
    "WFW_PG_DSN", "postgres://wfw:wfw@localhost:5432/wildfire_watch"
)


def _connect(dsn: str):
    """Lazy-import psycopg + connect. Raises if dry-run is needed."""
    import psycopg  # type: ignore

    return psycopg.connect(dsn, autocommit=True)


def seed_zones(args) -> int:
    geojson_path = Path(args.geojson).expanduser().resolve()
    feature_collection = json.loads(geojson_path.read_text())
    corridor = feature_collection.get("name", geojson_path.stem)

    inserts: list[tuple] = []
    for feat in feature_collection.get("features") or []:
        props = feat.get("properties") or {}
        zone_id = props.get("zone_id")
        if not zone_id:
            continue
        inserts.append(
            (
                zone_id,
                corridor,
                json.dumps(feat.get("geometry") or {}),
                props.get("fuel_load_class", "moderate"),
                props.get("primary_risk", "unknown"),
                float(props.get("elevation_min_m", 0.0)),
                float(props.get("elevation_max_m", 0.0)),
                bool(props.get("exclusion", False)),
                props.get("regulatory_basis"),
            )
        )

    if args.dry_run:
        print(f"[dry-run] would seed {len(inserts)} zones from {geojson_path.name}")
        for row in inserts:
            print(f"  zone_id={row[0]} fuel={row[3]} exclusion={row[7]}")
        return 0

    sql = """
    INSERT INTO wfw.zone (
        zone_id, corridor, polygon, fuel_load_class, primary_risk,
        elevation_min_m, elevation_max_m, is_exclusion, regulatory_basis
    ) VALUES (
        %s, %s, ST_GeogFromGeoJSON(%s), %s, %s, %s, %s, %s, %s
    )
    ON CONFLICT (zone_id) DO UPDATE SET
        corridor = EXCLUDED.corridor,
        polygon = EXCLUDED.polygon,
        fuel_load_class = EXCLUDED.fuel_load_class,
        primary_risk = EXCLUDED.primary_risk,
        elevation_min_m = EXCLUDED.elevation_min_m,
        elevation_max_m = EXCLUDED.elevation_max_m,
        is_exclusion = EXCLUDED.is_exclusion,
        regulatory_basis = EXCLUDED.regulatory_basis;
    """

    conn = _connect(args.dsn)
    with conn.cursor() as cur:
        cur.executemany(sql, inserts)
    print(f"seeded {len(inserts)} zones from {geojson_path.name}")
    return 0


def seed_fire_depts(args) -> int:
    """Seed the canonical Gunnison-corridor partner agencies (from AOR.md)."""
    fire_depts: list[dict[str, Any]] = [
        {
            "unit_id": "cbfpd",
            "name": "Crested Butte Fire Protection District",
            "primary_contact_role": "Fire Chief",
            "dispatch_phone": "(970) 349-5333",
            "physical_address": "700 6th Street, Crested Butte, CO 81224",
        },
        {
            "unit_id": "gcfpd",
            "name": "Gunnison County Fire Protection District",
            "primary_contact_role": "Fire Chief",
            "physical_address": "200 W Tomichi Ave, Gunnison, CO 81230",
        },
        {
            "unit_id": "mt-cbfpd",
            "name": "Mt. Crested Butte Fire Protection District",
            "primary_contact_role": "Fire Chief",
        },
        {
            "unit_id": "gmug-gunnison-rd",
            "name": "GMUG National Forest - Gunnison Ranger District",
            "primary_contact_role": "District Ranger",
            "physical_address": "216 N Colorado St, Gunnison, CO 81230",
        },
        {
            "unit_id": "co-dfpc",
            "name": "Colorado Division of Fire Prevention and Control",
            "primary_contact_role": "Wildland Operations",
        },
    ]

    if args.dry_run:
        print(f"[dry-run] would seed {len(fire_depts)} fire departments")
        for fd in fire_depts:
            print(f"  unit_id={fd['unit_id']:<20} name={fd['name']}")
        return 0

    sql = """
    INSERT INTO wfw.fire_department_unit (
        unit_id, name, primary_contact_role,
        dispatch_phone, physical_address, engagement_status
    ) VALUES (%s, %s, %s, %s, %s, 'not_contacted')
    ON CONFLICT (unit_id) DO NOTHING;
    """

    conn = _connect(args.dsn)
    with conn.cursor() as cur:
        for fd in fire_depts:
            cur.execute(
                sql,
                (
                    fd["unit_id"],
                    fd["name"],
                    fd.get("primary_contact_role"),
                    fd.get("dispatch_phone"),
                    fd.get("physical_address"),
                ),
            )
    print(f"seeded {len(fire_depts)} fire departments")
    return 0


def seed_drone(args) -> int:
    if args.dry_run:
        print(f"[dry-run] would seed drone {args.drone_id} (class {args.airframe_class})")
        return 0

    sql = """
    INSERT INTO wfw.drone (drone_id, airframe_class, blue_uas_status)
    VALUES (%s, %s, %s)
    ON CONFLICT (drone_id) DO UPDATE SET
        airframe_class = EXCLUDED.airframe_class,
        blue_uas_status = EXCLUDED.blue_uas_status;
    """

    blue_status = {
        "mavic_mini_2": "non_eligible",
        "holybro_x500_v2": "substitutable",
        "skydio_x10": "cleared",
        "teal_2": "cleared",
        "parrot_anafi_usa_gov": "cleared",
        "sim_only": "unknown",
        "generic_quad": "unknown",
    }.get(args.airframe_class, "unknown")

    conn = _connect(args.dsn)
    with conn.cursor() as cur:
        cur.execute(sql, (args.drone_id, args.airframe_class, blue_status))
    print(f"seeded drone {args.drone_id}")
    return 0


def ingest_signals(args) -> int:
    jsonl_path = Path(args.jsonl).expanduser().resolve()
    if not jsonl_path.exists():
        print(f"jsonl not found: {jsonl_path}", file=sys.stderr)
        return 2

    rows = []
    with jsonl_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                v1 = json.loads(line)
            except json.JSONDecodeError:
                continue
            coords = v1.get("coords") or {}
            target = v1.get("target_coords") or {}
            consensus = v1.get("consensus") or {}
            peers = consensus.get("peer_drone_ids") or []
            rows.append(
                (
                    v1["signal_id"],
                    v1["drone_id"],
                    v1["zone_id"],
                    None,  # flight_id (not yet linked)
                    v1["timestamp"],
                    coords.get("lon"),
                    coords.get("lat"),
                    coords.get("alt_msl_m") or coords.get("alt_agl_m") or 0,
                    target.get("lon"),
                    target.get("lat"),
                    target.get("alt_msl_m") or 0,
                    v1["signal_type"],
                    v1.get("signal_subtype"),
                    float(v1["confidence"]),
                    float(v1["risk_score"]),
                    v1["recommended_action"],
                    list(peers),
                    v1.get("schema_version", "1.0.0"),
                    json.dumps(v1, separators=(",", ":")),
                )
            )

    if args.dry_run:
        print(f"[dry-run] would ingest {len(rows)} signals from {jsonl_path.name}")
        return 0

    sql = """
    INSERT INTO wfw.wildfire_signal (
        signal_id, drone_id, zone_id, flight_id, timestamp,
        location, target_location,
        signal_type, signal_subtype, confidence, risk_score,
        recommended_action, consensus_peers, schema_version, raw_payload
    ) VALUES (
        %s, %s, %s, %s, %s,
        ST_SetSRID(ST_MakePoint(%s, %s, %s), 4326)::geography,
        CASE WHEN %s IS NULL OR %s IS NULL THEN NULL
             ELSE ST_SetSRID(ST_MakePoint(%s, %s, %s), 4326)::geography
        END,
        %s, %s, %s, %s, %s, %s, %s, %s
    )
    ON CONFLICT (signal_id) DO NOTHING;
    """

    conn = _connect(args.dsn)
    inserted = 0
    with conn.cursor() as cur:
        for row in rows:
            (
                sig_id, drone_id, zone_id, flight_id, ts,
                lon, lat, alt,
                t_lon, t_lat, t_alt,
                stype, subtype, conf, risk,
                rec, peers, schema_v, raw,
            ) = row
            cur.execute(
                sql,
                (
                    sig_id, drone_id, zone_id, flight_id, ts,
                    lon, lat, alt,
                    t_lon, t_lat, t_lon, t_lat, t_alt,
                    stype, subtype, conf, risk,
                    rec, peers, schema_v, raw,
                ),
            )
            if cur.rowcount > 0:
                inserted += 1
    print(f"ingested {inserted} of {len(rows)} signals (rest were duplicates)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="wildfire-watch PostGIS ingest tool")
    p.add_argument("--dsn", default=DEFAULT_DSN, help=f"Postgres DSN (default: {DEFAULT_DSN})")
    p.add_argument("--dry-run", action="store_true", help="don't write; show what would be done")

    sub = p.add_subparsers(dest="cmd", required=True)

    sz = sub.add_parser("seed-zones")
    sz.add_argument("--geojson", required=True)
    sz.set_defaults(func=seed_zones)

    sf = sub.add_parser("seed-fire-depts")
    sf.set_defaults(func=seed_fire_depts)

    sd = sub.add_parser("seed-drone")
    sd.add_argument("drone_id")
    sd.add_argument("airframe_class")
    sd.set_defaults(func=seed_drone)

    si = sub.add_parser("signals")
    si.add_argument("--jsonl", required=True)
    si.set_defaults(func=ingest_signals)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
