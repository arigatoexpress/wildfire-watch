# PostGIS — wildfire-watch system of record

Per `docs/intel/foundry-research-2026-05-01.md` Section 6 ("buy-vs-build"), the wildfire-watch system of record is **PostgreSQL 16 + PostGIS 3.4**, with Foundry's Developer Tier (when approved) acting as the ontology + AIP demo layer on top. This subtree provisions the database, the schema, and the ingestion path.

## Files

| Path | Purpose |
|---|---|
| `init.sql` | Full schema. Six tables + 2 views + 1 spatial function. Mirrors the Foundry ontology in `../foundry/ontology.py`. |
| `docker-compose.yml` | Local dev: brings up PostgreSQL 16 + PostGIS 3.4 on `localhost:5432`. |
| `ingest.py` | CLI that seeds zones (from GeoJSON) + fire departments (from AOR.md) + drones, and ingests v1 wildfire_signals from JSONL into the relational schema. |

## Quick start

```bash
cd ~/Code/wildfire-watch/sapphire_integration/postgis

# 1. Bring up the database
docker compose up -d
sleep 5  # wait for postgres to come up

# 2. Verify schema
psql postgres://wfw:wfw@localhost:5432/wildfire_watch -c "\dt wfw.*"

# 3. Seed canonical Gunnison-corridor zones
python3 -m sapphire_integration.postgis.ingest seed-zones \
    --geojson missions/zones/gunnison_crested_butte_corridor.geojson

# 4. Seed partner fire departments
python3 -m sapphire_integration.postgis.ingest seed-fire-depts

# 5. Seed a drone (Mavic Mini for Phase 0; sim drones for sim runs)
python3 -m sapphire_integration.postgis.ingest seed-drone wfw-unit01 mavic_mini_2

# 6. Ingest signals from the Sapphire bridge (or from a sim run)
python3 -m sapphire_integration.postgis.ingest signals \
    --jsonl ~/Code/Sapphire/data/wildfire_signals.jsonl

# 7. Operational query: signals within 5 km of CBFPD HQ
psql postgres://wfw:wfw@localhost:5432/wildfire_watch <<SQL
SELECT signal_id, signal_type, risk_score, timestamp
FROM wfw.signals_within(38.8697, -106.9878, 5000)
LIMIT 10;
SQL

# 8. Geofence breach view
psql postgres://wfw:wfw@localhost:5432/wildfire_watch -c \
    "SELECT * FROM wfw.geofence_breaches ORDER BY timestamp DESC LIMIT 10;"
```

## Schema

`wfw.drone` `wfw.zone` `wfw.fire_department_unit` `wfw.flight_log` `wfw.battery_cycle` `wfw.wildfire_signal` plus views `wfw.signals_24h_by_zone` `wfw.geofence_breaches` and the spatial helper `wfw.signals_within(lat, lon, radius_m)`.

Every signal is **idempotent on `signal_id`** (drone-side UUIDv4) — `INSERT ... ON CONFLICT DO NOTHING` is the contract. This matches the Sapphire bridge.

`wfw.geofence_breaches` is a view that surfaces signals whose location fell inside a registered exclusion zone (e.g. West Elk Wilderness). Useful as a near-real-time audit signal.

## Production posture

Local docker-compose is **dev only**. For production:
- Use Cloud SQL (GCP, since Sapphire already lives there) or RDS (AWS).
- Inject credentials via Secret Manager — **don't** use the `wfw:wfw` default.
- Enable automated backups + PITR.
- Enable `pg_stat_statements` for query profiling.
- TLS-only connections (`sslmode=require` in DSN).
- Tighten the `CHECK` constraints with regulatory_basis enums once the wilderness exclusion list is finalized.

## Foundry sync

Once the Foundry Developer Tier is approved (per the outreach kit's email 5), the existing Sapphire `lib/foundry/sync.py` daemon picks up wildfire_signals from this Postgres table and pushes them into `wfw.WildfireSignal` ontology objects in Foundry on a 15-minute delta-aware schedule. No code changes needed in Sapphire — the daemon is parameterized.

The Foundry ontology objects are defined in `../foundry/ontology.py`. They round-trip cleanly with the Postgres rows because both sides use the v1 wildfire_signal payload as the `raw_payload` field; the indexed columns are derived from it.

## Why this isn't a hard dependency

Wildfire-watch core (sim, web viewer, swarm, perception, TAK, valuation) does not require Postgres. Phase 0 reads/writes the JSONL directly. Postgres is the **next-tier** persistence — drop it in once flight volumes warrant a real query layer (anything more than a few thousand signals).
